"""Channel scanner — discovers new videos and runs the download→transcribe→summarize pipeline."""

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.config import config
from app.models import Channel, Video, Transcript, Summary, SummaryScope, Alert, AlertType, Notification
from app.services import downloader, transcriber, summarizer

logger = logging.getLogger(__name__)


def scan_channel(db: Session, channel: Channel) -> list[Video]:
    """Scan a channel for new videos and add them to the database.

    Returns list of newly discovered Video records.
    """
    limit = config.scanner.initial_video_limit
    logger.info(f"Scanning channel: {channel.channel_url} (limit={limit})")

    video_infos = downloader.get_channel_video_list(channel.channel_url, limit=limit)

    # Update channel name if we got it
    if video_infos and video_infos[0].channel_name and not channel.channel_name:
        channel.channel_name = video_infos[0].channel_name
        if video_infos[0].channel_id:
            channel.youtube_channel_id = video_infos[0].channel_id

    new_videos = []
    for vi in video_infos:
        # Skip if we already have this video
        existing = db.query(Video).filter(Video.youtube_video_id == vi.video_id).first()
        if existing:
            continue

        upload_date = None
        if vi.upload_date:
            try:
                upload_date = datetime.strptime(vi.upload_date, "%Y%m%d")
            except ValueError:
                pass

        video = Video(
            channel_id=channel.id,
            youtube_video_id=vi.video_id,
            title=vi.title,
            description=vi.description,
            duration_seconds=vi.duration_seconds,
            upload_date=upload_date,
        )
        db.add(video)
        new_videos.append(video)

    channel.last_scanned_at = datetime.utcnow()
    db.commit()

    logger.info(f"Found {len(new_videos)} new videos on {channel.channel_name or channel.channel_url}")
    return new_videos


def process_video(db: Session, video: Video) -> None:
    """Run the full pipeline on a single video: download → transcribe → summarize → check alerts."""
    if video.processed:
        return

    logger.info(f"Processing video: {video.title} ({video.youtube_video_id})")

    # Download audio
    result = downloader.download_audio(video.youtube_video_id)

    # Update video metadata from download if we have better data now
    if result.video_info.title and result.video_info.title != "Unknown":
        video.title = result.video_info.title
    if result.video_info.description:
        video.description = result.video_info.description
    if result.video_info.duration_seconds:
        video.duration_seconds = result.video_info.duration_seconds

    try:
        # Transcribe
        transcription = transcriber.transcribe(result.audio_path)

        # Store transcript
        transcript = Transcript(
            video_id=video.id,
            text=transcription.text,
            language=transcription.language,
        )
        db.add(transcript)

        # Summarize
        summary_text = summarizer.summarize_video(
            title=video.title or "Unknown",
            transcript=transcription.text,
        )
        summary = Summary(
            scope=SummaryScope.VIDEO,
            video_id=video.id,
            text=summary_text,
            model_used=_get_model_name(),
        )
        db.add(summary)

        # Check alerts
        _check_alerts(db, video, transcription.text)

        video.processed = True
        db.commit()

    finally:
        # Always clean up the audio file
        downloader.cleanup_audio(result.audio_path)


def _check_alerts(db: Session, video: Video, transcript_text: str) -> None:
    """Check all active alerts for the video's account."""
    channel = video.channel
    account = channel.account
    alerts = db.query(Alert).filter(
        Alert.account_id == account.id,
        Alert.enabled == True,
    ).all()

    for alert in alerts:
        matched = False
        snippet = ""

        if alert.alert_type == AlertType.KEYWORD:
            keyword = alert.criteria.lower()
            text_lower = transcript_text.lower()
            if keyword in text_lower:
                matched = True
                # Extract context around the keyword
                idx = text_lower.index(keyword)
                start = max(0, idx - 100)
                end = min(len(transcript_text), idx + len(keyword) + 100)
                snippet = f"...{transcript_text[start:end]}..."

        elif alert.alert_type == AlertType.AI_CLASSIFICATION:
            result = summarizer.classify_for_alert(
                title=video.title or "Unknown",
                transcript=transcript_text,
                alert_criteria=alert.criteria,
            )
            if result["match"]:
                matched = True
                snippet = f"[{result['confidence']} confidence] {result['reason']}"

        if matched:
            notification = Notification(
                alert_id=alert.id,
                video_id=video.id,
                snippet=snippet,
            )
            db.add(notification)
            logger.info(f"Alert triggered: '{alert.criteria}' on video '{video.title}'")


def generate_channel_summary(db: Session, channel: Channel) -> Summary | None:
    """Generate or regenerate a compiled summary for a channel."""
    video_summaries = (
        db.query(Summary)
        .join(Video, Summary.video_id == Video.id)
        .filter(
            Video.channel_id == channel.id,
            Summary.scope == SummaryScope.VIDEO,
        )
        .all()
    )

    if not video_summaries:
        return None

    combined = "\n\n---\n\n".join(
        f"**{s.video.title}**\n{s.text}" for s in video_summaries if s.video
    )

    summary_text = summarizer.summarize_channel(
        channel_name=channel.channel_name or "Unknown Channel",
        video_summaries=combined,
    )

    # Update or create channel summary
    existing = (
        db.query(Summary)
        .filter(Summary.channel_id == channel.id, Summary.scope == SummaryScope.CHANNEL)
        .first()
    )
    if existing:
        existing.text = summary_text
        existing.model_used = _get_model_name()
        existing.created_at = datetime.utcnow()
        db.commit()
        return existing

    summary = Summary(
        scope=SummaryScope.CHANNEL,
        channel_id=channel.id,
        text=summary_text,
        model_used=_get_model_name(),
    )
    db.add(summary)
    db.commit()
    return summary


def generate_account_summary(db: Session, account_id: int) -> Summary | None:
    """Generate or regenerate a compiled summary for an account."""
    from app.models import Account
    account = db.query(Account).get(account_id)
    if not account:
        return None

    channel_summaries = (
        db.query(Summary)
        .join(Channel, Summary.channel_id == Channel.id)
        .filter(
            Channel.account_id == account_id,
            Summary.scope == SummaryScope.CHANNEL,
        )
        .all()
    )

    if not channel_summaries:
        return None

    combined = "\n\n---\n\n".join(
        f"**{s.channel.channel_name or 'Unknown'}**\n{s.text}" for s in channel_summaries if s.channel
    )

    summary_text = summarizer.summarize_account(
        account_name=account.name,
        channel_summaries=combined,
    )

    existing = (
        db.query(Summary)
        .filter(Summary.account_id == account_id, Summary.scope == SummaryScope.ACCOUNT)
        .first()
    )
    if existing:
        existing.text = summary_text
        existing.model_used = _get_model_name()
        existing.created_at = datetime.utcnow()
        db.commit()
        return existing

    summary = Summary(
        scope=SummaryScope.ACCOUNT,
        account_id=account_id,
        text=summary_text,
        model_used=_get_model_name(),
    )
    db.add(summary)
    db.commit()
    return summary


def _get_model_name() -> str:
    cfg = config.summarizer
    if cfg.backend == "claude":
        return f"claude:{cfg.claude.model}"
    return f"openai_compat:{cfg.openai_compatible.model}"
