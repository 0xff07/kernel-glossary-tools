"""sections.other-sources: the section exists; every entry of an `### Added by`
block has the entry form, names a commit the tree knows and carries one of its
upstream trailers, or is a candidate; an empty block carries the sentence.
"""

import re

from tools.qa.inputs import candidate, rule_body, violation

# the heading of a model's block, group 1 the model; e.g. `### Added by Claude
# Opus 5.5` gives `Claude Opus 5.5`
ADDED_BY = re.compile(r"^### Added by (.+?)\s*$")


def check(page, context):
    body = rule_body(context, "sections.other-sources")
    # the sentence of an empty block as the rule file states it, group 1; e.g.
    # "empty-block sentence is `None: no commit behind this mechanism carries
    # an upstream link.`"
    empty_block = re.search(r"empty-block sentence is `([^`]+)`", body).group(
        1
    )
    # the length of a commit id as the rule file states it, groups 1 and 2;
    # e.g. `10 to 40 hex digits`
    digits = re.search(r"(\d+) to (\d+) hex digits", body)
    low, high = int(digits.group(1)), int(digits.group(2))
    # an entry of a block, `- [title (commit id)](url)`: group 1 the title, 2
    # the id, 3 the URL; e.g. `- [PCI/ERR: Fix uevent on failure to recover
    # (commit 1cbc5e25fb70)](https://patch.msgid.link/x)`
    entry_re = re.compile(
        rf"^- \[(.+?) \(commit ([0-9a-f]{{{low},{high}}})\)\]\((\S+)\)\s*$"
    )
    section = page.section("OTHER SOURCES")
    if section is None:
        yield violation(None, None, "no OTHER SOURCES section")
        return
    blocks, current = [], None
    for n in range(section.start + 1, section.end + 1):
        line = page.lines[n - 1]
        match = ADDED_BY.match(line)
        if match:
            current = (match.group(1), [])
            blocks.append(current)
            continue
        if line.startswith("### "):
            current = None
        if current is not None:
            current[1].append((n, line))
    commits = []
    for model, lines in blocks:
        bullets = [(n, l) for n, l in lines if l.startswith("- ")]
        for n, line in bullets:
            match = entry_re.match(line)
            if match:
                commits.append((n, line, match.group(2), match.group(3)))
            else:
                yield violation(
                    n,
                    line.strip(),
                    f"an entry of the block added by {model} is not"
                    " `[<subject> (commit <sha>)](<url>)`",
                )
        if not bullets and not any(
            l.strip() == empty_block for _n, l in lines
        ):
            yield violation(
                section.start,
                f"### Added by {model}",
                f"the block added by {model} has no entry and lacks the"
                f" sentence `{empty_block}`",
            )
    if not commits:
        return
    tree = context.require("tree")
    context.require("git")
    for n, line, sha, url in commits:
        if not tree.commit_exists(sha):
            yield violation(
                n, line.strip(), f"{sha[:12]}: no such commit in the tree"
            )
            continue
        trailers = tree.trailers(sha, page.profile.upstream_trailer)
        if url not in trailers:
            keys = page.profile.upstream_trailer
            keys = ", ".join(keys) if isinstance(keys, (list, tuple)) else keys
            yield candidate(
                n,
                line.strip(),
                f"{sha[:12]}: the URL is not one of the commit's {keys}:"
                f" trailers {trailers or '(none)'}; it stands only when the"
                " mailing-list archive's thread of the commit gives it",
            )
