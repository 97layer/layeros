#!/usr/bin/env python3
"""
gen_lookbook.py — WOOHWAHAE 룩북 Imagen 4.0 이미지 생성

사용법:
    python3 core/scripts/gen_lookbook.py
    python3 core/scripts/gen_lookbook.py --prompt-index 0
    python3 core/scripts/gen_lookbook.py --all
"""

import argparse
import os
import sys
import io
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

import google.genai as genai
from google.genai import types

OUTPUT_DIR = Path(__file__).resolve().parents[2] / "website/archive/lookbook/assets/images"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

GRAIN_INTENSITY = 28      # 0=없음, 18=subtle, 28=film, 40=heavy
GRAIN_HIGHLIGHT_PROTECT = 0.55  # 밝은 영역은 grain 줄이기 (0~1)


def apply_film_grain(img_bytes: bytes) -> bytes:
    """ISO 400 필름 그레인 시뮬레이션."""
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    arr = np.array(img, dtype=np.float32)

    # 루미넌스 기반 grain mask — 어두운 곳에 grain 많이
    luma = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
    shadow_mask = 1.0 - np.clip(luma / 255.0, 0, 1) * GRAIN_HIGHLIGHT_PROTECT
    shadow_mask = shadow_mask[:, :, np.newaxis]

    # 각 채널 독립 노이즈 (필름 느낌)
    rng = np.random.default_rng()
    noise = rng.normal(0, GRAIN_INTENSITY, arr.shape).astype(np.float32)
    noise *= shadow_mask

    # 미세한 blur로 grain 입자감
    noise_img = Image.fromarray(np.clip(noise + 128, 0, 255).astype(np.uint8))
    noise_img = noise_img.filter(ImageFilter.GaussianBlur(radius=0.4))
    noise = np.array(noise_img, dtype=np.float32) - 128

    result = np.clip(arr + noise, 0, 255).astype(np.uint8)
    out = Image.fromarray(result)

    buf = io.BytesIO()
    out.save(buf, format="JPEG", quality=92, subsampling=2)
    return buf.getvalue()

# 소거(消去) — 하나만 남기고 전부 어둠으로
BASE_STYLE = "pure black background, single light source, analog film grain, no text, no logo"

PROMPTS = [
    {
        "filename": "lookbook-01-stillness.jpg",
        "prompt": "A single white peony floating in absolute darkness. " + BASE_STYLE,
    },
    {
        "filename": "lookbook-02-texture.jpg",
        "prompt": "A woman's face in profile, eyes closed, one white flower resting on her hair. Black void. " + BASE_STYLE,
    },
    {
        "filename": "lookbook-03-space.jpg",
        "prompt": "A pair of hands releasing a single moth into darkness. " + BASE_STYLE,
    },
    {
        "filename": "lookbook-04-ritual.jpg",
        "prompt": "One stem of wild grass bending, a crescent moon far above. Nothing else. " + BASE_STYLE,
    },
    {
        "filename": "lookbook-05-material.jpg",
        "prompt": "A single fallen petal on black stone. Close. " + BASE_STYLE,
    },
    {
        "filename": "lookbook-06-portrait.jpg",
        "prompt": "A person's bare shoulder, one small flower placed on the collarbone. Dark. " + BASE_STYLE,
    },
    {
        "filename": "lookbook-07-moment.jpg",
        "prompt": "One candle flame and a moth circling it. Total darkness around. " + BASE_STYLE,
    },
    {
        "filename": "lookbook-08-light.jpg",
        "prompt": "A silk ribbon mid-fall in darkness, light catching only its edge. " + BASE_STYLE,
    },
]


def generate_image(client: genai.Client, prompt_data: dict, dry_run: bool = False) -> bool:
    out_path = OUTPUT_DIR / prompt_data["filename"]

    if out_path.exists():
        print("skip (exists): %s" % prompt_data["filename"])
        return True

    if dry_run:
        print("[dry-run] would generate: %s" % prompt_data["filename"])
        print("  prompt: %s" % prompt_data["prompt"][:80])
        return True

    print("generating: %s" % prompt_data["filename"])
    try:
        response = client.models.generate_images(
            model="imagen-4.0-generate-001",
            prompt=prompt_data["prompt"],
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio="3:4",
                safety_filter_level="BLOCK_LOW_AND_ABOVE",
            ),
        )
        img = response.generated_images[0].image
        grained = apply_film_grain(img.image_bytes)
        out_path.write_bytes(grained)
        print("  saved: %s (%d KB, grain applied)" % (out_path.name, len(grained) // 1024))
        return True
    except Exception as e:
        print("  ERROR: %s" % e)
        return False


def main():
    parser = argparse.ArgumentParser(description="WOOHWAHAE 룩북 이미지 생성")
    parser.add_argument("--prompt-index", type=int, help="단일 프롬프트 인덱스 (0-based)")
    parser.add_argument("--all", action="store_true", help="전체 생성")
    parser.add_argument("--dry-run", action="store_true", help="실제 생성 없이 프롬프트 확인")
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY or GOOGLE_API_KEY not set")
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    if args.prompt_index is not None:
        if args.prompt_index >= len(PROMPTS):
            print("ERROR: index %d out of range (0-%d)" % (args.prompt_index, len(PROMPTS) - 1))
            sys.exit(1)
        targets = [PROMPTS[args.prompt_index]]
    else:
        targets = PROMPTS

    print("target: %d images → %s" % (len(targets), OUTPUT_DIR))
    ok = 0
    for p in targets:
        if generate_image(client, p, dry_run=args.dry_run):
            ok += 1

    print("\ndone: %d/%d" % (ok, len(targets)))


if __name__ == "__main__":
    main()
