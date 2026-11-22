#!/usr/bin/env python3
"""Print source units in the page's fence form, verbatim from the tree.

    excerpt.py [--tree DIR] [--commit SHA] [--note TEXT] [--whole] UNIT

A UNIT is `path:A-B[,C-D...]`: the file from the tree root and one or more
ascending line ranges; with --whole it is `path:A`, and the unit becomes the
whole construct holding line A, found with the tree facts of tools/qa
(tree-sitter). The first range opens the unit with its provenance comment `/*
path:A */`; every later range is reached through a counted elision line `... /*
N lines, to :C */`, indented like the line it resumes at, N being the file
lines dropped between the ranges
(guidelines/page/rules/active/provenance.form.md, excerpts.contiguity.md). One
UNIT goes into the fence with its single provenance comment. Lines are read
from the working copy of the tree, or from `git show SHA:path` with --commit,
byte for byte. The tool prints the fence and decides nothing: whether a unit
begins and ends where the rules say is the checker's question
(tools/qa/run.py).
"""

import argparse
from pathlib import Path
import re
import subprocess
import sys

if not __package__:
    # run as a script: make the repository's packages importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.checkout import absolute, tree_or_exit

ROOT = str(absolute(__file__).parents[2])


class ExcerptError(Exception):
    pass


_cache = {}


def file_lines(tree, path, commit=None):
    """The file's lines without their newline, from the working copy or from a
    commit."""
    key = (tree, path, commit)
    if key in _cache:
        return _cache[key]
    if commit:
        done = subprocess.run(
            ["git", "-C", tree, "show", f"{commit}:{path}"],
            capture_output=True,
        )
        if done.returncode != 0:
            raise ExcerptError(
                f"{path} is not readable at {commit}:"
                f" {done.stderr.decode('utf-8', 'replace').strip()}"
            )
        data = done.stdout
    else:
        full = Path(tree, path)
        if not full.is_file():
            raise ExcerptError(f"no such file in the tree: {path}")
        data = full.read_bytes()
    lines = data.decode("utf-8").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    _cache[key] = lines
    return lines


def parse_unit(spec):
    """`path:A-B[,C-D...]` -> (path, [(A, B), ...]); a lone number is a
    one-line range."""
    spec = spec.strip()
    if ":" not in spec:
        raise ExcerptError(f"a unit is path:A-B[,C-D...]: {spec!r}")
    path, ranges = spec.rsplit(":", 1)
    out = []
    for part in ranges.split(","):
        part = part.strip()
        if not part:
            raise ExcerptError(f"empty range in {spec!r}")
        a, _, b = part.partition("-")
        try:
            start, end = int(a), int(b) if b else int(a)
        except ValueError:
            raise ExcerptError(
                f"a range is two line numbers A-B: {part!r} in {spec!r}"
            ) from None
        if start < 1 or end < start:
            raise ExcerptError(
                f"a range runs from its first line to its last: {part!r} in"
                f" {spec!r}"
            )
        out.append((start, end))
    for (_a, b), (c, _d) in zip(out, out[1:]):
        if c <= b + 1:
            raise ExcerptError(
                f"ranges {b} and {c} in {spec!r} leave no line to elide; merge"
                " them or leave a gap"
            )
    return path, out


def unit_lines(tree, path, ranges, note=None, commit=None):
    """The lines of one unit: provenance, the ranges, counted elisions between
    them."""
    source = file_lines(tree, path, commit)
    out = []
    for k, (start, end) in enumerate(ranges):
        if end > len(source):
            raise ExcerptError(
                f"{path} has {len(source)} lines; the range {start}-{end} runs"
                " past its end"
            )
        if k == 0:
            out.append(
                f"/* {path}:{start}" + (f" {note}" if note else "") + " */"
            )
        else:
            dropped = start - ranges[k - 1][1] - 1
            following = next(
                (line for line in source[start - 1 : end] if line.strip()), ""
            )
            # the indentation of the line the excerpt resumes at, which the
            # elision line takes; e.g. the tab of a line `\treturn 0;`
            indent = re.match(r"[ \t]*", following).group(0)
            out.append(
                f"{indent}... /* {dropped} line{'s' if dropped != 1 else ''},"
                f" to :{start} */"
            )
        out.extend(source[start - 1 : end])
    return out


def whole_unit(tree, spec):
    """`path:A` -> `path:line-end` of the construct holding line A, by the tree
    facts of tools/qa."""
    path, ranges = parse_unit(spec)
    if len(ranges) != 1 or ranges[0][0] != ranges[0][1]:
        raise ExcerptError(f"--whole takes one line, path:A: {spec!r}")
    # PyYAML and tree-sitter are needed only here
    from tools.qa.page import profile
    from tools.qa.tree import Tree

    construct = Tree(tree, profile(ROOT)).construct_at(path, ranges[0][0])
    if construct is None:
        raise ExcerptError(f"{path}:{ranges[0][0]} lies in no construct")
    return f"{path}:{construct['line']}-{construct['end']}"


def fence(tree, units, note=None, commit=None, lang="c"):
    """One fence holding exactly one UNIT spec."""
    if len(units) != 1:
        raise ExcerptError(
            "a source fence takes exactly one source unit; use separate fences"
            " with prose between them"
        )
    path, ranges = parse_unit(units[0])
    body = unit_lines(tree, path, ranges, note, commit)
    return "```" + lang + "\n" + "\n".join(body) + "\n```"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--tree",
        help=(
            "the kernel checkout (default: $KG_TREE, else the kernel checkout"
            " whose .claude directory holds this repository)"
        ),
    )
    parser.add_argument(
        "--commit",
        help=(
            "read the files at this commit with git show instead of the"
            " working copy"
        ),
    )
    parser.add_argument(
        "--note", help="a short annotation after the first unit's line number"
    )
    parser.add_argument(
        "--whole",
        action="store_true",
        help="UNIT is path:A; print the whole construct holding line A",
    )
    parser.add_argument(
        "unit",
        metavar="UNIT",
        help="path:A-B[,C-D...], or path:A with --whole",
    )
    args = parser.parse_args(argv)
    try:
        tree = tree_or_exit(ROOT, args.tree)
        unit = whole_unit(tree, args.unit) if args.whole else args.unit
        print(fence(tree, [unit], args.note, args.commit))
    except ExcerptError as error:
        raise SystemExit(f"excerpt: {error}")


if __name__ == "__main__":
    main()
