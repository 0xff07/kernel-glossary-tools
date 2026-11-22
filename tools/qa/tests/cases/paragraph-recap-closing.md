# Recap and closing

## DETAILS

The route names the two subsections in order. The first ends with a recap and a closing sentence, and the second repeats two single sentences.

### A recap may stand beside the closing sentence

The slot takes its top from the publish. The excerpt stands alone here.

```c
/* drivers/thunderbolt/writes.c:33 */
static void tb_slot_publish(struct tb_slot *slot, unsigned int top)
{
	WRITE_ONCE(slot->top, top);
}
```

So far, the slot has a top and nothing else.

The publish thus completes the slot.

### Two single sentences in a row stay a candidate

The slot takes its top from the publish. The excerpt is the same as above.

```c
/* drivers/thunderbolt/writes.c:33 */
static void tb_slot_publish(struct tb_slot *slot, unsigned int top)
{
	WRITE_ONCE(slot->top, top);
}
```

The top is stored once.

The store is a plain one.

The two sentences above are a run, and the closing sentence stands here with a second one. The run is the candidate.

<!-- kg:expect
only:
- arrangement.paragraphs
findings:
- - arrangement.paragraphs
  - review
  - 35
  - The top is stored once.
incomplete: []
-->
