#!/usr/bin/env python3
"""Run the complete checker of every active rule whose policy is auto, list the
manual work, and write nothing: no record, no state, no certificate. Exit
status: 0 every automatic check passed and no manual work remains; 1 a
violation; 2 an execution error, a missing input or an input problem; 3 the
automatic checks passed while manual rules or candidates remain."""

import argparse
import collections
import datetime
import importlib.util
import json
from pathlib import Path
import sys

if not __package__:
    # run as a script: make the repository's packages importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.rules import RuleError, load_rules
from tools.qa import inputs
from tools.qa.inputs import Context, Missing
from tools.qa.page import ModelError, Page

ROOT = Path(__file__).resolve().parents[2]

KINDS = ("violation", "candidate", "measurement")


def checker(path, rule_id):
    name = "kg_check_" + rule_id.encode().hex()
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    # Read the current source on every run, so a small checker edit takes
    # effect at once.
    exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
    if not callable(getattr(module, "check", None)):
        raise ValueError(f"{path}: expected check(page, context)")
    return module


def normalize(finding, page):
    if (
        not isinstance(finding, dict)
        or "line" not in finding
        or not isinstance(finding.get("message"), str)
        or not finding["message"]
    ):
        raise ValueError(
            "invalid finding: expected message and a valid original page line"
            " or null"
        )
    line = finding.get("line")
    if line is not None and (
        type(line) is not int or not 1 <= line <= len(page.lines)
    ):
        raise ValueError(
            "invalid finding: expected message and a valid original page line"
            " or null"
        )
    kind = finding.get("kind", "violation")
    if kind not in KINDS:
        raise ValueError(f"invalid finding kind {kind!r}")
    quote = finding.get("quote")
    if quote is not None and not isinstance(quote, str):
        raise ValueError("invalid finding: a quote is text")
    return {
        "line": line,
        "quote": quote,
        "message": finding["message"],
        "kind": kind,
    }


def run(
    text,
    skill=ROOT,
    context=None,
    only=(),
    page_path=None,
    tree=None,
    spec=None,
    scope=None,
    subsystem=None,
    tree_object=None,
    fixed=False,
    include_off=False,
    prefixes=(),
):
    """The report {automatic, manual, errors, inputs} of a page's text under
    the active rules; `only` names rules by id and `prefixes` families by id
    prefix, and with include_off either may name a rule whose QA policy is off,
    which then runs its checker or is listed as manual."""
    skill = Path(skill)
    every = load_rules(skill)
    rules = [rule for rule in every if rule.qa != "off"]
    if only or prefixes:
        pool = every if include_off else rules
        unknown = set(only) - {rule.id for rule in pool}
        if unknown:
            raise RuleError(
                f"unknown or QA-disabled rules: {', '.join(sorted(unknown))}"
            )
        rules = [
            rule
            for rule in pool
            if rule.id in only or any(rule.id.startswith(p) for p in prefixes)
        ]
        if not rules:
            raise RuleError(
                "no rule selected: the ids and prefixes name nothing in the"
                " pool"
            )
    report = {"automatic": [], "manual": [], "errors": [], "inputs": {}}
    page = run_context = None
    for rule in rules:
        path = skill / "tools" / "qa" / "checks" / (rule.id + ".py")
        if rule.qa == "manual" or not path.is_file():
            report["manual"].append(rule.id)
            continue
        findings = []
        try:
            if page is None:
                page = Page(text, page_path or "page.md", str(skill))
                run_context = Context(
                    page,
                    str(skill),
                    tree=tree_object,
                    tree_option=tree,
                    spec=spec,
                    scope=scope,
                    subsystem=subsystem,
                    fixed=fixed,
                    extra=context or {},
                )
                report["inputs"] = {
                    "tree": (
                        run_context.tree.path if run_context.tree else None
                    ),
                    "tag": run_context.tree.tag if run_context.tree else None,
                    "scope": run_context.scope,
                    "spec": run_context.spec_path,
                    "subsystem": (run_context.subsystem or {}).get("dir"),
                    "problems": list(run_context.problems),
                    "notes": list(run_context.notes),
                }
            module = checker(path, rule.id)
            if rule.id != "page.fence-close":
                page.require_valid()
            run_context["rule"] = rule
            run_context["skill"] = str(skill)
            result = module.check(page, run_context)
            if result is None or isinstance(result, (str, bytes, dict)):
                raise ValueError("checker must return or yield findings")
            for finding in result:
                findings.append(normalize(finding, page))
            report["automatic"].append({"rule": rule.id, "findings": findings})
        except Missing as error:
            report["errors"].append(
                {
                    "rule": rule.id,
                    "message": f"incomplete: {error}",
                    "findings": findings,
                }
            )
        except (Exception, SystemExit) as error:
            report["errors"].append(
                {
                    "rule": rule.id,
                    "message": f"{type(error).__name__}: {error}",
                    "findings": findings,
                }
            )
    return report


def exit_status(report):
    if report["errors"]:
        return 2
    if any(
        f["kind"] == "violation"
        for item in report["automatic"]
        for f in item["findings"]
    ):
        return 1
    candidates = any(
        f["kind"] == "candidate"
        for item in report["automatic"]
        for f in item["findings"]
    )
    return 3 if report["manual"] or candidates else 0


def finding_key(rule, finding):
    return f"{rule}|{finding['kind']}|{finding.get('quote') or ''}"


def keys_of(report):
    return collections.Counter(
        finding_key(item["rule"], f)
        for item in report["automatic"]
        for f in item["findings"]
        if f["kind"] in ("violation", "candidate")
    )


def render(report, since=None):
    """The text report: violations and candidates per rule, measurements
    counted, then the summary."""
    out = []
    for problem in report.get("inputs", {}).get("problems", []):
        out.append(f"inputs: {problem}")
    for note in report.get("inputs", {}).get("notes", []):
        out.append(f"note: {note}")
    previous = collections.Counter(since["keys"]) if since else None
    new = standing = 0
    for item in report["automatic"]:
        measurements = 0
        for finding in item["findings"]:
            if finding["kind"] == "measurement":
                measurements += 1
                continue
            tag = ""
            if previous is not None:
                key = finding_key(item["rule"], finding)
                if previous[key] > 0:
                    previous[key] -= 1
                    standing += 1
                    tag = " (standing)"
                else:
                    new += 1
            where = f"{finding['line']}: " if finding["line"] else ""
            label = "" if finding["kind"] == "violation" else "candidate: "
            out.append(
                f"{item['rule']}:{where}{label}{finding['message']}{tag}"
            )
        if measurements:
            out.append(
                f"{item['rule']}: {measurements} measurement(s), in --json"
            )
    for error in report["errors"]:
        for finding in error.get("findings", []):
            if finding["kind"] != "measurement":
                where = f"{finding['line']}: " if finding["line"] else ""
                out.append(f"{error['rule']}:{where}{finding['message']}")
        out.append(f"{error['rule']}: execution error: {error['message']}")
    passed = sum(
        not any(f["kind"] == "violation" for f in item["findings"])
        for item in report["automatic"]
    )
    candidates = sum(
        f["kind"] == "candidate"
        for item in report["automatic"]
        for f in item["findings"]
    )
    out.append(
        f"automatic: {passed}/{len(report['automatic'])} passed; candidates:"
        f" {candidates}; manual: {len(report['manual'])}; errors:"
        f" {len(report['errors'])}"
    )
    if previous is not None:
        out.append(
            f"since {since.get('date', 'the previous report')}: {new} new,"
            f" {sum(previous.values())} gone, {standing} standing"
        )
    if 0 < len(report["manual"]) <= 6:
        out.append("manual: " + ", ".join(report["manual"]))
    elif report["manual"]:
        out.append(
            "Use --json for manual rule IDs; read their original rule files."
        )
    if not report["automatic"] and not report["manual"]:
        out.append("No QA rules selected.")
    return "\n".join(out)


def command_line():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("page", type=Path)
    parser.add_argument(
        "--glossary-checkout",
        dest="skill",
        type=Path,
        default=ROOT,
        help=(
            "the checkout of this repository to work in (default: the one"
            " holding this file)"
        ),
    )
    parser.add_argument(
        "--tree",
        help=(
            "the documented kernel tree (default: $KG_TREE, else the kernel"
            " checkout whose .claude directory holds this repository)"
        ),
    )
    parser.add_argument(
        "--spec",
        help=(
            "the campaign spec holding the page's scope fence (default:"
            " campaigns/<dir>.md)"
        ),
    )
    parser.add_argument(
        "--scope", help="the scope names, comma-separated, instead of a spec"
    )
    parser.add_argument(
        "--subsystem",
        help="the subsystem entry's dir when the page lies outside docs/",
    )
    parser.add_argument(
        "--rule",
        action="append",
        default=[],
        help="check selected QA rule IDs only",
    )
    parser.add_argument(
        "--prefix",
        action="append",
        default=[],
        help=(
            "check the rules whose ID starts with this prefix (a family such"
            " as drawing.)"
        ),
    )
    parser.add_argument(
        "--include-off",
        action="store_true",
        help=(
            "let --rule name a rule whose QA policy is off; its checker then"
            " runs"
        ),
    )
    parser.add_argument(
        "--since",
        type=Path,
        help="a previous --json report; print the delta against it",
    )
    parser.add_argument("--json", action="store_true")
    return parser


def check_page(args):
    """(report, since): the report of the page the command line names, and
    what an earlier report it is compared with held."""
    text = args.page.read_bytes().decode("utf-8")
    scope = (
        [s.strip() for s in args.scope.split(",") if s.strip()]
        if args.scope
        else None
    )
    report = run(
        text,
        args.skill,
        {},
        args.rule,
        page_path=str(args.page.resolve()),
        tree=args.tree,
        spec=args.spec,
        scope=scope,
        subsystem=args.subsystem,
        include_off=args.include_off,
        prefixes=args.prefix,
    )
    since = None
    if args.since:
        previous = json.loads(args.since.read_text())
        since = {
            "date": previous.get("date"),
            "keys": previous.get("keys") or dict(keys_of(previous)),
        }
    return report, since


def main(argv=None):
    args = command_line().parse_args(argv)
    try:
        report, since = check_page(args)
    except (
        RuleError,
        ModelError,
        OSError,
        UnicodeError,
        ValueError,
        inputs.RuleTableError,
    ) as error:
        print(error, file=sys.stderr)
        raise SystemExit(2)
    if args.json:
        report["date"] = datetime.date.today().isoformat()
        report["keys"] = dict(keys_of(report))
        print(json.dumps(report, ensure_ascii=False))
    else:
        print(render(report, since))
    status = exit_status(report)
    if status:
        raise SystemExit(status)


if __name__ == "__main__":
    main()
