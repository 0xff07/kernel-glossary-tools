# Unsupported figure marks remain visible to QA

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
    │ ❶ mask     │
    └────────────┘

    ❶ tb_port_clx_enable tb.c:74 records the near mask
```

Mark ❶ lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask.

The next figure shows the records.

```
    ┌────────────┐
    │ Ⓐ mask     │
    └────────────┘

    Ⓐ tb_port_clx_enable tb.c:74 records the near mask
```

Mark Ⓐ lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask.

The next figure shows the records.

```
    ┌────────────┐
    │ ⓐ mask     │
    └────────────┘

    ⓐ tb_port_clx_enable tb.c:74 records the near mask
```

Mark ⓐ lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask.

The next figure shows the records.

```
    ┌────────────┐
    │ ⓵ mask     │
    └────────────┘

    ⓵ tb_port_clx_enable tb.c:74 records the near mask
```

Mark ⓵ lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask.

The next figure shows the records.

```
    ┌────────────┐
    │ ⑪ mask     │
    └────────────┘

    ⑪ tb_port_clx_enable tb.c:74 records the near mask
```

Mark ⑪ lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask.

The next figure shows the records.

```
    ┌────────────┐
    │ 🅰 mask     │
    └────────────┘

    🅰 tb_port_clx_enable tb.c:74 records the near mask
```

Mark 🅰 lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask.

The next figure shows the records.

```
    ┌────────────┐
    │ ⑴ mask     │
    └────────────┘

    ⑴ tb_port_clx_enable tb.c:74 records the near mask
```

Mark ⑴ lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask.

The next figure shows the records.

```
    ┌────────────┐
    │ ⒜ mask     │
    └────────────┘

    ⒜ tb_port_clx_enable tb.c:74 records the near mask
```

Mark ⒜ lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask.

The next figure shows the records.

```
    ┌────────────┐
    │ «01» mask  │
    └────────────┘

    «01» tb_port_clx_enable tb.c:74 records the near mask
```

Mark «01» lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask.

The next figure shows the records.

```
    ┌────────────┐
    │ «0» mask   │
    └────────────┘

    «0» tb_port_clx_enable tb.c:74 records the near mask
```

Mark «0» lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask.

The next figure shows the records.

```
    ┌────────────┐
    │ «a» mask   │
    └────────────┘

    «a» tb_port_clx_enable tb.c:74 records the near mask
```

Mark «a» lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask.

The next figure shows the records.

```
    ┌────────────┐
    │ «AA» mask  │
    └────────────┘

    «AA» tb_port_clx_enable tb.c:74 records the near mask
```

Mark «AA» lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask.

The next figure shows the records.

```
    ┌────────────┐
    │ @0 mask    │
    └────────────┘

    @0 tb_port_clx_enable tb.c:74 records the near mask
```

Mark @0 lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask.

The next figure shows the records.

```
    ┌────────────┐
    │ @01 mask   │
    └────────────┘

    @01 tb_port_clx_enable tb.c:74 records the near mask
```

Mark @01 lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask.

The next figure shows the records.

```
    ┌────────────┐
    │ @A1 mask   │
    └────────────┘

    @A1 tb_port_clx_enable tb.c:74 records the near mask
```

Mark @A1 lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask.

The next figure shows the records.

```
    ┌────────────┐
    │ @AA mask   │
    └────────────┘

    @AA tb_port_clx_enable tb.c:74 records the near mask
```

Mark @AA lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask.

The next figure shows the records.

```
    ┌────────────┐
    │ #1 mask    │
    └────────────┘

    #1 tb_port_clx_enable tb.c:74 records the near mask
```

Mark #1 lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask.

The next figure shows the records.

```
    ┌────────────┐
    │ ①② mask    │
    └────────────┘

    ①② tb_port_clx_enable tb.c:74 records the near mask
```

Mark ①② lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask.

<!-- kg:expect
only:
- drawing.marks
findings:
- - drawing.marks
  - FAIL
  - 17
  - ❶
- - drawing.marks
  - FAIL
  - 29
  - Ⓐ
- - drawing.marks
  - FAIL
  - 41
  - ⓐ
- - drawing.marks
  - FAIL
  - 53
  - ⓵
- - drawing.marks
  - FAIL
  - 65
  - ⑪
- - drawing.marks
  - FAIL
  - 77
  - 🅰
- - drawing.marks
  - FAIL
  - 89
  - ⑴
- - drawing.marks
  - FAIL
  - 101
  - ⒜
- - drawing.marks
  - FAIL
  - 113
  - «01»
- - drawing.marks
  - FAIL
  - 125
  - «0»
- - drawing.marks
  - FAIL
  - 137
  - «a»
- - drawing.marks
  - FAIL
  - 149
  - «AA»
- - drawing.marks
  - FAIL
  - 161
  - '@0'
- - drawing.marks
  - FAIL
  - 173
  - '@01'
- - drawing.marks
  - FAIL
  - 185
  - '@A1'
- - drawing.marks
  - FAIL
  - 197
  - '@AA'
- - drawing.marks
  - FAIL
  - 209
  - '#1'
- - drawing.marks
  - FAIL
  - 221
  - ①②
incomplete: []
-->
