"""A/B quality test: YouTube captions vs audio+Whisper.

Runs a sample of videos through BOTH transcription paths and writes side-by-side
transcripts plus a quality assessment, so a human can decide whether captions are
good enough to archive at scale or whether Whisper (or a hybrid) is warranted.

Per the assignment: sample a MIX of recent and OLD videos — YouTube auto-caption
quality degrades with video age, so recent-only sampling would flatter captions.

    # Auto-pick 3 recent + 3 old from the channel, Whisper=medium
    python -m scripts.ab_test --channel-url URL --recent 3 --old 3 --whisper-model medium

    # Explicit video ids
    python -m scripts.ab_test --video-ids abc123 def456 --whisper-model medium
"""

import argparse
import difflib
import logging
import re
import sys
import time
from pathlib import Path

from app.services import downloader, transcriber, captions
from app.services.ffmpeg_check import require_ffmpeg

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s: %(message)s",
                    datefmt="%H:%M:%S")
logger = logging.getLogger("ab_test")


def _gpu_info() -> str:
    try:
        import torch
        if torch.cuda.is_available():
            return f"CUDA available: {torch.cuda.get_device_name(0)}"
        return "CUDA NOT available — Whisper ran on CPU"
    except Exception as e:
        return f"torch/GPU probe failed: {e}"


def _select_video_ids(channel_url: str, recent: int, old: int) -> list[str]:
    url = channel_url.rstrip("/")
    if not url.endswith("/videos"):
        url += "/videos"
    logger.info("Listing channel videos (flat) to pick sample...")
    infos = downloader.get_channel_video_list(url, limit=None)
    ids = [vi.video_id for vi in infos if vi.video_id]
    logger.info(f"Channel has {len(ids)} listed videos")
    picked: list[str] = []
    picked += ids[:recent]                       # newest
    if old and len(ids) > recent:
        picked += ids[-old:]                     # oldest
    # De-dup while preserving order (short channels may overlap)
    seen, out = set(), []
    for v in picked:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _agreement(a: str, b: str) -> float:
    """Rough similarity 0..1 between two transcripts (order-sensitive)."""
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a.split(), b.split()).ratio()


def _caption_artifacts(text: str) -> list[str]:
    notes = []
    if re.search(r"\[(music|applause|laughter|inaudible)\]", text, re.I):
        notes.append("contains bracketed sound tags ([Music] etc.)")
    letters = [c for c in text if c.isalpha()]
    if letters and sum(c.islower() for c in letters) / len(letters) > 0.98:
        notes.append("virtually no capitalization (typical of auto-captions)")
    if text.count(".") + text.count("?") + text.count("!") < len(text) / 800:
        notes.append("very sparse sentence punctuation")
    return notes


def _process_one(video_id: str, whisper_model: str | None, out_dir: Path) -> dict:
    logger.info(f"=== {video_id} ===")
    row = {"video_id": video_id}

    # Caption path
    t0 = time.monotonic()
    cap = captions.fetch_captions(video_id)
    row["caption_seconds"] = time.monotonic() - t0
    if cap:
        row["caption_source"] = cap.source
        row["caption_text"] = cap.text
        row["title"] = cap.video_info.title
        row["upload_date"] = cap.video_info.upload_date
        row["duration"] = cap.video_info.duration_seconds
    else:
        row["caption_source"] = "none"
        row["caption_text"] = ""

    # Whisper path
    t0 = time.monotonic()
    require_ffmpeg()
    dl = downloader.download_audio(video_id)
    row.setdefault("title", dl.video_info.title)
    row.setdefault("upload_date", dl.video_info.upload_date)
    row.setdefault("duration", dl.video_info.duration_seconds)
    try:
        tr = transcriber.transcribe(dl.audio_path, model_name=whisper_model)
        row["whisper_text"] = tr.text
        row["whisper_language"] = tr.language
    finally:
        downloader.cleanup_audio(dl.audio_path)
    row["whisper_seconds"] = time.monotonic() - t0

    row["agreement"] = _agreement(row["caption_text"], row["whisper_text"])
    row["caption_artifacts"] = _caption_artifacts(row["caption_text"])
    row["caption_chars"] = len(row["caption_text"])
    row["whisper_chars"] = len(row["whisper_text"])

    _write_side_by_side(row, out_dir)
    return row


def _write_side_by_side(row: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{row['video_id']}.md"
    lines = [
        f"# A/B transcript — {row.get('title', row['video_id'])}",
        "",
        f"- Video ID: `{row['video_id']}`",
        f"- Upload date: {row.get('upload_date')}",
        f"- Duration (s): {row.get('duration')}",
        f"- Caption source: **{row['caption_source']}**",
        f"- Caption chars: {row['caption_chars']} | Whisper chars: {row['whisper_chars']}",
        f"- Word-order agreement: **{row['agreement']:.2f}**",
        f"- Caption fetch: {row['caption_seconds']:.1f}s | "
        f"Whisper: {row['whisper_seconds']:.1f}s",
        f"- Caption artifacts: {', '.join(row['caption_artifacts']) or 'none noted'}",
        "",
        "## Captions",
        "",
        row["caption_text"] or "_(no captions available)_",
        "",
        "## Whisper",
        "",
        row["whisper_text"] or "_(none)_",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    logger.info(f"Wrote {path}")


def _write_assessment(rows: list[dict], out_dir: Path, whisper_model: str,
                      gpu: str) -> None:
    path = out_dir / "ASSESSMENT.md"
    L = ["# A/B Quality Assessment — captions vs Whisper", "",
         f"- Whisper model: **{whisper_model or 'config default'}**",
         f"- GPU: {gpu}",
         f"- Sample size: {len(rows)} videos",
         "",
         "## Per-video", "",
         "| video | source | agree | cap chars | whisper chars | "
         "cap s | whisper s | artifacts |",
         "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(
            f"| {r['video_id']} | {r['caption_source']} | {r['agreement']:.2f} "
            f"| {r['caption_chars']} | {r['whisper_chars']} "
            f"| {r['caption_seconds']:.1f} | {r['whisper_seconds']:.1f} "
            f"| {len(r['caption_artifacts'])} |"
        )
    have_cap = [r for r in rows if r["caption_source"] != "none"]
    L += ["", "## Aggregate", "",
          f"- Caption availability: {len(have_cap)}/{len(rows)}",
          f"- Mean agreement (where captions exist): "
          f"{(sum(r['agreement'] for r in have_cap) / len(have_cap)):.2f}"
          if have_cap else "- Mean agreement: n/a",
          "",
          "## Notes for reviewer",
          "",
          "- Agreement is word-order similarity, NOT accuracy — low agreement "
          "means the two transcripts diverge, and the side-by-side files show "
          "which is right. Read a few directly.",
          "- Auto-captions typically lack capitalization/punctuation and drop "
          "sound cues; Whisper adds punctuation but can mis-hear names/jargon.",
          "- Check whether older videos show lower caption quality than recent "
          "ones — that is the specific risk this sample tests.",
          ""]
    path.write_text("\n".join(L), encoding="utf-8")
    logger.info(f"Wrote {path}")


def run(args) -> int:
    gpu = _gpu_info()
    logger.info(gpu)
    if args.video_ids:
        ids = args.video_ids
    else:
        ids = _select_video_ids(args.channel_url, args.recent, args.old)
    if not ids:
        logger.error("No video ids to test.")
        return 1
    logger.info(f"Sample: {ids}")

    out_dir = Path(args.out_dir)
    rows = []
    for vid in ids:
        try:
            rows.append(_process_one(vid, args.whisper_model, out_dir))
        except Exception:
            logger.exception(f"A/B failed for {vid}")
    if rows:
        _write_assessment(rows, out_dir, args.whisper_model, gpu)
    print(f"\nDone. Reports in {out_dir}/  (ASSESSMENT.md + per-video .md)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="A/B captions vs Whisper quality test")
    p.add_argument("--channel-url", help="Channel to auto-sample from")
    p.add_argument("--video-ids", nargs="+", help="Explicit video ids to test")
    p.add_argument("--recent", type=int, default=3, help="Newest videos to sample")
    p.add_argument("--old", type=int, default=3, help="Oldest videos to sample")
    p.add_argument("--whisper-model", default="medium",
                   help="Whisper model for the A/B (default: medium)")
    p.add_argument("--out-dir", default="reports/ab",
                   help="Where to write the A/B reports")
    return p


if __name__ == "__main__":
    args = build_parser().parse_args()
    if not args.video_ids and not args.channel_url:
        print("Provide --channel-url or --video-ids", file=sys.stderr)
        sys.exit(2)
    sys.exit(run(args))
