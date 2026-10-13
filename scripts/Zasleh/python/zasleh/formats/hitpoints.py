"""Hit points as a config.cpp describes them: which selection, what radius"""

import re
from typing import Dict

_BLOCK = re.compile(r"\{([^{}]*)\}")
_NAME = re.compile(r'\bname\s*=\s*"([^"]+)"', re.I)
_RADIUS = re.compile(r"\bradius\s*=\s*([-+]?[\d.]+(?:e[-+]?\d+)?)", re.I)


def radii(text: str) -> Dict[str, float]:
    """{selection: radius} of the classes that give both (class HitHull { name = "..."; radius = 0.15; })"""
    text = re.sub(r"//[^\n]*|/\*.*?\*/", "", text, flags=re.S)
    found: Dict[str, float] = {}
    for block in _BLOCK.findall(text):
        name, radius = _NAME.search(block), _RADIUS.search(block)
        if name and radius:
            try:
                found[name.group(1)] = float(radius.group(1))
            except ValueError:
                pass
    return found
