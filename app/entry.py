import asyncio
import os
import signal
import time
import uuid
from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import redis.asyncio as aioredis
import sounddevice as sd
from dotenv import load_dotenv
from faster_whisper import WhisperModel
from google import genai
from google.genai import types
from pynput import keyboard

from .db import Base, engine, save_summary_to_db
from .utils import extract_segments, sys_prompt

# Initialize DB
Base.metadata.create_all(engine)

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

@dataclass
class AudioConfig:
    sample_rate: int = 16000
    channels: int = 1
    chunk_duration: int = 3
    model_size: str = "small.en"
    device: str = "cpu"
    redis_url: str = "redis://localhost:6379/0"

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

        # Session info
        self.session_id: Optional[str] = None
        self.stream_start_time: Optional[float] = None
        self.stream_stop_time: Optional[float] = None

        # Asyncio loop (set in run)
        self.loop: Optional[asyncio.AbstractEventLoop] = None

        # Redis client
        self.redis: Optional[aioredis.Redis] = None

        print(f"✅ Whisper Model Loaded: {config.model_size} | Device: {config.device} | Precision: {config.compute_type}")

    async def _init_redis(self):
        self.redis = aioredis.from_url(self.config.redis_url)

    async def _push_to_stream(self, key: str, mapping: dict):
        if not self.redis:
            await self._init_redis()
        await self.redis.xadd(key, mapping)

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            print(f"SoundDevice status: {status}")
        self.audio_buffer.append(indata.copy())

    async def _transcribe_and_stream(self):
        frames = sum(arr.shape[0] for arr in self.audio_buffer)
        if frames < self.config.frames_per_chunk:
            return

        buffer = self.audio_buffer
        self.audio_buffer = []
        audio_data = np.concatenate(buffer, axis=0).flatten().astype(np.float32)
        max_amp = np.max(np.abs(audio_data))
        audio_data = audio_data / max_amp if max_amp > 0 else audio_data

        print(f"🎙️ Transcribing {self.config.chunk_duration}s audio...")
        segments, _ = await asyncio.to_thread(self.whisper_model.transcribe, audio_data)
        text = " ".join(seg.text for seg in segments).strip()

        if text:
            key = f"transcript_stream:{self.session_id}"
            await self._push_to_stream(key, {'text': text, 'ts': str(time.time())})
            print(f"🔄 Pushed chunk to Redis stream: {text}")
        else:
            print("🤔 No transcript for chunk.")

    async def _transcription_loop(self):
        try:
            while True:
                await asyncio.sleep(self.config.chunk_duration)
                if self.is_recording:
                    await self._transcribe_and_stream()
        except asyncio.CancelledError:
            pass

    async def _summarize_session(self):
        key = f"transcript_stream:{self.session_id}"
        if not self.redis:
            await self._init_redis()
        messages = await self.redis.xrange(key)
        texts = [msg[b'text'].decode() for _, msg in messages if b'text' in msg]
        full_text = " ".join(texts)
        print(full_text)

        if full_text:
            print("🧠 Generating summary...")
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                config=types.GenerateContentConfig(
                    system_instruction=sys_prompt),
                contents=full_text
            )
            summary = response.text
            data = extract_segments(summary)
            start_formatted = time.strftime(
                '%Y-%m-%d %H:%M:%S', 
                time.localtime(self.stream_start_time)
            )
            end_formatted = time.strftime(
                '%Y-%m-%d %H:%M:%S', 
                time.localtime(self.stream_stop_time)
            )
            
            try:
                await asyncio.to_thread(
                    save_summary_to_db,
                    recording_id=self.session_id,
                    start_time=start_formatted,
                    end_time=end_formatted,
                    summary_text=data.get('Summary'),
                    actual_text= full_text,
                    overview=data.get('Overview Summary'),
                    keywords=data.get('Keywords')
                )
                print("✅ Database transaction completed successfully")
            except Exception as e:
                print(f"❌ Database save failed: {e}")
            print(f"✅ Summary saved: {summary}")
        else:
            print("⚠️ No transcript chunks found for summary.")

        # Cleanup
        await self.redis.delete(key)

    def _on_key_press(self, key):
        try:
            if key.char and key.char.lower() == 'r':
                if not self.is_recording:
                    self.is_recording = True
                    self.session_id = str(uuid.uuid4())
                    self.stream_start_time = time.time()
                    print(f"🔴 Started recording session {self.session_id}")
                    self.stream.start()
                else:
                    self.is_recording = False
                    self.stream_stop_time = time.time()
                    self.stream.stop()
                    print(f"⏹️ Stopped recording session {self.session_id}")

                    # Push end marker and trigger summary via main loop
                    if self.loop:
                        asyncio.run_coroutine_threadsafe(
                            self._push_to_stream(
                                f"transcript_stream:{self.session_id}",
                                {'event': 'end', 'ts': str(time.time())}
                            ),
                            self.loop
                        )
                        asyncio.run_coroutine_threadsafe(
                            self._summarize_session(),
                            self.loop
                        )
        except AttributeError:
            pass

    def handle_signal(self, sig, frame):
        print("\n🛑 Signal received. Exiting...")
        raise KeyboardInterrupt

    def cleanup(self):
        print("Cleaning up...")
        if self.stream and self.stream.active:
            self.stream.stop()
        if self.keyboard_listener and self.keyboard_listener.running:
            self.keyboard_listener.stop()

    async def run(self):
        self.loop = asyncio.get_running_loop()
        self.redis = aioredis.from_url(self.config.redis_url)

        self.stream = sd.InputStream(
            samplerate=self.config.sample_rate,
            channels=self.config.channels,
            callback=self._audio_callback,
            dtype=np.int16
        )
        self.keyboard_listener = keyboard.Listener(on_press=self._on_key_press)
        self.keyboard_listener.start()

        self._transcription_task = asyncio.create_task(self._transcription_loop())
        print("🎤 Press 'r' to start/stop. Ctrl+C to exit.")

        try:
            await self._transcription_task
        except asyncio.CancelledError:
            pass
        finally:
            self.cleanup()


def main():
    config = AudioConfig()
    recorder = AudioRecorder(config)
    signal.signal(signal.SIGINT, recorder.handle_signal)
    try:
        asyncio.run(recorder.run())
    except KeyboardInterrupt:
        recorder.cleanup()

if __name__ == '__main__':
    main()
