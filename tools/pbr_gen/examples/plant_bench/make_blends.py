import sys, math, bpy
K = sys.argv[1]
sys.path.insert(0, K + "/scripts/pbr_gen"); import blender_material as bm
NAMES = {"gpt": "GPT Image 2.5 Sunburst", "gemini": "Nano Banana 2.1", "flux": "FLUX 3", "qwen": "Qwen Image 3 Pro"}

def base_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for part in ("plant_body", "plant_buds", "plant_pistils"):
        bpy.ops.import_scene.gltf(filepath=f"{K}/models/{part}.glb")
    for ob in bpy.data.objects:
        if ob.type == "MESH":
            for p in ob.data.polygons:
                p.use_smooth = True
    # camera, lights, world
    cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera")); bpy.context.scene.collection.objects.link(cam)
    cam.data.lens = 35; cam.location = (1.45, -1.45, 1.1); cam.rotation_euler = (math.radians(84), 0, math.radians(45))
    bpy.context.scene.camera = cam
    for name, rot, e, col in (("Key", (40, 0, 30), 4.0, (1, .95, .88)), ("Fill", (60, 0, 220), 1.2, (.85, .9, 1)), ("Rim", (65, 0, 160), 2.5, (1, .9, .75))):
        l = bpy.data.objects.new(name, bpy.data.lights.new(name, "SUN")); l.data.energy = e; l.data.color = col
        l.rotation_euler = tuple(math.radians(a) for a in rot); bpy.context.scene.collection.objects.link(l)
    w = bpy.data.worlds.new("World"); w.color = (0.35, 0.37, 0.4); bpy.context.scene.world = w
    sc = bpy.context.scene; sc.render.engine = "CYCLES"; sc.cycles.samples = 128

def materials(m):
    mats = {k: bm.build_material(f"{K}/textures/{m}/{k}", name=f"{k}", displacement=0) for k in ("leaf", "sugar", "bud", "stem", "soil")}
    simple = {"pistil": (0.7, 0.3, 0.1, 1), "pistil_w": (0.85, 0.72, 0.52, 1), "pot": (0.02, 0.02, 0.025, 1)}
    for k in simple:                              # free the glTF placeholder names first
        if k in bpy.data.materials:
            bpy.data.materials[k].name = k + "_import"
    for k, c in simple.items():
        mt = bpy.data.materials.new(k); mt.use_nodes = True
        b = mt.node_tree.nodes["Principled BSDF"]; b.inputs["Base Color"].default_value = c
        b.inputs["Roughness"].default_value = 0.55; mats[k] = mt
    for ob in bpy.data.objects:
        if ob.type == "MESH":
            key = ob.data.materials[0].name.split(".")[0].replace("_import", "") if ob.data.materials else ob.name
            if key in mats:
                bm.assign(ob, mats[key])
    for mt in list(bpy.data.materials):          # drop the placeholder materials from the glTF import
        if mt.users == 0:
            bpy.data.materials.remove(mt)

for m in ("gpt", "gemini", "flux", "qwen"):
    base_scene(); materials(m)
    bpy.context.scene["texture_model"] = NAMES[m]
    bpy.ops.wm.save_as_mainfile(filepath=f"{K}/blender/plant_{m}.blend", relative_remap=True)
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_mainfile()
    print("saved", m)

# FBX for Unreal: geometry + material slots (textures assigned in Unreal)
base_scene(); materials("gemini")
for ob in bpy.data.objects: ob.select_set(ob.type == "MESH")
bpy.ops.export_scene.fbx(filepath=f"{K}/models/plant.fbx", use_selection=True, object_types={"MESH"},
                         mesh_smooth_type="FACE", path_mode="STRIP", embed_textures=False, axis_forward="-Y", axis_up="Z")
print("fbx ok")
