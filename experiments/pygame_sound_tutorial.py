# I didn't get this working yet
import math
import time

import pygame


def play_sound_pygame(file_path, duration_sec):
    """
    Plays a sound file for a specified duration using pygame.
    If the sound file is shorter than duration_sec, it plays to completion.
    If longer, it's cut off after duration_sec.
    """
    pygame.mixer.init()  # Initialize the mixer module

    try:
        sound = pygame.mixer.Sound(file_path)
        print(f"Playing {file_path} for up to {duration_sec} second(s)...")
        sound.play()
        time.sleep(duration_sec)  # Let the sound play for the specified duration
        sound.stop()  # Stop the sound
        print("Sound stopped (or finished if shorter than the duration).")
    except pygame.error as e:
        print(f"Error playing sound with pygame: {e}")
        print(
            "Please ensure you have a valid audio file and pygame is installed correctly."
        )
        print(
            "For MP3 support on some systems, pygame's underlying SDL_mixer library might need MP3 support enabled."
        )
    finally:
        pygame.mixer.quit()  # Clean up the mixer


if __name__ == "__main__":
    # Replace 'your_sound_file.mp3' or 'your_sound_file.wav' with the path to your sound file.
    # This example assumes you have a sound file named 'test_sound.wav' in the same directory.
    # You'll need to create or provide your own sound file.
    sound_file = (
        "../voicetype/sounds/start-record.wav"  # <<< REPLACE THIS WITH YOUR FILE
    )
    try:
        # Create a dummy WAV file for testing if you don't have one
        # This requires 'wave' and 'audioop' modules (standard library)
        import audioop
        import wave

        sample_rate = 44100
        duration = 2  # seconds
        frequency = 440  # Hz (A4 note)
        n_frames = int(sample_rate * duration)
        amplitude = 16000  # 16-bit audio
        data = b""
        for i in range(n_frames):
            angle = 2 * 3.1415926535 * frequency * i / sample_rate
            sample = int(
                amplitude
                * (0.5 * (1 + (lambda x: x / abs(x) if x != 0 else 0)(math.sin(angle))))
            )  # Basic square wave for simplicity
            data += audioop.int2byte(sample, 2)  # 2 bytes for 16-bit

        with wave.open(sound_file, "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(data)
        print(f"Created a dummy sound file: {sound_file}")

        play_sound_pygame(sound_file, 1.0)  # Play for 1 second

    except ImportError:
        print(
            "Could not create a dummy WAV file as 'wave' or 'audioop' module is not available, or math is not imported."
        )
        print(f"Please create a sound file named '{sound_file}' manually to test.")
    except FileNotFoundError:
        print(
            f"Please ensure the sound file '{sound_file}' exists or provide the correct path."
        )
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
