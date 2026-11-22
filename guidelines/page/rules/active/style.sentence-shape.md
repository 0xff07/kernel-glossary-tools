---
qa: off
---

# Sentence shape

A sentence carries one mechanism: the operation, the condition it needs and the value or state it leaves. A consequence drawn from that mechanism for the reader's model, the sentence that would begin with "so" or "therefore", is the next sentence. Two parallel actions may share a sentence; three or more take one sentence each, or one table row each when they are members of one set.

The subject is short and the verb comes early: the actor or the object in a few words, the verb within the first seven or so words, the qualifications after the verb. A possessive chain, the field of the member of the device's bus, is unwound into a clause that names the owner first. A condition stands after the main clause or in its own sentence; a sentence opens on its condition only when the condition is the point.

Keep the concept beside its symbol in the paragraph. After a sentence that opens on a function, field or constant, consider whether the concept noun, actor or result (the survey, the device pass, the list, the window) gives the next sentence a clearer subject. Three consecutive sentences opening on an identifier are read for one that the concept can lead; repeating a symbol is appropriate when it prevents ambiguity.

Vary the subject to preserve the explanation's continuity, never to satisfy an alternating sentence pattern.

Read the sentences in their paragraph for a clear actor, the operation and its necessary conditions, and the result that the next sentence develops. These are manual reading targets, not automatic rejection thresholds:

| Unit | Measure | Target | Review candidate | Violation |
|---|---|---|---|---|
| a sentence | parallel actions | up to 2 | over 2 | |
| consecutive sentences opening on an identifier | sentences | up to 2 | over 2 | |

An illustration in plain text, from a page of this corpus, so that nothing in it goes stale; on a page every symbol is linked. One sentence carrying the test, its meaning and both outcomes. **Before:**

```
pcibios_allocate_dev_resources() tests PCI_COMMAND_IO for a slot whose
r->flags hold IORESOURCE_IO and PCI_COMMAND_MEMORY for the other slots,
and a set bit, decoding the firmware enabled, sends the BAR to pass 0
while a clear bit leaves it to pass 1.
```

**After:**

```
The device pass tests one Command bit per slot: PCI_COMMAND_IO for a slot
flagged IORESOURCE_IO, PCI_COMMAND_MEMORY for the others. A set bit means
the firmware enabled decoding, and pcibios_allocate_dev_resources() claims
that BAR in pass 0. A clear bit leaves the BAR to pass 1.
```
