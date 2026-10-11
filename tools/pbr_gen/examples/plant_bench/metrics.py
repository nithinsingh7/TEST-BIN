"""Score every model/material set and export viewer-ready textures + stats.json."""
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter

SETS, OUT = Path(sys.argv[1]), Path(sys.argv[2])
MODELS = {"gpt": "GPT Image 2.5 Sunburst", "gemini": "Nano Banana 2.1", "flux": "FLUX 3", "qwen": "Qwen Image 3 Pro"}
MATS = ["leaf", "bud", "stem", "soil"]
EXPORT = {"leaf": ["albedo", "opacity", "roughness", "normal_from_height", "translucency", "height"],
          "bud": ["albedo", "roughness", "normal_from_height", "ao_from_height", "height"],
          "stem": ["albedo", "roughness", "normal_from_height", "ao_from_height", "height"],
          "soil": ["albedo", "roughness", "normal_from_height", "ao_from_height", "height"]}


def gray(p, size=512):
    return np.asarray(Image.open(p).convert("L").resize((size, size), Image.LANCZOS), np.float32) / 255


def grad(a):
    a = np.asarray(Image.fromarray((a * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2)), np.float32) / 255
    gx = np.roll(a, -1, 1) - np.roll(a, 1, 1); gy = np.roll(a, -1, 0) - np.roll(a, 1, 0)
    return np.hypot(gx, gy)


def structure_match(ref, other, mask=None):
    """Correlation of edge maps: 1 = every edge in the map sits where the albedo has one."""
    g1, g2 = grad(gray(ref)), grad(gray(other))
    if mask is not None:
        m = np.asarray(Image.fromarray(mask).resize((512, 512)), bool)
        g1, g2 = g1[m], g2[m]
    g1 = g1 - g1.mean(); g2 = g2 - g2.mean()
    return float((g1 * g2).sum() / (np.linalg.norm(g1) * np.linalg.norm(g2) + 1e-9))


def seam_ratio(p):
    """Edge discontinuity across the wrap / typical neighbour difference. ~1 = already seamless."""
    a = np.asarray(Image.open(p).convert("RGB"), np.float32)
    wrap = (np.abs(a[:, 0] - a[:, -1]).mean() + np.abs(a[0] - a[-1]).mean()) / 2
    inner = (np.abs(a[:, 1:] - a[:, :-1]).mean() + np.abs(a[1:] - a[:-1]).mean()) / 2
    return float(wrap / (inner + 1e-9))


stats = {"models": MODELS, "materials": {}, "totals": {}}
results = {(r["model"], r["material"]): r for r in json.loads((SETS / "results.json").read_text())}
for mk in MODELS:
    tot_cost = tot_time = 0.0; n_img = 0
    for mat in MATS:
        d = SETS / mk / mat
        r = results.get((mk, mat), {})
        man = json.loads((d / "manifest.json").read_text()) if (d / "manifest.json").exists() else {}
        entry = {"ok": bool(r.get("ok")) and (d / "albedo.png").exists(), "error": r.get("error"),
                 "wall_seconds": r.get("wall_seconds"), "warnings": r.get("warnings", [])}
        if entry["ok"]:
            calls = [man.get("albedo", {})] + list(man.get("maps", {}).values())
            entry["cost"] = round(sum(c.get("cost", 0) or 0 for c in calls), 4)
            entry["api_seconds"] = round(sum(c.get("seconds", 0) or 0 for c in calls), 1)
            entry["images"] = len(calls)
            mask = None
            if mat == "leaf":
                mask = (np.asarray(Image.open(d / "opacity.png").convert("L")) > 127).astype(np.uint8)
                entry["silhouette"] = {k: v.get("alignment_score") for k, v in man["maps"].items()}
            raw = {k: d / f"{k}_raw.png" for k in man.get("maps", {})}
            entry["structure"] = {k: round(structure_match(d / "reference.png", p, mask), 3)
                                  for k, p in raw.items() if p.exists() and k in ("height", "roughness")}
            if mat != "leaf":
                entry["seam_ratio_raw"] = round(seam_ratio(d / "albedo_raw.png"), 2)
            tot_cost += entry["cost"]; tot_time += entry["wall_seconds"] or 0; n_img += entry["images"]
            dst = OUT / mk / mat; dst.mkdir(parents=True, exist_ok=True)
            for k in EXPORT[mat]:
                src = d / f"{k}.png"
                if not src.exists():
                    continue
                im = Image.open(src)
                if k == "opacity":
                    im.convert("L").save(dst / f"{k}.png", optimize=True)
                else:
                    im = im.convert("RGB") if k in ("albedo", "normal_from_height", "translucency") else im.convert("L")
                    im.save(dst / f"{k}.jpg", quality=88)
        stats["materials"].setdefault(mk, {})[mat] = entry
    stats["totals"][mk] = {"cost": round(tot_cost, 4), "wall_seconds": round(tot_time, 1), "images": n_img}
(OUT / "stats.json").write_text(json.dumps(stats, indent=1))
print(json.dumps(stats["totals"], indent=1))
for mk in MODELS:
    for mat in MATS:
        e = stats["materials"][mk][mat]
        print(mk, mat, e["ok"], e.get("cost"), e.get("structure"), e.get("silhouette"), e.get("seam_ratio_raw"), e.get("error"))
