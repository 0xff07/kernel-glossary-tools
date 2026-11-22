/* SPDX-License-Identifier: GPL-2.0 */
/*
 * The fixture router and its ports.
 */

#ifndef TB_H_
#define TB_H_

#include <linux/types.h>
#include "tb_regs.h"

#define TB_CL0S			BIT(0)
#define TB_CL1			BIT(1)
#define TB_CL2			BIT(2)

/**
 * enum tb_tmu_mode - the TMU modes of a router
 * @TB_TMU_OFF: the TMU is off
 * @TB_TMU_UNI: uni-directional time sync
 * @TB_TMU_BI: bi-directional time sync
 */
enum tb_tmu_mode {
	TB_TMU_OFF,
	TB_TMU_UNI,
	TB_TMU_BI,
};

/**
 * struct tb_port - a port of a router
 * @remote: the port at the other end of the link, or %NULL
 * @config: the cached config space of the port
 * @clx: the CL states enabled on the link
 * @bonded: whether the port is bonded with its sibling
 * @tmu_mode: the TMU mode the port reports
 */
struct tb_port {
	struct tb_port *remote;
	struct tb_regs_port_header config;
	unsigned int clx;
	bool bonded;
	enum tb_tmu_mode tmu_mode;
};

/**
 * tb_port_has_remote() - whether a port leads somewhere
 * @port: the port
 *
 * A port with no peer leads nowhere.
 */
static inline bool tb_port_has_remote(const struct tb_port *port)
{
	if (!port->remote)
		return false;
	return true;
}

int tb_port_enable(struct tb_port *port);
int tb_port_clx_enable(struct tb_port *port, unsigned int clx);
int tb_port_clx_disable(struct tb_port *port);
struct tb_port *tb_port_find(unsigned int index);

#endif
