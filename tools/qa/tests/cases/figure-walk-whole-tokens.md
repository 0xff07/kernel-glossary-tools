# Walkthroughs match complete visible tokens

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
    │ @1 mask    │
    │ @2 mask    │
    │ @3 mask    │
    │ @4 mask    │
    │ @5 mask    │
    │ @6 mask    │
    │ @7 mask    │
    │ @8 mask    │
    │ @9 mask    │
    │ @10 mask   │
    └────────────┘

    @1 tb_port_clx_enable tb.c:74 records the near mask
    @2 tb_port_clx_enable tb.c:74 records the near mask
    @3 tb_port_clx_enable tb.c:74 records the near mask
    @4 tb_port_clx_enable tb.c:74 records the near mask
    @5 tb_port_clx_enable tb.c:74 records the near mask
    @6 tb_port_clx_enable tb.c:74 records the near mask
    @7 tb_port_clx_enable tb.c:74 records the near mask
    @8 tb_port_clx_enable tb.c:74 records the near mask
    @9 tb_port_clx_enable tb.c:74 records the near mask
    @10 tb_port_clx_enable tb.c:74 records the near mask
```

Mark @2 lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask. Mark @3 lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask. Mark @4 lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask. Mark @5 lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask. Mark @6 lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask. Mark @7 lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask. Mark @8 lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask. Mark @9 lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask. Mark @10 lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask.

The next figure shows the records.

```
    ┌────────────┐
    │ @A mask    │
    └────────────┘

    @A tb_port_clx_enable tb.c:74 records the near mask
```

Mark @AA lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask.

The next figure shows the records.

```
    ┌────────────┐
    │ @1 mask    │
    └────────────┘

    @1 tb_port_clx_enable tb.c:74 records the near mask
```

Mark reader@1.example lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask.

The next figure shows the records.

```
    ┌────────────┐
    │ @1 mask    │
    └────────────┘

    @1 tb_port_clx_enable tb.c:74 records the near mask
```

Mark path/@1 lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask.

The next figure shows the records.

```
    ┌────────────┐
    │ «1» mask   │
    └────────────┘

    «1» tb_port_clx_enable tb.c:74 records the near mask
```

Mark symbol«1» lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask.

The next figure shows the records.

```
    ┌────────────┐
    │ @A mask    │
    └────────────┘

    @A tb_port_clx_enable tb.c:74 records the near mask
```

Mark [the record](https://example.invalid/?mark=@A) lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask.

<!-- kg:expect
only:
- drawing.walk
findings:
- - drawing.walk
  - FAIL
  - 43
  - '@1 tb_port_clx_enable'
- - drawing.walk
  - FAIL
  - 55
  - '@A tb_port_clx_enable'
- - drawing.walk
  - FAIL
  - 67
  - '@1 tb_port_clx_enable'
- - drawing.walk
  - FAIL
  - 79
  - '@1 tb_port_clx_enable'
- - drawing.walk
  - FAIL
  - 91
  - «1» tb_port_clx_enable
- - drawing.walk
  - FAIL
  - 103
  - '@A tb_port_clx_enable'
incomplete: []
-->
