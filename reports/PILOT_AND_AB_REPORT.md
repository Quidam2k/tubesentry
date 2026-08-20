# TubeSentry — Channel Archive Pilot + A/B Quality Report

**Channel:** Belle of the Ranch (youtube.com/c/BeauoftheFifthColumn, ~6,800 videos)
**Date:** 2026-08-20
**Assignments:** #3073 + #3074 (folded). Transcripts-only. Pilot + A/B before any full run.
**Bottom line:** Captions-first is the right default. Recent auto-captions are near-parity
with Whisper; OLD auto-captions are materially worse and should be upgraded with Whisper.
Recommend an **age-based hybrid**, enabled by the new transcript-provenance columns.

---

## 1. Pilot (caption path, 20 newest videos)

| Metric | Value |
|---|---|
| Caption hit rate | **19 / 20 (95%)** — all `caption_auto` |
| Wall time | 1:27 total (~4.4 s/video, incl. a few slow fetches) |
| Storage | 66.4 KB for 19 transcripts (avg 3,577 chars) |
| Extrapolated storage, full 6,800 | **~24 MB of text** (negligible) |
| Miss | 1 video (`iLHs_p9O6fE`) — just-posted, captions not generated yet |

**Read:** The caption path is fast and tiny. A full caption-only pass over 6,800 videos is
~overnight-comfortable (rough est. 4–8 hrs, network-bound). The lone miss is a fresh upload
whose captions hadn't been generated; under `captions-first` it falls through to Whisper.

---

## 2. A/B quality: captions vs Whisper (medium)

Sample = **3 recent + 3 old** (the #3074 rigor: auto-caption quality degrades with age).
Whisper model = **medium**, run on **CPU** (see §3). Full side-by-side transcripts in
`reports/ab/<video_id>.md`.

| video | era | agreement | artifacts | verdict |
|---|---|---|---|---|
| 5cDRZS8EPPY | recent (2026) | 0.93 | 0 | captions ≈ Whisper |
| GDsKil1WIJw | recent (2026) | 0.96 | 0 | captions ≈ Whisper |
| _4dsHBzLYU8 | recent (2026) | 0.94 | 0 | captions ≈ Whisper |
| XO6sdC3AlQ8 | old (2018) | 0.75 | 2 | Whisper better |
| WD8mWq0Hdcw | old (2018) | 0.68 | 2 | Whisper better |
| mfDasT0zSpg | old (2018) | 0.71 | 2 | Whisper better |

*(Agreement = word-order similarity, not accuracy. It flags divergence; the direction of
"who's right" comes from reading the pairs, done below.)*

### Recent videos — captions are fine
Modern YouTube auto-captions are now **punctuated and capitalized**. Example
(`GDsKil1WIJw`, 2026): captions read "Well, how do there internet people? It's Bell again.
So, today we're going to talk about Iran planning expansion to Europe…" — essentially the
same prose as Whisper. Remaining diffs are single proper nouns that BOTH sometimes miss
(captions "Trump and Hagel staff" vs Whisper's correct "Hegseth"; Whisper "gullible children"
vs captions' "global children"). Net: near-parity, both fully readable.

### Old videos — Whisper wins clearly
2018 auto-captions are **un-punctuated run-ons with real transcription errors**. Example
(`mfDasT0zSpg`, 2018-09):
- Captions: "…the slave labor **and it was back at Stan** picking a cotton…"
- Whisper:  "…The slave labor **in Uzbekistan** picking a cotton…" ✅
- Captions are one 2,400-char wall of lowercase text with almost no sentence breaks;
  Whisper produces punctuated, paragraphed, readable prose.

This is exactly the age-degradation #3074 anticipated: older videos were captioned by an
older, weaker ASR model. For a parental-awareness tool where a human skims transcripts,
the old-caption readability gap matters.

### Aggregate
- Caption availability in sample: 6/6.
- Mean agreement: recent 0.94 vs old 0.71 — a clean split by age.

---

## 3. Infrastructure finding: torch is CPU-only

`torch 2.13.0+cpu`, `CUDA=False`. Two consequences:
- **No GPU contention** with the TTS engine as things stand — Whisper won't touch the GPU.
- **Whisper is CPU-slow:** medium took ~150 s for a 4-min video and ~520 s (8.7 min) for the
  longest sample. Caption fetch, by contrast, is ~2 s.

All-Whisper over 6,800 videos on CPU is impractical (many days–weeks). This is the crux of
the path decision and is **Todd's call**: installing CUDA-enabled torch would make a Whisper
pass feasible but would share the GPU with the TTS engine.

---

## 4. Recommendation — age-based hybrid

1. **Default: `captions-first` for the whole archive, newest-first.** Fast, ~24 MB, and for
   recent content (where newest-first starts and topicality is highest) it's near-parity with
   Whisper. One overnight gets the entire channel captured.
2. **Targeted Whisper upgrade of the weak subset.** The new `Transcript.source` / `is_auto`
   columns + `Video.upload_date` let us later run:
   *"re-transcribe with Whisper every `caption_auto` transcript from videos older than
   ~2021."* Size and schedule this per Todd's GPU decision (CUDA → feasible; CPU-only →
   long background grind, but zero-urgency).
3. **Caption misses → Whisper** automatically (already how `captions-first` behaves).

This gives **full coverage quickly**, then **upgrades exactly the transcripts the A/B showed
are weak**, with no wasted Whisper time on recent videos that don't need it.

### Open decisions for Todd
- Install CUDA torch for a feasible Whisper pass on old videos? (GPU shared with TTS.)
- Confirm the "old" cutoff year for the Whisper-upgrade pass (proposed ~2021).
- "The Roads with Belle" joins at full-run time (already confirmed pilot = Belle only).

### How to run (once green-lit)
```
# Full caption-first archive, newest-first (default order/path):
python -m scripts.archive --channel-url "https://youtube.com/c/BeauoftheFifthColumn"

# Later: Whisper-upgrade pass for old auto-caption transcripts (subset selection TBD)
python -m scripts.archive --channel-url URL --path whisper --whisper-model medium --order oldest
```

**Status: STOPPING here for review. The full 6,800-video run has NOT been launched.**
