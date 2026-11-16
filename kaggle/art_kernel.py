"""Toonocalypse art kernel (runs on Kaggle GPU). The GitHub side embeds the job below before `kaggle kernels push`.

Phases: PORTRAITS / PANELS / REPAIR. For every item it generates N candidates with SDXL (+ IP-Adapter Plus
from approved cast portraits, masked left/right for two characters), pre-filters them (CLIP text-image score,
DINOv2 similarity of each character region to its portrait, OCR text check), keeps the top K, upscales them
(Real-ESRGAN x2 -> 1080x1920 Lanczos) and writes /kaggle/working/out/*.jpg + manifest.json progressively.
"""
import base64
import io
import json
import os
import subprocess
import sys
import time
import traceback
import urllib.request

JOB = json.loads(base64.b64decode("__JOB_B64__").decode("utf-8"))
OUT = "/kaggle/working/out"
RAW = "/kaggle/working/raw"
os.makedirs(OUT, exist_ok=True)
os.makedirs(RAW, exist_ok=True)
T0 = time.time()
MANIFEST = {"job_id": JOB["job_id"], "phase": JOB["phase"], "story_id": JOB["story_id"], "started": T0,
            "finished": None, "items": {}, "errors": [], "versions": {}}


def save_manifest():
    MANIFEST["gpu_seconds"] = round(time.time() - T0, 1)
    with open(os.path.join(OUT, "manifest.json"), "w") as f:
        json.dump(MANIFEST, f, indent=2)


def log(msg):
    print(f"[{time.time() - T0:7.1f}s] {msg}", flush=True)


save_manifest()
subprocess.run([sys.executable, "-m", "pip", "install", "-q", *JOB["pip"]], check=True)

import numpy as np  # noqa: E402
import torch  # noqa: E402
from PIL import Image, ImageOps  # noqa: E402

M = JOB["models"]
DEV = "cuda"


def b64_image(s):
    return Image.open(io.BytesIO(base64.b64decode(s))).convert("RGB")


def region_mask(where, w, h):
    m = Image.new("L", (w, h), 0)
    box = {"left": (0, 0, int(w * 0.58), h), "right": (int(w * 0.42), 0, w, h),
           "center": (int(w * 0.2), 0, int(w * 0.8), h), "full": (0, 0, w, h)}[where]
    m.paste(255, box)
    return m


# ---------------------------------------------------------------- generation
def generate_all():
    from compel import Compel, ReturnedEmbeddingsType
    from diffusers import DPMSolverMultistepScheduler, StableDiffusionXLPipeline
    from diffusers.image_processor import IPAdapterMaskProcessor
    import diffusers

    MANIFEST["versions"]["diffusers"] = diffusers.__version__
    pipe = StableDiffusionXLPipeline.from_pretrained(M["base"], torch_dtype=torch.float16, variant="fp16",
                                                     use_safetensors=True).to(DEV)
    pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config, use_karras_sigmas=True,
                                                             algorithm_type="dpmsolver++")
    pipe.set_progress_bar_config(disable=True)
    compel = Compel(tokenizer=[pipe.tokenizer, pipe.tokenizer_2], text_encoder=[pipe.text_encoder, pipe.text_encoder_2],
                    returned_embeddings_type=ReturnedEmbeddingsType.PENULTIMATE_HIDDEN_STATES_NON_NORMALIZED,
                    requires_pooled=[False, True], truncate_long_prompts=False)
    mask_proc = IPAdapterMaskProcessor()
    ip_loaded = False
    items = sorted(JOB["items"], key=lambda it: len(it.get("refs", [])) > 0)  # character-free first (no IP-Adapter)
    for it in items:
        rec = MANIFEST["items"].setdefault(it["id"], {"raw": [], "kept": [], "rejected": []})
        refs = it.get("refs", [])
        if refs and not ip_loaded:
            log("loading IP-Adapter Plus SDXL x2 (masked)")
            pipe.load_ip_adapter(M["ip_adapter_repo"], subfolder="sdxl_models",
                                 weight_name=[M["ip_adapter_weight"]] * 2, image_encoder_folder=M["ip_adapter_encoder"])
            ip_loaded = True
        cond, pooled = compel([it["prompt"], it["negative"]])
        kwargs = dict(prompt_embeds=cond[0:1], pooled_prompt_embeds=pooled[0:1], negative_prompt_embeds=cond[1:2],
                      negative_pooled_prompt_embeds=pooled[1:2], num_inference_steps=it["steps"],
                      guidance_scale=it["guidance"], width=it["width"], height=it["height"])
        if ip_loaded:
            if refs:
                imgs = [b64_image(JOB["refs"][r["char"]]) for r in refs]
                wheres = [r["where"] for r in refs]
                scales = [it["ip_scale"]] * len(refs)
                if len(refs) == 1:
                    imgs, wheres, scales = imgs * 2, ["full", "full"], [it["ip_scale"], 0.0]
            else:
                imgs, wheres, scales = [Image.new("RGB", (512, 512))] * 2, ["full", "full"], [0.0, 0.0]
            pipe.set_ip_adapter_scale(scales)
            masks = mask_proc.preprocess([region_mask(w, it["width"], it["height"]) for w in wheres],
                                         height=it["height"], width=it["width"])
            kwargs.update(ip_adapter_image=imgs, cross_attention_kwargs={"ip_adapter_masks": [masks[0:1], masks[1:2]]})
        for k in range(it["n"]):
            if time.time() - T0 > JOB["time_budget_s"]:
                log("time budget reached; stopping generation (GitHub re-pushes the rest)")
                return pipe
            seed = int(it["seed"]) + k * 7919
            g = torch.Generator(device=DEV).manual_seed(seed)
            img = pipe(generator=g, **kwargs).images[0]
            path = os.path.join(RAW, f"{it['id']}__s{seed}.png")
            img.save(path)
            rec["raw"].append({"path": path, "seed": seed})
            log(f"{it['id']} candidate {k + 1}/{it['n']} seed={seed}")
        save_manifest()
    return pipe


# ---------------------------------------------------------------- pre-filter + upscale
def prefilter_and_upscale():
    from transformers import AutoImageProcessor, AutoModel, CLIPModel, CLIPProcessor

    clip = CLIPModel.from_pretrained(M["clip"], torch_dtype=torch.float16).to(DEV).eval()
    clip_p = CLIPProcessor.from_pretrained(M["clip"])
    dino = AutoModel.from_pretrained(M["dino"]).to(DEV).eval()
    dino_p = AutoImageProcessor.from_pretrained(M["dino"])
    try:
        import easyocr
        ocr = easyocr.Reader(["en"], gpu=True, verbose=False)
    except Exception as e:  # text is also checked by Gemini QA on GitHub
        ocr = None
        MANIFEST["errors"].append(f"easyocr unavailable: {e}")

    import spandrel
    esr_path = "/kaggle/working/RealESRGAN_x2plus.pth"
    if not os.path.exists(esr_path):
        urllib.request.urlretrieve(M["esrgan_url"], esr_path)
    esr = spandrel.ModelLoader().load_from_file(esr_path).to(DEV).eval().half()

    @torch.no_grad()
    def clip_score(img, text):
        inp = clip_p(text=[text], images=img, return_tensors="pt", truncation=True, max_length=77, padding=True).to(DEV)
        out = clip(**{k: (v.half() if v.dtype == torch.float32 else v) for k, v in inp.items()})
        a = out.image_embeds / out.image_embeds.norm(dim=-1, keepdim=True)
        b = out.text_embeds / out.text_embeds.norm(dim=-1, keepdim=True)
        return float((a * b).sum())

    @torch.no_grad()
    def dino_emb(img):
        out = dino(**dino_p(images=img, return_tensors="pt").to(DEV))
        v = out.last_hidden_state[:, 0]
        return v / v.norm(dim=-1, keepdim=True)

    ref_emb = {c: dino_emb(b64_image(s)) for c, s in JOB["refs"].items()}

    def has_text(img):
        if ocr is None:
            return False
        small = np.array(img.resize((img.width // 2, img.height // 2)))
        for _box, txt, conf in ocr.readtext(small):
            if conf > 0.45 and sum(ch.isalnum() for ch in txt) >= 2:
                return True
        return False

    @torch.no_grad()
    def upscale(img):
        t = torch.from_numpy(np.array(img)).permute(2, 0, 1).unsqueeze(0).half().div(255).to(DEV)
        up = esr(t).clamp(0, 1).squeeze(0).permute(1, 2, 0).float().cpu().numpy()
        big = Image.fromarray((up * 255).round().astype("uint8"))
        return ImageOps.fit(big, (1080, 1920), method=Image.LANCZOS)

    for it in JOB["items"]:
        rec = MANIFEST["items"].get(it["id"])
        if not rec:
            continue
        scored = []
        for r in rec["raw"]:
            img = Image.open(r["path"]).convert("RGB")
            entry = {"seed": r["seed"], "clip": round(clip_score(img, it["clip_text"]), 4), "dino": None, "text": has_text(img)}
            if it.get("anchors"):
                entry["anchor_min"] = round(min(clip_score(img, a) for a in it["anchors"]), 4)
            sims = []
            for ref in it.get("refs", []):
                box = {"left": (0, 0, 0.6, 1), "right": (0.4, 0, 1, 1), "center": (0.2, 0, 0.8, 1), "full": (0, 0, 1, 1)}[ref["where"]]
                crop = img.crop((int(box[0] * img.width), 0, int(box[2] * img.width), img.height))
                sims.append(float((dino_emb(crop) * ref_emb[ref["char"]]).sum()))
            if sims:
                entry["dino"] = round(min(sims), 4)
            reasons = []
            if entry["text"]:
                reasons.append("text detected")
            if entry["dino"] is not None and entry["dino"] < JOB["thresholds"]["dino_min"]:
                reasons.append(f"dino {entry['dino']} < {JOB['thresholds']['dino_min']}")
            entry["reasons"] = reasons
            (rec["rejected"] if reasons else scored).append(entry)
            entry["_img"] = img
        # the weakest anchor dominates: a missing accessory / bled colour sinks the candidate
        scored.sort(key=lambda e: e["clip"] + (e["dino"] or 0) + 3 * e.get("anchor_min", 0), reverse=True)
        for e in scored[: it["keep"]]:
            img = e.pop("_img")
            final = upscale(img) if it["upscale"] else img
            name = f"{it['id']}__s{e['seed']}.jpg"
            final.save(os.path.join(OUT, name), quality=93)
            e["file"] = name
            rec["kept"].append(e)
        for e in scored[it["keep"]:] + rec["rejected"]:
            e.pop("_img", None)
        rec.pop("raw", None)
        save_manifest()
        log(f"{it['id']}: kept {len(rec['kept'])}, rejected {len(rec['rejected'])}")


try:
    pipe = generate_all()
    del pipe
    torch.cuda.empty_cache()
    prefilter_and_upscale()
except Exception as e:
    MANIFEST["errors"].append(f"{type(e).__name__}: {e}")
    MANIFEST["errors"].append(traceback.format_exc()[-2000:])
    log(traceback.format_exc())
finally:
    MANIFEST["finished"] = time.time()
    save_manifest()
    log(f"done in {time.time() - T0:.0f}s")
