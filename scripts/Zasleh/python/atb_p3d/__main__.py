"""Command line helpers"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time

from . import P3DError, dumps, loads, lod_name, read
from .compare import diff_models


def _p3d_files(paths):
    for path in paths:
        if os.path.isdir(path):
            for folder, _dirs, names in os.walk(path):
                for name in names:
                    if name.lower().endswith(".p3d"):
                        yield os.path.join(folder, name)
        else:
            yield path


def _info(args) -> int:
    p3d = read(args.file)
    print("%s: MLOD version 0x%x, %d LOD(s)" % (args.file, p3d.version, len(p3d.lods)))
    for index, lod in enumerate(p3d.lods):
        selections = lod.selections
        weighted = sum(1 for s in selections if s.is_weighted)
        print("  [%d] %-28s points %-7d normals %-7d faces %-7d selections %d (%d weighted)  uv sets %d"
              % (index, lod_name(lod.resolution), len(lod.points), len(lod.normals), len(lod.faces),
                 len(selections), weighted, len(lod.uvsets)))
        if args.verbose:
            for prop in lod.properties:
                print("        property  %s = %s" % (prop.key, prop.value))
            for selection in selections:
                points = len(selection.weights) - selection.weights.count(0)
                faces = len(selection.faces) - selection.faces.count(0)
                print("        selection %-40s points %-6d faces %-6d%s"
                      % (selection.name, points, faces, "  weighted" if selection.is_weighted else ""))
            for problem in lod.problems():
                print("        PROBLEM   %s" % problem)
    for warning in p3d.warnings:
        print("  warning: %s" % warning)
    return 0


def _check(args) -> int:
    ok = failed = skipped = 0
    started = time.time()
    for path in _p3d_files(args.paths):
        try:
            with open(path, "rb") as stream:
                data = stream.read()
        except OSError as error:
            print("FAIL  %s: %s" % (path, error))
            failed += 1
            continue
        if data[:4] != b"MLOD":
            skipped += 1
            continue
        try:
            out = dumps(loads(data))
        except P3DError as error:
            print("FAIL  %s: %s" % (path, error))
            failed += 1
            continue
        if out != data:
            at = next((i for i, (a, b) in enumerate(zip(out, data)) if a != b), min(len(out), len(data)))
            print("DIFF  %s: first difference at byte %d (read %d bytes, wrote %d)"
                  % (path, at, len(data), len(out)))
            failed += 1
            continue
        ok += 1
    print("%d identical, %d failed, %d not MLOD (skipped), %.1f s" % (ok, failed, skipped, time.time() - started))
    return 1 if failed else 0


def _diff(args) -> int:
    differences = diff_models(read(args.first), read(args.second))
    if not differences:
        print("equivalent")
        return 0
    for resolution, difference in differences:
        print("LOD %s" % lod_name(resolution))
        for key, value in difference.items():
            text = str(value)
            print("    %-36s %s" % (key, text if len(text) < 200 else text[:200] + " ..."))
    return 1


_NOT_A_NAME = re.compile(r"^(component\d+|proxy:.*|[-.].*|\d+|(box|cylinder|sphere|plane|line|object|shape|rectangle|circle)\d+)$", re.I)


def selection_names(paths) -> list:
    """Names of the selections of the given models, each once: no proxies, no ComponentNN, no scratch names"""
    found = {}
    for path in _p3d_files(paths):
        for lod in read(path).lods:
            for selection in lod.selections:
                name = selection.name.strip()
                if name and not _NOT_A_NAME.match(name):
                    found.setdefault(name.lower(), name)
    return sorted(found.values(), key=str.lower)


def _names(args) -> int:
    names = selection_names(args.paths)
    lines = ["# %s" % args.title] if args.title else []
    text = "\n".join(lines + names) + "\n"
    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        print("%d name(s) written to %s" % (len(names), args.output))
    else:
        sys.stdout.write(text)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="atb_p3d", description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    info = commands.add_parser("info", help="show what is inside a p3d")
    info.add_argument("file")
    info.add_argument("-v", "--verbose", action="store_true", help="list selections and properties")
    info.set_defaults(run=_info)
    check = commands.add_parser("check", help="round trip files or folders and compare byte for byte")
    check.add_argument("paths", nargs="+")
    check.set_defaults(run=_check)
    diff = commands.add_parser("diff", help="compare two models by meaning (order of tags, editor state "
                                            "and where a face's corner list starts do not count)")
    diff.add_argument("first")
    diff.add_argument("second")
    diff.set_defaults(run=_diff)
    names = commands.add_parser("names", help="list the selection names of models: a name set for the Selections tab")
    names.add_argument("paths", nargs="+", help="p3d files or folders")
    names.add_argument("-o", "--output", help="write a name set file (one name per line) instead of printing")
    names.add_argument("-t", "--title", default="", help="a comment line to put on top")
    names.set_defaults(run=_names)
    args = parser.parse_args(argv)
    try:
        return args.run(args)
    except P3DError as error:
        print("error: %s" % error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
