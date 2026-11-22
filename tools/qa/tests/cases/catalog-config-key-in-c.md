# A Kconfig option carried only by a C unit

## COVERAGE

### The option
- [`'CONFIG_USB4_DEBUGFS_WRITE'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/Kconfig#L6): the debugfs write option

## DETAILS

### The option

The line below stands in a C unit, which carries no Kconfig option:

```c
/* drivers/thunderbolt/tb.c:200 */
config USB4_DEBUGFS_WRITE
```

<!-- kg:expect
only:
- excerpts.catalog-completeness
findings:
- - excerpts.catalog-completeness
  - FAIL
  - null
  - CONFIG_USB4_DEBUGFS_WRITE
incomplete: []
-->
