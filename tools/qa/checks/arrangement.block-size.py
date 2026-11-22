"""arrangement.block-size: an excerpt's reproduced lines and a figure's lines
within their bands, over DETAILS."""

from tools.qa.inputs import limits_of, measured

RULE = "arrangement.block-size"


def check(page, context):
    excerpt = limits_of(context, RULE, "a `c`", "reproduced lines")
    figure = limits_of(context, RULE, "a `d`", "lines")
    runs = [page.preamble_items] + [sub["items"] for sub in page.subsections]
    for items in runs:
        for item in items:
            if item.kind == "C":
                finding = measured(
                    item.line,
                    item.text,
                    "excerpt lines",
                    item.size,
                    "lines",
                    **excerpt,
                )
            elif item.kind == "D":
                finding = measured(
                    item.line,
                    item.text,
                    "figure lines",
                    item.size,
                    "lines",
                    **figure,
                )
            else:
                continue
            if finding:
                yield finding
