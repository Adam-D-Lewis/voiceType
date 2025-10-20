import sys

from faster_whisper import WhisperModel

print("Testing faster_whisper CUDA...")
try:
    model = WhisperModel("tiny", device="cuda", compute_type="float16")
    print("[OK] Model loaded with CUDA successfully")

    # Test transcription
    segments, info = model.transcribe("voicetype/assets/sounds/start-record.wav")
    print(f"[OK] Test transcription successful. Language: {info.language}")

except Exception as e:
    print(f"[ERROR] Error: {e}")
    sys.exit(1)

print("\nNow testing speech_recognition's faster_whisper...")
try:
    import speech_recognition as sr
    from speech_recognition.recognizers.whisper_local import faster_whisper

    # Try to load audio and transcribe
    audio = sr.AudioData.from_file("voicetype/assets/sounds/start-record.wav")

    result = faster_whisper.recognize(
        None,
        audio_data=audio,
        model="tiny",  # Use tiny for testing
        language="en",
        init_options=faster_whisper.InitOptionalParameters(
            device="cuda",
        ),
    )
    print(f"[OK] Speech recognition transcription successful: {result}")

except Exception as e:
    print(f"[ERROR] Speech recognition error: {e}")
    import traceback

    traceback.print_exc()
