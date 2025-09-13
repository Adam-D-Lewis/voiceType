import time

from loguru import logger
from pynput.keyboard import Controller


def type_text(text):
    keyboard = Controller()

    # Type each character in the text
    for char in text:
        keyboard.tap(char)
        time.sleep(0.001)  # Adjust the delay between keypresses if needed  # noqa: F821

    # Press Enter key at the end
    keyboard.press("\n")
    keyboard.release("\n")


# def play_audio(filename):
#     # Open the file for reading.
#     with filename.open('rb') as f:
#         wav = wave.open(f, 'rb')

#         # Create an interface to PortAudio.
#         pa = pyaudio.PyAudio()

#         # Open a .Stream object to write the WAV file to.
#         # 'output = True' indicates that the sound will be outputted to the speaker.
#         # 'rate' is the sample rate from the wav file, which we set as the rate of the output stream.
#         # 'channels' is also set using the method getnchannels().
#         # 'format' we get from a lookup dictionary provided by PyAudio containing the appropriate format for the sample width returned from the wave file.
#         stream = pa.open(
#             format = pa.get_format_from_width(wav.getsampwidth()),
#             channels = wav.getnchannels(),
#             rate = wav.getframerate(),
#             output = True
#         )

#         # CHUNK size
#         CHUNK = 1024

#         # Read data in chunks
#         data = wav.readframes(CHUNK)

#         # Play the sound by writing the audio data to the stream.
#         while data != b'':
#             stream.write(data)
#             data = wav.readframes(CHUNK)

#         # Close and terminate everything properly.
#         stream.stop_stream()
#         stream.close()
#         pa.terminate()


def play_sound(sound_path):
    """Play a sound file using playsound3 with threading to avoid blocking.

    Args:
        sound_path: Path to the sound file to play
    """
    import threading
    from pathlib import Path

    def _play_sound_thread():
        try:
            from playsound3 import playsound

            sound_file = Path(sound_path)
            if not sound_file.exists():
                logger.warning(f"Sound file does not exist: {sound_file}")
                return

            logger.debug(f"Playing sound: {sound_file}")
            playsound(str(sound_file), block=True)
        except Exception as e:
            logger.error(f"Failed to play sound {sound_path}: {e}")

    # Each sound gets its own thread - simpler and more reliable
    threading.Thread(target=_play_sound_thread, daemon=True).start()
