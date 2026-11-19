"""Toonocalypse model bake-off (Kaggle GPU T4 x2).

Same 2 comic prompts x 2 seeds on 3 commercial-safe models; saves PNGs, a labelled
comparison sheet and manifest.json. Each model runs in its own try/except so one
failure never hides the others.
"""
import gc
import json
import os
import subprocess
import sys
import time
import traceback

CHILD = len(sys.argv) > 1 and sys.argv[1] in ("flux_schnell", "dreamshaper_xl", "pixart_sigma")
if not CHILD:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U", "diffusers>=0.32", "transformers>=4.46",
                "accelerate", "bitsandbytes>=0.45", "sentencepiece", "protobuf", "compel==2.0.3"], check=False)

import torch  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

OUT = "/kaggle/working"
W, H = 768, 1344
SEEDS = [1234, 98765]
STYLE = ("bold comic book art, thick black outlines, flat cel-shaded colours, clean simple background, "
         "dramatic rim lighting, expressive faces, high detail")
NEGATIVE = ("text, letters, words, speech bubble, caption, watermark, signature, logo, extra fingers, extra limbs, "
            "deformed hands, distorted face, blurry, lowres, crowd, photorealistic, 3d render, gore, blood, "
            "superhero costume, cowl, emblem")
HERO = ("Aarav Teshan, a 19 year old young man, lean athletic build, oval face, long black hair tied in a high topknot, "
        "amber eyes, warm brown skin, wearing a saffron-orange tunic with a brown leather chest strap, "
        "a quiver with one glowing silver arrow on his back")
GIRL = ("Kiri Valen, a 12 year old girl, small build, round face, short curly red hair, green eyes, fair freckled skin, "
        "wearing a teal hooded cloak and grey boots, holding a small wooden lantern")
GATE = "a windswept stone mountain gate at dawn, misty peaks, pale gold sky, simple clean background"
PROMPTS = {
    "closeup": f"{HERO}, close-up, determined expression, drawing his bowstring back, {GATE}, empty sky in upper quarter, {STYLE}",
    "twoshot": (f"{HERO}, on the left facing right, {GIRL}, on the right facing left, medium two-shot, "
                f"Kiri points up in alarm while Aarav turns toward her, {GATE}, empty sky in upper quarter, {STYLE}"),
}
MANIFEST = {"started": time.time(), "gpus": [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())],
            "models": {}, "images": []}


def save_manifest():
    with open(os.path.join(OUT, "manifest.json"), "w") as f:
        json.dump(MANIFEST, f, indent=2)


def run_model(key, label, license_name, build, gen):
    rec = MANIFEST["models"][key] = {"label": label, "license": license_name, "ok": False, "seconds": {}}
    save_manifest()
    try:
        t = time.time()
        pipe = build()
        rec["load_s"] = round(time.time() - t, 1)
        for pname, prompt in PROMPTS.items():
            for seed in SEEDS:
                t = time.time()
                img = gen(pipe, prompt, seed)
                name = f"{key}__{pname}__s{seed}.png"
                img.save(os.path.join(OUT, name))
                rec["seconds"][name] = round(time.time() - t, 1)
                MANIFEST["images"].append({"model": key, "prompt": pname, "seed": seed, "file": name})
                print(f"[{key}] {name} in {rec['seconds'][name]}s", flush=True)
                save_manifest()
        rec["ok"] = True
        del pipe
    except Exception as e:  # keep going with the next model
        rec["error"] = f"{type(e).__name__}: {e}"[:800]
        rec["trace"] = traceback.format_exc()[-2000:]
        print(f"[{key}] FAILED {rec['error']}", flush=True)
    pipe = None
    gc.collect()
    torch.cuda.empty_cache()
    rec["gpu_free_gb"] = round(torch.cuda.mem_get_info()[0] / 2**30, 2)
    save_manifest()


# ---------------------------------------------------------------- A: FLUX.1-schnell (Apache-2.0), 4-bit on T4
def build_flux():
    from diffusers import BitsAndBytesConfig as DBnb, FluxPipeline, FluxTransformer2DModel
    from transformers import BitsAndBytesConfig as TBnb, T5EncoderModel

    from huggingface_hub import hf_hub_download

    repo = None
    for cand in ("black-forest-labs/FLUX.1-schnell", "unsloth/FLUX.1-schnell"):  # mirror = same Apache-2.0 weights
        try:
            hf_hub_download(cand, "model_index.json")  # gated repos expose metadata but block files
            repo = cand
            break
        except Exception as e:
            print(f"[flux] {cand} unavailable: {type(e).__name__}", flush=True)
    if repo is None:
        raise RuntimeError("no FLUX.1-schnell repo reachable without a token")
    MANIFEST["models"]["flux_schnell"]["repo"] = repo
    dt = torch.float16
    tr = FluxTransformer2DModel.from_pretrained(repo, subfolder="transformer", torch_dtype=dt, quantization_config=DBnb(
        load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=dt))
    te = T5EncoderModel.from_pretrained(repo, subfolder="text_encoder_2", torch_dtype=dt,
                                        quantization_config=TBnb(load_in_8bit=True))
    pipe = FluxPipeline.from_pretrained(repo, transformer=tr, text_encoder_2=te, torch_dtype=dt)
    pipe.enable_model_cpu_offload()
    return pipe


def gen_flux(pipe, prompt, seed):
    g = torch.Generator("cpu").manual_seed(seed)
    return pipe(prompt, width=W, height=H, num_inference_steps=4, guidance_scale=0.0, max_sequence_length=512,
                generator=g).images[0]


# ---------------------------------------------------------------- B: DreamShaper XL (SDXL, OpenRAIL++-M) + Compel
def build_dreamshaper():
    from diffusers import DPMSolverMultistepScheduler, StableDiffusionXLPipeline

    pipe = StableDiffusionXLPipeline.from_pretrained("Lykon/dreamshaper-xl-1-0", torch_dtype=torch.float16,
                                                     variant="fp16").to("cuda")
    pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config, use_karras_sigmas=True,
                                                             algorithm_type="dpmsolver++")
    return pipe


def gen_sdxl(pipe, prompt, seed):
    from compel import Compel, ReturnedEmbeddingsType

    compel = Compel(tokenizer=[pipe.tokenizer, pipe.tokenizer_2], text_encoder=[pipe.text_encoder, pipe.text_encoder_2],
                    returned_embeddings_type=ReturnedEmbeddingsType.PENULTIMATE_HIDDEN_STATES_NON_NORMALIZED,
                    requires_pooled=[False, True], truncate_long_prompts=False)
    cond, pooled = compel(prompt)
    ncond, npooled = compel(NEGATIVE)
    cond, ncond = compel.pad_conditioning_tensors_to_same_length([cond, ncond])
    g = torch.Generator("cuda").manual_seed(seed)
    return pipe(prompt_embeds=cond, pooled_prompt_embeds=pooled, negative_prompt_embeds=ncond,
                negative_pooled_prompt_embeds=npooled, width=W, height=H, num_inference_steps=28,
                guidance_scale=6.0, generator=g).images[0]


# ---------------------------------------------------------------- C: PixArt-Sigma (OpenRAIL++-M), T5 300 tokens
def build_pixart():
    from diffusers import PixArtSigmaPipeline
    from transformers import BitsAndBytesConfig as TBnb, T5EncoderModel

    repo = "PixArt-alpha/PixArt-Sigma-XL-2-1024-MS"
    te = T5EncoderModel.from_pretrained(repo, subfolder="text_encoder", torch_dtype=torch.float16,
                                        quantization_config=TBnb(load_in_8bit=True))
    pipe = PixArtSigmaPipeline.from_pretrained(repo, text_encoder=te, torch_dtype=torch.float16)
    pipe.enable_model_cpu_offload()
    return pipe


def gen_pixart(pipe, prompt, seed):
    g = torch.Generator("cpu").manual_seed(seed)
    return pipe(prompt, negative_prompt=NEGATIVE, width=W, height=H, num_inference_steps=24, guidance_scale=4.5,
                max_sequence_length=300, generator=g).images[0]


def contact_sheet():
    models = [k for k, v in MANIFEST["models"].items() if v["ok"]]
    if not models:
        return
    cols = [(p, s) for p in PROMPTS for s in SEEDS]
    tw, th, pad = 384, 672, 60
    sheet = Image.new("RGB", (pad + len(cols) * tw, len(models) * (th + pad)), "white")
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.load_default(size=28)
    except TypeError:
        font = ImageFont.load_default()
    for r, m in enumerate(models):
        y = r * (th + pad)
        d.text((10, y + 10), MANIFEST["models"][m]["label"], fill="black", font=font)
        for c, (p, s) in enumerate(cols):
            im = Image.open(os.path.join(OUT, f"{m}__{p}__s{s}.png")).convert("RGB").resize((tw, th))
            sheet.paste(im, (pad // 2 + c * tw, y + pad))
    sheet.save(os.path.join(OUT, "comparison_sheet.jpg"), quality=90)


MODELS = {
    "flux_schnell": ("A: FLUX.1-schnell (Apache-2.0)", "Apache-2.0", build_flux, gen_flux),
    "dreamshaper_xl": ("B: DreamShaper XL (SDXL, OpenRAIL++-M)", "CreativeML OpenRAIL++-M", build_dreamshaper, gen_sdxl),
    "pixart_sigma": ("C: PixArt-Sigma (OpenRAIL++-M)", "CreativeML OpenRAIL++-M", build_pixart, gen_pixart),
}

if CHILD:  # child process: one model, clean GPU, own manifest
    key = sys.argv[1]
    run_model(key, *MODELS[key])
    with open(os.path.join(OUT, f"manifest_{key}.json"), "w") as f:
        json.dump({"models": MANIFEST["models"], "images": MANIFEST["images"]}, f)
    sys.exit(0)

script = os.path.abspath(sys.argv[0])
for key in MODELS:  # each model in its own process so GPU memory is fully released
    r = subprocess.run([sys.executable, script, key])
    part = os.path.join(OUT, f"manifest_{key}.json")
    if os.path.exists(part):
        d = json.load(open(part))
        MANIFEST["models"].update(d["models"])
        MANIFEST["images"] += d["images"]
        os.remove(part)
    else:
        MANIFEST["models"][key] = {"label": MODELS[key][0], "ok": False, "error": f"child exited {r.returncode}"}
    save_manifest()
contact_sheet()
MANIFEST["finished"] = time.time()
save_manifest()
print("done", json.dumps({k: (v["ok"], v.get("error")) for k, v in MANIFEST["models"].items()}), flush=True)
