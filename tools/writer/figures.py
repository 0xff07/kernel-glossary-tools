#!/usr/bin/env python3
"""Insert a figure into a page after the draft, and re-assign the mark families
of the page's figures.

    figures.py insert PAGE FRAGMENT --at N [--check]
    figures.py rotate PAGE [--check]

insert splices FRAGMENT, a page fragment holding the paragraph above the
figure, one figure fence and, for a figure with a legend, the paragraph that
walks its marks, before page line N, which begins a paragraph, a heading, a
block or a list after a blank line. The drawing is indented four spaces when
the fragment leaves it flat. A fragment with a tab in its fence, a `c` info
string, no drawing character or a line wider than the layout rule allows is
refused, and so is a position inside a fence, between two consecutive pieces of
one source construct, in a catalog section, in a lead or SUMMARY that already
holds its one figure, or without a prose paragraph above the fence. The
figure's marks may be written in any figure family: after the splice every
marked figure whose family the marks rule refuses, one equal to the figure
before it or to another figure of its subsection, takes the first family in the
order ①, ➊, «1», «A», @1, @A that its marks fit and that its neighbours and its
subsection do not use, and the marks are rewritten in that figure's fence and
legend, in the prose after it up to the next marked figure or the end of its
subsection; a figure the rule accepts keeps its marks. rotate does the
renumbering alone. --check prints what would change and writes nothing. The
tool copies, places and renumbers; whether the figure is right is the checker's
question: run the figure rules it names (tools/qa/run.py --rule ...).
"""

import argparse
from pathlib import Path
import sys

if not __package__:
    # run as a script: make the repository's packages importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.checkout import absolute
from tools.qa.geometry import cells
from tools.qa.inputs import rule_body, scalar
from tools.qa.page import (
    FIGURE_CAPACITY,
    FIGURE_FAMILIES,
    MARK_ALPHABETS,
    Page,
    figure_mark,
    mark_alphabet,
    mark_index,
    mark_occurrences,
)

ROOT = str(absolute(__file__).parents[2])

FIGURE_RULES = (
    "geometry.layout",
    "geometry.unicode",
    "geometry.figure-tabs",
    "drawing.marks",
    "drawing.legend",
    "drawing.walk",
    "lifecycle.order",
    "arrangement.open-close",
)
INDENT = "    "


class FigureError(Exception):
    pass


def read(path):
    """(lines, trailing newline) of a UTF-8 file."""
    with open(path, "rb") as handle:
        text = handle.read().decode("utf-8")
    lines = text.split("\n")
    trailing = text.endswith("\n")
    if trailing:
        lines.pop()
    return lines, trailing


def write(path, lines, trailing):
    with open(path, "wb") as handle:
        handle.write(
            ("\n".join(lines) + ("\n" if trailing else "")).encode("utf-8")
        )


def symbol(family, index):
    """The mark of a figure family at an index counted from 1."""
    capacity = FIGURE_CAPACITY[family]
    if index < 1 or (capacity is not None and index > capacity):
        raise FigureError(f"the {family} family has no mark {index}")
    if family == "guillemet digits":
        return f"«{index}»"
    if family == "at digits":
        return f"@{index}"
    return dict(MARK_ALPHABETS)[family][index - 1]


def marked_figures(page):
    """[(fence, distinct marks)] of the page's marked figures in page order,
    legend marks first."""
    out = []
    for fence in page.figures:
        marks = []
        drawn = sorted(
            page.drawn_marks.get(fence.start, set()),
            key=lambda m: (mark_index(m), m),
        )
        for mark in [
            e.mark for e in page.legends.get(fence.start) or []
        ] + drawn:
            if mark not in marks:
                marks.append(mark)
        if marks:
            out.append((fence, marks))
    return out


def bound_of(page, n):
    """The last line a sentence may refer to the figure at line n from: its
    DETAILS subsection, else its section."""
    sub = page.subsection_of(n)
    return sub["end"] if sub is not None else page.section_of(n).end


def plan(page):
    """The renumbering the marks rule asks for, [(fence, old family, new
    family, {old mark: new mark}, (reach start, end))]: a figure keeps its
    family unless it equals the figure before it or another figure of its
    subsection, or its marks exceed the family; it then takes the first family
    in the order of the rule that fits and that neither neighbour nor its
    subsection uses. Also the figures the tool leaves to the hand.
    """
    figures = marked_figures(page)
    subsection = [page.subsection_of(fence.start) for fence, _marks in figures]
    keys = [sub["line"] if sub else None for sub in subsection]
    families = []
    for fence, marks in figures:
        found = {mark_alphabet(m) for m in marks}
        family = next(iter(found)) if len(found) == 1 else None
        families.append(
            family
            if family in FIGURE_CAPACITY and all(figure_mark(m) for m in marks)
            else None
        )
    current = list(families)
    steps, problems = [], []
    for k, (fence, marks) in enumerate(figures):
        if families[k] is None:
            problems.append(
                f"line {fence.start}: the marks {', '.join(marks)} are not one"
                " figure family; renumber the figure by hand"
            )
            continue
        size = len(marks)

        def fits(family):
            capacity = FIGURE_CAPACITY[family]
            return capacity is None or capacity >= size

        def taken(family, earlier):
            """Whether the figure before (earlier) or after this one, or
            another figure of its subsection on that side, uses the family; the
            figures before are settled, the figures after hold their current
            families.
            """
            neighbour = k - 1 if earlier else k + 1
            if 0 <= neighbour < len(figures) and current[neighbour] == family:
                return True
            side = range(k) if earlier else range(k + 1, len(figures))
            return any(
                keys[j] is not None
                and keys[j] == keys[k]
                and current[j] == family
                for j in side
            )

        # a clash is the later figure's to resolve, so a figure keeps its
        # family unless an earlier one has it
        if fits(families[k]) and not taken(families[k], True):
            continue
        choice = next(
            (
                f
                for f in FIGURE_FAMILIES
                if fits(f) and not taken(f, True) and not taken(f, False)
            ),
            None,
        )
        if choice is None:
            choice = next(
                (f for f in FIGURE_FAMILIES if fits(f) and not taken(f, True)),
                None,
            )
        if choice is None:
            problems.append(
                f"line {fence.start}: no family is left that the figures"
                " before it and its subsection do not use; renumber the"
                " figure by hand"
            )
            continue
        try:
            mapping = {m: symbol(choice, mark_index(m)) for m in marks}
        except FigureError as error:
            problems.append(
                f"line {fence.start}: {error}; renumber the figure by hand"
            )
            continue
        current[k] = choice
        next_start = (
            figures[k + 1][0].start if k + 1 < len(figures) else page.n + 1
        )
        reach = (
            fence.end + 1,
            min(next_start - 1, bound_of(page, fence.start)),
        )
        steps.append((fence, families[k], choice, mapping, reach))
    return steps, problems


def width(text):
    return len(cells(text))


def replace_marks(text, found, mapping, drawing):
    """The line with its marks replaced; on a drawing line the columns after
    each mark keep their place, a narrower mark padded with spaces and a wider
    one absorbing the spaces beside it, one space kept before a following
    glyph. Returns (text, absorbed) with absorbed False where no space beside a
    widened mark could take the difference.
    """
    absorbed = True
    for mark, offset in sorted(found, key=lambda item: -item[1]):
        new = mapping[mark]
        head, tail = text[:offset], text[offset + len(mark) :]
        delta = width(new) - width(mark)
        if drawing and tail:
            if delta < 0:
                tail = " " * (-delta) + tail
            elif delta > 0:
                run = len(tail) - len(tail.lstrip(" "))
                take = min(delta, run if run == len(tail) else max(run - 1, 0))
                tail = tail[take:]
                delta -= take
                if delta > 0:
                    # never the indent
                    run = (
                        len(head) - len(head.rstrip(" "))
                        if head.strip()
                        else 0
                    )
                    take = min(delta, max(run - 1, 0))
                    head = head[: len(head) - take] if take else head
                    delta -= take
                if delta > 0:
                    absorbed = False
        text = head + new + tail
    return text, absorbed


def rewrite(lines, page, steps):
    """Apply each step's mapping to its fence lines and the prose lines of its
    reach; (the page lines touched, the drawing lines whose columns the tool
    could not keep)."""
    touched, unkept = [], []
    for fence, _old, _new, mapping, (start, end) in steps:
        legend_lines = {e.line for e in page.legends.get(fence.start) or []}
        targets = list(range(fence.start + 1, fence.end)) + [
            n for n in range(start, end + 1) if page.cls[n] == "prose"
        ]
        for n in targets:
            text = lines[n - 1]
            found = mark_occurrences(text, marks=list(mapping))
            if not found:
                continue
            drawing = fence.start < n < fence.end and n not in legend_lines
            text, absorbed = replace_marks(text, found, mapping, drawing)
            if not absorbed:
                unkept.append(n)
            lines[n - 1] = text
            touched.append(n)
    return touched, unkept


def rotate(lines, skill, path="page.md"):
    """Re-assign the families in place; (report lines, problems, the steps
    taken with the page they were planned on)."""
    page = Page("\n".join(lines) + "\n", path, skill)
    steps, problems = plan(page)
    report = []
    for fence, old, new, mapping, (start, end) in steps:
        touched, unkept = rewrite(
            lines, page, [(fence, old, new, mapping, (start, end))]
        )
        prose = [n for n in touched if n > fence.end]
        report.append(
            f"figure at line {fence.start}: {old} -> {new}"
            f" ({', '.join(f'{a} -> {b}' for a, b in mapping.items())});"
            f" {len(touched) - len(prose)} fence line(s)"
            + (
                f" and prose line(s) {', '.join(map(str, prose))}"
                if prose
                else ""
            )
            + " rewritten"
        )
        for n in unkept:
            problems.append(
                f"line {n}: a wider mark found no space beside it to absorb;"
                " re-pad the drawing line so the columns after it keep their"
                " place"
            )
    return report, problems, (page, steps)


def unit_last_line(unit):
    """The last file line a unit reproduces, from its provenance line and
    counted elisions."""
    position = unit.line
    elided = {n: resumes for n, _dropped, resumes in unit.elisions if resumes}
    for n, _text in unit.body:
        if n in elided:
            position = elided[n]
        else:
            position += 1
    return position - 1


def check_fragment(text, skill):
    """The fragment's lines with the drawing indented, and what the fragment
    carries: (lines, has intro, titled, marked)."""
    frag = Page(text, "fragment.md", skill)
    if frag.problems:
        raise FigureError("the fragment: " + frag.problems[0]["message"])
    if len(frag.fences) != 1:
        raise FigureError(
            f"the fragment holds {len(frag.fences)} fences; it holds one"
            " figure fence"
        )
    fence = frag.fences[0]
    if fence.info == frag.profile.source_lang:
        raise FigureError(
            "the fence's info string is the source language; a figure is no"
            " excerpt"
        )
    if fence.kind != "figure":
        raise FigureError("the fence carries no drawing character")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    # zero-based indices of the body lines
    body = range(fence.start, fence.end - 1)
    if any("\t" in lines[i] for i in body):
        raise FigureError("a tab inside the fence; use spaces")
    if any(lines[i].strip() and not lines[i].startswith(INDENT) for i in body):
        for i in body:
            if lines[i].strip():
                lines[i] = INDENT + lines[i]
    limit = scalar(
        rule_body({"skill": skill}, "geometry.layout"),
        r"within (\d+) cells",
        "geometry.layout",
    )
    for i in body:
        width = len(cells(lines[i]))
        if width > limit:
            raise FigureError(
                f"fragment line {i + 1} is {width} display cells wide; {limit}"
                " is the width"
            )
    has_intro = any(frag.cls[n] == "prose" for n in range(1, fence.start))
    nonblank = [lines[i].strip() for i in body if lines[i].strip()]
    titled = (
        len(nonblank) > 1
        and set(nonblank[1]) <= {"─"}
        and len(nonblank[1]) >= 3
    )
    marked = bool(
        frag.legends.get(fence.start) or frag.drawn_marks.get(fence.start)
    )
    ends_in_prose = frag.cls[frag.n] == "prose"
    return lines, has_intro, titled, marked, ends_in_prose


def refuse_line(page, n):
    """Line `n` begins a paragraph, a heading, a block or a list after a
    blank line, outside every fence."""
    if not 1 <= n <= page.n + 1:
        raise FigureError(f"line {n} is outside the page (1 to {page.n + 1})")
    for k in (n - 1, n):
        fence = page.fence_at(k)
        if fence is not None and not (k == n and fence.start == n):
            raise FigureError(
                f"line {n} lies inside the fence at lines"
                f" {fence.start}-{fence.end}"
            )
    if n > 1 and page.lines[n - 2].strip():
        raise FigureError(
            f"line {n - 1} is not blank; N begins a paragraph, heading, block"
            " or list after a blank line"
        )
    if n <= page.n and not page.lines[n - 1].strip():
        raise FigureError(
            f"line {n} is blank; name the first line of what the figure goes"
            " before"
        )


def refuse_section(page, n):
    """The section of line `n` takes one more figure."""
    section = page.section_of(min(n, page.n))
    if section.region == "catalog":
        raise FigureError(
            f"line {n} lies in {section.name}, a catalog section, which holds"
            " no figure"
        )
    holds_figure = any(
        section.start <= f.start <= section.end for f in page.figures
    )
    if section.name == "lead" and holds_figure:
        raise FigureError("the lead already holds its one figure")
    if section.name == "SUMMARY" and (
        holds_figure
        or any(
            page.cls[k] == "table"
            for k in range(section.start, section.end + 1)
        )
    ):
        raise FigureError("SUMMARY already holds its one table or figure")


def refuse_surroundings(page, n, has_intro, ends_in_prose):
    """Prose stands above the figure and below it, and the figure does not
    part another figure from its walk paragraph."""
    if n <= page.n and page.cls[n] == "heading" and not ends_in_prose:
        raise FigureError(
            f"line {n} is a heading, so the figure would close the subsection"
            " before it; end the fragment with a prose paragraph or choose an"
            " earlier line"
        )
    if not has_intro and page.prose_line_above(n) is None:
        raise FigureError(
            "no prose paragraph stands above the fence; put the paragraph that"
            " names what the figure shows in the fragment"
        )
    for fence in page.figures:
        if (
            fence.end < n
            and page.legends.get(fence.start)
            and page.prose_line_below(fence.end) == n
        ):
            raise FigureError(
                f"line {n} walks the marks of the figure at line"
                f" {fence.start}; a figure never stands between a figure and"
                " its walk paragraph"
            )


def nearest_source_fence(page, lines):
    """The fence first met along `lines` before any heading, when it is a
    source fence."""
    for k in lines:
        if page.cls[k] == "heading":
            return None
        fence = page.fence_at(k)
        if fence is not None:
            return fence if fence.kind == "source" else None
    return None


def refuse_between_pieces(page, n):
    """A figure never stands inside source read in consecutive pieces."""
    above = nearest_source_fence(page, range(n - 1, 0, -1))
    below = nearest_source_fence(page, range(n, page.n + 1))
    if above is not None and below is not None and above.units and below.units:
        a, b = above.units[-1], below.units[0]
        if a.path == b.path and unit_last_line(a) + 1 == b.line:
            raise FigureError(
                f"line {n} lies between consecutive pieces of {a.path}"
                f" ({a.line}-{unit_last_line(a)} and {b.line} on); a figure"
                " never stands inside source read in pieces"
            )


def position_notes(page, n):
    """What a figure at line `n` changes around it, for the writer to
    re-read."""
    notes = []
    if (
        n <= page.n
        and page.fence_at(n) is not None
        and page.fence_at(n).kind == "source"
    ):
        notes.append(
            f"the excerpt at line {n} is now introduced by the fragment's last"
            " paragraph; read that introduction against the excerpt rules"
        )
    sub = page.subsection_of(n) if n <= page.n else None
    if sub is not None and sub["figures"]:
        notes.append(
            f"the subsection [{sub['title']}] now holds {sub['figures'] + 1}"
            " figures; each carries its title"
        )
    return notes


def check_position(page, n, has_intro, ends_in_prose):
    """Refuse a position the rules refuse; the notes a writer re-reads
    afterwards."""
    refuse_line(page, n)
    refuse_section(page, n)
    refuse_surroundings(page, n, has_intro, ends_in_prose)
    refuse_between_pieces(page, n)
    return position_notes(page, n)


def insert(page_path, fragment_path, n, skill, check=False):
    lines, trailing = read(page_path)
    page = Page("\n".join(lines) + "\n", page_path, skill)
    with open(fragment_path, "rb") as handle:
        fragment = handle.read().decode("utf-8")
    frag_lines, has_intro, titled, marked, ends_in_prose = check_fragment(
        fragment, skill
    )
    notes = check_position(page, n, has_intro, ends_in_prose)
    if not titled:
        notes.append(
            "the figure carries no title line over a ──── rule; every figure"
            " carries one"
        )
    while frag_lines and not frag_lines[-1].strip():
        frag_lines.pop()
    while frag_lines and not frag_lines[0].strip():
        frag_lines.pop(0)
    new = (
        lines[: n - 1]
        + frag_lines
        + ([""] if n <= len(lines) else [])
        + lines[n - 1 :]
    )
    report = [
        f"inserted {len(frag_lines)} line(s) at {n}-{n + len(frag_lines) - 1}"
        + (" (marked)" if marked else " (unmarked)")
    ]
    rotated, problems, planned = rotate(new, skill, page_path)
    report += rotated
    if not check:
        write(page_path, new, trailing)
    return report, notes, problems


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("command", choices=["insert", "rotate"])
    parser.add_argument("page")
    parser.add_argument("fragment", nargs="?")
    parser.add_argument(
        "--at", type=int, help="insert: the page line the fragment goes before"
    )
    parser.add_argument(
        "--glossary-checkout",
        dest="skill",
        default=ROOT,
        help=(
            "the checkout of this repository to work in (default: the one"
            " holding this file)"
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="print what would change and write nothing",
    )
    args = parser.parse_args(argv)
    try:
        if args.command == "insert":
            if not args.fragment or args.at is None:
                parser.error("insert takes PAGE FRAGMENT --at N")
            report, notes, problems = insert(
                args.page, args.fragment, args.at, args.skill, check=args.check
            )
        else:
            lines, trailing = read(args.page)
            report, problems, planned = rotate(lines, args.skill, args.page)
            notes = []
            if not args.check:
                write(args.page, lines, trailing)
    except (FigureError, OSError, UnicodeError, ValueError) as error:
        raise SystemExit(f"refused: {error}")
    for line in report:
        print(("would: " if args.check else "") + line)
    if not report or len(report) == 1 and args.command == "rotate":
        print("no family changes")
    for note in notes:
        print(f"note: {note}")
    for problem in problems:
        print(f"by hand: {problem}")
    print(
        "then: python3 tools/qa/run.py "
        + args.page
        + " "
        + " ".join(f"--rule {r}" for r in FIGURE_RULES)
    )


if __name__ == "__main__":
    main()
