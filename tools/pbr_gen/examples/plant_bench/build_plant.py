"""Procedural flowering cannabis plant -> plant.glb (meshes grouped by material: stem, leaf, bud, soil, pot).
UVs: tubes wrap u around / v along length (tileable), buds cylindrical, leaves 0-1 cards, soil planar."""
import math, sys
import numpy as np
import bpy

OUT = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else "plant.glb"
rng = np.random.default_rng(42)
TILE = 0.12           # meters per texture repeat on stems/buds/soil

geo = {k: {"v": [], "f": [], "uv": []} for k in ("stem", "leaf", "sugar", "bud", "pistil", "pistil_w", "soil", "pot")}


def add(group, verts, faces, uvs):
    """faces index into verts; uvs are per-vertex (u, v)."""
    g = geo[group]; base = len(g["v"])
    g["v"].extend(map(tuple, verts)); g["uv"].extend(map(tuple, uvs))
    g["f"].extend([tuple(i + base for i in f) for f in faces])


def frame(t):
    t = t / np.linalg.norm(t)
    a = np.array([0, 0, 1.0]) if abs(t[2]) < 0.9 else np.array([1.0, 0, 0])
    n = np.cross(t, a); n /= np.linalg.norm(n)
    return n, np.cross(t, n)


def tube(group, pts, radii, sides=10):
    pts = np.asarray(pts, float); n = len(pts)
    verts, uvs, faces = [], [], []
    seg = np.r_[0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
    prev_n = None
    for i, p in enumerate(pts):
        t = pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]
        nn, bb = frame(t)
        if prev_n is not None:                       # keep rings from twisting
            t_ = t / np.linalg.norm(t)
            nn = prev_n - t_ * np.dot(prev_n, t_); nn /= np.linalg.norm(nn); bb = np.cross(t_, nn)
        prev_n = nn
        for s in range(sides + 1):
            a = 2 * math.pi * s / sides
            verts.append(p + radii[i] * (math.cos(a) * nn + math.sin(a) * bb))
            uvs.append((s / sides, seg[i] / TILE))
    for i in range(n - 1):
        for s in range(sides):
            a = i * (sides + 1) + s; b = a + sides + 1
            faces.append((a, a + 1, b + 1, b))
    add(group, verts, faces, uvs)


def bezier(p0, p1, p2, steps=14):
    t = np.linspace(0, 1, steps)[:, None]
    return (1 - t) ** 2 * p0 + 2 * (1 - t) * t * p1 + t ** 2 * p2


NUG_TILE = 0.035      # bud texture repeat (m): calyx-scale detail on each nug
GOLDEN = math.pi * (3 - math.sqrt(5))


def nug(center, direction, size, ru=6, rv=5):
    """One calyx cluster: a teardrop pointing along `direction`, with small calyx bumps."""
    d = direction / np.linalg.norm(direction); nn, bb = frame(d)
    phase = rng.uniform(0, 2 * math.pi)
    verts, uvs, faces = [], [], []
    for j in range(rv + 1):
        v = j / rv                                   # 0 = base, 1 = tip
        prof = (math.sin(math.pi * min(1.0, v * 1.1)) ** 0.7) * (1 - 0.55 * v ** 1.5) + 0.02
        for i in range(ru + 1):
            a = 2 * math.pi * i / ru
            bump = 1 + 0.18 * math.sin(3 * a + phase) * math.sin(math.pi * v * 2.5)
            r = size * 0.62 * prof * bump
            verts.append(center + d * ((v - 0.35) * size * 1.5) + r * (math.cos(a) * nn + math.sin(a) * bb))
            uvs.append((i / ru * 2 * math.pi * size * 0.62 / NUG_TILE, v * size * 1.5 / NUG_TILE))
    for j in range(rv):
        for i in range(ru):
            a = j * (ru + 1) + i; b = a + ru + 1
            faces.append((a, a + 1, b + 1, b))
    add("bud", verts, faces, uvs)
    # pistils: thin curly orange hairs from the nug tip area
    for _ in range(rng.integers(2, 5)):
        root = center + d * size * 0.55 + (rng.normal(size=3) * size * 0.12)
        out = d + rng.normal(size=3) * 0.8; out /= np.linalg.norm(out)
        side = np.cross(out, rng.normal(size=3)); side /= np.linalg.norm(side)
        L = size * rng.uniform(1.0, 2.0)
        pts = bezier(root, root + out * L * 0.55 + side * L * 0.45, root + out * L * 0.8 - side * L * 0.35, 4)
        tube("pistil_w" if rng.random() < 0.55 else "pistil", pts, np.linspace(0.0006, 0.00025, 4), sides=3)


def bud(base, axis, length, radius):
    """Cola: a spine packed with calyx nugs in a phyllotaxis spiral, pistils and sugar leaves."""
    axis = axis / np.linalg.norm(axis); nn, bb = frame(axis)
    # thin core so gaps between nugs never show through
    core = [base + axis * (length * t) for t in np.linspace(0, 0.92, 8)]
    tube("bud", core, [radius * 0.55 * (1 - 0.6 * t) for t in np.linspace(0, 1, 8)], sides=8)
    n = int(18 + 4200 * length * radius)
    for k in range(n):
        v = (k + 0.5) / n
        v = v ** 0.85                                # a little denser toward the tip
        prof = math.sin(math.pi * min(1, v * 0.88 + 0.08)) ** 0.5 * (1 - 0.4 * v)
        v = min(0.97, max(0.0, v + rng.normal(0, 0.02)))
        a = k * GOLDEN + rng.normal(0, 0.35)
        out = math.cos(a) * nn + math.sin(a) * bb
        size = radius * rng.uniform(0.26, 0.5) * (0.5 + 0.5 * prof)
        center = base + axis * (v * length) + out * radius * prof * rng.uniform(0.45, 0.75)
        nug(center, out * 0.75 + axis * 0.85 + rng.normal(size=3) * 0.15, size)
    # crown nug on the tip
    nug(base + axis * length * 0.97, axis, radius * 0.55)
    # frosted sugar leaves curling out between the nugs (they dominate a real cola's look)
    for _ in range(int(10 + 210 * length * (radius / 0.04) ** 0.5)):
        v = rng.uniform(0.0, 0.95) ** 0.8; a = rng.uniform(0, 2 * math.pi)
        prof = math.sin(math.pi * min(1, v * 0.88 + 0.08)) ** 0.5 * (1 - 0.4 * v)
        out = math.cos(a) * nn + math.sin(a) * bb
        p = base + axis * (v * length) + out * radius * prof * 0.5
        leaf_card(p, out * rng.uniform(0.6, 1.2) + axis * rng.uniform(0.5, 1.1),
                  size=rng.uniform(0.03, 0.065) * (radius / 0.04) ** 0.6 * (0.6 + 0.4 * prof),
                  droop=rng.uniform(0.15, 0.45), roll=rng.uniform(-1.2, 1.2), res=2, group="sugar")


def leaf_card(base, direction, size, droop=0.35, roll=0.0, res=8, group="leaf"):
    """Fan-leaf card, texture bottom (petiole) at `base`, texture up along `direction`."""
    d = direction / np.linalg.norm(direction)
    side = np.cross(d, [0, 0, 1.0])
    if np.linalg.norm(side) < 1e-3:
        side = np.array([1.0, 0, 0])
    side /= np.linalg.norm(side)
    up = np.cross(side, d)
    c, s = math.cos(roll * 0.5), math.sin(roll * 0.5)
    side, up = side * c + up * s, up * c - side * s
    verts, uvs, faces = [], [], []
    for j in range(res + 1):
        v = j / res
        for i in range(res + 1):
            u = i / res; x = (u - 0.5) * size
            fold = abs(u - 0.5) * size * 0.18           # slight V-fold along the midrib
            sag = -droop * size * v * v                  # tips droop
            verts.append(base + d * (v * size) + side * x + up * (fold + sag))
            uvs.append((u, v))
    for j in range(res):
        for i in range(res):
            a = j * (res + 1) + i; b = a + res + 1
            faces.append((a, a + 1, b + 1, b))
    add(group, verts, faces, uvs)


def fan_leaf(node, az, size, lift=0.25):
    """Petiole + fan leaf, pointing outward at azimuth az."""
    out = np.array([math.cos(az), math.sin(az), 0.0])
    pet_len = size * 0.42
    p_end = node + out * pet_len + np.array([0, 0, pet_len * 0.45])
    tube("stem", bezier(node, node + out * pet_len * 0.4 + [0, 0, pet_len * 0.5], p_end, 6),
         np.linspace(0.0035, 0.002, 6), sides=6)
    leaf_card(p_end - out * size * 0.06, out + np.array([0, 0, lift]), size,
              droop=rng.uniform(0.3, 0.5), roll=rng.uniform(-0.25, 0.25))


# ---------------------------------------------------------------- pot + soil
H_POT, R_TOP, R_BOT = 0.27, 0.17, 0.13
ring = 48
pv, pf, pu = [], [], []
for k, (z, r) in enumerate([(0, R_BOT), (H_POT, R_TOP), (H_POT + 0.02, R_TOP + 0.012),
                            (H_POT + 0.02, R_TOP - 0.01), (H_POT - 0.02, R_TOP - 0.012)]):
    for i in range(ring + 1):
        a = 2 * math.pi * i / ring
        pv.append((r * math.cos(a), r * math.sin(a), z)); pu.append((i / ring, k / 4))
for k in range(4):
    for i in range(ring):
        a = k * (ring + 1) + i; b = a + ring + 1
        pf.append((a, a + 1, b + 1, b))
pv.append((0, 0, 0)); pu.append((0.5, 0.5))
pf += [(len(pv) - 1, i + 1, i) for i in range(ring)]
add("pot", pv, pf, pu)

sv, sf, su = [(0, 0, H_POT - 0.008)], [], [(0.5 / TILE * 0, 0)]
su = [(0, 0)]
for k in range(1, 9):
    r = (R_TOP - 0.012) * k / 8
    for i in range(ring):
        a = 2 * math.pi * i / ring
        z = H_POT - 0.012 + 0.012 * (1 - (k / 8) ** 2) + rng.normal(0, 0.002)
        sv.append((r * math.cos(a), r * math.sin(a), z)); su.append((r * math.cos(a) / TILE, r * math.sin(a) / TILE))
for i in range(ring):
    sf.append((0, 1 + i, 1 + (i + 1) % ring))
for k in range(1, 8):
    for i in range(ring):
        a = 1 + (k - 1) * ring + i; b = 1 + (k - 1) * ring + (i + 1) % ring
        sf.append((a, a + ring, b + ring, b))   # wound so the soil faces up
add("soil", sv, sf, su)

# ---------------------------------------------------------------- main stem
TOP = 1.32
zs = np.linspace(H_POT - 0.01, TOP, 40)
stem_pts = np.stack([0.012 * np.sin(zs * 7), 0.01 * np.cos(zs * 5), zs], axis=1)
tube("stem", stem_pts, np.linspace(0.017, 0.006, len(zs)), sides=12)


def stem_at(z):
    return np.array([0.012 * math.sin(z * 7), 0.01 * math.cos(z * 5), z])


# top cola
bud(stem_at(TOP - 0.1), np.array([0.02, 0.0, 1.0]), 0.36, 0.062)
for k in range(7):  # crown leaves around the top cola
    fan_leaf(stem_at(TOP - 0.12 - 0.03 * (k % 2)), k * 0.9 + 0.3, 0.22, lift=0.5)

# nodes and branches (Christmas-tree silhouette)
nodes = np.linspace(0.40, TOP - 0.18, 12)
for n_i, z in enumerate(nodes):
    t = (z - nodes[0]) / (nodes[-1] - nodes[0])
    base_az = n_i * (math.pi / 2 if n_i < 5 else 2.4)
    for side in (0, math.pi):
        az = base_az + side + rng.uniform(-0.2, 0.2)
        node = stem_at(z)
        L = 0.46 * (1 - 0.72 * t) + rng.uniform(-0.03, 0.03)
        out = np.array([math.cos(az), math.sin(az), 0.0])
        p0 = node
        p1 = node + out * L * 0.75 + np.array([0, 0, L * 0.25])
        p2 = node + out * L * 0.9 + np.array([0, 0, L * 0.95])
        pts = bezier(p0, p1, p2, 16)
        tube("stem", pts, np.linspace(0.008 * (1 - 0.4 * t), 0.0035, 16), sides=8)
        # branch cola at the tip, pointing up along the branch end
        tip_dir = pts[-1] - pts[-3]
        bud(pts[-3], tip_dir / np.linalg.norm(tip_dir) * 0.5 + np.array([0, 0, 0.5]),
            0.13 + 0.14 * (1 - t) + rng.uniform(-0.02, 0.02), 0.034 + 0.016 * (1 - t))
        # bud sites along the branch
        for frac in (0.35, 0.55, 0.75):
            q = pts[int(frac * 15)]
            bud(q, np.array([0, 0, 1.0]) + out * 0.25, rng.uniform(0.06, 0.09), rng.uniform(0.02, 0.026))
        # fan leaves: at the node, mid-branch and near the tip
        fan_leaf(node + out * 0.01, az + rng.uniform(0.5, 0.9), 0.40 * (1 - 0.45 * t) + rng.uniform(-0.03, 0.03))
        fan_leaf(node + out * 0.01, az - rng.uniform(0.6, 1.0), 0.34 * (1 - 0.45 * t), lift=0.4)
        fan_leaf(pts[7], az + rng.uniform(-1.0, -0.5), 0.30 * (1 - 0.4 * t))
        fan_leaf(pts[11], az + rng.uniform(0.5, 1.0), 0.24 * (1 - 0.3 * t), lift=0.45)

# ---------------------------------------------------------------- build Blender objects + export
bpy.ops.wm.read_factory_settings(use_empty=True)
colors = {"stem": (0.25, 0.4, 0.15, 1), "leaf": (0.1, 0.35, 0.08, 1), "bud": (0.5, 0.6, 0.35, 1), "pistil": (0.75, 0.32, 0.1, 1), "pistil_w": (0.9, 0.88, 0.8, 1), "sugar": (0.15, 0.4, 0.12, 1),
          "soil": (0.1, 0.08, 0.06, 1), "pot": (0.08, 0.08, 0.09, 1)}
for name, g in geo.items():
    me = bpy.data.meshes.new(name)
    me.from_pydata(g["v"], [], g["f"]); me.update()
    uv = me.uv_layers.new(name="UVMap")
    for loop in me.loops:
        uv.data[loop.index].uv = g["uv"][loop.vertex_index]
    for p in me.polygons:
        p.use_smooth = name != "pot" or True
    mat = bpy.data.materials.new(name); mat.use_nodes = True
    mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = colors[name]
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob)
    print(name, len(g["v"]), "verts", len(g["f"]), "faces")
# two files so each stays small enough to serve: the plant body, and the flower detail
PARTS = {"": ("stem", "leaf", "soil", "pot"), "_buds": ("bud", "sugar"), "_hairs": ("pistil", "pistil_w")}
for suffix, names in PARTS.items():
    for ob in bpy.data.objects:
        ob.select_set(ob.name in names)
    path = OUT.replace(".glb", f"{suffix}.glb")
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", export_apply=True, export_yup=True,
                              use_selection=True, export_normals=False)  # viewer recomputes normals
    print("exported", path)
