"""Weekly learning loop + health report (§13). Analytics calls are best-effort: missing scopes are reported, not fatal."""
from __future__ import annotations

import os
import sys
import time
from statistics import mean

import requests
import yaml

from src.common import alerts
from src.common.config import CONFIG_DIR, categories
from src.common.quota import Quota
from src.common.state import load_state, save_state
from src.publish import buffer as buf


def youtube_metrics(video_ids: list[str]) -> dict[str, dict]:
    from src.publish import youtube

    if not video_ids:
        return {}
    tok = youtube.access_token()
    end = time.strftime("%Y-%m-%d")
    start = time.strftime("%Y-%m-%d", time.gmtime(time.time() - 28 * 86400))
    r = requests.get("https://youtubeanalytics.googleapis.com/v2/reports", headers={"Authorization": f"Bearer {tok}"}, timeout=60, params={
        "ids": "channel==MINE", "startDate": start, "endDate": end, "dimensions": "video",
        "metrics": "views,averageViewPercentage,shares,subscribersGained", "filters": f"video=={','.join(video_ids[:200])}"})
    if r.status_code != 200:
        raise RuntimeError(f"YouTube Analytics unavailable ({r.status_code}); the refresh token may lack yt-analytics.readonly scope")
    cols = [c["name"] for c in r.json()["columnHeaders"]]
    return {row[0]: dict(zip(cols, row)) for row in r.json().get("rows", [])}


def adjust_weights(cat_scores: dict[str, float], weights: dict[str, float], step: float = 0.10, floor: float = 5) -> dict[str, float]:
    """Move each weight ±10% toward performance (vs the mean score), renormalize to 100, keep a floor."""
    if not cat_scores:
        return weights
    avg = mean(cat_scores.values())
    new = {}
    for k, w in weights.items():
        s = cat_scores.get(k)
        new[k] = w * (1 + step) if s is not None and s > avg else w * (1 - step) if s is not None and s < avg else w
    total = sum(new.values())
    new = {k: max(floor, v * 100 / total) for k, v in new.items()}
    total = sum(new.values())
    return {k: round(v * 100 / total, 1) for k, v in new.items()}


def main() -> int:
    bible, pub, b = load_state("story_bible.json"), load_state("published.json", {"episodes": {}}), load_state("buffer.json", {"stories": []})
    q, tokens = Quota(), load_state("tokens.json", {})
    lines, notes = [], []
    # episode -> category
    cat_of = {}
    for h in bible.get("history", []):
        for ep_id in (h.get("platform_ids") or {}):
            cat_of[ep_id] = h["category"]
    yt_ids = {v["youtube"]["id"]: ep for ep, v in pub.get("episodes", {}).items() if v.get("youtube", {}).get("id")}
    per_ep = {}
    try:
        for vid, m in youtube_metrics(list(yt_ids)).items():
            per_ep[yt_ids[vid]] = m
    except Exception as e:
        notes.append(str(e))
    ranked = sorted(per_ep.items(), key=lambda kv: kv[1].get("averageViewPercentage", 0), reverse=True)
    if ranked:
        lines.append("**Top 3 (avg view %)**: " + ", ".join(f"{e} {m['averageViewPercentage']:.0f}%" for e, m in ranked[:3]))
        lines.append("**Bottom 3**: " + ", ".join(f"{e} {m['averageViewPercentage']:.0f}%" for e, m in ranked[-3:]))
        scores: dict[str, list[float]] = {}
        for e, m in per_ep.items():
            if e in cat_of:
                scores.setdefault(cat_of[e], []).append(m["averageViewPercentage"])
        cfg = categories()
        old = {k: v["weight"] for k, v in cfg["categories"].items()}
        new = adjust_weights({k: mean(v) for k, v in scores.items()}, old)
        if new != old:
            path = CONFIG_DIR / "categories.yaml"
            data = yaml.safe_load(path.read_text())
            for k, w in new.items():
                data["categories"][k]["weight"] = w
            path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
            lines.append(f"**Category weights**: {old} -> {new}")
    lines += [f"**Buffer**: {buf.ready_episode_count(b, pub)} ready episodes",
              f"**Kaggle GPU this week**: {q.data['kaggle']['gpu_hours_used']}h of {q.kaggle_limit_hours():.1f}h budget",
              f"**Gemini calls today**: {q.data['gemini']['calls']}",
              f"**Instagram token**: {tokens.get('instagram', {}).get('days_left', 'unknown')} days left",
              f"**Aborts in a row**: {q.data['aborts']['consecutive']} ({q.data['aborts']['last_reason'] or '-'})"]
    if notes:
        lines.append("**Notes**: " + "; ".join(notes))
    body = "\n".join(f"- {ln}" for ln in lines)
    print(body)
    subprocess_title = f"Toonocalypse weekly health {time.strftime('%Y-%m-%d')}"
    import subprocess

    subprocess.run(["gh", "issue", "create", "--title", subprocess_title, "--body", body], check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
