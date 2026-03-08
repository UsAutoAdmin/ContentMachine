"""
Unit tests for ContentMachine transcription module.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Import after potential path setup
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from transcribe import transcribe_audio, download_reel_audio, transcribe_reel, _format_count


class TestTranscribeAudio:
    """Tests for transcribe_audio function."""

    def test_transcribe_audio_file_not_found(self):
        """Should raise FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError, match="not found"):
            transcribe_audio(Path("/nonexistent/audio.wav"))

    @patch("transcribe.WhisperModel")
    def test_transcribe_audio_returns_text(self, mock_whisper):
        """Should return transcription from mock segments."""
        mock_segment = MagicMock()
        mock_segment.text = "Hello world"
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([mock_segment], None)
        mock_whisper.return_value = mock_model

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"fake audio")
            path = Path(f.name)

        try:
            result = transcribe_audio(path)
            assert result == "Hello world"
        finally:
            path.unlink()

    @patch("transcribe.WhisperModel")
    def test_transcribe_audio_joins_multiple_segments(self, mock_whisper):
        """Should join multiple segments with spaces."""
        seg1 = MagicMock()
        seg1.text = "First"
        seg2 = MagicMock()
        seg2.text = "Second"
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([seg1, seg2], None)
        mock_whisper.return_value = mock_model

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"fake audio")
            path = Path(f.name)

        try:
            result = transcribe_audio(path)
            assert result == "First Second"
        finally:
            path.unlink()


class TestDownloadReelAudio:
    """Tests for download_reel_audio function."""

    @patch("transcribe.yt_dlp.YoutubeDL")
    def test_download_raises_on_failure(self, mock_ydl):
        """Should raise ValueError when yt-dlp fails."""
        mock_ydl.return_value.__enter__.return_value.extract_info.side_effect = (
            Exception("Download failed")
        )
        with pytest.raises(ValueError, match="Failed to download"):
            download_reel_audio("https://www.instagram.com/reel/fake/")


class TestTranscribeReel:
    """Tests for transcribe_reel function."""

    @patch("transcribe.transcribe_audio")
    @patch("transcribe.download_reel_audio")
    def test_returns_transcription_and_insights(self, mock_download, mock_transcribe):
        """Should return dict with transcription and insights."""
        mock_download.return_value = (Path("/tmp/fake.wav"), {
            "view_count": 1000,
            "like_count": 50,
            "comment_count": 12,
        })
        mock_transcribe.return_value = "Hello world"

        result = transcribe_reel("https://instagram.com/reel/abc/")

        assert result["transcription"] == "Hello world"
        assert result["view_count"] == 1000
        assert result["like_count"] == 50
        assert result["comment_count"] == 12


class TestFetchViewCountFromEmbed:
    """Tests for _fetch_view_count_from_embed fallback."""

    @patch("transcribe.httpx.Client")
    def test_extracts_video_view_count(self, mock_client):
        """Should extract video_view_count from embed page JSON."""
        mock_resp = MagicMock()
        mock_resp.text = '{"shortcode_media": {"video_view_count": 12345}}'
        mock_resp.raise_for_status = MagicMock()
        mock_client.return_value.__enter__.return_value.get.return_value = mock_resp

        from transcribe import _fetch_view_count_from_embed

        result = _fetch_view_count_from_embed("https://www.instagram.com/reel/ABC123/")
        assert result == 12345

    @patch("transcribe.httpx.Client")
    def test_handles_regex_match_in_html(self, mock_client):
        """Should find video_view_count via regex in HTML."""
        mock_resp = MagicMock()
        mock_resp.text = 'window.__additionalDataLoaded("x", {"video_view_count": 99999})'
        mock_resp.raise_for_status = MagicMock()
        mock_client.return_value.__enter__.return_value.get.return_value = mock_resp

        from transcribe import _fetch_view_count_from_embed

        result = _fetch_view_count_from_embed("https://instagram.com/reel/xyz/")
        assert result == 99999


class TestFormatCount:
    """Tests for _format_count helper."""

    def test_none_returns_dash(self):
        assert _format_count(None) == "—"

    def test_small_numbers(self):
        assert _format_count(42) == "42"

    def test_thousands(self):
        assert _format_count(1500) == "1.5K"

    def test_millions(self):
        assert _format_count(1_500_000) == "1.5M"
