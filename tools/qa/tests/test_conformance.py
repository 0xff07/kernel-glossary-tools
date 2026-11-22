"""The conformance corpus: every case under tests/cases/ is a page followed by
a `<!-- kg:expect` block that states the findings the rules derive for it; the
fixture tree under tests/cases/tree/ is the source they cite. A case's
expectation is derived from the rule file, never captured from a run. The
figure patterns of guidelines/page/figures/ and the example figures of the
registers.* rules pass the figure checks as well."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

if not __package__:
    # run as a script: make the repository's packages importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.qa.page import Page, profile, scope_names_of
from tools.qa.run import run
from tools.qa.tree import Tree

ROOT = Path(__file__).resolve().parents[3]

CASES = Path(__file__).parent / "cases"
SEVERITY = {"violation": "FAIL", "candidate": "review"}


def parse_case(path):
    text = path.read_text(encoding="utf-8")
    marker = "\n<!-- kg:expect"
    at = text.find(marker)
    if at < 0:
        raise ValueError(f"{path}: no `<!-- kg:expect` block")
    rest = text[at + len(marker) :]
    end = rest.find("-->")
    if end < 0:
        raise ValueError(f"{path}: the expect block never closes")
    return text[: at + 1], yaml.safe_load(rest[:end]) or {}


def build_tree():
    """A temporary copy of the fixture tree made into a git repository by its
    init.sh."""
    target = tempfile.mkdtemp(prefix="kg-cases-")
    shutil.copytree(CASES / "tree", target, dirs_exist_ok=True)
    done = subprocess.run(
        ["bash", os.path.join(target, "init.sh")],
        cwd=target,
        capture_output=True,
        text=True,
    )
    if done.returncode != 0:
        raise RuntimeError(f"init.sh failed: {done.stderr.strip()[:400]}")
    return target


def outcome(report):
    found = set()
    for item in report["automatic"]:
        for finding in item["findings"]:
            if finding["kind"] in SEVERITY:
                found.add(
                    (
                        item["rule"],
                        SEVERITY[finding["kind"]],
                        finding["line"],
                        finding["quote"],
                    )
                )
    for error in report["errors"]:
        for finding in error.get("findings", []):
            if finding["kind"] in SEVERITY:
                found.add(
                    (
                        error["rule"],
                        SEVERITY[finding["kind"]],
                        finding["line"],
                        finding["quote"],
                    )
                )
    return found


class Conformance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree_path = build_tree()
        cls.tree = Tree(cls.tree_path, profile(str(ROOT)))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tree_path, ignore_errors=True)

    def test_writes_view_lists_the_field_writes_of_mapped_units(self):
        """The writes view lists, with their tree lines, the lines of the shown
        units that write a named field, so that the orchestrator reads them
        against the LIFECYCLE and EXCLUDED rows.
        """
        from tools.qa.inputs import Context
        from tools.qa.page import Page
        from tools.qa.views import writes

        body = "\n".join(
            Path(self.tree_path, "drivers/thunderbolt/tb.c")
            .read_text(encoding="utf-8")
            .split("\n")[73:76]
        )
        text = (
            "# Page\n\n```c\n/* drivers/thunderbolt/tb.c:74 */\n"
            + body
            + "\n```\n"
        )
        page = Page(text, "page.md", str(ROOT))
        context = Context(page, str(ROOT), tree_option=str(self.tree_path))
        rows = writes(page, context, ["clx"])
        self.assertEqual(
            [(r[0], r[1], r[3]) for r in rows],
            [
                ("drivers/thunderbolt/tb.c", 74, "port->clx ="),
                ("drivers/thunderbolt/tb.c", 75, "remote->clx ="),
            ],
        )
        self.assertEqual(writes(page, context, ["bonded"]), [])
        self.assertEqual([r[1] for r in writes(page, context, [])], [74, 75])

    def test_cases(self):
        names = sorted(p for p in CASES.iterdir() if p.suffix == ".md")
        self.assertTrue(names)
        pending = 0
        for path in names:
            with self.subTest(case=path.name):
                text, expect = parse_case(path)
                scope = (
                    scope_names_of(expect["scope_fence"])
                    if "scope_fence" in expect
                    else expect.get("scope")
                )
                report = run(
                    text,
                    ROOT,
                    {},
                    expect.get("only") or (),
                    page_path=str(ROOT / "docs" / "usb4" / "case" / path.name),
                    tree_object=self.tree,
                    scope=scope,
                    fixed=True,
                    include_off=True,
                )
                found = outcome(report)
                wanted = {tuple(e[:4]) for e in expect.get("findings") or []}
                incomplete = {
                    e["rule"]
                    for e in report["errors"]
                    if e["message"].startswith("incomplete:")
                }
                errors = [
                    f"{e['rule']}: {e['message']}"
                    for e in report["errors"]
                    if not e["message"].startswith("incomplete:")
                ]
                problems = report["inputs"].get("problems", [])
                if problems and not expect.get("problems"):
                    errors += [f"input: {p}" for p in problems]
                ok = (
                    found == wanted
                    and incomplete == set(expect.get("incomplete") or [])
                    and not errors
                )
                if expect.get("reference_fails"):
                    self.assertFalse(
                        ok, f"{path.name} passes; drop its reference_fails"
                    )
                    pending += 1
                    continue
                self.assertEqual(
                    sorted(found - wanted, key=str),
                    [],
                    f"{path.name}: found, not expected",
                )
                self.assertEqual(
                    sorted(wanted - found, key=str),
                    [],
                    f"{path.name}: expected, not found",
                )
                self.assertEqual(
                    incomplete,
                    set(expect.get("incomplete") or []),
                    f"{path.name}: incomplete rules",
                )
                self.assertEqual(errors, [], f"{path.name}: errors")
        print(
            f"\nconformance: {len(names) - pending} cases pass; {pending}"
            " pending, the checkers fail them on purpose",
            file=sys.stderr,
        )

    def test_reference_figures(self):
        """Every untagged fence of the figure patterns and of the registers.*
        rules, placed in a skeleton page, passes the figure checks."""
        config = profile(str(ROOT))
        files = sorted((ROOT / "guidelines" / "page" / "figures").glob("*.md"))
        files += sorted(
            (ROOT / "guidelines" / "page" / "rules" / "active").glob(
                "registers.*.md"
            )
        )
        skeleton = (
            "# Reference\n\n"
            + "\n".join(config.caution_lines)
            + "\n\nThe lead.\n\n## SUMMARY\n\nA map.\n\n##"
            " SPECIFICATIONS\n"
            "\n"
            "None.\n"
            "\n"
            "## COVERAGE\n"
            "\n"
            "## DOCUMENTATION\n"
            "\n"
            "## OTHER SOURCES\n"
            "\n"
            "## DETAILS\n"
            "\n"
            "The route.\n"
            "\n"
            "### The figure\n"
            "\n"
            "A paragraph above the figure.\n"
            "\n"
        )
        figures = 0
        for path in files:
            lines = path.read_text(encoding="utf-8").split("\n")
            i = 0
            while i < len(lines):
                if lines[i].startswith("```"):
                    j = i + 1
                    while j < len(lines) and not lines[j].startswith("```"):
                        j += 1
                    if not lines[i][3:].strip():
                        body = lines[i + 1 : j]
                        with self.subTest(figure=f"{path.name}:{i + 1}"):
                            text = (
                                skeleton
                                + "```\n"
                                + "\n".join(body)
                                + "\n```\n\nThe figure closes the"
                                " subsection.\n"
                            )
                            page = Page(
                                text,
                                str(
                                    ROOT
                                    / "docs"
                                    / "usb4"
                                    / "reference"
                                    / "figure.md"
                                ),
                                str(ROOT),
                            )
                            self.assertEqual(
                                len(page.figures),
                                1,
                                "the reference carries no drawing character",
                            )
                            figures += 1
                            report = run(
                                text,
                                ROOT,
                                {},
                                [
                                    "geometry.layout",
                                    "geometry.unicode",
                                    "registers.ruler",
                                    "geometry.figure-tabs",
                                ],
                                page_path=page.path,
                                fixed=True,
                                include_off=True,
                            )
                            self.assertEqual(report["errors"], [])
                            self.assertEqual(outcome(report), set())
                    i = j + 1
                else:
                    i += 1
        self.assertGreater(figures, 30)


if __name__ == "__main__":
    unittest.main()
