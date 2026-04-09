"""Account management — CRUD for monitored YouTube accounts."""

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Account, Channel, Summary, SummaryScope

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/new")
def new_account_form(request: Request):
    return templates.TemplateResponse("account_form.html", {"request": request})


@router.post("/new")
def create_account(
    request: Request,
    name: str = Form(...),
    youtube_handle: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    account = Account(
        name=name,
        youtube_handle=youtube_handle or None,
        notes=notes or None,
    )
    db.add(account)
    db.commit()
    return RedirectResponse(f"/accounts/{account.id}", status_code=303)


@router.get("/{account_id}")
def account_detail(request: Request, account_id: int, db: Session = Depends(get_db)):
    account = db.query(Account).get(account_id)
    if not account:
        return RedirectResponse("/", status_code=303)

    channels = db.query(Channel).filter(Channel.account_id == account_id).all()
    account_summary = (
        db.query(Summary)
        .filter(Summary.account_id == account_id, Summary.scope == SummaryScope.ACCOUNT)
        .first()
    )

    return templates.TemplateResponse("account_detail.html", {
        "request": request,
        "account": account,
        "channels": channels,
        "account_summary": account_summary,
    })


@router.post("/{account_id}/delete")
def delete_account(account_id: int, db: Session = Depends(get_db)):
    account = db.query(Account).get(account_id)
    if account:
        db.delete(account)
        db.commit()
    return RedirectResponse("/", status_code=303)
