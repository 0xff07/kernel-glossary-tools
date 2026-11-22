# Setup notes

The basic installation is in the [quick start](../README.md#install). These notes cover other layouts and optional tools. They describe existing behavior; they are not inputs to the skills or workflows.

## Select a kernel checkout

By default, the kernel tree is the checkout whose `.claude/` directory contains the plugin. The [prepare script](../skills/write-campaign/scripts/prepare.sh) reads the commit from the plan's Campaign block and refuses a tree at another commit.

For a campaign pinned to another checkout, export its path before running the skill:

```sh
export KG_TREE=/path/to/the/pinned/kernel
```

A `tags` file from `make tags` speeds up the research pack. Without it, the pack falls back to `git grep` and takes about a minute per page.

## Python environment

The workflows and shell scripts use the plugin checkout's `.venv/bin/python` when it exists. `KG_PYTHON` selects another interpreter for those scripts. The planning skill also invokes the campaign tool directly through `.venv/bin/python`, so keep that environment available in the plugin checkout.

The two requirement files install the QA and campaign dependencies, at the exact versions the test suites pass on. The QA runner's source-reading rules need tree-sitter with its C grammar. Without them, the eight tree rules remain incomplete and require manual checking; the brief reports this. `.venv/` is ignored by git.

## Python style

The Python under `tools/` is formatted by Black at 79 columns and passes flake8. CI checks both.

```sh
.venv/bin/pip install -r tools/requirements-lint.txt
.venv/bin/black tools
.venv/bin/flake8 tools
```

The code also keeps a short list of conventions, adapted from the Python section of the [Checkbox providers guidance](https://github.com/canonical/checkbox/blob/main/providers/README.md):

- Paths go through `pathlib`. `tools/checkout.py` holds the one `os.path` call, which makes a path absolute without following symbolic links.
- A file is read and written through a `Path` method or under `with`.
- A command runs through `subprocess`; its exit status is checked and its error output goes into the message.
- A script parses its arguments with `argparse` and keeps only `main()` under `if __name__ == "__main__":`. A failure leaves through `raise SystemExit`, carrying the message when the status is 1.
- An entry script makes the repository importable with the lines under `if not __package__:` and imports every other module as `tools.<name>`.
- A finding of the linter is fixed, never silenced with `# noqa`.

## Install outside the kernel tree

A clone elsewhere can be loaded through `CLAUDE_CODE_PLUGIN_DIRS`:

```sh
export CLAUDE_CODE_PLUGIN_DIRS=/absolute/path/to/the/plugin
export KG_TREE=/path/to/the/pinned/kernel
```

Set these in the shell profile or in a settings file's `env` block. Multiple plugin paths are separated by `:`. The external clone needs the same Python environment as the installation in the quick start.

The [manifest](../.claude-plugin/plugin.json) names the plugin `kernel-glossary`, which is the prefix of its skills; the repository is named `kernel-glossary-tools`. The three skills are the plugin's entry points. The workflow scripts sit beside the two skills that carry one and are not registered with the host separately.

## Optional research tools

A campaign names one tool per kind of question. [Research tools](../skills/research-tools.md) records their uses and measured limitations. When a tool is unavailable, that class of question is handled by hand.

- **Symbol index.** Register the `codebase-memory-mcp` server with the agent host and index the kernel checkout. `list_projects` identifies the project; `check_index_coverage` opens every file question.
- **Compile database.** Generate `compile_commands.json` at the kernel root from an `LLVM=1` build, using `make LLVM=1 compile_commands.json` or `scripts/clang-tools/gen_compile_commands.py` after the build. Use `clang`, `clang-query` and `clang-check` from the same LLVM installation. `pahole` helps when the objects contain full DWARF.
- **Universal Ctags.** The research pack's second pass and plan reviews use `ctags` for definition and end lines. The tree's `tags` file from `make tags` is optional; when available, `readtags` serves the pack first.
- **Git.** Used to inspect the pinned source and its history.
- **semcode.** Install [facebookexperimental/semcode](https://github.com/facebookexperimental/semcode) with its MCP server and index the kernel checkout with `semcode-index -s .`. Its `find_implementors` and `find_registrations` tools answer which functions a call through a struct member can reach. Without it, `git grep` and `clang-query` answer that question.

The [writer aids](../tools/writer/README.md) provide source excerpts, symbol anchors, template expansion and figure insertion with mark renumbering. They use the Python standard library; the figure tool also needs PyYAML, and `excerpt.py --whole` the QA dependencies.

## Workflow opt-in

Invoking a skill is the opt-in required by the Workflow tool. A prose request such as "write batch 23 of the PCI campaign" prompts Claude to ask once before launching agents. You can also explicitly say "use a workflow" or enable ultracode for the session.

The [QA guide](../tools/qa/README.md) covers the runner, views, checker API, conformance corpus and tests. The [campaign tool guide](../tools/campaign/README.md) covers its commands and tests.
