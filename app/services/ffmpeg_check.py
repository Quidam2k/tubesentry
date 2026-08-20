"""ffmpeg availability check.

yt-dlp needs ffmpeg to extract/convert audio. Without it, audio downloads fail
in confusing ways (yt-dlp warns but may leave a partial/unusable file). We check
explicitly at startup so the failure mode is a clear message, not a silent one.
"""

import logging
import shutil
import subprocess

logger = logging.getLogger(__name__)


class FFmpegMissingError(RuntimeError):
    """Raised when ffmpeg is not available on PATH."""


def ffmpeg_available() -> bool:
    """Return True if an ffmpeg binary is resolvable and runnable."""
    path = shutil.which("ffmpeg")
    if not path:
        return False
    try:
        subprocess.run(
            [path, "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=10,
        )
        return True
    except (subprocess.SubprocessError, OSError):
        return False


def require_ffmpeg() -> None:
    """Raise FFmpegMissingError with a helpful message if ffmpeg is missing.

    Only the Whisper/audio path needs ffmpeg; caption-only runs do not. Call
    this before any audio download.
    """
    if ffmpeg_available():
        return
    raise FFmpegMissingError(
        "ffmpeg not found on PATH. It is required for audio download + Whisper "
        "transcription (the caption-only path does not need it).\n"
        "  Windows: choco install ffmpeg   (or scoop install ffmpeg)\n"
        "  macOS:   brew install ffmpeg\n"
        "  Linux:   apt install ffmpeg / dnf install ffmpeg"
    )
