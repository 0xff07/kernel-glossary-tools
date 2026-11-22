"""figures.py: a figure spliced into a finished page at a line the rules allow,
the drawing indented, and the mark families of the figures after it re-assigned
in page order with their legends and walk paragraphs.
"""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

if not __package__:
    # run as a script: make the repository's packages importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
try:
    # the tool reads the page through the QA engine's page model, which
    # needs PyYAML
    from tools.writer import figures
except ImportError:
    figures = None

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(TOOLS))

CAUTION = (
    "> CAUTION: AI-GENERATED CONTENT\n"
    ">\n"
    "> STRICTLY DO NOT SUBMIT THIS UPSTREAM UNLESS YOU ARE AN EXPERT"
    " INTIMATELY FAMILIAR WITH THIS SUBSYSTEM.\n"
)

PAGE = "# Page\n\n" + CAUTION + """
The lead.

## SUMMARY

A map.

## SPECIFICATIONS

None.

## COVERAGE

- [`'tb_port_enable'`](https://elixir.bootlin.com/linux/v7.2/source/\
drivers/thunderbolt/tb.c#L17): enables a port

## DOCUMENTATION

## OTHER SOURCES

## DETAILS

The route.

### The first subsection shows two sites

The first paragraph.

```
    The first figure
    ────────────────
    ┌─────┐  ①  ┌─────┐
    │ a   │ ──▶ │ b   │ ②
    └─────┘     └─────┘
    ① tb_port_enable tb.c:17  enables the port
    ② tb_port_disable tb.c:25  disables the port
```

The walk names ① tb_port_enable() and then ② tb_port_disable() in order.

### The second subsection shows one site

The second paragraph.

```
    The second figure
    ─────────────────
    ┌─────┐ ①
    │ c   │
    └─────┘
    ① tb_port_enable tb.c:17  enables the port again
```

The walk names ① tb_port_enable() once more.

Closing sentence of the second subsection.

### The third subsection reads a function in pieces

The first piece.

```c
/* drivers/thunderbolt/tb.c:17 */
static int tb_port_enable(struct tb_port *port)
{
\tif (!port)
```

The second piece.

```c
/* drivers/thunderbolt/tb.c:20 */
\t\treturn -EINVAL;
\tport->enabled = true;
\treturn 0;
}
```

The close.
"""

UNMARKED = """The inserted paragraph names what the drawing shows.

```
The inserted figure
───────────────────
┌───┐
│ x │
└───┘
```
"""

MARKED = """The inserted paragraph names what the drawing shows.

```
    The inserted figure
    ───────────────────
    ┌───┐ ①
    │ x │
    └───┘
    ① tb_port_disable tb.c:25  disables the port here
```

The walk names ① tb_port_disable() for the inserted figure.
"""


def line_of(text, needle):
    for n, line in enumerate(text.split("\n"), 1):
        if needle in line:
            return n
    raise AssertionError(needle)


@unittest.skipIf(
    figures is None,
    "figures.py needs PyYAML, which the QA environment carries",
)
class Figures(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.page = os.path.join(self.root, "page.md")
        with open(self.page, "w", encoding="utf-8") as handle:
            handle.write(PAGE)

    def tearDown(self):
        subprocess.run(["rm", "-rf", self.root])

    def read(self):
        with open(self.page, encoding="utf-8") as handle:
            return handle.read()

    def fragment(self, text):
        path = os.path.join(self.root, "fragment.md")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def test_rotate_reassigns_the_families_after_the_first_figure(self):
        lines, trailing = figures.read(self.page)
        report, problems, _planned = figures.rotate(lines, ROOT, self.page)
        self.assertEqual(problems, [])
        self.assertEqual(len(report), 1)
        self.assertIn("circled digits -> sans-serif circled digits", report[0])
        text = "\n".join(lines)
        self.assertIn("┌─────┐ ➊", text)
        self.assertIn("➊ tb_port_enable tb.c:17  enables the port again", text)
        self.assertIn("The walk names ➊ tb_port_enable() once more.", text)
        self.assertIn(
            "The walk names ① tb_port_enable() and then ② tb_port_disable() in"
            " order.",
            text,
        )
        self.assertEqual(text.count("①"), 3)

    def test_an_unmarked_figure_is_indented_and_changes_no_other_figure(self):
        at = line_of(PAGE, "Closing sentence of the second subsection.")
        report, notes, problems = figures.insert(
            self.page, self.fragment(UNMARKED), at, ROOT
        )
        self.assertEqual(problems, [])
        self.assertEqual(
            report[0], f"inserted 9 line(s) at {at}-{at + 8} (unmarked)"
        )
        text = self.read()
        self.assertIn(
            "\n"
            "    The inserted figure\n"
            "    ───────────────────\n"
            "    ┌───┐\n"
            "    │ x │\n"
            "    └───┘\n"
            "```\n"
            "\n"
            "Closing sentence",
            text,
        )
        self.assertIn(
            "The inserted paragraph names what the drawing shows.\n\n```\n",
            text,
        )
        # the second figure's family changes in the same pass, since the page
        # was drafted with ① twice
        self.assertIn("┌─────┐ ➊", text)
        self.assertEqual(
            text.count("The walk names ➊ tb_port_enable() once more."), 1
        )
        self.assertTrue(
            any("now holds 2 figures" in note for note in notes), notes
        )

    def test_a_marked_figure_takes_its_family_and_shifts_the_figures_after_it(
        self,
    ):
        at = line_of(PAGE, "The second paragraph.")
        report, notes, problems = figures.insert(
            self.page, self.fragment(MARKED), at, ROOT
        )
        self.assertEqual(problems, [])
        text = self.read()
        # the inserted figure stands between two figures drawn with ①, so it
        # takes ➊; both neighbours keep their marks
        self.assertIn("    ┌───┐ ➊\n", text)
        self.assertIn(
            "    ➊ tb_port_disable tb.c:25  disables the port here", text
        )
        self.assertIn(
            "The walk names ➊ tb_port_disable() for the inserted figure.", text
        )
        self.assertIn("    ┌─────┐ ①\n", text)
        self.assertIn(
            "    ① tb_port_enable tb.c:17  enables the port again", text
        )
        self.assertIn("The walk names ① tb_port_enable() once more.", text)
        self.assertIn(
            "The walk names ① tb_port_enable() and then ② tb_port_disable() in"
            " order.",
            text,
        )
        self.assertEqual(len(report), 2, report)

    def test_check_writes_nothing(self):
        before = self.read()
        at = line_of(PAGE, "Closing sentence of the second subsection.")
        report, _notes, _problems = figures.insert(
            self.page, self.fragment(UNMARKED), at, ROOT, check=True
        )
        self.assertEqual(self.read(), before)
        self.assertTrue(report[0].startswith("inserted"))

    def test_refusals(self):
        closing = line_of(PAGE, "Closing sentence of the second subsection.")
        cases = [
            (
                UNMARKED.replace("│ x │", "│\tx │"),
                closing,
                "a tab inside the fence",
            ),
            (
                UNMARKED.replace("```\nThe inserted", "```c\nThe inserted"),
                closing,
                "the source language",
            ),
            (
                UNMARKED.replace(
                    "The inserted figure\n"
                    "───────────────────\n"
                    "┌───┐\n"
                    "│ x │\n"
                    "└───┘",
                    "x",
                ),
                closing,
                "no drawing character",
            ),
            (
                UNMARKED,
                line_of(PAGE, "The second piece."),
                (
                    "between consecutive pieces of drivers/thunderbolt/tb.c"
                    " (17-19 and 20 on)"
                ),
            ),
            (
                UNMARKED,
                line_of(PAGE, "    │ a   │ ──▶ │ b   │ ②"),
                "inside the fence",
            ),
            (
                UNMARKED,
                line_of(PAGE, "The walk names ① tb_port_enable() once more."),
                "walks the marks of the figure",
            ),
            (
                UNMARKED,
                line_of(PAGE, "- [`'tb_port_enable'`]"),
                "a catalog section",
            ),
            (
                UNMARKED,
                line_of(PAGE, "### The third subsection"),
                "would close the subsection",
            ),
            (
                UNMARKED.split("\n\n", 1)[1],
                line_of(PAGE, "The first paragraph."),
                "no prose paragraph stands above the fence",
            ),
            (
                UNMARKED.replace("│ x │", "│ x " + "x" * 120 + "│"),
                closing,
                "display cells wide",
            ),
        ]
        for fragment, at, message in cases:
            with self.subTest(message=message):
                with open(self.page, "w", encoding="utf-8") as handle:
                    handle.write(PAGE)
                with self.assertRaises(figures.FigureError) as caught:
                    figures.insert(
                        self.page, self.fragment(fragment), at, ROOT
                    )
                self.assertIn(message, str(caught.exception))
                self.assertEqual(self.read(), PAGE)

    def test_the_command_names_the_figure_rules(self):
        done = subprocess.run(
            [
                sys.executable,
                os.path.join(TOOLS, "figures.py"),
                "rotate",
                self.page,
                "--check",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("would: figure at line", done.stdout)
        self.assertIn("--rule drawing.marks", done.stdout)
        self.assertEqual(self.read(), PAGE)
        done = subprocess.run(
            [
                sys.executable,
                os.path.join(TOOLS, "figures.py"),
                "insert",
                self.page,
                self.fragment("x\n"),
                "--at",
                "1",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(done.returncode, 1)
        self.assertTrue(done.stderr.startswith("refused:"), done.stderr)


if __name__ == "__main__":
    unittest.main()
