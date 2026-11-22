"""style.label-colon: a short label ending in a colon inside a sentence or
heading of the lead, SUMMARY or DETAILS, and a prose line ending in a colon
that introduces no fence."""

import re

from tools.qa.inputs import candidate, rule_body
from tools.qa.page import last_sentence, readable, sentence_spans
from tools.qa.style import sweep_rows

# a colon and the whitespace after it, before a letter, a digit or `§`, the end
# of a label; e.g. the `: ` of `Scope: the frames of one node`
LABEL_COLON = re.compile(r":\s+(?=[A-Za-z0-9§])")


def check(page, context):
    body = rule_body(context, "style.label-colon")
    # the range the rule file states, groups 1 and 2; e.g. `holding 1 to 8
    # words`
    found = re.search(r"holding (\d+) to (\d+) words", body)
    low, high = int(found.group(1)), int(found.group(2))
    lines = set(range(page.lead.start, page.lead.end + 1))
    for name in ("DETAILS", "SUMMARY"):
        section = page.section(name)
        if section is not None:
            lines.update(range(section.start, section.end + 1))
    for n, tag, text, kind, _region, _level in sweep_rows(
        page, ("prose", "reference", "catalog", "heading")
    ):
        if n not in lines or tag == "[C] " or kind not in ("text", "heading"):
            continue
        raw = page.lines[n - 1] if kind == "text" else text
        spans = sentence_spans(text) if kind == "text" else [(0, len(text))]
        for start, end in spans:
            for match in LABEL_COLON.finditer(text, start, end):
                label = text[start : match.start()]
                # the words of the label, the tokens that hold a word
                # character; e.g. `Scope` is one word and `--` is none
                words = len([w for w in label.split() if re.search(r"\w", w)])
                if low <= words <= high:
                    yield candidate(
                        n,
                        readable(raw[start : match.end()]).strip(),
                        "a label ending in a colon:"
                        f" {readable(raw[start:match.start()]).strip()!r}; a"
                        " relation is one sentence with its own verb",
                    )
                    break
    for n in page.prose_lines(("prose", "reference")):
        if n not in lines:
            continue
        line = page.lines[n - 1]
        if not line.rstrip().endswith(":"):
            continue
        k = n + 1
        while k <= page.n and not page.lines[k - 1].strip():
            k += 1
        if k > page.n or not page.lines[k - 1].startswith("```"):
            yield candidate(
                n,
                last_sentence(line),
                "a paragraph ends in a colon that introduces no fence",
            )
