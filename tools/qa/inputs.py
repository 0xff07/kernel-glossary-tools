"""What a checker gets beside the page: the run context, the finding helpers
and the readers that take a rule's thresholds, patterns and word lists from its
own rule file, so that a checker carries none.

A checker is `check(page, context)`. It returns or yields findings, each
`{"line": int | None, "quote": str | None, "message": str, "kind": "violation"
| "candidate" | "measurement"}` (`kind` defaults to violation). It asks for an
input with `context.require(name)`; a missing input raises `Missing`, and the
runner keeps the findings yielded before it and reports the rule incomplete.
"""

from pathlib import Path
import re

from tools.checkout import absolute

from . import page as pagemod
from .tree import FactsError, GitError, Tree, map_units, resolve_tree, validate

ROOT = pagemod.ROOT
RULE_DIRECTORIES = ("active", "inactive")


class Missing(Exception):
    """A required input is absent; the rule is incomplete from here."""


def violation(line, quote, message, **data):
    return {
        "line": line,
        "quote": quote,
        "message": message,
        "kind": "violation",
        **data,
    }


def candidate(line, quote, message, **data):
    return {
        "line": line,
        "quote": quote,
        "message": message,
        "kind": "candidate",
        **data,
    }


def measurement(line, quote, message, **data):
    return {
        "line": line,
        "quote": quote,
        "message": message,
        "kind": "measurement",
        **data,
    }


# ---- the rule file's tables
# -------------------------------------------------------------------------

# the separator row of a Markdown table; e.g. `|---|:---:|`
SEPARATOR = re.compile(r"^\|(\s*:?-{3,}:?\s*\|)+\s*$")
COUNTED = [
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
    "twenty",
]


class RuleTableError(Exception):
    """A rule file states a threshold or a pattern in a form the checkers
    cannot read."""


def unescape(cell):
    """A table cell's text: `\\|` is the pipe of the text, `\\\\|` a backslash
    and a pipe."""
    # an escaped pipe of a table cell, a backslash or two before `|`; e.g. `a
    # \| b` becomes `a | b`, and `a \\| b` becomes `a \| b`
    return re.sub(r"\\(\\?)\|", lambda m: "\\|" if m.group(1) else "|", cell)


def split_row(line):
    inner = line.strip()
    inner = inner[1:] if inner.startswith("|") else inner
    if inner.endswith("|") and not inner.endswith("\\|"):
        inner = inner[:-1]
    # cuts a table row at the pipes no backslash escapes; e.g. `a | b \| c | d`
    # gives three cells
    return [unescape(cell.strip()) for cell in re.split(r"(?<!\\)\|", inner)]


def tables(body):
    """[(header cells lower-cased, [row cells])] of the Markdown tables of a
    rule body, fences skipped."""
    out, current, fence = [], None, False
    for line in body.split("\n"):
        if line.startswith("```"):
            fence = not fence
            current = None
            continue
        if fence or not line.startswith("|"):
            current = None
            continue
        if current is None:
            current = ([cell.lower() for cell in split_row(line)], [])
            out.append(current)
        elif not SEPARATOR.match(line):
            current[1].append(split_row(line))
    return out


def rule_body(context, rule_id):
    """The body of a rule: the one the runner selected when it is this rule,
    else the file under guidelines/page/rules/."""
    rule = context.get("rule") if isinstance(context, dict) else None
    if rule is not None and getattr(rule, "id", None) == rule_id:
        return rule.body
    skill = context.get("skill", ROOT) if isinstance(context, dict) else ROOT
    for directory in RULE_DIRECTORIES:
        path = Path(
            skill, "guidelines", "page", "rules", directory, rule_id + ".md"
        )
        if path.is_file():
            text = path.read_bytes().decode("utf-8")
            if text.startswith("---\n"):
                end = text.find("\n---\n", 4)
                if end >= 0:
                    text = text[end + len("\n---\n") :]
            return text
    raise RuleTableError(f"no rule file for {rule_id}")


def _range(text, where):
    text = text.strip()
    # a range `N-M`, with a hyphen or an en dash, groups 1 and 2 its ends; e.g.
    # `60-120` and `60–120`
    found = re.match(r"^(\d+)[–-](\d+)$", text)
    if found:
        return int(found.group(1)), int(found.group(2))
    # `up to N`, group 1 the number; e.g. `up to 40`
    found = re.match(r"^up to (\d+)$", text)
    if found:
        return 0, int(found.group(1))
    # `under N`, group 1 the number; e.g. `under 600`
    found = re.match(r"^under (\d+)$", text)
    if found:
        return 0, int(found.group(1)) - 1
    # a number alone; e.g. `30`
    found = re.match(r"^(\d+)$", text)
    if found:
        return int(found.group(1)), int(found.group(1))
    raise RuleTableError(
        f"{where}: target `{text}` is no range the checkers read"
    )


def limits(cells, where):
    """The band of one row of a rule's `Unit | Measure | Target | Review
    candidate | Violation` table."""
    out = {"normal": _range(cells.get("target", ""), where)}
    review = cells.get("review candidate", "").split(";")[0]
    for part in [p.strip() for p in review.split(",") if p.strip()]:
        # `over N`, group 1 the number; e.g. `over 600`
        over = re.match(r"^over (\d+)$", part)
        # `under N`, group 1 the number; e.g. `under 60`
        under = re.match(r"^under (\d+)$", part)
        # a number or a range, group 1 its first number; e.g. `121` and
        # `121-220` give 121
        span = re.match(r"^(\d+)(?:[–-]\d+)?$", part)
        if over:
            out["review"] = int(over.group(1))
        elif under:
            out["review_below"] = int(under.group(1))
        elif span:
            out["review"] = int(span.group(1)) - 1
        else:
            raise RuleTableError(
                f"{where}: review candidate `{part}` is no range the checkers"
                " read"
            )
    violation_cell = cells.get("violation", "").strip()
    if violation_cell:
        # `over N` in the Violation cell; e.g. `over 220`
        over = re.match(r"^over (\d+)$", violation_cell)
        if not over:
            raise RuleTableError(
                f"{where}: violation `{violation_cell}` is no range the"
                " checkers read"
            )
        out["fail"] = int(over.group(1))
    return out


def bands(body, rule_id):
    """{(unit, measure): limits} of a rule's band table."""
    out = {}
    for header, rows in tables(body):
        if "unit" not in header or "measure" not in header:
            continue
        for cells in rows:
            row = dict(zip(header, cells))
            where = f"{rule_id} / {row.get('unit')} / {row.get('measure')}"
            out[
                (row.get("unit", "").lower(), row.get("measure", "").lower())
            ] = limits(row, where)
    return out


def limits_of(context, rule_id, unit, measure):
    """The limits of one row of a rule's band table."""
    table = bands(rule_body(context, rule_id), rule_id)
    try:
        return dict(table[(unit.lower(), measure.lower())])
    except KeyError:
        raise RuleTableError(
            f"{rule_id} has no band row `{unit}` / `{measure}`"
        ) from None


def band(value, normal=None, review=None, fail=None, review_below=None):
    """("violation" | "candidate", description) for a measurement outside its
    band, or None."""
    if fail is not None and value > fail:
        return "violation", f"over {fail}"
    if review is not None and value > review:
        return "candidate", f"over {review}"
    if review_below is not None and value < review_below:
        return "candidate", f"under {review_below}"
    return None


def measured(line, quote, what, value, unit, **limits_):
    found = band(value, **limits_)
    if found is None:
        return None
    kind, description = found
    return {
        "line": line,
        "quote": quote,
        "message": f"{what}: {value} {unit}, {description}",
        "kind": kind,
    }


def word_list(body, name):
    """The words of a `` `<name>`: a, b, c. `` list of a rule body, in
    order."""
    # a word list of a rule body: a line that opens with the list's name in
    # backticks and angle brackets, group 1 the words up to the period that
    # ends them; e.g. for the name hedges, "`<hedges>`: perhaps, maybe,
    # likely." gives `perhaps, maybe, likely`
    match = re.search(
        r"^`<" + re.escape(name) + r">`: (.*?)\.(?: `|$)", body, re.M
    )
    if not match:
        raise RuleTableError(f"the rule has no `<{name}>` word list")
    words = []
    for part in match.group(1).split(","):
        part = part.strip()
        # a run of words given by its two ends, groups 1 and 2; e.g. `one
        # through ten`
        span = re.match(r"^(\w+) through (\w+)$", part)
        if span and span.group(1) in COUNTED and span.group(2) in COUNTED:
            words += COUNTED[
                COUNTED.index(span.group(1)) : COUNTED.index(span.group(2)) + 1
            ]
        else:
            words.append(part)
    return words


def expand(template, lists):
    """A pattern with its `<word list>` placeholders filled in."""
    # a placeholder of a pattern, a word list's name in angle brackets,
    # replaced by the list's words as an alternation; e.g. with the list hedges
    # of perhaps and maybe, `\b(<hedges>)\b` becomes `\b(perhaps|maybe)\b`
    return re.sub(
        r"<([a-z ]+)>",
        lambda m: "|".join(re.escape(w) for w in lists[m.group(1)]),
        template,
    )


def style_rows(body, rule_id):
    """The rows of a rule's `Pattern | Kind | Scope | Unless | Exception`
    table: [(pattern or None for a prose cell, kind, scope text, [(unless
    pattern, flags)], flags)].
    """
    lists = {}
    # the name of every word list the rule body defines; e.g. "`<hedges>`:
    # perhaps, maybe." gives hedges
    for name in re.findall(r"^`<([a-z ]+)>`:", body, re.M):
        lists[name] = word_list(body, name)
    out = []
    for header, rows in tables(body):
        if "pattern" not in header or "kind" not in header:
            continue
        for cells in rows:
            row = dict(zip(header, cells))
            # a Pattern cell that is one backticked text, group 1 the pattern;
            # e.g. the cell "`\bvery\b`" gives `\bvery\b`, and a cell of prose
            # gives none
            pattern = re.fullmatch(r"`(.*)`", row.get("pattern", "").strip())
            kind = {"violation": "violation", "candidate": "candidate"}.get(
                row.get("kind", "").strip()
            )
            if kind is None:
                raise RuleTableError(
                    f"{rule_id}: kind `{row.get('kind')}` is neither violation"
                    " nor candidate"
                )
            unless = []
            cell = row.get("unless", "")
            # every backticked pattern of an Unless cell; e.g. "`\bat least\b`
            # before it" gives `\bat least\b`
            for found in re.findall(r"`([^`]+)`", cell):
                unless.append(
                    (
                        expand(found, lists),
                        0 if "case-sensitively" in cell else re.I,
                    )
                )
            out.append(
                (
                    expand(pattern.group(1), lists) if pattern else None,
                    kind,
                    row.get("scope", "").strip(),
                    unless,
                    re.I,
                )
            )
    return out, lists


def scalar(body, pattern, rule_id):
    """One number a rule states in words, by a pattern with one group."""
    # the caller's pattern, whose one group is the number; e.g. `within (\d+)
    # lines` on a rule that says `within 40 lines` gives 40
    found = re.search(pattern, body)
    if not found:
        raise RuleTableError(f"{rule_id} does not state `{pattern}`")
    return int(found.group(1))


# ---- the run context
# -----------------------------------------------------------------------------


def subsystem_entries(skill):
    """[{name, dir, kernel_paths, consumers}] of guidelines/subsystems.md;
    consumers is `drivers` unless the entry says `core`."""
    path = Path(skill, "guidelines", "subsystems.md")
    try:
        lines = path.read_text(encoding="utf-8").split("\n")
    except OSError:
        return []
    entries, current = [], None
    for line in lines:
        if line.startswith("## "):
            current = {
                "name": line[3:].strip(),
                "dir": None,
                "kernel_paths": [],
                "consumers": "drivers",
            }
            entries.append(current)
            continue
        # a line of a subsystem entry that the checkers read, group 1 the key
        # and group 2 its value; e.g. "- dir: `pci`" gives dir and "`pci`"
        match = (
            re.match(r"^- (dir|kernel_paths|consumers): (.*)$", line)
            if current is not None
            else None
        )
        if match:
            # the backticked values of that line; e.g. "`drivers/pci/`,
            # `include/linux/pci.h`" gives the two paths
            values = re.findall(r"`([^`]+)`", match.group(2))
            if match.group(1) == "dir":
                current["dir"] = values[0] if values else None
            elif match.group(1) == "consumers":
                current["consumers"] = (
                    values[0] if values else match.group(2)
                ).strip()
            else:
                current["kernel_paths"] = values
    return [e for e in entries if e["dir"]]


def page_within(page_path, skill):
    """(top directory under docs/, group/slug.md) or (None, base name)."""
    page, base = absolute(page_path), absolute(skill)
    if base in page.parents:
        relative = page.relative_to(base).as_posix()
        if relative.startswith("docs/") and relative.endswith(".md"):
            parts = relative[len("docs/") : -3].split("/")
            if len(parts) >= 2:
                return parts[0], "/".join(parts[1:]) + ".md"
    return None, Path(page_path).name


def scope_names(spec_path, within):
    """The scope names of the page's `md kg:scope page=<group/slug>` fence, or
    None without one."""
    if not spec_path or not Path(spec_path).is_file():
        return None
    key = within[:-3] if within.endswith(".md") else within
    ticks, wanted, body = 0, False, []
    with open(spec_path, encoding="utf-8") as handle:
        for line in handle.read().split("\n"):
            # a line that opens or closes a fence: group 1 the backticks, group
            # 2 the info string; e.g. "```md kg:scope page=rc/portdrv/dpc"
            fence = re.match(r"^(`{3,})(.*)$", line)
            if ticks == 0:
                if fence:
                    ticks = len(fence.group(1))
                    # the info string of a scope fence, group 1 its page; e.g.
                    # `md kg:scope page=rc/portdrv/dpc` gives rc/portdrv/dpc
                    scope = re.match(
                        r"^\s*md\s+kg:scope\s+page=(.+?)\s*$", fence.group(2)
                    )
                    wanted = bool(scope) and scope.group(1).strip() == key
                continue
            if (
                fence
                and len(fence.group(1)) >= ticks
                and not fence.group(2).strip()
            ):
                if wanted:
                    return pagemod.scope_names_of("\n".join(body))
                ticks, body = 0, []
                continue
            if wanted:
                body.append(line)
    return None


class Context(dict):
    """The resolved inputs of one run. A plain dict serves a page-only checker;
    `require` names the inputs a checker may ask for: tree, facts, git,
    scope."""

    def __init__(
        self,
        page,
        skill=ROOT,
        tree=None,
        tree_option=None,
        spec=None,
        scope=None,
        subsystem=None,
        fixed=False,
        extra=None,
    ):
        super().__init__(extra or {})
        self.page, self.skill = page, str(absolute(skill))
        self.profile = page.profile
        self.problems, self.notes = [], []
        top, within = page_within(page.path, self.skill)
        entries = subsystem_entries(self.skill)
        self.subsystem = next(
            (e for e in entries if e["dir"] == (subsystem or top)), None
        )
        self.tree, self.tree_reason = tree, None
        if tree is None and not fixed:
            found, how, candidate_path = resolve_tree(tree_option, self.skill)
            if found is None:
                self.tree_reason = (
                    f"no tree: {candidate_path} ({how}); pass --tree or set"
                    " KG_TREE"
                )
                (self.problems if how == "option" else self.notes).append(
                    self.tree_reason
                )
            else:
                try:
                    self.tree = Tree(found, self.profile)
                except GitError as error:
                    self.problems.append(str(error))
                    self.tree_reason = str(error)
        if self.tree is not None:
            try:
                found = validate(self.tree, page)
            except GitError as error:
                found = [str(error)]
            if found:
                self.problems.extend(found)
                self.tree_reason = "source validation failed: " + "; ".join(
                    found
                )
        self.reproduced = map_units(
            page, self.tree if self.tree_reason is None else None
        )
        self.scope, self.spec_path = scope, None
        if scope is None and not fixed:
            self.spec_path = (
                str(absolute(spec))
                if spec
                else (
                    str(Path(self.skill, "campaigns", top + ".md"))
                    if top
                    else None
                )
            )
            self.scope = scope_names(self.spec_path, within)

    def require(self, name):
        if name == "tree":
            if self.tree is None or self.tree_reason:
                raise Missing(self.tree_reason or "no tree")
            return self.tree
        if name == "git":
            self.require("tree")
            if not self.tree.git:
                raise Missing("the tree is not a git repository")
            return self.tree
        if name == "facts":
            tree = self.require("tree")
            if tree.facts_error:
                raise Missing(tree.facts_error)
            try:
                tree.tags(
                    next(
                        (
                            f
                            for f in self.page.cited_files()
                            if self.profile.is_source(f)
                        ),
                        "Kconfig",
                    )
                )
            except FactsError as error:
                raise Missing(str(error)) from error
            return tree
        if name == "scope":
            return self.scope
        raise ValueError(name)
