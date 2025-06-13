from playsound3 import playsound

sound_file = "../voicetype/sounds/start-record.wav"

# Play sounds from disk
playsound(sound_file)

# or play sounds from the internet.
# playsound("http://url/to/sound/file.mp3")

# You can play sounds in the background
# sound = playsound("/path/to/sound/file.mp3", block=False)

# # and check if they are still playing
# if sound.is_alive():
#     print("Sound is still playing!")

# # and stop them whenever you like.
# sound.stop()
