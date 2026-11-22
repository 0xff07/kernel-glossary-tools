"""The style sweep shared by the style checkers: each reads its own rule file's
pattern table and sweeps the prose view of guidelines/page/page-model.md,
yielding one finding per match that no `unless` pattern encloses.
"""

import re

from .inputs import rule_body, style_rows
from .page import readable, sentence_spans

DEFAULT_REGIONS = ("prose", "reference", "catalog", "heading")


def sweep_rows(page, regions, spans_visible=False):
    for n, tag, text, kind, region, level in page.view_rows(spans_visible):
        if kind == "heading" and "heading" in regions:
            yield n, tag, text, kind, region, level
        elif kind == "text" and region in regions:
            yield n, tag, text, kind, region, level
        elif kind == "figure" and "figure" in regions:
            yield n, tag, text, kind, region, level


def enclosed(text, match, unless):
    for pattern, flags in unless:
        # every match of an Unless pattern in the text; a finding that lies
        # inside one is excused; e.g. the Unless pattern `at least` covers a
        # finding on the `least` of `at least two`
        for found in re.finditer(pattern, text, flags):
            if found.start() <= match.start() and match.end() <= found.end():
                return True
    return False


def quote_at(page, n, kind, text, match):
    """The sentence of the page line holding the match, readable; a heading or
    figure line whole."""
    if kind != "text":
        return readable(text).strip()
    raw = page.lines[n - 1]
    for start, end in sentence_spans(text):
        if start <= match.start() < end:
            return readable(raw[start:end]).strip()
    return readable(raw).strip()


def sweep(page, context, rule_id):
    """Every row of the rule's table over the prose view, the row's scope
    deciding the regions."""
    rows, _lists = style_rows(rule_body(context, rule_id), rule_id)
    for pattern, kind, scope, unless, flags in rows:
        if pattern is None:
            continue
        regions = DEFAULT_REGIONS + (("figure",) if "figure" in scope else ())
        spans_visible = "code spans" in scope
        # the row's pattern, compiled with the row's flags; e.g. the row
        # `\bvery\b` finds the `very` of `a very long line`
        regex = re.compile(pattern, flags)
        for n, _tag, text, row_kind, _region, _level in sweep_rows(
            page, regions, spans_visible
        ):
            for match in regex.finditer(text):
                if enclosed(text, match, unless):
                    continue
                where = " in a figure" if row_kind == "figure" else ""
                yield {
                    "line": n,
                    "quote": quote_at(page, n, row_kind, text, match),
                    "kind": kind,
                    "message": (
                        f"{rule_id.split('.')[1]}{where}: {match.group(0)!r}"
                    ),
                }
