"""Export LOD layers of the scene as an editable (MLOD) p3d"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

import pymxs

from zasleh import formats
from zasleh.formats import P3D

from . import materials, reader
from . import registry as reg
from .scene import define_maxscript, layer_info, layer_resolution
from .settings import default_texture_root

rt = pymxs.runtime


@dataclass
class Options:
    """What the export does about textures of ordinary 3ds Max materials"""
    convert_paa: bool = True            # write .paa instead of the bitmap's own extension
    tex_root: Optional[str] = None      # paths are written relative to this folder
    gen_rvmat: bool = False             # write an .rvmat per material and put it on the faces
    rvmat_preset: str = "Super"         # formats.rvmat.PRESETS
    deploy: bool = False                # copy / convert the textures into deploy_dir
    deploy_dir: str = "data"            # relative to the p3d, or absolute
    image_to_paa: str = ""              # ImageToPAA.exe of Arma 3 Tools, for the conversion
    tex_conv: str = ""                  # texconv.exe, for .dds sources


class Textures:
    """(texture, rvmat) of a face; finish() writes the .rvmat files and deploys afterwards"""

    def __init__(self, options: Optional[Options] = None, p3d_path: str = ""):
        self.options = options = options or Options()
        if (options.gen_rvmat or options.deploy) and not p3d_path:
            raise reader.SceneError("Writing .rvmat files and deploying textures needs the path of the p3d.")
        root = default_texture_root() if options.tex_root is None else options.tex_root
        folder = options.deploy_dir or "data"
        if not os.path.isabs(folder):
            folder = os.path.join(os.path.dirname(os.path.abspath(p3d_path)) if p3d_path else "", folder)
        self.plan = materials.TexturePlan(options.convert_paa, root, options.gen_rvmat, options.deploy, folder,
                                          options.image_to_paa, options.tex_conv, options.rvmat_preset)

    def __call__(self, material, material_id: int) -> Tuple[str, str]:
        sub = materials.sub_material(material, material_id)
        if sub is None:
            return ("", "")
        return materials.arma_attributes(sub) or (self.plan.face_texture(sub), self.plan.face_rvmat(sub))

    def finish(self) -> dict:
        done: dict = {}
        if self.options.gen_rvmat:
            done["rvmats"] = self.plan.write_rvmats()       # before the deploy: it queues the maps it names
            done["rvmats_kept"] = self.plan.kept
        if self.options.deploy:
            done["deploy"] = dict(self.plan.run_deploy(), folder=self.plan.deploy_folder)
        done["texture_notes"] = list(self.plan.notes)
        return done


def candidate_layers(include_empty: bool = False) -> List[dict]:
    """Layers that can be exported, with the LOD each one would become"""
    define_maxscript()
    out = []
    manager = rt.LayerManager
    for index in range(int(manager.count)):
        layer = manager.getLayer(index)
        nodes = list(rt.zaslehLayerNodes(layer))
        objects = sum(1 for node in nodes if rt.superClassOf(node) == rt.GeometryClass)
        points = sum(1 for node in nodes if rt.classOf(node) == rt.Point)
        info = layer_info(layer)
        if not include_empty and not objects and not points and not info:
            continue                    # an empty layer is a LOD only if one was imported into it
        resolution = layer_resolution(layer, info)
        name = str(layer.name)
        out.append({
            "layer": name,
            "lod": formats.lod_name(resolution) if resolution is not None else "",
            "objects": objects,
            "points": points,
            # the default layer "0" is a LOD only if a LOD was imported into it
            "checked": resolution is not None and (name != "0" or bool(info)) and bool(objects or points or info),
        })
    return out


def build_model(layer_names: Optional[List[str]] = None,
                textures: Optional[reader.TextureLookup] = None) -> Tuple[P3D, dict]:
    """The scene's LOD layers as a p3d model, and a report"""
    started = time.perf_counter()
    define_maxscript()
    if layer_names is None:
        layer_names = [c["layer"] for c in candidate_layers() if c["checked"]]
    if not layer_names:
        raise reader.SceneError("there are no LOD layers to export: name a layer after a LOD "
                                "(\"1\", \"Geometry\", \"Memory\" ...) and put the objects on it")
    try:
        registry = reg.Registry.load()
    except reg.OldScene as error:
        raise reader.SceneError(str(error))
    textures = textures or Textures()
    model = P3D()
    report = {"lods": [], "notes": []}
    problems = []
    for name in layer_names:
        layer = rt.LayerManager.getLayerFromName(name)
        if layer is None:
            problems.append("layer \"%s\" does not exist" % name)
            continue
        try:
            lod = reader.read_layer(layer, registry, textures, report["notes"])
        except reader.SceneError as error:
            problems.append(str(error))
            continue
        twin = next((row for row in report["lods"] if row["resolution"] == lod.resolution), None)
        if twin is not None:
            problems.append("layers \"%s\" and \"%s\" are the same LOD (%s)"
                            % (twin["layer"], name, formats.lod_name(lod.resolution)))
            continue
        model.lods.append(lod)
        row = {"layer": name, "lod": formats.lod_name(lod.resolution), "resolution": lod.resolution,
               "points": len(lod.points), "faces": len(lod.faces), "selections": len(lod.selections)}
        if lod.mass is not None:
            row["mass"] = round(sum(lod.mass), 3)
            if lod.faces and not row["mass"]:
                report["notes"].append("%s: the mass is 0 (Vertex Groups > Set mass)" % name)
        report["lods"].append(row)
    if problems:
        raise reader.SceneError("\n".join(problems))
    model.lods.sort(key=lambda lod: lod.resolution)
    report["lods"].sort(key=lambda row: row["resolution"])
    report["seconds"] = round(time.perf_counter() - started, 2)
    return model, report


def export_p3d(path: str, layer_names: Optional[List[str]] = None, options: Optional[Options] = None) -> dict:
    """Write the chosen LOD layers (default: all recognised ones) to a p3d file"""
    textures = Textures(options, path)
    model, report = build_model(layer_names, textures)
    formats.write(model, path)
    done = textures.finish()
    report["notes"] += done.pop("texture_notes")
    report.update(done)
    report["file"] = path
    return report


def summary(report: dict) -> str:
    lines = ["%s: %d LOD(s), %.1f s" % (os.path.basename(report.get("file", "")), len(report["lods"]),
                                        report["seconds"])]
    for row in report["lods"]:
        mass = ", mass %g kg" % row["mass"] if "mass" in row else ""
        lines.append("  %-28s %d points, %d faces, %d selections%s"
                     % (row["lod"], row["points"], row["faces"], row["selections"], mass))
    if "rvmats" in report:
        kept = report.get("rvmats_kept", 0)
        lines.append(".rvmat files written: %d%s" % (report["rvmats"], ", already there (kept): %d" % kept if kept else ""))
    deploy = report.get("deploy")
    if deploy:
        lines.append("Textures -> %s" % deploy["folder"])
        lines.append("  %d converted, %d copied, %d already there (kept), %d to supply by hand, %d failed"
                     % (deploy["converted"], deploy["copied"], deploy["kept"], deploy["by_hand"], deploy["failed"]))
    if report.get("notes"):
        lines.append("")
        lines.append("Notes:")
        lines += ["  " + note for note in report["notes"][:15]]
        if len(report["notes"]) > 15:
            lines.append("  ... and %d more" % (len(report["notes"]) - 15))
    return "\n".join(lines)
