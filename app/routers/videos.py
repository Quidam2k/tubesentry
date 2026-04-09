"""Video detail views — transcript and summary for individual videos."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Video, Transcript, Summary, SummaryScope

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/{video_id}")
def video_detail(request: Request, video_id: int, db: Session = Depends(get_db)):
    video = db.query(Video).get(video_id)
    if not video:
        return RedirectResponse("/", status_code=303)

    transcript = db.query(Transcript).filter(Transcript.video_id == video_id).first()
    summary = (
        db.query(Summary)
        .filter(Summary.video_id == video_id, Summary.scope == SummaryScope.VIDEO)
        .first()
    )

    return templates.TemplateResponse("video_detail.html", {
        "request": request,
        "video": video,
        "transcript": transcript,
        "summary": summary,
    })
