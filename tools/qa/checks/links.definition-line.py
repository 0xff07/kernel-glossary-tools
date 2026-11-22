"""links.definition-line: a plain C identifier in prose with no linked
occurrence earlier in its paragraph is a candidate; with the tree, every cited
link lands where the rule says (the anchors procedure), and every catalog entry
takes the form its trace decides."""

import collections
import re

from tools.qa import page as pagemod
from tools.qa.inputs import candidate, measurement
from tools.qa.page import symbol_name
from tools.qa.source import anchors, catalog_forms

# an identifier that stands alone in prose, with or without `()`, no path or
# member around it, group 1 the token; e.g. `pci_walk_bus()` in `calls
# pci_walk_bus() first`, and not the pci of `drivers/pci/bus.c`
PLAIN_TOKEN = re.compile(
    r"(?<![\w./-])([A-Za-z_]\w*(?:\(\))?)(?![\w/-]|\.[A-Za-z])"
)
# a file suffix, the sign that a token is a file's name; e.g. the `.c` of
# `probe.c` and the `.rst` of `pci.rst`
FILE_SUFFIX = re.compile(r"\.(?:c|h|S|rst|txt|yaml|json|py|sh|md)\b")
# a commit cited with its subject in parentheses, the id plain or linked; e.g.
# `commit 1cbc5e25fb70 ("PCI/ERR: Fix uevent")` and `Commit
# [1cbc5e25fb70](https://x) ("PCI/ERR: Fix uevent")`
COMMIT_SUBJECT = re.compile(
    r"\b[Cc]ommit (?:\[`?[0-9a-f]{10,40}`?\]\([^)\s]*\)|[0-9a-f]{10,40})"
    r" \([^)\n]*\)"
)


def plain_mask(raw):
    def blank(match):
        return " " * len(match.group(0))

    out = COMMIT_SUBJECT.sub(blank, raw)
    out = pagemod.LINK.sub(blank, out)
    out = pagemod.CODE_SPAN.sub(blank, out)
    out = pagemod.QUOTED.sub(blank, out)
    if pagemod.CONFIG is not None:
        out = pagemod.CONFIG.location_mask.sub(blank, out)
    return pagemod.COLON_PAIR.sub(blank, out)


def check(page, context):
    for n in page.prose_lines(("prose", "reference")):
        raw = page.lines[n - 1]
        linked = {}
        for match in pagemod.LINK.finditer(raw):
            name = symbol_name(match.group(1).strip().strip("`").lstrip("&*"))
            linked.setdefault(name, match.start())
        masked = plain_mask(raw)
        for match in PLAIN_TOKEN.finditer(masked):
            token = match.group(1)
            name = token[:-2] if token.endswith("()") else token
            if not (
                "_" in name
                or token.endswith("()")
                or page.profile.config_re.match(name)
            ):
                continue
            if name.strip("_") == "" or FILE_SUFFIX.match(
                raw[match.end() : match.end() + 6]
            ):
                continue
            if name in linked and linked[name] < match.start():
                continue
            yield candidate(
                n,
                token,
                f"plain identifier `{token}`; link it, or write it as a span"
                " under a licence for bare spans",
            )
    tree = context.require("tree")
    checked = collections.Counter()
    yield from anchors(page, context, tree, checked)
    yield from catalog_forms(page, context, tree)
    yield measurement(
        None,
        None,
        "anchors checked: "
        + ", ".join(f"{k} {v}" for k, v in sorted(checked.items())),
    )
