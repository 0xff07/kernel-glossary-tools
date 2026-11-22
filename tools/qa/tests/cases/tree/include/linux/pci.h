/* SPDX-License-Identifier: GPL-2.0 */
/*
 *	pci.h
 *
 *	PCI defines and function prototypes
 *	Copyright 1994, Drew Eckhardt
 *	Copyright 1997--1999 Martin Mares <mj@ucw.cz>
 *
 *	PCI Express ASPM defines and function prototypes
 *	Copyright (c) 2007 Intel Corp.
 *		Zhang Yanmin (yanmin.zhang@intel.com)
 *		Shaohua Li (shaohua.li@intel.com)
 *
 *	For more information, please consult the following manuals (look at
 *	http://www.pcisig.com/ for how to get them):
 *
 *	PCI BIOS Specification
 *	PCI Local Bus Specification
 *	PCI to PCI Bridge Specification
 *	PCI Express Specification
 *	PCI System Design Guide
 */
#ifndef LINUX_PCI_H
#define LINUX_PCI_H

#include <linux/args.h>
#include <linux/device-id/pci.h>

#include <linux/types.h>
#include <linux/sizes.h>
#include <linux/init.h>
#include <linux/ioport.h>
#include <linux/list.h>
#include <linux/compiler.h>
#include <linux/errno.h>
#include <linux/kobject.h>
#include <linux/atomic.h>
#include <linux/device.h>
#include <linux/interrupt.h>
#include <linux/io.h>
#include <linux/resource_ext.h>
#include <linux/msi_api.h>
#include <uapi/linux/pci.h>

#include <linux/pci_ids.h>

#define PCI_STATUS_ERROR_BITS (PCI_STATUS_DETECTED_PARITY  | \
			       PCI_STATUS_SIG_SYSTEM_ERROR | \
			       PCI_STATUS_REC_MASTER_ABORT | \
			       PCI_STATUS_REC_TARGET_ABORT | \
			       PCI_STATUS_SIG_TARGET_ABORT | \
			       PCI_STATUS_PARITY)

/* Number of reset methods used in pci_reset_fn_methods array in pci.c */
#define PCI_NUM_RESET_METHODS 8

#define PCI_RESET_PROBE		true
#define PCI_RESET_DO_RESET	false

/*
 * The PCI interface treats multi-function devices as independent
 * devices.  The slot/function address of each device is encoded
 * in a single byte as follows:
 *
 *	7:3 = slot
 *	2:0 = function
 *
 * PCI_DEVFN(), PCI_SLOT(), and PCI_FUNC() are defined in uapi/linux/pci.h.
 * In the interest of not exposing interfaces to user-space unnecessarily,
 * the following kernel-only defines are being added here.
 */
#define PCI_DEVID(bus, devfn)	((((u16)(bus)) << 8) | (devfn))
/* return bus from PCI devid = ((u16)bus_number) << 8) | devfn */
#define PCI_BUS_NUM(x) (((x) >> 8) & 0xff)

/*
 * PCI_SLOT_ALL_DEVICES indicates a slot that covers all devices on the bus.
 * Used for PCIe hotplug where the physical slot is the entire secondary bus,
 * and, if ARI Forwarding is enabled, functions may appear to be on multiple
 * devices.
 */
#define PCI_SLOT_ALL_DEVICES	0xfe

/* pci_slot represents a physical slot */
struct pci_slot {
	struct pci_bus		*bus;		/* Bus this slot is on */
	struct list_head	list;		/* Node in list of slots */
	struct hotplug_slot	*hotplug;	/* Hotplug info (move here) */
	unsigned char		number;		/* Device nr, or PCI_SLOT_ALL_DEVICES */
	struct kobject		kobj;
};

static inline const char *pci_slot_name(const struct pci_slot *slot)
{
	return kobject_name(&slot->kobj);
}

/* File state for mmap()s on /proc/bus/pci/X/Y */
enum pci_mmap_state {
	pci_mmap_io,
	pci_mmap_mem
};

/* For PCI devices, the region numbers are assigned this way: */
enum {
	/* #0-5: standard PCI resources */
	PCI_STD_RESOURCES,
	PCI_STD_RESOURCE_END = PCI_STD_RESOURCES + PCI_STD_NUM_BARS - 1,

	/* #6: expansion ROM resource */
	PCI_ROM_RESOURCE,

	/* Device-specific resources */
#ifdef CONFIG_PCI_IOV
	PCI_IOV_RESOURCES,
	PCI_IOV_RESOURCE_END = PCI_IOV_RESOURCES + PCI_SRIOV_NUM_BARS - 1,
#endif

/* PCI-to-PCI (P2P) bridge windows */
#define PCI_BRIDGE_IO_WINDOW		(PCI_BRIDGE_RESOURCES + 0)
#define PCI_BRIDGE_MEM_WINDOW		(PCI_BRIDGE_RESOURCES + 1)
#define PCI_BRIDGE_PREF_MEM_WINDOW	(PCI_BRIDGE_RESOURCES + 2)

/* CardBus bridge windows */
#define PCI_CB_BRIDGE_IO_0_WINDOW	(PCI_BRIDGE_RESOURCES + 0)
#define PCI_CB_BRIDGE_IO_1_WINDOW	(PCI_BRIDGE_RESOURCES + 1)
#define PCI_CB_BRIDGE_MEM_0_WINDOW	(PCI_BRIDGE_RESOURCES + 2)
#define PCI_CB_BRIDGE_MEM_1_WINDOW	(PCI_BRIDGE_RESOURCES + 3)

/* Total number of bridge resources for P2P and CardBus */
#define PCI_P2P_BRIDGE_RESOURCE_NUM	3
#define PCI_BRIDGE_RESOURCE_NUM		4

	/* Resources assigned to buses behind the bridge */
	PCI_BRIDGE_RESOURCES,
	PCI_BRIDGE_RESOURCE_END = PCI_BRIDGE_RESOURCES +
				  PCI_BRIDGE_RESOURCE_NUM - 1,

	/* Total resources associated with a PCI device */
	PCI_NUM_RESOURCES,

	/* Preserve this for compatibility */
	DEVICE_COUNT_RESOURCE = PCI_NUM_RESOURCES,
};
