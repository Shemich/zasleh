"""LOD resolution <-> LOD name"""

from __future__ import annotations

from typing import Optional

__all__ = ["lod_name", "lod_resolution", "is_point_lod", "is_shadow_lod", "has_mass",
           "MEMORY", "GEOMETRY", "SPECIAL_LODS"]

VIEW_GUNNER = 1.0e3
VIEW_PILOT = 1.1e3
VIEW_CARGO = 1.2e3
SHADOW_MIN = 1.0e4          # Shadow Volume N = 10000 + N
SHADOW_BUFFER_MIN = 1.1e4   # Shadow Buffer N = 11000 + N
EDIT_MIN = 2.0e4            # Edit N = 20000 + N
EDIT_MAX = 3.0e4
GEOMETRY = 1.0e13
MEMORY = 1.0e15

# (resolution, name) of the fixed special LODs
SPECIAL_LODS = (
    (VIEW_GUNNER, "View Gunner"),
    (VIEW_PILOT, "View Pilot"),
    (VIEW_CARGO, "View Cargo"),
    (GEOMETRY, "Geometry"),
    (2.0e13, "Geometry Buoyancy"),
    (3.0e13, "Geometry PhysX Old"),
    (4.0e13, "Geometry PhysX"),
    (MEMORY, "Memory"),
    (2.0e15, "Land Contact"),
    (3.0e15, "Roadway"),
    (4.0e15, "Paths"),
    (5.0e15, "HitPoints"),
    (6.0e15, "View Geometry"),
    (7.0e15, "Fire Geometry"),
    (8.0e15, "View Cargo Geometry"),
    (9.0e15, "View Cargo Fire Geometry"),
    (1.0e16, "View Commander"),
    (1.1e16, "View Commander Geometry"),
    (1.2e16, "View Commander Fire Geometry"),
    (1.3e16, "View Pilot Geometry"),
    (1.4e16, "View Pilot Fire Geometry"),
    (1.5e16, "View Gunner Geometry"),
    (1.6e16, "View Gunner Fire Geometry"),
    (1.7e16, "Sub Parts"),
    (1.8e16, "Shadow Volume - View Cargo"),
    (1.9e16, "Shadow Volume - View Pilot"),
    (2.0e16, "Shadow Volume - View Gunner"),
    (2.1e16, "Wreck"),
)

_INDEXED = (
    (SHADOW_MIN, SHADOW_BUFFER_MIN, "Shadow Volume"),
    (SHADOW_BUFFER_MIN, EDIT_MIN, "Shadow Buffer"),
    (EDIT_MIN, EDIT_MAX, "Edit"),
)


def _is(resolution: float, special: float) -> bool:
    # same tolerance as Object Builder's; the sign is ignored there too
    return abs(abs(resolution) - special) < special * 1e-3


def _number(value: float) -> str:
    text = "%.3f" % value
    return text.rstrip("0").rstrip(".") if "." in text else text


def lod_name(resolution: float) -> str:
    """Name of a LOD"""
    for special, name in SPECIAL_LODS:
        if _is(resolution, special):
            return name
    value = abs(resolution)
    for low, high, name in _INDEXED:
        if low <= value < high:
            return "%s %s" % (name, _number(value - low))
    return _number(resolution)


def lod_resolution(name: str) -> Optional[float]:
    """Resolution for a LOD name as produced by lod_name()"""
    text = name.strip()
    key = text.lower()
    for special, special_name in SPECIAL_LODS:
        if key == special_name.lower():
            return special
    for low, high, indexed_name in _INDEXED:
        prefix = indexed_name.lower() + " "
        if key.startswith(prefix):
            try:
                value = low + float(key[len(prefix):])
            except ValueError:
                return None
            return value if low <= value < high else None
    try:
        return float(text)
    except ValueError:
        return None


def is_point_lod(resolution: float) -> bool:
    """LODs that normally hold loose points and no faces (Memory, Land Contact, HitPoints)"""
    return any(_is(resolution, special) for special in (MEMORY, 2.0e15, 5.0e15))


def is_shadow_lod(resolution: float) -> bool:
    if SHADOW_MIN <= abs(resolution) < EDIT_MIN:
        return True
    return any(_is(resolution, special) for special in (1.8e16, 1.9e16, 2.0e16))


def has_mass(resolution: float) -> bool:
    """LODs for which O2 saves the #Mass# tag (Geometry, PhysX)"""
    return any(_is(resolution, special) for special in (GEOMETRY, 3.0e13, 4.0e13))
