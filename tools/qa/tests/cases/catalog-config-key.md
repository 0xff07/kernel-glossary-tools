# A Kconfig option in the catalog

## COVERAGE

### The option
- [`'CONFIG_USB4_DEBUGFS_WRITE'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/Kconfig#L6): the debugfs write option

## DETAILS

### The option

The option is declared in the fixture's Kconfig:

```c
/* drivers/thunderbolt/Kconfig:6 */
config USB4_DEBUGFS_WRITE
	bool "Enable write by debugfs"
	depends on USB4
```

<!-- kg:expect
only:
- excerpts.catalog-completeness
findings: []
incomplete: []
-->
