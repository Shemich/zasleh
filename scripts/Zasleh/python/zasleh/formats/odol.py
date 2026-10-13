"""Binarized (ODOL) models: this package reads none, an outside debinarizer turns them into MLOD first"""

import os
import shutil
import subprocess

from .mlod import P3DError

NO_WINDOW = 0x08000000


def is_odol(path: str) -> bool:
    with open(path, "rb") as stream:
        return stream.read(4) == b"ODOL"


def to_mlod(path: str, tool: str, work: str, timeout: int = 600) -> str:
    """Run the debinarizer (called as "tool inFolder outFolder") on a copy of the file.
    Gives the editable p3d: same file name, inside the work folder, which is emptied first."""
    if not tool or not os.path.isfile(tool):
        raise P3DError("this is a binarized (ODOL) model: set the path of a debinarizer (Settings) to have it converted on import")
    name = os.path.basename(path)
    source, target = os.path.join(work, "in"), os.path.join(work, "out")
    for folder in (source, target):
        shutil.rmtree(folder, ignore_errors=True)
        os.makedirs(folder)
    shutil.copyfile(path, os.path.join(source, name))
    try:
        subprocess.run([tool, source, target], cwd=os.path.dirname(tool) or None, timeout=timeout,
                       creationflags=NO_WINDOW if os.name == "nt" else 0, stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as error:
        raise P3DError("the debinarizer did not run: %s" % error)
    made = [entry for entry in os.listdir(target) if entry.lower().endswith(".p3d")]
    if len(made) != 1 or is_odol(os.path.join(target, made[0])):
        raise P3DError("%s made no editable p3d of %s" % (os.path.basename(tool), name))
    if made[0] != name:                                 # some tools add a suffix; the model keeps its name
        os.replace(os.path.join(target, made[0]), os.path.join(target, name))
    return os.path.join(target, name)
