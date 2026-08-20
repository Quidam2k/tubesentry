"""Transcript-only archiving core.

This is the captions-first pipeline used by the batch runner. Unlike
scanner.process_video(), it does NOT summarize or run alert checks — the goal is
to archive raw transcript text at channel scale with no LLM dependency.

Fallback chain (path="captions-first"):
    1. YouTube caption track (manual > auto)   -- cheap, no audio
    2. audio download + Whisper                 -- only when no captions
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Video, Transcript
from app.services import downloader, transcriber, captions
from app.services.ffmpeg_check import require_ffmpeg

logger = logging.getLogger(__name__)

# path modes
PATH_CAPTIONS = "captions"
PATH_WHISPER = "whisper"
PATH_CAPTIONS_FIRST = "captions-first"

# outcome methods
M_CAPTION_MANUAL = captions.CAPTION_MANUAL
M_CAPTION_AUTO = captions.CAPTION_AUTO
M_WHISPER = "whisper"
M_NO_CAPTIONS = "no_captions"   # captions-only run, none found -> left unprocessed
M_ERROR = "error"


@dataclass
class ArchiveOutcome:
    video_id: str
    method: str
    processed: bool
    char_count: int
    seconds: float
    error: str | None = None


def _store_transcript(db: Session, video: Video, text: str, language: str | None,
                      source: str, is_auto: bool) -> None:
    """Insert or replace the transcript row for a video."""
    existing = db.query(Transcript).filter(Transcript.video_id == video.id).first()
    if existing:
        existing.text = text
        existing.language = language
        existing.source = source
        existing.is_auto = is_auto
    else:
        db.add(Transcript(
            video_id=video.id,
            text=text,
            language=language,
            source=source,
            is_auto=is_auto,
        ))


def _update_metadata(video: Video, vi: downloader.VideoInfo) -> None:
    if vi.title and vi.title != "Unknown":
        video.title = vi.title
    if vi.description and not video.description:
        video.description = vi.description
    if vi.duration_seconds and not video.duration_seconds:
        video.duration_seconds = vi.duration_seconds
    if vi.upload_date and not video.upload_date:
        try:
            video.upload_date = datetime.strptime(vi.upload_date, "%Y%m%d")
        except ValueError:
            pass


def archive_video(
    db: Session,
    video: Video,
    path: str = PATH_CAPTIONS_FIRST,
    whisper_model: str | None = None,
) -> ArchiveOutcome:
    """Archive one video's transcript. Commits on success.

    Returns an ArchiveOutcome describing what happened (never raises for a
    single-video failure — the error is captured in the outcome so batch runs
    keep going).
    """
    start = time.monotonic()
    vid = video.youtube_video_id

    try:
        # --- Caption path -------------------------------------------------
        if path in (PATH_CAPTIONS, PATH_CAPTIONS_FIRST):
            cap = captions.fetch_captions(vid)
            if cap is not None:
                _update_metadata(video, cap.video_info)
                _store_transcript(db, video, cap.text, cap.language,
                                  cap.source, cap.is_auto)
                video.processed = True
                db.commit()
                return ArchiveOutcome(
                    video_id=vid, method=cap.source, processed=True,
                    char_count=len(cap.text), seconds=time.monotonic() - start,
                )
            if path == PATH_CAPTIONS:
                # Captions-only run: no captions -> leave unprocessed for a
                # later Whisper pass. Not an error.
                return ArchiveOutcome(
                    video_id=vid, method=M_NO_CAPTIONS, processed=False,
                    char_count=0, seconds=time.monotonic() - start,
                )

        # --- Whisper path -------------------------------------------------
        require_ffmpeg()
        result = downloader.download_audio(vid)
        _update_metadata(video, result.video_info)
        try:
            tr = transcriber.transcribe(result.audio_path, model_name=whisper_model)
            _store_transcript(db, video, tr.text, tr.language, M_WHISPER, False)
            video.processed = True
            db.commit()
            return ArchiveOutcome(
                video_id=vid, method=M_WHISPER, processed=True,
                char_count=len(tr.text), seconds=time.monotonic() - start,
            )
        finally:
            downloader.cleanup_audio(result.audio_path)

    except Exception as e:
        db.rollback()
        logger.exception(f"archive_video failed for {vid}")
        return ArchiveOutcome(
            video_id=vid, method=M_ERROR, processed=False,
            char_count=0, seconds=time.monotonic() - start, error=str(e),
        )
