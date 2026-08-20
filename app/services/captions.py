"""YouTube caption/subtitle fetching via yt-dlp.

Captions-first archiving: pull YouTube's own caption track (manual/uploaded when
available, else auto-generated) instead of downloading audio and running Whisper.
At channel scale (thousands of videos) this is the difference between minutes and
1000+ hours of transcription.

The fallback chain per video is:
    (a) manual/uploaded caption  -> highest quality
    (b) auto-generated caption   -> good enough for most speech
    (c) None                     -> caller falls back to audio + Whisper
"""

import json
import logging
import re
import urllib.request
from dataclasses import dataclass

import yt_dlp

from app.services.downloader import VideoInfo

logger = logging.getLogger(__name__)

# Language codes to try, in order. "en-orig" is YouTube's original-language
# track for videos whose default language is English; some channels expose it.
DEFAULT_CAPTION_LANGS = ("en", "en-US", "en-GB", "en-orig")

CAPTION_MANUAL = "caption_manual"
CAPTION_AUTO = "caption_auto"


@dataclass
class CaptionResult:
    """A successfully fetched caption track."""
    text: str
    source: str          # CAPTION_MANUAL or CAPTION_AUTO
    language: str         # the language code the track was found under
    is_auto: bool
    video_info: VideoInfo


def _info_to_videoinfo(info: dict, fallback_id: str) -> VideoInfo:
    return VideoInfo(
        video_id=info.get("id", fallback_id),
        title=info.get("title", "Unknown"),
        description=info.get("description"),
        duration_seconds=info.get("duration"),
        upload_date=info.get("upload_date"),
        channel_name=info.get("channel") or info.get("uploader"),
        channel_id=info.get("channel_id"),
    )


def _pick_track(tracks: dict, langs) -> tuple[str, list] | None:
    """From a yt-dlp subtitles/automatic_captions dict, pick the best language
    track. Returns (lang_code, list_of_format_dicts) or None."""
    if not tracks:
        return None
    for lang in langs:
        if lang in tracks and tracks[lang]:
            return lang, tracks[lang]
    # Fall back to any English-ish track we didn't explicitly list.
    for code, fmts in tracks.items():
        if code.lower().startswith("en") and fmts:
            return code, fmts
    return None


def _pick_format(fmts: list) -> dict | None:
    """Prefer vtt (easy to clean), then srv1/json3, then whatever exists."""
    by_ext = {f.get("ext"): f for f in fmts if f.get("url")}
    for ext in ("vtt", "srv1", "json3", "srv3", "ttml"):
        if ext in by_ext:
            return by_ext[ext]
    return next((f for f in fmts if f.get("url")), None)


def _http_get(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


# --- Parsers ---------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")            # inline <00:00:01.000> / <c> tags
_TIMING_RE = re.compile(r"-->")


def _clean_vtt(raw: str) -> str:
    """Turn a WEBVTT payload into readable prose.

    Auto-caption VTT uses a rolling window: each cue repeats the tail of the
    previous cue plus one new line. We strip timing/markup and then dedupe so
    the rolling repeats collapse to a single clean transcript.
    """
    out: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.upper().startswith("WEBVTT"):
            continue
        if line.startswith(("NOTE", "STYLE", "REGION", "Kind:", "Language:")):
            continue
        if _TIMING_RE.search(line):
            continue
        if line.isdigit():  # cue index
            continue
        line = _TAG_RE.sub("", line)               # remove inline tags
        line = line.replace("&nbsp;", " ").strip()
        if not line:
            continue
        # Dedupe: skip if identical to the last kept line (rolling window).
        if out and out[-1] == line:
            continue
        out.append(line)
    return _stitch(out)


def _clean_json3(raw: str) -> str:
    data = json.loads(raw)
    lines: list[str] = []
    for event in data.get("events", []):
        segs = event.get("segs")
        if not segs:
            continue
        text = "".join(seg.get("utf8", "") for seg in segs)
        text = text.replace("\n", " ").strip()
        if not text:
            continue
        if lines and lines[-1] == text:
            continue
        lines.append(text)
    return _stitch(lines)


def _stitch(lines: list[str]) -> str:
    """Join caption lines into paragraphs, collapsing whitespace."""
    text = " ".join(lines)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse(raw: str, ext: str) -> str:
    if ext == "json3":
        try:
            return _clean_json3(raw)
        except (ValueError, KeyError):
            pass
    # vtt, srv1, srv3, ttml all reduce acceptably through the VTT/text cleaner
    # once tags and timing lines are stripped.
    return _clean_vtt(raw)


# --- Public API ------------------------------------------------------------

def fetch_captions(
    video_id: str,
    langs=DEFAULT_CAPTION_LANGS,
    info: dict | None = None,
) -> CaptionResult | None:
    """Fetch the best available caption track for a video.

    Returns a CaptionResult, or None if no usable caption track exists (caller
    should then fall back to audio + Whisper).

    If `info` (a yt-dlp info dict already extracted by the caller) is provided,
    no extra network round-trip is made to discover tracks.
    """
    url = f"https://www.youtube.com/watch?v={video_id}"

    if info is None:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    if info is None:
        return None

    video_info = _info_to_videoinfo(info, video_id)

    manual = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}

    chosen = _pick_track(manual, langs)
    is_auto = False
    source = CAPTION_MANUAL
    if chosen is None:
        chosen = _pick_track(auto, langs)
        is_auto = True
        source = CAPTION_AUTO
    if chosen is None:
        logger.info(f"No captions available for {video_id}")
        return None

    lang, fmts = chosen
    fmt = _pick_format(fmts)
    if not fmt:
        return None

    try:
        raw = _http_get(fmt["url"])
    except Exception as e:  # network/URL expiry — treat as no captions
        logger.warning(f"Caption download failed for {video_id} ({lang}): {e}")
        return None

    text = _parse(raw, fmt.get("ext", ""))
    if not text.strip():
        logger.info(f"Caption track for {video_id} parsed empty; skipping")
        return None

    logger.info(
        f"Captions for {video_id}: {source} lang={lang} "
        f"ext={fmt.get('ext')} chars={len(text)}"
    )
    return CaptionResult(
        text=text,
        source=source,
        language=lang,
        is_auto=is_auto,
        video_info=video_info,
    )
