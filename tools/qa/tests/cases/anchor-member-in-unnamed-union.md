# A member inside an unnamed union

## COVERAGE

### The slot state
- [`'tb_slot_state.bits'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/forms.c#L16): the bits of the state, inside the unnamed union
- [`'\<struct tb_slot_state\>':'drivers/thunderbolt/forms.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/forms.c#L13): the state record

## DETAILS

### The record

[`struct tb_slot_state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/forms.c#L13) keeps [`tb_slot_state.bits`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/forms.c#L16) in an unnamed union.

```c
/* drivers/thunderbolt/forms.c:13 */
struct tb_slot_state {
	unsigned int generation;
	union {
		unsigned long bits;
		unsigned int halves[2];
	};
};
```

<!-- kg:expect
only:
- links.definition-line
findings: []
incomplete: []
-->
