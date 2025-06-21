import time
import mlx_whisper
import numpy as np
from datetime import datetime
import speech_recognition as sr


def setup_recognizer():
    r = sr.Recognizer()
    # Adjust these parameters for better recognition
    r.energy_threshold = 300  # Minimum audio energy to consider for recording
    r.dynamic_energy_threshold = True
    r.pause_threshold = (
        0.8  # Seconds of non-speaking audio before a phrase is considered complete
    )

    try:
        mic = sr.Microphone(sample_rate=16000)
        return r, mic
    except Exception as e:
        print(f"Error initializing microphone: {e}")
        return None, None


def transcribe_audio(audio_data):
    try:
        result = mlx_whisper.transcribe(
            audio_data, path_or_hf_repo="mlx-community/whisper-medium.en-mlx"
        )["text"]
        return result.strip()
    except Exception as e:
        print(f"Error during transcription: {e}")
        return None


def main():
    r, mic = setup_recognizer()
    if not r or not mic:
        return

    print("Initializing speech recognition...")
    print("Press Ctrl+C to stop")

    try:
        with mic as source:
            print("Adjusting for ambient noise...")
            r.adjust_for_ambient_noise(source, duration=2)
            print("Ready! Listening...")

            while True:
                try:
                    audio = r.listen(source, timeout=5, phrase_time_limit=10)
                    print("Processing audio...")

                    # Convert audio to numpy array
                    audio_data = (
                        np.frombuffer(audio.get_raw_data(), dtype=np.int16).astype(
                            np.float32
                        )
                        / 32768.0
                    )

                    # Transcribe audio
                    result = transcribe_audio(audio_data)

                    if result:
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        print(f"[{timestamp}] {result}")

                except sr.WaitTimeoutError:
                    print("No speech detected, listening again...")
                except Exception as e:
                    print(f"Error processing audio: {e}")
                    time.sleep(1)  # Prevent rapid error loops

    except KeyboardInterrupt:
        print("\nStopped listening.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


if __name__ == "__main__":
    main()
