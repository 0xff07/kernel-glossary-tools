# Missing legends cannot hide drawn marks

## DETAILS

### The mask is recorded

The two assignments keep the records consistent.

```c
/* drivers/thunderbolt/tb.c:74 */
	port->clx = clx;
	port->remote->clx = clx;
```

The next figure shows the records.

```
    ┌────────────┐
    │ ① mask     │
    └────────────┘

```

Mark ① lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask.

The next figure shows the records.

```
    ┌────────────┐
    │ ➊ mask     │
    └────────────┘

    ➊ tb_port_clx_enable tb.c:bad records the near mask
```

Mark ➊ lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask.

The next figure shows the records.

```
    ┌────────────┐
    │ «1» mask   │
    │ «2» mask   │
    └────────────┘

    «1» tb_port_clx_enable tb.c:74 records the near mask
```

Mark «1» lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask.

<!-- kg:expect
only:
- drawing.legend
findings:
- - drawing.legend
  - FAIL
  - 17
  - ①
- - drawing.legend
  - FAIL
  - 28
  - ➊
- - drawing.legend
  - FAIL
  - 40
  - «2»
incomplete: []
-->
