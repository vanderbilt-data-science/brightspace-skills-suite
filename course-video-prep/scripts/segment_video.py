#!/usr/bin/env python3
"""Cut a lecture recording into segments, each prefixed with a branded intro card.

Usage: python3 segment_video.py plan.json

Reads a plan (see references/package-format.md), then for each segment:
  1. renders an intro card PNG (Pillow, auto-installed)
  2. encodes the card as a short silent video matched to the source's
     resolution/fps
  3. cuts the content span (frame-accurate re-encode, EBU R128 loudness
     normalization)
  4. concatenates card + content
  5. slices the source VTT to the span, shifting timestamps past the intro

Outputs videos/, captions/, intro-cards/ inside plan["output_dir"] and prints
a per-segment report. Exits nonzero if any segment fails.
"""

import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------- utilities


def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        die(f"command failed: {' '.join(str(c) for c in cmd)}\n{r.stderr[-3000:]}")
    return r


def ensure_pillow():
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("Installing Pillow ...")
        # PEP 668 (externally-managed Homebrew Python) blocks plain pip
        for extra in ([], ["--user"], ["--user", "--break-system-packages"],
                      ["--break-system-packages"]):
            r = subprocess.run([sys.executable, "-m", "pip", "install",
                                "--quiet", *extra, "Pillow"],
                               capture_output=True)
            if r.returncode == 0:
                return
        die("could not install Pillow (pip blocked by PEP 668). Install "
            "manually: python3 -m pip install --user --break-system-packages Pillow")


def parse_ts(ts):
    """'HH:MM:SS(.mmm)' | 'MM:SS(.mmm)' -> float seconds."""
    parts = str(ts).strip().split(":")
    if not 2 <= len(parts) <= 3:
        die(f"bad timestamp: {ts}")
    parts = [float(p) for p in parts]
    if len(parts) == 2:
        parts = [0.0] + parts
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def fmt_vtt(seconds):
    if seconds < 0:
        seconds = 0.0
    h = int(seconds // 3600)
    m = int(seconds % 3600 // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def probe(video):
    r = run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams",
             "-show_format", str(video)])
    info = json.loads(r.stdout)
    vstream = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    if not vstream:
        die(f"no video stream in {video}")
    num, _, den = vstream.get("r_frame_rate", "30/1").partition("/")
    fps = float(num) / float(den or 1)
    if fps <= 1 or fps > 120 or math.isnan(fps):
        fps = 30.0
    return {
        "width": int(vstream["width"]),
        "height": int(vstream["height"]),
        "fps": round(fps, 3),
        "duration": float(info["format"].get("duration", 0)),
    }


# ---------------------------------------------------------------- intro card

BG = (16, 20, 25)          # near-black
GOLD = (207, 174, 112)     # accent
WHITE = (245, 245, 245)
GRAY = (170, 175, 182)

FONT_CANDIDATES = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def load_font(size, bold=False):
    from PIL import ImageFont
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            try:
                # index 1 in Helvetica.ttc is Bold
                return ImageFont.truetype(path, size, index=1 if bold and path.endswith(".ttc") else 0)
            except OSError:
                continue
    return ImageFont.load_default()


def wrap_text(draw, text, font, max_width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def render_card(seg, plan, size, out_png):
    from PIL import Image, ImageDraw
    W, H = size
    scale = H / 1080.0
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    margin = int(120 * scale)
    f_course = load_font(int(34 * scale))
    f_title = load_font(int(84 * scale), bold=True)
    f_sub = load_font(int(44 * scale))
    f_bullet = load_font(int(40 * scale))

    y = int(140 * scale)
    course_line = plan.get("course_line", "")
    if course_line:
        d.text((margin, y), course_line.upper(), font=f_course, fill=GOLD)
        y += int(60 * scale)
    module_line = plan.get("module_line", "")
    if module_line:
        d.text((margin, y), module_line, font=f_course, fill=GRAY)
        y += int(70 * scale)

    # gold rule
    d.rectangle([margin, y, margin + int(160 * scale), y + int(8 * scale)], fill=GOLD)
    y += int(70 * scale)

    for line in wrap_text(d, seg["title"], f_title, W - 2 * margin):
        d.text((margin, y), line, font=f_title, fill=WHITE)
        y += int(100 * scale)

    if seg.get("subtitle"):
        y += int(10 * scale)
        d.text((margin, y), seg["subtitle"], font=f_sub, fill=GOLD)
        y += int(90 * scale)

    bullets = seg.get("bullets", [])[:4]
    if bullets:
        y += int(20 * scale)
        for b in bullets:
            d.ellipse([margin, y + int(16 * scale), margin + int(14 * scale),
                       y + int(30 * scale)], fill=GOLD)
            bx = margin + int(40 * scale)
            for line in wrap_text(d, b, f_bullet, W - bx - margin):
                d.text((bx, y), line, font=f_bullet, fill=GRAY)
                y += int(56 * scale)
            y += int(14 * scale)

    img.save(out_png)


# ---------------------------------------------------------------- vtt slicing

CUE_RE = re.compile(
    r"(\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{3}\s*-->\s*(\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{3}")


def parse_vtt(path):
    cues, cur_times, cur_text = [], None, []
    for raw in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip("﻿").rstrip()
        if CUE_RE.match(line):
            if cur_times and cur_text:
                cues.append((*cur_times, "\n".join(cur_text)))
            a, b = [p.strip().replace(",", ".") for p in line.split("-->")[:2]]
            b = b.split()[0]  # drop cue settings
            cur_times, cur_text = (parse_ts(a), parse_ts(b)), []
        elif line == "":
            if cur_times and cur_text:
                cues.append((*cur_times, "\n".join(cur_text)))
            cur_times, cur_text = None, []
        elif cur_times is not None:
            cur_text.append(line)
        # else: header/NOTE/cue-number lines outside a cue -> ignored
    if cur_times and cur_text:
        cues.append((*cur_times, "\n".join(cur_text)))
    return cues


def slice_vtt(cues, start, end, offset, out_path):
    """Cues overlapping [start,end], shifted so segment start lands at +offset."""
    out = ["WEBVTT", ""]
    n = 0
    for a, b, text in cues:
        if b <= start or a >= end:
            continue
        n += 1
        na = max(a, start) - start + offset
        nb = min(b, end) - start + offset
        out += [str(n), f"{fmt_vtt(na)} --> {fmt_vtt(nb)}", text, ""]
    Path(out_path).write_text("\n".join(out), encoding="utf-8")
    return n


# ---------------------------------------------------------------- main build


def build_segment(seg, plan, src, meta, dirs, tmp):
    idx, slug = seg["index"], seg["slug"]
    name = f"{idx:02d}-{slug}"
    start, end = parse_ts(seg["start"]), parse_ts(seg["end"])
    if end <= start:
        die(f"segment {name}: end <= start")
    if end > meta["duration"] + 1:
        die(f"segment {name}: end {seg['end']} beyond recording "
            f"({meta['duration']:.0f}s)")
    dur = end - start
    intro_s = float(plan.get("intro_seconds", 6))
    W, H, fps = meta["width"], meta["height"], meta["fps"]

    card_png = dirs["cards"] / f"{name}.png"
    render_card(seg, plan, (W, H), card_png)

    enc = ["-c:v", "libx264", "-crf", "20", "-preset", "fast",
           "-pix_fmt", "yuv420p", "-r", f"{fps}",
           "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2"]

    intro_mp4 = tmp / f"{name}-intro.mp4"
    fade_out = max(intro_s - 0.5, 0)
    run(["ffmpeg", "-y", "-loop", "1", "-t", f"{intro_s}", "-i", str(card_png),
         "-f", "lavfi", "-t", f"{intro_s}",
         "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
         "-vf", f"scale={W}:{H},fade=t=in:st=0:d=0.4,fade=t=out:st={fade_out}:d=0.5",
         *enc, "-shortest", str(intro_mp4)])

    body_mp4 = tmp / f"{name}-body.mp4"
    run(["ffmpeg", "-y", "-ss", f"{start}", "-i", str(src), "-t", f"{dur}",
         "-vf", f"scale={W}:{H}",
         "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
         *enc, str(body_mp4)])

    final = dirs["videos"] / f"{name}.mp4"
    concat_list = tmp / f"{name}-list.txt"
    concat_list.write_text(f"file '{intro_mp4}'\nfile '{body_mp4}'\n")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
         "-c", "copy", "-movflags", "+faststart", str(final)])

    got = probe(final)["duration"]
    expect = intro_s + dur
    if abs(got - expect) > 2.0:
        # stream-copy concat disagreed; re-encode the join
        run(["ffmpeg", "-y", "-i", str(intro_mp4), "-i", str(body_mp4),
             "-filter_complex",
             "[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[v][a]",
             "-map", "[v]", "-map", "[a]", *enc,
             "-movflags", "+faststart", str(final)])
        got = probe(final)["duration"]
        if abs(got - expect) > 2.0:
            die(f"segment {name}: duration {got:.1f}s, expected {expect:.1f}s")

    n_cues = 0
    if plan.get("source_vtt"):
        n_cues = slice_vtt(parse_vtt(plan["source_vtt"]), start, end, intro_s,
                           dirs["captions"] / f"{name}.vtt")

    return {"segment": name, "title": seg["title"],
            "duration_seconds": round(got, 1),
            "content_seconds": round(dur, 1), "caption_cues": n_cues,
            "video": f"videos/{name}.mp4",
            "captions": f"captions/{name}.vtt" if n_cues else None,
            "intro_card": f"intro-cards/{name}.png"}


def main():
    if len(sys.argv) != 2:
        die("usage: segment_video.py plan.json")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        die("ffmpeg/ffprobe not found on PATH")
    ensure_pillow()

    plan = json.loads(Path(sys.argv[1]).read_text())
    src = Path(plan["source_video"])
    if not src.exists():
        die(f"source video not found: {src}")
    if plan.get("source_vtt") and not Path(plan["source_vtt"]).exists():
        die(f"source vtt not found: {plan['source_vtt']}")

    out = Path(plan["output_dir"])
    dirs = {"videos": out / "videos", "captions": out / "captions",
            "cards": out / "intro-cards"}
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)

    meta = probe(src)
    print(f"Source: {src.name}  {meta['width']}x{meta['height']} "
          f"@{meta['fps']}fps  {meta['duration']:.0f}s")

    results = []
    with tempfile.TemporaryDirectory() as tmp:
        for seg in plan["segments"]:
            print(f"-- building {seg['index']:02d}-{seg['slug']} "
                  f"({seg['start']} -> {seg['end']}) ...")
            results.append(build_segment(seg, plan, src, meta, dirs, Path(tmp)))

    report = out / "segments-report.json"
    report.write_text(json.dumps(results, indent=2))
    print(f"\n{'#':>2}  {'length':>8}  {'cues':>5}  title")
    for r in results:
        mins = f"{int(r['duration_seconds'] // 60)}:{int(r['duration_seconds'] % 60):02d}"
        print(f"{r['segment'][:2]:>2}  {mins:>8}  {r['caption_cues']:>5}  {r['title']}")
    print(f"\nOK: {len(results)} segments -> {out}  (report: {report.name})")


if __name__ == "__main__":
    main()
