"""Batch transcript-archiving runner for a whole YouTube channel.

Captions-first, transcripts-only, resumable. Web-click processing doesn't scale
to thousands of videos; this does.

Examples:
    # Pilot: 20 newest videos, captions-first (default)
    python -m scripts.archive --channel-url "https://youtube.com/c/BeauoftheFifthColumn" --limit 20

    # Force the Whisper path for everything (audio download + transcribe)
    python -m scripts.archive --channel-url URL --limit 5 --path whisper --whisper-model medium

    # Full run, oldest-first
    python -m scripts.archive --channel-url URL --path captions-first --order oldest

Resume: videos already marked processed are skipped, so re-running continues
where it left off.
"""

import argparse
import logging
import sys
import time
from datetime import datetime

from app.database import SessionLocal, init_db
from app.models import Account, Channel, Video
from app.services import downloader, archiver
from app.services.ffmpeg_check import ffmpeg_available

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("archive")


def _canonical_videos_url(channel_url: str) -> str:
    url = channel_url.rstrip("/")
    if not url.endswith("/videos"):
        url += "/videos"
    return url


def _get_or_create_channel(db, channel_url: str, account_name: str) -> Channel:
    channel = db.query(Channel).filter(Channel.channel_url == channel_url).first()
    if channel:
        return channel
    account = db.query(Account).filter(Account.name == account_name).first()
    if not account:
        account = Account(name=account_name, notes="Created by scripts/archive.py")
        db.add(account)
        db.flush()
    channel = Channel(account_id=account.id, channel_url=channel_url)
    db.add(channel)
    db.commit()
    logger.info(f"Created channel record for {channel_url}")
    return channel


def _discover(db, channel: Channel, url: str, limit: int | None) -> int:
    """Populate the DB with videos from the channel. Returns count of new rows.

    yt-dlp returns a channel's /videos tab newest-first, so with --limit we grab
    the newest N. Discovery order is preserved via each Video's id (insertion
    order), which we rely on for newest/oldest processing order.
    """
    infos = downloader.get_channel_video_list(url, limit=limit)
    if infos and infos[0].channel_name and not channel.channel_name:
        channel.channel_name = infos[0].channel_name
        if infos[0].channel_id:
            channel.youtube_channel_id = infos[0].channel_id
    new = 0
    for vi in infos:
        if not vi.video_id:
            continue
        if db.query(Video).filter(Video.youtube_video_id == vi.video_id).first():
            continue
        upload_date = None
        if vi.upload_date:
            try:
                upload_date = datetime.strptime(vi.upload_date, "%Y%m%d")
            except ValueError:
                pass
        db.add(Video(
            channel_id=channel.id,
            youtube_video_id=vi.video_id,
            title=vi.title,
            description=vi.description,
            duration_seconds=vi.duration_seconds,
            upload_date=upload_date,
        ))
        new += 1
    channel.last_scanned_at = datetime.utcnow()
    db.commit()
    logger.info(f"Discovery: {len(infos)} listed, {new} new added to DB")
    return new


def _fmt_hms(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}"


def run(args) -> int:
    init_db()
    db = SessionLocal()
    try:
        url = _canonical_videos_url(args.channel_url)
        channel = _get_or_create_channel(db, args.channel_url, args.account_name)

        if not args.no_discover:
            _discover(db, channel, url, args.limit)

        # Build the work list. Newest-first == insertion order (id ASC), since
        # discovery inserts newest first. Oldest-first reverses it.
        q = db.query(Video).filter(Video.channel_id == channel.id)
        if not args.reprocess:
            q = q.filter(Video.processed == False)  # noqa: E712
        q = q.order_by(Video.id.asc() if args.order == "newest" else Video.id.desc())
        videos = q.all()
        if args.limit:
            videos = videos[: args.limit]

        total = len(videos)
        if total == 0:
            logger.info("No unprocessed videos to archive. Done.")
            return 0

        if args.path in (archiver.PATH_WHISPER, archiver.PATH_CAPTIONS_FIRST):
            if not ffmpeg_available():
                logger.warning("ffmpeg not on PATH — the Whisper fallback will "
                               "fail. Caption hits are unaffected.")

        logger.info(f"Archiving {total} videos | path={args.path} | "
                    f"order={args.order} | whisper_model="
                    f"{args.whisper_model or 'config default'}")

        stats = {"total": total, "start": time.monotonic()}
        method_counts: dict[str, int] = {}
        method_seconds: dict[str, float] = {}
        errors = []

        for i, video in enumerate(videos, 1):
            outcome = archiver.archive_video(
                db, video, path=args.path, whisper_model=args.whisper_model,
            )
            method_counts[outcome.method] = method_counts.get(outcome.method, 0) + 1
            method_seconds[outcome.method] = (
                method_seconds.get(outcome.method, 0.0) + outcome.seconds
            )
            if outcome.error:
                errors.append((outcome.video_id, outcome.error))

            elapsed = time.monotonic() - stats["start"]
            avg = elapsed / i
            eta = avg * (total - i)
            # Cumulative caption-hit % for milestone visibility.
            cap_hits = (
                method_counts.get(archiver.M_CAPTION_MANUAL, 0)
                + method_counts.get(archiver.M_CAPTION_AUTO, 0)
            )
            logger.info(
                f"[{i}/{total}] {outcome.video_id} -> {outcome.method} "
                f"({outcome.char_count} chars, {outcome.seconds:.1f}s) | "
                f"caps {cap_hits}/{i} ({100 * cap_hits / i:.0f}%) | "
                f"ETA {_fmt_hms(eta)}"
            )

            # Optional throttle to stay under YouTube's bot-detection radar on
            # large runs (opt-in; default 0 preserves prior behavior).
            if args.sleep and i < total:
                time.sleep(args.sleep)

        _print_summary(total, method_counts, method_seconds,
                       time.monotonic() - stats["start"], errors)
        return 0
    finally:
        db.close()


def _print_summary(total, method_counts, method_seconds, elapsed, errors) -> None:
    caption_hits = (
        method_counts.get(archiver.M_CAPTION_MANUAL, 0)
        + method_counts.get(archiver.M_CAPTION_AUTO, 0)
    )
    print("\n" + "=" * 60)
    print("ARCHIVE RUN SUMMARY")
    print("=" * 60)
    print(f"Videos attempted : {total}")
    print(f"Wall time        : {_fmt_hms(elapsed)}")
    print(f"Caption hit rate : {caption_hits}/{total} "
          f"({100 * caption_hits / total:.0f}%)" if total else "n/a")
    print("\nBy method (count | total sec | avg sec):")
    for method in sorted(method_counts):
        c = method_counts[method]
        s = method_seconds.get(method, 0.0)
        print(f"  {method:16s} {c:4d} | {s:8.1f} | {s / c:6.1f}")
    if errors:
        print(f"\nErrors ({len(errors)}):")
        for vid, err in errors[:20]:
            print(f"  {vid}: {err}")
    print("=" * 60)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Batch channel transcript archiver")
    p.add_argument("--channel-url", required=True, help="YouTube channel URL")
    p.add_argument("--limit", type=int, default=None,
                   help="Max videos to process this run (newest N by default)")
    p.add_argument("--order", choices=["newest", "oldest"], default="newest",
                   help="Processing order (default: newest-first)")
    p.add_argument("--path", choices=[archiver.PATH_CAPTIONS_FIRST,
                                      archiver.PATH_CAPTIONS, archiver.PATH_WHISPER],
                   default=archiver.PATH_CAPTIONS_FIRST,
                   help="Transcription path (default: captions-first)")
    p.add_argument("--whisper-model", default=None,
                   help="Whisper model override for the audio path (e.g. medium)")
    p.add_argument("--account-name", default="Archive",
                   help="Account record to attach the channel to")
    p.add_argument("--reprocess", action="store_true",
                   help="Re-process videos even if already marked processed")
    p.add_argument("--no-discover", action="store_true",
                   help="Skip channel discovery; only process videos already in DB")
    p.add_argument("--sleep", type=float, default=0.0,
                   help="Seconds to sleep between videos (throttle to avoid "
                        "YouTube bot-detection on large runs; default 0)")
    return p


if __name__ == "__main__":
    args = build_parser().parse_args()
    try:
        sys.exit(run(args))
    except KeyboardInterrupt:
        print("\nInterrupted — progress is saved (resume by re-running).")
        sys.exit(130)
