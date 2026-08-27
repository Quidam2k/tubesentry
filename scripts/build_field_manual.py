"""Coverage / refresh helper for the Roads emergency-prep field manual.

The field manual (docs/roads-emergency-prep-field-manual.md) is a HAND-CURATED
distillation of the emergency-preparedness episodes on the "The Roads with Belle"
channel. Its per-episode checklists are extracted by hand (verbatim-faithful),
so this script does NOT rewrite the prose. Instead it keeps the manual *current*:

  1. Finds every prep-themed episode on the channel already in the DB.
  2. Reads which YouTube video IDs the manual already covers.
  3. Reports which prep episodes are NOT yet in the manual, and whether each
     already has a transcript.
  4. Prints the exact archive command to ingest+transcribe anything missing.

There is NO scheduled task (schtasks /create returns Access denied on this box
post-Q: migration). Stay-current workflow:

    # 1. Pull any new episodes from the channel into the DB + transcribe:
    .venv\\Scripts\\python.exe -m scripts.archive \\
        --channel-url "https://www.youtube.com/channel/UC_x7nc3Vi4BPgmNnMsz774A" \\
        --limit 5 --path captions-first

    # 2. See what prep episodes the manual is missing:
    .venv\\Scripts\\python.exe -m scripts.build_field_manual

    # 3. For each gap, extract a section (checklists first) and paste it into
    #    docs/roads-emergency-prep-field-manual.md.

Exit code is non-zero when uncovered prep episodes exist, so a Pantheon-side
reminder can surface "new prep episode to add" without a Windows task.
"""

import re
import sys
from pathlib import Path

from app.database import SessionLocal
from app.models import Channel, Video, Transcript

REPO = Path(__file__).resolve().parent.parent
MANUAL = REPO / "docs" / "roads-emergency-prep-field-manual.md"

CHANNEL_TITLE = "The Roads with Belle"

# Title keywords that mark an episode as part of the emergency-prep run.
# Deliberately broad; review the candidate list before adding to the manual.
PREP_KEYWORDS = [
    "emergency", "prepared", "preparedness", "survival kit", "survival",
    "disaster", "shelter", "water purification", "food storage", "fire and light",
    "understanding fire", "emergency bag", "ifak", "first aid", "little ones",
    "polar vortex", "black swan",
]


def _is_prep(title: str) -> bool:
    t = (title or "").lower()
    return any(k in t for k in PREP_KEYWORDS)


def _covered_ids() -> set[str]:
    if not MANUAL.exists():
        return set()
    text = MANUAL.read_text(encoding="utf-8")
    return set(re.findall(r"watch\?v=([\w-]{11})", text))


def main() -> int:
    db = SessionLocal()
    try:
        channel = db.query(Channel).filter(Channel.channel_name == CHANNEL_TITLE).first()
        if not channel:
            print(f"Channel '{CHANNEL_TITLE}' not found in DB.")
            return 2

        prep = [
            v for v in db.query(Video).filter(Video.channel_id == channel.id).all()
            if _is_prep(v.title)
        ]
        prep.sort(key=lambda v: (v.upload_date or ""), reverse=True)

        covered = _covered_ids()
        missing = []

        print(f"Emergency-prep episodes on '{CHANNEL_TITLE}': {len(prep)} candidate(s)\n")
        print(f"{'in manual':10} {'transcript':11} date        title")
        print("-" * 78)
        for v in prep:
            has_t = db.query(Transcript).filter(Transcript.video_id == v.id).first() is not None
            in_manual = v.youtube_video_id in covered
            date = str(v.upload_date)[:10] if v.upload_date else "----------"
            print(f"{'YES' if in_manual else 'no':10} "
                  f"{'yes' if has_t else 'MISSING':11} {date}  {(v.title or '')[:48]}")
            if not in_manual:
                missing.append(v)

        if missing:
            print(f"\n{len(missing)} prep episode(s) NOT yet in the manual:")
            for v in missing:
                need = "" if db.query(Transcript).filter(Transcript.video_id == v.id).first() else \
                       "  (needs transcript — run scripts.archive first)"
                print(f"  - {str(v.upload_date)[:10]}  {v.title}  [{v.youtube_video_id}]{need}")
            print("\nTo ingest+transcribe new episodes:")
            print('  .venv\\Scripts\\python.exe -m scripts.archive '
                  f'--channel-url "{channel.channel_url}" --limit 5 --path captions-first')
            return 1

        print("\nManual covers every prep episode currently in the DB.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
