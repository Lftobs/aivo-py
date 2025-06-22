import time
import signal
import asyncio
import numpy as np
import sounddevice as sd
from pynput import keyboard
from faster_whisper import WhisperModel

# 🔽 SELECT THE BEST MODEL FOR YOUR COMPUTER 🔽
# --------------------------------------------
# - "tiny"    → Fastest, least accurate, ~1GB RAM
# - "base"    → Fast, lower accuracy, ~2GB RAM
# - "small"   → Balanced, moderate speed, ~4GB RAM
# - "medium"  → Slower, better accuracy, ~7GB RAM
# - "large-v3" (default) → Slowest, best accuracy, needs 10GB+ VRAM
MODEL_SIZE = "small.en"  # Change this based on your system capabilities

# 🔽 DEVICE SELECTION (GPU vs CPU) 🔽
# -----------------------------------
# - "cuda" → Use GPU (best for NVIDIA GPUs with CUDA support)
# - "cpu"  → Use CPU only (for slower PCs or non-GPU devices)
DEVICE = "cpu"  # Change to "cpu" if you don't have a GPU

# 🔽 COMPUTE TYPE (Precision Optimization) 🔽
# -------------------------------------------
# - "float16" → Uses Half Precision (Recommended for GPUs, saves VRAM)
# - "float32" → Full Precision (More accurate, but uses more VRAM)
# - "int8"    → Lowest Precision (Best for CPUs, lowest RAM usage)
COMPUTE_TYPE = "float16" if DEVICE == "cuda" else "int8"

# ✅ Initialize the Whisper Model with optimized settings
whisper_model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)

print(
    f"✅ Whisper Model Loaded: {MODEL_SIZE} | Device: {DEVICE} | Precision: {COMPUTE_TYPE}"
)


# ✅ Audio Settings
SAMPLE_RATE = 16000
CHANNELS = 1
RECORDING = False
audio_buffer = []
recording_start_time = None
MIN_RECORD_TIME = 1


def callback(indata, frames, time, status):
    """Capture microphone audio and store it in a buffer when recording."""
    global RECORDING, audio_buffer
    if RECORDING:
        audio_buffer.append(indata.copy())


async def transcribe_audio():
    """Process and transcribe the recorded audio."""
    global audio_buffer

    if not audio_buffer:
        print("⚠️ No audio recorded. Skipping transcription...")
        return

    print("🎙️ Processing transcription...")

    # ✅ Convert buffer to numpy array
    audio_data = np.concatenate(audio_buffer, axis=0).flatten()
    audio_data = audio_data / np.max(np.abs(audio_data))  # Normalize audio

    # ✅ Transcribe with Faster-Whisper
    segments, _ = whisper_model.transcribe(audio_data)
    transcript = " ".join(segment.text for segment in segments).strip()

    if transcript:
        print(f"📝 Whisper Transcript: {transcript}")
    else:
        print("🤔 No words detected.")

    # ✅ Clear buffer after processing
    audio_buffer = []


def on_press(key):
    """Start recording when spacebar is pressed."""
    global RECORDING, recording_start_time, audio_buffer
    if key == keyboard.Key.esc:
        cleanup()
        exit(0)
    elif key == keyboard.Key.space and not RECORDING:
        RECORDING = True
        recording_start_time = time.time()
        audio_buffer.clear()
        print("🎤 Recording started...")


def on_release(key):
    """Stop recording and trigger transcription when spacebar is released."""
    global RECORDING, recording_start_time
    if key == keyboard.Key.space and RECORDING:
        elapsed_time = time.time() - recording_start_time
        if elapsed_time < MIN_RECORD_TIME:
            print(f"⏳ Holding space for at least {MIN_RECORD_TIME} sec to record.")
            return

        RECORDING = False
        print("🛑 Recording stopped. Processing...")
        asyncio.run(transcribe_audio())


# ✅ Global listener variable to ensure cleanup
listener = None


def cleanup():
    """Clean up resources when exiting."""
    global listener, stream
    print("\n🛑 Exiting... Cleaning up resources.")
    try:
        if stream.active:
            stream.close()
        if listener and listener.running:
            listener.stop()
    except Exception as e:
        print(f"⚠️ Cleanup error: {e}")
    print("✅ Cleanup complete. Goodbye!")


# ✅ Handle Ctrl+C (KeyboardInterrupt)
def signal_handler(sig, frame):
    cleanup()
    exit(0)


signal.signal(signal.SIGINT, signal_handler)  # Register Ctrl+C handler

# ✅ Start SoundDevice Stream
stream = sd.InputStream(
    samplerate=SAMPLE_RATE,
    channels=CHANNELS,
    callback=callback,
    dtype=np.int16,
    device=None,  # Make sure this is the correct mic device
)

print("🎤 Hold [SPACE] to record, release to transcribe. Press [ESC] to exit.")
print("🔴 Press [CTRL+C] to exit safely.")

# ✅ Start Listening for Keyboard Input
try:
    with stream:
        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.start()  # Start listener in a separate thread
        listener.join()  # Wait for the listener to finish
except KeyboardInterrupt:
    cleanup()