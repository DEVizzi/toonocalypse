"""Wide 16:9 film after a story's final part is published: each vertical part placed over its own blurred,
enlarged copy, identical encoding, title + moral cards, joined by stream copy, uploaded long-form to YouTube."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

from src.common.config import ROOT, settings
from src.common.state import load_state, save_state
from src.kaggle_jobs import cli_tools
from src.render.frames import FONT_SFX, font, wrap

ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", "30",
       "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2"]


def card(text: str, out: Path, seconds: float = 3.0) -> Path:
    img = Image.new("RGB", (1920, 1080), "#0E1020")
    d = ImageDraw.Draw(img)
    f = font(str(FONT_SFX), 110)
    rows = wrap(text, f, 1600)
    y = (1080 - 125 * len(rows)) // 2
    for r in rows:
        d.text(((1920 - f.getlength(r)) / 2, y), r, font=f, fill="#FFE14D", stroke_width=4, stroke_fill="black")
        y += 125
    png = out.with_suffix(".png")
    img.save(png)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-t", str(seconds), "-i", str(png), "-f", "lavfi", "-t", str(seconds),
                    "-i", "anullsrc=r=48000:cl=stereo", *ENC, "-shortest", str(out)], check=True)
    return out


def widen(src: Path, out: Path) -> Path:
    vf = ("[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,boxblur=24:2,eq=brightness=-0.08[bg];"
          "[0:v]scale=-2:1080[fg];[bg][fg]overlay=(W-w)/2:0[v]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-filter_complex", vf, "-map", "[v]", "-map", "0:a", *ENC, str(out)], check=True)
    return out


def main() -> int:
    pub = load_state("published.json", {"episodes": {}, "stories": {}})
    bible = load_state("story_bible.json")
    todo = [h for h in bible.get("history", []) if h.get("status") == "PUBLISHED" and not h.get("wide_id")]
    if not todo:
        print("No finished story waiting for a wide film.")
        return 0
    h = todo[0]
    story = bible.get("archive", {}).get(h["story_id"])
    if not story:
        print(f"ABORTED: archive missing for {h['story_id']}")
        return 0
    work = ROOT / "work" / "compile" / story["story_id"]
    work.mkdir(parents=True, exist_ok=True)
    from src.common.ids import make_episode_id

    total = len(story["parts"]) if isinstance(story["parts"], list) else int(story["parts"])
    names = [f"{make_episode_id(story['story_id'], i, total)}.mp4" for i in range(1, total + 1)]
    files = cli_tools.download_assets(story["story_id"], names, work)
    pieces = [card(story["title"], work / "title.mp4")]
    pieces += [widen(files[n], work / f"wide_{i}.mp4") for i, n in enumerate(names, 1)]
    pieces.append(card(f"Moral: {story['moral']}", work / "moral.mp4", 4))
    lst = work / "list.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in pieces))
    film = work / f"{story['story_id']}_film.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(film)], check=True, cwd=work)
    from src.publish import youtube

    tok = youtube.access_token()
    desc = f"{story['logline']}\n\nThe full {total}-part story.\n\nMoral: {story['moral']}"
    vid = youtube.find_existing(tok, f"{story['story_id']}-film") or youtube.upload(tok, film, f"{story['title']} | Full Story", desc, f"{story['story_id']}-film")
    h["wide_id"] = vid
    save_state("story_bible.json", bible)
    print(f"Wide film uploaded: {vid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
