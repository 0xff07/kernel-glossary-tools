"""excerpts.cited-shown: a prose line whose unreproduced location links reach
two or more files is a candidate, kept only as a census."""

from tools.qa.inputs import candidate
from tools.qa.page import first_sentence


def check(page, context):
    context.require("tree")
    for n in page.prose_lines(("prose", "reference")):
        files = set()
        for link in page.links_on(n):
            if link.cls != "location" or not link.cited:
                continue
            path = link.cited[0]
            _file, first, last = link.location
            if not set(range(first, last + 1)) <= context.reproduced.get(
                path, set()
            ):
                files.add(path)
        if len(files) >= 2:
            yield candidate(
                n,
                first_sentence(page.lines[n - 1]),
                "a paragraph whose unreproduced location links reach"
                f" {len(files)} files: " + ", ".join(sorted(files)),
            )
