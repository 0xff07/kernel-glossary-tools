"""lead-summary.lead: the lead's words, sentences, paragraphs and figure within
their bands, and its shape."""

from tools.qa.inputs import limits_of, measured, violation
from tools.qa.page import first_sentence, sentences_of

RULE = "lead-summary.lead"
CARRIED = {
    "C": "a source excerpt",
    "T": "a table",
    "L": "a list",
    "Q": "a fence that is neither source nor figure",
}


def check(page, context):
    items = page.items_of(page.lead.start, page.lead.end)
    prose = [i for i in items if i.kind == "P"]
    words = sum(i.size for i in prose)
    sentences = sum(len(sentences_of(i.text)) for i in prose)
    figures = [i for i in items if i.kind == "D"]
    quote = first_sentence(prose[0].text) if prose else None
    line = prose[0].line if prose else None
    for finding in (
        measured(
            line,
            quote,
            "lead words",
            words,
            "words",
            **limits_of(context, RULE, "the lead", "words"),
        ),
        measured(
            line,
            quote,
            "lead sentences",
            sentences,
            "sentences",
            **limits_of(context, RULE, "the lead", "sentences"),
        ),
        measured(
            line,
            quote,
            "lead paragraphs",
            len(prose),
            "paragraphs",
            **limits_of(context, RULE, "the lead", "`p` items"),
        ),
    ):
        if finding:
            yield finding
    for figure in figures:
        finding = measured(
            figure.line,
            figure.text,
            "lead figure",
            figure.size,
            "lines",
            **limits_of(context, RULE, "a figure in the lead", "lines"),
        )
        if finding:
            yield finding
    for item in items:
        if item.kind in "CTLQ":
            yield violation(
                item.line,
                item.text,
                f"the lead carries {CARRIED[item.kind]}",
            )
    if len(figures) > 1:
        yield violation(
            figures[1].line,
            figures[1].text,
            f"the lead carries {len(figures)} figures; at most one",
        )
    if items and items[0].kind != "P":
        yield violation(
            items[0].line,
            items[0].text,
            f"the lead opens with {items[0].kind}; it opens with prose",
        )
