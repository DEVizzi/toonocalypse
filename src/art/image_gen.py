"""2x3 comic page image generation with Gemini, HF Flux, Pollinations Flux, and offline fallback."""
from __future__ import annotations

import hashlib
import os
import time
import urllib.parse
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw, ImageOps

from src.art.prompt_builder import build_page_prompt
from src.common.config import load_all_characters, load_models, load_style_guide
from src.common.quota import QuotaTracker


def render_offline_comic_page(script: dict[str, Any], out_path: Path) -> Path:
    """Render a deterministic 2x3 comic page with 24px white gutters for dry-run & CI tests."""
    gutter = 24
    pw, ph = 900, 900
    w = gutter * 3 + pw * 2
    h = gutter * 4 + ph * 3
    img = Image.new("RGB", (w, h), "#FFFFFF")
    draw = ImageDraw.Draw(img)
    chars = load_all_characters()

    bg_colors = ["#E3F2FD", "#FFF8E1", "#FCE4EC", "#E8F5E9", "#EDE7F6", "#FFF3E0"]
    for idx, panel in enumerate(script["panels"][:6]):
        row, col = idx // 2, idx % 2
        x0 = gutter + col * (pw + gutter)
        y0 = gutter + row * (ph + gutter)
        x1, y1 = x0 + pw, y0 + ph
        draw.rectangle([x0, y0, x1, y1], fill=bg_colors[idx % len(bg_colors)], outline="#222222", width=4)

        slugs = panel.get("characters", [])[:3]
        for ci, slug in enumerate(slugs):
            c = chars.get(slug)
            if not c:
                continue
            pri = c["palette"]["primary"]
            acc = c["palette"]["accent"]
            scale = min(1.8, max(0.35, float(c.get("height_units", 1.0))))
            rad = int(95 * scale)
            cx = x0 + 220 + ci * 240
            cy = y1 - 140 - rad
            draw.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=pri, outline="#111111", width=5)
            draw.ellipse([cx - rad // 2, cy - rad // 2, cx + rad // 2, cy + rad // 2], fill=acc)
            ew = max(8, rad // 6)
            draw.ellipse([cx - ew * 2, cy - ew, cx - ew // 2, cy + ew // 2], fill="#FFFFFF")
            draw.ellipse([cx + ew // 2, cy - ew, cx + ew * 2, cy + ew // 2], fill="#FFFFFF")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return out_path


def _build_single_panel_prompt(script: dict[str, Any], panel: dict[str, Any], chars: dict[str, Any]) -> str:
    """Build a focused, high-detail single-panel prompt for Flux/diffusion models."""
    slugs = panel.get("characters") or script.get("heroes") or []
    char_lines = []
    for slug in slugs[:3]:
        c = chars.get(slug)
        if not c:
            continue
        anchors = ", ".join(c.get("anchors", [])[:3])
        char_lines.append(f"{c['name']} ({c['visual_prompt']}; key features: {anchors})")

    style_summary = " ".join(load_style_guide().splitlines()[:4])[:220]
    setting = script.get("setting", "vibrant cartoon town")
    action = panel.get("action", "Characters react dramatically.")
    return (
        f"Stylized 3D animated motion-comic frame, expressive character acting, crisp clean outlines, "
        f"cinematic warm lighting, rich detailed background ({setting}). {style_summary} "
        f"Characters in scene: {'; '.join(char_lines)}. "
        f"Action: {action}. "
        f"Composition: centered subject with breathing room around edges. "
        f"STRICTLY NO text, NO speech bubbles, NO captions, NO letters, NO watermark."
    )


def _composite_panels_page(panel_imgs: list[Image.Image], out_path: Path) -> Path:
    """Assemble 6 high-res panels onto a pixel-exact 2x3 page with 24px white gutters."""
    gutter = 24
    pw, ph = 900, 900
    w = gutter * 3 + pw * 2
    h = gutter * 4 + ph * 3
    page = Image.new("RGB", (w, h), "#FFFFFF")
    draw = ImageDraw.Draw(page)
    for idx, p_img in enumerate(panel_imgs[:6]):
        row, col = idx // 2, idx % 2
        x0 = gutter + col * (pw + gutter)
        y0 = gutter + row * (ph + gutter)
        fitted = ImageOps.fit(p_img.convert("RGB"), (pw, ph), method=Image.Resampling.LANCZOS)
        page.paste(fitted, (x0, y0))
        draw.rectangle([x0, y0, x0 + pw - 1, y0 + ph - 1], outline="#222222", width=3)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    page.save(out_path)
    return out_path


def _generate_panel_huggingface(prompt: str, hf_token: str) -> Image.Image:
    """Generate one high-res panel via Hugging Face Inference API (FLUX.1-dev -> FLUX.1-schnell)."""
    headers = {"Authorization": f"Bearer {hf_token}"}
    for model in ("black-forest-labs/FLUX.1-dev", "black-forest-labs/FLUX.1-schnell"):
        url = f"https://router.huggingface.co/hf-inference/models/{model}"
        resp = requests.post(
            url,
            headers=headers,
            json={"inputs": prompt, "parameters": {"width": 1024, "height": 1024}},
            timeout=120,
        )
        if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("image/"):
            return Image.open(BytesIO(resp.content)).convert("RGB")
    raise RuntimeError(f"HuggingFace inference failed ({resp.status_code}: {resp.text[:160]})")


def _generate_panel_pollinations(prompt: str, seed: int) -> Image.Image:
    """Generate one high-res panel via Pollinations.ai Flux (free, zero-key)."""
    encoded = urllib.parse.quote(prompt, safe="")
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?model=flux&width=1024&height=1024&nologo=true&enhance=true&seed={seed}"
    )
    headers = {}
    api_key = os.environ.get("POLLINATIONS_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    last_err: Exception | None = None
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=headers, timeout=90)
            if resp.status_code == 200 and resp.content and len(resp.content) > 5000:
                return Image.open(BytesIO(resp.content)).convert("RGB")
            last_err = RuntimeError(f"HTTP {resp.status_code}: {resp.text[:120]}")
        except Exception as exc:
            last_err = exc
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Pollinations failed: {last_err}")


def _generate_panels_free_fallback(script: dict[str, Any], out_path: Path) -> Path:
    """Generate 6 high-detail panels via HF Flux (if HF_TOKEN) or Pollinations Flux and composite 2x3."""
    chars = load_all_characters()
    hf_token = os.environ.get("HF_TOKEN", "").strip()
    base_seed = int(hashlib.sha256(str(script.get("story_id", "toon")).encode()).hexdigest()[:8], 16)
    panel_imgs: list[Image.Image] = []

    for idx, panel in enumerate(script["panels"][:6]):
        prompt = _build_single_panel_prompt(script, panel, chars)
        img: Image.Image | None = None
        if hf_token:
            try:
                img = _generate_panel_huggingface(prompt, hf_token)
            except Exception as exc:
                print(f"[image_gen] HF Flux panel {idx + 1} failed ({exc}); trying Pollinations Flux...")
        if img is None:
            img = _generate_panel_pollinations(prompt, seed=base_seed + idx)
        panel_imgs.append(img)
        time.sleep(1.0)

    return _composite_panels_page(panel_imgs, out_path)


def generate_comic_page(
    script: dict[str, Any],
    out_path: Path,
    offline: bool = False,
    quota: QuotaTracker | None = None,
) -> Path:
    """Generate a 2x3 comic page using Gemini, free Flux fallback (HF / Pollinations), or offline."""
    if out_path.exists():
        return out_path
    if offline:
        return render_offline_comic_page(script, out_path)

    from src.common.gemini import call_with_key_failover, has_gemini_keys

    last_err: Exception | None = None
    if has_gemini_keys():
        qt = quota or QuotaTracker()
        models_cfg = load_models()
        image_models = models_cfg.get("image_models", ["gemini-3.1-flash-image"])
        delay = float(models_cfg.get("quota", {}).get("min_delay_between_images_sec", 5))
        prompt, ref_paths = build_page_prompt(script)

        from google.genai import types

        contents: list[Any] = [prompt]
        for rp in ref_paths[:4]:
            contents.append(Image.open(rp))

        for model_name in image_models:
            if not qt.can_spend("image", 1):
                break
            try:
                resp = call_with_key_failover(
                    lambda client, m=model_name: client.models.generate_content(
                        model=m,
                        contents=contents,
                        config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
                    )
                )
                qt.spend("image", 1)
                for cand in getattr(resp, "candidates", []) or []:
                    for part in cand.content.parts:
                        if getattr(part, "inline_data", None) is not None:
                            img = Image.open(BytesIO(part.inline_data.data)).convert("RGB")
                            out_path.parent.mkdir(parents=True, exist_ok=True)
                            img.save(out_path)
                            time.sleep(delay)
                            return out_path
            except Exception as exc:
                last_err = exc
                time.sleep(1)

    print(f"[image_gen] Gemini image models unavailable ({last_err}); using free Flux panel generator...")
    return _generate_panels_free_fallback(script, out_path)
