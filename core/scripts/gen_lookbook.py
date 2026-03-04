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

GRAIN_INTENSITY = 10      # 0=없음, 10=subtle, 18=film, 28=heavy
GRAIN_HIGHLIGHT_PROTECT = 0.80  # 밝은 영역은 grain 줄이기 (0~1)


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
    out.save(buf, format="JPEG", quality=97, subsampling=0)
    return buf.getvalue()

SHARED = "analog 35mm film grain, no text, no logo, 3:4 portrait"

PROMPTS = [
    {
        "filename": "lookbook-01-stillness.jpg",
        "prompt": "A single white peony floating in absolute darkness. Pure black background, single directional light. " + SHARED,
    },
    {
        # 백자 그릇 — 단순, 동아시아 감각
        "filename": "lookbook-02-fragment.jpg",
        "prompt": "Overhead shot of a single white porcelain bowl on dark wet stone, one small smooth pebble inside, a thin film of still water at the bottom reflecting faint light. Minimal, contemporary. " + SHARED,
    },
    {
        # 황혼 복도 — 넓은 공간감
        "filename": "lookbook-03-interval.jpg",
        "prompt": "An empty corridor at blue dusk, worn concrete walls, all doors shut, one sheet of white paper lying face-down on the floor midway. No people. Cold ambient light. " + SHARED,
    },
    {
        # 콘크리트 옥상 — 현대적, 도시
        "filename": "lookbook-04-weight.jpg",
        "prompt": "Empty concrete rooftop at predawn, a single folded dark jacket left on the low ledge, city fog filling the space below, cool blue ambient light from above, modernist. " + SHARED,
    },
    {
        # 어두운 물 위 — 리본 유영
        "filename": "lookbook-05-drift.jpg",
        "prompt": "A long white silk cloth floating just above dark still water at night, one end already touching the surface and dissolving. Moonlight from the side. " + SHARED,
    },
    {
        # 계단 끝 / 안개 수면
        "filename": "lookbook-06-threshold.jpg",
        "prompt": "Stone steps descending into dark fog-covered water, only the top three steps visible, the rest swallowed. Low diffuse light from above. " + SHARED,
    },
    {
        # 현대 미용가위 — 클린, 정밀
        "filename": "lookbook-07-remains.jpg",
        "prompt": "A pair of sleek modern Japanese barber scissors lying flat on white marble, blades just slightly open, one long sharp shadow raking across the surface from side light. Clean, precise. " + SHARED,
    },
    {
        # 어두운 방 창문 — 부재의 후크
        "filename": "lookbook-08-absence.jpg",
        "prompt": "Dark interior room, gray fog outside a single tall window, an empty coat hook on the wall beside it, no coat, strong window light casting one long shadow. " + SHARED,
    },
    # ─── CGI / Surreal render series ───
    {
        "filename": "lookbook-12-render-a.jpg",
        "prompt": "A single white peony flower made entirely of shattered porcelain fragments, disintegrating in zero gravity, each shard perfectly lit with ray-traced reflections, absolute black void. Hyper-realistic 3D CGI render, Octane/Blender aesthetic, ultra-sharp. analog 35mm film grain, no text, no logo, 3:4 portrait",
    },
    {
        "filename": "lookbook-13-render-b.jpg",
        "prompt": "An impossibly thin vertical sheet of dark water suspended mid-air, its surface a perfect mirror, a single white flower reflection visible in it but no flower above. Black void. Hyperrealistic CGI render, ray-traced caustics, photorealistic 3D visualization, studio lighting. analog 35mm film grain, no text, no logo, 3:4 portrait",
    },
    {
        "filename": "lookbook-14-render-c.jpg",
        "prompt": "A single strand of black hair magnified to monumental scale, frozen mid-fall, forming an architectural curve against pure white fog. Hyper-detailed CGI visualization, studio lighting, subsurface scattering on the hair strand, perfect rendering. analog 35mm film grain, no text, no logo, 3:4 portrait",
    },
    # ─── Light series — 라이트 그레이 배경, 헤어 에디토리얼 ───
    {
        "filename": "lookbook-09-cut.jpg",
        "prompt": "A bundle of dark cut hair lying on pale concrete floor, strands spreading slightly outward. Overhead natural window light, soft shadow, minimal. analog 35mm film grain, editorial fashion, no text, no logo, 3:4 portrait",
    },
    {
        "filename": "lookbook-10-hold.jpg",
        "prompt": "A single hand loosely holding closed barber scissors against a pale gray wall. Strong side shadow. Desaturated. analog 35mm film grain, editorial fashion, no text, no logo, 3:4 portrait",
    },
    {
        "filename": "lookbook-11-after.jpg",
        "prompt": "Back of a person's bare nape, hair freshly cut very short, collar of a white garment just visible at the bottom. Off-white concrete wall background. Natural side light. analog 35mm film grain, editorial fashion, no text, no logo, 3:4 portrait",
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
