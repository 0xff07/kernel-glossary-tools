# A piece inside an unnamed union whose introduction links no definition

## COVERAGE

### The slot state
- [`'\<struct tb_slot_state\>':'drivers/thunderbolt/forms.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/forms.c#L13): the state record

## DETAILS

### The record

The halves of the word come last, two unsigned ints that overlay it.

```c
/* drivers/thunderbolt/forms.c:17 */
		unsigned int halves[2];
	};
};
```

<!-- kg:expect
only:
- excerpts.enclosing
findings:
- - excerpts.enclosing
  - FAIL
  - 15
  - drivers/thunderbolt/forms.c:17
incomplete: []
-->
