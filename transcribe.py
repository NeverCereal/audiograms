#!/usr/bin/env python3
"""
Transcribe audio with OpenAI Whisper and output caption files.

Supports SRT, VTT, and JSON (word-level) outputs.

Usage:
  python transcribe.py audio.mp3 --format srt vtt json
"""

import argparse
import json
import sys
from pathlib import Path

import whisper


def fmt_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def fmt_vtt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def to_srt(segments: list[dict]) -> str:
    lines = []
    idx = 1
    for seg in segments:
        start = fmt_srt_time(seg["start"])
        end = fmt_srt_time(seg["end"])
        lines.append(f"{idx}\n{start} --> {end}\n{seg['text'].strip()}\n")
        idx += 1
    return "\n".join(lines)


def to_vtt(segments: list[dict]) -> str:
    lines = ["WEBVTT\n"]
    for seg in segments:
        start = fmt_vtt_time(seg["start"])
        end = fmt_vtt_time(seg["end"])
        lines.append(f"{start} --> {end}\n{seg['text'].strip()}\n")
    return "\n".join(lines)


def to_json(segments: list[dict], words: list[dict]) -> str:
    return json.dumps({
        "segments": segments,
        "words": words,
    }, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Transcribe audio with Whisper and output captions")
    parser.add_argument("audio", help="Path to audio file")
    parser.add_argument("-f", "--format", nargs="+", default=["srt", "vtt"],
                        choices=["srt", "vtt", "json"],
                        help="Output formats (default: srt vtt)")
    parser.add_argument("-m", "--model", default="large-v3",
                        choices=["tiny", "base", "small", "medium", "large-v3"])
    parser.add_argument("-d", "--device", default="cuda")
    parser.add_argument("-l", "--language", default=None,
                        help="Language code (default: auto-detect)")
    args = parser.parse_args()

    audio_path = Path(args.audio)
    if not audio_path.exists():
        sys.exit(f"Audio file not found: {args.audio}")

    out_dir = Path(f"{audio_path.stem}-out")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_base = audio_path.stem

    print(f"Loading whisper-{args.model} ...")
    model = whisper.load_model(args.model, device=args.device)

    print(f"Transcribing {args.audio} ...")
    result = model.transcribe(
        str(audio_path),
        language=args.language,
        word_timestamps="json" in args.format,
    )

    segments = [{"start": s["start"], "end": s["end"], "text": s["text"].strip()}
                for s in result["segments"]]

    words = []
    if "json" in args.format:
        for seg in result.get("segments", []):
            for w in seg.get("words", []):
                words.append({
                    "text": w["text"].strip(),
                    "start": w["start"],
                    "end": w["end"],
                    "probability": round(w.get("probability", 0), 3),
                })

    for fmt in args.format:
        if fmt == "srt":
            out_path = out_dir / f"{out_base}.srt"
            out_path.write_text(to_srt(segments))
            print(f"  -> {out_path}")
        elif fmt == "vtt":
            out_path = out_dir / f"{out_base}.vtt"
            out_path.write_text(to_vtt(segments))
            print(f"  -> {out_path}")
        elif fmt == "json":
            out_path = out_dir / f"{out_base}.json"
            out_path.write_text(to_json(segments, words))
            print(f"  -> {out_path}")

    print(f"Done. {len(segments)} segments, {len(words)} words.")


if __name__ == "__main__":
    main()
