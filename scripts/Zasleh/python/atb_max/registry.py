"""Where selections live in a mesh: one table for the whole scene"""

from __future__ import annotations

import json
import struct
from typing import Dict, List, Optional, Tuple

import pymxs

rt = pymxs.runtime

APPDATA_ID = 0x41544201
GROUPS_APPDATA_ID = 0x41544204      # on a node: the names of the groups it has
SHOWN_APPDATA_ID = 0x41544205       # on a node: the group shown in colour, while one is
VERSION = 2
DISPLAY_CHANNEL = 9                 # scratch channel for showing a group in colour
FIRST_CHANNEL = 10
LAST_CHANNEL = 99

WEIGHTED = "weighted"       # real weights (skinning): a slot
NUMBER = "number"           # plain per-vert or per-face number (mass, flags): a slot

# slots that aren't user groups
POINT_ID = "#point"         # 1 + index of the p3d point a vert came from
FACE_ID = "#face"           # 1 + index of the p3d face a face came from
MASS = "#mass"
# flags: one slot per byte of the 32-bit value, written with meshprep.flag_code()
POINT_FLAGS = ("#pflags0", "#pflags1", "#pflags2", "#pflags3")
FACE_FLAGS = ("#fflags0", "#fflags1", "#fflags2", "#fflags3")
LOCKED_NORMAL = ("#lock_x", "#lock_y", "#lock_z")   # the kept normal of points flagged "lock normal"

FACE_FLAG = 2.0             # slots: added to a corner value when its face is in the selection
FACE_THRESHOLD = 1.5


class RegistryFull(Exception):
    pass


class OldScene(Exception):
    """The scene was imported by an earlier version of the toolbox and has to be imported again"""


def check_value(number: int) -> float:
    """What y must be for a group number: its square, as a 32-bit float holds it"""
    return struct.unpack("<f", struct.pack("<f", float(number) * float(number)))[0]


def group_number(x: float, y: float) -> int:
    """The group a layer corner is in, 0 if none or if the values are blended ones"""
    number = int(round(x))
    if number < 1 or abs(x - number) > 1e-4:
        return 0
    expected = check_value(number)
    return number if abs(y - expected) <= 1e-6 * expected + 1e-6 else 0


class Registry:
    def __init__(self):
        self.slots: Dict[str, dict] = {}        # name, exactly as written -> {"name", "slot", "kind"}
        self.layers: List[int] = []             # map channels used as layers
        self.ids: Dict[str, int] = {}           # group name -> number (1-based)
        self.names: List[str] = []              # number - 1 -> group name

    # persistence

    @classmethod
    def load(cls) -> "Registry":
        registry = cls()
        raw = rt.getAppData(rt.rootNode, APPDATA_ID)
        if raw:
            try:
                data = json.loads(str(raw))
            except ValueError:
                return registry
            if data.get("version") != VERSION:
                raise OldScene("This scene was imported by an earlier version of the plugin. "
                               "Reset the scene and import the p3d again.")
            registry.slots = data.get("slots", {})
            registry.layers = data.get("layers", [])
            registry.names = data.get("names", [])
            registry.ids = {name: index + 1 for index, name in enumerate(registry.names)}
        return registry

    def save(self) -> None:
        data = {"version": VERSION, "slots": self.slots, "layers": self.layers, "names": self.names}
        rt.setAppData(rt.rootNode, APPDATA_ID, json.dumps(data, sort_keys=True))

    # slots: channels from 10 upwards

    @staticmethod
    def place(slot: int) -> Tuple[int, int]:
        """(map channel, component 0..2) of a slot"""
        return FIRST_CHANNEL + slot // 3, slot % 3

    def get(self, name: str) -> Optional[dict]:
        return self.slots.get(name)

    def allocate(self, name: str, kind: str) -> dict:
        """The slot of a weighted group or of a number, created on first use"""
        entry = self.slots.get(name)
        if entry is not None:
            return entry
        taken = {e["slot"] for e in self.slots.values()}
        slot = 0
        while slot in taken:
            slot += 1
        lowest_layer = min(self.layers) if self.layers else LAST_CHANNEL + 1
        if FIRST_CHANNEL + slot // 3 >= lowest_layer:
            raise RegistryFull("all map channels of the scene are in use")
        entry = self.slots[name] = {"name": name, "slot": slot, "kind": kind}
        return entry

    def by_channel(self) -> Dict[int, List[Optional[dict]]]:
        """{channel: [entry or None] * 3} for every slot channel in use"""
        out: Dict[int, List[Optional[dict]]] = {}
        for entry in self.slots.values():
            channel, component = self.place(entry["slot"])
            out.setdefault(channel, [None, None, None])[component] = entry
        return out

    # layers: channels from 99 downwards

    def layer(self, index: int) -> int:
        """Map channel of the index-th layer, taking a new channel if there aren't that many yet"""
        while len(self.layers) <= index:
            channel = LAST_CHANNEL - len(self.layers)
            highest_slot = max((self.place(e["slot"])[0] for e in self.slots.values()), default=FIRST_CHANNEL - 1)
            if channel <= highest_slot:
                raise RegistryFull("all map channels of the scene are in use")
            self.layers.append(channel)
        return self.layers[index]

    def number(self, name: str) -> int:
        """The nr of a group, giving it one on first use"""
        found = self.ids.get(name)
        if found is None:
            self.names.append(name)
            found = self.ids[name] = len(self.names)
        return found

    def name_of(self, number: int) -> Optional[str]:
        return self.names[number - 1] if 1 <= number <= len(self.names) else None

    def is_weighted(self, name: str) -> bool:
        entry = self.slots.get(name)
        return entry is not None and entry["kind"] == WEIGHTED

    def rename(self, old: str, new: str) -> None:
        """Rename a group everywhere in the scene"""
        if old in self.ids:
            number = self.ids.pop(old)
            self.names[number - 1] = new
            self.ids[new] = number
        entry = self.slots.pop(old, None)
        if entry is not None:
            entry["name"] = new
            self.slots[new] = entry
