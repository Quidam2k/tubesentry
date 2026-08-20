# A/B Quality Assessment — captions vs Whisper

- Whisper model: **medium**
- GPU: CUDA NOT available — Whisper ran on CPU
- Sample size: 6 videos

## Per-video

| video | source | agree | cap chars | whisper chars | cap s | whisper s | artifacts |
|---|---|---|---|---|---|---|---|
| 5cDRZS8EPPY | caption_auto | 0.93 | 3220 | 3213 | 12.6 | 151.4 | 0 |
| GDsKil1WIJw | caption_auto | 0.96 | 3067 | 3065 | 2.4 | 150.3 | 0 |
| _4dsHBzLYU8 | caption_auto | 0.94 | 2915 | 2902 | 2.6 | 150.0 | 0 |
| XO6sdC3AlQ8 | caption_auto | 0.75 | 10264 | 10333 | 1.8 | 520.1 | 2 |
| WD8mWq0Hdcw | caption_auto | 0.68 | 6388 | 6436 | 2.0 | 329.1 | 2 |
| mfDasT0zSpg | caption_auto | 0.71 | 2397 | 2420 | 2.3 | 127.5 | 2 |

## Aggregate

- Caption availability: 6/6
- Mean agreement (where captions exist): 0.83

## Notes for reviewer

- Agreement is word-order similarity, NOT accuracy — low agreement means the two transcripts diverge, and the side-by-side files show which is right. Read a few directly.
- Auto-captions typically lack capitalization/punctuation and drop sound cues; Whisper adds punctuation but can mis-hear names/jargon.
- Check whether older videos show lower caption quality than recent ones — that is the specific risk this sample tests.
