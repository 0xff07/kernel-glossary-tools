#!/usr/bin/env python3
"""Print the reading aids a manual rule asks for: the prose view, the regions,
the block map, the skim and the inventories (openers, closers, post-fence,
members, unreproduced, reshow, enumerations, claims, headings, figures, spine,
writes). A view prints and decides nothing; it writes no file."""

import argparse
from pathlib import Path
import re
import sys

if not __package__:
    # run as a script: make the repository's packages importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.qa.inputs import Context
from tools.qa.page import (
    Page,
    claim_sentences,
    first_sentence,
    last_sentence,
    mark_alphabet,
    readable,
    readable_sentences,
    word_count,
)
from tools.qa.source import touched

ROOT = Path(__file__).resolve().parents[2]

WRITE_CALLS = (
    "WRITE_ONCE",
    "smp_store_release",
    "xchg",
    "cmpxchg",
    "try_cmpxchg",
    "atomic_set",
    "atomic_or",
    "atomic_and",
    "atomic_xchg",
    "atomic_fetch_and",
    "atomic_fetch_or",
    "atomic_inc",
    "atomic_dec",
    "atomic_inc_return",
    "atomic_dec_return",
    "set_bit",
    "clear_bit",
    "change_bit",
    "assign_bit",
    "__set_bit",
    "__clear_bit",
    "memset",
    "memcpy",
    "swap",
    "resource_set_range",
    "resource_set_size",
    "list_add",
    "list_add_tail",
    "list_del",
    "list_del_init",
    "list_move",
    "list_move_tail",
    "kfree",
    "kzalloc_obj",
    "kzalloc",
)


def writes(page, context, fields):
    """(path, file line, page line, what, text) for every line of a mapped unit
    that assigns to one of the fields (any `x->field` or `x.field` on the left
    of an assignment operator) or calls a write helper with the field among its
    arguments; with no fields, every such assignment and call of a shown unit.
    """
    names = "|".join(re.escape(f) for f in fields) if fields else r"\w+"
    # an assignment to a field: an object, `->` or `.`, the field and an
    # assignment operator, `==` set aside, groups 1 to 3; e.g. `port->clx =
    # clx;` gives port, clx and `=`, and `sw->flags |= x;` gives sw, flags and
    # `|=`
    assign = re.compile(
        r"\b(\w+)\s*(?:->|\.)\s*(" + names + r")\s*([-+*/%|&^]?=|<<=|>>=)(?!=)"
    )
    # a call of one of the write helpers of WRITE_CALLS, group 1 the helper;
    # e.g. `atomic_set(&p->count, 0);` gives atomic_set
    call = re.compile(r"\b(" + "|".join(WRITE_CALLS) + r")\s*\(")
    rows = []
    for unit in page.units:
        if not unit.mapped:
            continue
        for page_line, file_line in unit.mapped:
            text = page.lines[page_line - 1]
            hit = assign.search(text)
            helper = call.search(text)
            # a helper counts only when the line also names one of the fields,
            # as a member access or as a word of its own; e.g. for the field
            # count: `atomic_set(&p->count, 0);`
            if (
                helper
                and fields
                and not re.search(r"(?:->|\.)\s*(?:" + names + r")\b", text)
                and not any(
                    re.search(r"\b" + re.escape(f) + r"\b", text)
                    for f in fields
                )
            ):
                helper = None
            if hit or helper:
                what = (
                    f"{hit.group(1)}->{hit.group(2)} {hit.group(3)}"
                    if hit
                    else ""
                ) + (
                    (" " if hit else "") + helper.group(1) + "()"
                    if helper
                    else ""
                )
                rows.append(
                    (unit.path, file_line, page_line, what, text.strip())
                )
    return rows


def mentions(name, text):
    """Whether the text carries the name as a word of its own."""
    # the name as a word of its own; e.g. pci_dev in `struct pci_dev *dev`, and
    # not in `pci_dev_put(dev)`
    return re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text)


def print_prose(page, context):
    for row in page.printed_view():
        print(row)


def print_spans_visible(page, context):
    for row in page.printed_view(spans_visible=True):
        print(row)


def print_raw(page, context):
    for n, line in enumerate(page.lines, 1):
        if page.fence_at(n) is None:
            print(f"{n}:{line}")


def print_regions(page, context):
    for n, line in enumerate(page.lines, 1):
        fence = page.fence_at(n)
        print(
            f"{n}:{page.region[n]:9}"
            f" {fence.kind if fence else page.cls[n]:10} {line}"
        )


def print_blocks(page, context):
    for sub in page.subsections:
        print(
            f"{sub['line']:5} [{sub['title']}] {sub['map']} "
            f" words={sub['words']} paras={sub['paragraphs']}"
            f" blocks={sub['blocks']}"
        )
    print(f"preamble: {' '.join(i.kind for i in page.preamble_items)}")


def print_skim(page, context):
    skim = page.skim()
    for text in skim["preamble"]:
        print(f"route: {text}")
    for sub in skim["subsections"]:
        print(f"\n### {sub['title']}  (page {sub['line']})")
        print(f"  first: {sub['opener']}")
        for recap in sub["recaps"]:
            print(f"  recap: {recap}")
        print(f"  last:  {sub['closer']}")


def print_openers(page, context):
    for n, _level, text in page.headings:
        k = n + 1
        while k <= page.n and page.cls[k] not in ("heading", "prose"):
            k += 1
        if k <= page.n and page.cls[k] == "prose":
            print(f"{k:5} [{text}] {first_sentence(page.lines[k - 1])}")


def print_closers(page, context):
    for sub in page.subsections:
        prose = [i for i in sub["items"] if i.kind == "P"]
        if prose:
            print(
                f"{prose[-1].line:5} [{sub['title']}]"
                f" {last_sentence(prose[-1].text)}"
            )


def print_post_fence(page, context):
    for fence in page.source_fences:
        below = page.prose_line_below(fence.end)
        label = fence.units[0].label if fence.units else "```"
        if below:
            opening = first_sentence(page.lines[below - 1])
        else:
            opening = "(no prose after the fence)"
        print(f"{fence.start:5} {label}: {opening}")


def prose_around(page, fence):
    """The readable text of the prose lines next above and next below a
    fence."""
    around = ""
    for k in (
        page.prose_line_above(fence.start),
        page.prose_line_below(fence.end),
    ):
        if k:
            around += " " + readable(page.lines[k - 1])
    return around


def print_members(page, context):
    """Per struct, union or enum whose definition line a unit shows: how many
    of the members shown the prose around the fence names."""
    for unit in page.units:
        if not unit.mapped:
            continue
        for construct in touched(context.tree, unit).values():
            if (
                construct["kind"] not in ("struct", "union", "enum")
                or construct["line"] not in unit.file_lines
            ):
                continue
            shown = [
                m["name"]
                for m in context.tree.members_of(unit.path, construct["name"])
                if m["line"] in unit.file_lines
            ]
            around = prose_around(page, unit.fence)
            named = [m for m in shown if mentions(m, around)]
            unnamed = [m for m in shown if m not in named]
            print(
                f"{unit.start:5} {construct['kind']}"
                f" {construct['name']}: shown {len(shown)}, named"
                f" {len(named)}"
                + (f"; unnamed: {', '.join(unnamed)}" if unnamed else "")
            )


def print_unreproduced(page, context):
    """The location links of the prose whose lines no excerpt shows."""
    for link in page.location_links():
        if (
            page.region[link.line] not in ("prose", "reference")
            or page.cls[link.line] != "prose"
        ):
            continue
        _file, first, last = link.location
        if not set(range(first, last + 1)) <= context.reproduced.get(
            link.cited[0], set()
        ):
            print(f"{link.line:5} {link.text}  ({link.cited[0]})")


def print_reshow(page, context):
    """The location links whose lines only another subsection shows, then
    the units an earlier unit already shows whole."""
    for link in page.location_links():
        sub = page.subsection_of(link.line)
        if sub is None or page.cls[link.line] != "prose":
            continue
        _file, first, last = link.location
        wanted = set(range(first, last + 1))
        here = set().union(
            *(
                u.file_lines
                for u in page.units
                if u.path == link.cited[0]
                and sub["line"] <= u.start <= sub["end"]
            )
        )
        if (
            wanted <= context.reproduced.get(link.cited[0], set())
            and not wanted <= here
        ):
            print(
                f"{link.line:5} {link.text} is shown only in another"
                " subsection"
            )
    seen = {}
    for unit in page.units:
        lines = unit.file_lines
        if len(lines) > 12 and lines <= seen.get(unit.path, set()):
            print(
                f"{unit.start:5} {unit.label}: {len(lines)} lines all"
                " shown by an earlier unit"
            )
        seen.setdefault(unit.path, set()).update(lines)


def print_enumerations(page, context):
    for n in page.prose_lines(("prose", "reference")):
        for sentence in readable_sentences(page.lines[n - 1]):
            if sentence.count(",") >= 3 and " and " in sentence:
                # every location a sentence cites, counted; e.g.
                # `drivers/pci/probe.c:120` and `pci.h:45`
                sites = len(
                    re.findall(r"\b[\w/.-]+\.(?:c|h|S|rst):\d+", sentence)
                )
                print(f"{n:5} ({sites} sites) {sentence}")


def print_claims(page, context):
    for n, sentence, kinds in claim_sentences(page):
        print(f"{n:5} {'/'.join(kinds):15} {sentence}")


def print_headings(page, context):
    details = page.section("DETAILS")
    for n, level, text in page.headings:
        if details and level in (3, 4) and details.start < n <= details.end:
            print(f"{n:5} {'#' * level} {text}  ({word_count(text)} words)")


def print_figure_list(page):
    """Every figure: its line, where it stands, its title, its marks."""
    marks_of = {s.line: s.marks for s in page.series() if s.kind == "figure"}
    for fence in page.figures:
        nonblank = [t.strip() for t in fence.body if t.strip()]
        titled = (
            len(nonblank) > 1
            and len(nonblank[1]) >= 3
            and set(nonblank[1]) <= {"─"}
        )
        sub = page.subsection_of(fence.start)
        where = sub["title"] if sub else page.section_of(fence.start).name
        marks = marks_of.get(fence.start, [])
        family = mark_alphabet(marks[0]) if marks else None
        print(
            f"{fence.start:5} [{where}]"
            f" {nonblank[0] if titled else '(untitled)'} "
            f" {len(set(marks))} marks" + (f", {family}" if family else "")
        )


def print_figure_spacing(page):
    """Every subsection: its figures, and what has passed since the last
    subsection that had one."""
    since = {"subsections": 0, "words": 0, "source": 0}
    for sub in page.subsections:
        print(
            f"{sub['line']:5} [{sub['title']}] figures={sub['figures']} "
            f" since the last figure: {since['subsections']} subsections,"
            f" {since['words']} words, {since['source']} source lines"
        )
        if sub["figures"]:
            since = {"subsections": 0, "words": 0, "source": 0}
        else:
            since["subsections"] += 1
            since["words"] += sub["words"]
            since["source"] += sub["source"]


def print_figures(page, context):
    print_figure_list(page)
    print_figure_spacing(page)


def longest_rising_run(indices):
    """The length of the longest run of entries, None aside, each greater
    than the one before it."""
    best = run = 0
    previous = None
    for k in indices:
        run = (
            run + 1
            if (k is not None and previous is not None and k > previous)
            else (1 if k is not None else 0)
        )
        best = max(best, run)
        previous = k
    return best


def print_spine(page, context):
    """Per subsection, the first catalog name its title or first paragraph
    carries; then how far the subsections follow the catalog's order."""
    names = page.catalog_names
    indices = []
    for sub in page.subsections:
        prose = [i for i in sub["items"] if i.kind == "P"]
        text = sub["title"] + " " + (readable(prose[0].text) if prose else "")
        found = next(
            (k for k, name in enumerate(names) if mentions(name, text)),
            None,
        )
        indices.append(found)
        print(
            f"{sub['line']:5} [{sub['title']}]"
            f" {names[found] if found is not None else '-'}"
        )
    print(
        "longest run of subsections in catalog order:"
        f" {longest_rising_run(indices)} of {len(indices)}"
    )


def print_writes(page, context):
    seen = set()
    for path, file_line, page_line, what, text in writes(
        page, context, context.fields
    ):
        if (path, file_line) in seen:
            continue
        seen.add((path, file_line))
        print(f"{page_line:5} {path}:{file_line}  {what:30} | {text[:90]}")
    skipped = [u for u in page.units if not u.mapped]
    print(
        f"-- {len(seen)} write sites in"
        f" {len([u for u in page.units if u.mapped])} mapped units"
        + (f"; {len(skipped)} units not mapped" if skipped else "")
    )


# every view by its name, in the order the command line lists them
PRINTERS = {
    "prose": print_prose,
    "spans-visible": print_spans_visible,
    "raw": print_raw,
    "regions": print_regions,
    "blocks": print_blocks,
    "skim": print_skim,
    "openers": print_openers,
    "closers": print_closers,
    "post-fence": print_post_fence,
    "members": print_members,
    "unreproduced": print_unreproduced,
    "reshow": print_reshow,
    "enumerations": print_enumerations,
    "claims": print_claims,
    "headings": print_headings,
    "figures": print_figures,
    "spine": print_spine,
    "writes": print_writes,
}
VIEWS = tuple(PRINTERS)
# the views that print nothing without the kernel tree
TREE_VIEWS = ("unreproduced", "reshow", "members")


def print_view(page, what, context):
    """Print one view; the exit status, 2 when a view that reads the tree has
    none."""
    if what in TREE_VIEWS and (context.tree is None or context.tree_reason):
        print(f"views: {context.tree_reason or 'no tree'}", file=sys.stderr)
        return 2
    PRINTERS[what](page, context)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("page", type=Path)
    parser.add_argument("what", choices=VIEWS)
    parser.add_argument(
        "--glossary-checkout",
        dest="skill",
        type=Path,
        default=ROOT,
        help=(
            "the checkout of this repository to work in (default: the one"
            " holding this file)"
        ),
    )
    parser.add_argument("--tree")
    parser.add_argument(
        "--fields",
        default="",
        help=(
            "for the writes view: the field names to list, comma-separated"
            " (default: every field)"
        ),
    )
    args = parser.parse_args(argv)
    page = Page.read(str(args.page), str(args.skill))
    context = (
        Context(page, str(args.skill), tree_option=args.tree)
        if args.what in TREE_VIEWS + ("writes",)
        else Context(page, str(args.skill), fixed=True)
    )
    context.fields = [f.strip() for f in args.fields.split(",") if f.strip()]
    status = print_view(page, args.what, context)
    if status:
        raise SystemExit(status)


if __name__ == "__main__":
    main()
