---
qa: auto
---

# Catalog completeness

Every catalog symbol appears in at least one fenced source block.

COVERAGE entries use linked backticked keys in either `'\<KEY\>':'PATH'` or `'KEY'` form. Check each key against C source-fence bodies.

Match `struct X`, `enum X` and `union X` with their tag; match a member `A.B` by B as a whole word; match a CONFIG key by its complete name or the option named on a `config` or `menuconfig` line in a unit whose provenance names a Kconfig file; match other keys by their symbol name as a whole word. An unavailable or malformed entry prevents a clean result. This presence check does not decide whether the excerpt is a definition or concrete usage.
