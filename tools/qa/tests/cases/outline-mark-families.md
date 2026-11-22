# Prose examples are independent and open ended

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
| ❶ | [tb.c:74-75](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L74) | records the masks |
| ❷ | [tb.c:74-75](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L74) | records the masks |

| piece | lines | stage |
|---|---|---|
| Ⓐ | [tb.c:74-75](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L74) | records the masks |
| Ⓑ | [tb.c:74-75](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L74) | records the masks |

| piece | lines | stage |
|---|---|---|
| ⓐ | [tb.c:74-75](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L74) | records the masks |
| ⓑ | [tb.c:74-75](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L74) | records the masks |

| piece | lines | stage |
|---|---|---|
| ⓵ | [tb.c:74-75](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L74) | records the masks |
| ⓶ | [tb.c:74-75](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L74) | records the masks |

| piece | lines | stage |
|---|---|---|
| 🅰 | [tb.c:74-75](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L74) | records the masks |
| 🅱 | [tb.c:74-75](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L74) | records the masks |

| piece | lines | stage |
|---|---|---|
| ⑴ | [tb.c:74-75](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L74) | records the masks |
| ⑵ | [tb.c:74-75](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L74) | records the masks |

| piece | lines | stage |
|---|---|---|
| ⒜ | [tb.c:74-75](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L74) | records the masks |
| ⒝ | [tb.c:74-75](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L74) | records the masks |

| piece | lines | stage |
|---|---|---|
| Ⅰ | [tb.c:74-75](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L74) | records the masks |
| Ⅱ | [tb.c:74-75](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L74) | records the masks |

The next figure shows the records.

```
    ┌────────────┐
    │ ① mask     │
    └────────────┘

    ① tb_port_clx_enable tb.c:74 records the near mask
```

Mark ① lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask.

<!-- kg:expect
only:
- drawing.marks
findings: []
incomplete: []
-->
