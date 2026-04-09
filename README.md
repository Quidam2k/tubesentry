# TubeSentry

**TubeSentry helps parents stay informed about what their kids watch and post on YouTube — without having to watch it all themselves.**

It downloads audio from YouTube channels, transcribes it locally using Whisper, and generates AI-powered summaries at the video, channel, and account level. Parents can monitor subscribed channels, track uploaded content, and set up keyword or natural-language alerts to be notified about videos that match concerns they define — all from a simple web dashboard.

## How It Works

- **Subscribe & Sync** — Point TubeSentry at YouTube channels or an entire subscription list. It keeps your library updated as new videos are posted.
- **Transcribe & Summarize** — Audio is transcribed locally (Whisper) and summarized by AI (Claude API or local models like Gemma). No cloud dependency required.
- **Monitor Uploads** — See what the monitored account has posted publicly.
- **Smart Alerts** — Define keywords or describe concerns in plain English. Get flagged when something matches.
- **Multi-Account** — Monitor multiple kids from one parent dashboard.

## Privacy

Everything runs locally. No data leaves your machine unless you choose a cloud LLM. No accounts, no subscriptions required beyond the tool itself.

## Tech Stack

- Python 3.11+
- FastAPI (backend)
- SQLite via SQLAlchemy (database)
- Jinja2 + HTMX (frontend)
- yt-dlp (YouTube audio download)
- OpenAI Whisper (local transcription)
- Pluggable LLM summarization (Claude API / OpenAI-compatible API for local models)

## Status

Early development — Phase 1 scaffold in progress.
