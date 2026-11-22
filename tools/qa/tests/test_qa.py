"""Exercise rule maintenance, policy selection, checker failure handling and
original page locations."""

import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

if not __package__:
    # run as a script: make the repository's packages importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.qa.page import Page, profile
from tools.qa.run import checker, exit_status, run
from tools.qa.source import code_text, declares_bare_type
from tools.rules import RuleError, load_rules, prompt_rules
from tools.guidelines_lint import lint_rules

ROOT = Path(__file__).resolve().parents[3]

MODEL = (ROOT / "guidelines" / "page" / "page-model.md").read_text(
    encoding="utf-8"
)
CASES = Path(__file__).parent / "cases"


def case_text(name):
    text = (CASES / name).read_text(encoding="utf-8")
    return text[: text.find("\n<!-- kg:expect") + 1]


class RuleMaintenance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.skill = Path(self.temp.name)
        (self.skill / "guidelines/page/rules/active").mkdir(parents=True)
        (self.skill / "guidelines/page/rules/inactive").mkdir()
        (self.skill / "guidelines/page/page-model.md").write_text(
            MODEL, encoding="utf-8"
        )
        # the files the page model refers to, so that the temp skill's
        # references resolve
        (self.skill / "guidelines/subsystems.md").write_text("# Subsystems\n")
        (self.skill / "guidelines/campaign").mkdir()
        (self.skill / "guidelines/campaign/spec.md").write_text(
            "# The campaign spec format\n"
        )
        (self.skill / "tools/qa").mkdir(parents=True)

    def rule(self, identity, body, policy="", directory="active"):
        path = (
            self.skill
            / "guidelines/page/rules"
            / directory
            / (identity + ".md")
        )
        path.write_text(
            ("---\n" + policy + "\n---\n" if policy else "") + body
        )
        return path

    def implementation(self, identity, body):
        folder = self.skill / "tools/qa/checks"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / (identity + ".py")).write_text(body)

    def test_three_new_rule_policies_need_no_registry(self):
        self.rule("new.writer", "# Writer\n\nUse concrete names.\n")
        self.rule(
            "new.manual",
            "# Manual\n\nExplain every transition.\n",
            "qa: manual",
        )
        self.rule("new.auto", "# Auto\n\nForbid BAD.\n", "qa: auto")
        self.assertFalse((self.skill / "tools/qa/checks").exists())
        prompt = prompt_rules(self.skill)
        self.assertIn("Use concrete names.", prompt)
        self.assertEqual(
            run("# Good\n", self.skill, fixed=True)["manual"],
            ["new.auto", "new.manual"],
        )
        self.implementation(
            "new.auto",
            "def check(page, context):\n"
            "    return [{'line': 1, 'message': 'BAD is forbidden.'}] if"
            " 'BAD' in page.text else []\n",
        )
        clean = run("# Good\n", self.skill, fixed=True)
        self.assertEqual(
            clean["automatic"], [{"rule": "new.auto", "findings": []}]
        )
        self.assertEqual(clean["manual"], ["new.manual"])
        self.assertEqual(exit_status(clean), 3)
        self.assertEqual(
            exit_status(run("# BAD\n", self.skill, fixed=True)), 1
        )
        (self.skill / "tools/qa/checks/new.auto.py").unlink()
        self.assertEqual(
            run("# Good\n", self.skill, fixed=True)["manual"],
            ["new.auto", "new.manual"],
        )

    def test_subsystem_entry_consumers_defaults_to_drivers(self):
        from tools.qa.inputs import subsystem_entries

        (self.skill / "guidelines/subsystems.md").write_text(
            "# Subsystems\n"
            "\n"
            "## A\n"
            "\n"
            "- dir: `a`\n"
            "- kernel_paths: `drivers/a/`\n"
            "\n"
            "## B\n"
            "\n"
            "- dir: `b`\n"
            "- kernel_paths: `mm/`\n"
            "- consumers: `core`\n"
        )
        entries = {e["dir"]: e for e in subsystem_entries(self.skill)}
        self.assertEqual(entries["a"]["consumers"], "drivers")
        self.assertEqual(entries["b"]["consumers"], "core")

    def test_directory_move_controls_both_prompt_and_qa(self):
        body = "# Scope\n\nOnly when X applies.\n\nException: Y.\n"
        path = self.rule("new.rule", body, "qa: auto")
        self.implementation(
            "new.rule", "def check(page, context):\n    return []\n"
        )
        self.assertEqual(load_rules(self.skill)[0].body, body)
        self.assertIn(
            "<!-- rule: new.rule; qa: auto -->\n" + body,
            prompt_rules(self.skill),
        )
        self.assertEqual(
            run("", self.skill, fixed=True)["automatic"],
            [{"rule": "new.rule", "findings": []}],
        )
        inactive = self.skill / "guidelines/page/rules/inactive/new.rule.md"
        path.rename(inactive)
        self.assertNotIn(body, prompt_rules(self.skill))
        self.assertEqual(run("", self.skill, fixed=True)["automatic"], [])
        with self.assertRaises(RuleError):
            run("", self.skill, only=["new.rule"], fixed=True)
        inactive.rename(path)
        self.assertIn(body, prompt_rules(self.skill))
        self.assertEqual(
            run("", self.skill, fixed=True)["automatic"],
            [{"rule": "new.rule", "findings": []}],
        )

    def test_inactive_files_and_checkers_are_not_loaded(self):
        self.rule(
            "inactive.rule", "Unused.\n", "qa: unknown", directory="inactive"
        )
        self.implementation(
            "inactive.rule", "raise RuntimeError('Must not execute')\n"
        )
        self.assertEqual(load_rules(self.skill), [])
        report = run("", self.skill, fixed=True)
        self.assertEqual(
            (report["automatic"], report["manual"], report["errors"]),
            ([], [], []),
        )
        self.assertNotIn("Unused.", prompt_rules(self.skill))
        self.assertTrue(lint_rules(self.skill))

    def test_lint_rejects_duplicate_ids_across_directories(self):
        self.rule("same.rule", "Active requirement.\n")
        self.rule("same.rule", "Inactive requirement.\n", directory="inactive")
        self.assertTrue(
            any(
                "duplicate rule ID same.rule" in p
                for p in lint_rules(self.skill)
            )
        )

    def test_lint_rejects_a_checker_without_a_rule(self):
        self.rule("new.rule", "A requirement.\n", "qa: auto")
        self.implementation(
            "new.rule", "def check(page, context):\n    return []\n"
        )
        self.assertEqual(lint_rules(self.skill), [])
        self.implementation(
            "orphan.rule", "def check(page, context):\n    return []\n"
        )
        self.assertTrue(
            any(
                "orphan.rule" in p and "no rule" in p
                for p in lint_rules(self.skill)
            )
        )

    def test_lint_checks_template_references_and_allows_existing_aids(self):
        template = self.skill / "guidelines/page/page-template.md"
        template.write_text("Read `guidelines/page/figures/example.md`.\n")
        self.assertTrue(
            any(
                "missing reference guidelines/page/figures/example.md" in p
                for p in lint_rules(self.skill)
            )
        )
        folder = self.skill / "guidelines/page/figures"
        folder.mkdir()
        (folder / "example.md").write_text("An optional illustration.\n")
        self.rule(
            "new.rule",
            "Read the model and optional"
            " `guidelines/page/figures/example.md`.\n",
        )
        self.assertEqual(lint_rules(self.skill), [])

    def test_tree_heads_a_function_at_its_signature_not_at_a_folded_macro(
        self,
    ):
        """tools/qa/tree.py: a macro invocation without a `;` above a function
        (INTERVAL_TREE_DEFINE) is folded into the function by tree-sitter as
        its type; the construct's head stays at the signature's first line, so
        the macro's lines belong to no construct and a split signature still
        heads at its specifier line.
        """
        from tools.qa.tree import Tree

        folder = tempfile.mkdtemp(prefix="kg-tree-")
        try:
            Path(folder, "x.c").write_text(
                "MACRO_DEFINE(struct a, b,\n"
                "\t     c)\n"
                "\n"
                "void wrapper(int x)\n"
                "{\n"
                "\treturn;\n"
                "}\n"
                "\n"
                "static int\n"
                "split(void)\n"
                "{\n"
                "\treturn 0;\n"
                "}\n"
            )
            tree = Tree(folder, profile(str(ROOT)))
            heads = {
                t["name"]: (t["head"], t["line"], t["end"])
                for t in tree.tags("x.c")
                if t["kind"] == "function"
            }
            self.assertEqual(heads["wrapper"], (4, 4, 7))
            self.assertEqual(heads["split"], (9, 10, 13))
            self.assertIsNone(tree.construct_at("x.c", 1))
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_tree_closes_a_body_that_ends_in_a_macro_without_a_semicolon(self):
        """tools/qa/tree.py: a union whose body is a bare macro invocation with
        no `;` (dmub_cmd.h's COMMON_STREAM_STATIC_SUB_STATE) loses its closing
        brace to tree-sitter, which files every later definition as the union's
        member; the union ends at its own brace and what follows it belongs to
        no body. A type on one line with its declarator on the next is no such
        macro and stays a member.
        """
        from tools.qa.tree import Tree

        folder = tempfile.mkdtemp(prefix="kg-tree-")
        try:
            Path(folder, "x.h").write_text(
                "union a {\n"
                "\tMEMBERS\n"
                "}; //v1\n"
                "\n"
                "union b {\n"
                "\tMEMBERS /* the same three */\n"
                "}; //v2\n"
                "\n"
                "struct after {\n"
                "\tint y;\n"
                "\tfoo_t\n"
                "\t\tz;\n"
                "};\n"
                "\n"
                "static inline int f(void)\n"
                "{\n"
                "\treturn 0;\n"
                "}\n"
            )
            tree = Tree(folder, profile(str(ROOT)))
            spans = {
                t["name"]: (t["kind"], t["head"], t["end"], t["scope"])
                for t in tree.constructs("x.h")
            }
            self.assertEqual(
                spans,
                {
                    "a": ("union", 1, 3, None),
                    "b": ("union", 5, 7, None),
                    "after": ("struct", 9, 13, None),
                    "f": ("function", 15, 18, None),
                },
            )
            self.assertEqual(
                [t["name"] for t in tree.members_of("x.h", "after")],
                ["y", "z"],
            )
            self.assertEqual(
                tree.members_of("x.h", "a") + tree.members_of("x.h", "b"), []
            )
            self.assertEqual(tree.construct_at("x.h", 10)["name"], "after")
            self.assertIsNone(tree.construct_at("x.h", 8))
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_tree_keeps_the_member_after_a_macro_without_a_semicolon(self):
        """tools/qa/tree.py: a bare macro invocation with no `;` above a member
        (dmub_cmd.h's union dmub_fams2_stream_static_sub_state_v2) is read by
        tree-sitter as that member's type, so the member's first word becomes a
        member named `struct`, `int` or `u32` and the member itself is lost or
        loses its type; each body keeps its own members with their types. A
        type in lower case on one line with its declarator on the next is no
        such macro, even where its declarator fails to parse.
        """
        from tools.qa.tree import Tree

        folder = tempfile.mkdtemp(prefix="kg-tree-")
        try:
            Path(folder, "x.h").write_text(
                "union a {\n"
                "\tMEMBERS\n"
                "\tstruct alt alternate;\n"
                "}; //v2\n"
                "\n"
                "struct b {\n"
                "\tint w;\n"
                "\tFIELDS(uint8_t)\n"
                "\tint x;\n"
                "\tMEMBERS\n"
                "\tu32 y;\n"
                "\tstruct alt *p;\n"
                "};\n"
                "\n"
                "struct c {\n"
                "\tfoo_t\n"
                "\t\tz;\n"
                "\tbar_t\n"
                "\t\tq not_an_attribute_here;\n"
                "};\n"
            )
            tree = Tree(folder, profile(str(ROOT)))

            def members(name):
                return [
                    (t["name"], t["line"], t["typeref"])
                    for t in tree.members_of("x.h", name)
                ]

            self.assertEqual(members("a"), [("alternate", 3, "struct:alt")])
            self.assertEqual(
                members("b"),
                [
                    ("w", 7, "typename:int"),
                    ("x", 9, "typename:int"),
                    ("y", 11, "typename:u32"),
                    ("p", 12, "struct:alt"),
                ],
            )
            self.assertEqual(members("c")[0], ("z", 17, "typename:foo_t"))
            self.assertEqual(
                [t["typeref"] for t in tree.members_of("x.h", "c")],
                ["typename:foo_t", "typename:bar_t"],
            )
            self.assertEqual(
                {
                    t["name"]: (t["head"], t["end"])
                    for t in tree.constructs("x.h")
                },
                {"a": (1, 4), "b": (6, 13), "c": (15, 20)},
            )
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_tree_reads_one_branch_when_each_branch_opens_a_block(
        self,
    ):
        """tools/qa/tree.py: a conditional group whose branches each open the
        same block (amdgpu_dm_cursor.c's dm_check_cursor_fb), and one that
        stands between the operands of a condition or the parameters of a
        signature (the same file's amdgpu_dm_crtc_get_cursor_mode), break
        tree-sitter's reading of the function around them; each function ends
        at its own closing brace. A group whose branches are whole statements
        or whole definitions, or whose braces stand in `#define` bodies, keeps
        every branch.
        """
        from tools.qa.tree import Tree

        folder = tempfile.mkdtemp(prefix="kg-tree-")
        try:
            Path(folder, "x.c").write_text(
                "int opens(int a)\n"
                "{\n"
                "#ifdef A\n"
                "\tif (a == 1 ||\n"
                "\t    a == 2) {\n"
                "#else\n"
                "\tif (a == 1) {\n"
                "#endif\n"
                "\t\ta++;\n"
                "\t}\n"
                "\treturn a;\n"
                "}\n"
                "\n"
                "int operands(int a)\n"
                "{\n"
                "\tif (a == 1 ||\n"
                "#ifdef A\n"
                "\t    a == 2 ||\n"
                "#else\n"
                "\t    a == 3 ||\n"
                "#endif\n"
                "\t    !a) {\n"
                "\t\treturn 0;\n"
                "\t}\n"
                "\treturn a;\n"
                "}\n"
                "\n"
                "static int parameters(int a,\n"
                "#ifdef A\n"
                "\t\t      int b,\n"
                "#endif\n"
                "\t\t      int c)\n"
                "{\n"
                "\treturn a + c;\n"
                "}\n"
                "\n"
                "#ifdef A\n"
                "#define BEGIN {\n"
                "#else\n"
                "#define BEGIN do {\n"
                "#endif\n"
                "\n"
                "#ifdef B\n"
                "int whole(void)\n"
                "{\n"
                "\treturn 0;\n"
                "}\n"
                "#else\n"
                "int whole(void);\n"
                "#endif\n"
                "\n"
                "int last(void)\n"
                "{\n"
                "#ifdef A\n"
                "\treturn 1;\n"
                "#else\n"
                "\treturn 0;\n"
                "#endif\n"
                "}\n"
            )
            tree = Tree(folder, profile(str(ROOT)))
            found = [
                (t["kind"], t["name"], t["head"], t["end"])
                for t in tree.tags("x.c")
                if t["kind"] in ("function", "prototype", "macro")
            ]
            self.assertEqual(
                found,
                [
                    ("function", "opens", 1, 12),
                    ("function", "operands", 14, 26),
                    ("function", "parameters", 28, 35),
                    ("macro", "BEGIN", 38, 38),
                    ("macro", "BEGIN", 40, 40),
                    ("function", "whole", 44, 47),
                    ("prototype", "whole", 49, 49),
                    ("function", "last", 52, 59),
                ],
            )
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def tree_with(self, name, text):
        """A Tree over a temporary folder that holds the one file `name`,
        removed with the test."""
        from tools.qa.tree import Tree

        folder = tempfile.mkdtemp(prefix="kg-tree-")
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        Path(folder, name).write_text(text)
        return Tree(folder, profile(str(ROOT)))

    @staticmethod
    def spans(tree, name, kinds=None):
        return sorted(
            (t["head"], t["end"], t["kind"], t["name"])
            for t in tree.tags(name)
            if (kinds is None and t["kind"] not in ("member", "enumerator"))
            or (kinds and t["kind"] in kinds)
        )

    def test_tree_leaves_an_attribute_macro_alone_in_a_directive(self):
        """tools/qa/tree.py: an attribute macro is blanked where a declaration
        uses it, never on a directive's lines. The definition of `__init`
        (include/linux/init.h) with its name blanked was read as defining the
        last word of its body, and `__bss_decrypted` (mem_encrypt.h) with its
        body blanked ran on over the declarations below it."""
        tree = self.tree_with(
            "x.h",
            '#define __init\t\t__section(".init.text")'
            " __cold\t\\\n\t\t\t\t\t\t__no_erase\n#define __bss_decrypted"
            ' __section(".bss..decrypted")\n\nextern char'
            " __start_bss_decrypted[], __end_bss_decrypted[];\n\nstatic int"
            " __init setup(void)\n{\n\treturn 0;\n}\n",
        )
        self.assertEqual(
            self.spans(tree, "x.h"),
            [
                (1, 2, "macro", "__init"),
                (3, 3, "macro", "__bss_decrypted"),
                (5, 5, "variable", "__end_bss_decrypted"),
                (5, 5, "variable", "__start_bss_decrypted"),
                (7, 10, "function", "setup"),
            ],
        )

    def test_tree_reads_the_declarator_before_an_attribute_it_does_not_know(
        self,
    ):
        """tools/qa/tree.py: an attribute macro the list does not name, after a
        declarator (mm/memblock.c's `struct memblock memblock
        __initdata_memblock = {`), was read as the variable's name; the
        variable keeps its own name and its whole initializer. A prototype
        whose first word after the type is such a macro (include/linux/list.h's
        __list_add_valid_or_report) keeps the name tree-sitter already reads.
        """
        tree = self.tree_with(
            "x.c",
            "static struct region regions[4] __initdata_table;\n"
            "\n"
            "struct table table __initdata_table = {\n"
            "\t.regions = regions,\n"
            "\t.max = 4,\n"
            "};\n"
            "\n"
            "bool __list_valid_slowpath __list_add_valid_or_report(struct"
            " list_head *new,\n"
            "\t\t\t\t\t\t      struct list_head *prev);\n",
        )
        self.assertEqual(
            self.spans(tree, "x.c", ("variable",)),
            [(1, 1, "variable", "regions"), (3, 6, "variable", "table")],
        )
        self.assertEqual(
            [t["name"] for t in tree.tags("x.c") if t["kind"] == "prototype"],
            ["__list_add_valid_or_report"],
        )

    def test_tree_finds_definitions_after_a_macro_without_semicolon(
        self,
    ):
        """tools/qa/tree.py: a macro invocation that stands alone at file scope
        with no `;` (include/linux/pci.h's `_PCI_NOP_ALL(read, *)`,
        drivers/pci/pcie/aer.c's `aer_ratelimit_attrs(correctable)`) is read by
        tree-sitter as the type of what follows it, and the definitions after
        it were lost or filed under a keyword; each is read. A name on a line
        of its own under its return type (spinlock_api_smp.h's
        _raw_spin_lock_nest_lock) is a declarator, not such an invocation."""
        tree = self.tree_with(
            "x.h",
            "#define _NOP(o, s, t) \\\n"
            "\tstatic inline int cfg_##o##_##s(int where, t val) \\\n"
            "\t\t{ return -1; }\n"
            "\n"
            "#define _NOP_ALL(o, x)\t_NOP(o, byte, u8 x) \\\n"
            "\t\t\t_NOP(o, word, u16 x)\n"
            "_NOP_ALL(read, *)\n"
            "_NOP_ALL(write,)\n"
            "\n"
            "static inline void flush_queue(void) { }\n"
            "\n"
            "static inline struct dev *get_device(unsigned int vendor,\n"
            "\t\t\t\t     struct dev *from)\n"
            "{ return NULL; }\n"
            "\n"
            "ratelimit_attrs(correctable)\n"
            "ratelimit_attrs(nonfatal)\n"
            "\n"
            "static struct attribute *aer_attrs[] = {\n"
            "\t&dev_attr_correctable.attr,\n"
            "\tNULL\n"
            "};\n"
            "\n"
            "static umode_t aer_attrs_are_visible(struct kobject *kobj,\n"
            "\t\t\t\t     struct attribute *a, int n)\n"
            "{\n"
            "\treturn a->mode;\n"
            "}\n"
            "\n"
            "void __lockfunc\n"
            "_raw_spin_lock_nest_lock(raw_spinlock_t *lock, struct"
            " lockdep_map *map)\n"
            "\t\t\t\t\t\t\t\t__acquires(lock);\n",
        )
        self.assertEqual(
            self.spans(tree, "x.h", ("function", "variable")),
            [
                (10, 10, "function", "flush_queue"),
                (12, 14, "function", "get_device"),
                (19, 22, "variable", "aer_attrs"),
                (24, 28, "function", "aer_attrs_are_visible"),
            ],
        )
        self.assertEqual(
            [
                (t["name"], t["line"])
                for t in tree.tags("x.h")
                if t["kind"] == "prototype"
            ],
            [("_raw_spin_lock_nest_lock", 31)],
        )
        self.assertEqual(
            tree.construct_at("x.h", 27)["name"], "aer_attrs_are_visible"
        )

    def test_tree_names_a_function_by_its_signature(self):
        """tools/qa/tree.py: a specifier macro tree-sitter does not know, above
        or beside a return type that opens with `struct` or `enum`
        (amdgpu_dm_connector.c's `STATIC_IFN_KUNIT struct dc_stream_state *`),
        was read as a variable named `struct` on the function's first line,
        which then held that line in the function's place; and an attribute
        with arguments above the name (fortify-string.h's `__diagnose_as(...)`)
        took the name or lost the function. No fact is named by a C keyword and
        each function has its own name; a function a macro writes keeps the
        name tree-sitter gives it."""
        tree = self.tree_with(
            "x.c",
            "__FORTIFY_INLINE __diagnose_as(__builtin_strlen, 1)\n"
            "__kernel_size_t __fortify_strlen(const char * const POS p)\n"
            "{\n"
            "\treturn __member_size(p);\n"
            "}\n"
            "\n"
            "STATIC_IFN_KUNIT struct dc_stream_state *\n"
            "create_stream(struct drm_connector *connector)\n"
            "{\n"
            "\treturn NULL;\n"
            "}\n"
            "\n"
            "STATIC_IFN_KUNIT enum dc_status validate_stream(struct"
            " dc_stream_state *stream)\n"
            "{\n"
            "\treturn 0;\n"
            "}\n"
            "\n"
            "DEFINE_IDTENTRY(exc_divide_error)\n"
            "{\n"
            "\tdo_error_trap(regs, 0);\n"
            "}\n"
            "\n"
            "SYSCALL_DEFINE2(getcwd, char __user *, buf, unsigned long, size)"
            "\n"
            "{\n"
            "\treturn 0;\n"
            "}\n",
        )
        self.assertEqual(
            [
                (t["kind"], t["name"], t["head"], t["line"], t["end"])
                for t in sorted(tree.tags("x.c"), key=lambda t: t["head"])
            ],
            [
                ("function", "__fortify_strlen", 2, 2, 5),
                ("function", "create_stream", 7, 8, 11),
                ("function", "validate_stream", 13, 13, 16),
                ("function", "exc_divide_error", 18, 18, 21),
                ("function", "SYSCALL_DEFINE2", 23, 23, 26),
            ],
        )
        self.assertEqual(
            [tree.construct_at("x.c", n)["name"] for n in (7, 13)],
            ["create_stream", "validate_stream"],
        )

    def test_tree_ends_a_function_at_its_own_closing_brace(self):
        """tools/qa/tree.py: a block a macro closes (kernel/cgroup/cgroup.c's
        `} while_each_thread(leader, task);`) made tree-sitter run the function
        on over the ones after it, and a block a macro opens around a `goto`
        (kernel/events/core.c's `scoped_guard (rcu) {`) made it end the
        function at an inner brace; a function runs from its signature to the
        `}` that kernel style puts in column 0, and the next one is read.
        """
        tree = self.tree_with(
            "x.c",
            "int attach(struct task *leader)\n"
            "{\n"
            "\tstruct task *task = leader;\n"
            "\n"
            "\tdo {\n"
            "\t\tadd(task);\n"
            "\t} while_each_thread(leader, task);\n"
            "\treturn 0;\n"
            "}\n"
            "\n"
            "int after(void)\n"
            "{\n"
            "\treturn 0;\n"
            "}\n"
            "\n"
            "static int\n"
            "attach_all(int n)\n"
            "{\n"
            "again:\n"
            "\tscoped_guard (rcu) {\n"
            "\t\tfor_each_thread(g, p) {\n"
            "\t\t\tif (p)\n"
            "\t\t\t\tcontinue;\n"
            "\t\t\tgoto alloc;\n"
            "\t\t}\n"
            "\t}\n"
            "\n"
            "\treturn 0;\n"
            "alloc:\n"
            "\tn++;\n"
            "\tgoto again;\n"
            "}\n"
            "\n"
            "static int last(void)\n"
            "{\n"
            "\treturn 0;\n"
            "}\n",
        )
        self.assertEqual(
            self.spans(tree, "x.c"),
            [
                (1, 9, "function", "attach"),
                (11, 14, "function", "after"),
                (16, 32, "function", "attach_all"),
                (34, 37, "function", "last"),
            ],
        )

    def test_tree_reads_a_type_a_macro_opens_and_a_body_of_macros(self):
        """tools/qa/tree.py: `context_lock_struct(mutex) {`
        (include/linux/mutex_types.h) was read as a function named mutex, and a
        struct whose body is two macros with no `;`
        (drivers/acpi/acpica/amlresrc.h's struct aml_resource_address) was lost
        with what follows it; each is a struct with its own members, and a
        macro is neither a member nor a member's type."""
        tree = self.tree_with(
            "x.h",
            "context_lock_struct(mutex) {\n"
            "\tatomic_long_t\t\towner;\n"
            "\traw_spinlock_t\t\twait_lock;\n"
            "#ifdef CONFIG_MUTEX_SPIN_ON_OWNER\n"
            "\tstruct optimistic_spin_queue osq;\n"
            "#endif\n"
            "\tstruct mutex_waiter\t*first_waiter __guarded_by(&wait_lock);\n"
            "};\n"
            "\n"
            "struct aml_resource_address {\n"
            "AML_RESOURCE_LARGE_HEADER_COMMON AML_RESOURCE_ADDRESS_COMMON};\n"
            "\n"
            "struct aml_resource_extended_address64 {\n"
            "\tAML_RESOURCE_LARGE_HEADER_COMMON\n"
            "\t    AML_RESOURCE_ADDRESS_COMMON u8 revision_ID;\n"
            "\tu8 reserved;\n"
            "};\n"
            "\n"
            "struct aml_resource_csi2_serialbus {\n"
            "\tAML_RESOURCE_LARGE_HEADER_COMMON AML_RESOURCE_SERIAL_COMMON\n"
            "\t    /*\n"
            "\t     * Optional fields follow immediately\n"
            "\t     */\n"
            "};\n"
            "\n"
            "struct plain {\n"
            "\tint a;\n"
            "};\n",
        )
        self.assertEqual(
            self.spans(tree, "x.h"),
            [
                (1, 8, "struct", "mutex"),
                (10, 11, "struct", "aml_resource_address"),
                (13, 17, "struct", "aml_resource_extended_address64"),
                (19, 24, "struct", "aml_resource_csi2_serialbus"),
                (26, 28, "struct", "plain"),
            ],
        )

        def members(name):
            return [
                (t["name"], t["line"], t["typeref"])
                for t in tree.members_of("x.h", name)
            ]

        self.assertEqual(
            members("mutex"),
            [
                ("owner", 2, "typename:atomic_long_t"),
                ("wait_lock", 3, "typename:raw_spinlock_t"),
                ("osq", 5, "struct:optimistic_spin_queue"),
                ("first_waiter", 7, "struct:mutex_waiter"),
            ],
        )
        self.assertEqual(
            members("aml_resource_address")
            + members("aml_resource_csi2_serialbus"),
            [],
        )
        self.assertEqual(
            members("aml_resource_extended_address64"),
            [
                ("revision_ID", 15, "typename:u8"),
                ("reserved", 16, "typename:u8"),
            ],
        )

    def test_tree_finds_an_initialized_variable_the_parse_lost(self):
        """tools/qa/tree.py: after a declaration a macro writes over several
        lines (sound/soc/codecs/rt5682.c's `static const
        DECLARE_TLV_DB_RANGE(bst_tlv, ...);`) tree-sitter lost the variables
        and the functions that follow; a variable is read whether its
        initializer begins on the line after its `=` or opens a block on that
        line, and so is the function after them."""
        declared = (
            "static const DECLARE_TLV_DB_RANGE(%s,\n"
            "\t0, 0, TLV_DB_SCALE_ITEM(0, 0, 0),\n"
            "\t1, 1, TLV_DB_SCALE_ITEM(2000, 0, 0),\n"
            "\t2, 2, TLV_DB_SCALE_ITEM(2400, 0, 0),\n"
            "\t3, 5, TLV_DB_SCALE_ITEM(3000, 500, 0),\n"
            "\t6, 6, TLV_DB_SCALE_ITEM(4400, 0, 0),\n"
            "\t7, 7, TLV_DB_SCALE_ITEM(5000, 0, 0),\n"
            "\t8, 8, TLV_DB_SCALE_ITEM(5200, 0, 0)\n"
            ");\n"
            "\n"
        )
        tree = self.tree_with(
            "x.c",
            "/* {0, +20, +24, +30, +35, +40, +44, +50, +52} dB */\n"
            + declared % "bst_tlv"
            + "static const struct snd_kcontrol_new if2_adc_swap_mux"
            ' =\n\tSOC_DAPM_ENUM("IF2 ADC Swap Mux", if2_adc_enum);\n\n'
            + declared % "mic_tlv"
            + 'static const char * const data_select[] = {\n\t"L/R", "R/L",'
            ' "L/L", "R/R"\n};\n\nstatic int probe(void)\n{\n\treturn'
            " 0;\n}\n",
        )
        self.assertEqual(
            self.spans(tree, "x.c"),
            [
                (12, 13, "variable", "if2_adc_swap_mux"),
                (25, 27, "variable", "data_select"),
                (29, 32, "function", "probe"),
            ],
        )

    def test_tree_reads_a_macro_from_define_to_end_of_continuation(
        self,
    ):
        """tools/qa/tree.py: a comment inside a macro's body ends tree-sitter's
        reading of the macro, and it reads the rest of the body as code: the
        macro ended at the comment (include/linux/interval_tree_generic.h's
        INTERVAL_TREE_DEFINE), the members of its body were filed as variables
        of the file (drivers/acpi/acpica/aclocal.h's ACPI_STATE_COMMON), or the
        macro took the name of a word of its body (include/drm/drm_atomic.h's
        for_each_oldnew_connector_in_state). A macro is named by its `#define`
        line and runs to the end of its continuation, nothing but a function
        with a body of its own is filed out of it, and such a function, which a
        macro that writes functions holds, stays a place a page can name.
        """
        pad = "\t\t\t      \\\n"
        tree = self.tree_with(
            "x.h",
            "#define TREE_DEFINE(ITSTRUCT, ITSTATIC, ITPREFIX)"
            + pad
            + "\t\t\t\t\t\t"
            + pad
            + "/* Insert a node into the tree */\t\t"
            + pad
            + "\t\t\t\t\t\t"
            + pad
            + "ITSTATIC void ITPREFIX ## _insert(ITSTRUCT *node)"
            + pad
            + "{\t\t\t\t\t\t"
            + pad
            + "\tnode->last = 0;\t\t\t\t"
            + pad
            + "}\t\t\t\t\t\t"
            + pad
            + "\t\t\t\t\t\t"
            + pad
            + "/*\t\t\t\t\t\t"
            + pad
            + " * Iterate over the nodes\t\t\t"
            + pad
            + " */\t\t\t\t\t\t"
            + pad
            + "\t\t\t\t\t\t"
            + pad
            + "ITSTATIC ITSTRUCT *ITPREFIX ## _iter_first(ITSTRUCT *node)"
            + pad
            + "{\t\t\t\t\t\t"
            + pad
            + "\treturn node;\t\t\t\t\t"
            + pad
            + "}\n\n#define STATE_COMMON \\\n\tvoid                           "
            " *next; \\\n"
            "\tu8                              descriptor_type; /* To tell"
            " the objects apart */\\\n"
            "\tu8                              flags; \\\n"
            "\tu16                             value;\n"
            "\n"
            "#define for_each_pair(__state, old_state, new_state, __i) \\\n"
            "\tfor ((__i) = 0; (__i) < (__state)->num; (__i)++) \\\n"
            "\t\tfor_each_if (((old_state) = (__state)->old[__i], \\\n"
            "\t\t\t     (void)(old_state) /* Only to avoid a warning */, \\\n"
            "\t\t\t     (new_state) = (__state)->new[__i], 1))\n"
            "\n"
            "int after;\n",
        )
        self.assertEqual(
            self.spans(tree, "x.h", ("macro", "variable")),
            [
                (1, 17, "macro", "TREE_DEFINE"),
                (19, 23, "macro", "STATE_COMMON"),
                (25, 29, "macro", "for_each_pair"),
                (31, 31, "variable", "after"),
            ],
        )
        self.assertIn(
            (14, 17, "function", "_iter_first"),
            self.spans(tree, "x.h", ("function",)),
        )
        self.assertEqual(
            [tree.construct_at("x.h", n)["name"] for n in (7, 16, 22, 28)],
            ["TREE_DEFINE", "_iter_first", "STATE_COMMON", "for_each_pair"],
        )

    def test_lint_checks_plugin_root_paths_in_documents(self):
        (self.skill / "README.md").write_text(
            "Run `${CLAUDE_PLUGIN_ROOT}/extra/run.sh` first.\n"
        )
        self.assertTrue(
            any(
                "missing reference ${CLAUDE_PLUGIN_ROOT}/extra/run.sh" in p
                for p in lint_rules(self.skill)
            )
        )
        (self.skill / "extra").mkdir()
        (self.skill / "extra" / "run.sh").write_text("true\n")
        self.assertFalse(
            any("CLAUDE_PLUGIN_ROOT" in p for p in lint_rules(self.skill))
        )

    def test_lint_keeps_the_conventions_of_claude_md_in_every_skill(self):
        """The host loads CLAUDE.md only where the repository is the working
        directory, so each skill repeats its list items word for word; a
        missing or reworded item is a problem, and a checkout without a skill
        has none.
        """
        (self.skill / "CLAUDE.md").write_text(
            "# kernel-glossary\n"
            "\n"
            "Conventions:\n"
            "\n"
            "- Facts come from the pinned tree.\n"
            "- Nothing here is submitted upstream.\n"
        )
        self.assertEqual(lint_rules(self.skill), [])
        folder = self.skill / "skills" / "one"
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text(
            "---\n"
            "name: one\n"
            "---\n"
            "\n"
            "- Facts come from the pinned tree.\n"
            "- Nothing is submitted upstream.\n"
        )
        problems = lint_rules(self.skill)
        self.assertEqual(len(problems), 1)
        self.assertIn(
            "SKILL.md: the convention of CLAUDE.md is missing or reworded: -"
            " Nothing here is submitted upstream.",
            problems[0],
        )
        (folder / "SKILL.md").write_text(
            "---\n"
            "name: one\n"
            "---\n"
            "\n"
            "- Facts come from the pinned tree.\n"
            "- Nothing here is submitted upstream.\n"
        )
        self.assertEqual(lint_rules(self.skill), [])

    def test_lint_reads_band_and_pattern_tables(self):
        self.rule(
            "new.band",
            "# Band\n"
            "\n"
            "| Unit | Measure | Target | Review candidate | Violation |\n"
            "|---|---|---|---|---|\n"
            "| a `P` | words | 45–80 | over 120 | |\n",
            "qa: auto",
        )
        self.rule(
            "new.style",
            "# Style\n"
            "\n"
            "| Pattern | Kind | Scope | Unless | Exception |\n"
            "|---|---|---|---|---|\n"
            "| `\\bfoo\\b` | violation | | | none |\n",
            "qa: auto",
        )
        self.assertEqual(lint_rules(self.skill), [])
        self.rule(
            "new.band",
            "# Band\n"
            "\n"
            "| Unit | Measure | Target | Review candidate | Violation |\n"
            "|---|---|---|---|---|\n"
            "| a `P` | words | about 60 | over 120 | |\n",
            "qa: auto",
        )
        self.assertTrue(any("new.band" in p for p in lint_rules(self.skill)))
        self.rule("new.band", "# Band\n\nNo table.\n", "qa: auto")
        self.rule(
            "new.style",
            "# Style\n"
            "\n"
            "| Pattern | Kind | Scope | Unless | Exception |\n"
            "|---|---|---|---|---|\n"
            "| `\\bfoo\\b` | sometimes | | | none |\n",
            "qa: auto",
        )
        self.assertTrue(any("new.style" in p for p in lint_rules(self.skill)))

    def test_document_rule_ids_survive_activation_changes(self):
        rule = self.rule(
            "new.rule", "A local requirement.\n", policy="qa: manual"
        )
        reference = self.skill / "guidelines/reference.md"
        reference.write_text("Related active rule: `new.rule`.\n")
        self.assertEqual(lint_rules(self.skill), [])
        rule.rename(self.skill / "guidelines/page/rules/inactive/new.rule.md")
        self.assertEqual(lint_rules(self.skill), [])
        self.assertNotIn("new.rule", prompt_rules(self.skill))

    def test_lint_checks_tool_readmes_without_reading_raw_page_fixtures(self):
        folder = self.skill / "tools/research"
        folder.mkdir(parents=True)
        readme = folder / "README.md"
        readme.write_text("Use `tools/research/missing.py`.\n")
        self.assertTrue(
            any(
                "missing reference tools/research/missing.py" in p
                for p in lint_rules(self.skill)
            )
        )
        (folder / "missing.py").write_text("")
        fixtures = self.skill / "tools/qa/tests/cases"
        fixtures.mkdir(parents=True)
        (fixtures / "raw-page.md").write_text(
            "Kernel source: `tools/objtool/check.c`.\n"
        )
        self.assertEqual(lint_rules(self.skill), [])

    def test_lint_keeps_tool_paths_out_of_the_standard(self):
        """The standard names no path this repository holds under tools/; the
        directory alone and a path of the kernel's own tools/ are none."""
        (self.skill / "tools/qa/run.py").write_text("")
        spec = self.skill / "guidelines/campaign/spec.md"
        spec.write_text(
            "# The campaign spec format\n\nThe kernel keeps its selftests"
            " under `tools/testing/selftests/` and its scripts under"
            " `tools/`.\n"
        )
        self.assertEqual(lint_rules(self.skill), [])
        for named in ("`tools/qa/run.py`", "the engine under tools/qa/."):
            spec.write_text(f"# The campaign spec format\n\nRun {named}\n")
            problems = lint_rules(self.skill)
            self.assertEqual(len(problems), 1, problems)
            self.assertIn(
                "guidelines/campaign/spec.md: line 3: the standard names no"
                " tool: tools/qa",
                problems[0],
            )
        readme = self.skill / "tools/qa/README.md"
        readme.write_text("Run `tools/qa/run.py`.\n")
        spec.write_text("# The campaign spec format\n")
        self.assertEqual(lint_rules(self.skill), [])

    def test_lint_rejects_obligations_delegated_to_rule_ids_or_paths(self):
        self.rule("other.rule", "A complete local requirement.\n")
        for body in (
            "Follow `other.rule`.\n",
            "Follow `guidelines/page/rules/active/other.rule.md`.\n",
        ):
            with self.subTest(body=body):
                self.rule("new.rule", body)
                self.assertTrue(
                    any(
                        "keep the requirement and its scope local" in p
                        for p in lint_rules(self.skill)
                    )
                )

    def test_manual_policy_does_not_run_an_existing_checker(self):
        self.rule("new.manual", "Read the relationship.\n", "qa: manual")
        self.implementation(
            "new.manual",
            "raise RuntimeError('Manual policy must not run this')\n",
        )
        report = run("", self.skill, fixed=True)
        self.assertEqual(
            (report["automatic"], report["manual"], report["errors"]),
            ([], ["new.manual"], []),
        )

    def test_auto_error_never_falls_back_or_passes(self):
        self.rule("new.auto", "Need source input.\n", "qa: auto")
        for code in (
            "def check(page, context):\n    return context['source']\n",
            "raise ImportError('source module absent')\n",
            (
                "def check(page, context):\n"
                "    raise TimeoutError('unavailable')\n"
            ),
            "def check(page, context):\n    return None\n",
            (
                "def check(page, context):\n"
                "    return [{'line': 99, 'message': 'bad'}]\n"
            ),
            (
                "def check(page, context):\n"
                "    return [{'line': 1, 'message': 'bad', 'kind':"
                " 'maybe'}]\n"
            ),
            "def check(page, context):\n    raise SystemExit(0)\n",
        ):
            with self.subTest(code=code):
                self.implementation("new.auto", code)
                result = run("# Page\n", self.skill, fixed=True)
                self.assertEqual(result["automatic"], [])
                self.assertEqual(result["manual"], [])
                self.assertEqual(len(result["errors"]), 1)
                self.assertEqual(exit_status(result), 2)

    def test_missing_input_keeps_page_findings_and_rule_incomplete(
        self,
    ):
        self.rule(
            "new.auto",
            "Needs the tree after its page-only part.\n",
            "qa: auto",
        )
        self.implementation(
            "new.auto",
            "from tools.qa.inputs import Missing, violation\n"
            "def check(page, context):\n"
            "    yield violation(1, 'x', 'page-only finding')\n"
            "    context.require('tree')\n"
            "    yield violation(1, 'y', 'never reached')\n",
        )
        result = run("# Page\n", self.skill, fixed=True)
        self.assertEqual(result["automatic"], [])
        self.assertEqual(len(result["errors"]), 1)
        self.assertTrue(
            result["errors"][0]["message"].startswith("incomplete:")
        )
        self.assertEqual(
            [f["quote"] for f in result["errors"][0]["findings"]], ["x"]
        )
        self.assertEqual(exit_status(result), 2)

    def test_candidates_are_manual_work_and_measurements_decide_nothing(self):
        self.rule("new.auto", "Lists candidates.\n", "qa: auto")
        self.implementation(
            "new.auto",
            "from tools.qa.inputs import candidate, measurement\n"
            "def check(page, context):\n"
            "    yield measurement(None, None, 'ten things')\n"
            "    yield candidate(1, 'x', 'read this')\n",
        )
        result = run("# Page\n", self.skill, fixed=True)
        self.assertEqual(
            [f["kind"] for f in result["automatic"][0]["findings"]],
            ["measurement", "candidate"],
        )
        self.assertEqual(exit_status(result), 3)
        self.implementation(
            "new.auto",
            "from tools.qa.inputs import measurement\n"
            "def check(page, context):\n"
            "    yield measurement(None, None, 'ten things')\n",
        )
        self.assertEqual(
            exit_status(run("# Page\n", self.skill, fixed=True)), 0
        )

    def test_a_prefix_selects_a_family_of_rules(self):
        self.rule("fam.one", "A manual rule of the family.\n", "qa: manual")
        self.rule(
            "fam.two", "Another manual rule of the family.\n", "qa: manual"
        )
        self.rule("other.one", "A manual rule outside it.\n", "qa: manual")
        self.rule("fam.off", "An off rule of the family.\n", "qa: off")
        report = run("# T\n", self.skill, prefixes=("fam.",), fixed=True)
        self.assertEqual(sorted(report["manual"]), ["fam.one", "fam.two"])
        report = run(
            "# T\n",
            self.skill,
            prefixes=("fam.",),
            fixed=True,
            include_off=True,
        )
        self.assertEqual(
            sorted(report["manual"]), ["fam.off", "fam.one", "fam.two"]
        )
        with self.assertRaises(RuleError):
            run("# T\n", self.skill, prefixes=("nothing.",), fixed=True)

    def test_metadata_errors_and_disabled_selection_fail_explicitly(self):
        for policy in (
            "qa: manual\nqa: auto",
            "writer: true",
            "writer: false",
            "qa: automation",
            "requires: other.rule",
        ):
            with self.subTest(policy=policy):
                self.rule("new.rule", "Requirement.\n", policy)
                with self.assertRaises(RuleError):
                    load_rules(self.skill)
        self.rule("new.rule", "Requirement.\n")
        with self.assertRaises(RuleError):
            run("", self.skill, only=["new.rule"], fixed=True)
        self.assertEqual(exit_status(run("", self.skill, fixed=True)), 0)

    def test_small_checker_edits_take_effect_immediately(self):
        self.rule("new.auto", "Check the current source.\n", "qa: auto")
        code = (
            "def check(page, context):\n"
            "    return [{'line': 1, 'message': 'A'}]\n"
        )
        self.implementation("new.auto", code)
        self.assertEqual(
            run("Page\n", self.skill, fixed=True)["automatic"][0]["findings"][
                0
            ]["message"],
            "A",
        )
        self.implementation("new.auto", code.replace("'A'", "'B'"))
        self.assertEqual(
            run("Page\n", self.skill, fixed=True)["automatic"][0]["findings"][
                0
            ]["message"],
            "B",
        )

    def test_rule_prompt_works_without_site_packages_or_qa(self):
        self.rule("new.rule", "Requirement.\n")
        result = subprocess.run(
            [
                sys.executable,
                "-S",
                str(ROOT / "tools/rules.py"),
                "prompt",
                "--glossary-checkout",
                str(self.skill),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Requirement.", result.stdout)
        self.assertEqual(result.stdout.count("kg:profile"), 1)

    def test_prompt_contains_one_model_and_all_active_policies(self):
        for policy in ("off", "manual", "auto"):
            self.rule(
                "new." + policy,
                "Unique " + policy + " requirement.\n",
                "qa: " + policy,
            )
        prompt = prompt_rules(self.skill)
        self.assertEqual(prompt.count("<!-- page model -->"), 1)
        for policy in ("off", "manual", "auto"):
            self.assertIn(
                "<!-- rule: new." + policy + "; qa: " + policy + " -->", prompt
            )
            self.assertIn("Unique " + policy + " requirement.", prompt)

    def test_prompt_rejects_missing_or_empty_model(self):
        path = self.skill / "guidelines/page/page-model.md"
        path.write_text("")
        with self.assertRaises(RuleError):
            prompt_rules(self.skill)
        path.unlink()
        with self.assertRaises(OSError):
            prompt_rules(self.skill)


class PageChecks(unittest.TestCase):
    def check(self, identity, text):
        return list(
            checker(
                ROOT / "tools/qa/checks" / (identity + ".py"), identity
            ).check(Page(text, "page.md", str(ROOT)), {})
        )

    def test_wrapped_prose_is_checked_before_any_renderer_joins_it(self):
        findings = self.check(
            "page.one-line-paragraphs", "# Page\n\nFirst line.\nSecond line.\n"
        )
        self.assertEqual(
            [(r["line"], r["quote"]) for r in findings], [(4, "Second line.")]
        )

    def test_protected_blocks_and_original_locations(self):
        text = (
            "# Page\n"
            "\n"
            "```c\n"
            "/* x.c:1 */\n"
            "\tfirst\r\n"
            "second\n"
            "```\n"
            "\n"
            "> quoted\n"
            "> wrapped\n"
            "\n"
            "| a | b |\n"
            "|---|---|\n"
            "| c | d |\n"
            "\n"
            "First.\n"
            "Second.\n"
        )
        page = Page(text, "page.md", str(ROOT))
        self.assertEqual(page.source_fences[0].body[1], "\tfirst\r")
        self.assertEqual(
            self.check("page.one-line-paragraphs", text)[0]["line"], 17
        )
        self.assertEqual(self.check("geometry.figure-tabs", text), [])
        diagram = text + "\n```\n    ┌───┐\n\t└───┘\n```\n"
        self.assertEqual(
            self.check("geometry.figure-tabs", diagram)[0]["line"], 21
        )

    def test_bad_fences_fail_and_block_other_auto_checks(self):
        for text, line in (
            ("# Page\n\n```c\nbody\n", 3),
            ("```\nbody\n```trailing\n", 3),
        ):
            with self.subTest(text=text):
                self.assertEqual(
                    self.check("page.fence-close", text)[0]["line"], line
                )
                result = run(
                    text,
                    ROOT,
                    only=["page.fence-close", "page.one-line-paragraphs"],
                    fixed=True,
                    include_off=True,
                )
                self.assertTrue(result["automatic"][0]["findings"])
                self.assertEqual(
                    result["errors"][0]["rule"], "page.one-line-paragraphs"
                )

    def test_catalog_config_requires_non_c_provenance(self):
        self.assertEqual(
            self.check(
                "excerpts.catalog-completeness",
                case_text("catalog-config-key.md"),
            ),
            [],
        )
        rows = self.check(
            "excerpts.catalog-completeness",
            case_text("catalog-config-key-in-c.md"),
        )
        self.assertEqual(rows[0]["quote"], "CONFIG_USB4_DEBUGFS_WRITE")

    def test_cli_writes_nothing_and_reports_a_delta(self):
        with tempfile.TemporaryDirectory() as folder:
            page = Path(folder) / "page.md"
            notes = Path(folder) / "notes.md"
            page.write_text(case_text("clean-page.md"), encoding="utf-8")
            notes.write_text(
                "# Notes\n\nA file beside the page stays untouched.\n"
            )
            before = {p.name: p.read_bytes() for p in Path(folder).iterdir()}
            identities = [
                "page.one-line-paragraphs",
                "page.fence-close",
                "geometry.figure-tabs",
                "excerpts.catalog-completeness",
                "style.hedges",
            ]
            args = [
                sys.executable,
                str(ROOT / "tools/qa/run.py"),
                str(page),
                "--json",
                "--include-off",
            ]
            for identity in identities:
                args.extend(["--rule", identity])
            result = subprocess.run(
                args, cwd=folder, capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(
                {item["rule"] for item in report["automatic"]}, set(identities)
            )
            self.assertEqual((report["manual"], report["errors"]), ([], []))
            self.assertEqual(
                before,
                {p.name: p.read_bytes() for p in Path(folder).iterdir()},
            )
            previous = Path(folder) / "previous.json"
            previous.write_text(result.stdout)
            page.write_text(
                page.read_text(encoding="utf-8").replace(
                    "is therefore one word", "is simply one word"
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [a for a in args if a != "--json"]
                + ["--since", str(previous)],
                cwd=folder,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("1 new, 0 gone, 0 standing", result.stdout)
            self.assertEqual(
                before
                | {
                    "previous.json": previous.read_bytes(),
                    "page.md": page.read_bytes(),
                },
                {p.name: p.read_bytes() for p in Path(folder).iterdir()},
            )


class SourceText(unittest.TestCase):
    def test_code_text_blanks_the_comments_and_keeps_the_code(self):
        """A source line is read without its comments, column for column: a
        comment that opens and closes on the line leaves the code before and
        after it, and only a `*/` with no `/*` before it on the line closes a
        comment begun above.
        """
        for line, code in (
            ("int x; /* the lock */", "int x;"),
            (
                "#define PCI_PM_D3HOT_WAIT 10\t/* msec */",
                "#define PCI_PM_D3HOT_WAIT 10",
            ),
            ("int a; /* one */ int b; /* two */", "int a;           int b;"),
            ("x = 1; // note", "x = 1;"),
            ("int x; /* the lock", "int x;"),
            ("by the caller */ int y;", "                 int y;"),
            ("end */ int y; /* next */", "       int y;"),
            (" * held by the caller", ""),
            ("/* a whole line */", ""),
            ("int z;", "int z;"),
        ):
            blanked = code_text(line)
            self.assertEqual(len(blanked), len(line), line)
            self.assertEqual(blanked.rstrip(), code, line)

    def test_a_bare_declaration_stands_before_its_comment(self):
        """links.definition-line: an incomplete type the tree declares and
        never defines links its declaration line, and a comment after the
        declaration does not hide it.
        """
        link = unittest.mock.Mock()
        link.name = "encoded_page"
        self.assertTrue(declares_bare_type(link, "struct encoded_page;"))
        self.assertTrue(
            declares_bare_type(link, "struct encoded_page;\t/* opaque */")
        )
        self.assertFalse(
            declares_bare_type(link, "/* struct encoded_page; */")
        )
        self.assertFalse(
            declares_bare_type(link, "in the comment */ struct page;")
        )


class TreeLocation(unittest.TestCase):
    def test_tree_is_the_checkout_whose_claude_directory_holds_the_repository(
        self,
    ):
        from tools.qa.tree import resolve_tree

        with (
            tempfile.TemporaryDirectory() as folder,
            unittest.mock.patch.dict("os.environ"),
        ):
            os.environ.pop("KG_TREE", None)
            checkout = (
                Path(folder) / "x" / ".claude" / "skills" / "kernel-glossary"
            )
            checkout.mkdir(parents=True)
            (Path(folder) / "x" / "Kconfig").write_text("", encoding="utf-8")
            found, how, candidate = resolve_tree(None, str(checkout))
            self.assertEqual(
                (found, how), (str(Path(folder) / "x"), "convention")
            )
            found, how, candidate = resolve_tree(None, folder)
            self.assertIsNone(found)
            self.assertIn("no .claude directory above", candidate)
            found, how, _candidate = resolve_tree(
                str(Path(folder) / "x"), folder
            )
            self.assertEqual((found, how), (str(Path(folder) / "x"), "option"))


if __name__ == "__main__":
    unittest.main()
