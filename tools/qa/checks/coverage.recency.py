"""coverage.recency: an example driver's directory has a commit within the
rule's window before the documented commit."""

import re

from tools.qa.inputs import candidate, measurement, rule_body
from tools.qa.source import within
from tools.qa.tree import date_of, years_between

WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


def check(page, context):
    # the number the rule file states in words, group 1; e.g. `within three
    # years` gives three
    found = re.search(
        r"within (\w+) years", rule_body(context, "coverage.recency")
    )
    window = WORDS.get(
        found.group(1), int(found.group(1)) if found.group(1).isdigit() else 3
    )
    profile = page.profile
    files = [
        f
        for f in page.cited_files()
        if any(f.startswith(p) for p in profile.example_consumer_paths)
        and f.rsplit("/", 1)[-1] not in ("Kconfig", "Makefile")
    ]
    entry = (context.subsystem or {}) if hasattr(context, "subsystem") else {}
    if entry.get("consumers") == "core":
        yield measurement(
            None,
            None,
            "the subsystem's consumers are core subsystems (consumers: core);"
            " it owes no example driver",
        )
        return
    own = entry.get("kernel_paths", [])
    examples = [f for f in files if not within(f, own)]
    if not examples:
        return
    tree = context.require("tree")
    context.require("git")
    head = tree.head_timestamp()
    seen = set()
    for path in examples:
        directory = path.rsplit("/", 1)[0] if "/" in path else path
        if directory in seen:
            continue
        seen.add(directory)
        newest = tree.newest_timestamp(directory)
        if newest is None:
            yield measurement(None, path, f"{directory}: no commit date")
            continue
        age = years_between(head, newest)
        if age > window:
            yield candidate(
                None,
                path,
                f"{directory}: newest commit {date_of(newest)}, more than"
                f" {window} years before HEAD ({date_of(head)}); an example"
                " driver is active",
            )
