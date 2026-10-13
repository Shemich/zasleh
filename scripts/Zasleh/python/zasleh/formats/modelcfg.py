"""model.cfg: skeleton, sections and animations of a model"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

ANIMATION_TYPES = ("rotation", "rotationX", "rotationY", "rotationZ", "translation", "translationX",
                   "translationY", "translationZ", "hide", "direct")
_KNOWN = ("type", "source", "selection", "axis", "memory", "minvalue", "maxvalue")


class CfgError(Exception):
    pass


@dataclass
class Animation:
    name: str
    type: str = "rotation"
    source: str = ""
    selection: str = ""
    axis: str = ""
    memory: bool = True
    min_value: float = 0.0
    max_value: float = 1.0
    extra: Dict[str, str] = field(default_factory=dict)     # angle0, angle1, offset0, hideValue...


@dataclass
class ModelCfg:
    model: str = ""
    skeleton: str = ""
    skeleton_inherit: str = ""
    bones: List[Tuple[str, str]] = field(default_factory=list)      # (bone, parent), parents first
    sections: List[str] = field(default_factory=list)
    sections_inherit: str = ""
    animations: List[Animation] = field(default_factory=list)


def sorted_bones(bones: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """Parents before children, otherwise in the given order; a parent that is no bone is kept as it is"""
    names = {name.lower() for name, _parent in bones}
    done: List[Tuple[str, str]] = []
    placed = set()
    left = list(bones)
    while left:
        rest = []
        for name, parent in left:
            if not parent or parent.lower() in placed or parent.lower() not in names:
                done.append((name, parent))
                placed.add(name.lower())
            else:
                rest.append((name, parent))
        if len(rest) == len(left):          # a loop of parents
            done += rest
            break
        left = rest
    return done


def _is_number(text: str) -> bool:
    try:
        float(text)
        return True
    except ValueError:
        return False


def _value(value) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return "%g" % value
    text = str(value)
    return text if _is_number(text) else '"%s"' % text.replace('"', '""')


def _array(names: List[str], indent: str) -> str:
    if not names:
        return "{};"
    lines = ",\n".join('%s\t"%s"' % (indent, name) for name in names)
    return "\n%s{\n%s\n%s};" % (indent, lines, indent)


def generate(cfg: ModelCfg) -> str:
    out = ["class CfgSkeletons", "{", "\tclass %s" % (cfg.skeleton or "Skeleton"), "\t{", "\t\tisDiscrete = 1;",
           '\t\tskeletonInherit = "%s";' % cfg.skeleton_inherit]
    bones = sorted_bones(cfg.bones)
    if bones:
        out += ["\t\tskeletonBones[] =", "\t\t{"]
        out += ['\t\t\t"%s", "%s"%s' % (name, parent, "," if i + 1 < len(bones) else "")
                for i, (name, parent) in enumerate(bones)]
        out.append("\t\t};")
    else:
        out.append("\t\tskeletonBones[] = {};")
    out += ["\t};", "};", "class CfgModels", "{", "\tclass Default", "\t{", '\t\tsectionsInherit = "";',
            "\t\tsections[] = {};", '\t\tskeletonName = "";', "\t};",
            "\tclass %s : Default" % (cfg.model or "Model"), "\t{",
            '\t\tskeletonName = "%s";' % (cfg.skeleton or "Skeleton"),
            '\t\tsectionsInherit = "%s";' % cfg.sections_inherit,
            "\t\tsections[] =" + (_array(cfg.sections, "\t\t") if cfg.sections else " {};"),
            "\t\tclass Animations", "\t\t{"]
    for animation in cfg.animations:
        out += ["\t\t\tclass %s" % animation.name, "\t\t\t{", '\t\t\t\ttype = "%s";' % animation.type,
                '\t\t\t\tsource = "%s";' % animation.source, '\t\t\t\tselection = "%s";' % animation.selection]
        if animation.axis:
            out.append('\t\t\t\taxis = "%s";' % animation.axis)
        out += ["\t\t\t\tmemory = %s;" % _value(animation.memory), "\t\t\t\tminValue = %s;" % _value(animation.min_value),
                "\t\t\t\tmaxValue = %s;" % _value(animation.max_value)]
        out += ["\t\t\t\t%s = %s;" % (key, _value(value)) for key, value in animation.extra.items()]
        out.append("\t\t\t};")
    out += ["\t\t};", "\t};", "};", ""]
    return "\n".join(out)


# -- reading

class _Class:
    def __init__(self, name: str, parent: Optional[str]):
        self.name, self.parent = name, parent
        self.props: Dict[str, object] = {}
        self.keys: Dict[str, str] = {}          # lower-case name -> name as written
        self.classes: List["_Class"] = []

    def get(self, key: str, default=None):
        return self.props.get(key.lower(), default)

    def find(self, name: str) -> Optional["_Class"]:
        return next((c for c in self.classes if c.name.lower() == name.lower()), None)


def _tokens(text: str):
    at, size, line = 0, len(text), 1
    while at < size:
        char = text[at]
        if char == "\n":
            line += 1
            at += 1
        elif char.isspace():
            at += 1
        elif text.startswith("//", at) or (char == "#" and text[text.rfind("\n", 0, at) + 1:at].strip() == ""):
            end = text.find("\n", at)                   # a comment, or a preprocessor line
            at = size if end < 0 else end
        elif text.startswith("/*", at):
            end = text.find("*/", at)
            end = size if end < 0 else end + 2
            line += text.count("\n", at, end)
            at = end
        elif char == '"':
            value = []
            at += 1
            while at < size:
                if text[at] == '"':
                    if text.startswith('""', at):
                        value.append('"')
                        at += 2
                        continue
                    break
                value.append(text[at])
                at += 1
            at += 1
            yield ("str", "".join(value), line)
        elif char in "{};=,:[]":
            at += 1
            yield (char, char, line)
        else:
            end = at
            while end < size and not text[end].isspace() and text[end] not in '{};=,:[]"':
                end += 1
            yield ("word", text[at:end], line)
            at = end


class _Parser:
    def __init__(self, text: str):
        self.items = list(_tokens(text))
        self.at = 0

    def peek(self):
        return self.items[self.at] if self.at < len(self.items) else ("end", "", 0)

    def take(self, kind: Optional[str] = None):
        token = self.peek()
        if kind is not None and token[0] != kind:
            raise CfgError("line %d: expected %s, found %s" % (token[2], kind, token[1] or "the end of the file"))
        self.at += 1
        return token

    def value(self):
        token = self.peek()
        if token[0] == "{":
            self.take()
            values = []
            while self.peek()[0] != "}":
                values.append(self.value())
                if self.peek()[0] == ",":
                    self.take()
            self.take("}")
            return values
        if token[0] == "str":
            return self.take()[1]
        words = []
        while self.peek()[0] in ("word", ":"):
            words.append(self.take()[1])
        if not words:
            raise CfgError("line %d: a value is missing" % token[2])
        text = " ".join(words)
        if _is_number(text):
            number = float(text)
            return int(number) if number == int(number) else number
        return text

    def body(self, into: _Class) -> None:
        while self.peek()[0] not in ("}", "end"):
            token = self.take()
            if token[0] == ";":
                continue
            if token[0] != "word":
                raise CfgError("line %d: unexpected %s" % (token[2], token[1]))
            if token[1].lower() == "class":
                name = self.take("word")[1]
                parent = None
                if self.peek()[0] == ":":
                    self.take()
                    parent = self.take("word")[1]
                if self.peek()[0] == ";":           # a forward declaration
                    continue
                child = _Class(name, parent)
                self.take("{")
                self.body(child)
                self.take("}")
                into.classes.append(child)
            elif token[1].lower() == "delete":
                self.take("word")
            else:
                if self.peek()[0] == "[":
                    self.take()
                    self.take("]")
                self.take("=")
                into.props[token[1].lower()] = self.value()
                into.keys[token[1].lower()] = token[1]


def _text(value) -> str:
    return "" if value is None else ("%g" % value if isinstance(value, float) else str(value))


def _chain(holder: _Class, item: Optional[_Class]) -> List[_Class]:
    """A class and the classes it is derived from, the nearest first"""
    out: List[_Class] = []
    while item is not None and item not in out:
        out.append(item)
        item = holder.find(item.parent) if item.parent else None
    return out


def _own_or_inherited(holder: _Class, item: _Class, key: str):
    return next((each.props[key] for each in _chain(holder, item) if key in each.props), None)


def _merge(names: List[str], more: List[str]) -> List[str]:
    have = {name.lower() for name in names}
    return names + [name for name in more if name.lower() not in have]


def parse(text: str) -> List[ModelCfg]:
    """The models of a model.cfg, each one whole: what a model takes from the classes it is derived from,
    from skeletonInherit and from sectionsInherit is put into it. Macros and includes are not followed."""
    root = _Class("", None)
    parser = _Parser(text)
    parser.body(root)
    if parser.peek()[0] != "end":
        raise CfgError("line %d: unexpected %s" % (parser.peek()[2], parser.peek()[1]))
    skeletons = root.find("CfgSkeletons") or _Class("", None)
    models = root.find("CfgModels") or _Class("", None)
    found: List[ModelCfg] = []

    def bones_of(name: str, seen: Tuple[str, ...] = ()) -> List[Tuple[str, str]]:
        skeleton = skeletons.find(name) if name else None
        if skeleton is None or name.lower() in seen:
            return []
        flat = [str(v) for v in (_own_or_inherited(skeletons, skeleton, "skeletonbones") or [])]
        bones = bones_of(_text(_own_or_inherited(skeletons, skeleton, "skeletoninherit")), seen + (name.lower(),))
        have = {bone.lower() for bone, _parent in bones}
        return bones + [pair for pair in zip(flat[0::2], flat[1::2]) if pair[0].lower() not in have]

    def sections_of(name: str, seen: Tuple[str, ...] = ()) -> List[str]:
        model = models.find(name) if name else None
        if model is None or name.lower() in seen:
            return []
        own = [str(v) for v in (_own_or_inherited(models, model, "sections") or [])]
        return _merge(sections_of(_text(_own_or_inherited(models, model, "sectionsinherit")), seen + (name.lower(),)), own)

    def animations_of(model: _Class) -> List[_Class]:
        """The animation classes of a model and of its parents, each with what it takes from its own parent"""
        whole: Dict[str, _Class] = {}
        for holder in reversed(_chain(models, model)):
            animations = holder.find("Animations")
            for item in (animations.classes if animations is not None else []):
                merged = _Class(item.name, None)
                base = whole.get((item.parent or "").lower())
                for source in (base, item):
                    if source is not None:
                        merged.props.update(source.props)
                        merged.keys.update(source.keys)
                whole.pop(item.name.lower(), None)
                whole[item.name.lower()] = merged
        return list(whole.values())

    for model in models.classes:
        if model.name.lower() == "default":
            continue
        cfg = ModelCfg(model=model.name, skeleton=_text(_own_or_inherited(models, model, "skeletonname")),
                       sections=sections_of(model.name))
        cfg.bones = bones_of(cfg.skeleton)
        for item in animations_of(model):
            animation = Animation(item.name, type=_text(item.get("type", "rotation")), source=_text(item.get("source")),
                                  selection=_text(item.get("selection")), axis=_text(item.get("axis")),
                                  memory=str(item.get("memory", 1)).strip().lower() not in ("0", "false"))
            for key, target in (("minvalue", "min_value"), ("maxvalue", "max_value")):
                try:
                    setattr(animation, target, float(item.get(key, getattr(animation, target))))
                except (TypeError, ValueError):
                    animation.extra[item.keys[key]] = _text(item.get(key))
            animation.extra.update({item.keys[key]: _text(value) for key, value in item.props.items() if key not in _KNOWN})
            cfg.animations.append(animation)
        found.append(cfg)
    if not found:
        for skeleton in skeletons.classes:
            found.append(ModelCfg(skeleton=skeleton.name, bones=bones_of(skeleton.name)))
    return found
