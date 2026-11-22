#!/bin/bash
# Turn this directory into the git repository the conformance cases cite: three commits with fixed
# authors and dates, so every sha is the same on every machine, and HEAD tagged v7.2.
set -e
cd "$(dirname "$0")"
export GIT_AUTHOR_NAME=kg GIT_AUTHOR_EMAIL=kg@example.invalid
export GIT_COMMITTER_NAME=kg GIT_COMMITTER_EMAIL=kg@example.invalid
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null
rm -rf .git
git init -q .
git config commit.gpgsign false
export GIT_AUTHOR_DATE="2020-01-15T12:00:00+00:00" GIT_COMMITTER_DATE="2020-01-15T12:00:00+00:00"
git add drivers/old
git commit -q -m "old: add an old consumer of the port API"
export GIT_AUTHOR_DATE="2026-01-15T12:00:00+00:00" GIT_COMMITTER_DATE="2026-01-15T12:00:00+00:00"
git add Kconfig Documentation drivers/thunderbolt/Kconfig drivers/thunderbolt/tb.c drivers/thunderbolt/tb.h drivers/thunderbolt/tb_regs.h
git commit -q -m "thunderbolt: add the fixture router" -m "Link: https://lore.kernel.org/r/fixture-router@example.invalid"
git add include/linux/thunderbolt.h
git commit -q -m "thunderbolt: add the lanes of an adapter"
export GIT_AUTHOR_DATE="2026-02-01T12:00:00+00:00" GIT_COMMITTER_DATE="2026-02-01T12:00:00+00:00"
git add drivers/thunderbolt/writes.c
git commit -q -m "thunderbolt: add the write forms of a slot"
export GIT_AUTHOR_DATE="2026-02-02T12:00:00+00:00" GIT_COMMITTER_DATE="2026-02-02T12:00:00+00:00"
git add drivers/thunderbolt/entry.c drivers/thunderbolt/sysfs-class-fixture
git commit -q -m "thunderbolt: add the macro-defined entry point" -m "Closes: https://lore.kernel.org/r/fixture-entry@example.invalid"
export GIT_AUTHOR_DATE="2026-02-03T12:00:00+00:00" GIT_COMMITTER_DATE="2026-02-03T12:00:00+00:00"
git add drivers/thunderbolt/slots.c drivers/thunderbolt/export.c
git commit -q -m "thunderbolt: add the slot map and the exported pair"
export GIT_AUTHOR_DATE="2026-02-04T12:00:00+00:00" GIT_COMMITTER_DATE="2026-02-04T12:00:00+00:00"
git add drivers/thunderbolt/forms.c
git commit -q -m "thunderbolt: add the parse forms"
export GIT_AUTHOR_DATE="2026-02-05T12:00:00+00:00" GIT_COMMITTER_DATE="2026-02-05T12:00:00+00:00"
git add drivers/thunderbolt/testbit.c
git commit -q -m "thunderbolt: add a bit operation outside the write forms"
export GIT_AUTHOR_DATE="2026-02-06T12:00:00+00:00" GIT_COMMITTER_DATE="2026-02-06T12:00:00+00:00"
git add include/linux/pci.h
git commit -q -m "pci: carry include/linux/pci.h:1-144 of v7.2 verbatim" -m "The resource enum whose body holds #define lines, kept at the real line numbers: the shape tree-sitter-c parses as an ERROR node, which the links.definition-line cases cite."
export GIT_AUTHOR_DATE="2026-02-07T12:00:00+00:00" GIT_COMMITTER_DATE="2026-02-07T12:00:00+00:00"
git add drivers/thunderbolt/record.h
git commit -q -m "thunderbolt: add a record whose trailing member carries an attribute macro"
export GIT_AUTHOR_DATE="2026-02-08T12:00:00+00:00" GIT_COMMITTER_DATE="2026-02-08T12:00:00+00:00"
git add mm/kg_slab.h mm/kg_opaque.h
git commit -q -m "mm: carry mm/slab.h:47-66 of v7.3 verbatim" -m "The kmalloc prototypes with their parameter and attribute macros, which tree-sitter-c parses as ERROR nodes that swallow the typedef after them; the links.definition-line typedef case cites it."
git tag v7.2
git log --format='%H %s' | cat
