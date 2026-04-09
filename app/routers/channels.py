"""Channel management — add/remove channels, trigger scans and processing."""

import threading

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app.models import Channel, Video, Summary, SummaryScope

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.post("/add")
def add_channel(
    account_id: int = Form(...),
    channel_url: str = Form(...),
    is_uploads: bool = Form(False),
    db: Session = Depends(get_db),
):
    channel = Channel(
        account_id=account_id,
        channel_url=channel_url.strip(),
        is_account_uploads=is_uploads,
    )
    db.add(channel)
    db.commit()
    return RedirectResponse(f"/accounts/{account_id}", status_code=303)


@router.get("/{channel_id}")
def channel_detail(request: Request, channel_id: int, db: Session = Depends(get_db)):
    channel = db.query(Channel).get(channel_id)
    if not channel:
        return RedirectResponse("/", status_code=303)

    videos = (
        db.query(Video)
        .filter(Video.channel_id == channel_id)
        .order_by(Video.upload_date.desc().nullslast())
        .all()
    )
    channel_summary = (
        db.query(Summary)
        .filter(Summary.channel_id == channel_id, Summary.scope == SummaryScope.CHANNEL)
        .first()
    )

    return templates.TemplateResponse("channel_detail.html", {
        "request": request,
        "channel": channel,
        "videos": videos,
        "channel_summary": channel_summary,
    })


@router.post("/{channel_id}/scan")
def scan_channel_route(channel_id: int, db: Session = Depends(get_db)):
    """Trigger a scan for new videos on this channel."""
    from app.services.scanner import scan_channel
    channel = db.query(Channel).get(channel_id)
    if not channel:
        return RedirectResponse("/", status_code=303)

    scan_channel(db, channel)
    return RedirectResponse(f"/channels/{channel_id}", status_code=303)


@router.post("/{channel_id}/process")
def process_channel_videos(channel_id: int, db: Session = Depends(get_db)):
    """Start processing unprocessed videos in background."""
    channel = db.query(Channel).get(channel_id)
    if not channel:
        return RedirectResponse("/", status_code=303)

    unprocessed = (
        db.query(Video)
        .filter(Video.channel_id == channel_id, Video.processed == False)
        .all()
    )
    video_ids = [v.id for v in unprocessed]

    # Process in a background thread so we don't block the web UI
    if video_ids:
        thread = threading.Thread(
            target=_process_videos_background,
            args=(video_ids,),
            daemon=True,
        )
        thread.start()

    return RedirectResponse(f"/channels/{channel_id}", status_code=303)


def _process_videos_background(video_ids: list[int]):
    """Process videos in a background thread with its own DB session."""
    from app.services.scanner import process_video
    db = SessionLocal()
    try:
        for vid_id in video_ids:
            video = db.query(Video).get(vid_id)
            if video and not video.processed:
                try:
                    process_video(db, video)
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).error(f"Failed to process video {vid_id}: {e}")
    finally:
        db.close()


@router.post("/{channel_id}/summarize")
def summarize_channel_route(channel_id: int, db: Session = Depends(get_db)):
    """Generate/regenerate a channel-level summary."""
    from app.services.scanner import generate_channel_summary
    channel = db.query(Channel).get(channel_id)
    if channel:
        generate_channel_summary(db, channel)
    return RedirectResponse(f"/channels/{channel_id}", status_code=303)


@router.post("/{channel_id}/delete")
def delete_channel(channel_id: int, db: Session = Depends(get_db)):
    channel = db.query(Channel).get(channel_id)
    if channel:
        account_id = channel.account_id
        db.delete(channel)
        db.commit()
        return RedirectResponse(f"/accounts/{account_id}", status_code=303)
    return RedirectResponse("/", status_code=303)
