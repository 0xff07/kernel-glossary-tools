#!/usr/bin/env python3
"""Build a page from a template: excerpt directives become verbatim fences,
link shorthand becomes links.

    expand.py [--tree DIR] [--commit SHA] [--version TAG] [--anchors TSV ...]
              [--figures DIR] TEMPLATE OUT

The template is the page with two kinds of shorthand outside its fences;
everything else is copied.

Directives, each a line by itself:
    @@c UNIT [| note]
        a source fence of one unit, `path:A-B[,C-D...]`, in the form
        excerpt.py prints (provenance comment, counted elisions)
    @@fig NAME
        the file NAME.txt under --figures, inlined verbatim

Inline shorthand:
    [[key]] [[key()]] [[text|key]]
        a symbol link, the key resolved through the anchors TSV
        (name<TAB>path:line, as anchors.py prints) to its definition line;
        `struct X`, `A.B` and `CONFIG_X` keys work the same way
    [[@path:N]] [[@path:N-M]]
        a location link; its text is the file's base name, or the path when
        another cited file shares that base name or the file is a Kconfig or
        Makefile (links.site-text)
    [[commit:SHA]]
        `commit [<12 digits>](<commit URL>)`, the hash resolved by git
    [[file:path]]
        a file link, its text the base name (Documentation keeps its path)

Every link uses the one documented version. Unknown keys, missing files, lines
past a file's end and empty elisions are errors: the page is written anyway so
the places can be fixed, the errors are printed, and the exit status is 1. The
tool copies and resolves; it decides nothing about the page, which the QA
runner checks like any other.
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
from tools.writer import excerpt

ROOT = str(absolute(__file__).parents[2])

PERMALINK = "https://elixir.bootlin.com/linux/{version}/source/{path}#L{line}"
FILE_LINK = "https://elixir.bootlin.com/linux/{version}/source/{path}"
COMMIT_LINK = (
    "https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commi"
    "t/?id={commit}"
)
# a shorthand of a template, a text in double square brackets on one line,
# group 1 the text; e.g. `[[pci_walk_bus]]`, `[[@drivers/pci/bus.c:120-134]]`
# and `[[commit:1cbc5e25fb70]]`
SHORTHAND = re.compile(r"\[\[([^\[\]\n]+)\]\]")
KEEP_PATH = ("Kconfig", "Makefile")


def load_anchors(paths):
    """key -> (path, line) from anchors.py TSV files; a later file overrides an
    earlier one."""
    anchors = {}
    for tsv in paths:
        for raw in Path(tsv).read_text(encoding="utf-8").split("\n"):
            if not raw or raw.startswith("#"):
                continue
            cells = raw.split("\t")
            if len(cells) < 2 or ":" not in cells[1]:
                continue
            path, _, line = cells[1].rpartition(":")
            if line.isdigit():
                anchors[cells[0].strip()] = (path, int(line))
    return anchors


def normalize_key(key):
    key = key.strip()
    if key.endswith("()"):
        key = key[:-2]
    return key


class Expander:
    def __init__(self, tree, version, anchors, figures=None, commit=None):
        self.tree, self.version, self.anchors, self.figures, self.commit = (
            tree,
            version,
            anchors,
            figures,
            commit,
        )
        self.errors = []
        self.cited = set()
        self.base_count = {}

    # ---- pass 1: the files the page cites, for the site text of location
    # links ----

    def collect(self, lines):
        in_fence = False
        for line in lines:
            if line.startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            if line.startswith("@@c "):
                for spec in self.unit_specs(line)[0]:
                    try:
                        self.cited.add(excerpt.parse_unit(spec)[0])
                    except excerpt.ExcerptError:
                        pass
                continue
            for m in SHORTHAND.finditer(line):
                body = m.group(1)
                if body.startswith("@"):
                    self.cited.add(body[1:].rsplit(":", 1)[0])
                elif body.startswith("file:"):
                    self.cited.add(body[5:].strip())
                elif not body.startswith("commit:"):
                    key = normalize_key(body.split("|")[-1])
                    if key in self.anchors:
                        self.cited.add(self.anchors[key][0])
        for path in self.cited:
            base = Path(path).name
            self.base_count[base] = self.base_count.get(base, 0) + 1

    def site_text(self, path):
        base = Path(path).name
        if base in KEEP_PATH or self.base_count.get(base, 0) > 1:
            return path
        return base

    # ---- directives ----

    @staticmethod
    def unit_specs(line):
        body = line[len("@@c ") :]
        note = None
        if " | " in body:
            body, note = body.split(" | ", 1)
            note = note.strip()
        return [s.strip() for s in body.split(";") if s.strip()], note

    def source_fence(self, line):
        specs, note = self.unit_specs(line)
        try:
            return excerpt.fence(self.tree, specs, note, self.commit).split(
                "\n"
            )
        except excerpt.ExcerptError as error:
            self.errors.append(str(error))
            return [line]

    def figure(self, name):
        if not self.figures:
            self.errors.append(f"@@fig {name}: no --figures directory given")
            return []
        path = Path(self.figures, name + ".txt")
        if not path.is_file():
            self.errors.append(f"@@fig {name}: no file {path}")
            return []
        return path.read_text(encoding="utf-8").rstrip("\n").split("\n")

    # ---- inline shorthand ----

    def file_exists(self, path):
        if self.commit:
            return (
                subprocess.run(
                    [
                        "git",
                        "-C",
                        self.tree,
                        "cat-file",
                        "-e",
                        f"{self.commit}:{path}",
                    ],
                    capture_output=True,
                ).returncode
                == 0
            )
        return Path(self.tree, path).is_file()

    def line_count(self, path):
        try:
            return len(excerpt.file_lines(self.tree, path, self.commit))
        except (excerpt.ExcerptError, UnicodeDecodeError):
            return None

    def url(self, path, line=None):
        if line is None:
            return FILE_LINK.format(version=self.version, path=path)
        return PERMALINK.format(version=self.version, path=path, line=line)

    def replace(self, match):
        body = match.group(1)
        if body.startswith("@"):
            location = body[1:].strip()
            path, _, rng = location.rpartition(":")
            # a line or a range of lines, groups 1 and 2; e.g. `120` and
            # `120-134`
            m = re.fullmatch(r"(\d+)(?:-(\d+))?", rng)
            if not path or not m:
                self.errors.append(f"[[{body}]] is not @path:N or @path:N-M")
                return match.group(0)
            first = int(m.group(1))
            count = self.line_count(path)
            if count is None:
                self.errors.append(
                    f"[[{body}]]: no such file in the tree: {path}"
                )
            elif first > count or (m.group(2) and int(m.group(2)) > count):
                self.errors.append(f"[[{body}]]: {path} has {count} lines")
            return f"[`{self.site_text(path)}:{rng}`]({self.url(path, first)})"
        if body.startswith("commit:"):
            short = body[len("commit:") :].strip()
            done = subprocess.run(
                [
                    "git",
                    "-C",
                    self.tree,
                    "rev-parse",
                    "--verify",
                    "--quiet",
                    short + "^{commit}",
                ],
                capture_output=True,
                text=True,
            )
            full = done.stdout.strip()
            if len(full) != 40:
                self.errors.append(
                    f"[[{body}]]: the tree does not resolve {short}"
                )
                return match.group(0)
            return f"commit [{full[:12]}]({COMMIT_LINK.format(commit=full)})"
        if body.startswith("file:"):
            path = body[len("file:") :].strip()
            if not self.file_exists(path):
                self.errors.append(
                    f"[[{body}]]: no such file in the tree: {path}"
                )
            text = (
                path if path.startswith("Documentation/") else Path(path).name
            )
            return f"[`{text}`]({self.url(path)})"
        text, _, key = body.rpartition("|")
        if not text:
            text = key
        key = normalize_key(key)
        if key not in self.anchors:
            self.errors.append(
                f"[[{body}]]: no anchor for {key}; add it to the anchors TSV"
            )
            return f"`{text.strip()}`"
        path, line = self.anchors[key]
        return f"[`{text.strip()}`]({self.url(path, line)})"

    # ---- the page ----

    def expand(self, text):
        lines = text.split("\n")
        self.collect(lines)
        out = []
        in_fence = False
        for line in lines:
            if line.startswith("```"):
                in_fence = not in_fence
                out.append(line)
                continue
            if in_fence:
                out.append(line)
                continue
            if line.startswith("@@c "):
                out.extend(self.source_fence(line))
                continue
            if line.startswith("@@fig "):
                out.extend(self.figure(line[len("@@fig ") :].strip()))
                continue
            out.append(SHORTHAND.sub(self.replace, line))
        if in_fence:
            self.errors.append("a fence is never closed")
        return "\n".join(out)


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
            "read source through git show at this commit instead of the"
            " working copy"
        ),
    )
    parser.add_argument(
        "--version",
        required=True,
        help="the documented tag every link names, such as v7.2",
    )
    parser.add_argument(
        "--anchors",
        action="append",
        default=[],
        metavar="TSV",
        help="an anchors.py TSV; repeatable",
    )
    parser.add_argument(
        "--figures",
        help="the directory holding NAME.txt files for @@fig lines",
    )
    parser.add_argument("template")
    parser.add_argument("out")
    args = parser.parse_args(argv)
    tree = tree_or_exit(ROOT, args.tree)
    expander = Expander(
        tree,
        args.version,
        load_anchors(args.anchors),
        args.figures,
        args.commit,
    )
    text = expander.expand(Path(args.template).read_text(encoding="utf-8"))
    Path(args.out).write_text(text.rstrip("\n") + "\n", encoding="utf-8")
    for error in expander.errors:
        print(f"expand: {error}", file=sys.stderr)
    print(
        f"{args.out}: {text.count(chr(10)) + 1} lines,"
        f" {len(text.encode('utf-8'))} bytes, {len(expander.errors)} error(s)",
        file=sys.stderr,
    )
    if expander.errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
