#!/usr/bin/env python3
"""Validate rule metadata, local requirements, checker placement, the tables
the checkers read, current documentation references, the conventions each skill
repeats from CLAUDE.md and the direction of the layers: the standard names no
tool, and the standard and its tools never name the plugin layer."""

import argparse
from pathlib import Path
import re
import sys

if not __package__:
    # run as a script: make the repository's packages importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.rules import RuleError, load_rules, page_model

ROOT = Path(__file__).resolve().parents[1]


def table_problems(skill, rules):
    """A band or pattern table a checker could not read is a problem of the
    rule file, found before a run."""
    sys.path.insert(0, str(skill.parent if skill.name == "tools" else skill))
    try:
        from tools.qa.inputs import RuleTableError, bands, style_rows, tables
    except ImportError:
        return []
    problems = []
    for rule in rules:
        try:
            for header, _rows in tables(rule.body):
                if "unit" in header and "measure" in header:
                    bands(rule.body, rule.id)
                if "pattern" in header and "kind" in header:
                    style_rows(rule.body, rule.id)
        except RuleTableError as error:
            problems.append(f"{rule.path.relative_to(skill)}: {error}")
    return problems


def numbered_lines(path):
    return enumerate(path.read_text(encoding="utf-8").splitlines(), 1)


def duplicate_ids(rules):
    problems = []
    seen = {}
    for rule in rules:
        if rule.id in seen:
            problems.append(
                f"duplicate rule ID {rule.id}: {seen[rule.id]} and {rule.path}"
            )
        seen[rule.id] = rule.path
    return problems


def misplaced_rules(skill):
    """A rule file lies in active/ or inactive/, never beside them."""
    return [
        f"{path.relative_to(skill)}: move the rule into active/ or inactive/"
        for path in (skill / "guidelines" / "page" / "rules").glob("*.md")
    ]


def delegated_requirements(skill, rules, ids):
    """A requirement may not delegate its completion to another rule; IDs in
    a rule's title or comment are harmless."""
    problems = []
    for rule in rules:
        for number, line in enumerate(rule.body.splitlines(), 1):
            if line.startswith(("#", "<!--")):
                continue
            # every rule id a line names in backticks, lowercase words joined
            # by dots; e.g. "`sections.kconfig`" and "`coverage.scope-closure`"
            referenced = set(
                re.findall(r"`([a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)+)`", line)
            ) & ids - {rule.id}
            # every rule a line names by its file; e.g.
            # `guidelines/page/rules/active/sections.kconfig.md` gives
            # sections.kconfig
            referenced |= set(
                re.findall(
                    r"guidelines/page/rules/(?:active|inactive)"
                    r"/([a-z][a-z0-9.-]*)\.md",
                    line,
                )
            ) & ids - {rule.id}
            if referenced:
                problems.append(
                    f"{rule.path.relative_to(skill)}: body line {number}: keep"
                    " the requirement and its scope local"
                )
    return problems


def orphan_checkers(skill, ids):
    """A checker belongs to one rule, active or inactive; a file under
    checks/ with no rule is an orphan."""
    return [
        f"{path.relative_to(skill)}: no rule carries the ID {path.stem}; a"
        " checker is named after its rule"
        for path in sorted((skill / "tools" / "qa" / "checks").glob("*.py"))
        if path.stem not in ids
    ]


def campaign_references(skill):
    """The page standard stands alone: nothing under guidelines/page/ refers
    to the campaign standard."""
    return [
        f"{path.relative_to(skill)}: line {number}: the page standard does"
        " not refer to the campaign standard"
        for path in sorted((skill / "guidelines" / "page").rglob("*.md"))
        for number, line in numbered_lines(path)
        if "guidelines/campaign/" in line
    ]


# a path under tools/ in a document of the standard, a file or a directory, up
# to the punctuation that closes a sentence; e.g. `tools/campaign/run.py` and
# `tools/qa/`, and also a path of the kernel tree such as
# `tools/testing/selftests/`, which the check tells apart by what this
# repository holds
TOOL_PATH = re.compile(r"(?<![\w./-])tools/[A-Za-z0-9_./-]+")


def tool_references(skill):
    """The standard stands without its tools: no document under guidelines/
    names a path this repository holds under tools/. The directory alone and a
    path of the kernel's own tools/ are no reference to a tool."""
    problems = []
    for path in sorted((skill / "guidelines").rglob("*.md")):
        for number, line in numbered_lines(path):
            for match in TOOL_PATH.finditer(line):
                target = match.group().rstrip("./")
                if target != "tools" and (skill / target).exists():
                    problems.append(
                        f"{path.relative_to(skill)}: line {number}: the"
                        f" standard names no tool: {target}"
                    )
    return problems


# a reference to the plugin layer, which the standard and the tools never name:
# a path under skills/, one of the four scripts, or the old workflow name; e.g.
# `skills/write-campaign/SKILL.md` and `scripts/finish.sh`
PLUGIN_LAYER = re.compile(
    r"\bskills/|scripts/(?:prepare|finish|fold|lib)\.sh|claude-workflow"
)


def plugin_layer_references(skill):
    """The standard and its tools do not know the plugin layer above them: no
    path of it, by name."""
    standard = sorted(
        list((skill / "guidelines").rglob("*.md"))
        + list((skill / "tools").rglob("*.md"))
        + list((skill / "tools").rglob("*.py"))
    )
    return [
        f"{path.relative_to(skill)}: line {number}: the standard and its"
        " tools do not refer to the plugin layer"
        for path in standard
        if path != skill / "tools" / "guidelines_lint.py"
        for number, line in numbered_lines(path)
        if PLUGIN_LAYER.search(line)
    ]


# a repository path a document names: a file under guidelines/, tools/ or
# skills/ that ends in md, py, sh, js or json, or one of the four scripts; e.g.
# `tools/campaign/run.py` and `guidelines/page/page-model.md`, and not the glob
# `guidelines/page/figures/*.md`
REFERENCE = re.compile(
    r"(?<![\w./-])(?:(?:guidelines|tools|skills)/[A-Za-z0-9_./-]+\.(?:md|"
    r"py|sh|js|json)|scripts/(?:prepare|finish|fold|lib)\.sh)(?![\w./*-])"
)
# a path given under the plugin root, group 1 the path without the punctuation
# that closes a sentence; e.g. `${CLAUDE_PLUGIN_ROOT}/tools/campaign/run.py,`
# gives tools/campaign/run.py
PLUGIN_ROOT = re.compile(
    r"\$\{CLAUDE_PLUGIN_ROOT\}/([A-Za-z0-9_./-]+?)"
    r"[.,;:]?(?![A-Za-z0-9_./-])"
)


def missing_references(skill):
    """Every path of this repository a document names is there."""
    documents = [skill / "README.md", skill / "CLAUDE.md"]
    documents.extend((skill / "tools").rglob("README.md"))
    documents.extend((skill / "guidelines").rglob("*.md"))
    documents.extend((skill / "skills").rglob("*.md"))
    problems = []
    for path in documents:
        if not path.is_file():
            continue
        for number, line in numbered_lines(path):
            for match in REFERENCE.finditer(line):
                target = match.group()
                if not (skill / target).is_file():
                    problems.append(
                        f"{path.relative_to(skill)}:{number}: missing"
                        f" reference {target}"
                    )
            for match in PLUGIN_ROOT.finditer(line):
                target = match.group(1)
                if not (skill / target).exists():
                    problems.append(
                        f"{path.relative_to(skill)}:{number}: missing"
                        f" reference ${{CLAUDE_PLUGIN_ROOT}}/{target}"
                    )
    return problems


def drifted_conventions(skill):
    """The host loads CLAUDE.md only where this repository is the working
    directory, so every skill repeats its conventions, the list items of that
    file, word for word; a copy that drifts from the file is a problem."""
    conventions = skill / "CLAUDE.md"
    if not conventions.is_file():
        return []
    items = [
        line
        for line in conventions.read_text(encoding="utf-8").splitlines()
        if line.startswith("- ")
    ]
    problems = []
    for path in sorted((skill / "skills").glob("*/SKILL.md")):
        lines = set(path.read_text(encoding="utf-8").splitlines())
        for item in items:
            if item not in lines:
                problems.append(
                    f"{path.relative_to(skill)}: the convention of"
                    f" CLAUDE.md is missing or reworded: {item}"
                )
    return problems


def lint_rules(skill=ROOT):
    skill = Path(skill)
    try:
        rules = load_rules(skill) + load_rules(skill, "inactive")
        page_model(skill)
    except (RuleError, OSError, UnicodeError) as error:
        return [str(error)]
    ids = {rule.id for rule in rules}
    return (
        duplicate_ids(rules)
        + misplaced_rules(skill)
        + delegated_requirements(skill, rules, ids)
        + orphan_checkers(skill, ids)
        + table_problems(skill, rules)
        + campaign_references(skill)
        + tool_references(skill)
        + plugin_layer_references(skill)
        + missing_references(skill)
        + drifted_conventions(skill)
    )


def main(argv=None):
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    problems = lint_rules()
    for problem in problems:
        print(problem)
    print(
        f"guidelines lint: {len(problems)} problem(s); semantic conflicts"
        " require review"
    )
    if problems:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
