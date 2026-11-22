---
qa: auto
---

# Scope closure

Every anchor symbol and behavior the request names has a location on the page, or the page names it as a seam or as left out, with the reason, in the prose where it would have appeared; a scope name the page carries nowhere is a candidate, read against the request. The catalog rows start from the catalog and cannot supply this, and removing a catalog entry never discharges the obligation.

A page's **scope** is the list of backticked names the request gives for it; a campaign plan gives it as the page's scope fence. Its **scope names** are the names its backticked texts give, those inside a bracketed annotation included. A backticked text gives a name, a C identifier `[A-Za-z_]\w*`, in four forms only, its spaces aside:

1. the identifier alone (`tb_switch`);
2. `struct X`, `enum X` or `union X`, which gives `X`;
3. a call, the identifier followed by one parenthesized list that ends the text (`tb_port_enable(port)` gives `tb_port_enable`), unless the identifier is a C keyword (`sizeof(struct tb)` gives none); and
4. an array, the identifier followed by one bracketed size that ends the text (`tmu_rates[]` gives `tmu_rates`).

Any other text gives no name and is set aside:

- a family (`TB_CFG_*`, `CS_0/1/2`, `tb_port_read/write()`),
- an expression (`hotplug_active = false`, `A | B`),
- a field (`xd->lock`),
- a value or a path.

A scope names symbols defined at the pinned commit; a shorthand such as `_enable` names none.

A scope name is on the page when it occurs as a whole word anywhere in the page's text with the URLs of links removed, fences and catalog included. Scope texts that give no name are listed as skipped, not failed.
