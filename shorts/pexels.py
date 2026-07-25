# -*- coding: utf-8 -*-
"""pexels.py — tải video stock từ Pexels cho B-roll, reframe sẵn 1080x1920. CẦN PEXELS_API_KEY."""
import json, os, subprocess, urllib.parse, urllib.request
from pathlib import Path

API = "https://api.pexels.com/videos/search"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def _get_json(url, key):
    req = urllib.request.Request(url, headers={"Authorization": key, "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _download(link, dest: Path):
    req = urllib.request.Request(link, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)


def fetch_broll(query: str, out_path: Path, dur_sec: float, w=1080, h=1920):
    """Tìm 1 video Pexels theo query -> tải -> reframe {w}x{h} cover, cắt dur_sec (không tiếng).
    Trả out_path hoặc None."""
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        print("  [pexels] thiếu PEXELS_API_KEY"); return None
    try:
        for params in ({"query": query, "per_page": 5, "orientation": "portrait"},
                       {"query": query, "per_page": 5}):
            data = _get_json(API + "?" + urllib.parse.urlencode(params), key)
            vids = data.get("videos", [])
            if vids:
                break
        if not vids:
            print(f"  [pexels] không thấy: {query}"); return None
        link = None
        for v in vids:
            files = v.get("video_files", [])
            pick = (next((f for f in sorted(files, key=lambda f: f.get("height") or 0)
                          if (f.get("height") or 0) >= 1080), None)
                    or (max(files, key=lambda f: f.get("height") or 0) if files else None))
            if pick and pick.get("link"):
                link = pick["link"]; break
        if not link:
            return None
        raw = out_path.with_suffix(".raw.mp4")
        _download(link, raw)
        subprocess.run(["ffmpeg", "-y", "-t", f"{dur_sec:.2f}", "-i", str(raw),
                        "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps=30",
                        "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", str(out_path)],
                       check=True, capture_output=True)
        try:
            raw.unlink()
        except OSError:
            pass
        return out_path
    except Exception as e:
        print(f"  [pexels] lỗi '{query}': {e}"); return None
