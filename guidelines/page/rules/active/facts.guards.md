---
qa: manual
---

# Guards

A restated guard or threshold is derived from the reproduced code by exact negation of its operator with the exact constants, shown as a code block beside the sentence. Prose never outruns its excerpt, and the semantics a primitive's name carries (an ordering suffix, a `_locked` variant, an RCU flavor, saturation) are stated.

An invariant ("set once", "always under lock L", "freed only through F") gets a counterexample search over every assignment site, lock-less caller and free path, citing the kernel's own enforcement where it exists. Headings are claims, true of everything in their section, re-checked after every rewording.

An illustration from the original guidance, in plain text so that nothing in it goes stale: it shows content, not page formatting, and on a page every symbol is linked. A sentence that outruns its operation. **Before:**

```
A failed write returns before the log line, so a message in the log
means the register really changed.
```

**After:**

```
__tb_port_enable() returns immediately when tb_port_write() reports an
error. A zero result allows execution to reach tb_port_dbg().
```
