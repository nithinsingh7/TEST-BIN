# pbr_gen

Generates pixel-aligned PBR texture sets with `openai/gpt-image-2.5-sunburst` through
OpenRouter's Image API (`POST /api/v1/images`), and builds Blender materials from them.
Designed to be driven by an agent: one command, one JSON line back.

```bash
pip install -r requirements.txt
export OPENROUTER_API_KEY=sk-or-...     # never commit the key; read it from the environment
```

## For agents: the two calls

```bash
# 1. make the textures (progress on stderr, one JSON result line on stdout)
python pbr_gen.py all --kind cutout   --subject "a fresh green hydrangea leaf" --out tex/leaf --json
python pbr_gen.py all --kind tileable --subject "weathered oak bark" --out tex/bark --json
python pbr_gen.py all --kind tileable --subject "rusty painted steel plate" \
    --maps height,normal,roughness,ao,metallic \
    --notes "bare steel shows where the paint is chipped" --out tex/steel --json

# 2. build the Blender material (and optionally assign it / make a leaf card)
blender --background --python blender_material.py -- tex/leaf --card --save leaf.blend
blender --background --python blender_material.py -- tex/bark --object Trunk --tile-scale 3 --save scene.blend
```

Or from Python inside a running Blender:

```python
import sys; sys.path.append("/abs/path/tools/pbr_gen")
import blender_material as bm
mat = bm.build_material("/abs/path/tex/bark", tile_scale=3)
bm.assign(bpy.data.objects["Trunk"], mat)
```

`pbr_gen.py --json` result:

```json
{"ok": true, "error": null, "kind": "cutout", "out": "/abs/tex/leaf",
 "files": {"albedo": "...", "opacity": "...", "normal_from_height": "...", ...},
 "warnings": [], "cost_usd": 0.31,
 "blender": "blender --background --python /abs/.../blender_material.py -- \"/abs/tex/leaf\""}
```

Exit code 0 = success, 2 = API/input error (see `error`). Check `warnings` for maps that
didn't line up well.

### Choosing options

| Option | Use |
|---|---|
| `--kind cutout` | One isolated object on alpha: leaves, petals, feathers, decals, foliage cards. Gets `opacity.png`. |
| `--kind tileable` | Seamless surfaces: bark, brick, ground, fabric, metal, plaster. |
| `--maps` | Default cutout: `height,normal,roughness,ao,translucency`. Default tileable: `height,normal,roughness,ao`. Add `metallic` for anything with bare metal. |
| `--notes` | Material facts added to every prompt ("polished brass with dirty crevices"). |
| `--quality` | Derived maps. `medium` while iterating, `high` (default) for final. Albedo uses `--albedo-quality max`. |
| `--albedo` | Start from an existing image instead of generating one. |

Typical cost: about $0.05 per image at `high` quality and 1024 px, so roughly $0.30 for a full set.

## Output files

| File | Blender color space | Notes |
|---|---|---|
| `albedo.png` | sRGB | Cutout: colors padded past the edge (no halos). Tileable: seamless. |
| `opacity.png`, `albedo_rgba.png` | Non-Color | Cutout only |
| `normal_from_height.png` | Non-Color | OpenGL normal computed from height. Default in Blender. |
| `normal.png` | Non-Color | AI-generated normal, re-normalized |
| `height.png`, `roughness.png`, `ao.png`, `ao_from_height.png`, `metallic.png` | Non-Color | |
| `translucency.png` | sRGB | Cutout foliage |
| `orm_packed.png` | Non-Color | R=AO, G=roughness, B=metallic (Unreal/glTF) |
| `*_raw.png`, `reference.png` | | Untouched model output / what the model was shown |
| `manifest.json` | | kind, prompts, alignment scores, files, cost |

## How alignment is enforced

1. Every map is generated from the same reference image, never from another generated map.
2. Cutouts: each map is resized, scaled and shifted to the albedo's silhouette, and regenerated if
   the shape still doesn't match (`--min-iou`, `--retries`). Background pixels get neutral values.
3. Tileables: the albedo and every map get the same offset-and-blend, so they are seamless and still
   line up with each other.
4. Normal and AO are also computed from the height map, so there's always an aligned fallback.

## Limits

- OpenRouter accepts only `aspect_ratio`, `quality`, `background`, `n`, `input_references` and
  `output_compression` for this model, so output is about 1024 px. There is no size/4K option there.
  Upscale every map with the same upscaler, or call OpenAI's API directly for 3840 px.
- Real displacement in Blender needs Cycles and a subdivided mesh; otherwise height acts as bump.
