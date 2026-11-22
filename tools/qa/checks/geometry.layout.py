"""geometry.layout: a figure line within the width the rule sets (a single-row
L-connector register excepted), and the joins, shifted verticals, frames and
floating runs of the rule's inspection procedure as candidates; each quotation
fence is a measurement so none is overlooked."""

import re

from tools.qa.geometry import analyze, cells
from tools.qa.inputs import (
    candidate,
    measurement,
    rule_body,
    scalar,
    violation,
)

# a border row of a box: an optional label, a left corner or tee, then border
# glyphs and spaces alone, group 1 the opening glyph; e.g. `┌──────┬──────┐`
# and `└──┘`
BORDER = re.compile(
    r"^\s*(?:[\w+.:]+\s+)?([┌├└╔╠╚╒╞╘╓╟╙])[─━═┬┴┼┐┤┘╤╧╪╥╨╫╗╣╝╕╡╛╖╢╜ ]*$"
)
TOP, DIVIDER, BOTTOM = "┌╔╒╓", "├╠╞╟", "└╚╘╙"
# an elbow of a callout, a horizontal line at a bottom corner; e.g. the `└─` of
# `└─ periodic floor` and `─┘`
ELBOW = re.compile(r"─┘|└─")
# the ruler of a register drawn in one row, `bit` and a digit; e.g. `bit 31
# 16 15       0`
RULER_LINE = re.compile(r"^\s*bit\s+\d")


def single_row_register(body):
    if not any(RULER_LINE.match(line) for line in body):
        return False
    borders = [
        (row, m.group(1)) for row, m in enumerate(map(BORDER.match, body)) if m
    ]
    tops = [r for r, c in borders if c in TOP]
    dividers = [r for r, c in borders if c in DIVIDER]
    bottoms = [r for r, c in borders if c in BOTTOM]
    if len(tops) != 1 or dividers or len(bottoms) != 1 or bottoms[0] < tops[0]:
        return False
    return any(ELBOW.search(line) for line in body[bottoms[0] + 1 :])


def check(page, context):
    width_limit = scalar(
        rule_body(context, "geometry.layout"),
        r"within (\d+) cells",
        "geometry.layout",
    )
    for fence in page.quotations:
        yield measurement(
            fence.start,
            "```" + fence.info,
            "a fence with no drawing character, read as a quotation or"
            " listing",
        )
    for fence in page.figures:
        body = fence.body
        register = single_row_register(body)
        for row, line in enumerate(body):
            width = len(cells(line))
            if width > width_limit:
                message = (
                    f"a figure line of {width} display columns; {width_limit}"
                    " is the width"
                )
                if register:
                    yield measurement(
                        fence.start + 1 + row,
                        line.strip(),
                        message
                        + " (a single-row L-connector register, which may run"
                        " wider)",
                    )
                else:
                    yield violation(
                        fence.start + 1 + row, line.strip(), message
                    )
        legends = {e.line for e in page.legends.get(fence.start, [])}
        drawing = [
            "" if fence.start + 1 + row in legends else line
            for row, line in enumerate(body)
        ]
        for row, issues in sorted(analyze(drawing).items()):
            columns = sorted({issue["column"] for issue in issues})
            for issue in issues:
                if "neighbor_row" in issue:
                    issue["neighbor_line"] = fence.start + issue.pop(
                        "neighbor_row"
                    )
            descriptions = list(
                dict.fromkeys(issue["message"] for issue in issues)
            )
            yield candidate(
                fence.start + 1 + row,
                body[row].strip(),
                "figure columns "
                + ", ".join(map(str, columns))
                + ": "
                + "; ".join(descriptions),
            )
