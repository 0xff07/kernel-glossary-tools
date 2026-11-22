"""coverage.scope-closure: every scope name is on the page; a name the page
carries nowhere is a candidate, read against the request."""

import re

from tools.qa.inputs import candidate, measurement


def check(page, context):
    names = context.require("scope")
    if names is None:
        yield measurement(
            None,
            None,
            "no scope fence for the page in the campaign spec; nothing to"
            " close",
        )
        return
    # the URL of every link, cut out so that a name spelled only inside a URL
    # does not count; e.g. "[`pci_dev`](https://x/bus.c#L5)" leaves
    # "[`pci_dev`]"
    text = re.sub(r"\]\([^)]*\)", "]", page.text)
    named = skipped = 0
    for name in names:
        # a scope name that is one identifier; e.g. `pci_walk_bus`, and not the
        # family `PCI_EXP_*`
        if not re.match(r"^[A-Za-z_]\w*$", name):
            skipped += 1
            yield measurement(
                None,
                name,
                f"scope span `{name}` gives no name (a family, an expression,"
                " a field or a value); not checked",
            )
            continue
        # the name as a whole word of the page's text; e.g. pci_walk_bus in
        # "calls `pci_walk_bus`", and not in `__pci_walk_bus`
        if re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text):
            named += 1
            continue
        yield candidate(
            None,
            name,
            f"scope symbol {name} is named nowhere on the page; name it as a"
            " seam or as left out with the reason, unless the request"
            " drops it",
        )
    yield measurement(
        None,
        None,
        f"scope: {len(names)} names, {named} on the page, {skipped} skipped",
    )
