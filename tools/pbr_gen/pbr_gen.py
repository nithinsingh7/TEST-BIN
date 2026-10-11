#!/usr/bin/env python3
"""
Generate a full, pixel-aligned PBR texture set with OpenRouter's
openai/gpt-image-2.5-sunburst image model. Built to be called by people and by
agents (e.g. an agent modelling in Blender): pass --json for one machine-readable
result line on stdout; progress always goes to stderr.

Two kinds of material
  cutout   : one isolated object on alpha (leaf, feather, decal, sticker, card foliage).
             Gets an opacity mask; every map is re-fitted to the albedo's silhouette.
  tileable : a seamless surface filling the frame (bark, brick, fabric, rusty metal).
             No mask; every map is made seamless with the same blend, so they stay aligned.

Pipeline
  1. albedo : text -> image (transparent for cutout), local cleanup.
  2. maps   : the albedo is sent as the reference image with a per-map prompt. Every map
              comes from the SAME albedo (never chained), so errors don't accumulate.
  3. post   : resize to the albedo, re-fit to its silhouette (cutout), retry on shape
              drift, canonical background values, re-normalized normals, seamless blend
              (tileable). Normal and AO are also computed locally from the height map.

Usage
  export OPENROUTER_API_KEY=sk-or-...
  python pbr_gen.py all --kind cutout   --subject "a fresh green hydrangea leaf" --out tex/leaf --json
  python pbr_gen.py all --kind tileable --subject "weathered oak bark" --out tex/bark --json
  python pbr_gen.py all --kind tileable --subject "rusty painted steel plate" \\
                        --maps height,normal,roughness,ao,metallic \\
                        --notes "bare steel shows through where the paint is chipped" --out tex/steel --json
  # two-step, to inspect or hand-fix the albedo in between:
  python pbr_gen.py albedo --subject "..." --out tex/x
  python pbr_gen.py maps --out tex/x                        # or --albedo my_fixed.png

Then in Blender:  blender_material.py  (see README) builds the material from the folder.

Requires: requests, pillow, numpy
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFilter

API_URL = "https://openrouter.ai/api/v1/images"
DEFAULT_MODEL = "openai/gpt-image-2.5-sunburst"
QUALITIES = ["auto", "low", "medium", "high", "xhigh", "max"]
DEFAULT_MAPS = {"cutout": "height,normal,roughness,ao,translucency",
                "tileable": "height,normal,roughness,ao"}


def log(*a) -> None:
    print(*a, file=sys.stderr, flush=True)

# --------------------------------------------------------------------------- prompts


NO_LIGHT = ("This is an ALBEDO texture: completely even, shadowless, diffuse light; no shadows, no "
            "specular highlights, no gloss, no reflections, no rim light, no backlight glow, no "
            "vignette, no depth of field. Color-accurate, razor sharp, ultra-detailed.")

ALBEDO_PROMPTS = {
    "cutout": (
        "{subject}. A single isolated specimen, perfectly flat, seen straight down in an orthographic "
        "top view, centered, filling about 88% of a square frame; if it has a base or stem, it points "
        "to the bottom edge. Scan quality with primary, secondary and fine micro detail, subtle natural "
        "color variation and small natural imperfections. " + NO_LIGHT +
        " Isolated on a fully transparent background."),
    "tileable": (
        "Seamless tileable texture of {subject}. Fills the entire square frame edge to edge, "
        "orthographic straight-down view with no perspective, uniform scale, density and brightness "
        "across the whole frame, no single focal point, no border, no frame, no text. Scan quality "
        "with fine micro detail. " + NO_LIGHT),
}

ALIGN = {
    "cutout": ("Image 1 is the reference albedo texture. Produce a texture map of the EXACT same object, "
               "pixel-aligned with Image 1: identical silhouette, outline, size, position, rotation and "
               "framing, with every detail in exactly the same place. Do not redraw, move, crop, zoom or "
               "reinterpret the object. Square output, same composition. "),
    "tileable": ("Image 1 is the reference albedo texture. Produce a texture map of the EXACT same surface, "
                 "pixel-aligned with Image 1: every feature in exactly the same place and at the same "
                 "scale, filling the whole frame edge to edge. Do not redraw, move, crop, zoom or "
                 "reinterpret the surface. Square output. "),
}

# key -> (what the map is, canonical background RGB for cutouts, grayscale?)
MAP_SPECS: dict[str, tuple[str, tuple[int, int, int], bool]] = {
    "height": (
        "Output a grayscale HEIGHT / displacement map. White = highest, black = lowest. Raised features "
        "(ribs, veins, grain, bumps, ridges) are lighter, cracks, grooves and recesses darker, the base "
        "surface mid gray. Smooth gradients, no lighting, no shading, no shadows, no color.",
        (0, 0, 0), True),
    "normal": (
        "Output a tangent-space NORMAL map in OpenGL convention (Y+, green channel up). Flat areas are "
        "exactly RGB(128,128,255). Raised features show the standard normal-map edge colors consistent "
        "with being raised, recesses the opposite. No lighting, no shadows, no other colors.",
        (128, 128, 255), False),
    "roughness": (
        "Output a grayscale ROUGHNESS map. Black = glossy/smooth, white = fully rough/matte, with values "
        "true to the real material, soft subtle variation, worn or polished spots smoother, dirt and "
        "crevices rougher. No color, no lighting, no shadows.",
        (255, 255, 255), True),
    "ao": (
        "Output a grayscale AMBIENT OCCLUSION map. Mostly white; soft darkening only in cracks, grooves, "
        "crevices and where features meet. No color, no directional lighting.",
        (255, 255, 255), True),
    "metallic": (
        "Output a grayscale METALLIC mask. Pure white where the surface is bare metal, pure black where it "
        "is not metal (paint, rust, dirt, wood, stone, plastic, organic matter). Hard, nearly binary "
        "values. No lighting, no shading.",
        (0, 0, 0), True),
    "translucency": (
        "Output a TRANSLUCENCY / subsurface color map: how the material looks with strong light shining "
        "through it from behind. Thin areas glow with the transmitted color, thicker parts (veins, ribs, "
        "dense areas) appear darker and more opaque. No front lighting, no shadows.",
        (0, 0, 0), False),
}

BG_SENTENCE = {(0, 0, 0): "The background is pure black.",
               (255, 255, 255): "The background is pure white.",
               (128, 128, 255): "The background is flat RGB(128,128,255)."}


def map_prompt(key: str, kind: str, notes: str) -> str:
    desc, bg, _ = MAP_SPECS[key]
    p = ALIGN[kind] + desc
    if kind == "cutout":
        p += " " + BG_SENTENCE[bg]
    if notes:
        p += " Material notes: " + notes
    return p

# --------------------------------------------------------------------------- API


class ApiError(RuntimeError):
    pass


_cost_lock = threading.Lock()
_total_cost = [0.0]


def _data_url(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


_params_cache: dict[str, dict] = {}
_stats = threading.local()


def model_params(model: str) -> dict:
    """Parameters the model's endpoints accept, e.g. {"quality": [...], "background": [...], ...}."""
    if model not in _params_cache:
        url = f"https://openrouter.ai/api/v1/images/models/{model}/endpoints"
        try:
            eps = requests.get(url, timeout=30).json().get("endpoints", [])
        except (requests.RequestException, ValueError):
            eps = []
        merged: dict = {}
        for e in eps:
            for k, v in (e.get("supported_parameters") or {}).items():
                merged.setdefault(k, v)
        _params_cache[model] = merged
    return _params_cache[model]


def supports(model: str, param: str, value=None) -> bool:
    spec = model_params(model).get(param)
    if spec is None:
        return False
    return value is None or "values" not in spec or value in spec["values"]


def call_image_api(prompt: str, *, model: str, quality: str, background: str | None = None,
                   refs: list[Image.Image] | None = None, resolution: str | None = None,
                   retries: int = 4) -> tuple[Image.Image, float]:
    """POST /api/v1/images. Returns (image, cost_usd). Only sends parameters the model accepts.
    The wall-clock seconds of the successful call are left in _stats.seconds."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise ApiError("Set the OPENROUTER_API_KEY environment variable.")
    body: dict = {"model": model, "prompt": prompt, "n": 1}
    for k, v in (("aspect_ratio", "1:1"), ("quality", quality), ("background", background),
                 ("resolution", resolution)):
        if v and supports(model, k, v):
            body[k] = v
    if refs:
        body["input_references"] = [{"type": "image_url", "image_url": {"url": _data_url(r)}} for r in refs]
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json",
               "X-Title": "pbr_gen"}

    err = "no attempt made"
    for attempt in range(retries + 1):
        t0 = time.time()
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
                with _cost_lock:
                    _total_cost[0] += cost
                _stats.seconds = time.time() - t0
                return Image.open(io.BytesIO(raw)).copy(), cost
            err = f"HTTP {r.status_code}: {r.text[:500]}"
            if r.status_code in (400, 401, 402, 403, 413):
                raise ApiError(err)  # not retryable
        if attempt < retries:
            wait = 2 ** (attempt + 1)
            log(f"   ! {err} -- retrying in {wait}s")
            time.sleep(wait)
    raise ApiError(err)

# --------------------------------------------------------------------------- image helpers


def to_f(img: Image.Image) -> np.ndarray:
    return np.asarray(img, dtype=np.float32) / 255.0


def to_img(a: np.ndarray, mode: str | None = None) -> Image.Image:
    return Image.fromarray(np.clip(a * 255.0 + 0.5, 0, 255).astype(np.uint8), mode)


def blur(a: np.ndarray, r: float) -> np.ndarray:
    return to_f(to_img(a, "L").filter(ImageFilter.GaussianBlur(r)))


def corner_color(rgb: np.ndarray, k: int = 12) -> np.ndarray:
    c = [rgb[:k, :k], rgb[:k, -k:], rgb[-k:, :k], rgb[-k:, -k:]]
    return np.median(np.concatenate([x.reshape(-1, rgb.shape[2]) for x in c]), axis=0)


def has_alpha(img: Image.Image) -> bool:
    return img.mode in ("RGBA", "LA") and to_f(img.getchannel("A")).min() < 0.5


def object_mask(img: Image.Image, thresh: float = 0.10) -> np.ndarray:
    """Foreground mask: alpha if the image has real transparency, else 'differs from the corner color'."""
    if has_alpha(img):
        return to_f(img.getchannel("A")) > 0.5
    rgb = to_f(img.convert("RGB"))
    d = np.abs(rgb - corner_color(rgb)).sum(axis=2)
    return d > thresh


def clean_mask(m: np.ndarray, open_px: int = 3, erode_px: int = 1) -> np.ndarray:
    """Remove specks, fill holes, and pull the edge in slightly to drop fringe pixels."""
    im = Image.fromarray((m * 255).astype(np.uint8), "L")
    if open_px:
        k = open_px * 2 + 1
        im = im.filter(ImageFilter.MinFilter(k)).filter(ImageFilter.MaxFilter(k))  # opening
        im = im.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))  # light closing (keeps gaps between leaflets)
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
    if not mask.any() or mask.all():
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


def seamless_weights(h: int, w: int, border: float = 0.22) -> np.ndarray:
    """1 in the middle, falling smoothly to 0 near the edges."""
    def ramp(n):
        d = np.minimum(np.arange(n), np.arange(n)[::-1]) / (border * n)
        t = np.clip(d, 0, 1)
        return t * t * (3 - 2 * t)
    return np.minimum.outer(ramp(h), ramp(w)).astype(np.float32)


def make_seamless(a: np.ndarray) -> np.ndarray:
    """Offset-and-blend: near the edges use the half-shifted copy (whose borders come from the
    continuous center), in the middle keep the original. The same weights are used for every
    map, so all maps of a set stay aligned with each other."""
    h, w = a.shape[:2]
    shifted = np.roll(a, (h // 2, w // 2), axis=(0, 1))
    wt = seamless_weights(h, w)
    if a.ndim == 3:
        wt = wt[..., None]
    return a * wt + shifted * (1 - wt)


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
    """OpenGL (Y+) tangent-space normal map from a height map in [0,1] (wraps at the edges)."""
    scale = strength * h.shape[0] / 1024.0
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.5 * scale
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 0.5 * scale
    n = np.stack([-dx, dy, np.ones_like(h)], axis=-1)  # image rows go down, so +dy flips to Y+
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return n * 0.5 + 0.5


def ao_from_height(h: np.ndarray, strength: float = 0.5, wrap: bool = False) -> np.ndarray:
    """Cheap cavity-style AO: darken where the surface sits below its blurred neighborhood."""
    p = int(48 * h.shape[0] / 1024) if wrap else 0
    hp = np.pad(h, p, mode="wrap") if p else h
    s = h.shape[0] / 1024.0
    cav = sum(np.clip(blur(hp, r * s) - hp, 0, None) for r in (2, 6, 16))
    ao = np.clip(1.0 - cav * strength * 3.0, 0, 1)
    return ao[p:-p, p:-p] if p else ao

# --------------------------------------------------------------------------- steps


def save(img: Image.Image, out: Path, name: str, files: dict) -> None:
    img.save(out / f"{name}.png")
    files[name] = str((out / f"{name}.png").resolve())


def read_manifest(out: Path) -> dict:
    p = out / "manifest.json"
    return json.loads(p.read_text()) if p.exists() else {}


def write_manifest(out: Path, m: dict) -> None:
    (out / "manifest.json").write_text(json.dumps(m, indent=2, default=str))


def prepare_albedo(raw: Image.Image, out: Path, kind: str, files: dict) -> None:
    """Writes albedo.png, reference.png (what the model sees) and, for cutouts, opacity + rgba."""
    if kind == "cutout":
        mask = clean_mask(object_mask(raw))
        rgb = to_f(raw.convert("RGB"))
        albedo = to_img(edge_pad(rgb, mask), "RGB")
        mask_img = to_img(mask.astype(np.float32), "L")
        save(albedo, out, "albedo", files)
        save(mask_img, out, "opacity", files)
        rgba = albedo.copy(); rgba.putalpha(mask_img)
        save(rgba, out, "albedo_rgba", files)
        to_img(rgb * mask[..., None], "RGB").save(out / "reference.png")      # object on pure black
        log(f"   object covers {mask.mean():.1%} of the frame")
    else:
        rgb = to_f(raw.convert("RGB"))
        raw.convert("RGB").save(out / "reference.png")                       # un-blended original
        save(to_img(make_seamless(rgb), "RGB"), out, "albedo", files)


def step_albedo(args, files: dict, manifest: dict) -> None:
    out = Path(args.out)
    prompt = ALBEDO_PROMPTS[args.kind].format(subject=args.subject[0].upper() + args.subject[1:])
    if args.notes:
        prompt += " Material notes: " + args.notes
    bg = "transparent" if args.kind == "cutout" else "opaque"
    if args.kind == "cutout" and not supports(args.model, "background", "transparent"):
        prompt = prompt.replace("Isolated on a fully transparent background.",
                                "Isolated on a pure, flat black background (#000000) with nothing else in the frame.")
        log("   model has no transparent background; asking for pure black and keying it out")
    log(f"-> albedo ({args.kind}, {args.model}, quality={args.albedo_quality})")
    img, cost = call_image_api(prompt, model=args.model, quality=args.albedo_quality, background=bg,
                               resolution=args.resolution)
    img.save(out / "albedo_raw.png")
    log(f"   {img.size[0]}x{img.size[1]} {img.mode}, ${cost:.3f}")
    if args.kind == "cutout" and not has_alpha(img) and supports(args.model, "background", "transparent"):
        manifest["warnings"].append("albedo came back without transparency; mask was keyed from the background color")
    prepare_albedo(img, out, args.kind, files)
    manifest["albedo"] = {"prompt": prompt, "cost": cost, "seconds": round(_stats.seconds, 1),
                          "size": img.size}


def step_maps(args, files: dict, manifest: dict) -> None:
    out = Path(args.out)
    kind = args.kind
    if args.albedo:
        log(f"-> using albedo {args.albedo}")
        prepare_albedo(Image.open(args.albedo), out, kind, files)
    elif not (out / "reference.png").exists():
        raise ApiError(f"No albedo in {out}. Run the 'albedo' step first or pass --albedo.")
    for name in ("albedo", "opacity", "albedo_rgba"):
        if (out / f"{name}.png").exists():
            files.setdefault(name, str((out / f"{name}.png").resolve()))

    ref = Image.open(out / "reference.png").convert("RGB")
    size = ref.size
    mask = (np.asarray(Image.open(out / "opacity.png").convert("L")) > 127) if kind == "cutout" \
        else np.ones((size[1], size[0]), bool)
    ref_box = bbox(mask)
    keys = [k.strip() for k in args.maps.split(",") if k.strip()]
    bad = [k for k in keys if k not in MAP_SPECS]
    if bad:
        raise ApiError(f"Unknown map(s) {bad}. Choose from: {', '.join(MAP_SPECS)}")

    def one(key: str):
        prompt = map_prompt(key, kind, args.notes)
        _, bg, gray = MAP_SPECS[key]
        best = None
        spent = [0.0, 0.0]
        for attempt in range(1, args.retries + 2):
            img, cost = call_image_api(prompt, model=args.model, quality=args.quality, refs=[ref],
                                       resolution=args.resolution)
            spent[0] += cost; spent[1] += _stats.seconds
            img.convert("RGB").save(out / f"{key}_raw{'' if attempt == 1 else attempt}.png")
            img = img.convert("RGB").resize(size, Image.LANCZOS)
            if kind == "tileable":   # nothing to fit against; the reference is full-frame
                log(f"   {key:<12} try {attempt}: ${cost:.3f}")
                best = (img, None)
                break
            fitted, before = fit_to_reference(img, ref_box, bg)
            if key == "normal":  # flat normals look like the background, so compare outlines instead
                fb = bbox(object_mask(fitted))
                score = box_iou(fb, ref_box) if fb else 0.0
            else:
                score = shape_iou(fitted, mask)
            moved = "" if before > 0.995 else f" (re-fitted, box IoU was {before:.3f})"
            log(f"   {key:<12} try {attempt}: shape IoU {score:.3f}{moved}, ${cost:.3f}")
            if best is None or score > best[1]:
                best = (fitted, score)
            if score >= args.min_iou:
                break
        img, score = best
        return key, finalize(key, img, mask, bg, gray, kind), score, prompt, spent

    log(f"-> generating {', '.join(keys)} ({args.quality}) from the albedo reference")
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(one, keys))

    maps = {}
    for key, img, score, prompt, spent in results:
        save(img, out, key, files); maps[key] = img
        manifest["maps"][key] = {"prompt": prompt, "alignment_score": None if score is None else round(score, 4),
                                 "cost": round(spent[0], 4), "seconds": round(spent[1], 1)}
        if score is not None and score < args.min_iou:
            manifest["warnings"].append(f"{key}: alignment score {score:.3f} is below {args.min_iou}; "
                                        f"inspect {key}.png or use the *_from_height maps")

    # local, deterministic maps from height (always aligned, physically consistent)
    if "height" in maps:
        h = to_f(maps["height"].convert("L"))
        if kind == "cutout":
            h = edge_pad(h[..., None], mask)[..., 0]
        n = normal_from_height(h, args.normal_strength)
        ao = ao_from_height(h, wrap=(kind == "tileable"))
        n[~mask] = (0.5, 0.5, 1.0); ao[~mask] = 1.0
        save(to_img(n, "RGB"), out, "normal_from_height", files)
        save(to_img(ao, "L"), out, "ao_from_height", files)
        log("   computed normal_from_height.png and ao_from_height.png")

    # ORM pack (R=AO, G=roughness, B=metallic) for Unreal / glTF
    if "roughness" in maps:
        ao = maps.get("ao") or (Image.open(out / "ao_from_height.png") if "ao_from_height" in files
                                else Image.new("L", size, 255))
        met = maps.get("metallic") or Image.new("L", size, 0)
        save(Image.merge("RGB", (ao.convert("L"), maps["roughness"].convert("L"), met.convert("L"))),
             out, "orm_packed", files)


def finalize(key: str, img: Image.Image, mask: np.ndarray, bg, gray: bool, kind: str) -> Image.Image:
    """Canonical background, grayscale where needed, re-normalized normals, seamless for tileables."""
    a = to_f(img.convert("RGB"))
    if kind == "tileable":
        a = make_seamless(a)
    if key == "normal":
        n = a * 2 - 1
        n[..., 2] = np.clip(n[..., 2], 0.05, None)
        n /= np.linalg.norm(n, axis=-1, keepdims=True)
        a = n * 0.5 + 0.5
    if kind == "cutout":
        a[~mask] = np.array(bg, dtype=np.float32) / 255.0
    if gray:
        return to_img(a.mean(axis=2), "L")
    return to_img(a, "RGB")

# --------------------------------------------------------------------------- CLI


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["albedo", "maps", "all"])
    ap.add_argument("--out", required=True, help="output folder")
    ap.add_argument("--kind", choices=["cutout", "tileable"],
                    help="cutout = isolated object on alpha; tileable = seamless surface "
                         "(default: what the folder was made with, else cutout)")
    ap.add_argument("--subject", default="a fresh green leaf", help="what to make (albedo step)")
    ap.add_argument("--notes", default="", help="extra material facts added to every prompt")
    ap.add_argument("--albedo", help="use this albedo image instead of generating one")
    ap.add_argument("--maps", help="comma list from: " + ", ".join(MAP_SPECS) +
                    f". Default cutout: {DEFAULT_MAPS['cutout']}; tileable: {DEFAULT_MAPS['tileable']}")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--albedo-quality", default="max", choices=QUALITIES)
    ap.add_argument("--quality", default="high", choices=QUALITIES, help="quality for the derived maps")
    ap.add_argument("--resolution", default="1K", help="1K, 2K or 4K, for models that accept it (not GPT Image)")
    ap.add_argument("--retries", type=int, default=1, help="extra attempts when a cutout map doesn't line up")
    ap.add_argument("--min-iou", type=float, default=0.93, help="silhouette IoU (after auto-fit) to accept a map")
    ap.add_argument("--workers", type=int, default=3, help="parallel API calls")
    ap.add_argument("--normal-strength", type=float, default=16.0, help="for normal_from_height.png")
    ap.add_argument("--json", action="store_true", help="print one JSON result line on stdout")
    args = ap.parse_args()

    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    manifest = read_manifest(out)
    args.kind = args.kind or manifest.get("kind") or "cutout"
    args.maps = args.maps or DEFAULT_MAPS[args.kind]
    manifest.update(kind=args.kind, model=args.model, subject=args.subject if args.step != "maps"
                    else manifest.get("subject", args.subject))
    manifest.setdefault("maps", {})
    manifest["warnings"] = []
    files: dict[str, str] = {}

    ok, error = True, None
    try:
        if args.step in ("albedo", "all"):
            step_albedo(args, files, manifest)
        if args.step in ("maps", "all"):
            step_maps(args, files, manifest)
    except ApiError as e:
        ok, error = False, str(e)
        log(f"error: {e}")

    manifest["files"] = {**manifest.get("files", {}), **files}
    manifest["cost_usd_last_run"] = round(_total_cost[0], 4)
    write_manifest(out, manifest)
    for w in manifest["warnings"]:
        log(f"   ! {w}")
    log(f"{'done' if ok else 'failed'} -> {out.resolve()}  (cost ${_total_cost[0]:.3f})")

    if args.json:
        print(json.dumps({
            "ok": ok, "error": error, "kind": args.kind, "out": str(out.resolve()),
            "manifest": str((out / "manifest.json").resolve()),
            "files": manifest["files"], "warnings": manifest["warnings"],
            "cost_usd": round(_total_cost[0], 4),
            "blender": f'blender --background --python "{Path(__file__).resolve().with_name("blender_material.py")}"'
                       f' -- "{out.resolve()}"',
        }))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
