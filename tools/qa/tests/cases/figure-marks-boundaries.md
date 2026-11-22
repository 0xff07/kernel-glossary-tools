# Line joins and punctuation bound whole tokens

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
    ──@1──
    └────────────┘

    @1 tb_port_clx_enable tb.c:74 records the near mask
```

[`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) records the mask at @1.

The next figure shows the records.

```
    ┌────────────┐
    ──@A──
    └────────────┘

    @A tb_port_clx_enable tb.c:74 records the near mask
```

[`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) records the mask at @A.

The next figure shows the records.

```
    ┌────────────┐
    ──«1»──
    └────────────┘

    «1» tb_port_clx_enable tb.c:74 records the near mask
```

[`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) records the mask at «1».

The next figure shows the records.

```
    ┌────────────┐
    ──«A»──
    └────────────┘

    «A» tb_port_clx_enable tb.c:74 records the near mask
```

[`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) records the mask at «A».

<!-- kg:expect
only:
- drawing.legend
- drawing.walk
findings: []
incomplete: []
-->
