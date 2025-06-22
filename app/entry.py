import asyncio
import signal
import time
import uuid
from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
from pynput import keyboard

from .db import Base, save_recording_to_db, engine

Base.metadata.create_all(engine)


@dataclass
class AudioConfig:
    sample_rate: int = 16000
    channels: int = 1
    chunk_duration: int = 3
    model_size: str = "small.en"
    device: str = "cpu"
    
    @property
    def compute_type(self) -> str:
        return "float16" if self.device == "cuda" else "int8"
    
    @property
    def frames_per_chunk(self) -> int:
        return int(self.sample_rate * self.chunk_duration)


class AudioRecorder:
    def __init__(self, config: AudioConfig):
        self.config = config
        self.whisper_model = WhisperModel(
            config.model_size, 
            device=config.device, 
            compute_type=config.compute_type
        )
        self.audio_buffer: List[np.ndarray] = []
        self.stream: Optional[sd.InputStream] = None
        self.keyboard_listener: Optional[keyboard.Listener] = None
        self.is_recording = False
        self.stream_id: Optional[str] = None
        self.stream_start_time: Optional[float] = None
        self.stream_stop_time: Optional[float] = None
        self._transcription_task: Optional[asyncio.Task] = None
        
        print(f"✅ Whisper Model Loaded: {config.model_size} | Device: {config.device} | Precision: {config.compute_type}")

    def _audio_callback(self, indata, frames, time, status):
        """Capture microphone audio and store it in buffer."""
        if status:
            print(f"SoundDevice status: {status}")
        self.audio_buffer.append(indata.copy())

    async def _transcribe_audio(self):
        """Process and transcribe the accumulated audio buffer."""
        current_frames_in_buffer = sum(arr.shape[0] for arr in self.audio_buffer)

        if current_frames_in_buffer < self.config.frames_per_chunk:
            return

        print(f"\n🎙️ Processing {self.config.chunk_duration}s audio chunk ({current_frames_in_buffer} frames)...")

        buffer_to_process = self.audio_buffer
        self.audio_buffer = []

        if not buffer_to_process:
            print("⚠️ Audio buffer is empty despite having enough frames. Skipping transcription.")
            return

        audio_data = np.concatenate(buffer_to_process, axis=0).flatten()

        max_amplitude = np.max(np.abs(audio_data))
        if max_amplitude > 0:
            audio_data = audio_data / max_amplitude
        else:
            audio_data = np.zeros_like(audio_data)

        try:
            audio_data = audio_data.astype(np.float32)
            segments, _ = await asyncio.to_thread(self.whisper_model.transcribe, audio_data)
            transcript = " ".join(segment.text for segment in segments).strip()

            if transcript:
                asyncio.create_task(
                    asyncio.to_thread(
                        save_recording_to_db,
                        unique_id=self.stream_id,
                        start_time=time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.stream_start_time)),
                        end_time=time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.stream_stop_time)),
                        transcript=transcript
                    )
                )
                print(f"📝 Live Transcript: {transcript}")
            else:
                print("🤔 No words detected in this chunk.")

        except Exception as e:
            print(f"❌ Transcription error: {e}")

    async def _transcription_loop(self):
        """Continuous transcription loop."""
        try:
            while True:
                await asyncio.sleep(self.config.chunk_duration)
                if not self.is_recording:
                    continue
                await self._transcribe_audio()
        except asyncio.CancelledError:
            print("Transcription loop cancelled.")
        except Exception as e:
            print(f"❌ Transcription loop error: {e}")

    def _process_final_audio_chunk(self):
        """Process any remaining audio in the buffer before exit."""
        if self.audio_buffer:
            print("🎙️ Processing final audio chunk before exit...")
            buffer_to_process = self.audio_buffer.copy()
            self.audio_buffer.clear()

            if buffer_to_process:
                audio_data = np.concatenate(buffer_to_process, axis=0).flatten()
            
                max_amplitude = np.max(np.abs(audio_data))
                if max_amplitude > 0:
                    audio_data = audio_data / max_amplitude
                else:
                    audio_data = np.zeros_like(audio_data)
                
                try:
                    audio_data = audio_data.astype(np.float32)
                    segments, _ = self.whisper_model.transcribe(audio_data)
                    transcript = " ".join(segment.text for segment in segments).strip()
                    
                    if transcript:
                        print(f"📝 Final Transcript: {transcript}")
                    else:
                        print("🤔 No words detected in final chunk.")
                        
                except Exception as e:
                    print(f"❌ Final transcription error: {e}")

    def _on_key_press(self, key):
        """Handle key press events."""
        try:
            if key.char and key.char.lower() == 'r':
                if not self.is_recording:
                    self.is_recording = True
                    self.stream_id = str(uuid.uuid4())
                    self.stream_start_time = time.time()
                    self.stream.start()
                    print(f"🔴 Recording started at {time.strftime('%H:%M:%S', time.localtime(self.stream_start_time))}...")
                else:
                    self.is_recording = False
                    self.stream_stop_time = time.time()
                    print(f"⏹️ Recording stopped at {time.strftime('%H:%M:%S', time.localtime(self.stream_stop_time))}.")
                    self.stream.stop()
                    self._process_final_audio_chunk()
                    print("✅ Audio stream stopped.")
        except AttributeError:
            pass

    def cleanup(self):
        """Clean up resources when exiting."""
        print("\n🛑 Exiting...Cleaning up resources.")
        try:
            if self.stream and self.stream.active:
                self.stream.stop()
                self.stream.close()
                print("✅ Audio stream stopped.")
            if self.keyboard_listener and self.keyboard_listener.running:
                self.keyboard_listener.stop()
        except Exception as e:
            print(f"⚠️ Cleanup error: {e}")
        print("✅ Cleanup complete. Goodbye!")

    def handle_signal(self, sig, frame):
        """Handle Ctrl+C signal."""
        print("\nCtrl+C detected. Initiating graceful exit...")
        
        if self.stream and self.stream.active:
            self.stream.stop()
            self.stream.close()
            print("🛑 Audio recording stopped.")

        self._process_final_audio_chunk()
        raise KeyboardInterrupt()

    async def run(self):
        """Main execution method."""
        try:
            self.stream = sd.InputStream(
                samplerate=self.config.sample_rate,
                channels=self.config.channels,
                callback=self._audio_callback,
                dtype=np.int16,
                device=None,
            )
            
            self.keyboard_listener = keyboard.Listener(
                on_press=self._on_key_press,
            )
            self.keyboard_listener.start()

            # Start the transcription loop
            self._transcription_task = asyncio.create_task(self._transcription_loop())

            print("🎤 Press 'r' to start/stop recording. Press Ctrl+C to exit.")
            
            # Wait for the transcription task
            await self._transcription_task
            
        except Exception as e:
            print(f"❌ Failed to start audio stream: {e}")
            print("   Please ensure a microphone is connected and working.")
        except asyncio.CancelledError:
            print("Transcription task cancelled.")
        except KeyboardInterrupt:
            print("KeyboardInterrupt received in main.")
            if self._transcription_task:
                self._transcription_task.cancel()
                try:
                    await self._transcription_task
                except asyncio.CancelledError:
                    pass
        finally:
            self.cleanup()


def main():
    config = AudioConfig()
    recorder = AudioRecorder(config)
    
    # Register signal handler
    signal.signal(signal.SIGINT, recorder.handle_signal)

    try:
        asyncio.run(recorder.run())
    except KeyboardInterrupt:
        print("Final cleanup after KeyboardInterrupt.")
        recorder.cleanup()


if __name__ == "__main__":
    main()
