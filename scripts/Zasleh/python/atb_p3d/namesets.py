"""Name sets: the selections a kind of model is usually cut into, each with a word on what it is.

A set is a text file, a line per selection:   name = what it is
The part after "=" may be left out; a line that starts with # is a comment.
"""

import os
from typing import List, Tuple

EXTENSION = ".txt"


def parse(text: str) -> List[Tuple[str, str]]:
    """(name, description) in the order of the file, each name once"""
    found: List[Tuple[str, str]] = []
    seen = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, _sep, description = line.partition("=")
        name = name.strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            found.append((name, description.strip()))
    return found


def available(folder: str) -> List[str]:
    """Names of the sets of a folder"""
    try:
        files = os.listdir(folder)
    except OSError:
        return []
    return sorted((name[:-len(EXTENSION)] for name in files if name.lower().endswith(EXTENSION)), key=str.lower)


def read(folder: str, name: str) -> List[Tuple[str, str]]:
    """The entries of a set; nothing if there is no such set"""
    try:
        with open(os.path.join(folder, name + EXTENSION), encoding="utf-8", errors="replace") as stream:
            return parse(stream.read())
    except OSError:
        return []
