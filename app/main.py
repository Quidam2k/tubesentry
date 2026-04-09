from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.database import init_db
from app.routers import dashboard, accounts, channels, videos, alerts

app = FastAPI(title="TubeSentry", version="0.1.0")

# Static files and templates
app_dir = Path(__file__).parent
app.mount("/static", StaticFiles(directory=app_dir / "static"), name="static")
templates = Jinja2Templates(directory=app_dir / "templates")

# Routers
app.include_router(dashboard.router)
app.include_router(accounts.router, prefix="/accounts", tags=["accounts"])
app.include_router(channels.router, prefix="/channels", tags=["channels"])
app.include_router(videos.router, prefix="/videos", tags=["videos"])
app.include_router(alerts.router, prefix="/alerts", tags=["alerts"])


@app.on_event("startup")
def on_startup():
    init_db()
