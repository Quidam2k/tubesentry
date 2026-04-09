# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project: TubeSentry

TubeSentry is a local-first parental awareness tool for YouTube. It downloads audio from YouTube channels via yt-dlp, transcribes locally with Whisper, and generates AI summaries so parents can stay informed about what their kids watch and post without watching everything themselves.

## Tech Stack

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy with SQLite
- **Frontend:** Jinja2 templates + HTMX (no Node toolchain)
- **YouTube:** yt-dlp (no YouTube API dependency)
- **Transcription:** OpenAI Whisper (local)
- **Summarization:** Pluggable — Claude API and OpenAI-compatible API (for local models via LM Studio, Ollama, etc.)

## Architecture

### Data Flow Pipeline
```
yt-dlp (audio download) → Whisper (transcription) → LLM (summarization) → SQLite (storage) → FastAPI (web UI)
```
Audio files are deleted after transcription. Only text (transcripts + summaries) is stored long-term.

### Core Data Model
- **Account** — A monitored YouTube account (one per kid)
- **Channel** — A YouTube channel being tracked (linked to an account's subscriptions or directly added)
- **Video** — Individual video metadata
- **Transcript** — Full text transcript from Whisper
- **Summary** — AI-generated summary (per-video, per-channel, or per-account)
- **Alert** — User-defined alert rules (keywords or natural language descriptions)
- **Notification** — Triggered alerts shown in the web UI

### Key Design Decisions
- **No YouTube API:** Uses yt-dlp to avoid API quotas and OAuth complexity. Parent provides channel URLs or account subscription lists.
- **Audio-only downloads:** Video files are never stored. Audio is downloaded, transcribed, then deleted.
- **Local-first:** All processing happens on the user's machine. Cloud LLMs are optional.
- **Pluggable LLM:** Summarizer interface supports both Claude API (via Anthropic SDK) and any OpenAI-compatible endpoint (LM Studio, Ollama, etc.) configured in config.yaml.
- **Multi-account:** One parent dashboard can monitor multiple kid accounts.

### Project Structure
```
app/
├── main.py              # FastAPI app entry point
├── models.py            # SQLAlchemy models
├── database.py          # DB session/engine setup
├── config.py            # Configuration loading
├── routers/             # FastAPI route handlers
│   ├── dashboard.py     # Main parent dashboard
│   ├── accounts.py      # Kid account CRUD
│   ├── channels.py      # Channel management
│   ├── videos.py        # Video detail views
│   └── alerts.py        # Alert config & triggered notifications
├── services/            # Business logic
│   ├── downloader.py    # yt-dlp audio download + cleanup
│   ├── transcriber.py   # Whisper transcription
│   ├── summarizer.py    # LLM summarization (pluggable backend)
│   └── scanner.py       # Channel scanning / subscription sync
├── templates/           # Jinja2 HTML templates
└── static/              # CSS/JS assets
```

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the development server
uvicorn app.main:app --reload --port 8000

# Run tests
pytest

# Run a single test
pytest tests/test_something.py::test_name -v
```

## Future Features (Not Yet Implemented)
- **Watch history monitoring:** Browser extension to capture what videos are watched (YouTube API no longer exposes this). Noted as important future work.
- **Watch progress tracking:** How much of a video was watched. No viable data source yet.
- **Email notifications:** Currently alerts are web UI only. Email is a stretch goal.
- **User uploads monitoring:** Track videos posted by the monitored account.
