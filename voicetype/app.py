from typing import List, Union

from fastapi import Depends, FastAPI, HTTPException
from .utils import play_audio, type_text, make_sound_thread
from pathlib import Path
import speech_recognition as sr

from .sounds import ERROR_SOUND, START_RECORD_SOUND

_HERE = Path(__file__).resolve().parent

app = FastAPI()

# global variables
source = None
recognizer = None

@app.on_event("startup")
def initialize():
    global source, recognizer
    print('Initializing...')
    source = sr.Microphone()
    recognizer = sr.Recognizer()
    
    # Adjust ambient noise threshold, if needed
    with source:
        recognizer.adjust_for_ambient_noise(source)


def main(): 
    global source, recognizer
    with source:
        print('playing START_RECORD_SOUND')
        make_sound_thread(START_RECORD_SOUND).start()

        # Record the audio
        print("Listening...")
        audio = recognizer.listen(
            source, 
            timeout=5, 
            phrase_time_limit=10
        )
        print('done listening')
        try:
            # Perform speech recognition
            text = recognizer.recognize_google(audio)

            # Print the recognized text
            print("Detected Speech:", text)
            type_text(text)
            
        except sr.UnknownValueError as e:
            make_sound_thread(ERROR_SOUND).start()
            print("Unable to recognize speech")
            with open(_HERE.joinpath('error_log.txt'), "a") as error_file:
                error_file.write(str(e) + '\n')

@app.on_event("shutdown")
def finalize():
    global source, recognizer
    print('Finalizing...')
    del source, recognizer


@app.get("/")
def voice_type():
    return main()

