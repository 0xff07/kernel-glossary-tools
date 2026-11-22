# A list directly before a block

## DETAILS

The one subsection opens with prose, lists the two steps, and shows the excerpt directly after the list.

### The list runs into the excerpt

The enable has two steps, and the list below names them before the excerpt shows them.

- the validation of the mask
- the write to both adapters

```c
/* drivers/thunderbolt/tb.c:30 */
int tb_port_enable(struct tb_port *port)
{
	if (!tb_port_has_remote(port))
		return -ENODEV;
	port->bonded = true;
	return 0;
}
```

The excerpt closes the subsection with a sentence after it.

<!-- kg:expect
only:
- arrangement.open-close
findings:
- - arrangement.open-close
  - review
  - 14
  - The list runs into the excerpt
incomplete: []
-->
