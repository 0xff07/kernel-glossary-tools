"""links.commits: a hash after `commit` is a link whose text is the plain hash
and whose URL is the commit's page built from the full hash the tree
resolves."""

import re

from tools.qa.inputs import violation

# a commit id after the word commit, commits or and, in backticks or not: group
# 1 the word, group 3 the id; e.g. `commit 1cbc5e25fb70` and "and
# `9011f0667c93`"
HASH_AFTER_COMMIT = re.compile(
    r"\b([Cc]ommits?|and)\s+(`?)([0-9a-f]{10,40})\2(?!\w)"
)
# the word commit or commits; e.g. the first word of `Commit 1cbc5e25fb70
# changed it`
COMMIT_WORD = re.compile(r"\b[Cc]ommits?\b")


def check(page, context):
    tree = None
    for n in range(1, page.n + 1):
        if page.region[n] not in ("prose", "reference") or page.cls[n] not in (
            "prose",
            "table",
            "list",
        ):
            continue
        raw = page.lines[n - 1]
        for match in HASH_AFTER_COMMIT.finditer(raw):
            word, digest = match.group(1), match.group(3)
            if word == "and" and not COMMIT_WORD.search(raw[: match.start()]):
                continue
            yield violation(
                n,
                digest,
                f"commit {digest} is not linked; write `commit"
                f" [{digest}](<commit URL>)`",
            )
        for link in page.links_on(n):
            if link.cls != "commit":
                continue
            if link.backticked:
                yield violation(
                    n,
                    link.text,
                    "a commit link's text is the plain hash, not a span",
                )
            if tree is None:
                tree = context.require("tree")
                context.require("git")
            full = tree.full_sha(link.text)
            if not full:
                yield violation(
                    n,
                    link.text,
                    f"{link.text}: the tree resolves no commit for it",
                )
                continue
            wanted = page.profile.commit_url(full)
            if link.url != wanted:
                yield violation(
                    n, link.text, f"the URL is not the commit's page {wanted}"
                )
