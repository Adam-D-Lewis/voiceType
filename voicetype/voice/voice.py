# import math # No longer needed directly
import os
import sys # For stderr output
import queue
import threading
import tempfile
import time
import warnings
import numpy as np

# Remove prompt_toolkit as it's no longer used for blocking input
# from prompt_toolkit.shortcuts import prompt

from aider.llm import litellm

from .dump import dump  # noqa: F401

warnings.filterwarnings(
    "ignore", message="Couldn't find ffmpeg or avconv - defaulting to ffmpeg, but may not work"
)
warnings.filterwarnings("ignore", category=SyntaxWarning)


from pydub import AudioSegment  # noqa
from pydub.exceptions import CouldntDecodeError, CouldntEncodeError  # noqa

try:
    import soundfile as sf
except (OSError, ModuleNotFoundError):
    sf = None


class SoundDeviceError(Exception):
    pass


class Voice:
    max_rms = 0
    min_rms = 1e5
    pct = 0.0  # Initialize pct

    threshold = 0.15 # Threshold for RMS visualization (if needed later)

    def __init__(self, audio_format="wav", device_name=None):
        if sf is None:
            raise SoundDeviceError("SoundFile library not available.")
        try:
            print("Initializing sound device...")
            import sounddevice as sd
            self.sd = sd
        except (OSError, ModuleNotFoundError) as e:
            raise SoundDeviceError(f"SoundDevice library error: {e}")

        self.device_id = self._find_device_id(device_name)
        print(f"Using input device ID: {self.device_id}")

        if audio_format not in ["wav", "mp3", "webm"]:
            raise ValueError(f"Unsupported audio format: {audio_format}")
        self.audio_format = audio_format

        try:
            device_info = self.sd.query_devices(self.device_id, "input")
            self.sample_rate = int(device_info["default_samplerate"])
            print(f"Using sample rate: {self.sample_rate} Hz")
        except (TypeError, ValueError, KeyError) as e:
            print(f"Warning: Could not query default sample rate ({e}), falling back to 16kHz.")
            self.sample_rate = 16000
        except self.sd.PortAudioError as e:
            raise SoundDeviceError(f"PortAudio error querying device: {e}")

        self.q = queue.Queue()
        self.stream = None
        self.audio_file = None
        self.temp_wav = None
        self.is_recording = False
        self.start_time = None
        self._stop_event = threading.Event() # Used to signal the callback to stop processing

    def _find_device_id(self, device_name):
        """Helper to find the input device ID."""
        devices = self.sd.query_devices()
        if not devices:
            raise SoundDeviceError("No audio devices found.")

        input_devices = [(i, d) for i, d in enumerate(devices) if d["max_input_channels"] > 0]
        if not input_devices:
            raise SoundDeviceError("No audio input devices found.")

        if device_name:
            for i, device in input_devices:
                if device_name.lower() in device["name"].lower():
                    print(f"Found specified device: {device['name']} (ID: {i})")
                    return i
            available_names = [d["name"] for _, d in input_devices]
            raise ValueError(
                f"Device '{device_name}' not found. Available input devices: {available_names}"
            )
        else:
            # Return default input device ID if available
            try:
                default_device_id = self.sd.default.device[0] # 0 is input index
                if default_device_id != -1 and devices[default_device_id]["max_input_channels"] > 0:
                     print(f"Using default input device: {devices[default_device_id]['name']} (ID: {default_device_id})")
                     return default_device_id
                else: # Default is invalid or not an input device
                    print("Warning: Default input device is invalid or not found.")
            except Exception as e:
                 print(f"Warning: Could not get default input device ({e}).")

            # Fallback: return the first available input device
            first_input_id, first_input_device = input_devices[0]
            print(f"Falling back to first available input device: {first_input_device['name']} (ID: {first_input_id})")
            return first_input_id


    def callback(self, indata, frames, time_info, status):
        """This is called (from a separate thread) for each audio block."""
        if status:
            print(f"Audio callback status: {status}", file=sys.stderr)
        if self._stop_event.is_set(): # Check if stop signal received
             raise self.sd.CallbackStop # Signal sounddevice to stop the callback chain
        try:
            rms = np.sqrt(np.mean(indata**2))
            # Update RMS tracking (optional, could be used for visual feedback)
            self.max_rms = max(self.max_rms, rms)
            self.min_rms = min(self.min_rms, rms)

            rng = self.max_rms - self.min_rms
            if rng > 0.001:
                self.pct = (rms - self.min_rms) / rng
            else:
                self.pct = 0.5 # Avoid division by zero if range is tiny

            self.q.put(indata.copy())
        except Exception as e:
            print(f"Error in audio callback: {e}", file=sys.stderr)
            # Decide if the error is critical enough to stop recording
            # For now, just print it.

    # Removed get_prompt method as it's no longer used
    # def get_prompt(self): ...

    def start_recording(self):
        """Starts recording audio."""
        if self.is_recording:
            print("Already recording.")
            return

        print("Starting recording...")
        self.max_rms = 0 # Reset RMS tracking
        self.min_rms = 1e5
        self.pct = 0.0
        self._stop_event.clear() # Ensure stop event is clear

        try:
            self.temp_wav = tempfile.mktemp(suffix=".wav")
            self.audio_file = sf.SoundFile(
                self.temp_wav, mode="x", samplerate=self.sample_rate, channels=1
            )
            self.stream = self.sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                callback=self.callback,
                device=self.device_id,
                blocksize=int(self.sample_rate * 0.1) # Process in 100ms chunks
            )
            self.stream.start()
            self.start_time = time.time()
            self.is_recording = True
            print(f"Recording started, saving to {self.temp_wav}")
        except self.sd.PortAudioError as e:
            self.is_recording = False # Ensure state is correct
            if self.audio_file:
                self.audio_file.close()
                self.audio_file = None
            if os.path.exists(self.temp_wav):
                 os.remove(self.temp_wav)
                 self.temp_wav = None
            raise SoundDeviceError(f"Failed to start audio stream: {e}")
        except Exception as e:
            self.is_recording = False
            if self.audio_file:
                self.audio_file.close()
                self.audio_file = None
            if self.temp_wav and os.path.exists(self.temp_wav):
                 os.remove(self.temp_wav)
                 self.temp_wav = None
            print(f"An unexpected error occurred during start_recording: {e}")
            raise # Re-raise the exception

    def stop_recording(self):
        """Stops recording audio and returns the path to the saved WAV file."""
        if not self.is_recording:
            print("Not recording.")
            return None

        print("Stopping recording...")
        self._stop_event.set() # Signal callback to stop processing queue

        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
                print("Audio stream stopped and closed.")
            except self.sd.PortAudioError as e:
                print(f"Warning: PortAudioError stopping/closing stream: {e}")
            except Exception as e:
                 print(f"Warning: Unexpected error stopping/closing stream: {e}")
            finally:
                self.stream = None

        # Process any remaining items in the queue after stopping the stream
        print(f"Processing remaining audio data (queue size: {self.q.qsize()})...")
        while not self.q.empty():
            try:
                data = self.q.get_nowait()
                if self.audio_file and not self.audio_file.closed:
                    self.audio_file.write(data)
            except queue.Empty:
                break # Should not happen with while not self.q.empty()
            except Exception as e:
                 print(f"Error writing remaining audio data: {e}")


        if self.audio_file:
            try:
                self.audio_file.close()
                print(f"Audio file closed: {self.temp_wav}")
            except Exception as e:
                print(f"Warning: Error closing audio file: {e}")
            finally:
                self.audio_file = None

        recorded_filename = self.temp_wav
        self.temp_wav = None # Clear temp path
        self.is_recording = False
        self.start_time = None
        print("Recording stopped.")
        return recorded_filename

    def transcribe(self, filename, history=None, language=None):
        """Transcribes the audio file using the configured model."""
        if not filename or not os.path.exists(filename):
            print(f"Error: Audio file not found or invalid: {filename}")
            return None

        print(f"Transcribing {filename}...")
        final_filename = filename
        use_audio_format = self.audio_format

        # Check file size and offer to convert if too large and format is wav
        file_size = os.path.getsize(filename)
        if file_size > 24.9 * 1024 * 1024 and self.audio_format == "wav":
            print(f"\nWarning: {filename} ({file_size / (1024*1024):.1f} MB) may be too large for some APIs, converting to mp3.")
            use_audio_format = "mp3"

        # Convert if necessary
        if use_audio_format != "wav":
            try:
                new_filename = tempfile.mktemp(suffix=f".{use_audio_format}")
                print(f"Converting {filename} to {use_audio_format}...")
                audio = AudioSegment.from_wav(filename)
                audio.export(new_filename, format=use_audio_format)
                print(f"Conversion successful: {new_filename}")
                # Keep original wav for now, transcribe the converted file
                final_filename = new_filename
            except (CouldntDecodeError, CouldntEncodeError) as e:
                print(f"Error converting audio to {use_audio_format}: {e}. Will attempt transcription with original WAV.")
                final_filename = filename # Fallback to original wav
            except (OSError, FileNotFoundError) as e:
                print(f"File system error during conversion: {e}. Will attempt transcription with original WAV.")
                final_filename = filename
            except Exception as e:
                print(f"Unexpected error during audio conversion: {e}. Will attempt transcription with original WAV.")
                final_filename = filename

        # Transcribe
        transcript_text = None
        try:
            with open(final_filename, "rb") as fh:
                transcript = litellm.transcription(
                    model="whisper-1", file=fh, prompt=history, language=language
                )
                transcript_text = transcript.text
                print("Transcription successful.")
        except Exception as err:
            print(f"Error during transcription of {final_filename}: {err}")
            transcript_text = None # Ensure it's None on error

        # Cleanup
        if final_filename != filename: # If conversion happened, remove the converted file
            try:
                os.remove(final_filename)
                print(f"Cleaned up temporary converted file: {final_filename}")
            except OSError as e:
                print(f"Warning: Could not remove temporary converted file {final_filename}: {e}")

        # Always remove the original temporary WAV file
        try:
            os.remove(filename)
            print(f"Cleaned up original recording file: {filename}")
        except OSError as e:
            print(f"Warning: Could not remove original recording file {filename}: {e}")


        return transcript_text


    # --- Old methods removed ---
    # def record_and_transcribe(self, history=None, language=None): ...
    # def raw_record_and_transcribe(self, history, language): ...

# --- Example Usage ---
if __name__ == "__main__":
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("Please set the OPENAI_API_KEY environment variable.")

    try:
        # Initialize with default device
        # You can specify a device name like: voice = Voice(device_name="USB PnP Audio Device")
        voice = Voice()

        # Start recording
        voice.start_recording()

        # Simulate recording duration (e.g., 5 seconds)
        print("Recording for 5 seconds...")
        time.sleep(5)

        # Stop recording and get the filename
        audio_filename = voice.stop_recording()

        if audio_filename:
            # Transcribe the recorded audio
            transcribed_text = voice.transcribe(audio_filename)

            if transcribed_text:
                print("\n--- Transcription ---")
                print(transcribed_text)
            else:
                print("\nTranscription failed.")
        else:
            print("\nRecording failed or was stopped prematurely.")

    except SoundDeviceError as e:
        print(f"\nSound device error: {e}")
        print("Please ensure you have a working audio input device and necessary libraries (PortAudio, sounddevice, SoundFile).")
    except ValueError as e:
        print(f"\nConfiguration error: {e}")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
