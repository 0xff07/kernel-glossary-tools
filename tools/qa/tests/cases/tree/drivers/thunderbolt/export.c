// SPDX-License-Identifier: GPL-2.0
/*
 * Functions exported the way ACPICA exports them, the export line after the body with no semicolon.
 */

#include "tb.h"

#define ACPI_EXPORT_SYMBOL(name)

int tb_export_first(struct tb_port *port)
{
	return port->clx;
}

ACPI_EXPORT_SYMBOL(tb_export_first)

int tb_export_second(struct tb_port *port)
{
	return port->clx + 1;
}

ACPI_EXPORT_SYMBOL(tb_export_second)
