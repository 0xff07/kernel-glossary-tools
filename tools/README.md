# Tools

This directory began as a place to keep tools, so that agents would stop generating the same tool again and again. Apart from a simple frame that lets an agent sort its tools, no human work has gone into it. The tools are used and maintained by agents only: none has a stable interface, and a more capable agent may rewrite any of them completely at any time.

## What is stable

Nothing in this directory. What stays is defined outside it, in `guidelines/`:

- the formats: the page, the scope names and the rules under `guidelines/page/`, the campaign spec in `guidelines/campaign/spec.md`;
- the procedures over those formats, each stated so that it can be carried out by hand.

The standard names no file of this directory, and a tool implements the standard without being its source: a format changes there first, and where a tool and the standard differ, the tool is wrong.

## How a tool is used

A tool says how it is run in two places, both kept beside the code: the README of its directory and the `--help` of its command line. Read them before running a tool and trust them over any command remembered from an earlier version; a document elsewhere in this repository that gives a command is repeating them and may have fallen behind.

| path | what it does | how it is run |
|---|---|---|
| `qa/` | checks a page against the active rules | `tools/qa/README.md` |
| `campaign/` | carries out the procedures of the campaign spec: validation, the index, a page's content, the notes and the assignments | `tools/campaign/README.md` |
| `writer/` | mechanical aids for a page writer: anchors, excerpts, figures | `tools/writer/README.md` |
| `rules.py` | loads the rules and prints them, for a prompt or as a list | `python3 tools/rules.py --help` |
| `guidelines_lint.py` | checks the rule files and the references between the documents | `python3 tools/guidelines_lint.py` |
| `tagsfile.py`, `checkout.py` | modules the tools share: the tree's tags file, and where the kernel tree is | imported, not run |

## The frame

- One directory per kind of work, with a README, the tool's own `requirements.txt` when it needs a package, and its tests under `tests/`. A tool that fits no directory gets a new one, never a place inside another tool.
- The campaign tool and the QA engine never depend on each other: neither imports a module of the other or runs it. They share the spec, the page and the scope names as file formats, each with its own reader.
- The writer aids may read a page through the QA engine. They decide nothing about a page: a page written by hand and a page written with them are checked the same way.
- A tool knows the standard below it and nothing above it: no tool names a procedure of the plugin that runs it.
- `guidelines_lint.py` keeps these directions: it fails when the standard names a path of this directory, and when the standard or a tool names the plugin layer.
