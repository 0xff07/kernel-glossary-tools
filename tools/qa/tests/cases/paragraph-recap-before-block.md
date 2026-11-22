# A recap and a closing sentence before a block

## DETAILS

The one subsection ends with a recap, one closing sentence and the excerpt the closing sentence introduces.

### The closing sentence stands before the excerpt

The slot takes its top from the publish. The excerpt stands below the two sentences.

So far, the slot has a top and nothing else.

The publish thus completes the slot.

```c
/* drivers/thunderbolt/writes.c:33 */
static void tb_slot_publish(struct tb_slot *slot, unsigned int top)
{
	WRITE_ONCE(slot->top, top);
}
```

<!-- kg:expect
only:
- arrangement.paragraphs
findings: []
incomplete: []
-->
