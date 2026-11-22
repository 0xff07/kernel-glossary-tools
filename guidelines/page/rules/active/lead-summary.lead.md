---
qa: off
---

# Lead

The lead says what the mechanism is for, where it sits and what the page traces, and then stops. Every sentence is purpose, position or promise, with the promise last; none opens on a symbol, count, size or ordinal. Keep the local targets and shapes. Review a candidate range with a reason, and a figure outside its target for what it could drop. The lead may end on its figure. Identify each sentence's role when reviewing.

Target and review boundaries:

| Unit | Measure | Target | Review candidate | Violation |
|---|---|---|---|---|
| the lead | words | 60–120 | 121–220 | over 220 |
| the lead | sentences | 4–6 | 7–8 | over 8 |
| the lead | `P` items | 1–2 | 3 | over 3 |
| a figure in the lead | lines | 8–80 | under 8, over 80 | |

Allow at most one figure and no source excerpt, table, list or quotation. The first item is prose; the lead may end on its figure.


For these boundaries, P is a prose paragraph, C a source fence and D a figure fence. Count C as reproduced source lines, excluding provenance and elision lines. Count D as nonblank body lines, including legends. Measure the lead or SUMMARY as a whole, as the unit column specifies.

An illustration from the original guidance, in plain text so that nothing in it goes stale: it shows content, not page formatting, and on a page every symbol is linked. A lead. **Before:**

```
A root-hub port on a PCI-attached xHCI host carries three groups of
writable control bits that decide whether it is powered, what link state
it holds, and which events wake the machine through it.
```

**After:**

```
A USB port carries both the power a device draws and the link it talks
over, and the kernel controls each of them on its own, apart from the
data traffic through the port. Powering a port off saves the current a
device would draw and isolates a device that has stopped behaving. A
device the USB core suspends needs its link driven into a low-power
state, and driven back out of it when the device is needed again. ...
```
