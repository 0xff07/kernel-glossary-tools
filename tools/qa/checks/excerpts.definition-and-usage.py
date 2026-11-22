"""excerpts.definition-and-usage: for every catalog entry, a unit reproduces
its anchored definition line, and another unit reproduces a line that spells
the symbol, its usage."""

import re

from tools.qa.inputs import measurement, violation
from tools.qa.page import MEMBER_KEY


def pattern_of(entry):
    words, member = entry["key"].split(), MEMBER_KEY.match(entry["key"])
    if len(words) == 2 and words[0] in ("struct", "enum", "union"):
        # a tagged key in a line of code, keyword and tag as whole words; e.g.
        # the key `struct pci_dev` in `struct pci_dev *dev`
        return re.compile(
            r"(?<!\w)" + words[0] + r"\s+" + re.escape(words[1]) + r"(?!\w)"
        )
    if member:
        # a member key's member as a whole word; e.g. error_detected for the
        # key `pci_error_handlers.error_detected`
        return re.compile(r"(?<!\w)" + re.escape(member.group(2)) + r"(?!\w)")
    # any other entry's name as a whole word; e.g. pcie_do_recovery in
    # `pcie_do_recovery(dev, state, cb);`, and not in `__pcie_do_recovery(dev)`
    return re.compile(r"(?<!\w)" + re.escape(entry["name"]) + r"(?!\w)")


def check(page, context):
    context.require("tree")
    seen = set()
    shown = used = 0
    for entry in page.catalog:
        if entry["name"] in seen:
            continue
        seen.add(entry["name"])
        path, line = entry["cited_path"], entry["cited_line"]
        if not path or not line:
            continue
        definition = next(
            (
                u
                for u in page.units
                if u.mapped
                and (
                    u.path == path
                    or u.path.rsplit("/", 1)[-1] == path.rsplit("/", 1)[-1]
                )
                and line in u.file_lines
            ),
            None,
        )
        if definition is None:
            yield violation(
                entry["line"],
                entry["name"],
                f"no excerpt reproduces the definition line {path}:{line} of"
                f" `{entry['key']}`; show it, or de-catalog the symbol with"
                " its reason in the notes",
            )
        else:
            shown += 1
        pattern = pattern_of(entry)
        usage = next(
            (
                u
                for u in page.units
                if u is not definition
                and any(pattern.search(text) for _n, text in u.reproduced)
            ),
            None,
        )
        if usage is None:
            yield violation(
                entry["line"],
                entry["name"],
                "no excerpt other than the definition's shows a use of"
                f" `{entry['key']}`; show one, or de-catalog the symbol with"
                " its reason in the notes",
            )
        else:
            used += 1
    yield measurement(
        None,
        None,
        f"catalog: {len(seen)} symbols, {shown} with their definition excerpt,"
        f" {used} with a usage excerpt",
    )
