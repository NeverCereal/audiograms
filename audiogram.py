#!/usr/bin/env python3
"""
Generate a vertical audiogram video with burned-in captions.

Takes audio + SRT and produces a 9:16 video ready for Shorts/Reels/TikTok.
"""

import argparse
import colorsys
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


AVOID_RANGES: dict[str, list[tuple[int, int]]] = {
    "pinks": [(300, 340)],
    "purples": [(270, 300)],
    "reds": [(340, 360), (0, 20)],
    "oranges": [(20, 50)],
    "yellows": [(50, 80)],
    "greens": [(80, 170)],
    "cyans": [(170, 220)],
    "blues": [(220, 270)],
}

SRT_TIME_RE = re.compile(r"(\d{2}):(\d{2}):(\d{2})[,.](\d+)")


def random_hex_color(avoid: list[str] | None = None) -> str:
    ranges: list[tuple[int, int]] = []
    for name in (avoid or []):
        if name.strip() in AVOID_RANGES:
            ranges.extend(AVOID_RANGES[name.strip()])
    for _ in range(200):
        r, g, b = random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)
        h, s, _ = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if ranges and s > 0.05:
            h_deg = h * 360
            if any(start <= h_deg <= end for start, end in ranges):
                continue
        return f"{r:02x}{g:02x}{b:02x}"
    return f"{random.randint(0, 0xFFFFFF):06x}"


def relative_luminance(hex_color: str) -> float:
    r, g, b = (int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4))

    def linearize(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b)


def is_dark(hex_color: str) -> bool:
    return relative_luminance(hex_color) < 0.5


def hex_to_ass_color(hex_rgb: str) -> str:
    rr, gg, bb = hex_rgb[0:2], hex_rgb[2:4], hex_rgb[4:6]
    return f"&H00{bb}{gg}{rr}"


def random_visible_color(bg_hex: str, avoid: list[str] | None = None) -> str:
    bg_lum = relative_luminance(bg_hex)
    ranges: list[tuple[int, int]] = []
    for name in (avoid or []):
        if name.strip() in AVOID_RANGES:
            ranges.extend(AVOID_RANGES[name.strip()])
    for _ in range(200):
        r, g, b = random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)
        h, s, _ = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if ranges and s > 0.05:
            h_deg = h * 360
            if any(start <= h_deg <= end for start, end in ranges):
                continue
        lum = relative_luminance(f"{r:02x}{g:02x}{b:02x}")
        if abs(lum - bg_lum) > 0.4:
            return f"{r:02x}{g:02x}{b:02x}"
    return "ffffff" if bg_lum < 0.5 else "000000"


def resolve_font(font_name: str) -> str:
    try:
        result = subprocess.run(
            ["fc-match", "-f", "%{family}", font_name],
            capture_output=True, text=True, timeout=5)
        resolved = result.stdout.strip().split(",")[0]
        if resolved.lower() != font_name.lower():
            print(f"Warning: Font '{font_name}' not found, using '{resolved}' instead")
        return resolved
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return font_name


def parse_srt(path: str) -> list[tuple[str, str, str]]:
    with open(path, encoding="utf-8") as f:
        content = f.read()
    blocks = re.split(r"\n\n+", content.strip())
    events: list[tuple[str, str, str]] = []
    for block in blocks:
        lines = block.strip().split("\n")
        time_line = None
        text_lines: list[str] = []
        for i, line in enumerate(lines):
            if "-->" in line:
                time_line = line
                text_lines = lines[i+1:]
                break
        if not time_line:
            continue

        def to_ass(ts: str) -> str:
            def repl(m):
                cs = m.group(4)[:2].zfill(2)
                return f"{m.group(1)}:{m.group(2)}:{m.group(3)}.{cs}"
            return SRT_TIME_RE.sub(repl, ts)

        parts = time_line.split("-->")
        start = to_ass(parts[0].strip())
        end = to_ass(parts[1].strip())
        text = "\\N".join(text_lines).replace("{", "\\{").replace("}", "\\}")
        events.append((start, end, text))
    return events


def srt_to_ass(srt_path: str, width: int, height: int,
               font: str, font_size: int,
               primary: str, outline: str,
               margin_v: int = 80) -> str:
    events = parse_srt(srt_path)
    black = "&H00000000"
    style = (f"Default,{font},{font_size},{primary},{black},{outline},{black},"
             f"0,0,0,0,100,100,0,0,1,2,1,2,10,10,{margin_v},1")
    ass_lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: {style}",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for start, end, text in events:
        ass_lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")
    ass_lines.append("")

    fd, ass_path = tempfile.mkstemp(suffix=".ass")
    with os.fdopen(fd, "w") as f:
        f.write("\n".join(ass_lines))
    return ass_path


def build_ffmpeg_cmd(args, sub_filter: str, out_path: str,
                     bg: str, waveform_color: str | None) -> list[str]:
    w, h = args.width, args.height

    if not args.no_waveform:
        inputs = ["-f", "lavfi", "-i", f"color=c={bg}:s={w}x{h}:r={args.fps}", "-i", args.audio]
        vfilter = (
            f"[1:a]showwaves=s={w}x{h}:mode=cline:rate={args.fps}"
            f":colors={waveform_color}"
            f",colorkey=black:0.05:0.0[wave];"
            f"[0:v][wave]overlay=format=auto:shortest=1[vid]"
        )
        vid = "[vid]"
        amap = "1:a"
        shortest = False
    elif args.bg_image:
        inputs = ["-loop", "1", "-i", args.bg_image, "-i", args.audio]
        vfilter = (
            f"[0:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color={bg}[bg]"
        )
        vid = "[bg]"
        amap = "1:a"
        shortest = True
    else:
        inputs = ["-f", "lavfi", "-i", f"color=c={bg}:s={w}x{h}:r={args.fps}", "-i", args.audio]
        vfilter = ""
        vid = "[0:v]"
        amap = "1:a"
        shortest = True

    sub_part = sub_filter if sub_filter else "null"
    filter_graph = f"{vid}{sub_part},format=yuv420p[out]"
    if vfilter:
        filter_graph = f"{vfilter};{filter_graph}"

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_graph,
        "-map", "[out]",
        "-map", amap,
        "-sn",
        "-c:v", "libx264",
        "-preset", args.preset,
        "-crf", str(args.crf),
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
    ]
    if shortest:
        cmd.append("-shortest")
    cmd.append(out_path)
    return cmd


def main():
    parser = argparse.ArgumentParser(
        description="Generate a vertical audiogram with burned-in captions")
    parser.add_argument("audio", help="Path to audio file")
    parser.add_argument("subtitles", help="Path to SRT file")
    parser.add_argument("--bg", default=None,
                        help="Background color (hex, default: random)")
    parser.add_argument("--avoid", default="",
                        help="Avoid color families (comma-separated: pinks,purples,reds,...)")
    parser.add_argument("--bg-image", help="Background image (overrides --bg)")
    parser.add_argument("--font", default="Arial",
                        help="Caption font (default: Arial)")
    parser.add_argument("--font-size", type=int, default=42,
                        help="Caption font size (default: 42)")
    parser.add_argument("--width", type=int, default=1080,
                        help="Video width (default: 1080)")
    parser.add_argument("--height", type=int, default=1920,
                        help="Video height (default: 1920)")
    parser.add_argument("--fps", type=int, default=30,
                        help="Frame rate (default: 30)")
    parser.add_argument("--crf", type=int, default=18,
                        help="Video quality: lower=better, 18-28 typical (default: 18)")
    parser.add_argument("--preset", default="fast",
                        choices=["ultrafast", "superfast", "veryfast", "fast", "medium", "slow"],
                        help="Encoding speed preset (default: fast)")
    parser.add_argument("--no-waveform", action="store_true",
                        help="Disable audio waveform visualization")
    args = parser.parse_args()

    for path_attr in ("audio", "subtitles"):
        p = getattr(args, path_attr)
        if not Path(p).exists():
            sys.exit(f"{path_attr.capitalize()} file not found: {p}")
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found. Install it: sudo apt install ffmpeg")

    avoid = [a.strip() for a in args.avoid.split(",") if a.strip()] if args.avoid else []
    if args.bg is None:
        args.bg = random_hex_color(avoid)

    if args.bg_image:
        sub_ass_color = "&H00FFFFFF"
        outline_ass_color = "&H00000000"
    else:
        sub_hex, outline_hex = ("FFFFFF", "000000") if is_dark(args.bg) else ("000000", "FFFFFF")
        sub_ass_color = hex_to_ass_color(sub_hex)
        outline_ass_color = hex_to_ass_color(outline_hex)

    waveform_color = random_visible_color(args.bg, avoid) if not args.no_waveform else None

    stem = Path(args.audio).stem
    out_dir = Path(f"{stem}-out")
    out_dir.mkdir(parents=True, exist_ok=True)
    subs_path = str(out_dir / f"{stem}-subs.mp4")
    no_subs_path = str(out_dir / f"{stem}.mp4")

    font = resolve_font(args.font)
    ass_path = srt_to_ass(
        args.subtitles, args.width, args.height,
        font, args.font_size, sub_ass_color, outline_ass_color)
    try:
        sub_filter = f"subtitles='{ass_path}':original_size={args.width}x{args.height}"
        cmd = build_ffmpeg_cmd(args, sub_filter, subs_path, args.bg, waveform_color)

        print(f"Generating audiogram (with subtitles): {subs_path}")
        print(f"  Audio: {args.audio}")
        print(f"  Captions: {args.subtitles}")
        print(f"  Size: {args.width}x{args.height} @ {args.fps}fps")
        print(f"  Quality: CRF {args.crf} / preset {args.preset}")

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.stderr:
            print(f"ffmpeg messages:\n{result.stderr}")
        if result.returncode != 0:
            sys.exit(f"ffmpeg failed with code {result.returncode}")

        print(f"Done: {subs_path}")

        cmd_no_subs = build_ffmpeg_cmd(args, "", no_subs_path, args.bg, waveform_color)
        print(f"\nGenerating audiogram (no subtitles): {no_subs_path}")
        result_no_subs = subprocess.run(cmd_no_subs, capture_output=True, text=True)
        if result_no_subs.stderr:
            print(f"ffmpeg messages:\n{result_no_subs.stderr}")
        if result_no_subs.returncode != 0:
            sys.exit(f"ffmpeg (no subs) failed with code {result_no_subs.returncode}")
        print(f"Done: {no_subs_path}")
    finally:
        os.unlink(ass_path)


if __name__ == "__main__":
    main()
