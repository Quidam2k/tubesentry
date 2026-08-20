"""YouTube audio downloader using yt-dlp."""

import logging
from dataclasses import dataclass
from pathlib import Path

import yt_dlp

from app.config import config

logger = logging.getLogger(__name__)


@dataclass
class VideoInfo:
    """Metadata extracted from a YouTube video."""
    video_id: str
    title: str
    description: str | None
    duration_seconds: int | None
    upload_date: str | None  # YYYYMMDD format from yt-dlp
    channel_name: str | None
    channel_id: str | None


@dataclass
class DownloadResult:
    """Result of downloading a video's audio."""
    video_info: VideoInfo
    audio_path: Path


def _get_download_dir() -> Path:
    download_dir = Path(config.download_dir)
    download_dir.mkdir(parents=True, exist_ok=True)
    return download_dir


def get_channel_video_list(channel_url: str, limit: int | None = None) -> list[VideoInfo]:
    """Get a list of videos from a YouTube channel without downloading them."""
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "playlistend": limit,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(channel_url, download=False)
        if info is None:
            return []

        entries = info.get("entries", [])
        videos = []
        for entry in entries:
            if entry is None:
                continue
            videos.append(VideoInfo(
                video_id=entry.get("id", ""),
                title=entry.get("title", "Unknown"),
                description=entry.get("description"),
                duration_seconds=entry.get("duration"),
                upload_date=entry.get("upload_date"),
                channel_name=info.get("channel") or info.get("uploader"),
                channel_id=info.get("channel_id"),
            ))

        return videos


def download_audio(video_id: str) -> DownloadResult:
    """Download audio from a single YouTube video. Returns path to the audio file."""
    download_dir = _get_download_dir()
    output_template = str(download_dir / "%(id)s.%(ext)s")

    # Extract to WAV (PCM) rather than MP3: Whisper decodes WAV fine and PCM is
    # always available in ffmpeg, whereas MP3 needs the libmp3lame encoder which
    # many ffmpeg builds omit. The file is temporary and deleted after transcribe.
    ydl_opts = {
        "format": "bestaudio/best",
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "wav",
        }],
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
    }

    url = f"https://www.youtube.com/watch?v={video_id}"

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if info is None:
            raise RuntimeError(f"Failed to download video {video_id}")

        video_info = VideoInfo(
            video_id=info.get("id", video_id),
            title=info.get("title", "Unknown"),
            description=info.get("description"),
            duration_seconds=info.get("duration"),
            upload_date=info.get("upload_date"),
            channel_name=info.get("channel") or info.get("uploader"),
            channel_id=info.get("channel_id"),
        )

        audio_path = download_dir / f"{video_id}.wav"
        if not audio_path.exists():
            # Postprocessor may leave a different extension; find the audio file.
            candidates = [
                p for p in download_dir.glob(f"{video_id}.*")
                if p.suffix.lower() != ".part"
            ]
            if candidates:
                audio_path = candidates[0]
            else:
                raise RuntimeError(f"Audio file not found after download for {video_id}")

        logger.info(f"Downloaded audio: {audio_path} ({video_info.title})")
        return DownloadResult(video_info=video_info, audio_path=audio_path)


def cleanup_audio(audio_path: Path) -> None:
    """Delete an audio file after transcription."""
    if audio_path.exists():
        audio_path.unlink()
        logger.info(f"Cleaned up audio: {audio_path}")
