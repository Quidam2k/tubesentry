import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.database import init_db
from app.routers import dashboard, accounts, channels, videos, alerts
from app.services.ffmpeg_check import ffmpeg_available

logger = logging.getLogger(__name__)

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
    # ffmpeg is required only for the audio+Whisper path; caption-only archiving
    # works without it. Warn loudly rather than fail so the web UI still starts.
    if not ffmpeg_available():
        logger.warning(
            "ffmpeg not found on PATH — audio download + Whisper transcription "
            "will fail. Install ffmpeg, or use captions-only archiving. "
            "(choco install ffmpeg / brew install ffmpeg / apt install ffmpeg)"
        )
