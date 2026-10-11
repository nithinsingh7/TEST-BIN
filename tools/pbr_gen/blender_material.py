"""
Build a Blender material from a pbr_gen output folder.

Inside a running Blender (e.g. from an agent's Python):
    import sys; sys.path.append("/path/to/tools/pbr_gen")
    import blender_material as bm
    mat = bm.build_material("/path/to/tex/leaf")
    bm.assign(bpy.data.objects["Leaf"], mat)
    card = bm.make_card(mat)            # cutouts: a 1x1 card with the stem/base at the origin

Command line (background):
    blender --background --python blender_material.py -- tex/leaf [--object Leaf] [--card]
            [--tile-scale 2] [--displacement 0.02] [--normal model|height] [--save out.blend]

Prints one JSON line: {"ok": true, "material": "...", "object": "..."}.
Works with Blender 3.6 - 5.x (node and setting names are looked up defensively).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy


def _inp(node, *names):
    for n in names:
        if n in node.inputs:
            return node.inputs[n]
    raise KeyError(f"{node.bl_idname} has none of {names}")


def build_material(folder, name: str | None = None, *, normal: str = "height",
                   displacement: float = 0.02, tile_scale: float = 1.0,
                   translucency: float = 0.35, use_ao: bool = False):
    """Create (or rebuild) a material from the maps in `folder`.

    normal       : "height" uses normal_from_height.png (consistent, recommended),
                   "model" uses the AI-generated normal.png. Falls back to whichever exists.
    displacement : Displacement node scale in meters (0 disables). Needs Cycles + subdivided mesh
                   to show real displacement; otherwise it acts as bump.
    tile_scale   : UV repeat for tileable materials.
    translucency : mix of light passing through (cutouts with a translucency map).
    use_ao       : multiply AO into base color (Cycles/EEVEE already compute AO, so off by default).
    """
    folder = Path(folder).resolve()
    manifest = {}
    if (folder / "manifest.json").exists():
        manifest = json.loads((folder / "manifest.json").read_text())
    kind = manifest.get("kind", "cutout" if (folder / "opacity.png").exists() else "tileable")

    def f(n):
        p = folder / f"{n}.png"
        return p if p.exists() else None

    if not f("albedo"):
        raise FileNotFoundError(f"{folder} has no albedo.png")

    name = name or f"PBR_{folder.name}"
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    nodes.clear()

    out = nodes.new("ShaderNodeOutputMaterial"); out.location = (900, 0)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (300, 0)
    coord = nodes.new("ShaderNodeTexCoord"); coord.location = (-1100, 0)
    mapping = nodes.new("ShaderNodeMapping"); mapping.location = (-900, 0)
    links.new(coord.outputs["UV"], mapping.inputs["Vector"])
    if kind == "tileable":
        mapping.inputs["Scale"].default_value = (tile_scale, tile_scale, 1)

    row = [300]

    def tex(path, color: bool, label: str):
        img = bpy.data.images.load(str(path), check_existing=True)
        img.colorspace_settings.name = "sRGB" if color else "Non-Color"
        node = nodes.new("ShaderNodeTexImage")
        node.image, node.label = img, label
        node.location = (-600, row[0]); row[0] -= 280
        if kind == "cutout":
            node.extension = "CLIP"
        links.new(mapping.outputs["Vector"], node.inputs["Vector"])
        return node

    # base color (+ optional AO)
    alb = tex(f("albedo"), True, "Albedo")
    ao_path = f("ao") or f("ao_from_height")
    if use_ao and ao_path:
        ao = tex(ao_path, False, "AO")
        mix = nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"; mix.blend_type = "MULTIPLY"
        mix.location = (-200, 300)
        mix.inputs["Factor"].default_value = 1.0
        links.new(alb.outputs["Color"], mix.inputs[6])
        links.new(ao.outputs["Color"], mix.inputs[7])
        links.new(mix.outputs[2], _inp(bsdf, "Base Color"))
    else:
        links.new(alb.outputs["Color"], _inp(bsdf, "Base Color"))

    if f("roughness"):
        links.new(tex(f("roughness"), False, "Roughness").outputs["Color"], _inp(bsdf, "Roughness"))
    if f("metallic"):
        links.new(tex(f("metallic"), False, "Metallic").outputs["Color"], _inp(bsdf, "Metallic"))
    else:
        _inp(bsdf, "Metallic").default_value = 0.0

    order = ["normal_from_height", "normal"] if normal == "height" else ["normal", "normal_from_height"]
    npath = next((f(n) for n in order if f(n)), None)
    if npath:
        nmap = nodes.new("ShaderNodeNormalMap"); nmap.location = (0, -400)
        links.new(tex(npath, False, "Normal").outputs["Color"], nmap.inputs["Color"])
        links.new(nmap.outputs["Normal"], _inp(bsdf, "Normal"))

    if f("height") and displacement > 0:
        disp = nodes.new("ShaderNodeDisplacement"); disp.location = (600, -400)
        disp.inputs["Scale"].default_value = displacement
        disp.inputs["Midlevel"].default_value = 0.5
        links.new(tex(f("height"), False, "Height").outputs["Color"], disp.inputs["Height"])
        links.new(disp.outputs["Displacement"], out.inputs["Displacement"])
        for owner in (mat, getattr(mat, "cycles", None)):
            if owner is not None and hasattr(owner, "displacement_method"):
                owner.displacement_method = "BOTH"
                break

    surface = bsdf.outputs["BSDF"]
    if kind == "cutout" and f("translucency") and translucency > 0:
        tr = nodes.new("ShaderNodeBsdfTranslucent"); tr.location = (300, -650)
        links.new(tex(f("translucency"), True, "Translucency").outputs["Color"], tr.inputs["Color"])
        mix = nodes.new("ShaderNodeMixShader"); mix.location = (550, -100)
        mix.inputs["Fac"].default_value = translucency
        links.new(surface, mix.inputs[1]); links.new(tr.outputs["BSDF"], mix.inputs[2])
        surface = mix.outputs["Shader"]

    if kind == "cutout" and f("opacity"):
        op = tex(f("opacity"), False, "Opacity")
        transp = nodes.new("ShaderNodeBsdfTransparent"); transp.location = (550, 200)
        cut = nodes.new("ShaderNodeMixShader"); cut.location = (720, 50)
        links.new(op.outputs["Color"], cut.inputs["Fac"])
        links.new(transp.outputs["BSDF"], cut.inputs[1]); links.new(surface, cut.inputs[2])
        surface = cut.outputs["Shader"]
        # EEVEE settings (names differ across versions)
        for attr, val in (("surface_render_method", "DITHERED"), ("blend_method", "CLIP"),
                          ("shadow_method", "CLIP")):
            if hasattr(mat, attr):
                try:
                    setattr(mat, attr, val)
                except TypeError:
                    pass
        mat.use_backface_culling = False

    links.new(surface, out.inputs["Surface"])
    mat["pbr_gen_folder"] = str(folder)
    mat["pbr_gen_kind"] = kind
    return mat


def assign(obj, mat) -> None:
    """Make `mat` the only material on `obj`."""
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def make_card(mat, size: float = 1.0, name: str | None = None):
    """A square card for a cutout, with the bottom edge (stem/base) at the origin, facing +Y."""
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0, 0, 0))
    obj = bpy.context.active_object
    obj.name = name or mat.name.replace("PBR_", "") + "_card"
    for v in obj.data.vertices:          # stand it up and move the base to the origin
        x, y, _ = v.co
        v.co = (x, 0.0, y + size / 2)
    assign(obj, mat)
    return obj


def _cli(argv) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="blender_material.py")
    ap.add_argument("folder")
    ap.add_argument("--name")
    ap.add_argument("--object", help="assign to this existing object")
    ap.add_argument("--card", action="store_true", help="create a card mesh for a cutout")
    ap.add_argument("--normal", choices=["height", "model"], default="height")
    ap.add_argument("--displacement", type=float, default=0.02)
    ap.add_argument("--tile-scale", type=float, default=1.0)
    ap.add_argument("--translucency", type=float, default=0.35)
    ap.add_argument("--ao", action="store_true", help="multiply AO into base color")
    ap.add_argument("--save", help="save the .blend here")
    a = ap.parse_args(argv)
    res = {"ok": True}
    try:
        mat = build_material(a.folder, a.name, normal=a.normal, displacement=a.displacement,
                             tile_scale=a.tile_scale, translucency=a.translucency, use_ao=a.ao)
        res["material"] = mat.name
        if a.object:
            assign(bpy.data.objects[a.object], mat); res["object"] = a.object
        if a.card:
            res["object"] = make_card(mat).name
        if a.save:
            bpy.ops.wm.save_as_mainfile(filepath=str(Path(a.save).resolve())); res["saved"] = a.save
    except Exception as e:  # report to the calling agent instead of a traceback dump
        res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    print(json.dumps(res))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    code = _cli(argv)
    if bpy.app.background:
        sys.exit(code)
