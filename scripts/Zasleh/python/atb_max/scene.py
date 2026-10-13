"""What the toolbox keeps in a 3ds Max scene, and the bit of MAXScript every module needs"""

from __future__ import annotations

import json
import re
from typing import Iterable, List, Optional

import pymxs

import atb_p3d

rt = pymxs.runtime

LAYER_APPDATA_ID = 0x41544202       # on a layer: what is recorded about its LOD
COMPONENT = re.compile(r"^component\d+$", re.I)
PROXY_PREFIX = "proxy:"
UNNAMED_POINT = "point"             # the name of a point helper that is in no selection
PREVIEW_EXTENSIONS = (".tga", ".png", ".tif", ".tiff", ".jpg", ".bmp", ".dds")     # pictures 3ds Max opens

_MAXSCRIPT = r'''
fn atbLayerNodes l = (local found = #(); l.nodes &found; found)
fn atbBits b = (b as array)
global atbArmaMaterialCA = attributes atbArmaMaterial attribID:#(0x41544203, 0x6d61746c)
(
    parameters main rollout:params
    (
        texture type:#string ui:edTexture default:""
        rvmat type:#string ui:edRvmat default:""
    )
    rollout params "Arma"
    (
        edittext edTexture "Texture" labelOnTop:true
        edittext edRvmat "RVMAT" labelOnTop:true
    )
)
'''
_defined = False


def define_maxscript() -> None:
    global _defined
    if not _defined:
        rt.execute(_MAXSCRIPT)
        _defined = True


def to_bits(numbers: Iterable[int]):
    """A MAXScript bitarray of 1-based numbers"""
    return rt.execute("#{%s}" % ",".join(str(i) for i in numbers))


def from_bits(bitarray) -> List[int]:
    define_maxscript()
    return [int(i) for i in rt.atbBits(bitarray)]


def layers() -> list:
    manager = rt.LayerManager
    return [manager.getLayer(index) for index in range(int(manager.count))]


def layer_info(layer) -> dict:
    """What is recorded about a LOD layer: model, resolution, properties, original order"""
    raw = rt.getAppData(layer.layerAsRefTarg, LAYER_APPDATA_ID)
    if raw:
        try:
            return json.loads(str(raw))
        except ValueError:
            pass
    return {}


def set_layer_info(layer, info: dict) -> None:
    rt.setAppData(layer.layerAsRefTarg, LAYER_APPDATA_ID, json.dumps(info))


def layer_resolution(layer, info: Optional[dict] = None) -> Optional[float]:
    """The LOD a layer stands for, None if its name is no LOD's"""
    info = layer_info(layer) if info is None else info
    named = atb_p3d.lod_resolution(str(layer.name).split(" [")[0])
    if "resolution" in info:
        stored = float(info["resolution"])
        # the layer name wins once the user has renamed the layer to another kind of LOD
        if named is None or atb_p3d.lod_name(stored) == atb_p3d.lod_name(named):
            return stored
    return named
