# ContentMachine

Internal tool to transcribe Instagram reels and view insights. Paste a reel URL to get:
- **Transcription** – spoken content as text
- **Views** – view count
- **Likes** – like count
- **Comments** – comment count

## Requirements

- **Python 3.10+**
- **FFmpeg** – required for extracting audio from videos. Install via:
  - macOS: `brew install ffmpeg`
  - Ubuntu/Debian: `apt install ffmpeg`
  - Windows: [Download from ffmpeg.org](https://ffmpeg.org/download.html)

## Setup

```bash
# Clone the repo (if not already)
git clone https://github.com/UsAutoAdmin/ContentMachine.git
cd ContentMachine

# Create virtual environment
python -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Run

```bash
uvicorn app:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.

## Usage

1. Copy the URL of an Instagram reel (e.g. `https://www.instagram.com/reel/ABC123/`)
2. Paste it into the input field
3. Choose a Whisper model (Base is a good balance of speed and accuracy)
4. Click **Transcribe**

The first run will download the Whisper model (~140MB for base), so it may take a moment.

## API

```bash
# POST /transcribe
curl -X POST http://127.0.0.1:8000/transcribe \
  -F "url=https://www.instagram.com/reel/..." \
  -F "model_size=base"
```

Response:
```json
{"success": true, "transcription": "Your transcribed text here..."}
```

## Notes

- **Instagram access**: Some reels may be private or region-locked. Public reels generally work.
- **yt-dlp**: Uses [yt-dlp](https://github.com/yt-dlp/yt-dlp) for downloading. Instagram support can change; keep yt-dlp updated (`pip install -U yt-dlp`).
- **Model sizes**: Tiny is fastest but less accurate. Large v3 is most accurate but slower and uses more memory.
