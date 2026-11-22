"""provenance.form: every source fence has one unit and provenance line, every
elision is well formed and indented like the line it resumes at, and no other
fence carries provenance."""

import re

from tools.qa.inputs import violation

# the indentation of a line, the spaces and tabs at its start; e.g. the two
# tabs of a line `\t\treturn 0;`
INDENT = re.compile(r"[ \t]*")


def check(page, context):
    profile = page.profile
    for fence in page.fences:
        if fence.kind == "source":
            first = next((t for t in fence.body if t.strip()), None)
            if first is None:
                yield violation(
                    fence.start, "```" + fence.info, "an empty source fence"
                )
                continue
            if not profile.provenance_re.match(first.strip()):
                yield violation(
                    fence.start + 1 + fence.body.index(first),
                    first.strip(),
                    "the first line of a source fence is its provenance"
                    f" `{profile.comment_open} path:LINE"
                    f" {profile.comment_close}`",
                )
            for unit in fence.units[1:]:
                yield violation(
                    unit.start,
                    page.lines[unit.start - 1].strip(),
                    "a source fence contains exactly one source unit and"
                    " provenance comment; introduce the next unit in a"
                    " separate fence",
                )
            for unit in fence.units:
                base = unit.path.rsplit("/", 1)[-1]
                if "/" not in unit.path and base not in (
                    "Kconfig",
                    "Makefile",
                ):
                    yield violation(
                        unit.start,
                        unit.label,
                        "a provenance path is the path from the tree root",
                    )
                for n, dropped, _resumes in unit.elisions:
                    if dropped is None:
                        yield violation(
                            n,
                            page.lines[n - 1].strip(),
                            "a malformed elision; the one form is `..."
                            f" {profile.comment_open} N lines, to :LINE"
                            f" {profile.comment_close}`",
                        )
                        continue
                    following = next(
                        (
                            text
                            for m, text in unit.body
                            if m > n and text.strip()
                        ),
                        None,
                    )
                    if following is None:
                        continue
                    want, have = INDENT.match(following).group(
                        0
                    ), INDENT.match(page.lines[n - 1]).group(0)
                    if want != have:
                        shape = (
                            " and ".join(
                                f"{want.count(c)}"
                                f" {name}{'s' if want.count(c) != 1 else ''}"
                                for c, name in (("\t", "tab"), (" ", "space"))
                                if want.count(c)
                            )
                            or "no indentation"
                        )
                        yield violation(
                            n,
                            page.lines[n - 1].strip(),
                            "an elision line is indented like the line it"
                            f" resumes at: {shape}, as"
                            f" `{following.strip()[:40]}` has",
                        )
        else:
            for k, text in enumerate(fence.body):
                if profile.provenance_re.match(text.strip()):
                    yield violation(
                        fence.start + 1 + k,
                        text.strip(),
                        f"a provenance line in a {fence.kind} fence; source is"
                        f" fenced as {profile.source_lang}",
                    )
