"""arrangement.paragraphs: each sentence's and paragraph's words within their
bands, the runs the rule names, and a blockless subsection within its words."""

from tools.qa.inputs import candidate, limits_of, measured, rule_body, scalar
from tools.qa.page import (
    RECAP,
    first_sentence,
    readable,
    readable_sentences,
    sentence_words,
    sentences_of,
)

RULE = "arrangement.paragraphs"


def runs_of(page):
    runs = [("preamble", page.preamble_items)]
    runs += [(sub["title"], sub["items"]) for sub in page.subsections]
    return runs


def check(page, context):
    body = rule_body(context, RULE)
    long_paragraph = scalar(
        body, r"three consecutive paragraphs over (\d+) words", RULE
    )
    word_limits = limits_of(context, RULE, "a `p`", "words")
    sentence_limits = limits_of(context, RULE, "a sentence", "words")
    blockless = limits_of(
        context, RULE, "a details subsection without a block", "words"
    )["review"]
    for _title, items in runs_of(page):
        for item in items:
            if item.kind != "P":
                continue
            quote = first_sentence(item.text)
            finding = measured(
                item.line,
                quote,
                "paragraph words",
                item.size,
                "words",
                **word_limits,
            )
            if finding:
                yield finding
            shown = readable_sentences(item.text)
            for k, sentence in enumerate(sentences_of(item.text)):
                quote = shown[k] if k < len(shown) else sentence
                finding = measured(
                    item.line,
                    quote,
                    "sentence words",
                    sentence_words(sentence),
                    "words",
                    **sentence_limits,
                )
                if finding:
                    yield finding
        last_prose = next((i for i in reversed(items) if i.kind == "P"), None)
        k = 0
        while k < len(items):
            if items[k].kind != "P":
                k += 1
                continue
            j = k
            while j + 1 < len(items) and items[j + 1].kind == "P":
                j += 1
            run = items[k : j + 1]
            if len(run) > 3:
                yield candidate(
                    run[0].line,
                    first_sentence(run[0].text),
                    f"{len(run)} paragraphs in a row with no block between; at"
                    " most three",
                )
            for a, b in zip(run, run[1:]):
                if (
                    len(sentences_of(a.text)) == 1
                    and len(sentences_of(b.text)) == 1
                ):
                    if (
                        RECAP.match(readable(a.text).lstrip())
                        and b is last_prose
                    ):
                        continue
                    yield candidate(
                        a.line,
                        first_sentence(a.text),
                        "two directly consecutive one-sentence paragraphs",
                    )
            for a, b, c in zip(run, run[1:], run[2:]):
                if (
                    a.size > long_paragraph
                    and b.size > long_paragraph
                    and c.size > long_paragraph
                ):
                    yield candidate(
                        a.line,
                        first_sentence(a.text),
                        f"three consecutive paragraphs over {long_paragraph}"
                        " words",
                    )
            k = j + 1
    for sub in page.subsections:
        if sub["blocks"] == 0 and sub["words"] > blockless:
            yield candidate(
                sub["line"],
                sub["title"],
                f"[{sub['title']}] has no block and {sub['words']} words; a"
                f" subsection without a block stays within {blockless}",
            )
