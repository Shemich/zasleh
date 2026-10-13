"""Settings, kept in plugcfg\\Zasleh.ini"""

import os

import pymxs

rt = pymxs.runtime
SECTION = "Zasleh"


def _path() -> str:
    return os.path.join(str(rt.getDir(rt.Name("plugcfg"))), "Zasleh.ini")


def get(key: str, default: str = "") -> str:
    value = rt.getINISetting(_path(), SECTION, key)
    return str(value) if value else default


def put(key: str, value) -> None:
    rt.setINISetting(_path(), SECTION, key, str(value))


def flag(key: str, default: bool = True) -> bool:
    return get(key, "1" if default else "0") != "0"


def default_texture_root() -> str:
    r"""The "Tex root" setting, else P:\ if there is one"""
    return get("texRoot") or ("P:\\" if os.path.isdir("P:\\") else "")


def scratch_folder(name: str, tex_root: str) -> str:
    """Where the toolbox keeps files it makes for itself: under the texture root, else in the user's profile"""
    if tex_root and os.path.isdir(tex_root):
        return os.path.join(tex_root, "temp", "zasleh_" + name)
    return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Zasleh", name)
