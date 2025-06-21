import numpy as np
import mlx_whisper
from datetime import datetime
import speech_recognition as sr

r = sr.Recognizer()
mic = sr.Microphone(sample_rate=16000)


print("Initializing speech recognition...")
try:
    with mic as source:
        r.adjust_for_ambient_noise(source)
        while True:
            print("Press Ctrl+C to stop")
            audio = r.listen(source)
            # Convert audio to numpy array
            audio_data = np.frombuffer(audio.get_raw_data(), dtype=np.int16).astype(np.float32) / 32768.0
            # Process audio with the preloaded Apple MLXWhisper model
            result = mlx_whisper.transcribe(audio_data, path_or_hf_repo="mlx-community/whisper-medium.en-mlx")
            # Print the transcribed text
            if result:
                timestamp = datetime.now().strftime("%H:%M:%S")
                print(f"[{timestamp}] {result}")
            else:
                print("No result from MLXWhisper")

except KeyboardInterrupt:
    print("Stopped listening.")
