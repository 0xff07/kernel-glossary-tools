"""arrangement.subsection-size: a DETAILS subsection's prose words within their
band."""

from tools.qa.inputs import limits_of, measured

RULE = "arrangement.subsection-size"


def check(page, context):
    word_limits = limits_of(
        context, RULE, "a details subsection", "prose words"
    )
    for sub in page.subsections:
        finding = measured(
            sub["line"],
            sub["title"],
            f"[{sub['title']}] prose words",
            sub["words"],
            "words",
            **word_limits,
        )
        if finding:
            yield finding
