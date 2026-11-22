# A redundant provenance still begins another unit

## DETAILS

### The excerpt identifies its source

The code below shows the source sites discussed here.

```c
/* drivers/thunderbolt/tb.c:30 */
int tb_port_enable(struct tb_port *port)
{
	if (!tb_port_has_remote(port))
/* drivers/thunderbolt/tb.c:33 */
		return -ENODEV;
	port->bonded = true;
	return 0;
}
```

<!-- kg:expect
only:
- provenance.form
- excerpts.verbatim
findings:
- - provenance.form
  - FAIL
  - 14
  - /* drivers/thunderbolt/tb.c:33 */
-->
