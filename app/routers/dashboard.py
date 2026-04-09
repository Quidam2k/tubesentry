"""Main dashboard — overview of all monitored accounts."""

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Account, Notification

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    accounts = db.query(Account).all()
    unread_count = db.query(Notification).filter(Notification.read == False).count()
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "accounts": accounts,
        "unread_count": unread_count,
    })
