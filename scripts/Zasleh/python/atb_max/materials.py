"""Textures of 3ds Max materials: Arma paths, .rvmat files, deploy; the material manager's checks"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import List, Tuple

import pymxs

from atb_p3d import rvmat

from .scene import PREVIEW_EXTENSIONS, define_maxscript, to_bits

rt = pymxs.runtime
SUFFIXES = ("_co", "_ca", "_dt", "_lco", "_nopx")
OK, WARN, BAD = "ok", "warn", "bad"

def _prop(obj, name: str):
    if obj is None or not rt.isProperty(obj, rt.Name(name)):
        return None
    return rt.getProperty(obj, rt.Name(name))


def bitmap_node(tex_map):
    """The Bitmaptexture behind a map, through Normal Bump, Color Correction and the like"""
    for _depth in range(8):
        if tex_map is None:
            return None
        if rt.classOf(tex_map) == rt.Bitmaptexture:
            return tex_map
        tex_map = _prop(tex_map, "normal_map") or _prop(tex_map, "map")
    return None


def map_file(tex_map) -> str:
    node = bitmap_node(tex_map)
    name = _prop(node, "filename") if node is not None else _prop(tex_map, "filename")
    return str(name) if name else ""


def _first(material, names) -> object:
    for name in names:
        found = _prop(material, name)
        if found is not None:
            return found
    return None


def diffuse_map(material):
    if material is None:
        return None
    if rt.classOf(material) == rt.Standardmaterial:
        return material.diffuseMap
    return _first(material, ("base_color_map", "diffuseMap"))


def normal_map(material):
    if material is None:
        return None
    if rt.classOf(material) == rt.Standardmaterial:
        return material.bumpMap
    return _first(material, ("bump_map", "norm_map", "bumpMap"))


def specular_map(material):
    if material is None:
        return None
    if rt.classOf(material) == rt.Standardmaterial:
        return material.specularMap
    if rt.classOf(material) == rt.PhysicalMaterial:
        return _prop(material, "roughness_map")
    return _prop(material, "specularMap")


def sub_material(material, material_id: int):
    """The material a face id refers to (Multi/Sub-Object ids may have gaps and wrap around)"""
    if material is None or rt.classOf(material) != rt.Multimaterial:
        return material
    subs = list(material.materialList)
    if not subs:
        return None
    ids = [int(i) for i in material.materialIDList]
    if material_id in ids:
        return subs[ids.index(material_id)]
    wrapped = (material_id - 1) % len(subs) + 1
    return subs[ids.index(wrapped)] if wrapped in ids else subs[wrapped - 1]


def arma_attributes(material):
    """(texture, rvmat) of a material imported from a p3d, None for any other"""
    if material is None:
        return None
    definition = rt.execute("try (atbArmaMaterialCA) catch (undefined)")
    if definition is None:
        return None
    attributes = rt.custAttributes.get(material, definition)
    return None if attributes is None else (str(attributes.texture), str(attributes.rvmat))


def arma_path(full: str, convert_paa: bool, tex_root: str) -> str:
    """A path as Arma wants it: relative to the texture root, backslashes, .paa if asked"""
    if not full:
        return ""
    path = full.replace("/", "\\")
    if tex_root:
        root = tex_root.replace("/", "\\").rstrip("\\") + "\\"
        if path.lower().startswith(root.lower()):
            path = path[len(root):]
    if convert_paa:
        base, extension = os.path.splitext(path)
        if extension:
            path = base + ".paa"
    return path


def strip_suffix(base: str) -> str:
    for suffix in SUFFIXES:
        if base.lower().endswith(suffix):
            return base[:-len(suffix)]
    return base


def _stem(colour: str) -> str:
    """A colour map's full path w/o suffix and extension: its other maps and its .rvmat are named after it"""
    colour = colour.replace("/", "\\")
    return os.path.dirname(colour) + "\\" + strip_suffix(os.path.splitext(os.path.basename(colour))[0])


def neighbour(colour: str, suffix: str) -> str:
    """The map lying next to a colour map (X_nohq.* for X_co.*); a picture 3ds Max opens, if there is one"""
    if not colour:
        return ""
    stem = _stem(colour)
    for extension in PREVIEW_EXTENSIONS + (".paa",):
        if os.path.isfile(stem + suffix + extension):
            return stem + suffix + extension
    return ""


def _run(arguments: List[str], folder: str) -> bool:
    try:
        subprocess.run(arguments, cwd=folder or None, creationflags=0x08000000, timeout=300,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


class TexturePlan:
    """What an export does about the textures of ordinary materials, and what it owes afterwards"""

    def __init__(self, convert_paa=True, tex_root="", gen_rvmat=False, deploy=False, deploy_folder="",
                 image_to_paa="", tex_conv="", preset=rvmat.DEFAULT):
        self.convert_paa, self.tex_root = convert_paa, tex_root or ""
        self.gen_rvmat, self.deploy = gen_rvmat, deploy
        self.preset = preset if preset in rvmat.PRESETS else rvmat.DEFAULT
        self.kept = 0                                       # .rvmat files that were there already
        self.deploy_folder = deploy_folder.rstrip("\\/") + "\\" if deploy_folder else ""
        self.image_to_paa, self.tex_conv = image_to_paa or "", tex_conv or ""
        self.queue: List[Tuple[str, str, bool]] = []        # (source, target, is the colour map)
        self.used: list = []                                # materials that get an .rvmat
        self.notes: List[str] = []

    def resolve(self, source: str, fallback: str, diffuse: bool) -> str:
        use = source or fallback
        if not use:
            return ""
        if not self.deploy:
            return arma_path(use, self.convert_paa, self.tex_root)
        name = os.path.basename(use.replace("/", "\\"))
        if self.convert_paa:
            base, extension = os.path.splitext(name)
            if extension:
                name = base + ".paa"
        target = self.deploy_folder + name
        if not any(queued[1].lower() == target.lower() for queued in self.queue):
            self.queue.append((source, target, diffuse))
        return arma_path(target, self.convert_paa, self.tex_root)

    def face_texture(self, material) -> str:
        return self.resolve(map_file(diffuse_map(material)), "", True)

    def rvmat_file(self, material) -> str:
        """Full path of the .rvmat of a material: next to its colour map, or in the deploy folder"""
        diffuse = map_file(diffuse_map(material)).replace("/", "\\")
        if not diffuse:
            return ""
        return (self.deploy_folder + os.path.basename(_stem(diffuse)) if self.deploy else _stem(diffuse)) + ".rvmat"

    def face_rvmat(self, material) -> str:
        if not self.gen_rvmat:
            return ""
        full = self.rvmat_file(material)
        if full and not any(material == used for used in self.used):
            self.used.append(material)
        return arma_path(full, False, self.tex_root)

    def write_rvmats(self, replace: bool = False) -> int:
        """An .rvmat that is there already stays as it is (it may have been edited by hand), unless told to replace"""
        written = self.kept = 0
        for material in self.used:
            target = self.rvmat_file(material)
            diffuse = map_file(diffuse_map(material))
            maps = {}
            for kind in rvmat.MAPS[self.preset]:
                lookup, suffix, expected = _MAPS[kind]
                source = (map_file(lookup(material)) if lookup else "") or neighbour(diffuse, suffix)
                # a normal or specular map nobody made yet is named all the same: the user supplies it
                maps[kind] = self.resolve(source, _stem(diffuse) + suffix + ".paa" if expected else "", False)
            if os.path.isfile(target) and not replace:
                self.kept += 1
                continue
            try:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, "w", encoding="utf-8", newline="\r\n") as stream:
                    stream.write(rvmat.text(self.preset, **maps))
                written += 1
            except OSError as error:
                self.notes.append("%s not written: %s" % (target, error))
        return written

    def run_deploy(self) -> dict:
        """Copy or convert what was queued. A file that is there already is never replaced."""
        counts = {"converted": 0, "copied": 0, "kept": 0, "by_hand": 0, "failed": 0}
        have_paa = bool(self.image_to_paa) and os.path.isfile(self.image_to_paa)
        have_conv = bool(self.tex_conv) and os.path.isfile(self.tex_conv)
        for source, target, _diffuse in self.queue:
            folder = os.path.dirname(target)
            try:
                os.makedirs(folder, exist_ok=True)
            except OSError:
                pass
            if os.path.isfile(target):
                counts["kept"] += 1
            elif not source or not os.path.isfile(source):
                counts["by_hand"] += 1
            else:
                extension = os.path.splitext(source)[1].lower()
                needs_paa = self.convert_paa and extension != ".paa"
                if needs_paa and not have_paa:
                    counts["failed"] += 1
                    self.notes.append("%s not deployed: set ImageToPAA.exe to convert it to .paa" % os.path.basename(source))
                elif needs_paa and extension == ".dds" and have_conv:
                    tmp = os.path.join(folder, "__atb_tmp")
                    os.makedirs(tmp, exist_ok=True)
                    tga = os.path.join(tmp, os.path.splitext(os.path.basename(source))[0] + ".tga")
                    _run([self.tex_conv, "-nologo", "-y", "-ft", "tga", "-f", "R8G8B8A8_UNORM", "-o", tmp, source],
                         os.path.dirname(self.tex_conv))
                    if os.path.isfile(tga):
                        _run([self.image_to_paa, tga, target], os.path.dirname(self.image_to_paa))
                    shutil.rmtree(tmp, ignore_errors=True)
                    counts["converted" if os.path.isfile(target) else "failed"] += 1
                elif needs_paa:
                    _run([self.image_to_paa, source, target], os.path.dirname(self.image_to_paa))
                    counts["converted" if os.path.isfile(target) else "failed"] += 1
                else:
                    try:
                        shutil.copyfile(source, target)
                        counts["copied"] += 1
                    except OSError:
                        counts["failed"] += 1
        return counts


_MAPS = {"normal": (normal_map, "_nohq", True), "specular": (specular_map, "_smdi", True), "detail": (None, "_dt", False)}


# -- texture and rvmat of faces

def _pair(material, tex_root: str) -> Tuple[str, str]:
    """(texture, rvmat) a face with this material gets in the p3d"""
    if material is None:
        return ("", "")
    return arma_attributes(material) or (TexturePlan(True, tex_root).face_texture(material), "")


def _face_ids(node, faces) -> List[int]:
    get = rt.polyop.getFaceMatID
    return [int(get(node, face)) for face in faces]


def of_faces(node, faces, tex_root: str) -> List[Tuple[str, str, int]]:
    """(texture, rvmat, number of faces) for the given faces, the most used first"""
    counts: dict = {}
    for material_id in _face_ids(node, faces):
        counts[material_id] = counts.get(material_id, 0) + 1
    pairs: dict = {}
    for material_id, count in counts.items():
        pair = _pair(sub_material(node.material, material_id), tex_root)
        pairs[pair] = pairs.get(pair, 0) + count
    return sorted(((texture, path, count) for (texture, path), count in pairs.items()), key=lambda row: -row[2])


def put_on_faces(node, faces, texture: str, rvmat_path: str, make) -> int:
    """Give faces a texture and an .rvmat: they get the id of the sub-material that stands for the pair,
    made with make(texture, rvmat) if there is none yet. Gives the id."""
    faces = list(faces)
    count = int(rt.polyop.getNumFaces(node))
    everything = list(range(1, count + 1))
    material = node.material
    if material is None or rt.classOf(material) != rt.Multimaterial:
        # one material for all faces so far: it becomes id 1, whatever ids the faces had
        multi = rt.Multimaterial(numsubs=1, name=str(node.name))
        multi.materialList[0] = material if material is not None else make("", "")
        rt.polyop.setFaceMatID(node, to_bits(everything), 1)
        node.material = material = multi
    ids = [int(i) for i in material.materialIDList]
    # ids the list doesn't have wrap around it; they would point elsewhere once the list grows
    stray = [(face, i) for face, i in zip(everything, _face_ids(node, everything)) if i not in ids]
    for face, material_id in stray:
        wrapped = (material_id - 1) % len(ids) + 1
        rt.polyop.setFaceMatID(node, to_bits([face]), wrapped if wrapped in ids else ids[wrapped - 1])
    found = next((i for i, sub in zip(ids, material.materialList)
                  if sub is not None and arma_attributes(sub) == (texture, rvmat_path)), None)
    if found is None:
        found = max(ids) + 1
        material.numsubs = len(ids) + 1
        made = make(texture, rvmat_path)
        material.materialList[len(ids)] = made
        material.materialIDList[len(ids)] = found
        material.names[len(ids)] = str(made.name)
    if faces:
        rt.polyop.setFaceMatID(node, to_bits(faces), found)
    return found


# -- the material manager

def _leaves(material, into: list) -> None:
    if material is None:
        return
    if rt.classOf(material) == rt.Multimaterial:
        for sub in material.materialList:
            _leaves(sub, into)
    elif not any(material == seen for seen in into):
        into.append(material)


def scene_materials(selected_only: bool = False) -> list:
    """The materials geometry really uses, sub-materials taken apart"""
    found: list = []
    for node in (rt.selection if selected_only else rt.objects):
        if rt.superClassOf(node) == rt.GeometryClass:
            _leaves(node.material, found)
    return found


def describe(material, tex_root: str) -> dict:
    """A row of the manager: what the material has and what is wrong with it"""
    kind = {rt.Standardmaterial: "Standard", rt.PhysicalMaterial: "Physical"}.get(rt.classOf(material), str(rt.classOf(material)))
    arma = arma_attributes(material)
    diffuse = map_file(diffuse_map(material))

    def mark(lookup, suffix: str) -> str:       # Y: in the material, f: a file next to the colour map
        return "Y" if map_file(lookup(material)) else "f" if neighbour(diffuse, suffix) else ""

    row = {"name": str(material.name), "type": kind, "diffuse": diffuse, "arma": arma,
           "normal": mark(normal_map, "_nohq"), "specular": mark(specular_map, "_smdi")}
    if arma is not None:
        row.update(type="Arma", diffuse=arma[0] or diffuse, status="paths set", level=OK)
    elif not diffuse:
        row.update(status="no _co", level=BAD)
    elif not os.path.isfile(diffuse):
        row.update(status="file missing", level=BAD)
    elif tex_root and not diffuse.lower().replace("/", "\\").startswith(tex_root.lower().replace("/", "\\")):
        row.update(status="outside root", level=WARN)
    elif not (row["normal"] and row["specular"]):
        row.update(status="no nohq/smdi", level=WARN)
    else:
        row.update(status="OK", level=OK)
    return row


def derived(material, tex_root: str) -> Tuple[str, str]:
    """(texture, rvmat) an export would work out from the maps of a material"""
    plan = TexturePlan(True, tex_root, gen_rvmat=True)
    return plan.face_texture(material), plan.face_rvmat(material)


def set_arma(material, texture: str, rvmat_path: str) -> None:
    """Paths that go into the p3d as they are, whatever maps the material has"""
    define_maxscript()
    if rt.custAttributes.get(material, rt.atbArmaMaterialCA) is None:
        rt.custAttributes.add(material, rt.atbArmaMaterialCA)
    attributes = rt.custAttributes.get(material, rt.atbArmaMaterialCA)
    attributes.texture = texture
    attributes.rvmat = rvmat_path


def clear_arma(material) -> bool:
    define_maxscript()
    if rt.custAttributes.get(material, rt.atbArmaMaterialCA) is None:
        return False
    rt.custAttributes.delete(material, rt.atbArmaMaterialCA)
    return True


def _put(material, kind: str, path: str) -> bool:
    bitmap = rt.Bitmaptexture(filename=path, name=os.path.splitext(os.path.basename(path))[0])
    standard = rt.classOf(material) == rt.Standardmaterial
    try:
        if kind == "normal":
            bump = rt.Normal_Bump()
            bump.normal_map = bitmap
            slot = "bumpMap" if standard else next((n for n in ("bump_map", "norm_map", "bumpMap")
                                                    if rt.isProperty(material, rt.Name(n))), "")
            if not slot:
                return False
            rt.setProperty(material, rt.Name(slot), bump)
            if standard:
                material.bumpMapAmount = 100
        elif standard or rt.isProperty(material, rt.Name("specularMap")) and rt.classOf(material) != rt.PhysicalMaterial:
            material.specularMap = bitmap
        elif rt.classOf(material) == rt.PhysicalMaterial:
            material.roughness_map = bitmap
            material.roughness_map_on = False       # an _smdi is no roughness map: kept for its path only
        else:
            return False
    except Exception:  # noqa: BLE001 - a material that has no such slot after all
        return False
    return True


def find_maps(materials) -> dict:
    """Put the _nohq and _smdi pictures lying next to the colour map into the slots that are free"""
    counts = {"normal": 0, "specular": 0, "paa_only": 0}
    for material in materials:
        diffuse = map_file(diffuse_map(material))
        if not diffuse or arma_attributes(material) is not None:
            continue
        for kind in ("normal", "specular"):
            lookup, suffix, _expected = _MAPS[kind]
            if map_file(lookup(material)):
                continue
            found = neighbour(diffuse, suffix)
            if found.lower().endswith(".paa"):
                counts["paa_only"] += 1             # 3ds Max can't open it; an .rvmat names it all the same
            elif found and _put(material, kind, found):
                counts[kind] += 1
    return counts


def rvmat_files(materials) -> List[Tuple[object, str]]:
    """(material, its .rvmat) for the materials an .rvmat can be made for"""
    plan = TexturePlan(True, "", gen_rvmat=True)
    return [(material, plan.rvmat_file(material)) for material in materials
            if arma_attributes(material) is None and plan.rvmat_file(material)]


def generate_rvmats(materials, preset: str, tex_root: str, replace: bool = False) -> dict:
    """An .rvmat next to the colour map of each material; materials with paths of their own are left out"""
    plan = TexturePlan(True, tex_root, gen_rvmat=True, preset=preset)
    plan.used = [material for material, _file in rvmat_files(materials)]
    written = plan.write_rvmats(replace)
    return {"written": written, "kept": plan.kept, "skipped": len(materials) - len(plan.used), "notes": plan.notes}


def replace_paths(materials, find: str, replacement: str) -> int:
    """Swap a piece of the texture paths (colour, normal, specular); returns how many changed"""
    changed = 0
    for material in materials:
        for tex_map in (diffuse_map(material), normal_map(material), specular_map(material)):
            node = bitmap_node(tex_map)
            name = str(node.filename) if node is not None and node.filename else ""
            if find and find.lower() in name.lower():
                at = name.lower().index(find.lower())
                node.filename = name[:at] + replacement + name[at + len(find):]
                changed += 1
    return changed


def objects_using(materials) -> list:
    hits = []
    for node in rt.objects:
        if rt.superClassOf(node) != rt.GeometryClass:
            continue
        leaves: list = []
        _leaves(node.material, leaves)
        if any(leaf == wanted for leaf in leaves for wanted in materials):
            hits.append(node)
    return hits


def to_editor(material) -> None:
    try:
        rt.meditMaterials[0] = material
        rt.medit.SetActiveMtlSlot(1, False)
    except Exception:  # noqa: BLE001 - no Compact Material Editor
        pass
