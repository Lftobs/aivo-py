# AIVO - AI Voice Operations

AIVO is a background service that continuously records audio, transcribes it using speech-to-text models, and organizes the transcriptions with AI-generated summaries and keywords.

## Features

- **Continuous Audio Recording**: Records audio in 3-minute chunks for optimal transcription quality
- **Minimal Data Loss**: Implements emergency backup buffering to prevent audio data loss
- **Smart Transcription**: Uses Faster Whisper for efficient speech-to-text conversion  
- **Hourly Aggregation**: Automatically processes and summarizes transcript chunks every hour
- **AI-Powered Insights**: Generates summaries, overviews, and keywords using Google Gemini
- **Database Storage**: Organized storage with daily and hourly records linked to transcript chunks
- **System Service**: Runs as a background systemd service with automatic startup
- **Graceful Shutdown**: Handles termination signals properly to save all pending audio

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Audio Input   │    │   Entry.py      │    │   Database      │
│   (Microphone)  │───▶│   (Recorder)    │───▶│   (PostgreSQL)  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │                         ▲
                              ▼                         │
                       ┌─────────────────┐    ┌─────────────────┐
                       │   Scheduler.py  │    │     Job.py      │
                       │   (Triggers)    │───▶│  (Aggregator)   │
                       └─────────────────┘    └─────────────────┘
                                                       │
                                                       ▼
                                              ┌─────────────────┐
                                              │    Utils.py     │
                                              │  (AI Insights)  │
                                              └─────────────────┘
```

## Database Schema

- **Days**: Each calendar day
- **HourlyRecord**: Each hour within a day, contains aggregated summaries
- **TranscriptChunk**: Individual 3-minute transcription segments

## Installation

### Prerequisites

- Python 3.8+
- PostgreSQL database
- Audio input device (microphone)
- Linux system with systemd

### Quick Setup

1. **Clone and setup**:
   ```bash
   git clone <repository>
   cd aivo-py
   cp .env.example .env
   # Edit .env with your database and API keys
   ```

2. **Install dependencies**:
   ```bash
   # Make sure uv is installed: https://github.com/astral-sh/uv
   uv pip install -e .
   ```

3. **Install as system service**:
   ```bash
   chmod +x setup.sh
   ./setup.sh
   ```

4. **Start services**:
   ```bash
   sudo systemctl start aivo-recorder
   sudo systemctl start aivo-scheduler
   ```

### Manual Installation

1. **Database setup**:
   ```sql
   CREATE DATABASE aivo_db;
   CREATE USER aivo_user WITH PASSWORD 'your_password';
   GRANT ALL PRIVILEGES ON DATABASE aivo_db TO aivo_user;
   ```

2. **Environment configuration**:
   ```bash
   # Required
   DB_URL=postgresql://aivo_user:your_password@localhost:5432/aivo_db
   
   # Optional (for AI summaries)
   GEMINI_API_KEY=your_gemini_api_key
   ```

3. **Test the application**:
   ```bash
   python app/entry.py
   ```

## Configuration

All configuration is managed through environment variables in the `.env` file:

- `DB_URL`: PostgreSQL connection string
- `GEMINI_API_KEY`: Google Gemini API key 
<!-- - `CHUNK_DURATION_SECONDS`: Recording chunk duration (default: 180)
- `WHISPER_MODEL_SIZE`: Whisper model size (default: base.en)
- `WHISPER_DEVICE`: Processing device (cpu/cuda) -->

## Usage

### As a System Service

```bash
# Start/stop services
sudo systemctl start aivo-recorder
sudo systemctl stop aivo-recorder

# View logs
sudo journalctl -u aivo-recorder -f
sudo journalctl -u aivo-scheduler -f

# Check status
sudo systemctl status aivo-recorder
sudo systemctl status aivo-scheduler
```

### Manual Execution

```bash
# Start recorder
python main.py recoder

# Start scheduler
python main.py scheduler

```

## Data Flow

1. **Recording** (entry.py): Audio → 3-min chunks → TranscriptChunk records
2. **Scheduling** (scheduler.py): Runs hourly aggregation at :05 past each hour  
3. **Aggregation** (job.py): Combines chunks → AI processing → HourlyRecord updates
4. **AI Processing** (utils.py): Full transcript → Summary + Overview + Keywords

## Monitoring

### Log Files

- Recorder: `/var/log/aivo-recorder.log`
- Scheduler: `/var/log/aivo-scheduler.log`  
- System logs: `journalctl -u aivo-recorder`

### Database Queries

```sql
-- Recent chunks
SELECT * FROM transcript_chunks ORDER BY created_at DESC LIMIT 10;

-- Hourly summaries
SELECT * FROM hourly_records WHERE status = 'COMPLETED' ORDER BY hour_start_time DESC;

-- Daily overview
SELECT day_date, COUNT(*) as hours_recorded 
FROM days d JOIN hourly_records hr ON d.id = hr.day_id 
GROUP BY day_date ORDER BY day_date DESC;
```

## Troubleshooting

### Audio Issues
- Check microphone permissions: `groups $USER` (should include 'audio')
- Test audio devices: `python app/list_audio_devices.py`
- Verify ALSA/PulseAudio setup

### Database Issues  
- Check connection: `psql $DB_URL`
- Verify table creation: Run `python -c "from app.db import init_db; init_db()"`

### Service Issues
- Check service status: `systemctl status aivo-recorder`
- View recent logs: `journalctl -u aivo-recorder --since "1 hour ago"`
- Restart services: `sudo systemctl restart aivo-recorder`

### Performance Tuning

- **CPU Usage**: Switch to smaller Whisper model (tiny.en, base.en)
- **Memory Usage**: Reduce max_buffer_seconds in configuration
- **Storage**: Set up log rotation for `/var/log/aivo/`

## Development

### Project Structure
```
aivo-py/
├── app/
│   ├── __init__.py
│   ├── db.py                 # Database models and setup
│   ├── entry.py              # Main recorder service
│   ├── job.py                # Aggregation and summarization logic
│   ├── list_audio_devices.py   # Utility to list audio devices
│   ├── scheduler.py          # Hourly job scheduler
│   └── utils.py              # AI processing helpers
├── .env.example              # Configuration template
├── .gitignore
├── aivo-recorder.service     # Systemd service file for recorder
├── aivo-scheduler.service    # Systemd service file for scheduler
├── main.py                   # Main entry point for direct execution
├── pyproject.toml            # Project metadata and dependencies
├── README.md
├── setup.sh                  # Installation and setup script
└── uv.lock                   # Pinned dependencies for uv
```

### Adding Features

1. **New Audio Sources**: Modify `AudioConfig` in `entry.py`
2. **Different AI Models**: Update `utils.py` with new providers
3. **Custom Aggregation**: Extend `job.py` processing logic
4. **Additional Storage**: Add new models to `db.py`

## Security

- Services run as dedicated `aivo` user
- Restricted file system access via systemd
- Audio group membership required for microphone access
- Database credentials via environment variables only
