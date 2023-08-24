from threading import Thread
import wave

import pyaudio
from pynput.keyboard import Controller

def type_text(text):
    keyboard = Controller()

    # Give some time for the user to focus on the input field
    # time.sleep(2)

    # Type each character in the text
    for char in text:
        keyboard.press(char)
        keyboard.release(char)
        # time.sleep(0.1)  # Adjust the delay between keypresses if needed

    # Press Enter key at the end
    keyboard.press('\n')
    keyboard.release('\n')


def play_audio(filename):
    # Open the file for reading.
    wav = wave.open(filename, 'rb')

    # Create an interface to PortAudio.
    pa = pyaudio.PyAudio()

    # Open a .Stream object to write the WAV file to.
    # 'output = True' indicates that the sound will be outputted to the speaker.
    # 'rate' is the sample rate from the wav file, which we set as the rate of the output stream.
    # 'channels' is also set using the method getnchannels().
    # 'format' we get from a lookup dictionary provided by PyAudio containing the appropriate format for the sample width returned from the wave file.
    stream = pa.open(
        format = pa.get_format_from_width(wav.getsampwidth()),
        channels = wav.getnchannels(),
        rate = wav.getframerate(),
        output = True
    )

    # CHUNK size
    CHUNK = 1024

    # Read data in chunks
    data = wav.readframes(CHUNK)

    # Play the sound by writing the audio data to the stream.
    while data != b'':
        stream.write(data)
        data = wav.readframes(CHUNK)

    # Close and terminate everything properly.
    stream.stop_stream()
    stream.close()
    pa.terminate()

def make_sound_thread(filepath):
    sound_file_path = str(filepath)
    thread = Thread(
        target=play_audio, 
        args=(sound_file_path,)
    )
    return thread
