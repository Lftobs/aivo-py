import time
import signal
import asyncio
import threading
import numpy as np
import tkinter as tk
from tkinter import ttk
from google import genai
import sounddevice as sd
from google.genai import types
from faster_whisper import WhisperModel

# Add env for api keys
client = genai.Client(api_key="Gemini API Key")


# 🔽 SELECT THE BEST MODEL FOR YOUR COMPUTER 🔽
# --------------------------------------------
# - "tiny"    → Fastest, least accurate, ~1GB RAM
# - "base"    → Fast, lower accuracy, ~2GB RAM
# - "small"   → Balanced, moderate speed, ~4GB RAM
# - "medium"  → Slower, better accuracy, ~7GB RAM
# - "large-v3" (default) → Slowest, best accuracy, needs 10GB+ VRAM
MODEL_SIZE = "base.en"  # Change this based on your system capabilities

# 🔽 DEVICE SELECTION (GPU vs CPU) 🔽
# -----------------------------------
# - "cuda" → Use GPU (best for NVIDIA GPUs with wheCUDA support)
# - "cpu"  → Use CPU only (for slower PCs or non-GPU devices)
DEVICE = "cpu"  # Change to "cpu" if you don't have a GPU

# 🔽 COMPUTE TYPE (Precision Optimization) 🔽
# -------------------------------------------
# - "float16" → Uses Half Precision (Recommended for GPUs, saves VRAM)
# - "float32" → Full Precision (More accurate, but uses more VRAM)
# - "int8"    → Lowest Precision (Best for CPUs, lowest RAM usage)
COMPUTE_TYPE = "float16" if DEVICE == "cuda" else "int8"

# ✅ Audio Settings
SAMPLE_RATE = 16000
CHANNELS = 1
RECORDING = False
audio_buffer = []
recording_start_time = None
current_transcript = ""
MIN_RECORD_TIME = 1

# ✅ Real-time processing settings
CHUNK_DURATION = 2.0  # Process audio in 2-second chunks
CHUNK_SAMPLES = int(SAMPLE_RATE * CHUNK_DURATION)
PROCESSING_ACTIVE = False
last_chunk_time = 0

# ✅ Initialize the Whisper Model with optimized settings
whisper_model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)

async_loop = asyncio.new_event_loop()


def _start_loop():
    asyncio.set_event_loop(async_loop)
    async_loop.run_forever()


threading.Thread(target=_start_loop, daemon=True).start()

print(
    f"✅ Whisper Model Loaded: {MODEL_SIZE} | Device: {DEVICE} | Precision: {COMPUTE_TYPE}"
)


def callback(indata, frames, time, status):
    """Capture microphone audio and store it in a buffer when recording."""
    global RECORDING, audio_buffer
    if RECORDING:
        audio_buffer.append(indata.copy())


# ✅ Initialize main application window
root = tk.Tk()
root.title("Audio Transcriber")
root.geometry("600x400")
root.configure(bg="#f0f0f0")

# Create a main frame with padding
main_frame = ttk.Frame(root, padding="20")
main_frame.pack(fill=tk.BOTH, expand=True)

# Style configuration
style = ttk.Style()
style.configure("Custom.TButton", padding=10, font=("Arial", 12, "bold"))
style.configure(
    "Status.TLabel", font=("Arial", 12), background="#f0f0f0", foreground="#333333"
)

# ✅ Create GUI elements with improved styling
status_frame = ttk.Frame(main_frame)
status_frame.pack(fill=tk.X, pady=(0, 10))

status_label = ttk.Label(status_frame, text="Ready to Record", style="Status.TLabel")
status_label.pack(side=tk.LEFT)

duration_label = ttk.Label(status_frame, text="00:00", style="Status.TLabel")
duration_label.pack(side=tk.RIGHT)

record_button = ttk.Button(
    main_frame, text="🎤 Start Recording", style="Custom.TButton"
)
record_button.pack(pady=10)

transcript_frame = ttk.LabelFrame(main_frame, text="Transcript", padding=10)
transcript_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

transcript_display = tk.Text(
    transcript_frame,
    height=10,
    wrap=tk.WORD,
    font=("Arial", 11),
    bg="white",
    relief=tk.SOLID,
    padx=10,
    pady=10,
)
transcript_display.pack(fill=tk.BOTH, expand=True)

scrollbar = ttk.Scrollbar(
    transcript_frame, orient=tk.VERTICAL, command=transcript_display.yview
)
scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
transcript_display.configure(yscrollcommand=scrollbar.set)


def update_duration():
    """Update the recording duration display"""
    if RECORDING:
        elapsed = time.time() - recording_start_time
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        duration_label.config(text=f"{minutes:02d}:{seconds:02d}")
        root.after(1000, update_duration)
    else:
        duration_label.config(text="00:00")


def toggle_recording():
    """Handle recording start/stop with button click"""
    global RECORDING, recording_start_time, audio_buffer, PROCESSING_ACTIVE, current_transcript

    if not RECORDING:
        # Start recording
        RECORDING = True
        PROCESSING_ACTIVE = True
        recording_start_time = time.time()
        audio_buffer.clear()
        current_transcript = ""
        transcript_display.delete(1.0, tk.END)  # Clear display
        status_label.config(text="Recording in progress...")
        record_button.config(text="🛑 Stop Recording")

        update_duration()  # Start the duration timer
        print("🎤 Recording started...")
        root.after(100, process_audio_chunks)  # Start chunk processing
    else:
        # Stop recording
        RECORDING = False
        PROCESSING_ACTIVE = False
        elapsed_time = time.time() - recording_start_time
        status_label.config(text="Processing final audio...")
        record_button.config(text="🎤 Start Recording", state=tk.DISABLED)

        if elapsed_time < MIN_RECORD_TIME:
            status_label.config(
                text=f"Please record for at least {MIN_RECORD_TIME} second"
            )
            record_button.config(state=tk.NORMAL)
            return

        # Fix: Create task with coroutine properly
        async_loop.call_soon_threadsafe(
            async_loop.create_task, async_process_final_audio()
        )


record_button.config(command=toggle_recording)


def update_transcript(text):
    """Update the GUI with the latest transcript text."""
    # No need to update current_transcript here, it's handled elsewhere
    transcript_display.delete(1.0, tk.END)
    transcript_display.insert(tk.END, text)
    transcript_display.see(tk.END)  # Scroll to the end

    if RECORDING:
        status_label.config(text="Recording...")


def process_audio_chunks():
    """Process audio in chunks for real-time transcription"""
    global audio_buffer, PROCESSING_ACTIVE, last_chunk_time

    if not PROCESSING_ACTIVE:
        return

    current_time = time.time()
    elapsed_since_last_chunk = current_time - last_chunk_time

    # Only process a chunk if we have enough data and enough time has passed
    if (
        RECORDING
        and len(audio_buffer) > 0
        and elapsed_since_last_chunk >= CHUNK_DURATION
    ):
        # Process the chunk
        chunk_data = np.concatenate(audio_buffer, axis=0).flatten()
        audio_buffer.clear()  # Clear the buffer for new audio
        last_chunk_time = current_time

        # Create and run the coroutine properly
        async def process_chunk():
            await transcribe_chunk(chunk_data)

        # Schedule the transcription on our background loop
        async_loop.call_soon_threadsafe(async_loop.create_task, process_chunk())

    # Schedule the next check
    if PROCESSING_ACTIVE:
        root.after(100, process_audio_chunks)


def improve_transcript(full_raw_text):
    """Send the entire raw transcript for one-shot correction."""
    if not full_raw_text:
        return ""  # Return empty if nothing to improve

    print(f"⚙️ Sending full transcript for final improvement...")

    system_instruction = """You are an expert assistant tasked with correcting and improving speech-to-text transcripts in real-time.
Focus on fixing grammar, punctuation, and capitalization.
Combine the user's inputs sequentially into a single, coherent, corrected text.
Preserve the original meaning accurately. Only output the corrected text."""

    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash-8b-latest",
            contents=full_raw_text,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.2,
            ),
        )
        print(f"💡 Received corrected transcript.")
        return response.text
    except Exception as e:
        print(f"⚠️ Transcription generation API error: {e}")
        # Fallback: return the original raw text if correction fails
        return full_raw_text


async def transcribe_chunk(audio_data):
    """Transcribe a single chunk of audio data and append to raw transcript"""
    global current_transcript
    # Normalize audio
    audio_data = (
        audio_data / np.max(np.abs(audio_data))
        if np.max(np.abs(audio_data)) > 0
        else audio_data
    )

    # Transcribe with Faster-Whisper
    segments, _ = whisper_model.transcribe(audio_data)
    chunk_transcript = " ".join(segment.text for segment in segments).strip()

    if chunk_transcript:
        # Append the new raw chunk to the existing raw transcript
        current_transcript += (
            (" " + chunk_transcript) if current_transcript else chunk_transcript
        )
        # Update display in the main thread with the raw, accumulated transcript
        root.after(0, lambda: update_transcript(current_transcript))


async def async_process_final_audio():
    """Process remaining audio, combine, and call final improvement (async version)"""
    global audio_buffer, current_transcript

    final_raw_text = ""
    if audio_buffer:
        # Process remaining audio
        audio_data = np.concatenate(audio_buffer, axis=0).flatten()
        audio_data = (
            audio_data / np.max(np.abs(audio_data))
            if np.max(np.abs(audio_data)) > 0
            else audio_data
        )
        audio_buffer = []  # Clear buffer after processing

        # Final transcription
        segments, _ = whisper_model.transcribe(audio_data)
        final_raw_text = " ".join(segment.text for segment in segments).strip()

    # Append the final raw chunk (if any) to the current transcript
    if final_raw_text:
        current_transcript += (
            (" " + final_raw_text) if current_transcript else final_raw_text
        )

    # Now, improve the *entire* accumulated transcript
    final_improved_transcript = improve_transcript(current_transcript)

    # Update the display with the final *improved* transcript
    root.after(0, lambda: update_transcript(final_improved_transcript))
    # Store the improved version back into current_transcript if needed for future reference
    current_transcript = final_improved_transcript

    # Update status and re-enable button
    root.after(0, lambda: status_label.config(text="Ready"))
    root.after(0, lambda: record_button.config(state=tk.NORMAL))


def cleanup():
    """Clean up resources when exiting."""
    global stream, root
    print("\n🛑 Exiting... Cleaning up resources.")
    try:
        if "stream" in globals() and stream.active:
            stream.stop()
            stream.close()
        root.destroy()
    except Exception as e:
        print(f"⚠️ Cleanup error: {e}")
    print("✅ Cleanup complete. Goodbye!")


# ✅ Handle Ctrl+C (KeyboardInterrupt)
def signal_handler(sig, frame):
    cleanup()
    exit(0)


# Register signal handler
signal.signal(signal.SIGINT, signal_handler)

# ✅ Start SoundDevice Stream
stream = sd.InputStream(
    samplerate=SAMPLE_RATE,
    channels=CHANNELS,
    callback=callback,
    dtype=np.int16,
    device=None,  # Make sure this is the correct mic device
)

try:
    stream.start()
    print(
        f"🔊 Using audio device: {sd.query_devices(stream.device)['name']} at {SAMPLE_RATE}Hz"
    )
    print("✅ Close the application window to exit safely.")

    print("✅ Starting GUI application...")
    # Bind the window close event ('X' button) to the cleanup function
    root.protocol("WM_DELETE_WINDOW", cleanup)
    # Start the main loop
    root.mainloop()
except Exception as e:
    print(f"⚠️ Error: {e}")
    cleanup()
