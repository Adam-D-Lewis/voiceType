import os
import sys

# Add CUDA 11 libraries to PATH
cuda_path = r"C:\Users\Adam Lewis\voiceType\.pixi\envs\default\Library\bin"
os.environ["PATH"] = cuda_path + os.pathsep + os.environ.get("PATH", "")

print(f"Added to PATH: {cuda_path}")

from faster_whisper import WhisperModel

print("\nTesting with CUDA 11 libraries in PATH...")
try:
    # Try different compute types
    for compute_type in ["float16", "int8", "float32"]:
        print(f"\nTrying compute_type={compute_type}...")
        try:
            model = WhisperModel("tiny", device="cuda", compute_type=compute_type)
            print(f"  [OK] Model loaded with {compute_type}")

            segments, info = model.transcribe(
                "voicetype/assets/sounds/start-record.wav"
            )
            print(f"  [OK] Transcription successful with {compute_type}")
            break
        except Exception as e:
            print(f"  [ERROR] Failed with {compute_type}: {e}")

except Exception as e:
    print(f"[ERROR] Overall error: {e}")
    import traceback

    traceback.print_exc()
