# AGENTS.md — shiny-meme (Audiogram Generator)

## Project Purpose
Takes audio + SRT captions → produces vertical 9:16 videos (Shorts/Reels/TikTok) with burned-in captions and optional waveform visualization.

## Key Files
- `audiogram.py` — Main video generator: random colors, subtitles, ffmpeg pipeline
- `transcribe.py` — Whisper transcription: audio → SRT/VTT/JSON
- `run.sh` — Entry-point: manages venv, GPU detection, dispatches to Python scripts

## Output Convention
All outputs go to `<audio_stem>-out/` in the working directory, regardless of where the source audio lives. transcribe.py outputs `<stem>-out/<stem>.srt` etc., audiogram.py outputs `<stem>-out/<stem>.mp4`.

## Code Style Preferences
- **No unnecessary abstractions** — flat is better than nested
- **No repetitive blocks** — if you see the same pattern 3x, factor it out
- **No dead code** — remove unused functions, don't leave placeholders
- **Opinionated defaults** — remove flags that exist just to override defaults. If there's one right way, make it the only way.
- **Type hints** on function signatures
- **No docstrings** on obvious functions — the code should be readable without them
- **Minimal dependencies** — prefer subprocess calls to CLI tools over Python libraries
- **Never `:set paste` in vim for Python** — use `:r !cat` or paste directly into the open buffer like a normal person

## Key Design Decisions
- No `-o`/`--output` flag — output dir is always `<stem>-out/`
- No `make` command — workflow is `transcribe` → review/edit SRT → `audiogram`
- Waveform enabled by default (`--no-waveform` to disable)
- Random background color when `--bg` not specified
- `--avoid pinks,purples` etc. to blacklist hue ranges from random generation
- Subtitle text color (white or black) chosen for contrast against background
- Waveform color is random but guaranteed visible vs background (+ `--avoid`)
- SRT is converted to a temp ASS file at runtime (`srt_to_ass()`) then passed to ffmpeg — `force_style` is unreliable (ffmpeg 6.1.1 creates 2 filter instances + garbled output). ASS files give single rendering at correct position.
- Always passes `original_size=WxH` to subtitles filter — required for correct positioning

## Dependencies
- ffmpeg (subprocess)
- openai-whisper (transcription)
- PyTorch (whisper backend, auto-detected GPU)

## Common Gotchas
- If subtitles don't appear or appear doubled: `original_size` must be set on `subtitles` filter
- If ffmpeg command is wrong: check the filter_complex string construction, escaping is finicky
- Subtitle SRT is always user-edited between transcribe and audiogram steps
- ASS temp file uses centisecond format `h:mm:ss.cc`, NOT millisecond `h:mm:ss.ccc` — libass silently drops events with wrong timestamps
- Temp ASS file is cleaned up by `os.unlink()` after ffmpeg completes; if the script fails before that line, temp files accumulate in /tmp
