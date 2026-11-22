# Outlines cannot take figure-only circled marks

## DETAILS

### The mask is recorded

The two assignments keep the records consistent.

```c
/* drivers/thunderbolt/tb.c:74 */
	port->clx = clx;
	port->remote->clx = clx;
```

| piece | lines | stage |
|---|---|---|
| ① | [tb.c:74-75](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L74) | records the masks |

| piece | lines | stage |
|---|---|---|
| ➊ | [tb.c:74-75](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L74) | records the masks |

| piece | lines | stage |
|---|---|---|
| ⑪ | [tb.c:74-75](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L74) | records the masks |

<!-- kg:expect
only:
- drawing.marks
findings:
- - drawing.marks
  - FAIL
  - 15
  - ①
- - drawing.marks
  - FAIL
  - 19
  - ➊
- - drawing.marks
  - FAIL
  - 23
  - ⑪
incomplete: []
-->
