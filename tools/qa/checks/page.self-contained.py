"""page.self-contained: no link to another page of the knowledge base, no
template residue outside a fence."""

import re

from tools.qa.inputs import violation

# the residue of a template or a draft: `{{`, or TODO, XXX or FIXME as a word
# unless `the`, `a` or `its` stands before it; e.g. `{{name}}` and `TODO:
# check`, and not `the TODO list`
RESIDUE = re.compile(
    r"\{\{|(?<![Tt]he )(?<![Aa] )(?<![Ii]ts )\b(TODO|XXX|FIXME)\b"
)


def check(page, context):
    for link in page.links:
        url = link.url.split("#")[0]
        # a URL with a scheme, which is no link to another page; e.g.
        # `https://x/page.md`, where `../zone/zone.md` has none
        if url.endswith(".md") and not re.match(
            r"^[a-z][a-z0-9+.-]*:", link.url
        ):
            yield violation(
                link.line,
                link.text,
                f"a link to another page of the knowledge base ({link.url}); a"
                " page points nowhere inside it",
            )
    for n, line in enumerate(page.lines, 1):
        if page.fence_at(n) is not None:
            continue
        for match in RESIDUE.finditer(line):
            yield violation(
                n,
                match.group(0),
                f"template residue {match.group(0)!r} outside a fence",
            )
