"""Hit points as a config.cpp describes them: which selection, what radius"""

import re
from typing import Dict, Iterator, Tuple

_CLASS = re.compile(r"\bclass\s+\w+[^{};]*\{")
_NAME = re.compile(r'\bname\s*=\s*"([^"]+)"', re.I)
_RADIUS = re.compile(r"\bradius\s*=\s*([-+]?[\d.]+(?:e[-+]?\d+)?)", re.I)


def _closing(text: str, opened: int) -> int:
    """Where the brace opened at this place closes"""
    depth = 0
    for at in range(opened, len(text)):
        if text[at] == "{":
            depth += 1
        elif text[at] == "}":
            depth -= 1
            if depth == 0:
                return at
    return len(text)


def _bodies(text: str) -> Iterator[Tuple[str, str]]:
    """Every class, however deep: (what it says itself, with its inner classes and arrays cut out)"""
    at = 0
    while True:
        found = _CLASS.search(text, at)
        if not found:
            return
        end = _closing(text, found.end() - 1)
        body = text[found.end():end]
        own, last, depth = [], 0, 0
        for position, char in enumerate(body):          # keep the top level only
            if char == "{":
                if depth == 0:
                    own.append(body[last:position])
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    last = position + 1
        own.append(body[last:])
        yield "".join(own), body
        yield from _bodies(body)
        at = end + 1


def radii(text: str) -> Dict[str, float]:
    """{selection: radius} of the classes that give both (class HitHull { name = "..."; radius = 0.15; })"""
    text = re.sub(r"//[^\n]*|/\*.*?\*/", "", text, flags=re.S)
    found: Dict[str, float] = {}
    for own, _whole in _bodies(text):
        name, radius = _NAME.search(own), _RADIUS.search(own)
        if name and radius:
            try:
                found.setdefault(name.group(1), float(radius.group(1)))
            except ValueError:
                pass
    return found
