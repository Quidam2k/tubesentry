"""Alert management and notification display."""

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Alert, AlertType, Notification, Account

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/")
def alerts_list(request: Request, db: Session = Depends(get_db)):
    alerts = db.query(Alert).all()
    accounts = db.query(Account).all()
    notifications = (
        db.query(Notification)
        .order_by(Notification.created_at.desc())
        .limit(50)
        .all()
    )
    unread_count = db.query(Notification).filter(Notification.read == False).count()

    return templates.TemplateResponse("alerts.html", {
        "request": request,
        "alerts": alerts,
        "accounts": accounts,
        "notifications": notifications,
        "unread_count": unread_count,
    })


@router.post("/new")
def create_alert(
    account_id: int = Form(...),
    alert_type: str = Form(...),
    criteria: str = Form(...),
    db: Session = Depends(get_db),
):
    alert = Alert(
        account_id=account_id,
        alert_type=AlertType(alert_type),
        criteria=criteria.strip(),
    )
    db.add(alert)
    db.commit()
    return RedirectResponse("/alerts", status_code=303)


@router.post("/{alert_id}/toggle")
def toggle_alert(alert_id: int, db: Session = Depends(get_db)):
    alert = db.query(Alert).get(alert_id)
    if alert:
        alert.enabled = not alert.enabled
        db.commit()
    return RedirectResponse("/alerts", status_code=303)


@router.post("/{alert_id}/delete")
def delete_alert(alert_id: int, db: Session = Depends(get_db)):
    alert = db.query(Alert).get(alert_id)
    if alert:
        db.delete(alert)
        db.commit()
    return RedirectResponse("/alerts", status_code=303)


@router.post("/notifications/{notification_id}/read")
def mark_read(notification_id: int, db: Session = Depends(get_db)):
    notification = db.query(Notification).get(notification_id)
    if notification:
        notification.read = True
        db.commit()
    return RedirectResponse("/alerts", status_code=303)


@router.post("/notifications/read-all")
def mark_all_read(db: Session = Depends(get_db)):
    db.query(Notification).filter(Notification.read == False).update({"read": True})
    db.commit()
    return RedirectResponse("/alerts", status_code=303)
