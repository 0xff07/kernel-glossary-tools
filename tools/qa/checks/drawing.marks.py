"""drawing.marks: one family per figure, counted without a gap and within the
family's capacity; two marked figures that follow each other, and the marked
figures of one subsection, use different families; an outline series uses a
recognized prose family, never a reserved one."""

from tools.qa.inputs import candidate, violation
from tools.qa.page import (
    FIGURE_CAPACITY,
    FIGURE_FAMILIES,
    RESERVED_MARKS,
    figure_mark,
    mark_alphabet,
    mark_index,
)


def marks_of(series):
    """(marks, families, family): the marks of a series with repeats in a
    row folded, the families they belong to, and the one family when every
    mark is of it."""
    marks = [
        m
        for k, m in enumerate(series.marks)
        if k == 0 or m != series.marks[k - 1]
    ]
    alphabets = sorted({mark_alphabet(m) for m in marks if mark_alphabet(m)})
    alphabet = (
        alphabets[0]
        if len(alphabets) == 1 and all(mark_alphabet(m) for m in marks)
        else None
    )
    return marks, alphabets, alphabet


def counts_without_gap(marks):
    return [mark_index(m) for m in marks] == list(range(1, len(marks) + 1))


def outline_findings(series, marks, alphabets, alphabet, previous):
    quote = marks[0] if marks else ""
    reserved = next(
        (m for m in marks if any(c in RESERVED_MARKS for c in m)), None
    )
    if reserved:
        yield violation(
            series.line,
            reserved,
            f"outline mark {reserved} is reserved for figures and"
            " their explanations",
        )
    elif len(alphabets) > 1:
        yield violation(
            series.line,
            quote,
            "one outline series uses more than one recognized mark family",
        )
    elif alphabet:
        if not counts_without_gap(marks):
            yield candidate(
                series.line,
                quote,
                "the outline counts from its family's first mark"
                " without a gap",
            )
        if alphabet == previous:
            yield candidate(
                series.line,
                quote,
                "consecutive outlines reuse the same mark family;"
                " rotate prose families independently of figures",
            )


def family_findings(page, series, marks, alphabet, previous, used):
    """A figure whose marks are of one figure family: its count against the
    family's capacity, its numbering, and its family against the figure
    before it and the figures of its subsection, which `used` records."""
    quote = marks[0] if marks else ""
    size = len(set(marks))
    capacity = FIGURE_CAPACITY[alphabet]
    if capacity is not None and size > capacity:
        yield violation(
            series.line,
            quote,
            f"{size} distinct marks exceed the {alphabet} capacity of"
            f" {capacity}",
        )
    if not counts_without_gap(marks):
        yield candidate(
            series.line,
            quote,
            "the figure counts from its family's first mark without a gap",
        )
    sub = page.subsection_of(series.line)
    key = sub["line"] if sub else None
    if previous is not None and alphabet == previous[0]:
        yield candidate(
            series.line,
            quote,
            f"the figure uses {alphabet} like the figure before it at"
            f" line {previous[1]}; two marked figures that"
            " follow each other use different families",
        )
    elif key is not None and alphabet in used.get(key, {}):
        yield candidate(
            series.line,
            quote,
            f"the figure uses {alphabet} like the figure at line"
            f" {used[key][alphabet]} of the same subsection; the"
            " marked figures of one subsection use different"
            " families",
        )
    if key is not None:
        used.setdefault(key, {}).setdefault(alphabet, series.line)


def check(page, context):
    previous_figure, previous_outline = None, None
    used = {}  # subsection start line -> {family: figure line}
    for series in page.series():
        marks, alphabets, alphabet = marks_of(series)
        if series.kind == "outline":
            yield from outline_findings(
                series, marks, alphabets, alphabet, previous_outline
            )
            previous_outline = alphabet
            continue
        invalid = [m for m in marks if not figure_mark(m)]
        if invalid:
            yield violation(
                series.line,
                invalid[0],
                "unsupported figure mark(s): "
                + ", ".join(dict.fromkeys(invalid)),
            )
        if len(alphabets) > 1:
            yield violation(
                series.line,
                marks[0] if marks else "",
                "one figure uses more than one mark family",
            )
        elif alphabet in FIGURE_FAMILIES and not invalid:
            yield from family_findings(
                page, series, marks, alphabet, previous_figure, used
            )
            previous_figure = (alphabet, series.line)
        else:
            previous_figure = None
