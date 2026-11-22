"""style.counting-headings: a level 3 or 4 heading outside the catalog sections
opening on a number."""

import re

from tools.qa.inputs import rule_body, style_rows, violation


def check(page, context):
    rows, _lists = style_rows(
        rule_body(context, "style.counting-headings"),
        "style.counting-headings",
    )
    # the rule's one pattern, the first row of its table, without regard to
    # case: a heading that opens with a digit or a number word; e.g. `3 ways to
    # map a BAR` and `Three ways to map a BAR`
    pattern = re.compile(rows[0][0], re.I)
    for n, _tag, text, kind, region, level in page.view_rows():
        if (
            kind == "heading"
            and level in (3, 4)
            and region != "catalog"
            and pattern.match(text)
        ):
            yield violation(
                n,
                text,
                "a heading opening on a number; the count opens the paragraph"
                " beneath it",
            )
