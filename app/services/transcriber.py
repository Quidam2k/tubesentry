"""Local transcription using OpenAI Whisper."""

import logging
from dataclasses import dataclass
from pathlib import Path

from app.config import config

logger = logging.getLogger(__name__)

# Lazy-loaded whisper model
_model = None


def _get_model():
    global _model
    if _model is None:
        import whisper
        model_name = config.whisper.model
        logger.info(f"Loading Whisper model: {model_name}")
        _model = whisper.load_model(model_name)
    return _model


@dataclass
class TranscriptionResult:
    text: str
    language: str | None


def transcribe(audio_path: Path) -> TranscriptionResult:
    """Transcribe an audio file using Whisper.

    Args:
        audio_path: Path to the audio file.

    Returns:
        TranscriptionResult with the full text and detected language.
    """
    model = _get_model()

    whisper_opts = {}
    if config.whisper.language:
        whisper_opts["language"] = config.whisper.language

    logger.info(f"Transcribing: {audio_path}")
    result = model.transcribe(str(audio_path), **whisper_opts)

    text = result.get("text", "").strip()
    language = result.get("language")

    logger.info(f"Transcription complete: {len(text)} characters, language={language}")
    return TranscriptionResult(text=text, language=language)
