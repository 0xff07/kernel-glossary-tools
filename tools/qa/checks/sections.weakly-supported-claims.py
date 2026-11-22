"""sections.weakly-supported-claims: when the page has the section, it is the
last H2, opens with the rule's paragraph and holds nothing else but at most the
rule's number of one-line entries, each `- <class>, in "<DETAILS H3>": ...`
with a class from the rule's list and a heading the page has (or SUMMARY, or
the lead), every identifier span linked; an entry that names a length is a
candidate. A page without the section has nothing to check.
"""

import re

from tools.qa.inputs import candidate, rule_body, violation, word_list

# a size an entry states, a number of lines, words or sentences; e.g. `41
# lines` and `566 words`
SIZE = re.compile(r"\b\d+ (?:lines?|words?|sentences?)\b")
# a span that is one identifier, with or without `()`; e.g. `pci_walk_bus` and
# `pci_walk_bus()`
IDENTIFIER = re.compile(r"^[A-Za-z_]\w*(?:\(\))?$")


def line_findings(page, section, classes, opening):
    """The findings of the section's lines one by one; returns whether the
    opening paragraph stands and how many entries follow it."""
    # an entry of the section, `- <class>, in "<DETAILS H3>": text`, the place
    # also SUMMARY or the lead: group 1 the class, group 2 the heading; e.g. `-
    # Code not shown, in "The entry checks refuse a request": the page says`
    entry_re = re.compile(
        r"^- ("
        + "|".join(re.escape(c) for c in classes)
        + r'), in (?:"([^"]+)"|SUMMARY|the lead): \S'
    )
    h3 = {
        text
        for n, level, text in page.headings
        if level == 3 and page.section_of(n).name == "DETAILS"
    }
    opened, entries = False, 0
    for n in range(section.start + 1, section.end + 1):
        line = page.lines[n - 1]
        cls = page.class_of(n)
        if cls == "blank":
            continue
        if cls == "prose" and not opened and line == opening:
            opened = True
            continue
        if cls != "list":
            yield violation(
                n,
                line[:60],
                "the section holds its opening paragraph and the list of"
                " entries and nothing else",
            )
            continue
        entries += 1
        match = entry_re.match(line)
        if match is None:
            yield violation(
                n,
                line[2:].split(": ")[0][:80],
                'an entry is `- <class>, in "<DETAILS H3>": <claim, support,'
                " reach>` with a class from " + ", ".join(classes),
            )
            continue
        heading = match.group(2)
        if heading is not None and heading not in h3:
            yield violation(
                n, heading, f'no DETAILS H3 heading reads "{heading}"'
            )
        size = SIZE.search(line)
        if size:
            yield candidate(
                n,
                size.group(0),
                "a length is a matter of form, not a claim; an entry names"
                " what the page asserts on less support",
            )
    return opened, entries


def bare_span_findings(page, section):
    for text, n, _region, linked in page.span_occurrences:
        if (
            section.start < n <= section.end
            and not linked
            and IDENTIFIER.match(text)
            and (
                "_" in text
                or text.endswith("()")
                or page.profile.config_re.match(text)
            )
        ):
            yield violation(
                n,
                text,
                f"bare span `{text}` in an entry; every span of the section is"
                " linked at its definition line",
            )


def check(page, context):
    section = next(
        (s for s in page.sections if s.name in page.profile.claims_sections),
        None,
    )
    if section is None:
        return
    body = rule_body(context, "sections.weakly-supported-claims")
    classes = word_list(body, "classes")
    # the opening paragraph the rule file states, group 1 its text; e.g. "opens
    # with the paragraph `The claims below rest on less ...`"
    opening = re.search(r"opens with the paragraph `([^`]+)`", body).group(1)
    # the limit the rule file states, group 1 the number; e.g. `at most 10
    # entries`
    limit = int(re.search(r"at most (\d+) entries", body).group(1))
    if page.sections[-1] is not section:
        yield violation(
            section.start,
            section.name,
            f"{section.name} is not the last H2; {page.sections[-1].name}"
            " follows it",
        )
    opened, entries = yield from line_findings(page, section, classes, opening)
    if not opened:
        yield violation(
            section.start,
            section.name,
            "the section does not open with the paragraph"
            f" `{opening[:50]}...`",
        )
    if entries == 0:
        yield violation(
            section.start,
            section.name,
            "the section stands with no entry; a page whose every claim is"
            " supported has no such section",
        )
    if entries > limit:
        yield violation(
            section.start,
            section.name,
            f"{entries} entries, more than {limit}: the page owes"
            " verification, not disclosure",
        )
    yield from bare_span_findings(page, section)
