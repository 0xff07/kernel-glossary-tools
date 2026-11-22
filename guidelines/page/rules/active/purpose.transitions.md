---
qa: off
---

# Transitions

A transition carries forward the object, state, condition or relationship that makes the next explanation necessary, in the order the source establishes, with an explanatory sequence kept distinct from runtime order. Show how the previous result becomes an input, constraint or unresolved question for the next step; announcing the next function alone gives no connection. On returning from a variant or supporting helper, restore the main object's current state before continuing.

Recurring objects, states and computed values keep the names a figure or an earlier paragraph gave them; distinct concepts have distinct names. Where another function uses a different local name, retain that source name and identify the same object by its established name. Identify a newly introduced symbol by its role in that relationship so that changing functions does not make the reader rebuild the object model.

An illustration from the original guidance, in plain text so that nothing in it goes stale: it shows content, not page formatting, and on a page every symbol is linked. A transition that leaves the previous result behind. **Before:**

```
A host router has no DROM to describe itself, and some device DROMs omit
the pairing, so the driver needs a rule that produces the same answer the
hardware uses. The rule is adjacency, because lane adapters are numbered
in pairs and the lower number is the primary, so
tb_switch_default_link_ports() scans the adapter array for a lane adapter
immediately followed by another one.
```

**After:**

```
Pairing left unset by the DROM can be supplied by the default pass.
tb_switch_default_link_ports() examines adjacent lane adapters and
assigns their pairing when both dual_link_port pointers are unset.
```

Objects that lose their identity across functions. **Before:**

```
tb_configure_link() sets remote on the downstream and upstream primary
adapters unconditionally and on their siblings whenever both ends have a
dual_link_port, so on a two-lane link four adapters end up with a peer
pointer.
```

**After:**

```
tb_configure_link() connects the parent's primary adapter to the child's
primary adapter through their remote pointers. When both ends have a
dual_link_port, it also connects the parent's lane 1 adapter to the
child's lane 1 adapter. Each dual_link_port continues to identify a
sibling on the same router.
```
