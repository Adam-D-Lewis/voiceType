import speech_recognition as sr
import keyboard

def main():
    # Initialize the recognizer
    r = sr.Recognizer()

    # Open the microphone for recording
    with sr.Microphone() as source:
        print("Listening... (Press Home key to stop)")

        # Continuous listening loop
        while not keyboard.is_pressed('home'):
            # Adjust ambient noise threshold, if needed
            r.adjust_for_ambient_noise(source)

            # Record the audio
            audio = r.listen(source)

            try:
                # Perform speech recognition
                text = r.recognize_google(audio)

                # Print the recognized text
                print("You said:", text)

            except sr.UnknownValueError:
                print("Unable to recognize speech")

    print("Program stopped")

if __name__ == "__main__":
    main()
