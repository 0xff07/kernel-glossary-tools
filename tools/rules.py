#!/usr/bin/env python3
"""Load active writing rules; no QA implementation is required."""

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
# a rule id to the end of the text, lowercase words joined by dots; e.g.
# `sections.kconfig` and `coverage.scope-closure`
ID = re.compile(r"[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)*\Z")


class RuleError(ValueError):
    pass


@dataclass(frozen=True)
class Rule:
    id: str
    path: Path
    body: str
    qa: str = "off"


def read_rule(path):
    """The optional frontmatter has only qa: off/manual/auto."""
    if not ID.fullmatch(path.stem):
        raise RuleError(f"{path}: invalid rule filename")
    text = path.read_bytes().decode("utf-8")
    policy = {}
    body = text
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end < 0:
            raise RuleError(f"{path}: unclosed policy frontmatter")
        for number, line in enumerate(text[4:end].splitlines(), 2):
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            key, separator, value = line.partition(":")
            key, value = key.strip(), value.strip()
            if not separator or key != "qa" or key in policy:
                raise RuleError(
                    f"{path}:{number}: unknown, duplicate or malformed policy"
                    " field"
                )
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            if value not in {"off", "manual", "auto"}:
                raise RuleError(
                    f"{path}:{number}: invalid {key} value {value!r}"
                )
            policy[key] = value
        body = text[end + len("\n---\n") :]
    if not body.strip():
        raise RuleError(f"{path}: empty rule")
    return Rule(path.stem, path, body, policy.get("qa", "off"))


def load_rules(skill=ROOT, directory="active"):
    if directory not in {"active", "inactive"}:
        raise RuleError(f"unknown rule directory: {directory}")
    folder = Path(skill) / "guidelines" / "page" / "rules" / directory
    if not folder.is_dir():
        if directory == "inactive":
            return []
        raise RuleError(f"missing rule directory: {folder}")
    return [read_rule(path) for path in sorted(folder.glob("*.md"))]


def page_model(skill=ROOT):
    path = Path(skill) / "guidelines" / "page" / "page-model.md"
    body = path.read_bytes().decode("utf-8")
    if not body.strip():
        raise RuleError(f"{path}: empty page model")
    return body


def prompt_rules(skill=ROOT):
    """Copy shared definitions once and every active body with its QA
    policy."""
    parts = ["<!-- page model -->\n" + page_model(skill)]
    parts.extend(
        f"<!-- rule: {rule.id}; qa: {rule.qa} -->\n{rule.body}"
        for rule in load_rules(skill)
    )
    return "\n\n".join(parts)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["list", "prompt"])
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
        "--qa", action="store_true", help="list only active rules requiring QA"
    )
    args = parser.parse_args(argv)
    if args.qa and args.command != "list":
        parser.error(
            "--qa is only valid with list; prompt always includes all active"
            " rules"
        )
    try:
        rules = load_rules(args.skill)
        if args.command == "prompt":
            print(prompt_rules(args.skill))
        else:
            for rule in rules:
                if not args.qa or rule.qa != "off":
                    print(f"{rule.id}\tqa={rule.qa}")
    except (RuleError, OSError, UnicodeError) as error:
        print(error, file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
