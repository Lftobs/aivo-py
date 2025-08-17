import asyncio
import signal
import logging
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime, timezone, timedelta

import numpy as np
import sounddevice as sd
from dotenv import load_dotenv
from faster_whisper import WhisperModel

from .db import init_db, save_transcript_chunk

# Configure logging for service operation
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - (AIVO-Recorder) - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(), logging.FileHandler("./recorder.log", mode="a")],
)
logger = logging.getLogger(__name__)

# --- Initialize DB on startup ---
# This ensures tables are created before we try to write to them.
init_db()

load_dotenv()

# The Gemini client and prompts are for summarization, which should now be a separate process.
# We can remove them from this real-time recording script.
# client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
# from .utils import extract_segments, sys_prompt


@dataclass
class AudioConfig:
    """
    Configuration for the AIVO Recorder service.
    This includes audio settings, model parameters, and buffer management.
    """
    sample_rate: int = 16000
    channels: int = 1
    
    chunk_duration_seconds: int = 180 # 3 minutes 
    model_size: str = "base.en"
    device: str = "cpu"

    max_buffer_seconds: int = 360

    backup_interval_seconds: int = 60

    @property
    def compute_type(self) -> str:
        return "float16" if self.device == "cuda" else "int8"

    @property
    def frames_per_chunk(self) -> int:
        # The buffer size to wait for before processing
        return int(self.sample_rate * self.chunk_duration_seconds)

    @property
    def max_buffer_frames(self) -> int:
        # Maximum buffer size to prevent memory overflow
        return int(self.sample_rate * self.max_buffer_seconds)


class AivoRecorder:
    """
    AIVO Recorder Service that captures audio, transcribes it using Whisper, and saves it to the database.
    It runs continuously, processing audio in chunks and creating emergency backups to prevent data loss.
    It also handles graceful shutdowns and periodic backups.
    """
    def __init__(self, config: AudioConfig):
        self.config = config
        try:
            self.whisper_model = WhisperModel(
                config.model_size,
                device=config.device,
                compute_type=config.compute_type,
            )
            logger.info(
                "✅ Whisper Model Loaded: %s | Device: %s | Precision: %s",
                config.model_size,
                config.device,
                config.compute_type,
            )
        except Exception as e:
            logger.error("❌ Failed to load Whisper model: %s", e)
            raise

        self.audio_buffer: List[np.ndarray] = []
        self.stream: Optional[sd.InputStream] = None
        self.main_task: Optional[asyncio.Task] = None
        self.backup_task: Optional[asyncio.Task] = None
        self.is_running = False
        self.last_backup_time = datetime.now(timezone.utc)

        # Emergency backup buffer to prevent data loss
        self.emergency_backup: List[np.ndarray] = []

        logger.info(
            "🎤 Recording in chunks of %s seconds (3 minutes for optimal quality).",
            config.chunk_duration_seconds,
        )

    def _audio_callback(self, indata, frames, time_info, status):
        """This function is called by sounddevice for each new audio buffer."""
        if status:
            logger.warning("SoundDevice status: %s", status)
        if self.is_running:
            try:
                # Add to main buffer
                self.audio_buffer.append(indata.copy())

                # Add to emergency backup (rotating buffer)
                self.emergency_backup.append(indata.copy())

                # Keep emergency backup within limits
                current_frames = sum(len(chunk) for chunk in self.emergency_backup)
                if current_frames > self.config.max_buffer_frames:
                    # Remove oldest chunks
                    while (
                        current_frames > self.config.max_buffer_frames
                        and self.emergency_backup
                    ):
                        removed = self.emergency_backup.pop(0)
                        current_frames -= len(removed)

            except Exception as e:
                logger.error("❌ Error in audio callback: %s", e)

    async def _emergency_backup_chunk(self):
        """Emergency backup function to save audio data if main processing fails."""
        try:
            if not self.emergency_backup:
                return

            current_time = datetime.now(timezone.utc)
            backup_start_time = current_time - timedelta(
                seconds=self.config.backup_interval_seconds
            )

            # Create smaller backup audio data
            backup_audio = (
                np.concatenate(self.emergency_backup, axis=0)
                .flatten()
                .astype(np.float32)
            )

            # Normalize audio
            max_amp = np.max(np.abs(backup_audio))
            if max_amp > 0:
                backup_audio = backup_audio / max_amp

            logger.info("🔄 Creating emergency backup transcription...")

            # Transcribe backup audio
            segments, _ = await asyncio.to_thread(
                self.whisper_model.transcribe, backup_audio
            )
            text = " ".join(seg.text for seg in segments).strip()

            if text:
                await asyncio.to_thread(
                    save_transcript_chunk,
                    transcript_text=f"[BACKUP] {text}",
                    start_time=backup_start_time,
                    end_time=current_time,
                )
                logger.info("✅ Emergency backup saved successfully")

            # Clear backup buffer after successful save
            self.emergency_backup.clear()

        except Exception as e:
            logger.error("❌ Emergency backup failed: %s", e)

    async def _process_audio_chunk(self):
        """Takes the audio buffer, transcribes it, and saves it to the database."""
        if not self.audio_buffer:
            logger.warning("🤔 No audio in buffer, skipping process.")
            return

        try:
            # Record end time immediately, calculate start time
            end_time = datetime.now(timezone.utc)

            # Concatenate all parts of the buffer
            audio_data = (
                np.concatenate(self.audio_buffer, axis=0).flatten().astype(np.float32)
            )
            duration_seconds = len(audio_data) / self.config.sample_rate
            start_time = end_time - timedelta(seconds=duration_seconds)

            # Clear buffer for the next chunk immediately to prevent data loss
            self.audio_buffer.clear()

            # Normalize audio
            max_amp = np.max(np.abs(audio_data))
            if max_amp > 0:
                audio_data = audio_data / max_amp

            logger.info(
                "🎙️ Transcribing audio from %s to %s...",
                start_time.strftime("%H:%M:%S"),
                end_time.strftime("%H:%M:%S"),
            )

            # Run blocking whisper model in a separate thread to not block asyncio loop
            segments, _ = await asyncio.to_thread(
                self.whisper_model.transcribe, audio_data
            )
            text = " ".join(seg.text for seg in segments).strip()

            if text:
                if len(text) > 100:
                    logger.info('💬 Transcript: "%s..."', text[:100])
                else:
                    logger.info('💬 Transcript: "%s"', text)
                # Run blocking DB operation in a separate thread
                await asyncio.to_thread(
                    save_transcript_chunk,
                    transcript_text=text,
                    start_time=start_time,
                    end_time=end_time,
                )
                logger.info("✅ Chunk saved to database successfully")
            else:
                logger.info("🤔 No speech detected in chunk.")

        except Exception as e:
            logger.error("❌ Failed to process audio chunk: %s", e)
            # Try emergency backup if main processing fails
            try:
                await self._emergency_backup_chunk()
            except Exception as backup_error:
                logger.error("❌ Emergency backup also failed: %s", backup_error)

    async def _backup_loop(self):
        """Background task that periodically creates emergency backups."""
        try:
            while self.is_running:
                await asyncio.sleep(self.config.backup_interval_seconds)
                current_time = datetime.now(timezone.utc)
                if (
                    current_time - self.last_backup_time
                ).total_seconds() >= self.config.backup_interval_seconds:
                    if len(self.emergency_backup) > 0:
                        logger.debug("Creating periodic emergency backup...")
                        await self._emergency_backup_chunk()
                        self.last_backup_time = current_time
        except asyncio.CancelledError:
            logger.info("🛑 Backup loop cancelled.")
        except Exception as e:
            logger.error("❌ Error in backup loop: %s", e)

    async def _recording_loop(self):
        """The main loop that periodically processes the collected audio."""
        self.is_running = True
        if self.stream:
            self.stream.start()
        logger.info("🔴 REC: Continuous recording started. Press Ctrl+C to stop.")

        try:
            while self.is_running:
                await asyncio.sleep(self.config.chunk_duration_seconds)
                await self._process_audio_chunk()
        except asyncio.CancelledError:
            logger.info("\n🛑 Recording loop cancelled.")
        except Exception as e:
            logger.error("❌ Error in recording loop: %s", e)
        finally:
            logger.info("⏹️ Stopping audio stream.")
            if self.stream:
                self.stream.stop()

    async def shutdown(self):
        """Gracefully shuts down the recorder, processing any remaining audio."""
        if not self.is_running:
            return

        logger.info("\n🔄 Gracefully shutting down...")

        # Stop the main loop from running more iterations
        self.is_running = False

        # Cancel background tasks
        if self.main_task:
            self.main_task.cancel()
        if self.backup_task:
            self.backup_task.cancel()

        # Wait for tasks to acknowledge cancellation
        await asyncio.sleep(0.1)

        # Process any leftover audio in the buffer
        logger.info("   - Processing final audio chunk before exit...")
        await self._process_audio_chunk()

        # Final emergency backup
        logger.info("   - Creating final emergency backup...")
        await self._emergency_backup_chunk()

        logger.info("✅ Shutdown complete.")

    def start(self):
        """Initializes and starts the recording process."""
        try:
            self.stream = sd.InputStream(
                samplerate=self.config.sample_rate,
                channels=self.config.channels,
                callback=self._audio_callback,
                dtype=np.int16,
            )
            self.main_task = asyncio.create_task(self._recording_loop())
            self.backup_task = asyncio.create_task(self._backup_loop())
            logger.info("✅ Audio stream and background tasks initialized")
            return self.main_task
        except Exception as e:
            logger.error("❌ Failed to start recording: %s", e)
            raise


async def main():
    """Main function to initialize and run the AIVO recorder service."""
    try:
        config = AudioConfig()
        recorder = AivoRecorder(config)

        # Set up the signal handler for graceful shutdown
        loop = asyncio.get_running_loop()
        shutdown_event = asyncio.Event()

        def signal_handler():
            logger.info("🛑 Shutdown signal received")
            shutdown_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, signal_handler)

        # Start the recorder
        recorder.start()

        # Wait for shutdown signal
        await shutdown_event.wait()

        # Graceful shutdown
        await recorder.shutdown()

    except Exception as e:
        logger.error("❌ Critical error in main: %s", e)
        raise
