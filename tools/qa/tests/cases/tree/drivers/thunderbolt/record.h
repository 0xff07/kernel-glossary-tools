/* SPDX-License-Identifier: GPL-2.0 */
#ifndef TB_RECORD_H_
#define TB_RECORD_H_

/* a record with a trailing area for its creator */
struct tb_record {
	int count;
	unsigned long private[] ____cacheline_aligned;
};

#endif
