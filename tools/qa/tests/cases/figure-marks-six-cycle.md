# Six figure families rotate independently

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

The next figure shows the records.

```
    ┌────────────┐
    │ ① mask     │
    │ ② mask     │
    │ ① mask     │
    └────────────┘

    ① tb_port_clx_enable tb.c:74 records the near mask
    ② tb_port_clx_enable tb.c:74 records the near mask
```

Mark ① lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask. Mark ② lets tb_port_clx_enable() record the mask.

The next figure shows the records.

```
    ┌────────────┐
    │ mask       │
    └────────────┘

```

The mask remains in its record.

| piece | lines | stage |
|---|---|---|
| 🅰 | [tb.c:74-75](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L74) | records the masks |
| 🅱 | [tb.c:74-75](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L74) | records the masks |

The next figure shows the records.

```
    ┌────────────┐
    │ ➊ mask     │
    │ ➋ mask     │
    └────────────┘

    ➊ tb_port_clx_enable tb.c:74 records the near mask
    ➋ tb_port_clx_enable tb.c:74 records the near mask
```

Mark ➊ lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask. Mark ➋ lets tb_port_clx_enable() record the mask.

| piece | lines | stage |
|---|---|---|
| ⑴ | [tb.c:74-75](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L74) | records the masks |
| ⑵ | [tb.c:74-75](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L74) | records the masks |

The next figure shows the records.

```
    ┌────────────┐
    │ «1» mask   │
    │ «2» mask   │
    └────────────┘

    «1» tb_port_clx_enable tb.c:74 records the near mask
    «2» tb_port_clx_enable tb.c:74 records the near mask
```

Mark «1» lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask. Mark «2» lets tb_port_clx_enable() record the mask.

| piece | lines | stage |
|---|---|---|
| ⒜ | [tb.c:74-75](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L74) | records the masks |
| ⒝ | [tb.c:74-75](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L74) | records the masks |

The next figure shows the records.

```
    ┌────────────┐
    │ «A» mask   │
    │ «B» mask   │
    └────────────┘

    «A» tb_port_clx_enable tb.c:74 records the near mask
    «B» tb_port_clx_enable tb.c:74 records the near mask
```

Mark «A» lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask. Mark «B» lets tb_port_clx_enable() record the mask.

The next figure shows the records.

```
    ┌────────────┐
    │ @1 mask    │
    │ @2 mask    │
    └────────────┘

    @1 tb_port_clx_enable tb.c:74 records the near mask
    @2 tb_port_clx_enable tb.c:74 records the near mask
```

Mark @1 lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask. Mark @2 lets tb_port_clx_enable() record the mask.

The next figure shows the records.

```
    ┌────────────┐
    │ @A mask    │
    │ @B mask    │
    └────────────┘

    @A tb_port_clx_enable tb.c:74 records the near mask
    @B tb_port_clx_enable tb.c:74 records the near mask
```

Mark @A lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask. Mark @B lets tb_port_clx_enable() record the mask.

The next figure shows the records.

```
    ┌────────────┐
    │ ① mask     │
    │ ② mask     │
    └────────────┘

    ① tb_port_clx_enable tb.c:74 records the near mask
    ② tb_port_clx_enable tb.c:74 records the near mask
```

Mark ① lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask. Mark ② lets tb_port_clx_enable() record the mask.

<!-- kg:expect
only:
- drawing.marks
- drawing.legend
- drawing.walk
- geometry.layout
- geometry.unicode
findings:
- - drawing.marks
  - review
  - 133
  - ①
incomplete: []
-->
