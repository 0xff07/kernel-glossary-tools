"""style.lists: no list under DETAILS or SUMMARY."""

from tools.qa.inputs import violation


def check(page, context):
    for name in ("DETAILS", "SUMMARY"):
        section = page.section(name)
        if section is None:
            continue
        for item in page.items_of(section.start + 1, section.end):
            if item.kind == "L":
                yield violation(
                    item.line,
                    item.text,
                    f"a list under {name}; the members of a set are one"
                    " flowing paragraph or a table",
                )
