# Handover: PlantKit (AI PBR textures + procedural cannabis plant for an Unreal growing game)

You are picking up work started in a Claude Code cloud session. Read this first, then `PlantKit/README.md`.

## 1. Goal

The user is building an **Unreal Engine game where the player grows cannabis plants**. Work so far:

1. **A texture pipeline.** It makes pixel-aligned PBR texture sets with AI image models (via OpenRouter) and drops them into Blender.
2. **A procedural 3D plant**, fully flowering, textured by four models and compared on cost and quality.
3. **Next (not started):** growth animation in Unreal (see §7).

## 2. Where everything is

**On this laptop: the `PlantKit/` folder.** It arrived as 19 zips; extract them all into one folder.

```
PlantKit/
  README.md                  folder guide + Unreal material setup (read it)
  HANDOVER.md                this file
  blender/plant_<m>.blend    full scene per texture model (gpt, gemini, flux, qwen); materials wired, relative texture paths
  models/plant.fbx           whole plant for Unreal, 8 material slots, no embedded textures
  models/plant_body.glb      stem, fan leaves, soil, pot       (glb has no normals; importers compute them)
  models/plant_buds.glb      calyx clusters + sugar leaves
  models/plant_pistils.glb   pistil hairs (two materials)
  textures/<m>/<material>/   leaf | sugar | bud | stem | soil  (final maps + *_raw.png + manifest.json)
  scripts/pbr_gen/           texture generator + Blender material builder + benchmark (same code as the repo)
  scripts/build_plant.py     procedural plant generator (Blender Python / `pip install bpy`)
  scripts/make_blends.py     rebuilds the four .blend files and plant.fbx from models/ + textures/
  viewer/plant_texture_bench offline three.js comparison viewer (serve with `python -m http.server`)
  renders/, extras/          preview renders, contact sheets, replaced round-1 bud textures, first leaf test
```

**In the git repo:**
- **Repo:** `github.com/nithinsingh7/TEST-BIN`
- **Branch:** `ccr-cb364cf4-vh4s25`
- **PR:** #2, "Add pbr_gen: AI-generated PBR texture sets with Blender integration", into `feat/init-architecture-doc-2413623728769708145`. Not merged yet.
- **Contents:** everything lives under `tools/pbr_gen/`. Large assets (textures, .blend, FBX) are **not** in git; they exist only in PlantKit.

**Web viewer** (private, owned by the user): https://claude.ai/artifact/C23eXSBdD43ELrHW8ehVky. It has a model switcher, three lighting presets and the comparison table.

## 3. Decisions already made (don't relitigate)

**Image models (via OpenRouter). Two tiers, chosen by the user after a 4-model benchmark:**

| Tier | Model | Use for |
|---|---|---|
| `--tier standard` (default) | `google/gemini-nano-banana-2.1` | Everything by default: about 35% cheaper and about 2× faster than hq, nearly as good |
| `--tier hq` | `openai/gpt-image-2.5-sunburst` | Hero assets, close-ups, cutouts that need clean alpha (the only model with native transparency) |

**Rejected models:**
- **FLUX 3:** drew buds as a repeating grid of rosettes twice; its height and roughness maps are near-copies of the albedo.
- **Qwen Image 3 Pro:** drew a whole fan leaf when asked for a single sugar leaf; slowest.
- **Seedream 5.0 Pro:** its content moderation refuses the word "cannabis". Don't try to word around it.

**Pipeline rules that make the maps line up** (all implemented in `pbr_gen.py`):
- Generate the albedo first. Generate every other map **from that same albedo as the reference image**, never from another generated map.
- Re-fit each map to the albedo's silhouette and regenerate it if the shape drifts.
- Apply the same seamless blend to every map of a tileable set.
- **Use `normal_from_height.png` (computed locally) rather than the AI's normal map.** Image models get normal maps wrong.
- Normal maps are **OpenGL (Y+)**. In Unreal, tick **Flip Green Channel**.

**Format detail:** OpenRouter's Image API is `POST https://openrouter.ai/api/v1/images`. GPT Image 2.5 there has **no size/resolution parameter** (about 1024 px). Nano Banana accepts `resolution` 1K/2K/4K. `pbr_gen` queries each model's supported parameters and only sends those.

## 4. How to run things

```bash
pip install -r scripts/pbr_gen/requirements.txt            # requests, pillow, numpy
export OPENROUTER_API_KEY=<new key>                        # see §6, never hard-code it

# textures (progress on stderr, one JSON result line on stdout)
python scripts/pbr_gen/pbr_gen.py all --kind tileable --subject "weathered oak bark" --out out/bark --json
python scripts/pbr_gen/pbr_gen.py all --kind cutout --subject "a single cannabis sugar leaf ..." \
       --maps height,roughness,translucency --notes "..." --out out/sugar --json --tier hq
#   other options: --maps (height,normal,roughness,ao,metallic,translucency), --albedo <existing image>,
#   --model <any OpenRouter image model>, --resolution 2K, --retries, --min-iou, --workers

# Blender material from a texture folder (CLI or `import blender_material as bm` inside Blender)
blender --background --python scripts/pbr_gen/blender_material.py -- out/bark --object Trunk --tile-scale 3 --save scene.blend

# rebuild the plant geometry (writes plant.glb, plant_buds.glb, plant_hairs.glb)
blender --background --python scripts/build_plant.py -- plant.glb      # or: pip install bpy && python build_plant.py -- plant.glb
```

**Prompts used for the current plant**: see `scripts/pbr_gen/examples/plant_bench/run_bench.py`, entries `leaf`, `sugar`, `bud2` (the fresh bud), `stem` and `soil`. Each set's `manifest.json` also records the exact prompts.

## 5. Plant model facts

- **Size:** about 1.4 m tall, Z-up in Blender, meters. Pot plus soil, main stem with 12 nodes in a Christmas-tree shape, about 80 fan-leaf cards.
- **Colas:** made of hundreds of pointed calyx "nugs" in a spiral, plus frosted sugar-leaf cards and about 10k pistil tubes.
- **Polygon count:** about 340k vertices, mostly buds and pistils. **Too heavy for a game as-is**: decimate, or swap pistils for cards or a texture, and add LODs.
- **Material slots:** `leaf`, `sugar` (alpha cards, two-sided), `bud`, `stem`, `soil` (tileable, UVs in world scale, so keep tiling at 1), `pistil`, `pistil_w` (flat colors), `pot`.
- **Built with a fixed RNG seed (42)**, so the same code gives the same plant.

## 6. Security / cost

- An OpenRouter key was pasted in the cloud chat. **Treat it as exposed: rotate it** at openrouter.ai → Settings → Keys before doing anything, and use the new key only through `OPENROUTER_API_KEY`.
- **Spend so far: about $4.25** (OpenRouter-reported), including all tests and retries.
- **Typical cost per material** (albedo plus 2–3 maps, 1K): standard about $0.12–0.16, hq about $0.18–0.24 (more with `max` albedo quality).

## 7. Next task: growth animation in Unreal

The user asked how plant growth should animate. Recommended approach, agreed in principle but **not started**:

1. **Stage meshes:** extend `build_plant.py` with an `age` parameter. Export 4–5 stages (seedling, vegetative, pre-flower, flowering, harvest) from the same seed so the plant keeps its shape between stages. Swap meshes at stage boundaries with a short scale or dissolve.
2. **Continuous growth inside a stage via the material (World Position Offset):** bake per-vertex data in Blender:
   - the growth order (0–1, when each part appears) into vertex color;
   - each part's attachment or pivot point into a spare UV channel (or use Pivot Painter 2).
   The material scales each part out from its pivot as a `Growth` parameter rises.
3. **Material-only stage changes:** pistils white → orange → brown, trichome frost clear → milky → amber, lower leaves yellowing, drooping when underwatered. Add wind in the same material.
4. **Gameplay:** a Blueprint turns game time, water and nutrients into an `Age` value. Use a dynamic material instance for single plants, and instanced meshes with **Custom Primitive Data** for grow rooms.
5. **Unreal pitfalls:** increase mesh bounds (WPO growth gets culled otherwise); test WPO cost with Nanite foliage early.

**Suggested first deliverable:** stage FBXs plus baked growth vertex data, and an Unreal material graph (written step by step) with a `Growth` slider to scrub in the editor.

## 8. Known limitations

- **Normal map convention** is OpenGL; Unreal needs Flip Green Channel.
- **No native alpha on standard tier:** Nano Banana cutouts are generated on black and keyed. Fine for leaves; use `hq` for hair, fur or lace.
- **Stem height glitch:** Nano Banana's stem height map has one rectangular glitch. Regenerate it, or use the GPT stem.
- **Texture resolution:** all textures are 1K. Use `--resolution 2K` (standard tier) or upscale every map in a set with the same upscaler.
- **Viewer packaging:** the web viewer splits the model into three JSON files only because artifact pages limit file size. Locally, use the GLB/FBX.
