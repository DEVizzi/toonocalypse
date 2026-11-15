"""2x3 comic page panel slicer with white-gutter detection (§5)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


def _find_splits(profile: np.ndarray, expected_parts: int, min_val: float = 242.0) -> list[tuple[int, int]]:
    length = len(profile)
    # Identify contiguous white bands
    white = profile >= min_val
    bands: list[tuple[int, int]] = []
    start: int | None = None
    for i, is_w in enumerate(white):
        if is_w and start is None:
            start = i
        elif not is_w and start is not None:
            if i - start >= 6:
                bands.append((start, i))
            start = None
    if start is not None and length - start >= 6:
        bands.append((start, length))

    # Filter out outer margins to find internal gutters
    internal = [b for b in bands if b[0] > int(length * 0.08) and b[1] < int(length * 0.92)]
    if len(internal) == expected_parts - 1:
        left_edge = bands[0][1] if bands and bands[0][0] < int(length * 0.08) else 0
        right_edge = bands[-1][0] if bands and bands[-1][1] > int(length * 0.92) else length
        cuts = [left_edge]
        for g0, g1 in internal:
            cuts.extend([g0, g1])
        cuts.append(right_edge)
        return [(cuts[2 * k], cuts[2 * k + 1]) for k in range(expected_parts)]

    # Fallback: uniform 24px-gutter grid
    gutter = max(8, int(length * 0.012))
    cell = (length - gutter * (expected_parts + 1)) // expected_parts
    return [
        (gutter + k * (cell + gutter), gutter + k * (cell + gutter) + cell)
        for k in range(expected_parts)
    ]


def detect_gutters(img: Image.Image) -> list[tuple[int, int, int, int]]:
    """Return 6 (x0, y0, x1, y1) boxes in reading order (row-major 2 cols x 3 rows)."""
    arr = np.asarray(img.convert("L"), dtype=np.float32)
    col_means = arr.mean(axis=0)
    row_means = arr.mean(axis=1)
    xs = _find_splits(col_means, expected_parts=2)
    ys = _find_splits(row_means, expected_parts=3)
    boxes: list[tuple[int, int, int, int]] = []
    for y0, y1 in ys:
        for x0, x1 in xs:
            boxes.append((x0, y0, x1, y1))
    return boxes


def slice_page(page_path: Path, out_dir: Path) -> list[Path]:
    """Slice a 2x3 comic page into 6 cached panel PNGs."""
    out_dir.mkdir(parents=True, exist_ok=True)
    expected = [out_dir / f"panel_{i}.png" for i in range(1, 7)]
    if all(p.exists() for p in expected):
        return expected
    img = Image.open(page_path).convert("RGB")
    boxes = detect_gutters(img)
    paths: list[Path] = []
    for idx, box in enumerate(boxes[:6], start=1):
        crop = img.crop(box)
        p = out_dir / f"panel_{idx}.png"
        crop.save(p)
        paths.append(p)
    return paths
