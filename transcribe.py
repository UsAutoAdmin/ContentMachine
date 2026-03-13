"""
ContentMachine - Instagram Reel Transcription Module

Handles downloading video/audio from Instagram reels and transcribing
the content using faster-whisper.
"""

import re
import shutil
import tempfile
import uuid
from pathlib import Path

import httpx
import yt_dlp
from faster_whisper import WhisperModel


def _get_ffmpeg_location() -> str | None:
    """Find ffmpeg binary path for yt-dlp (handles environments where PATH differs)."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg
    # Fallback: common Homebrew paths
    for path in ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"]:
        if Path(path).exists():
            return path
    return None


def _fetch_view_count_from_embed(url: str) -> int | None:
    """
    Fallback: fetch Instagram pages and extract view_count from embedded JSON.
    View count requires /api/v1/media/{id}/info/ (auth-only); we try main + embed pages.
    """
    base = url.strip().split("?")[0].rstrip("/")
    if "/embed" in base:
        return None

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.instagram.com/",
    }

    # Try main page first (may have more data), then embed
    urls_to_try = [base, f"{base}/embed/"]

    patterns = [
        r'"video_view_count"\s*:\s*(\d+)',
        r'"video_views"\s*:\s*(\d+)',
        r'"view_count"\s*:\s*(\d+)',
        r'"play_count"\s*:\s*(\d+)',
        r'"playCount"\s*:\s*(\d+)',
        r'"videoViewCount"\s*:\s*(\d+)',
        r'"views"\s*:\s*(\d+)',
        # Some pages use different nesting
        r'video_view_count["\']?\s*:\s*(\d+)',
        r'play_count["\']?\s*:\s*(\d+)',
    ]

    for page_url in urls_to_try:
        try:
            with httpx.Client(follow_redirects=True, timeout=15.0) as client:
                resp = client.get(page_url, headers=headers)
                resp.raise_for_status()
                html = resp.text
        except Exception:
            continue

        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                try:
                    val = int(match.group(1))
                    if val > 0:
                        return val
                except (ValueError, IndexError):
                    continue

    return None


def _format_count(value: int | None) -> str:
    """Format count for display (e.g. 1234567 -> 1.2M)."""
    if value is None:
        return "—"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)


def download_reel_audio(
    url: str, output_dir: Path | None = None
) -> tuple[Path, dict]:
    """
    Download audio from an Instagram reel URL using yt-dlp.
    Returns (audio_path, metadata_dict) with view_count, like_count, comment_count.
    """
    output_dir = output_dir or Path(tempfile.gettempdir()) / "contentmachine"
    output_dir.mkdir(parents=True, exist_ok=True)
    base_name = uuid.uuid4().hex
    output_template = str(output_dir / f"{base_name}.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
                "preferredquality": "192",
            }
        ],
        "quiet": True,
        "no_warnings": True,
    }
    ffmpeg_path = _get_ffmpeg_location()
    if ffmpeg_path:
        ydl_opts["ffmpeg_location"] = ffmpeg_path

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as e:
        raise ValueError(f"Failed to download reel: {e}") from e

    # Extract insights from metadata (Instagram exposes these when available)
    view_count = info.get("view_count") or info.get("play_count")
    if view_count is None:
        view_count = _fetch_view_count_from_embed(url)
    metadata = {
        "view_count": view_count,
        "like_count": info.get("like_count"),
        "comment_count": info.get("comment_count"),
    }

    # FFmpegExtractAudio converts to .wav
    audio_path = output_dir / f"{base_name}.wav"
    if not audio_path.exists():
        for ext in [".mp3", ".m4a", ".webm"]:
            p = output_dir / f"{base_name}{ext}"
            if p.exists():
                return p, metadata
        raise ValueError("Download completed but output file not found")
    return audio_path, metadata


def transcribe_audio(audio_path: Path, model_size: str = "base") -> str:
    """
    Transcribe audio file using faster-whisper.
    Returns the full transcription text.
    """
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(str(audio_path), language=None, vad_filter=True)

    transcription = " ".join(segment.text.strip() for segment in segments if segment.text)
    return transcription.strip()


def list_profile_reels(profile_url: str) -> list[dict]:
    """
    Extract reel URLs from an Instagram profile page using yt-dlp.
    Returns list of dicts with 'url' and optionally 'title'.
    """
    ydl_opts = {
        "extract_flat": True,
        "quiet": True,
        "no_warnings": True,
    }
    ffmpeg_path = _get_ffmpeg_location()
    if ffmpeg_path:
        ydl_opts["ffmpeg_location"] = ffmpeg_path

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(profile_url, download=False)
    except Exception as e:
        raise ValueError(f"Failed to fetch profile reels: {e}") from e

    entries = info.get("entries") or []
    reels = []
    for entry in entries:
        entry_url = entry.get("url") or entry.get("webpage_url")
        if not entry_url:
            continue
        if not entry_url.startswith("http"):
            entry_url = f"https://www.instagram.com/reel/{entry_url}/"
        reels.append({
            "url": entry_url,
            "title": entry.get("title", ""),
        })
    return reels


def transcribe_reel(url: str, model_size: str = "base") -> dict:
    """
    Full pipeline: download Instagram reel, transcribe, and extract insights.
    Returns dict with transcription, view_count, like_count, comment_count.
    """
    audio_path = None
    try:
        audio_path, metadata = download_reel_audio(url)
        transcription = transcribe_audio(audio_path, model_size=model_size)
        if not transcription:
            transcription = "(No speech detected in the reel)"
        return {
            "transcription": transcription,
            "view_count": metadata.get("view_count"),
            "like_count": metadata.get("like_count"),
            "comment_count": metadata.get("comment_count"),
        }
    finally:
        if audio_path and audio_path.exists():
            try:
                audio_path.unlink()
            except OSError:
                pass
