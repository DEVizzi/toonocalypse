"""Side-by-side contact sheet for consistency reviews."""
from __future__ import annotations

import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from src.common.config import ROOT

TW, TH, PAD, CAP = 384, 672, 24, 110


def _font(size: int):
    try:
        return ImageFont.truetype(str(ROOT / "assets" / "fonts" / "ComicNeue-Bold.ttf"), size)
    except OSError:
        return ImageFont.load_default()


def contact_sheet(results: dict, portraits: dict[str, Path], kout: Path, dest: Path) -> Path:
    tiles = [(f"PORTRAIT {n}", p, results["portraits"][n]["results"][results["portraits"][n]["best"]]["avg"])
             for n, p in portraits.items()]
    for pid, v in results["panels"].items():
        if "best" in v:
            b = v["best"]
            tiles.append((f"{pid}  avg {b['avg']}  consistency {b['scores'].get('character_consistency')}",
                          kout / b["file"], None))
    cols = 4
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (PAD + cols * (TW + PAD), PAD + rows * (TH + CAP + PAD)), "white")
    d = ImageDraw.Draw(sheet)
    f = _font(22)
    for i, (label, path, avg) in enumerate(tiles):
        x, y = PAD + (i % cols) * (TW + PAD), PAD + (i // cols) * (TH + CAP + PAD)
        sheet.paste(Image.open(path).convert("RGB").resize((TW, TH)), (x, y))
        text = label + (f"  (QA avg {avg})" if avg is not None else "")
        d.multiline_text((x, y + TH + 6), "\n".join(textwrap.wrap(text, 32)), fill="black", font=f)
    sheet.save(dest, quality=90)
    return dest
