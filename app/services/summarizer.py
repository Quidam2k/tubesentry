"""Pluggable LLM summarization — Claude API or OpenAI-compatible (LM Studio, Ollama, etc.)."""

import logging
from abc import ABC, abstractmethod

from app.config import config

logger = logging.getLogger(__name__)

VIDEO_SUMMARY_PROMPT = """You are analyzing a YouTube video transcript for a parent who wants to understand what their child might be watching.

Video title: {title}

Provide a concise summary that covers:
1. **Topic/Content**: What is this video about?
2. **Tone**: What is the overall tone? (educational, entertainment, aggressive, calm, etc.)
3. **Notable Content**: Flag anything a parent might want to know about — language, themes, attitudes, behaviors depicted or encouraged.
4. **Age Appropriateness**: Your assessment of the content's suitability.

Keep the summary to 2-4 paragraphs. Be factual and specific, not vague.

Transcript:
{transcript}"""

CHANNEL_SUMMARY_PROMPT = """You are analyzing summaries from multiple videos on a YouTube channel to help a parent understand what kind of content this channel produces.

Channel: {channel_name}

Below are summaries of individual videos from this channel. Provide a compiled overview that covers:
1. **Overall Theme**: What does this channel primarily cover?
2. **Content Patterns**: Common themes, tone, and style across videos.
3. **Parental Notes**: Anything a parent should be aware of — recurring themes, language patterns, concerning or positive content.
4. **Overall Assessment**: Brief assessment of the channel's content.

Keep it to 2-3 paragraphs.

Video summaries:
{video_summaries}"""

ACCOUNT_SUMMARY_PROMPT = """You are analyzing channel summaries across a child's YouTube subscriptions to help a parent get an overview of their child's YouTube diet.

Account: {account_name}

Below are summaries of channels this account follows. Provide a high-level overview:
1. **Content Diet**: What types of content does this child primarily consume?
2. **Patterns**: Any notable patterns across channels.
3. **Concerns**: Anything that might warrant parental attention.
4. **Positives**: Any educational or constructive content worth noting.

Keep it to 2-3 paragraphs.

Channel summaries:
{channel_summaries}"""

ALERT_CLASSIFICATION_PROMPT = """You are a content classifier helping parents monitor their child's YouTube viewing.

The parent has set up the following alert rule:
"{alert_criteria}"

Review the following video transcript and determine if it matches the alert criteria.

Video title: {title}

Respond with EXACTLY this format:
MATCH: yes/no
CONFIDENCE: high/medium/low
REASON: <one sentence explaining why>

If you're unsure, err on the side of flagging it (say yes).

Transcript:
{transcript}"""


class SummarizerBackend(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Send a prompt to the LLM and return the response text."""
        ...


class ClaudeBackend(SummarizerBackend):
    def __init__(self):
        import anthropic
        self.client = anthropic.Anthropic(api_key=config.summarizer.claude.api_key)
        self.model = config.summarizer.claude.model

    def generate(self, prompt: str) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text


class OpenAICompatibleBackend(SummarizerBackend):
    def __init__(self):
        from openai import OpenAI
        cfg = config.summarizer.openai_compatible
        self.client = OpenAI(base_url=cfg.base_url, api_key=cfg.api_key)
        self.model = cfg.model

    def generate(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2048,
        )
        return response.choices[0].message.content or ""


def _get_backend() -> SummarizerBackend:
    backend_name = config.summarizer.backend
    if backend_name == "claude":
        return ClaudeBackend()
    elif backend_name == "openai_compatible":
        return OpenAICompatibleBackend()
    else:
        raise ValueError(f"Unknown summarizer backend: {backend_name}")


# Lazy singleton
_backend: SummarizerBackend | None = None


def get_backend() -> SummarizerBackend:
    global _backend
    if _backend is None:
        _backend = _get_backend()
    return _backend


def summarize_video(title: str, transcript: str) -> str:
    """Generate a summary for a single video transcript."""
    prompt = VIDEO_SUMMARY_PROMPT.format(title=title, transcript=transcript)
    logger.info(f"Summarizing video: {title}")
    return get_backend().generate(prompt)


def summarize_channel(channel_name: str, video_summaries: str) -> str:
    """Generate a compiled summary for a channel from its video summaries."""
    prompt = CHANNEL_SUMMARY_PROMPT.format(
        channel_name=channel_name,
        video_summaries=video_summaries,
    )
    logger.info(f"Summarizing channel: {channel_name}")
    return get_backend().generate(prompt)


def summarize_account(account_name: str, channel_summaries: str) -> str:
    """Generate a compiled summary for an account from its channel summaries."""
    prompt = ACCOUNT_SUMMARY_PROMPT.format(
        account_name=account_name,
        channel_summaries=channel_summaries,
    )
    logger.info(f"Summarizing account: {account_name}")
    return get_backend().generate(prompt)


def classify_for_alert(title: str, transcript: str, alert_criteria: str) -> dict:
    """Check if a video transcript matches an alert's criteria.

    Returns dict with keys: match (bool), confidence (str), reason (str).
    """
    prompt = ALERT_CLASSIFICATION_PROMPT.format(
        alert_criteria=alert_criteria,
        title=title,
        transcript=transcript,
    )
    response = get_backend().generate(prompt)

    # Parse the structured response
    result = {"match": False, "confidence": "low", "reason": ""}
    for line in response.strip().split("\n"):
        line = line.strip()
        if line.upper().startswith("MATCH:"):
            result["match"] = "yes" in line.lower()
        elif line.upper().startswith("CONFIDENCE:"):
            result["confidence"] = line.split(":", 1)[1].strip().lower()
        elif line.upper().startswith("REASON:"):
            result["reason"] = line.split(":", 1)[1].strip()

    return result
