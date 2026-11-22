"""arrangement.open-close: a subsection opens and closes with prose, and no
block touches a heading, a list or another block."""

from tools.qa.inputs import candidate


def check(page, context):
    for sub in page.subsections:
        items = sub["items"]
        if not items:
            continue
        if items[0].kind != "P":
            yield candidate(
                items[0].line,
                sub["title"],
                f"[{sub['title']}] opens with {items[0].kind}; a subsection"
                " opens with a prose paragraph",
            )
        if items[-1].kind != "P":
            yield candidate(
                items[-1].line,
                sub["title"],
                f"[{sub['title']}] ends with {items[-1].kind}; a subsection"
                " closes with a prose paragraph",
            )
        dense = False
        for item in items:
            if item.kind == "P":
                dense = False
            elif item.kind in "CDTQ":
                if dense:
                    yield candidate(
                        item.line,
                        sub["title"],
                        f"[{sub['title']}] {item.kind}@{item.line} follows"
                        " another block, a list or a heading with no prose"
                        " between",
                    )
                dense = True
            elif item.kind in ("H", "L"):
                dense = True
