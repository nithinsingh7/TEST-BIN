import json, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
TOOL, OUT = sys.argv[1], sys.argv[2]
MODELS = {"gpt": "openai/gpt-image-2.5-sunburst", "gemini": "google/gemini-nano-banana-2.1",
          "flux": "black-forest-labs/flux-3-image", "qwen": "qwen/qwen-image-3-pro"}
MATS = {
 "leaf": dict(kind="cutout", maps="height,roughness,translucency",
   subject="a single large cannabis (Cannabis sativa) fan leaf with seven serrated leaflets radiating from the petiole, healthy deep green",
   notes="serrated leaflet edges; each leaflet has a prominent central vein with fine side veins"),
 "bud": dict(kind="tileable", maps="height,roughness",
   subject="a macro close-up of a dense cannabis flower bud surface: tightly packed light-green calyxes, curly orange-brown pistil hairs and a frosty coating of tiny white glandular trichomes",
   notes="trichomes are tiny bright frosty bulbs; pistils are thin curly hairs lying on the calyxes"),
 "stem": dict(kind="tileable", maps="height,roughness",
   subject="a close-up of a green cannabis plant stem surface: fibrous ridges and grooves running straight from top to bottom, fine tiny hairs, faint purple-red streaks",
   notes="all ridges run vertically from the top edge to the bottom edge"),
 "soil": dict(kind="tileable", maps="height,roughness",
   subject="dark moist potting soil seen from above, with small white perlite granules, coco coir fibers and tiny bark chips",
   notes="perlite granules are bright white and rough; damp soil is slightly glossy"),
}
def job(mk, mat):
    m, cfg = MODELS[mk], MATS[mat]
    q = ["--albedo-quality", "high", "--quality", "high"] if mk == "gpt" else ["--resolution", "1K"]
    cmd = [sys.executable, f"{TOOL}/pbr_gen.py", "all", "--model", m, "--kind", cfg["kind"], "--maps", cfg["maps"],
           "--subject", cfg["subject"], "--notes", cfg["notes"], "--out", f"{OUT}/{mk}/{mat}", "--json", "--workers", "3", *q]
    t0 = time.time()
    with open(f"{OUT}/{mk}_{mat}.log", "w") as lf:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=lf, text=True)
    try:
        res = json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:
        res = {"ok": False, "error": f"no JSON (exit {p.returncode})"}
    res.update(model=mk, material=mat, wall_seconds=round(time.time() - t0, 1))
    print(mk, mat, res["ok"], res.get("error"), res.get("cost_usd"), res["wall_seconds"], flush=True)
    return res
jobs = [(mk, mat) for mk in MODELS for mat in MATS]
with ThreadPoolExecutor(8) as ex:
    results = list(ex.map(lambda a: job(*a), jobs))
json.dump(results, open(f"{OUT}/results.json", "w"), indent=1)
print("TOTAL", round(sum(r.get("cost_usd") or 0 for r in results), 3))
