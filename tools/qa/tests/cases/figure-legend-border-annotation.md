# A source annotation after a border is not a legend

## DETAILS

### The object has a cache

The object is defined at [tb.h:16](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.h#L16).

```
    ┌────────────┐
    │ clx cache  │
    └────────────┘            tb_port  tb.h:16
```

The source annotation identifies the object beside its border.

<!-- kg:expect
only:
- drawing.legend
- drawing.marks
- drawing.walk
findings: []
incomplete: []
-->
