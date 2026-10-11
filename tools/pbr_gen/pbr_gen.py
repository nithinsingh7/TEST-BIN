#!/usr/bin/env python3
"""
Generate a full, pixel-aligned PBR texture set with OpenRouter's
openai/gpt-image-2.5-sunburst image model.

Pipeline
  1. albedo  : text -> image with a transparent background, then local cleanup
               (opacity mask from alpha, hole fill, speck removal, edge padding).
  2. maps    : the cleaned albedo is sent as a reference image with a per-map
               prompt. Every map is generated from the SAME albedo (never chained
               from another generated map) so errors don't accumulate.
  3. post    : each map is resized to the albedo, re-fitted to the albedo's
               silhouette, given a canonical background, and value-cleaned.
               Normal and AO can also be computed locally from the height map.

Usage
  export OPENROUTER_API_KEY=sk-or-...
  python pbr_gen.py albedo --subject "a fresh green hydrangea leaf" --out out/leaf
  #   -> inspect / hand-fix out/leaf/albedo.png if needed, then:
  python pbr_gen.py maps --out out/leaf
  # or everything in one go:
  python pbr_gen.py all --subject "a fresh green hydrangea leaf" --out out/leaf
  # use your own albedo (PNG with alpha, or opaque on a plain background):
  python pbr_gen.py maps --albedo my_leaf.png --out out/leaf

Requires: requests, pillow, numpy
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFilter

API_URL = "https://openrouter.ai/api/v1/images"
DEFAULT_MODEL = "openai/gpt-image-2.5-sunburst"

# --------------------------------------------------------------------------- prompts

ALBEDO_PROMPT = """\
{subject}, a single specimen, perfectly flat, seen straight down in an orthographic top view, \
centered, filling about 88% of a square frame, base/stem pointing to the bottom edge. \
Botanical-scan quality, ultra-detailed surface: visible primary, secondary and fine micro detail, \
subtle natural color variation and tiny natural imperfections. \
This is an ALBEDO texture: completely even, shadowless, diffuse light; no shadows, no specular \
highlights, no gloss, no reflections, no rim light, no backlight glow, no vignette, no depth of field. \
Isolated on a fully transparent background. Color-accurate, razor sharp."""

ALIGN = (
    "Image 1 is the reference albedo texture. Produce a texture map of the EXACT same object, "
    "pixel-aligned with Image 1: identical silhouette, outline, size, position, rotation and framing, "
    "with every vein and detail in exactly the same place. Do not redraw, move, crop, zoom or "
    "reinterpret the object. Square output, same composition. "
)

# key -> (prompt, canonical background RGB, grayscale?)
MAP_SPECS: dict[str, tuple[str, tuple[int, int, int], bool]] = {
    "height": (
        ALIGN + "Output a grayscale HEIGHT / displacement map. White = highest, black = lowest. "
        "Raised ribs and veins are light gray to white, the flat surface between them is mid gray "
        "(about 50%), fine micro detail is subtle. Smooth gradients, no lighting, no shading, no "
        "shadows, no color. The background is pure black.",
        (0, 0, 0), True),
    "normal": (
        ALIGN + "Output a tangent-space NORMAL map in OpenGL convention (Y+, green channel up). "
        "Flat areas are exactly RGB(128,128,255). Raised veins show the standard normal-map edge "
        "colors, consistent with the geometry being raised. No lighting, no shadows, no other colors. "
        "The background is flat RGB(128,128,255).",
        (128, 128, 255), False),
    "roughness": (
        ALIGN + "Output a grayscale ROUGHNESS map. Black = glossy, white = fully rough. The main "
        "surface is a slightly waxy dark-to-mid gray (about 35-45% brightness), raised veins and "
        "ribs slightly lighter (rougher), with soft subtle variation. No color, no lighting, no "
        "shadows. The background is pure white.",
        (255, 255, 255), True),
    "ao": (
        ALIGN + "Output a grayscale AMBIENT OCCLUSION map. Mostly white; only very soft, subtle "
        "darkening in the shallow grooves alongside the veins and at the base. No color, no "
        "directional lighting. The background is pure white.",
        (255, 255, 255), True),
    "translucency": (
        ALIGN + "Output a TRANSLUCENCY / subsurface color map: how the object looks with strong "
        "light shining through it from behind. Thin tissue glows warm yellow-green, thicker veins "
        "and ribs appear darker and more opaque. No front lighting, no shadows. The background is "
        "pure black.",
        (0, 0, 0), False),
}

# --------------------------------------------------------------------------- API


class ApiError(RuntimeError):
    pass


def _data_url(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def call_image_api(prompt: str, *, model: str, quality: str, background: str | None = None,
                   refs: list[Image.Image] | None = None, retries: int = 4) -> tuple[Image.Image, float]:
    """POST /api/v1/images. Returns (image, cost_usd)."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise ApiError("Set the OPENROUTER_API_KEY environment variable.")
    body: dict = {"model": model, "prompt": prompt, "aspect_ratio": "1:1", "quality": quality, "n": 1}
    if background:
        body["background"] = background
    if refs:
        body["input_references"] = [{"type": "image_url", "image_url": {"url": _data_url(r)}} for r in refs]
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json",
               "X-Title": "pbr_gen"}

    for attempt in range(retries + 1):
        try:
            r = requests.post(API_URL, headers=headers, json=body, timeout=900)
        except requests.RequestException as e:
            err = f"network error: {e}"
        else:
            if r.ok:
                payload = r.json()
                item = payload["data"][0]
                if item.get("b64_json"):
                    raw = base64.b64decode(item["b64_json"])
                else:
                    raw = requests.get(item["url"], timeout=300).content
                cost = float((payload.get("usage") or {}).get("cost") or 0.0)
                return Image.open(io.BytesIO(raw)).copy(), cost
            err = f"HTTP {r.status_code}: {r.text[:500]}"
            if r.status_code in (400, 401, 402, 403, 413):
                raise ApiError(err)  # not retryable
        if attempt < retries:
            wait = 2 ** (attempt + 1)
            print(f"   ! {err} -- retrying in {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise ApiError(err)

# --------------------------------------------------------------------------- image helpers


def to_f(img: Image.Image) -> np.ndarray:
    return np.asarray(img, dtype=np.float32) / 255.0


def to_img(a: np.ndarray, mode: str | None = None) -> Image.Image:
    return Image.fromarray(np.clip(a * 255.0 + 0.5, 0, 255).astype(np.uint8), mode)


def corner_color(rgb: np.ndarray, k: int = 12) -> np.ndarray:
    c = [rgb[:k, :k], rgb[:k, -k:], rgb[-k:, :k], rgb[-k:, -k:]]
    return np.median(np.concatenate([x.reshape(-1, rgb.shape[2]) for x in c]), axis=0)


def object_mask(img: Image.Image, thresh: float = 0.10) -> np.ndarray:
    """Foreground mask: alpha if the image has real transparency, else 'differs from the corner color'."""
    if img.mode in ("RGBA", "LA"):
        a = to_f(img.getchannel("A"))
        if a.min() < 0.5:
            return a > 0.5
    rgb = to_f(img.convert("RGB"))
    d = np.abs(rgb - corner_color(rgb)).sum(axis=2)
    return d > thresh


def clean_mask(m: np.ndarray, open_px: int = 3, erode_px: int = 1) -> np.ndarray:
    """Remove specks, fill holes, and pull the edge in slightly to drop fringe pixels."""
    im = Image.fromarray((m * 255).astype(np.uint8), "L")
    if open_px:
        k = open_px * 2 + 1
        im = im.filter(ImageFilter.MinFilter(k)).filter(ImageFilter.MaxFilter(k))  # opening
        im = im.filter(ImageFilter.MaxFilter(k)).filter(ImageFilter.MinFilter(k))  # closing
    # fill interior holes: flood the background from the border, everything not reached is object
    padded = Image.new("L", (im.width + 2, im.height + 2), 0)
    padded.paste(im, (1, 1))
    ImageDraw.floodfill(padded, (0, 0), 128)
    filled = np.asarray(padded)[1:-1, 1:-1] != 128
    im = Image.fromarray((filled * 255).astype(np.uint8), "L")
    if erode_px:
        im = im.filter(ImageFilter.MinFilter(erode_px * 2 + 1))
    return np.asarray(im) > 127


def edge_pad(rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Push-pull fill: extend object colors into the background so mipmaps/filtering don't
    pull the background color into the edges (the classic foliage halo)."""
    if not mask.any():
        return rgb
    c = rgb * mask[..., None]
    w = mask.astype(np.float32)
    stack = []
    while True:
        stack.append((c, w))
        if min(w.shape) <= 1:
            break
        ph, pw = w.shape[0] % 2, w.shape[1] % 2
        c = np.pad(c, ((0, ph), (0, pw), (0, 0)))
        w = np.pad(w, ((0, ph), (0, pw)))
        c = c.reshape(c.shape[0] // 2, 2, c.shape[1] // 2, 2, -1).sum((1, 3))
        w = w.reshape(w.shape[0] // 2, 2, w.shape[1] // 2, 2).sum((1, 3))
    c, w = stack[-1]
    out = c / np.maximum(w, 1e-8)[..., None]
    for c, w in reversed(stack[:-1]):
        up = np.repeat(np.repeat(out, 2, 0), 2, 1)[: w.shape[0], : w.shape[1]]
        a = np.clip(w, 0, 1)[..., None]
        out = (c / np.maximum(w, 1e-8)[..., None]) * a + up * (1 - a)
    # soften the blocky pyramid fill so the padding is a smooth color field
    r = max(8.0, rgb.shape[0] / 48.0)
    out = np.stack([blur(out[..., i], r) for i in range(out.shape[2])], axis=-1)
    return np.where(mask[..., None], rgb, out)


def bbox(m: np.ndarray, frac: float = 0.002) -> tuple[int, int, int, int] | None:
    """Bounding box (x0, y0, x1, y1) ignoring rows/cols with only stray pixels."""
    rows = np.where(m.sum(1) > m.shape[1] * frac)[0]
    cols = np.where(m.sum(0) > m.shape[0] * frac)[0]
    if len(rows) == 0 or len(cols) == 0:
        return None
    return cols[0], rows[0], cols[-1] + 1, rows[-1] + 1


def box_iou(a, b) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    area = lambda r: (r[2] - r[0]) * (r[3] - r[1])
    return inter / float(area(a) + area(b) - inter)


def fit_to_reference(img: Image.Image, ref_box, bg_rgb) -> tuple[Image.Image, float]:
    """Scale/shift a generated map so its object's bounding box matches the albedo's.
    Returns (fitted image, bbox IoU before fitting)."""
    out_box = bbox(object_mask(img))
    if out_box is None:
        return img, 0.0
    iou = box_iou(out_box, ref_box)
    if iou > 0.995:
        return img, iou
    sx = (out_box[2] - out_box[0]) / (ref_box[2] - ref_box[0])
    sy = (out_box[3] - out_box[1]) / (ref_box[3] - ref_box[1])
    # affine maps output pixel -> input pixel
    coeffs = (sx, 0, out_box[0] - ref_box[0] * sx, 0, sy, out_box[1] - ref_box[1] * sy)
    fill = tuple(bg_rgb) if img.mode == "RGB" else int(bg_rgb[0])
    return img.transform(img.size, Image.AFFINE, coeffs, Image.BICUBIC, fillcolor=fill), iou


def shape_iou(img: Image.Image, mask: np.ndarray) -> float:
    """How well a generated map's silhouette matches the albedo mask (after fitting)."""
    m = clean_mask(object_mask(img), erode_px=0)
    return float((m & mask).sum() / max((m | mask).sum(), 1))


def normal_from_height(h: np.ndarray, strength: float = 16.0) -> np.ndarray:
    """OpenGL (Y+) tangent-space normal map from a height map in [0,1]."""
    scale = strength * h.shape[0] / 1024.0
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.5 * scale
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 0.5 * scale
    n = np.stack([-dx, dy, np.ones_like(h)], axis=-1)  # image rows go down, so +dy flips to Y+
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return n * 0.5 + 0.5


def blur(a: np.ndarray, r: float) -> np.ndarray:
    return to_f(to_img(a, "L").filter(ImageFilter.GaussianBlur(r)))


def ao_from_height(h: np.ndarray, strength: float = 0.5) -> np.ndarray:
    """Cheap cavity-style AO: darken where the surface sits below its blurred neighborhood."""
    s = h.shape[0] / 1024.0
    cav = sum(np.clip(blur(h, r * s) - h, 0, None) for r in (2, 6, 16))
    return np.clip(1.0 - cav * strength * 3.0, 0, 1)

# --------------------------------------------------------------------------- steps


def load_albedo(path: Path) -> tuple[Image.Image, np.ndarray]:
    img = Image.open(path)
    mask = clean_mask(object_mask(img))
    return img.convert("RGB"), mask


def cleanup_albedo(raw: Image.Image, out: Path) -> tuple[Image.Image, np.ndarray]:
    mask = clean_mask(object_mask(raw))
    rgb = to_f(raw.convert("RGB"))
    padded = edge_pad(rgb, mask)
    albedo = to_img(padded, "RGB")
    albedo.save(out / "albedo.png")                                       # edge-padded, opaque
    to_img(mask.astype(np.float32), "L").save(out / "opacity.png")
    rgba = albedo.copy(); rgba.putalpha(to_img(mask.astype(np.float32), "L"))
    rgba.save(out / "albedo_rgba.png")                                    # albedo + alpha in one file
    reference(albedo, mask).save(out / "reference.png")
    print(f"   coverage {mask.mean():.1%}, saved albedo.png / albedo_rgba.png / opacity.png / reference.png")
    return albedo, mask


def reference(albedo: Image.Image, mask: np.ndarray) -> Image.Image:
    """Opaque reference for the model: object on pure black, no transparency surprises."""
    rgb = to_f(albedo) * mask[..., None]
    return to_img(rgb, "RGB")


def step_albedo(args) -> None:
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    prompt = ALBEDO_PROMPT.format(subject=args.subject[0].upper() + args.subject[1:])
    print(f"-> albedo ({args.model}, quality={args.albedo_quality}, transparent)")
    img, cost = call_image_api(prompt, model=args.model, quality=args.albedo_quality,
                               background="transparent")
    img.save(out / "albedo_raw.png")
    print(f"   {img.size[0]}x{img.size[1]} {img.mode}, ${cost:.3f}")
    if img.mode != "RGBA" or to_f(img.getchannel("A")).min() > 0.5:
        print("   ! no transparency in the result; falling back to background-color keying")
    cleanup_albedo(img, out)
    _log(out, "albedo", {"prompt": prompt, "cost": cost, "size": img.size})


def step_maps(args) -> None:
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    if args.albedo:
        print(f"-> using your albedo {args.albedo}")
        albedo, mask = cleanup_albedo(Image.open(args.albedo), out)
    elif (out / "albedo.png").exists():
        albedo = Image.open(out / "albedo.png").convert("RGB")
        mask = np.asarray(Image.open(out / "opacity.png").convert("L")) > 127
    else:
        sys.exit(f"No albedo found in {out}. Run the 'albedo' step first or pass --albedo.")

    ref = reference(albedo, mask)
    ref_box = bbox(mask)
    size = albedo.size
    keys = [k for k in args.maps.split(",") if k]
    for k in keys:
        if k not in MAP_SPECS:
            sys.exit(f"Unknown map '{k}'. Choose from: {', '.join(MAP_SPECS)}")

    def one(key: str):
        prompt, bg, gray = MAP_SPECS[key]
        best = None
        for attempt in range(1, args.retries + 2):
            img, cost = call_image_api(prompt, model=args.model, quality=args.quality, refs=[ref])
            img.convert("RGB").save(out / f"{key}_raw{'' if attempt == 1 else attempt}.png")
            img = img.convert("RGB").resize(size, Image.LANCZOS)
            fitted, box_iou_before = fit_to_reference(img, ref_box, bg)
            if key == "normal":  # flat normals look like the background, so compare outlines instead
                fb = bbox(object_mask(fitted))
                iou = box_iou(fb, ref_box) if fb else 0.0
            else:
                iou = shape_iou(fitted, mask)
            moved = "" if box_iou_before > 0.995 else f" (re-fitted, box IoU was {box_iou_before:.3f})"
            print(f"   {key:<12} try {attempt}: shape IoU {iou:.3f}{moved}, ${cost:.3f}")
            if best is None or iou > best[1]:
                best = (fitted, iou, cost)
            if iou >= args.min_iou:
                break
        fitted, iou, cost = best
        if iou < args.min_iou:
            print(f"   ! {key}: best IoU {iou:.3f} is below {args.min_iou}; check {key}.png by eye")
        return key, finalize(key, fitted, mask, bg, gray), iou, prompt

    print(f"-> generating {', '.join(keys)} ({args.quality}) from the albedo reference")
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(one, keys))

    maps = {}
    for key, img, iou, prompt in results:
        img.save(out / f"{key}.png"); maps[key] = img
        _log(out, key, {"prompt": prompt, "shape_iou": round(iou, 4)})

    # local, deterministic maps from height (always aligned, physically consistent)
    if "height" in maps:
        h = edge_pad(to_f(maps["height"].convert("RGB")), mask)[..., 0]
        n = normal_from_height(h, args.normal_strength)
        n[~mask] = (0.5, 0.5, 1.0)
        to_img(n, "RGB").save(out / "normal_from_height.png")
        ao = ao_from_height(h); ao[~mask] = 1.0
        to_img(ao, "L").save(out / "ao_from_height.png")
        print("   computed normal_from_height.png and ao_from_height.png")

    # ORM pack (R=AO, G=roughness, B=metallic=0) for Unreal/glTF-style workflows
    if "roughness" in maps:
        ao = maps.get("ao")
        if ao is None and (out / "ao_from_height.png").exists():
            ao = Image.open(out / "ao_from_height.png")
        if ao is None:
            ao = Image.new("L", size, 255)
        orm = Image.merge("RGB", (ao.convert("L"), maps["roughness"].convert("L"), Image.new("L", size, 0)))
        orm.save(out / "orm_packed.png")
        print("   packed orm_packed.png (R=AO, G=roughness, B=metallic)")
    print(f"done -> {out.resolve()}")


def finalize(key: str, img: Image.Image, mask: np.ndarray, bg, gray: bool) -> Image.Image:
    """Canonical background, grayscale where needed, re-normalized normals."""
    a = to_f(img.convert("RGB"))
    if key == "normal":
        n = a * 2 - 1
        n[..., 2] = np.clip(n[..., 2], 0.05, None)
        n /= np.linalg.norm(n, axis=-1, keepdims=True)
        a = n * 0.5 + 0.5
    a[~mask] = np.array(bg, dtype=np.float32) / 255.0
    if gray:
        return to_img(a.mean(axis=2), "L")
    return to_img(a, "RGB")


def _log(out: Path, key: str, data: dict) -> None:
    p = out / "manifest.json"
    m = json.loads(p.read_text()) if p.exists() else {}
    m[key] = data
    p.write_text(json.dumps(m, indent=2, default=str))

# --------------------------------------------------------------------------- CLI


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["albedo", "maps", "all"])
    ap.add_argument("--out", required=True, help="output folder")
    ap.add_argument("--subject", default="a fresh green leaf", help="what to make (albedo step)")
    ap.add_argument("--albedo", help="use this albedo image instead of the one in --out")
    ap.add_argument("--maps", default="height,normal,roughness,ao,translucency",
                    help="comma list from: " + ", ".join(MAP_SPECS))
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--albedo-quality", default="max", choices=["auto", "low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--quality", default="high", choices=["auto", "low", "medium", "high", "xhigh", "max"],
                    help="quality for the derived maps")
    ap.add_argument("--retries", type=int, default=1, help="extra attempts when a map doesn't line up")
    ap.add_argument("--min-iou", type=float, default=0.93, help="silhouette IoU (after auto-fit) needed to accept a map")
    ap.add_argument("--workers", type=int, default=3, help="parallel API calls")
    ap.add_argument("--normal-strength", type=float, default=16.0, help="for normal_from_height.png")
    args = ap.parse_args()
    try:
        if args.step in ("albedo", "all"):
            step_albedo(args)
        if args.step in ("maps", "all"):
            step_maps(args)
    except ApiError as e:
        sys.exit(f"API error: {e}")


if __name__ == "__main__":
    main()
