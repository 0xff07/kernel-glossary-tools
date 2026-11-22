#!/usr/bin/env python3
"""Resolve symbols to their definition lines, the anchors a page's links need.

    anchors.py [--tree DIR] [--tags FILE | --no-tags] resolve NAME [NAME ...]
    anchors.py [--tree DIR] check TSV

A NAME is a C identifier (`pcie_do_recovery`), a tagged type (`struct
pci_error_handlers`), a member (`pci_error_handlers.error_detected`) or a
Kconfig option (`CONFIG_PCIEAER`); `NAME@path` keeps only the definitions in
files under that path when a name is defined in several. `resolve` prints one
TSV line per name, `name<TAB>path:line<TAB>kind`, listing every definition it
finds, so a name with several is settled by the writer, and names it cannot
find on standard error. It reads the tree's `tags` file through `readtags` when
both exist (tools/tagsfile.py settles each entry's search pattern to its line
on disk, since `make tags` writes no line numbers, and moves a function to the
first line of a split signature), and otherwise searches the tree with `git
grep` for the lines that look like definitions. `check` re-reads a TSV and
reports every line whose file no longer spells the name at the line it names,
the test the link checker applies.

An anchor is a hint to re-read on disk, never a citation: links.definition-line
decides what a definition line is, and the QA runner checks every link of the
finished page.
"""

import argparse
from pathlib import Path
import re
import shutil
import subprocess
import sys

if not __package__:
    # run as a script: make the repository's packages importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.checkout import absolute, tree_or_exit
from tools.tagsfile import (
    entries as tags_entries,
    file_lines,
    head_of,
    scope_holder,
)

ROOT = str(absolute(__file__).parents[2])

KINDS = {
    "f": "function",
    "p": "prototype",
    "s": "struct",
    "u": "union",
    "g": "enum",
    "e": "enumerator",
    "d": "macro",
    "t": "typedef",
    "v": "variable",
    "m": "member",
    "c": "config",
    "x": "extern",
}
TAG_KINDS = {"struct": "s", "union": "u", "enum": "g"}


def parse_name(text):
    """(key, tag or None, member or None, path filter or None, is_config)."""
    text = text.strip()
    path = None
    if "@" in text:
        text, path = text.rsplit("@", 1)
        text = text.strip()
    if text.startswith("CONFIG_"):
        return text, None, None, path, True
    # a tagged type, group 1 the keyword and group 2 the tag; e.g. `struct
    # pci_error_handlers`
    m = re.fullmatch(r"(struct|union|enum)\s+([A-Za-z_]\w*)", text)
    if m:
        return m.group(2), m.group(1), None, path, False
    # a member, `Holder.member`, groups 1 and 2; e.g.
    # `pci_error_handlers.error_detected`
    m = re.fullmatch(r"([A-Za-z_]\w*)\.([A-Za-z_]\w*)", text)
    if m:
        return m.group(1), None, m.group(2), path, False
    if text.endswith("()"):
        text = text[:-2]
    # a plain C identifier, what is left once a trailing `()` is cut off; e.g.
    # `pcie_do_recovery`
    if not re.fullmatch(r"[A-Za-z_]\w*", text):
        raise ValueError(
            "not a symbol, a tagged type, a member or a CONFIG option:"
            f" {text!r}"
        )
    return text, None, None, path, False


def posix_pattern(pattern):
    """A Perl-style pattern rewritten for POSIX extended regex, which knows no
    `\\w`, `\\b` or `\\t`."""
    # a `\w` inside a bracket expression, spelled out for POSIX; e.g. `[\w.]`
    # becomes `[A-Za-z0-9_.]`
    out = re.sub(
        r"\[([^\]]*?)\\w([^\]]*)\]",
        lambda m: "[" + m.group(1) + "A-Za-z0-9_" + m.group(2) + "]",
        pattern,
    )
    out = out.replace("\\w", "[A-Za-z0-9_]").replace("\\t", "\t")
    # a `\b` before a name or a `(`, rewritten as the start of the line or a
    # character that is no word character; e.g. `\bstruct` becomes
    # `(^|[^A-Za-z0-9_])struct`
    out = re.sub(r"\\b(?=[A-Za-z_(])", "(^|[^A-Za-z0-9_])", out)
    return out.replace("\\b", "")


def git_grep(tree, pattern, paths=(), fixed=False):
    """(path, line, text) for every match; Perl regex when git has PCRE, else
    the POSIX rewrite."""
    base = ["git", "-C", tree, "grep", "-n", "-I"]
    cmd = (
        base
        + (["-F"] if fixed else ["-P"])
        + [pattern, "--"]
        + list(paths or ())
    )
    done = subprocess.run(cmd, capture_output=True, text=True)
    if done.returncode not in (0, 1) and not fixed:
        cmd = base + ["-E", posix_pattern(pattern), "--"] + list(paths or ())
        done = subprocess.run(cmd, capture_output=True, text=True)
    if done.returncode not in (0, 1):
        raise RuntimeError(done.stderr.strip())
    out = []
    for line in done.stdout.splitlines():
        path, number, text = line.split(":", 2)
        out.append((path, int(number), text))
    return out


def resolve_config(tree, option, path):
    name = option[len("CONFIG_") :]
    hits = git_grep(
        tree,
        r"^[ \t]*(menu)?config[ \t]+" + re.escape(name) + r"[ \t]*$",
        [path] if path else ["*Kconfig*"],
    )
    return [
        (p, n, "config")
        for p, n, _t in hits
        if Path(p).name.startswith("Kconfig")
    ]


def readtags_entries(tree, tags, name):
    """(path, line, kind, fields) per entry of the tags file for name, each
    settled to a line of its file."""
    return tags_entries(tree, tags, name)


def resolve_with_tags(tree, tags, key, tag, member, path):
    entries = readtags_entries(tree, tags, member or key)
    out = []
    for p, n, kind, fields in entries:
        if path and not p.startswith(path.rstrip("/") + "/") and p != path:
            continue
        if tag and kind != TAG_KINDS[tag]:
            continue
        if member:
            # the holder is the innermost struct, union or enum of the entry's
            # scope that has a tag: a member the tags file puts in
            # `struct:mm_struct::__anon...`, an anonymous struct or union
            # inside, is mm_struct's
            holder = scope_holder(fields)
            if holder is None:
                holder = (
                    fields.get("struct")
                    or fields.get("union")
                    or fields.get("enum")
                    or fields.get("typeref", "")
                ).split(":")[-1]
            if holder != key:
                continue
        if not tag and not member and kind in ("m", "p", "x"):
            continue
        out.append((p, n, KINDS.get(kind, kind)))
    return out


MEMBER_AFTER = (
    r"(?!\w)\s*(\[[^\]]*\])*(\s+[A-Za-z_]\w*(\([^)]*\))?)*\s*[;:,=)]"
)


def code_part(text, in_comment):
    """(the line without its comments, whether a block comment is still open at
    its end): a `/* ... */` that began on an earlier line or begins on this one
    and a `//` tail are dropped, a comment marker inside a string or a
    character literal stays text. A member's line is looked for in the code, so
    that a comment naming the member on another member's line (`unsigned long
    vm_pgoff; /* Offset (within vm_file) ... */`) is not taken for its
    declaration."""
    out, i, quote = [], 0, None
    while i < len(text):
        if in_comment:
            end = text.find("*/", i)
            if end < 0:
                return "".join(out), True
            i, in_comment = end + 2, False
            out.append(" ")
            continue
        ch = text[i]
        if quote:
            out.append(ch)
            if ch == "\\" and i + 1 < len(text):
                out.append(text[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
        elif text.startswith("/*", i):
            in_comment = True
            i += 2
            continue
        elif text.startswith("//", i):
            break
        else:
            if ch in "\"'":
                quote = ch
            out.append(ch)
        i += 1
    return "".join(out), in_comment


def resolve_with_grep(tree, key, tag, member, path):
    paths = [path] if path else ["*.c", "*.h", "*.S"]
    out = []
    if tag:
        for p, n, _t in git_grep(
            tree,
            r"^[ \t]*" + tag + r"[ \t]+" + re.escape(key) + r"[ \t]*\{",
            paths,
        ):
            out.append((p, n, tag))
        return out
    if member:
        holders = git_grep(
            tree,
            r"^[ \t]*(struct|union|enum)[ \t]+" + re.escape(key) + r"[ \t]*\{",
            paths,
        )
        for p, start, _t in holders:
            lines = (
                Path(tree, p)
                .read_text(encoding="utf-8", errors="replace")
                .split("\n")
            )
            depth, in_comment = 0, False
            # the member's name where a body declares it: no word character or
            # `.` before it and, after it, what MEMBER_AFTER allows up to `;`,
            # `:`, `,`, `=` or `)`; e.g. error_detected in `pci_ers_result_t
            # (*error_detected)(struct pci_dev *dev,`
            spelled = re.compile(
                r"(?<![\w.])" + re.escape(member) + MEMBER_AFTER
            )
            for k in range(start - 1, len(lines)):
                # the braces and the name count in code only
                code, in_comment = code_part(lines[k], in_comment)
                depth += code.count("{") - code.count("}")
                if k > start - 1 and spelled.search(code):
                    out.append((p, k + 1, "member"))
                    break
                if depth <= 0 and k > start - 1:
                    break
        return out
    patterns = [
        (r"^[A-Za-z_][\w \t*]*\b" + re.escape(key) + r"[ \t]*\(", "function"),
        (
            r"^[ \t]*#[ \t]*define[ \t]+" + re.escape(key) + r"(\(|[ \t]|$)",
            "macro",
        ),
        (
            r"^[ \t]*(struct|union|enum)[ \t]+" + re.escape(key) + r"[ \t]*\{",
            "tagged",
        ),
        (
            r"^[ \t]*typedef\b.*\b" + re.escape(key) + r"[ \t]*(;|\[|\))",
            "typedef",
        ),
        (r"^\s*" + re.escape(key) + r"\s*(=|,|$)", "enumerator"),
        (
            r"^[A-Za-z_][\w \t*]*\b"
            + re.escape(key)
            + r"(\[[^\]]*\])*[ \t]*(=|;)",
            "variable",
        ),
        (
            r"^(static["
            r" \t]+)?((DEFINE|DECLARE)_[A-Z0-9_]+|TRACE_EVENT[A-Z_]*|"
            r"[A-Z0-9_]+_HEAD)\(([^()]*[,(]["
            r" \t]*)?" + re.escape(key) + r"[ \t]*[,)]",
            "macro invocation",
            # the object a kernel macro defines at column 0, the name at any
            # argument: DEFINE_STATIC_KEY_MAYBE(CONFIG_X, name), static
            # DEFINE_PER_CPU(type, name), DEFINE_EVENT(class, name, ...
            # (unclosed); the same macros as run.py's _MACRO_OBJECT
        ),
    ]
    for pattern, kind in patterns:
        for p, n, text in git_grep(tree, pattern, paths):
            if kind == "function" and (
                text.rstrip().endswith(";")
                or text.lstrip().startswith("extern ")
            ):
                continue  # a prototype, not a definition
            if kind == "enumerator" and not text.strip().startswith(key):
                continue
            out.append((p, n, kind))
    # a split signature: the name opens its line and the return type stands on
    # the line above
    for p, n, text in git_grep(
        tree, r"^" + re.escape(key) + r"[ \t]*\(", paths
    ):
        lines = file_lines(tree, p)
        if text.rstrip().endswith(";") or not lines:
            continue
        head = head_of(lines, n)
        if head < n:
            out.append((p, head, "function"))
    return out


def resolve(tree, name, tags=None):
    key, tag, member, path, is_config = parse_name(name)
    if is_config:
        return resolve_config(tree, key, path)
    if tags:
        found = resolve_with_tags(tree, tags, key, tag, member, path)
        if found:
            return found
    return resolve_with_grep(tree, key, tag, member, path)


def check(tree, tsv):
    """Every TSV line whose file does not spell the name at its line, or whose
    file is missing."""
    problems = []
    for raw in Path(tsv).read_text(encoding="utf-8").split("\n"):
        if not raw or raw.startswith("#"):
            continue
        cells = raw.split("\t")
        if len(cells) < 2 or ":" not in cells[1]:
            problems.append(f"{raw!r}: not name<TAB>path:line")
            continue
        name, location = cells[0], cells[1]
        path, _, line = location.rpartition(":")
        full = Path(tree, path)
        if not full.is_file() or not line.isdigit():
            problems.append(
                f"{name}: {location} names no file line of the tree"
            )
            continue
        lines = full.read_text(encoding="utf-8", errors="replace").split("\n")
        n = int(line)
        if n < 1 or n > len(lines):
            problems.append(f"{name}: {path} has {len(lines)} lines, not {n}")
            continue
        key, tag, member, _p, is_config = parse_name(name)
        wanted = member or (key[len("CONFIG_") :] if is_config else key)
        text = lines[n - 1]
        following = lines[n] if n < len(lines) else ""
        pattern = r"(?<![\w])" + re.escape(wanted) + r"(?!\w)"
        # the wanted name as a whole word of the line, or of the line after it
        # when the line ends no statement; e.g. pcie_do_recovery in
        # `pci_ers_result_t pcie_do_recovery(struct pci_dev *dev,`
        if not re.search(pattern, text) and not (
            re.search(pattern, following) and not text.rstrip().endswith(";")
        ):
            problems.append(
                f"{name}: {location} does not spell {wanted}:"
                f" {text.strip()[:70]!r}"
            )
    return problems


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
        "--tags",
        help="the tags file (default: <tree>/tags when readtags is installed)",
    )
    parser.add_argument(
        "--no-tags", action="store_true", help="search with git grep only"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("resolve")
    r.add_argument("names", nargs="+", metavar="NAME")
    c = sub.add_parser("check")
    c.add_argument("tsv")
    args = parser.parse_args(argv)
    tree = tree_or_exit(ROOT, args.tree)
    if args.command == "check":
        problems = check(tree, args.tsv)
        for problem in problems:
            print(problem, file=sys.stderr)
        if problems:
            raise SystemExit(1)
        return
    tags = None
    if not args.no_tags:
        tags = args.tags or str(Path(tree, "tags"))
        if not (Path(tags).is_file() and shutil.which("readtags")):
            tags = None
    missing = 0
    for name in args.names:
        try:
            found = resolve(tree, name, tags)
        except ValueError as error:
            print(f"anchors: {error}", file=sys.stderr)
            missing += 1
            continue
        if not found:
            print(f"anchors: no definition found for {name}", file=sys.stderr)
            missing += 1
            continue
        for path, line, kind in sorted(set(found)):
            print(f"{name}\t{path}:{line}\t{kind}")
    if missing:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
