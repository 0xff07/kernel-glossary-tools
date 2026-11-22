"""lead-summary.summary: SUMMARY's words, sentences, paragraphs and figure
within their bands, and its shape."""

from tools.qa.inputs import limits_of, measured, violation
from tools.qa.page import (
    TABLE_SEPARATOR,
    first_sentence,
    sentences_of,
    split_cells,
)

RULE = "lead-summary.summary"


def size_findings(context, prose, line, with_block):
    """SUMMARY's words, sentences and paragraphs against their bands."""
    quote = first_sentence(prose[0].text) if prose else None
    words = sum(i.size for i in prose)
    sentences = sum(len(sentences_of(i.text)) for i in prose)
    words_band = limits_of(
        context,
        RULE,
        (
            "summary beside its table or figure, both sides together"
            if with_block
            else "summary with no table and no figure"
        ),
        "words",
    )
    for finding in (
        measured(
            line,
            quote,
            "SUMMARY words" + (" beside its block" if with_block else ""),
            words,
            "words",
            **words_band,
        ),
        measured(
            line,
            quote,
            "SUMMARY sentences",
            sentences,
            "sentences",
            **limits_of(context, RULE, "summary", "sentences"),
        ),
        measured(
            line,
            quote,
            "SUMMARY paragraphs",
            len(prose),
            "paragraphs",
            **limits_of(context, RULE, "summary", "`p` items"),
        ),
    ):
        if finding:
            yield finding


def figure_findings(context, figures):
    for figure in figures:
        finding = measured(
            figure.line,
            figure.text,
            "SUMMARY figure",
            figure.size,
            "lines",
            **limits_of(context, RULE, "a figure in summary", "lines"),
        )
        if finding:
            yield finding


def block_findings(items, tables, figures):
    """What SUMMARY may not carry: a source excerpt or another fence, a table
    beside a figure, a second table, a second figure."""
    for item in items:
        if item.kind in "CQ":
            carried = (
                "a source excerpt"
                if item.kind == "C"
                else "a fence that is neither source nor figure"
            )
            yield violation(item.line, item.text, f"SUMMARY carries {carried}")
    if tables and figures:
        yield violation(
            tables[0].line,
            tables[0].text,
            "SUMMARY carries a table and a figure; one or the other",
        )
    if len(tables) > 1:
        yield violation(
            tables[1].line,
            tables[1].text,
            f"SUMMARY carries {len(tables)} tables; at most one",
        )
    if len(figures) > 1:
        yield violation(
            figures[1].line,
            figures[1].text,
            f"SUMMARY carries {len(figures)} figures; at most one",
        )


def table_findings(page, tables):
    for table in tables:
        rows = [
            split_cells(page.lines[k - 1])
            for k in range(table.line, table.end + 1)
            if not TABLE_SEPARATOR.match(page.lines[k - 1])
        ]
        body, columns = max(len(rows) - 1, 0), max(
            (len(r) for r in rows), default=0
        )
        if body > 6 or columns > 4:
            yield violation(
                table.line,
                table.text,
                f"SUMMARY table of {body} body rows and {columns} columns; at"
                " most six rows and four columns",
            )


def edge_findings(items):
    """Prose stands on both sides of SUMMARY's block."""
    if items and items[0].kind != "P":
        yield violation(
            items[0].line,
            items[0].text,
            f"SUMMARY opens with {items[0].kind}; prose stands on both sides"
            " of its block",
        )
    if items and items[-1].kind != "P":
        yield violation(
            items[-1].line,
            items[-1].text,
            f"SUMMARY ends with {items[-1].kind}; prose stands on both sides"
            " of its block",
        )


def check(page, context):
    section = page.section("SUMMARY")
    if section is None:
        yield violation(None, None, "no SUMMARY section")
        return
    items = page.items_of(section.start + 1, section.end)
    prose = [i for i in items if i.kind == "P"]
    figures = [i for i in items if i.kind == "D"]
    tables = [i for i in items if i.kind == "T"]
    line = prose[0].line if prose else section.start
    yield from size_findings(context, prose, line, bool(tables or figures))
    yield from figure_findings(context, figures)
    yield from block_findings(items, tables, figures)
    yield from table_findings(page, tables)
    yield from edge_findings(items)
