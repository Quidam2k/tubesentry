"""Local transcription using OpenAI Whisper."""

import logging
from dataclasses import dataclass
from pathlib import Path

from app.config import config

logger = logging.getLogger(__name__)

# Lazy-loaded whisper models, cached per model name so the A/B harness can run
# a heavier model (e.g. "medium") without evicting the default.
_models: dict[str, object] = {}


def _get_model(model_name: str | None = None):
    name = model_name or config.whisper.model
    if name not in _models:
        import whisper
        logger.info(f"Loading Whisper model: {name}")
        _models[name] = whisper.load_model(name)
    return _models[name]


@dataclass
class TranscriptionResult:
    text: str
    language: str | None


def transcribe(audio_path: Path, model_name: str | None = None) -> TranscriptionResult:
    """Transcribe an audio file using Whisper.

    Args:
        audio_path: Path to the audio file.
        model_name: Optional Whisper model override (e.g. "medium"). Defaults
            to the configured model.

    Returns:
        TranscriptionResult with the full text and detected language.
    """
    model = _get_model(model_name)

    whisper_opts = {}
    if config.whisper.language:
        whisper_opts["language"] = config.whisper.language

    logger.info(f"Transcribing: {audio_path}")
    result = model.transcribe(str(audio_path), **whisper_opts)

    text = result.get("text", "").strip()
    language = result.get("language")

    logger.info(f"Transcription complete: {len(text)} characters, language={language}")
    return TranscriptionResult(text=text, language=language)
