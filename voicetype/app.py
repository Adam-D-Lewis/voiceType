from typing import List, Union

from fastapi import Depends, FastAPI, HTTPException
from utils import play_audio, type_text, make_sound_thread
from pathlib import Path
import speech_recognition as sr

from threading import Thread
import wave

from .sounds import ERROR_SOUND, START_RECORD_SOUND

_HERE = Path(__file__).resolve().parent

app = FastAPI()

@app.on_event("startup")
def startup_event():
    print("Startup: Initialize your resources here.")


# global variables
source = None
recognizer = None


def initialize():
    global source, recognizer
    source = sr.Microphone()
    source.__enter__()
    recognizer = sr.Recognizer()
    
    # Adjust ambient noise threshold, if needed
    recognizer.adjust_for_ambient_noise(source)


def main(): 
    global source, recognizer
            
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


def finalize():
    global source, recognizer
    source.__exit__()
    del source, recognizer


@app.get("/")
def voice_type():
    return main()

