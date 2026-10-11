# pbr_gen

Generates a pixel-aligned PBR texture set (albedo, opacity, height, normal, roughness, AO,
translucency) with `openai/gpt-image-2.5-sunburst` through OpenRouter's Image API
(`POST /api/v1/images`).

```bash
pip install -r requirements.txt
export OPENROUTER_API_KEY=sk-or-...

# 1. albedo with a transparent background, cleaned up locally
python pbr_gen.py albedo --subject "a fresh green hydrangea leaf" --out out/leaf
# (optional) fix out/leaf/albedo_rgba.png by hand, then pass it back with --albedo

# 2. every other map, generated from the cleaned albedo as the reference image
python pbr_gen.py maps --out out/leaf
python pbr_gen.py maps --albedo my_fixed_leaf.png --out out/leaf

# or both steps at once
python pbr_gen.py all --subject "a fresh green hydrangea leaf" --out out/leaf
```

## Output

| File | What it is |
|---|---|
| `albedo.png` | Color, with leaf colors padded out past the edge (stops halos in mipmaps) |
| `albedo_rgba.png` | Same with the opacity mask in its alpha channel |
| `opacity.png` | Cut-out mask from the model's alpha, cleaned (specks removed, holes filled, 1 px edge trim) |
| `height.png`, `roughness.png`, `ao.png` | Grayscale maps from the model, re-fitted to the albedo |
| `normal.png` | Normal map from the model, re-normalized, OpenGL (Y+) |
| `normal_from_height.png` | Normal computed locally from `height.png`. Always aligned and physically consistent |
| `ao_from_height.png` | AO computed locally from `height.png` |
| `translucency.png` | Backlit color for subsurface / two-sided foliage shading |
| `orm_packed.png` | R = AO, G = roughness, B = metallic (0) |
| `*_raw.png` | Untouched model output, for comparison |
| `manifest.json` | Prompts, cost and alignment score per map |

## How alignment is enforced

1. Every map gets the same reference: the cleaned albedo on pure black. Maps are never generated
   from other generated maps, so errors don't pile up.
2. Each result is resized to the albedo, then scaled and shifted so the object's bounding box
   matches the albedo's.
3. Its silhouette is compared with the opacity mask. Below `--min-iou` (default 0.93) the map is
   generated again (`--retries`, default 1) and the best attempt is kept.
4. Pixels outside the mask are set to each map's neutral value (normal 128,128,255; height 0; roughness 1; AO 1).

## Limits

- OpenRouter's endpoint for this model only accepts `aspect_ratio`, `quality`, `background`, `n`,
  `input_references` and `output_compression`. It does not accept `size`/`resolution`, so you
  can't request 3840 px through OpenRouter. Upscale every map with the same upscaler, or call
  OpenAI's API directly for 4K.
- Masks/inpainting aren't exposed on OpenRouter for this model.
- Metallic isn't generated; for organic materials it is 0.
