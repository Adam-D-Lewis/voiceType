from contextlib import asynccontextmanager
from typing import List, Union

from fastapi import Depends, FastAPI, HTTPException
from .utils import play_audio, type_text, make_sound_thread
from pathlib import Path
import sys
import logging
import fastapi
logging.warn(fastapi.__file__)
logging.warn(sys.executable)
import speech_recognition as sr

from .sounds import ERROR_SOUND, START_RECORD_SOUND

_HERE = Path(__file__).resolve().parent


# global variables
source = None
recognizer = None

def initialize():
    global source, recognizer
    print('Initializing...')
    # List all microphone names
    mic_list = sr.Microphone.list_microphone_names()
    working_mic_list = sr.Microphone.list_working_microphones()

    for index, mic_list_index in enumerate(mic_list):
        print(f"Microphone {index}: {mic_list_index}")

    for index, mic_list_index in enumerate(working_mic_list):
        print(f"Working Microphone {index}: {mic_list[mic_list_index]}")
    
    # index = mic_list.index("sysdefault")
    # index = mic_list.index("spdif")
    try:
        index = mic_list.index("USB Audio Device: - (hw:3,0)")
    except ValueError:
        index = mic_list.index("USB Audio Device: - (hw:0,0)")
    print(index)
    # breakpoint()
    
    # for i in range(len(mic_list)):
    # try:
    
    source = sr.Microphone(device_index=index)
    recognizer = sr.Recognizer()
    
    # Adjust ambient noise threshold, if needed
    # breakpoint()
    with source:
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
    # breakpoint()
    #     with open(_HERE.joinpath('devices.txt'), "a") as f:
    #         f.write(f"Microphone {i}: {mic_list[i]}\n")
    # except Exception as e:
    #     with open(_HERE.joinpath('devices.txt'), "a") as f:
    #         f.write(f"Microphone {i}: {mic_list[i]} Error: {str(e)} + '\n'")


def finalize():
    global source, recognizer
    print('Finalizing...')
    del source, recognizer

@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize()
    try:
        yield
    finally:
        finalize()

app = FastAPI(lifespan=lifespan)


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
            # text = recognizer.recognize_google(audio)
            text = recognizer.recognize_whisper(audio, model='large-v3') # base.en, tiny.en, large-v3

            # Print the recognized text
            print("Detected Speech:", text)
            type_text(text)
            
        except sr.UnknownValueError as e:
            make_sound_thread(ERROR_SOUND).start()
            print("Unable to recognize speech")
            with open(_HERE.joinpath('error_log.txt'), "a") as error_file:
                error_file.write(str(e) + '\n')



@app.get("/")
def voice_type():
    return main()

