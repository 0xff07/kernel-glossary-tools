"""sections.coverage-form: every `- [` line of COVERAGE is a catalog entry, and
no key is a declaration or a traced member."""

from tools.qa.inputs import violation
from tools.qa.page import MEMBER_KEY, symbol_tag


def check(page, context):
    coverage = page.section("COVERAGE")
    if coverage is None:
        return
    entries = {entry["line"]: entry for entry in page.catalog}
    for n in range(coverage.start + 1, coverage.end + 1):
        line = page.lines[n - 1]
        entry = entries.get(n)
        if entry:
            key = entry["key"]
            if len(key.split()) > 1 and "(" not in key and not symbol_tag(key):
                yield violation(
                    n,
                    line,
                    f"catalog key `{key}` is a declaration; a member is keyed"
                    " `A.B` and any other symbol by its name",
                )
            elif entry["form"] == "traced" and MEMBER_KEY.match(key):
                yield violation(
                    n,
                    line,
                    f"a member entry is bare, `'{key}'`: git log -L finds no"
                    " member",
                )
        elif line.startswith("- ["):
            yield violation(
                n,
                line,
                "a COVERAGE bullet that is no catalog entry, `-"
                " [`'\\<KEY\\>':'PATH'`](URL): role` or `- [`'KEY'`](URL):"
                " role`",
            )
