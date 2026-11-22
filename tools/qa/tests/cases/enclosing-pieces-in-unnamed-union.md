# A definition read in pieces across its unnamed union

## COVERAGE

### The slot state
- [`'\<struct tb_slot_state\>':'drivers/thunderbolt/forms.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/forms.c#L13): the state record, read in two pieces

## DETAILS

### The record

[`struct tb_slot_state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/forms.c#L13) is read in two pieces, outlined below. The cut falls between the two members of its unnamed union, so the second piece shows members of the union without the line that opens it, and the union counts as part of the record around it.

| piece | lines | member group |
|---|---|---|
| ❶ | [forms.c:13-16](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/forms.c#L13) | the generation and the first member of the union |
| ❷ | [forms.c:17-19](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/forms.c#L17) | the halves and the closing braces |

Piece ❶ of [`struct tb_slot_state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/forms.c#L13) opens the record with its generation and the first member of the union.

```c
/* drivers/thunderbolt/forms.c:13 */
struct tb_slot_state {
	unsigned int generation;
	union {
		unsigned long bits;
```

The word the union overlays is its first member.

Piece ❷ of [`struct tb_slot_state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/forms.c#L13) closes the union with the halves of the word and ends the record.

```c
/* drivers/thunderbolt/forms.c:17 */
		unsigned int halves[2];
	};
};
```

The halves give the same word as two unsigned ints.

<!-- kg:expect
only:
- excerpts.enclosing
- excerpts.walkthrough
- excerpts.outline
findings: []
incomplete: []
-->
