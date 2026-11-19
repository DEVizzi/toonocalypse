"""Toonocalypse art kernel (Kaggle GPU T4 x2): FLUX.1-schnell job runner.

The job (prompts, seeds, candidate counts) is embedded by GitHub as base64. Outputs are written progressively
with manifest.json so a killed session can be resumed. Text encoders (CLIP + 8-bit T5) run on cuda:1, the 4-bit
transformer and VAE on cuda:0. Any prompt over the T5 token limit fails that item (never silently truncated).
"""
import base64
import json
import os
import subprocess
import sys
import time
import traceback

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U", "diffusers>=0.32", "transformers>=4.46",
                "accelerate", "bitsandbytes>=0.45", "sentencepiece", "protobuf"], check=False)

import torch  # noqa: E402

JOB = json.loads(base64.b64decode("__JOB_B64__"))
IM = JOB["image"]
OUT = "/kaggle/working"
MANIFEST = {"story_id": JOB["story_id"], "started": time.time(), "items": {}, "errors": [],
            "gpus": [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]}


def save():
    with open(os.path.join(OUT, "manifest.json"), "w") as f:
        json.dump(MANIFEST, f, indent=1)


def load_flux():
    from diffusers import BitsAndBytesConfig as DBnb, FluxPipeline, FluxTransformer2DModel
    from huggingface_hub import hf_hub_download
    from transformers import BitsAndBytesConfig as TBnb, T5EncoderModel

    repo = None
    for cand in IM["repos"]:
        try:
            hf_hub_download(cand, "model_index.json")
            repo = cand
            break
        except Exception as e:  # gated or missing: try the next configured repo
            print(f"[load] {cand} unavailable: {type(e).__name__}", flush=True)
    if repo is None:
        raise RuntimeError("no configured FLUX repo is downloadable")
    MANIFEST["repo"] = repo
    dt = torch.float16
    te = T5EncoderModel.from_pretrained(repo, subfolder="text_encoder_2", torch_dtype=dt,
                                        quantization_config=TBnb(load_in_8bit=True), device_map={"": 1})
    text = FluxPipeline.from_pretrained(repo, transformer=None, vae=None, text_encoder_2=te, torch_dtype=dt)
    text.text_encoder.to("cuda:1")
    tr = FluxTransformer2DModel.from_pretrained(repo, subfolder="transformer", torch_dtype=dt, device_map={"": 0},
                                                quantization_config=DBnb(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                                                         bnb_4bit_compute_dtype=dt))
    image = FluxPipeline.from_pretrained(repo, transformer=tr, text_encoder=None, text_encoder_2=None, tokenizer=None,
                                         tokenizer_2=None, torch_dtype=dt)
    image.vae.to("cuda:0")
    return text, image


def main():
    t0 = time.time()
    text, image = load_flux()
    MANIFEST["load_s"] = round(time.time() - t0, 1)
    save()
    for it in JOB["items"]:
        rec = MANIFEST["items"].setdefault(it["id"], {"kind": it["kind"], "character": it.get("character"),
                                                      "prompt": it["prompt"], "files": [], "seeds": []})
        try:
            t5 = len(text.tokenizer_2(it["prompt"]).input_ids)
            clip = len(text.tokenizer(it["prompt"]).input_ids)
            rec.update(t5_tokens=t5, clip_tokens=clip)
            if t5 > IM["max_t5_tokens"]:
                raise ValueError(f"prompt is {t5} T5 tokens (max {IM['max_t5_tokens']}); refusing to truncate")
            with torch.no_grad():
                pe, pooled, _ = text.encode_prompt(prompt=it["prompt"], prompt_2=None, device="cuda:1",
                                                   max_sequence_length=IM["max_t5_tokens"])
            for k in range(it["n"]):
                seed = int(it["seed"]) + k * 1000
                name = f"{it['id']}__s{seed}.png"
                if name in rec["files"]:
                    continue
                t = time.time()
                g = torch.Generator("cpu").manual_seed(seed)
                img = image(prompt_embeds=pe.to("cuda:0"), pooled_prompt_embeds=pooled.to("cuda:0"),
                            width=IM["width"], height=IM["height"], num_inference_steps=IM["steps"],
                            guidance_scale=IM["guidance"], generator=g).images[0]
                img.save(os.path.join(OUT, name))
                rec["files"].append(name)
                rec["seeds"].append(seed)
                print(f"{name} t5={t5} {time.time() - t:.1f}s", flush=True)
                save()
        except Exception as e:
            rec["error"] = f"{type(e).__name__}: {e}"[:500]
            MANIFEST["errors"].append(f"{it['id']}: {rec['error']}")
            print(traceback.format_exc()[-1500:], flush=True)
        save()
    MANIFEST["finished"] = time.time()
    save()


try:
    main()
except Exception as e:
    MANIFEST["errors"].append(f"fatal: {type(e).__name__}: {e}"[:800])
    print(traceback.format_exc(), flush=True)
    save()
