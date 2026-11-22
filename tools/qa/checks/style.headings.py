"""style.headings: a level 3 or 4 heading under DETAILS that asks or opens on
why, how, where or what."""

import re

from tools.qa.inputs import rule_body, style_rows, violation


def check(page, context):
    details = page.section("DETAILS")
    if details is None:
        return
    rows, _lists = style_rows(
        rule_body(context, "style.headings"), "style.headings"
    )
    # the rule's one pattern, the first row of its table, without regard to
    # case; e.g. the row `^(why|how|where|what)\b|\?$` finds `How the walk
    # ends` and `Is the lock held?`
    pattern = re.compile(rows[0][0], re.I)
    for n, _tag, text, kind, _region, level in page.view_rows():
        if (
            kind == "heading"
            and level in (3, 4)
            and details.start < n <= details.end
            and pattern.search(text)
        ):
            yield violation(
                n,
                text,
                "a heading that asks or opens on Why, How, Where or What; a"
                " DETAILS heading is a declarative clause",
            )
