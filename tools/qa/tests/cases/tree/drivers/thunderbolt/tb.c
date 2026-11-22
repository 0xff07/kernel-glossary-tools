// SPDX-License-Identifier: GPL-2.0
/*
 * The fixture router: enabling ports and their CL states.
 */

#include <linux/mutex.h>
#include <linux/module.h>
#include "tb.h"

static DEFINE_MUTEX(tb_lock);
static bool clx_enabled = true;
module_param_named(clx, clx_enabled, bool, 0444);

static const unsigned int tb_rates[] = {
	[TB_TMU_OFF] = 0,
	[TB_TMU_UNI] = 16,
	[TB_TMU_BI] = 1000,
};

static struct tb_port ports[4];

static DEVICE_ATTR_RO(authorized);

/**
 * tb_port_enable() - enable a port
 * @port: the port to enable
 *
 * Marks the port bonded and returns 0.
 */
int tb_port_enable(struct tb_port *port)
{
	if (!tb_port_has_remote(port))
		return -ENODEV;
	port->bonded = true;
	return 0;
}

static int tb_port_clx_write(struct tb_port *port, unsigned int clx)
{
	port->config.type = clx;
	return 0;
}

/**
 * tb_port_clx_enable() - enable CL states on a port
 * @port: the port
 * @clx: the mask of states to enable
 *
 * Validates the mask, writes it to the adapter and records it.
 */
int tb_port_clx_enable(struct tb_port *port, unsigned int clx)
{
	int ret;

	if (!clx_enabled)
		return -EOPNOTSUPP;
	if (clx & ~(TB_CL0S | TB_CL1 | TB_CL2))
		return -EINVAL;
	if (!port->remote)
		return -ENODEV;

	mutex_lock(&tb_lock);
	ret = tb_port_clx_write(port, clx);
	if (ret) {
		mutex_unlock(&tb_lock);
		return ret;
	}
	ret = tb_port_clx_write(port->remote, clx);
	if (ret) {
		tb_port_clx_write(port, 0);
		mutex_unlock(&tb_lock);
		return ret;
	}
	port->clx = clx;
	port->remote->clx = clx;
	mutex_unlock(&tb_lock);

	return 0;
}

int tb_port_clx_disable(struct tb_port *port)
{
	int ret;

	ret = tb_port_clx_write(port, 0);
	if (ret)
		return ret;
	port->clx = 0;
	return tb_port_enable(port);
}

static struct tb_port *
tb_port_lookup(unsigned int index)
{
	if (index >= ARRAY_SIZE(ports))
		return NULL;
	return &ports[index];
}

struct tb_port *tb_port_find(unsigned int index)
{
	return tb_port_lookup(index);
}
