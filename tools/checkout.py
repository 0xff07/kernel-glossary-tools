#!/usr/bin/env python3
"""Where the kernel tree is, answered one way for every tool of this
repository."""

import os
from pathlib import Path


def absolute(path):
    """`path` made absolute as text: `..` is folded and a symbolic link is
    kept, so that a checkout reached through a link stays under the directory
    that links it. pathlib has `absolute()`, which keeps `..`, and `resolve()`,
    which follows links; this is the one place that asks os.path instead."""
    return Path(os.path.abspath(path))


def tree_of(checkout):
    """The kernel checkout whose .claude directory holds this repository's
    checkout: the parent of the nearest ancestor directory named .claude, or
    None when no ancestor is named so."""
    here = absolute(checkout)
    for directory in (here, *here.parents):
        if directory.name == ".claude":
            return str(directory.parent)
    return None


def tree_default(checkout, explicit=None):
    """(path or None, how): the explicit path, else $KG_TREE, else
    tree_of(checkout); how is "option" for the first two and "convention" for
    the last."""
    explicit = explicit or os.environ.get("KG_TREE")
    if explicit:
        return str(absolute(explicit)), "option"
    return tree_of(checkout), "convention"


def tree_or_exit(checkout, explicit=None):
    """The kernel tree as tree_default finds it; SystemExit, naming what to
    pass, when there is none."""
    found, _how = tree_default(checkout, explicit)
    if found is None:
        raise SystemExit(
            f"no .claude directory above {checkout}; pass --tree or set"
            " KG_TREE"
        )
    return found
