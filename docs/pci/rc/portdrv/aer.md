# The AER service of Root Ports and RCECs

> CAUTION: AI-GENERATED CONTENT
>
> STRICTLY DO NOT SUBMIT THIS UPSTREAM UNLESS YOU ARE AN EXPERT INTIMATELY FAMILIAR WITH THIS SUBSYSTEM.

A PCIe function that detects an error logs it in its own Advanced Error Reporting registers and sends an error message toward the Root Complex. A Root Port, or a Root Complex Event Collector for the integrated endpoints associated with it, collects those messages and raises an interrupt. The kernel answers that interrupt with a service of the PCIe port driver, which finds the functions that logged the error, prints what they logged and starts recovery. The service runs where firmware leaves AER to the operating system or a boot option claims it. This page traces the service from its registration and binding, through its two interrupt halves and the search for the reporting functions, to recovery, the reset below the port and the paths that disable it again.

```text
    One Root Port, the bus below it, and the objects the AER service keeps for it
    ─────────────────────────────────────────────────────────────────────────────

    struct pci_dev: the Root Port                         struct pcie_device: the AER service device
    ┌─────────────────────────────────────────────┐       ┌────────────────────────────────────────────┐
    │ aer_cap ──▶ its AER capability              │◀──────┤ port        the Root Port                  │
    │   Root Error Command   enables the IRQ      │parent │ service     PCIE_PORT_SERVICE_AER          │
    │   Root Error Status    latches messages     │       │ irq         the vector both halves use     │
    │   Error Source ID      their Requester IDs  │       │ priv_data ───────────┐                     │
    │ subordinate ─────────┐                      │       └──────────────────────┼─────────────────────┘
    └──────────────────────┼──────────────────────┘                              ▼
      ▲                    ▼                              struct aer_rpc
      │ ERR_COR       ┌───────────────────────────────┐   ┌────────────────────────────────────────────┐
      │ ERR_NONFATAL  │ struct pci_bus: the bus below │   │ rpd         the Root Port                  │
      │ ERR_FATAL     │ functions with their own AER  │   │ aer_fifo    128 slots, each a              │
      │               │ status and mask registers;    │   │             struct aer_err_source          │
      └───────────────┤ one that detects an error     │   │             {status, id}                   │
                      │ logs it and sends an error    │   └────────────────────────────────────────────┘
                      │ message toward the root       │
                      └───────────────────────────────┘

    An RCEC takes the Root Port's place for the integrated endpoints associated with it,
    which reach it through its rcec_ea association; the service objects are the same.
```

## SUMMARY

The service keeps one object per collecting port and one transient record per error message, and the table settles which kernel object stands for each term of the specification. The rest of the page calls the collecting Root Port or RCEC the root, and a function that logged the error a reporting function.

| Specification term | Kernel representation | Set by |
|---|---|---|
| Root Port or RCEC that collects error messages | the [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) that [`rpd`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L55) of a [`struct aer_rpc`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L54) names, the root | [`aer_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1607) |
| the AER service of that port | a [`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59), portdrv's service instance, bound to [`aerdriver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1719) | [`pcie_device_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L290) and the driver core |
| `ERR_COR`, `ERR_NONFATAL` or `ERR_FATAL` received | bits of [`PCI_ERR_ROOT_STATUS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L826), copied with [`PCI_ERR_ROOT_ERR_SRC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L835) into a [`struct aer_err_source`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L49) | [`aer_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1470) |
| correctable, non-fatal or fatal error | [`severity`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L841) of a [`struct aer_err_info`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L833): [`AER_CORRECTABLE`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L16), [`AER_NONFATAL`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L14) or [`AER_FATAL`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L15) | [`aer_isr_one_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1405) |
| Requester ID of the error source | [`id`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L839), one half of the Error Source Identification register | [`ERR_COR_ID`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L122) or [`ERR_UNCOR_ID`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L123) |
| a function that logged the error | an entry of [`dev`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L834), up to [`AER_MAX_MULTI_ERR_DEVICES`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L812) per record | [`add_error_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L985) |

The primary journey starts at the root's interrupt. [`aer_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1470) copies the root's status into the queue of the [`struct aer_rpc`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L54), and [`aer_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1449) empties that queue in the interrupt thread, turning each queued message into at most one correctable and one uncorrectable [`struct aer_err_info`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L833). Each record is searched for its reporting functions, and [`aer_process_err_devices()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1352) prints every reporting function before it handles any, which its comment gives as the way to keep a reset from losing records. Uncorrectable errors go to the PCI core's recovery with [`aer_root_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1667) as the reset callback, which keeps the root's interrupt disabled while it resets.

## SPECIFICATIONS

The registers and messages are defined by the PCI Express Base Specification, which the tree cites by revision and section without titles in the comments listed here. The service itself, its per-root object and its records, is a kernel synthesis read from drivers/pci/pcie/aer.c and drivers/pci/pcie/portdrv.c.

- PCIe r6.0, section 7.8.4.9, cited without a title at [`aer.c:404-408`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L404) for [`PCI_ERR_ROOT_COMMAND`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L822), which Root Ports and RCECs implement.
- PCIe r7.0, section 6.2.7, cited without a title at [`aer.c:817`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L817) for the errors whose TLP header is always logged, which [`tlp_header_logged()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L815) tests.
- PCIe 5.0-1, section 7.9.10.3, cited without a title at [`rcec.c:91`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L91) for the bus range an RCEC is associated with, which [`walk_rcec()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L68) visits.
- PCI Express Base Specification 1.0a, sections 7.8.2, 7.8.9 and 7.9 to 7.11, cited without titles at [`portdrv.c:212-214`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L212) for the port capabilities [`get_port_device_capability()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L218) reads.

## COVERAGE

### The service driver and its registration

- [`'\<aerdriver\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1719): the port service driver for the AER service bit, with the probe, remove and sleep callbacks of this page.
- [`'\<pcie_aer_init\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1735): registers the service driver at boot when AER is available.
- [`'\<aer_probe\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1607): binds the service to a Root Port or RCEC, allocates the per-root object, requests the interrupt and enables it.
- [`'\<aer_remove\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1594): disables the root's interrupt when the service driver unbinds.
- [`'\<aer_suspend\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1645): disables the root's interrupt before system sleep.
- [`'\<aer_resume\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1653): clears stale status and enables the interrupt again on resume.

### Per-root state and the record queue

- [`'\<struct aer_rpc\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L54): the per-root object, the root's function and the queue of received messages.
- [`'\<struct aer_err_source\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L49): one queued message, the root's status word and its source identification word.
- [`'AER_ERROR_SOURCES_MAX'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L44): the number of records the queue holds.

### Enabling and disabling the root

- [`'\<aer_enable_rootport\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1533): clears the root's and the reporting functions' stale status, then enables the root's interrupt.
- [`'\<aer_disable_rootport\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1575): disables the root's interrupt and clears its status.
- [`'\<aer_enable_irq\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1491): sets the three enables of the Root Error Command register.
- [`'\<aer_disable_irq\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1502): clears the three enables of the Root Error Command register.
- [`'\<clear_status_iter\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1513): clears the AER and Device Status of one function below the root.

### The interrupt halves and the records

- [`'\<aer_irq\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1470): the hard interrupt half, which copies the root's registers into the queue.
- [`'\<aer_isr\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1449): the threaded half, which empties the queue.
- [`'\<aer_isr_one_error\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1405): turns one queued message into a correctable and an uncorrectable record.
- [`'ERR_COR_ID'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L122): the correctable source's Requester ID in the low half of the source identification word.
- [`'ERR_UNCOR_ID'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L123): the uncorrectable source's Requester ID in the high half.
- [`'\<struct aer_err_info\>':'drivers/pci/pci.h'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L833): one error record, its class, its source ID, its reporting functions and the registers read from the current one.
- [`'AER_MAX_MULTI_ERR_DEVICES'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L812): the number of reporting functions one record holds.

### Finding and reading the reporting functions

- [`'\<aer_isr_one_error_type\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1373): searches for one record's reporting functions, prints the source line and processes them.
- [`'\<find_source_device\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1099): tests the root and the functions below it.
- [`'\<find_device_iter\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1067): the per-function step of that search, which adds a match and decides whether to go on.
- [`'\<is_error_source\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1015): decides whether one function logged the error, by Requester ID or by its own status registers.
- [`'\<add_error_device\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L985): records a reporting function with a reference and decides whether its lines print.
- [`'\<aer_process_err_devices\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1352): prints every reporting function, then handles each.
- [`'\<aer_get_device_error_info\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1293): reads one reporting function's status, mask, first error and logged header into the record.

### Handling and reset

- [`'\<handle_error_source\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1196): hands one reporting function to its handling and drops its reference.
- [`'\<pci_aer_handle_error\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1170): clears and reports a correctable error, or starts recovery for an uncorrectable one.
- [`'aer_root_reset'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1667): the reset callback of that recovery, which resets below the root with its interrupt disabled.

### Root error registers of the AER capability (include/uapi/linux/pci_regs.h)

- [`'PCI_ERR_ROOT_COMMAND'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L822): offset of the Root Error Command register and its three interrupt enables.
- [`'PCI_ERR_ROOT_STATUS'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L826): offset of the Root Error Status register, whose bits record the messages received.
- [`'PCI_ERR_ROOT_ERR_SRC'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L835): offset of the Error Source Identification register, the Requester IDs of the sources.

## DOCUMENTATION

- [`Documentation/PCI/pcieaer-howto.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/PCI/pcieaer-howto.rst): the AER driver as a Root Port service driver, how an error message reaches the Root Port and how the Root Error Command register gates its interrupt.
- [`Documentation/PCI/pciebus-howto.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/PCI/pciebus-howto.rst): the PCIe port bus driver, its service devices and the service drivers that bind them.
- [`Documentation/PCI/pci-error-recovery.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/PCI/pci-error-recovery.rst): the driver callbacks the recovery sends after an uncorrectable error.
- [`Documentation/admin-guide/kernel-parameters.txt`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/admin-guide/kernel-parameters.txt): the pci=noaer option and the `pcie_ports=` option that decide whether the service runs.
- [`Documentation/ABI/testing/sysfs-bus-pci-devices-aer`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/ABI/testing/sysfs-bus-pci-devices-aer): the per-device statistics files that the counters of the service feed.

## OTHER SOURCES

- [PCI-SIG specifications](https://pcisig.com/specifications): the source for the PCI Express Base and PCI Firmware specifications referenced above.
- [PCI: PCIe Native AER and DPC ownership thread](https://lore.kernel.org/all/20220406184706.546547-1-helgaas@kernel.org/): an LKML discussion of how _OSC ownership of AER and DPC interacts with the native services.

### Added by Claude Opus 5.5

- [PCI/AER: Stop ruling out unbound devices as error source (commit 1ab4a3c80508)](https://patch.msgid.link/734338c2e8b669db5a5a3b45d34131b55ffebfca.1774605029.git.lukas@wunner.de)
- [PCI/AER: Clear stale errors on reporting agents upon probe (commit e242d09b58e8)](https://patch.msgid.link/3011c2ed30c11f858e35e29939add754adea7478.1769332702.git.lukas@wunner.de)
- [PCI/AER: Add message when AER_MAX_MULTI_ERR_DEVICES limit is hit (commit a6f494becf09)](https://patch.msgid.link/20250619185041.73240-1-akshayaj.lkd@gmail.com)
- [PCI/AER: Ratelimit correctable and non-fatal error logging (commit a57f2bfb4a58)](https://patch.msgid.link/20250522232339.1525671-19-helgaas@kernel.org)
- [PCI/AER: Convert aer_get_device_error_info(), aer_print_error() to index (commit 94bc15c3484a)](https://patch.msgid.link/20250522232339.1525671-17-helgaas@kernel.org)
- [PCI/AER: Initialize aer_err_info before using it (commit 57964ba39057)](https://patch.msgid.link/20250522232339.1525671-9-helgaas@kernel.org)
- [PCI/AER: Consolidate Error Source ID logging in aer_isr_one_error_type() (commit 6a1eda745967)](https://patch.msgid.link/20250522232339.1525671-5-helgaas@kernel.org)
- [PCI/AER: Factor COR/UNCOR error handling out from aer_isr_one_error() (commit 6fc4dae74afc)](https://patch.msgid.link/20250522232339.1525671-4-helgaas@kernel.org)
- [PCI/AER: Disable AER service on suspend (commit 5afc2f763edc)](https://lore.kernel.org/r/20240416043225.1462548-2-kai.heng.feng@canonical.com)
- [PCI/AER: Decode Requester ID when no error info found (commit 1291b716bbf9)](https://lore.kernel.org/r/20231206224231.732765-3-helgaas@kernel.org)
- [PCI/AER: Factor out interrupt toggling into helpers (commit 13cf36c648df)](https://lore.kernel.org/r/20230512000014.118942-1-kai.heng.feng@canonical.com)
- [PCI/AER: Add pcie_walk_rcec() to RCEC AER handling (commit af113553d961)](https://lore.kernel.org/r/20201121001036.8560-14-sean.v.kelley@intel.com)
- [PCI/ERR: Recover from RCiEP AER errors (commit 579086225502)](https://lore.kernel.org/r/20201121001036.8560-13-sean.v.kelley@intel.com)
- [PCI/AER: Use managed resource allocations (commit 369fd7b00fce)](https://lore.kernel.org/linux-pci/20180918235848.26694-12-keith.busch@intel.com)

## REGISTERS

The service reads and writes registers of two capabilities, the AER capability of the root and of each reporting function, at offsets from [`aer_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370), and a few error bits of the PCI Express capability. The map shows the AER capability with the offset macros of include/uapi/linux/pci_regs.h, and the figures after it draw the fields these paths test.

```text
    The AER capability, offsets from aer_cap
    ────────────────────────────────────────

    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x00  │         Next          │  Ver  │ ID 0x01 = PCI_EXT_CAP_ID_ERR  │
          │        (31:20)        │       │                               │
          ├───────────────────────┴───────┴───────────────────────────────┤
    0x04  │     Uncorrectable Error Status       PCI_ERR_UNCOR_STATUS     │
          ├───────────────────────────────────────────────────────────────┤
    0x08  │      Uncorrectable Error Mask         PCI_ERR_UNCOR_MASK      │
          ├───────────────────────────────────────────────────────────────┤
    0x0c  │     Uncorrectable Error Severity     PCI_ERR_UNCOR_SEVER      │
          ├───────────────────────────────────────────────────────────────┤
    0x10  │      Correctable Error Status         PCI_ERR_COR_STATUS      │
          ├───────────────────────────────────────────────────────────────┤
    0x14  │       Correctable Error Mask           PCI_ERR_COR_MASK       │
          ├───────────────────────────────────────────────────────────────┤
    0x18  │         Capabilities and Control         PCI_ERR_CAP          │
          ├───────────────────────────────────────────────────────────────┤
    0x1c  │      Header Log, 16 bytes             PCI_ERR_HEADER_LOG      │
          ├───────────────────────────────────────────────────────────────┤
    0x2c  │     Root Error Command               PCI_ERR_ROOT_COMMAND     │
          ├───────────────────────────────────────────────────────────────┤
    0x30  │     Root Error Status                PCI_ERR_ROOT_STATUS      │
          ├───────────────────────────────────────────────────────────────┤
    0x34  │     Error Source Identification      PCI_ERR_ROOT_ERR_SRC     │
          ├───────────────────────────────────────────────────────────────┤
    0x38  │      TLP Prefix Log, up to 16 bytes   PCI_ERR_PREFIX_LOG      │
          └───────────────────────────────────────────────────────────────┘

    ID = PCI_EXT_CAP_ID(header), Ver = PCI_EXT_CAP_VER(header), Next = PCI_EXT_CAP_NEXT(header)
    every offset is relative to pci_dev.aer_cap, which pci_aer_init() sets from the capability search
    0x2c, 0x30 and 0x34 are the root registers, which Root Ports and RCECs implement
    0x04 to 0x18 exist on every function with the capability: is_error_source and
      aer_get_device_error_info read them on the reporting functions, aer_enable_rootport clears 0x04 and 0x10
    the Header Log runs from 0x1c to 0x2b; offsets 0x20, 0x24 and 0x28 are not drawn as rows
```

The three root registers at 0x2c, 0x30 and 0x34 are the root's, and on this page's paths the interrupt halves, the enabling and disabling code and the reset callback read or write them. The status and mask pairs at 0x04 to 0x14 are read on the reporting functions as whole words: [`is_error_source()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1015) and [`aer_get_device_error_info()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1293) compare a status word with its mask, [`tlp_header_logged()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L815) tests a group of uncorrectable bits for a logged header, and the printers of the service decode the remaining bits.

```text
    Root Error Command, PCI_ERR_ROOT_COMMAND at aer_cap + 0x2c
    ──────────────────────────────────────────────────────────

    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x2c  │                        reserved                         │ │ │ │
          └─────────────────────────────────────────────────────────┴┬┴┬┴┬┘
                                                                     │ │ └──  COR_EN
                                                                     │ └────  NONFATAL_EN
                                                                     └──────  FATAL_EN

    Root Error Status, PCI_ERR_ROOT_STATUS at aer_cap + 0x30
    ────────────────────────────────────────────────────────

    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x30  │   IRQ   │               reserved                │ │ │ │ │ │ │ │
          └─────────┴───────────────────────────────────────┴┬┴┬┴┬┴┬┴┬┴┬┴┬┘
                                                             │ │ │ │ │ │ └──  COR_RCV
                                                             │ │ │ │ │ └────  MULTI_COR_RCV
                                                             │ │ │ │ └──────  UNCOR_RCV
                                                             │ │ │ └────────  MULTI_UNCOR_RCV
                                                             │ │ └──────────  FIRST_FATAL
                                                             │ └────────────  NONFATAL_RCV
                                                             └──────────────  FATAL_RCV

    COR_EN = PCI_ERR_ROOT_CMD_COR_EN (Correctable Err Reporting Enable)
    NONFATAL_EN = PCI_ERR_ROOT_CMD_NONFATAL_EN (Non-Fatal Err Reporting Enable)
    FATAL_EN = PCI_ERR_ROOT_CMD_FATAL_EN (Fatal Err Reporting Enable)
      the three together are ROOT_PORT_INTR_ON_MESG_MASK, which aer_enable_irq sets and aer_disable_irq clears
    COR_RCV = PCI_ERR_ROOT_COR_RCV (ERR_COR Received)
    MULTI_COR_RCV = PCI_ERR_ROOT_MULTI_COR_RCV (Multiple ERR_COR)
    UNCOR_RCV = PCI_ERR_ROOT_UNCOR_RCV (ERR_FATAL/NONFATAL)
    MULTI_UNCOR_RCV = PCI_ERR_ROOT_MULTI_UNCOR_RCV (Multiple FATAL/NONFATAL)
    FIRST_FATAL = PCI_ERR_ROOT_FIRST_FATAL (First UNC is Fatal)
    NONFATAL_RCV = PCI_ERR_ROOT_NONFATAL_RCV (Non-Fatal Received)
    FATAL_RCV = PCI_ERR_ROOT_FATAL_RCV (Fatal Received)
    IRQ = PCI_ERR_ROOT_AER_IRQ (Advanced Error Interrupt Message Number)
      bits 3:0 are AER_ERR_STATUS_MASK; aer_irq copies the whole word into aer_err_source.status
```

The Root Error Command enables decide whether a received message raises the root's interrupt at all, and the service sets or clears the three together. Bits 3:0 of Root Error Status, [`AER_ERR_STATUS_MASK`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L125), decide in [`aer_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1470) whether the interrupt was the root's AER interrupt, and [`aer_isr_one_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1405) reads `COR_RCV`, `MULTI_COR_RCV`, `UNCOR_RCV`, `MULTI_UNCOR_RCV` and `FATAL_RCV` to build its records. `FIRST_FATAL` and `NONFATAL_RCV` are copied and written back with the rest of the word, and in drivers/pci/ at v7.2 only the error injector of [`CONFIG_PCIEAER_INJECT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L37) names them. The interrupt message number in bits 31:27 is copied the same way, and the service tests none of its bits.

```text
    Error Source Identification, PCI_ERR_ROOT_ERR_SRC at aer_cap + 0x34
    ───────────────────────────────────────────────────────────────────

    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x34  │ ERR_FATAL/NONFATAL Source ID  │       ERR_COR Source ID       │
          │            (31:16)            │            (15:0)             │
          └───────────────────────────────┴───────────────────────────────┘

    One Requester ID, either half of the register above
    ───────────────────────────────────────────────────

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    ID    │  Bus Number   │ Device  │ Fn  │
          │    (15:8)     │  (7:3)  │(2:0)│
          └───────────────┴─────────┴─────┘

    ERR_FATAL/NONFATAL Source ID = ERR_UNCOR_ID(id) (id >> 16, into aer_err_info.id of the uncorrectable record)
    ERR_COR Source ID = ERR_COR_ID(id) (id & 0xffff, into aer_err_info.id of the correctable record)
      the whole register is cached in aer_err_source.id
    Bus Number = PCI_BUS_NUM(id) (bits 15:8; a zero bus makes is_error_source read status registers)
    Device = PCI_SLOT(id) (bits 7:3), Fn = PCI_FUNC(id) (bits 2:0), as aer_print_source decodes them
      pci_dev_id() builds the same 16 bits for a function as PCI_DEVID(bus number, devfn)
```

Error Source Identification holds two Requester IDs, a correctable source's in the low half and an uncorrectable source's in the high half. [`ERR_COR_ID`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L122) and [`ERR_UNCOR_ID`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L123) select the half that matches the class of the record, and [`is_error_source()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1015) compares the result with the Requester ID of each function. A bus number of zero in the ID is the case the code comments as a bad ID, and it sends the search to the status registers.

```text
    Device Control, PCI_EXP_DEVCTL at pcie_cap + 0x08
    ─────────────────────────────────────────────────

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x08  │         other         │ │ │ │ │
          └───────────────────────┴┬┴┬┴┬┴┬┘
                                   │ │ │ └──  CERE
                                   │ │ └────  NFERE
                                   │ └──────  FERE
                                   └────────  URRE

    Device Status, PCI_EXP_DEVSTA at pcie_cap + 0x0a
    ────────────────────────────────────────────────

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x0a  │         other         │ │ │ │ │
          └───────────────────────┴┬┴┬┴┬┴┬┘
                                   │ │ │ └──  CED
                                   │ │ └────  NFED
                                   │ └──────  FED
                                   └────────  URD

    Root Control, PCI_EXP_RTCTL at pcie_cap + 0x1c
    ──────────────────────────────────────────────

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x1c  │          other          │ │ │ │
          └─────────────────────────┴┬┴┬┴┬┘
                                     │ │ └──  SECEE
                                     │ └────  SENFEE
                                     └──────  SEFEE

    CERE = PCI_EXP_DEVCTL_CERE (Correctable Error Reporting En.)
    NFERE = PCI_EXP_DEVCTL_NFERE (Non-Fatal Error Reporting Enable)
    FERE = PCI_EXP_DEVCTL_FERE (Fatal Error Reporting Enable)
    URRE = PCI_EXP_DEVCTL_URRE (Unsupported Request Reporting En.)
      the four together are PCI_EXP_AER_FLAGS, tested by is_error_source and clear_status_iter
    CED, NFED, FED, URD = PCI_EXP_DEVSTA_CED, _NFED, _FED, _URD (Correctable, Non-Fatal, Fatal
      Error and Unsupported Request Detected), written back by aer_enable_rootport and pcie_clear_device_status
    SECEE, SENFEE, SEFEE = PCI_EXP_RTCTL_SECEE, _SENFEE, _SEFEE (System Error on Correctable,
      Non-Fatal and Fatal Error), together SYSTEM_ERROR_INTR_ON_MESG_MASK, cleared by aer_enable_rootport
    other = bits these paths neither test nor change; pcie_cap is the offset of the PCI Express capability
```

These bits of the PCI Express capability frame the AER registers. Device Control's four reporting enables, [`PCI_EXP_AER_FLAGS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L108), tell the search and the clearing walk whether a function's AER setup has run. Device Status records detected errors and is cleared by writing it back. Root Control's three system-error enables would turn received messages into system errors, and [`aer_enable_rootport()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1533) clears them so that the AER interrupt alone signals them.

```text
    Capabilities and Control, PCI_ERR_CAP at aer_cap + 0x18
    ───────────────────────────────────────────────────────

    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x18  │     other     │  SIZE   │ │  other  │ │ │   other   │   FEP   │
          └───────────────┴─────────┴┬┴─────────┴┬┴┬┴───────────┴─────────┘
                                     │           │ └────────────────────────  PREFIX_LOG_PRESENT
                                     │           └──────────────────────────  COMP_TIME_LOG
                                     └──────────────────────────────────────  TLP_LOG_FLIT

    FEP = PCI_ERR_CAP_FEP(x) (First Error Pointer, bits 4:0, into aer_err_info.first_error)
    COMP_TIME_LOG = PCI_ERR_CAP_COMP_TIME_LOG (Completion Timeout Prefix/Header Log Capable)
    TLP_LOG_FLIT = PCI_ERR_CAP_TLP_LOG_FLIT (TLP was logged in Flit Mode)
    SIZE = PCI_ERR_CAP_TLP_LOG_SIZE (Logged TLP Size, only in Flit mode), read by aer_tlp_log_len
    PREFIX_LOG_PRESENT = PCI_ERR_CAP_PREFIX_LOG_PRESENT (TLP Prefix Log Present), read by aer_tlp_log_len
    other = bits these paths do not test, the ECRC bits among them
```

[`aer_get_device_error_info()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1293) reads this register on an uncorrectable reporting function. The First Error Pointer lands in [`first_error`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L846). The logged-header capability helps decide whether a header was logged, and the Flit Mode bit, the logged size and the prefix-log bit decide how many dwords of the Header Log and Prefix Log are read into [`tlp`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L853).

## DETAILS

DETAILS first shows where the decision that the operating system owns AER comes from, how the port driver registers [`aerdriver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1719) and creates the AER service device of a root, and how [`aer_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1607) gives the root its [`struct aer_rpc`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L54) and enables its interrupt after clearing stale status. It then follows one error message through the hard interrupt half, the interrupt thread and the split into per-class [`struct aer_err_info`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L833) records. The search for the reporting functions, the test applied to each function, the printing pass and the register reads come next. The handling of each function by severity, the reset callback with its interrupt bracket, and the sleep and unbind paths that disable the root follow, and the page ends with the messages, the tracepoint, the hand-offs and the files that expose the service.

### Kconfig assumptions

The page documents the x86-64 default configuration resolved at v7.2 from `x86_64_defconfig`, with the PCIe, ACPI and dynamic-debug options of this campaign added and their dependencies resolved. The architecture is x86-64 with ACPI, whose host-bridge code passes the firmware's AER decision to the kernel.

| option | assumed value | what it decides here |
|---|---|---|
| [`CONFIG_PCIEPORTBUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L5) | y | builds the port driver, which creates service devices and registers [`aerdriver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1719) |
| [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28) | y | builds drivers/pci/pcie/aer.c; without it [`pcie_aer_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1735) is an empty inline |
| [`CONFIG_PCI_MSI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L44) | y | lets [`pci_msi_enabled()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/msi/api.c#L407) return the MSI switch; without it AER is never available |
| [`CONFIG_PM`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L217) | y | builds the port driver's sleep callbacks, which reach [`aer_suspend()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1645) and [`aer_resume()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1653) |
| [`CONFIG_PCIE_DPC`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L121) | y | builds the DPC driver, the second caller of [`aer_get_device_error_info()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1293) |
| [`CONFIG_ACPI_APEI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Kconfig#L8) | unset | leaves out the APEI support on which the firmware-first path depends |
| [`CONFIG_ACPI_APEI_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Kconfig#L37) | unset | compiles out [`aer_recover_queue()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1263) and its work function |
| [`CONFIG_CXL_RAS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/cxl/Kconfig#L237) | unset | makes two bus-specific hooks of [`aer_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1607) and [`handle_error_source()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1196) empty inlines |
| [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120) | y | makes the [`pci_dbg()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2896) lines of the recovery dynamic-debug sites |
| [`CONFIG_PCI_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L70) | unset | leaves DEBUG undefined for drivers/pci/, so those lines print only when enabled |
| [`CONFIG_PCIEAER_INJECT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L37) | unset | leaves out the software error injector |

The table indexes the prose, and each subsection below names an option again where its effect applies.

### Firmware ownership and boot options gate the service

Error messages reach a root whether or not the operating system drives the root's AER registers, and on an ACPI system the firmware decides who drives them. The kernel records that decision per host bridge in [`native_aer`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L653) of the [`struct pci_host_bridge`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L628) above the root, and two boot options can override it or switch AER off. This subsection reads where those values come from, and the port driver tests them together when it chooses a port's services.

A host bridge starts with every native feature granted. [`pci_init_host_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L659) sets [`native_aer`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L653) before any firmware is consulted, and its comment names `_OSC` as the way firmware keeps a feature for itself.

```c
/* drivers/pci/probe.c:659 */
static void pci_init_host_bridge(struct pci_host_bridge *bridge)
{
	INIT_LIST_HEAD(&bridge->windows);
	INIT_LIST_HEAD(&bridge->dma_ranges);
	INIT_LIST_HEAD(&bridge->ports);

	/*
	 * We assume we can manage these PCIe features.  Some systems may
	 * reserve these for use by the platform itself, e.g., an ACPI BIOS
	 * may implement its own AER handling and use _OSC to prevent the
	 * OS from interfering.
	 */
	bridge->native_aer = 1;
```

The bit stays at 1 unless a later step clears it. On x86 with ACPI, [`acpi_pci_root_create()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/pci_root.c#L995) creates the root bus and then clears each native bit whose `_OSC` control the firmware did not grant; read the stage that does so.

```c
/* drivers/acpi/pci_root.c:995 */
struct pci_bus *acpi_pci_root_create(struct acpi_pci_root *root,
				     struct acpi_pci_root_ops *ops,
				     struct acpi_pci_root_info *info,
				     void *sysdata)
{
	... /* 29 lines, to :1029 */
	host_bridge = to_pci_host_bridge(bus->bridge);
	if (!(root->osc_control_set & OSC_PCI_EXPRESS_NATIVE_HP_CONTROL))
		host_bridge->native_pcie_hotplug = 0;
	if (!(root->osc_control_set & OSC_PCI_SHPC_NATIVE_HP_CONTROL))
		host_bridge->native_shpc_hotplug = 0;
	if (!(root->osc_control_set & OSC_PCI_EXPRESS_AER_CONTROL))
		host_bridge->native_aer = 0;
```

When the control set the firmware granted lacks `OSC_PCI_EXPRESS_AER_CONTROL`, [`native_aer`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L653) is 0 for every port below that host bridge. The port driver then gives those ports no AER service unless the boot option below overrides the firmware. [`pcie_port_setup()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L622) parses `pcie_ports=` into three flags of portdrv.c, whose comments state what each means.

```c
/* drivers/pci/pcie/portdrv.c:606 */
/* If this switch is set, PCIe port native services should not be enabled. */
bool pcie_ports_disabled;

/*
 * If the user specified "pcie_ports=native", use the PCIe services regardless
 * of whether the platform has given us permission.  On ACPI systems, this
 * means we ignore _OSC.
 */
bool pcie_ports_native;

/*
 * If the user specified "pcie_ports=dpc-native", use the Linux DPC PCIe
 * service even if the platform hasn't given us permission.
 */
bool pcie_ports_dpc_native;

static int __init pcie_port_setup(char *str)
{
	if (!strncmp(str, "compat", 6))
		pcie_ports_disabled = true;
	else if (!strncmp(str, "native", 6))
		pcie_ports_native = true;
	else if (!strncmp(str, "dpc-native", 10))
		pcie_ports_dpc_native = true;

	return 1;
}
__setup("pcie_ports=", pcie_port_setup);
```

[`pcie_ports_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L614) makes the port driver use its services whatever the firmware granted. [`pcie_ports_disabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L607), set by `pcie_ports=compat`, keeps the port driver from registering any service, and [`pcie_ports_dpc_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L620) concerns DPC alone. The second option is AER's own. [`pci_setup()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L6743) parses the comma-separated pci= options early in boot, and its noaer branch calls [`pci_no_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L133).

```c
/* drivers/pci/pci.c:6743 */
static int __init pci_setup(char *str)
{
	while (str) {
		char *k = strchr(str, ',');
		if (k)
			*k++ = 0;
		if (*str && (str = pcibios_setup(str)) && *str) {
			if (!pci_setup_cardbus(str)) {
				/* Function handled the parameters */
			} else if (!strcmp(str, "nomsi")) {
				pci_no_msi();
			} else if (!strncmp(str, "noats", 5)) {
				pr_info("PCIe: ATS is disabled\n");
				pcie_ats_disabled = true;
			} else if (!strcmp(str, "noaer")) {
				pci_no_aer();
```

The nomsi branch above it switches MSI off for the whole system, and both branches bear on AER. [`pci_aer_available()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L138) combines the flag that [`pci_no_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L133) sets with the system-wide MSI switch, and the service is registered and offered to ports only while it returns true.

```c
/* drivers/pci/pcie/aer.c:130 */
static bool pcie_aer_disable;
static pci_ers_result_t aer_root_reset(struct pci_dev *dev);

void pci_no_aer(void)
{
	pcie_aer_disable = true;
}

bool pci_aer_available(void)
{
	return !pcie_aer_disable && pci_msi_enabled();
}
```

AER is available while pci=noaer was not given and [`pci_msi_enabled()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/msi/api.c#L407) returns true. The line between the flag and [`pci_no_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L133) is the forward declaration of [`aer_root_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1667), which the handling code passes as a callback above the function's definition. The MSI switch is read by [`pci_msi_enabled()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/msi/api.c#L407), whose comment lists what clears it.

```c
/* drivers/pci/msi/api.c:401 */
/**
 * pci_msi_enabled() - Are MSI(-X) interrupts enabled system-wide?
 *
 * Return: true if MSI has not been globally disabled through ACPI FADT,
 * PCI bridge quirks, or the "pci=nomsi" kernel command-line option.
 */
bool pci_msi_enabled(void)
{
	return pci_msi_enable;
}
```

With [`CONFIG_PCI_MSI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L44) set, as this page assumes, the switch decides. With the option unset, the header's stub replaces the function and returns false, so AER is never available.

```c
/* include/linux/pci.h:1792 */
static inline bool pci_msi_enabled(void) { return false; }
```

Three values thus gate the service. [`native_aer`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L653) carries the firmware's decision, [`pcie_ports_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L614) overrides it, and [`pci_aer_available()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L138) turns false with pci=noaer or with MSI switched off; the registration below reads the last, and the port driver reads all of them.

### pcie_aer_init registers aerdriver before any port is probed

A port gets its services from service drivers registered on the port driver's own bus, and the AER service driver is registered before the port driver probes ports. [`pcie_portdrv_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L839) runs as a device initcall, registers the services through [`pcie_init_services()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L830) and then registers the port driver itself; read the two functions for that order.

```c
/* drivers/pci/pcie/portdrv.c:830 */
static void __init pcie_init_services(void)
{
	pcie_aer_init();
	pcie_pme_init();
	pcie_dpc_init();
	pcie_bwctrl_init();
	pcie_hp_init();
}

static int __init pcie_portdrv_init(void)
{
	if (pcie_ports_disabled)
		return -EACCES;

	pcie_init_services();
	dmi_check_system(pcie_portdrv_dmi_table);

	return pci_register_driver(&pcie_portdriver);
}
device_initcall(pcie_portdrv_init);
```

`pcie_ports=compat` stops the sequence before any service is registered. Otherwise [`pcie_aer_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1735) is the first service registration, and the port driver that creates service devices registers last. When [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28) is unset, the call compiles to an empty inline of portdrv.h that reports success.

```c
/* drivers/pci/pcie/portdrv.h:30 */
#ifdef CONFIG_PCIEAER
int pcie_aer_init(void);
#else
static inline int pcie_aer_init(void) { return 0; }
#endif
```

This page assumes [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28) set, which depends on [`CONFIG_PCIEPORTBUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L5). A service is named by one bit of a mask, and portdrv.h defines the bits with their positions.

```c
/* drivers/pci/pcie/portdrv.h:14 */
/* Service Type */
#define PCIE_PORT_SERVICE_PME_SHIFT	0	/* Power Management Event */
#define PCIE_PORT_SERVICE_PME		(1 << PCIE_PORT_SERVICE_PME_SHIFT)
#define PCIE_PORT_SERVICE_AER_SHIFT	1	/* Advanced Error Reporting */
#define PCIE_PORT_SERVICE_AER		(1 << PCIE_PORT_SERVICE_AER_SHIFT)
#define PCIE_PORT_SERVICE_HP_SHIFT	2	/* Native Hotplug */
#define PCIE_PORT_SERVICE_HP		(1 << PCIE_PORT_SERVICE_HP_SHIFT)
#define PCIE_PORT_SERVICE_DPC_SHIFT	3	/* Downstream Port Containment */
#define PCIE_PORT_SERVICE_DPC		(1 << PCIE_PORT_SERVICE_DPC_SHIFT)
#define PCIE_PORT_SERVICE_BWCTRL_SHIFT	4	/* Bandwidth Controller (notifications) */
#define PCIE_PORT_SERVICE_BWCTRL	(1 << PCIE_PORT_SERVICE_BWCTRL_SHIFT)

#define PCIE_PORT_DEVICE_MAXSERVICES   5
```

[`PCIE_PORT_SERVICE_AER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L18) is bit 1, at [`PCIE_PORT_SERVICE_AER_SHIFT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L17), and [`PCIE_PORT_DEVICE_MAXSERVICES`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L26) counts the five services a port can have. A service driver states its bit and the port types it accepts in a [`struct pcie_port_service_driver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L78), the driver type of the port driver's bus, whose callbacks take the service device.

```c
/* drivers/pci/pcie/portdrv.h:78 */
struct pcie_port_service_driver {
	const char *name;
	int (*probe)(struct pcie_device *dev);
	void (*remove)(struct pcie_device *dev);
	int (*suspend)(struct pcie_device *dev);
	int (*resume_noirq)(struct pcie_device *dev);
	int (*resume)(struct pcie_device *dev);
	int (*runtime_suspend)(struct pcie_device *dev);
	int (*runtime_resume)(struct pcie_device *dev);

	int (*slot_reset)(struct pcie_device *dev);

	int port_type;  /* Type of the port this driver can handle */
	u32 service;    /* Port service this device represents */

	struct device_driver driver;
};
#define to_service_driver(d) \
	container_of(d, struct pcie_port_service_driver, driver)
```

Each callback receives a service device, and the embedded [`driver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L93) is what the driver core registers, with [`to_service_driver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L95) converting back. The port types are values of the port's Device/Port Type, and one more value accepts every type.

```c
/* drivers/pci/pcie/portdrv.h:56 */
/* Port Type */
#define PCIE_ANY_PORT			(~0)
```

The registered object of the AER service is [`aerdriver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1719), an instance of that type.

```c
/* drivers/pci/pcie/aer.c:1719 */
static struct pcie_port_service_driver aerdriver = {
	.name		= "aer",
	.port_type	= PCIE_ANY_PORT,
	.service	= PCIE_PORT_SERVICE_AER,

	.probe		= aer_probe,
	.suspend	= aer_suspend,
	.resume		= aer_resume,
	.remove		= aer_remove,
};
```

[`service`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L91) is [`PCIE_PORT_SERVICE_AER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L18), the bit the port driver gives an AER service device, and [`port_type`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L90) is [`PCIE_ANY_PORT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L57), so the driver itself places no condition on the port's type. [`probe`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L80), [`suspend`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L82), [`resume`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L84) and [`remove`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L81) are the four callbacks of this page, and [`name`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L79) becomes the driver's name on the bus. [`pcie_aer_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1735) registers the driver only while AER is available, which is where pci=noaer and the MSI switch take effect.

```c
/* drivers/pci/pcie/aer.c:1730 */
/**
 * pcie_aer_init - register AER service driver
 *
 * Invoked when AER service driver is loaded.
 */
int __init pcie_aer_init(void)
{
	if (!pci_aer_available())
		return -ENXIO;
	return pcie_port_service_register(&aerdriver);
}
```

When [`pci_aer_available()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L138) is false, the function returns -ENXIO and no AER service driver exists, so an AER service device would find no driver. Otherwise [`pcie_port_service_register()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L586) puts the driver on the port driver's bus.

```c
/* drivers/pci/pcie/portdrv.c:582 */
/**
 * pcie_port_service_register - register PCI Express port service driver
 * @new: PCI Express port service driver to register
 */
int pcie_port_service_register(struct pcie_port_service_driver *new)
{
	if (pcie_ports_disabled)
		return -ENODEV;

	new->driver.name = new->name;
	new->driver.bus = &pcie_port_bus_type;

	return driver_register(&new->driver);
}
```

The driver's embedded [`driver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L93) takes the service's name and the bus [`pcie_port_bus_type`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L575), so the driver core matches it against the service devices of that bus. `pcie_ports=compat` makes this function refuse as well, through [`pcie_ports_disabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L607). After boot, [`aerdriver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1719) waits on that bus for service devices with the AER bit, which the port driver creates next.

### The port driver creates an AER service device for a root

A port's services are separate devices, and the port driver creates one for each service the port qualifies for. Each is a [`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59), portdrv's service instance and no PCIe device of its own: it stands for one service of one port and points back at the port's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352). The AER service device exists for a port when [`get_port_device_capability()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L218) grants the AER bit; read the stage of that function that does so.

```c
/* drivers/pci/pcie/portdrv.c:218 */
static int get_port_device_capability(struct pci_dev *dev)
{
	struct pci_host_bridge *host = pci_find_host_bridge(dev->bus);
	int services = 0;

... /* 16 lines, to :239 */
#ifdef CONFIG_PCIEAER
	if ((pci_pcie_type(dev) == PCI_EXP_TYPE_ROOT_PORT ||
             pci_pcie_type(dev) == PCI_EXP_TYPE_RC_EC) &&
	    dev->aer_cap && pci_aer_available() &&
	    (pcie_ports_native || host->native_aer))
		services |= PCIE_PORT_SERVICE_AER;
#endif
```

The AER bit requires four things together. The port is a Root Port or an RCEC, it has an AER capability at [`aer_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370), [`pci_aer_available()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L138) is true, and either [`pcie_ports_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L614) or the host bridge's [`native_aer`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L653) is set. At v7.2 this test is the one place that grants [`PCIE_PORT_SERVICE_AER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L18), so a Switch Downstream Port or an Endpoint never gets the AER service, and the code of this page runs for roots alone.

[`pcie_port_device_register()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L331) turns the granted bits into service devices. It requests the port's interrupt vectors first, keeps only the hotplug service when that fails, and creates one device per remaining bit.

```c
/* drivers/pci/pcie/portdrv.c:331 */
static int pcie_port_device_register(struct pci_dev *dev)
{
	int status, capabilities, i, nr_service;
	int irqs[PCIE_PORT_DEVICE_MAXSERVICES];

	/* Enable PCI Express port device */
	status = pci_enable_device(dev);
	if (status)
		return status;

	/* Get and check PCI Express port services */
	capabilities = get_port_device_capability(dev);
	if (!capabilities)
		return 0;

	pci_set_master(dev);
	/*
	 * Initialize service irqs. Don't use service devices that
	 * require interrupts if there is no way to generate them.
	 * However, some drivers may have a polling mode (e.g. pciehp_poll_mode)
	 * that can be used in the absence of irqs.  Allow them to determine
	 * if that is to be used.
	 */
	status = pcie_init_service_irqs(dev, irqs, capabilities);
	if (status) {
		capabilities &= PCIE_PORT_SERVICE_HP;
		if (!capabilities)
			goto error_disable;
	}

	/* Allocate child services if any */
	status = -ENODEV;
	nr_service = 0;
	for (i = 0; i < PCIE_PORT_DEVICE_MAXSERVICES; i++) {
		int service = 1 << i;
		if (!(capabilities & service))
			continue;
		if (!pcie_device_init(dev, service, irqs[i]))
			nr_service++;
	}
	if (!nr_service)
		goto error_cleanup_irqs;
```

The AER service device therefore exists only if the vector setup in [`pcie_init_service_irqs()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L177) succeeded, and its interrupt is the entry for its bit in the local array irqs, the bit's position being [`PCIE_PORT_SERVICE_AER_SHIFT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L17). [`pcie_device_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L290) builds each device from the port, the bit and that vector.

```c
/* drivers/pci/pcie/portdrv.c:290 */
static int pcie_device_init(struct pci_dev *pdev, int service, int irq)
{
	int retval;
	struct pcie_device *pcie;
	struct device *device;

	pcie = kzalloc_obj(*pcie);
	if (!pcie)
		return -ENOMEM;
	pcie->port = pdev;
	pcie->irq = irq;
	pcie->service = service;

	/* Initialize generic device interface */
	device = &pcie->device;
	device->bus = &pcie_port_bus_type;
	device->release = release_pcie_device;	/* callback to free pcie dev */
	dev_set_name(device, "%s:pcie%03x",
		     pci_name(pdev),
		     get_descriptor_id(pci_pcie_type(pdev), service));
	device->parent = &pdev->dev;
	device_enable_async_suspend(device);

	retval = device_register(device);
	if (retval) {
		put_device(device);
		return retval;
	}

	pm_runtime_no_callbacks(device);

	return 0;
}
```

The service device is allocated zeroed and records the port in [`port`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L61), the vector in [`irq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L60) and the bit in [`service`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L62). Its embedded [`device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L64) joins [`pcie_port_bus_type`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L575) with the port's own device as its parent, so the port's device is the parent of every service device it has. The definition of the service instance shows those members with the accessors a service uses for its own data.

```c
/* drivers/pci/pcie/portdrv.h:59 */
struct pcie_device {
	int		irq;	    /* Service IRQ/MSI/MSI-X Vector */
	struct pci_dev *port;	    /* Root/Upstream/Downstream Port */
	u32		service;    /* Port service this device represents */
	void		*priv_data; /* Service Private Data */
	struct device	device;     /* Generic Device Interface */
};
#define to_pcie_device(d) container_of(d, struct pcie_device, device)

static inline void set_service_data(struct pcie_device *dev, void *data)
{
	dev->priv_data = data;
}

static inline void *get_service_data(struct pcie_device *dev)
{
	return dev->priv_data;
}
```

[`priv_data`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L63) is the member a service fills. [`set_service_data()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L68) stores a pointer there and [`get_service_data()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L73) returns it, and the AER service stores its [`struct aer_rpc`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L54) in it. [`to_pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L66) converts the embedded device back to the service instance, which the bus callbacks do first. The bus itself is [`pcie_port_bus_type`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L575), named `pci_express`, and its match and probe callbacks are the port driver's.

```c
/* drivers/pci/pcie/portdrv.c:575 */
const struct bus_type pcie_port_bus_type = {
	.name = "pci_express",
	.match = pcie_port_bus_match,
	.probe = pcie_port_bus_probe,
	.remove = pcie_port_bus_remove,
};
```

Registering a service device runs the bus's match against every driver on the bus. [`pcie_port_bus_match()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L511) compares the service bits and the port type.

```c
/* drivers/pci/pcie/portdrv.c:511 */
static int pcie_port_bus_match(struct device *dev, const struct device_driver *drv)
{
	struct pcie_device *pciedev = to_pcie_device(dev);
	const struct pcie_port_service_driver *driver = to_service_driver(drv);

	if (driver->service != pciedev->service)
		return 0;

	if (driver->port_type != PCIE_ANY_PORT &&
	    driver->port_type != pci_pcie_type(pciedev->port))
		return 0;

	return 1;
}
```

A driver matches when its service bit equals the device's and its port type is [`PCIE_ANY_PORT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L57) or the port's type, so [`aerdriver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1719) matches every AER service device. The figure shows the result for a Root Port that qualifies for PME, AER and DPC.

```text
    The Root Port's service devices on the pci_express bus, and the driver that binds the AER one
    ─────────────────────────────────────────────────────────────────────────────────────────────

                               struct pci_dev: the Root Port
                               ┌─────────────────────────────────────────┐
                               │ dev   its embedded struct device        │
                               └────────────────────┬────────────────────┘
                    device.parent                   │                    device.parent
                  ┌─────────────────────────────────┼─────────────────────────────────┐
                  ▼                                 ▼                                 ▼
    ┌───────────────────────────┐     ┌───────────────────────────┐     ┌───────────────────────────┐
    │ struct pcie_device        │     │ struct pcie_device        │     │ struct pcie_device        │
    │ service    PME bit        │     │ service    AER bit        │     │ service    DPC bit        │
    │ port       the Root Port  │     │ port       the Root Port  │     │ port       the Root Port  │
    └───────────────────────────┘     └─────────────┬─────────────┘     └───────────────────────────┘
                                                    │ bus match: equal service bits,
                                                    │ and a port_type of PCIE_ANY_PORT
    the PME and DPC devices                         ▼
    bind their own service            ┌───────────────────────────┐
    drivers by the same rule          │ aerdriver, name "aer"     │
                                      │ service    AER bit        │
                                      │ port_type  PCIE_ANY_PORT  │
                                      └───────────────────────────┘
                                      struct pcie_port_service_driver
```

On a match, the driver core calls [`pcie_port_bus_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L534), which hands the service instance to the driver's probe callback.

```c
/* drivers/pci/pcie/portdrv.c:526 */
/**
 * pcie_port_bus_probe - probe driver for given PCI Express port service
 * @dev: PCI Express port service device to probe against
 *
 * If PCI Express port service driver is registered with
 * pcie_port_service_register(), this function will be called by the driver core
 * whenever match is found between the driver and a port service device.
 */
static int pcie_port_bus_probe(struct device *dev)
{
	struct pcie_device *pciedev;
	struct pcie_port_service_driver *driver;
	int status;

	driver = to_service_driver(dev->driver);
	if (!driver || !driver->probe)
		return -ENODEV;

	pciedev = to_pcie_device(dev);
	status = driver->probe(pciedev);
	if (status)
		return status;

	get_device(dev);
	return 0;
}
```

The probe callback receives the [`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59), and for the AER service that callback is [`aer_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1607). A successful probe takes a reference on the service device, which the remove path drops. A root with the AER service thus has a service device bound to [`aerdriver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1719), and the probe gives it state next.

### aer_probe gives the root a record queue and an interrupt

The root's interrupt can arrive at any time once it is enabled, and the work it starts, searching the hierarchy and calling drivers, needs to sleep. The service splits that work between a hard interrupt half, which copies the root's registers, and an interrupt thread, which does the rest, with a queue of copies per root between them. The queue and the root form a [`struct aer_rpc`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L54), whose element is a [`struct aer_err_source`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L49), and a size macro bounds the queue.

```c
/* drivers/pci/pcie/aer.c:44 */
#define AER_ERROR_SOURCES_MAX		128

#define AER_MAX_TYPEOF_COR_ERRS		16	/* as per PCI_ERR_COR_STATUS */
#define AER_MAX_TYPEOF_UNCOR_ERRS	32	/* as per PCI_ERR_UNCOR_STATUS*/
```

[`AER_ERROR_SOURCES_MAX`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L44) is the number of messages a root's queue holds, 128. [`AER_MAX_TYPEOF_COR_ERRS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L46) and [`AER_MAX_TYPEOF_UNCOR_ERRS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L47) size the statistics counters and error-name tables of the service, which [`aer_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1607) checks at build time. The element and the per-root object follow, with comments naming the register each word comes from.

```c
/* drivers/pci/pcie/aer.c:49 */
struct aer_err_source {
	u32 status;			/* PCI_ERR_ROOT_STATUS */
	u32 id;				/* PCI_ERR_ROOT_ERR_SRC */
};

struct aer_rpc {
	struct pci_dev *rpd;		/* Root Port device */
	DECLARE_KFIFO(aer_fifo, struct aer_err_source, AER_ERROR_SOURCES_MAX);
};
```

[`status`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L50) holds a copy of the root's [`PCI_ERR_ROOT_STATUS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L826) and [`id`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L51) a copy of its [`PCI_ERR_ROOT_ERR_SRC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L835), so one element is one interrupt's view of the root. [`rpd`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L55) is the root's function, a Root Port or an RCEC although its comment says Root Port. [`aer_fifo`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L56) is a kfifo of [`AER_ERROR_SOURCES_MAX`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L44) elements declared inside the object by [`DECLARE_KFIFO()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/kfifo.h#L123), so the queue needs no allocation of its own.

[`aer_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1607) is the probe callback of [`aerdriver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1719). It creates the per-root object, installs both interrupt halves on the service device's vector and enables the root; read it for the order of those steps.

```c
/* drivers/pci/pcie/aer.c:1607 */
static int aer_probe(struct pcie_device *dev)
{
	int status;
	struct aer_rpc *rpc;
	struct device *device = &dev->device;
	struct pci_dev *port = dev->port;

	BUILD_BUG_ON(ARRAY_SIZE(aer_correctable_error_string) <
		     AER_MAX_TYPEOF_COR_ERRS);
	BUILD_BUG_ON(ARRAY_SIZE(aer_uncorrectable_error_string) <
		     AER_MAX_TYPEOF_UNCOR_ERRS);

	/* Limit to Root Ports or Root Complex Event Collectors */
	if ((pci_pcie_type(port) != PCI_EXP_TYPE_RC_EC) &&
	    (pci_pcie_type(port) != PCI_EXP_TYPE_ROOT_PORT))
		return -ENODEV;

	rpc = devm_kzalloc(device, sizeof(struct aer_rpc), GFP_KERNEL);
	if (!rpc)
		return -ENOMEM;

	rpc->rpd = port;
	INIT_KFIFO(rpc->aer_fifo);
	set_service_data(dev, rpc);

	status = devm_request_threaded_irq(device, dev->irq, aer_irq, aer_isr,
					   IRQF_SHARED, "aerdrv", dev);
	if (status) {
		pci_err(port, "request AER IRQ %d failed\n", dev->irq);
		return status;
	}

	cxl_rch_enable_rcec(port);
	aer_enable_rootport(rpc);
	pci_info(port, "enabled with IRQ %d\n", dev->irq);
	return 0;
}
```

The type test repeats the condition of [`get_port_device_capability()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L218), so it fails only for a service device created for no root. The object comes from [`devm_kzalloc()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/device/devres.h#L48) on the service device, so it starts zeroed and is freed when the driver unbinds, and the probe has no matching free. [`set_service_data()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L68) stores it in the service device for both halves to find. [`devm_request_threaded_irq()`](https://elixir.bootlin.com/linux/v7.2/source/kernel/irq/devres.c#L100) installs [`aer_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1470) as the hard half and [`aer_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1449) as the threaded half on [`irq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L60), shared and named aerdrv, with the service device as the argument both halves receive. A failure there prints the request error, and the service stays unbound.

The call before the enabling belongs to a bus topic this page leaves out. With [`CONFIG_CXL_RAS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/cxl/Kconfig#L237) unset, as this page assumes, it and the handling hook of the same topic are the empty inlines of portdrv.h.

```c
/* drivers/pci/pcie/portdrv.h:127 */
struct aer_err_info;

#ifdef CONFIG_CXL_RAS
bool is_aer_internal_error(struct aer_err_info *info);
void cxl_rch_handle_error(struct pci_dev *dev, struct aer_err_info *info);
void cxl_rch_enable_rcec(struct pci_dev *rcec);
#else
static inline bool is_aer_internal_error(struct aer_err_info *info) { return false; }
static inline void cxl_rch_handle_error(struct pci_dev *dev, struct aer_err_info *info) { }
static inline void cxl_rch_enable_rcec(struct pci_dev *rcec) { }
#endif /* CONFIG_CXL_RAS */
```

The root is enabled last, by [`aer_enable_rootport()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1533) once the handler is installed, and the info line reports the vector. The strip follows the object and one record from the service device's allocation through one interrupt to unbind, and the subsections after this one show the marks after ⑤ in order.

```text
    One struct aer_rpc from probe to unbind, and one record through its queue
    ─────────────────────────────────────────────────────────────────────────

    fields: the object, rpd, aer_fifo, the service device's priv_data, and each half's own record

    time ────────────────────────────────────────────────────────────────────────────────────────────────────────▶
    event             created     probe               hard IRQ            push            thread            unbind
                      ▼           ▼                   ▼                   ▼               ▼                 ▼
                                  ┌─────────────────────────────────────────────────────────────────────────┐
    the object                    │② zeroed, owned by the service device through devres                     │ freed
                                  └─────────────────────────────────────────────────────────────────────────┘
                                  ┌─────────────────────────────────────────────────────────────────────────┐
    rpd                           │③ the root                                                               │
                                  └─────────────────────────────────────────────────────────────────────────┘
                                  ┌───────────────────────────────────────┬───────────────┬─────────────────┐
    aer_fifo                      │④ empty                                │⑨ one record   │⑩ empty          │
                                  └───────────────────────────────────────┴───────────────┴─────────────────┘
                      ┌───────────┬─────────────────────────────────────────────────────────────────────────┐
    priv_data         │① NULL     │⑤ the object                                                             │
                      └───────────┴─────────────────────────────────────────────────────────────────────────┘
                                                      ┌───────────────────┐
    aer_irq's record                                  │⑥ 0  ⑦ status  ⑧ id│
                                                      └───────────────────┘
                                                                                          ┌─────────────────┐
    aer_isr's record                                                                      │⑩ status, id     │
                                                                                          └─────────────────┘

    ① pcie_device_init  portdrv.c:296  allocates the service device zeroed with kzalloc_obj
    ② aer_probe         aer.c:1624     allocates the object zeroed with devm_kzalloc
    ③ aer_probe         :1628          stores the root in rpd
    ④ aer_probe         :1629          initializes the queue empty with INIT_KFIFO
    ⑤ aer_probe         :1630          stores the object in priv_data through set_service_data
    ⑥ aer_irq           :1476          starts its record at zero
    ⑦ aer_irq           :1478          reads Root Error Status into the record with pci_read_config_dword
    ⑧ aer_irq           :1482          reads the Error Source ID into the record with pci_read_config_dword
    ⑨ aer_irq           :1485          copies the record into aer_fifo with kfifo_put
    ⑩ aer_isr           :1458          moves the oldest record out of aer_fifo with kfifo_get
```

① [`pcie_device_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L290) allocates the service device zeroed with `kzalloc_obj()`, so its [`priv_data`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L63) starts NULL. ② [`aer_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1607) allocates the object zeroed with [`devm_kzalloc()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/device/devres.h#L48). ③ aer_probe() stores the root in [`rpd`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L55). ④ aer_probe() initializes [`aer_fifo`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L56) empty with [`INIT_KFIFO()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/kfifo.h#L129). ⑤ aer_probe() stores the object in priv_data through [`set_service_data()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L68). ⑥ [`aer_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1470) starts its own record at zero. ⑦ aer_irq() reads Root Error Status into that record with [`pci_read_config_dword()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/access.c#L580). ⑧ aer_irq() reads the Error Source ID into the record the same way. ⑨ aer_irq() copies the record into the queue with [`kfifo_put()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/kfifo.h#L440). ⑩ [`aer_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1449) moves the oldest record out of the queue into its own record with [`kfifo_get()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/kfifo.h#L477).

The object is freed by the driver core's release of managed resources in drivers/base/devres.c, which the unbind path reaches after [`aer_remove()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1594); the page shows the call into that release, and the release itself belongs to the driver core. Other services of the same port write the [`priv_data`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L63) of their own service devices, which are other instances of the type. After the probe, the root's service device points at a zeroed object with an empty queue, both halves are installed, and the root's enabling is the last step before an error can be handled.

### aer_enable_rootport clears stale status, then enables the interrupt

A root may hold message bits latched before the service probed, and the functions below it may hold errors logged before then; enabling the interrupt on that state would report old errors as new ones. [`aer_enable_rootport()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1533) clears the root's status registers, clears the functions below it when the root had latched a message, and enables the interrupt last. Its masks are macros of aer.c.

```c
/* drivers/pci/pcie/aer.c:116 */
#define SYSTEM_ERROR_INTR_ON_MESG_MASK	(PCI_EXP_RTCTL_SECEE|	\
					PCI_EXP_RTCTL_SENFEE|	\
					PCI_EXP_RTCTL_SEFEE)
#define ROOT_PORT_INTR_ON_MESG_MASK	(PCI_ERR_ROOT_CMD_COR_EN|	\
					PCI_ERR_ROOT_CMD_NONFATAL_EN|	\
					PCI_ERR_ROOT_CMD_FATAL_EN)
#define ERR_COR_ID(d)			(d & 0xffff)
#define ERR_UNCOR_ID(d)			(d >> 16)

#define AER_ERR_STATUS_MASK		(PCI_ERR_ROOT_UNCOR_RCV |	\
					PCI_ERR_ROOT_COR_RCV |		\
					PCI_ERR_ROOT_MULTI_COR_RCV |	\
					PCI_ERR_ROOT_MULTI_UNCOR_RCV)
```

[`SYSTEM_ERROR_INTR_ON_MESG_MASK`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L116) holds the three Root Control bits that turn received messages into system errors, and [`ROOT_PORT_INTR_ON_MESG_MASK`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L119) the three Root Error Command enables. [`ERR_COR_ID`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L122) and [`ERR_UNCOR_ID`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L123) split a source identification word into its two Requester IDs, which the record subsection uses, and [`AER_ERR_STATUS_MASK`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L125) holds the four message bits of Root Error Status. The register offsets come from the uapi header, with the bits each register holds.

```c
/* include/uapi/linux/pci_regs.h:822 */
#define PCI_ERR_ROOT_COMMAND	0x2c	/* Root Error Command */
#define  PCI_ERR_ROOT_CMD_COR_EN	0x00000001 /* Correctable Err Reporting Enable */
#define  PCI_ERR_ROOT_CMD_NONFATAL_EN	0x00000002 /* Non-Fatal Err Reporting Enable */
#define  PCI_ERR_ROOT_CMD_FATAL_EN	0x00000004 /* Fatal Err Reporting Enable */
#define PCI_ERR_ROOT_STATUS	0x30
#define  PCI_ERR_ROOT_COR_RCV		0x00000001 /* ERR_COR Received */
#define  PCI_ERR_ROOT_MULTI_COR_RCV	0x00000002 /* Multiple ERR_COR */
#define  PCI_ERR_ROOT_UNCOR_RCV		0x00000004 /* ERR_FATAL/NONFATAL */
#define  PCI_ERR_ROOT_MULTI_UNCOR_RCV	0x00000008 /* Multiple FATAL/NONFATAL */
#define  PCI_ERR_ROOT_FIRST_FATAL	0x00000010 /* First UNC is Fatal */
#define  PCI_ERR_ROOT_NONFATAL_RCV	0x00000020 /* Non-Fatal Received */
#define  PCI_ERR_ROOT_FATAL_RCV		0x00000040 /* Fatal Received */
#define  PCI_ERR_ROOT_AER_IRQ		0xf8000000 /* Advanced Error Interrupt Message Number */
#define PCI_ERR_ROOT_ERR_SRC	0x34	/* Error Source Identification */
```

Each offset is relative to the start of the AER capability, so the code adds [`aer_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370) of the root to it, and the register figures near the top of the page draw the bits. [`aer_enable_rootport()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1533) runs at probe and at resume, on the root that [`rpd`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L55) names; read it for the order of the clears.

```c
/* drivers/pci/pcie/aer.c:1533 */
static void aer_enable_rootport(struct aer_rpc *rpc)
{
	struct pci_dev *pdev = rpc->rpd;
	int aer = pdev->aer_cap;
	u16 reg16;
	u32 reg32;

	/* Clear PCIe Capability's Device Status */
	pcie_capability_read_word(pdev, PCI_EXP_DEVSTA, &reg16);
	pcie_capability_write_word(pdev, PCI_EXP_DEVSTA, reg16);

	/* Disable system error generation in response to error messages */
	pcie_capability_clear_word(pdev, PCI_EXP_RTCTL,
				   SYSTEM_ERROR_INTR_ON_MESG_MASK);

	/* Clear error status of this Root Port or RCEC */
	pci_read_config_dword(pdev, aer + PCI_ERR_ROOT_STATUS, &reg32);
	pci_write_config_dword(pdev, aer + PCI_ERR_ROOT_STATUS, reg32);

	/* Clear error status of agents reporting to this Root Port or RCEC */
	if (reg32 & AER_ERR_STATUS_MASK) {
		if (pci_pcie_type(pdev) == PCI_EXP_TYPE_RC_EC)
			pcie_walk_rcec(pdev, clear_status_iter, NULL);
		else if (pdev->subordinate)
			pci_walk_bus(pdev->subordinate, clear_status_iter,
				     NULL);
	}

	pci_read_config_dword(pdev, aer + PCI_ERR_COR_STATUS, &reg32);
	pci_write_config_dword(pdev, aer + PCI_ERR_COR_STATUS, reg32);
	pci_read_config_dword(pdev, aer + PCI_ERR_UNCOR_STATUS, &reg32);
	pci_write_config_dword(pdev, aer + PCI_ERR_UNCOR_STATUS, reg32);

	aer_enable_irq(pdev);
}
```

The function writes Device Status back to itself, which clears the bits that were set, and it clears the system-error enables in Root Control, as its comment says, so that messages raise the AER interrupt and no system error. It reads Root Error Status and writes the value back, which clears the latched message bits. If one of the [`AER_ERR_STATUS_MASK`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L125) bits was set, it visits the functions that report to the root, with [`pcie_walk_rcec()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L134) for an RCEC and [`pci_walk_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/bus.c#L461) for a Root Port that has a bus below it. The root's own correctable and uncorrectable status are cleared the same way before [`aer_enable_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1491) sets the enables.

The visit of the functions below was added by commit [e242d09b58e8](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=e242d09b58e869f86071b7889acace4cff215935) ("PCI/AER: Clear stale errors on reporting agents upon probe"). Its message gives the reason, that an error logged between enumeration and the probe was otherwise reported only together with the next error. [`clear_status_iter()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1513) is the per-function step of that visit, and it skips a function whose AER setup has not run.

```c
/* drivers/pci/pcie/aer.c:1513 */
static int clear_status_iter(struct pci_dev *dev, void *data)
{
	u16 devctl;

	/* Skip if pci_enable_pcie_error_reporting() hasn't been called yet */
	pcie_capability_read_word(dev, PCI_EXP_DEVCTL, &devctl);
	if (!(devctl & PCI_EXP_AER_FLAGS))
		return 0;

	pci_aer_clear_status(dev);
	pcie_clear_device_status(dev);
	return 0;
}
```

A function whose Device Control has none of the [`PCI_EXP_AER_FLAGS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L108) enables is left alone, and the commit explains why: such a function has not run its AER setup, so its [`aer_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370) may not be set. Any other function gets its AER status cleared by [`pci_aer_clear_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L333) and its Device Status by [`pcie_clear_device_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2240), and the step returns 0 so the visit goes on. The four enables are one macro of drivers/pci/pci.h.

```c
/* drivers/pci/pci.h:108 */
#define PCI_EXP_AER_FLAGS	(PCI_EXP_DEVCTL_CERE | PCI_EXP_DEVCTL_NFERE | \
				 PCI_EXP_DEVCTL_FERE | PCI_EXP_DEVCTL_URRE)
```

The per-function AER setup sets these four bits, so their presence marks a function that went through it. [`pci_aer_clear_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L333) clears only where the operating system owns AER for the function, and [`pci_aer_raw_clear_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L308) does the writes.

```c
/* drivers/pci/pcie/aer.c:299 */
/**
 * pci_aer_raw_clear_status - Clear AER error registers.
 * @dev: the PCI device
 *
 * Clear AER error status registers unconditionally, regardless of
 * whether they're owned by firmware or the OS.
 *
 * Return: 0 on success, or negative on failure.
 */
int pci_aer_raw_clear_status(struct pci_dev *dev)
{
	int aer = dev->aer_cap;
	u32 status;
	int port_type;

	if (!aer)
		return -EIO;

	port_type = pci_pcie_type(dev);
	if (port_type == PCI_EXP_TYPE_ROOT_PORT ||
	    port_type == PCI_EXP_TYPE_RC_EC) {
		pci_read_config_dword(dev, aer + PCI_ERR_ROOT_STATUS, &status);
		pci_write_config_dword(dev, aer + PCI_ERR_ROOT_STATUS, status);
	}

	pci_read_config_dword(dev, aer + PCI_ERR_COR_STATUS, &status);
	pci_write_config_dword(dev, aer + PCI_ERR_COR_STATUS, status);

	pci_read_config_dword(dev, aer + PCI_ERR_UNCOR_STATUS, &status);
	pci_write_config_dword(dev, aer + PCI_ERR_UNCOR_STATUS, status);

	return 0;
}

int pci_aer_clear_status(struct pci_dev *dev)
{
	if (!pcie_aer_is_native(dev))
		return -EIO;

	return pci_aer_raw_clear_status(dev);
}
```

The raw clear writes each status register back to itself, and touches Root Error Status only on a Root Port or RCEC. Ownership is the question [`pcie_aer_is_native()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L242) answers for one function.

```c
/* drivers/pci/pcie/aer.c:242 */
int pcie_aer_is_native(struct pci_dev *dev)
{
	struct pci_host_bridge *host = pci_find_host_bridge(dev->bus);

	if (!dev->aer_cap)
		return 0;

	return pcie_ports_native || host->native_aer;
}
EXPORT_SYMBOL_NS_GPL(pcie_aer_is_native, "CXL");
```

A function is native when it has the capability and either [`pcie_ports_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L614) or its host bridge's [`native_aer`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L653) is set, the same pair the port driver tested for the root. [`pcie_clear_device_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2240) clears the four detected bits of Device Status and exists only with [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28).

```c
/* drivers/pci/pci.c:2239 */
#ifdef CONFIG_PCIEAER
void pcie_clear_device_status(struct pci_dev *dev)
{
	pcie_capability_write_word(dev, PCI_EXP_DEVSTA,
				   PCI_EXP_DEVSTA_CED | PCI_EXP_DEVSTA_NFED |
				   PCI_EXP_DEVSTA_FED | PCI_EXP_DEVSTA_URD);
}
```

The visit uses one of two walkers. [`pci_walk_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/bus.c#L461) holds [`pci_bus_sem`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/search.c#L17) for reading and hands the work to [`__pci_walk_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/bus.c#L408).

```c
/* drivers/pci/bus.c:448 */
/**
 *  pci_walk_bus - walk devices on/under bus, calling callback.
 *  @top: bus whose devices should be walked
 *  @cb: callback to be called for each device found
 *  @userdata: arbitrary pointer to be passed to callback
 *
 *  Walk the given bus, including any bridged devices
 *  on buses under this bus.  Call the provided callback
 *  on each device found.
 *
 *  We check the return of @cb each time. If it returns anything
 *  other than 0, we break out.
 */
void pci_walk_bus(struct pci_bus *top, int (*cb)(struct pci_dev *, void *), void *userdata)
{
	down_read(&pci_bus_sem);
	__pci_walk_bus(top, cb, userdata);
	up_read(&pci_bus_sem);
}
```

[`__pci_walk_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/bus.c#L408) calls the callback for each function of a bus and, before moving to the next function, walks the bus behind it; a nonzero return from the callback stops the walk.

```c
/* drivers/pci/bus.c:408 */
static int __pci_walk_bus(struct pci_bus *top, int (*cb)(struct pci_dev *, void *),
			  void *userdata)
{
	struct pci_dev *dev;
	int ret = 0;

	list_for_each_entry(dev, &top->devices, bus_list) {
		ret = cb(dev, userdata);
		if (ret)
			break;
		if (dev->subordinate) {
			ret = __pci_walk_bus(dev->subordinate, cb, userdata);
			if (ret)
				break;
		}
	}
	return ret;
}
```

The order is depth first, a bridge function before the functions behind it, and a walk below a Root Port starts at its secondary bus, so the Root Port itself is no step of it. For an RCEC, [`pcie_walk_rcec()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L134) visits the integrated endpoints associated with it, through the association that [`rcec_ea`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L374) records.

```c
/* drivers/pci/pcie/rcec.c:124 */
/**
 * pcie_walk_rcec - Walk RCiEP devices associating with RCEC and call callback.
 * @rcec:	RCEC whose RCiEP devices should be walked
 * @cb:		Callback to be called for each RCiEP device found
 * @userdata:	Arbitrary pointer to be passed to callback
 *
 * Walk the given RCEC. Call the callback on each RCiEP found.
 *
 * If @cb returns anything other than 0, break out.
 */
void pcie_walk_rcec(struct pci_dev *rcec, int (*cb)(struct pci_dev *, void *),
		    void *userdata)
{
	struct walk_rcec_data rcec_data;

	if (!rcec->rcec_ea)
		return;

	rcec_data.rcec = rcec;
	rcec_data.user_callback = cb;
	rcec_data.user_data = userdata;

	walk_rcec(walk_rcec_helper, &rcec_data);
}
```

An RCEC without an association record is skipped. The callback is wrapped, and how the wrapper treats its return value is read with the search, where it changes the result. The last step of [`aer_enable_rootport()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1533), and the first of disabling, are two helpers that change the three enables together.

```c
/* drivers/pci/pcie/aer.c:1491 */
static void aer_enable_irq(struct pci_dev *pdev)
{
	int aer = pdev->aer_cap;
	u32 reg32;

	/* Enable Root Port's interrupt in response to error messages */
	pci_read_config_dword(pdev, aer + PCI_ERR_ROOT_COMMAND, &reg32);
	reg32 |= ROOT_PORT_INTR_ON_MESG_MASK;
	pci_write_config_dword(pdev, aer + PCI_ERR_ROOT_COMMAND, reg32);
}

static void aer_disable_irq(struct pci_dev *pdev)
{
	int aer = pdev->aer_cap;
	u32 reg32;

	/* Disable Root Port's interrupt in response to error messages */
	pci_read_config_dword(pdev, aer + PCI_ERR_ROOT_COMMAND, &reg32);
	reg32 &= ~ROOT_PORT_INTR_ON_MESG_MASK;
	pci_write_config_dword(pdev, aer + PCI_ERR_ROOT_COMMAND, reg32);
}
```

[`aer_enable_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1491) reads Root Error Command, sets [`ROOT_PORT_INTR_ON_MESG_MASK`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L119) and writes the word back, and [`aer_disable_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1502) clears the same bits. Both act on the root and leave the other bits of the register as they were. The figure sets the state before the enabling against the state it leaves.

```text
    The root's registers and the functions below it, before aer_enable_rootport() and after it
    ──────────────────────────────────────────────────────────────────────────────────────────

                            before aer_enable_rootport()              after it
                            ┌─────────────────────────────────┐       ┌─────────────────────────────────┐
    Device Status           │ detected bits as found          │       │ written back: cleared           │
    Root Control            │ system-error enables as found   │       │ SECEE, SENFEE, SEFEE clear      │
    Root Error Status       │ message bits latched            │       │ written back: cleared           │
    functions below         │ COR and UNCOR status stale      │       │ cleared if a message bit        │
                            │ Device Status stale             │ ───▶  │ was latched, for each one       │
                            │                                 │       │ with a reporting enable         │
    root COR status         │ as latched                      │       │ written back: cleared           │
    root UNCOR status       │ as latched                      │       │ written back: cleared           │
    Root Error Command      │ enables as found                │       │ COR_EN, NONFATAL_EN and         │
                            │                                 │       │ FATAL_EN set                    │
                            └─────────────────────────────────┘       └─────────────────────────────────┘
```

After [`aer_enable_rootport()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1533), the root starts from cleared status with its three enables set, and when the root had latched a message, the functions below it hold no errors from before the probe. The next message raises the interrupt.

### aer_irq copies the root's status into the queue

The hard interrupt half runs with interrupts off on its CPU and cannot sleep, and the vector may be shared with the port's other services. Its job is to decide whether the interrupt is the root's AER interrupt, copy the root's two registers before another message changes them, clear the status so the root can latch the next message, and leave the rest to the thread. [`aer_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1470) is that half, with its kerneldoc.

```c
/* drivers/pci/pcie/aer.c:1463 */
/**
 * aer_irq - Root Port's ISR
 * @irq: IRQ assigned to Root Port
 * @context: pointer to Root Port data structure
 *
 * Invoked when Root Port detects AER messages.
 */
static irqreturn_t aer_irq(int irq, void *context)
{
	struct pcie_device *pdev = (struct pcie_device *)context;
	struct aer_rpc *rpc = get_service_data(pdev);
	struct pci_dev *rp = rpc->rpd;
	int aer = rp->aer_cap;
	struct aer_err_source e_src = {};

	pci_read_config_dword(rp, aer + PCI_ERR_ROOT_STATUS, &e_src.status);
	if (!(e_src.status & AER_ERR_STATUS_MASK))
		return IRQ_NONE;

	pci_read_config_dword(rp, aer + PCI_ERR_ROOT_ERR_SRC, &e_src.id);
	pci_write_config_dword(rp, aer + PCI_ERR_ROOT_STATUS, e_src.status);

	if (!kfifo_put(&rpc->aer_fifo, e_src))
		return IRQ_HANDLED;

	return IRQ_WAKE_THREAD;
}
```

The handler finds the root through the service device's [`priv_data`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L63) and reads Root Error Status into a zeroed record. A word with none of the [`AER_ERR_STATUS_MASK`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L125) bits means the interrupt was no AER message of this root, and `IRQ_NONE` says so to the interrupt core. Otherwise the handler reads Error Source Identification and writes the status word back, which clears the bits it read, before it queues the record. A full queue drops the record and returns `IRQ_HANDLED` without waking the thread for it, and a queued record returns `IRQ_WAKE_THREAD`.

The queue takes no lock. The kfifo header allows that for one reader and one writer, at [`kfifo.h:30-36`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/kfifo.h#L30).

```c
/* include/linux/kfifo.h:30 */
 * Note about locking: There is no locking required until only one reader
 * and one writer is using the fifo and no kfifo_reset() will be called.
 * kfifo_reset_out() can be safely used, until it will be only called
 * in the reader thread.
 * For multiple writer and one reader there is only a need to lock the writer.
 * And vice versa for only one writer and multiple reader there is only a need
 * to lock the reader.
```

Apart from [`INIT_KFIFO()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/kfifo.h#L129) in the probe, [`aer_fifo`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L56) is written at v7.2 by the [`kfifo_put()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/kfifo.h#L440) of [`aer_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1470) alone and read by [`aer_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1449) alone, one writer and one reader per root, so the condition of that comment holds. The swimlane follows one message across the reporting function, the root, the two halves and the queue.

```text
    One error message through the two halves of the AER interrupt
    ─────────────────────────────────────────────────────────────

    time ↓
    reporting function    Root Port              hard IRQ: aer_irq        aer_fifo             IRQ thread: aer_isr
    ───────────────────┼──────────────────────┼────────────────────────┼────────────────────┼────────────────────
    logs the error     ╎                      ╎                        ╎                    ╎
    ERR_* message ──────▶ status bit and      ╎                        ╎                    ╎
                       ╎  source ID latched   ╎                        ╎                    ╎
                       ╎  interrupt ───────────▶ status read; no       ╎                    ╎
                       ╎                      ╎  message bit: IRQ_NONE ╎                    ╎
                       ╎                      ╎  else source ID read   ╎                    ╎
                       ╎  status cleared ◀────── status written back   ╎                    ╎
                       ╎                      ╎  record pushed ─────────▶ one more record   ╎
                       ╎                      ╎  IRQ_WAKE_THREAD ────────────────────────────▶ woken
                       ╎                      ╎                        ╎  one fewer ◀───────── record popped,
                       ╎                      ╎                        ╎                    ╎  handled in full
                       ╎                      ╎                        ╎                    ╎  repeat while the
                       ╎                      ╎                        ╎                    ╎  queue holds one
                       ╎                      ╎                        ╎  empty             ╎  IRQ_HANDLED
                       ╎                      ╎                        ╎                    ╎
                       ╎                      ╎  queue full: record    ╎                    ╎
                       ╎                      ╎  dropped, IRQ_HANDLED  ╎                    ╎
```

After the hard half returns, the root's status is clear and the message waits in the queue as one record, which the thread takes next.

### aer_isr empties the queue in the interrupt thread

The interrupt thread runs after the hard half returns `IRQ_WAKE_THREAD`, in process context where it may sleep, take locks and visit the hierarchy. [`aer_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1449) takes records until the queue is empty, so one wakeup handles every message that arrived while the thread was busy.

```c
/* drivers/pci/pcie/aer.c:1442 */
/**
 * aer_isr - consume errors detected by Root Port
 * @irq: IRQ assigned to Root Port
 * @context: pointer to Root Port data structure
 *
 * Invoked, as DPC, when Root Port records new detected error
 */
static irqreturn_t aer_isr(int irq, void *context)
{
	struct pcie_device *dev = (struct pcie_device *)context;
	struct aer_rpc *rpc = get_service_data(dev);
	struct aer_err_source e_src;

	if (kfifo_is_empty(&rpc->aer_fifo))
		return IRQ_NONE;

	while (kfifo_get(&rpc->aer_fifo, &e_src))
		aer_isr_one_error(rpc->rpd, &e_src);
	return IRQ_HANDLED;
}
```

An empty queue at entry returns `IRQ_NONE`. Each record goes to [`aer_isr_one_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1405) together with the root from [`rpd`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L55), and the thread returns `IRQ_HANDLED` once the queue is empty. commit [6200cc5ee2ba](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=6200cc5ee2baa573e7ac4dbcfca750e0b777c37d) ("PCI/AER: Use threaded IRQ for bottom half") moved this half into the interrupt thread because, in its message's words, the threaded IRQ is naturally single threaded, so the records of one root are handled one at a time.

So far, the root's service device is bound, its [`struct aer_rpc`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L54) holds the root and the queue, the root's interrupt is enabled, and one message has passed through the hard half into the queue and out to the thread.

What the thread does with one record fills the rest of the error path.

### aer_isr_one_error turns one record into per-class records

A record holds the root's status word, and one word can report a correctable and an uncorrectable message together, each with its own source ID. The code treats the two classes as separate errors, each described by a [`struct aer_err_info`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L833) on the thread's stack. [`aer_isr_one_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1405) builds them from one record, the correctable one first as its comment asks.

```c
/* drivers/pci/pcie/aer.c:1405 */
static void aer_isr_one_error(struct pci_dev *root,
			      struct aer_err_source *e_src)
{
	u32 status = e_src->status;

	pci_rootport_aer_stats_incr(root, e_src);

	/*
	 * There is a possibility that both correctable error and
	 * uncorrectable error being logged. Report correctable error first.
	 */
	if (status & PCI_ERR_ROOT_COR_RCV) {
		int multi = status & PCI_ERR_ROOT_MULTI_COR_RCV;
		struct aer_err_info e_info = {
			.id = ERR_COR_ID(e_src->id),
			.severity = AER_CORRECTABLE,
			.level = KERN_WARNING,
			.multi_error_valid = multi ? 1 : 0,
		};

		aer_isr_one_error_type(root, &e_info);
	}

	if (status & PCI_ERR_ROOT_UNCOR_RCV) {
		int fatal = status & PCI_ERR_ROOT_FATAL_RCV;
		int multi = status & PCI_ERR_ROOT_MULTI_UNCOR_RCV;
		struct aer_err_info e_info = {
			.id = ERR_UNCOR_ID(e_src->id),
			.severity = fatal ? AER_FATAL : AER_NONFATAL,
			.level = KERN_ERR,
			.multi_error_valid = multi ? 1 : 0,
		};

		aer_isr_one_error_type(root, &e_info);
	}
}
```

The root's message counters are updated first, by [`pci_rootport_aer_stats_incr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L781). A set [`PCI_ERR_ROOT_COR_RCV`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L827) yields a correctable record whose ID is [`ERR_COR_ID`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L122) of the source word, printed at `KERN_WARNING`. A set [`PCI_ERR_ROOT_UNCOR_RCV`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L829) yields an uncorrectable record whose ID is [`ERR_UNCOR_ID`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L123), fatal when [`PCI_ERR_ROOT_FATAL_RCV`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L833) is set and non-fatal otherwise, printed at `KERN_ERR`. Each class's multiple-message bit sets [`multi_error_valid`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L844), which later lets the search collect more than one function. The members the initializer does not name start at zero, and each record goes to [`aer_isr_one_error_type()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1373) before the next one is built.

The severities are three macros of include/linux/aer.h, and the rest of the page uses their names for the classes.

```c
/* include/linux/aer.h:14 */
#define AER_NONFATAL			0
#define AER_FATAL			1
#define AER_CORRECTABLE			2
```

The value of [`severity`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L841) decides the record's log level here and its handling later, and the table sets the three side by side.

| severity | root status bits | log level | handling of each reporting function |
|---|---|---|---|
| [`AER_CORRECTABLE`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L16) | [`PCI_ERR_ROOT_COR_RCV`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L827) | `KERN_WARNING` | status cleared, the driver's [`cor_error_detected`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L960) called where AER is native |
| [`AER_NONFATAL`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L14) | [`PCI_ERR_ROOT_UNCOR_RCV`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L829) without [`PCI_ERR_ROOT_FATAL_RCV`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L833) | `KERN_ERR` | [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) with [`pci_channel_io_normal`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L210) |
| [`AER_FATAL`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L15) | [`PCI_ERR_ROOT_UNCOR_RCV`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L829) with [`PCI_ERR_ROOT_FATAL_RCV`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L833) | `KERN_ERR` | [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) with [`pci_channel_io_frozen`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L213) |

[`pci_rootport_aer_stats_incr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L781) counts the classes of the messages the root received, in the [`struct aer_info`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L60) of the root's function, before anything is searched or printed.

```c
/* drivers/pci/pcie/aer.c:781 */
static void pci_rootport_aer_stats_incr(struct pci_dev *pdev,
				 struct aer_err_source *e_src)
{
	struct aer_info *aer_info = pdev->aer_info;

	if (!aer_info)
		return;

	if (e_src->status & PCI_ERR_ROOT_COR_RCV)
		aer_info->rootport_total_cor_errs++;

	if (e_src->status & PCI_ERR_ROOT_UNCOR_RCV) {
		if (e_src->status & PCI_ERR_ROOT_FATAL_RCV)
			aer_info->rootport_total_fatal_errs++;
		else
			aer_info->rootport_total_nonfatal_errs++;
	}
}
```

The root's totals grow for every message, whether or not a line is printed later, and a root without [`aer_info`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L371) counts nothing. A fatal message counts as fatal and every other uncorrectable one as non-fatal, the same split the records use. The figure maps the record's bits and halves onto the two records.

```text
    One struct aer_err_source becomes up to two struct aer_err_info records
    ───────────────────────────────────────────────────────────────────────

    struct aer_err_source                             struct aer_err_info, correctable
    ┌─────────────────────────────────┐               ┌─────────────────────────────────────────────────┐
    │ status  bit 0  COR_RCV          │  if COR_RCV   │ id                 ERR_COR_ID(id), bits 15:0    │
    │         bit 1  MULTI_COR_RCV    ├──────────────▶│ severity           AER_CORRECTABLE              │
    │         bit 2  UNCOR_RCV        │               │ level              KERN_WARNING                 │
    │         bit 3  MULTI_UNCOR_RCV  │               │ multi_error_valid  MULTI_COR_RCV set            │
    │         bit 6  FATAL_RCV        │               └─────────────────────────────────────────────────┘
    │                                 │
    │ id      31:16  uncorrectable ID │               struct aer_err_info, uncorrectable
    │         15:0   correctable ID   │ if UNCOR_RCV  ┌─────────────────────────────────────────────────┐
    │                                 ├──────────────▶│ id                 ERR_UNCOR_ID(id), bits 31:16 │
    └─────────────────────────────────┘               │ severity           AER_FATAL if FATAL_RCV,      │
                                                      │                    else AER_NONFATAL            │
    the correctable record is searched,               │ level              KERN_ERR                     │
    logged and handled first, the                     │ multi_error_valid  MULTI_UNCOR_RCV set          │
    uncorrectable one after it                        └─────────────────────────────────────────────────┘
```

The record type carries more than the initializer fills. Its definition in drivers/pci/pci.h follows the macro that sizes its arrays, and the table names what each member holds and which function writes it.

| member | what it holds | written by |
|---|---|---|
| [`dev`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L834) | the reporting functions found, each with a reference | [`add_error_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L985) |
| [`ratelimit_print`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L835) | per function, whether its lines print | [`add_error_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L985) |
| [`error_dev_num`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L836) | how many entries of the arrays are used | [`find_source_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1099), [`add_error_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L985) |
| [`level`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L837), [`id`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L839), [`severity`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L841), [`multi_error_valid`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L844) | the log level, the source's Requester ID, the class and whether several messages arrived | [`aer_isr_one_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1405) |
| [`root_ratelimit_print`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L842) | whether the root's source line prints | [`add_error_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L985) |
| [`first_error`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L846), [`is_cxl`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L848), [`tlp_header_valid`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L849), [`status`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L851), [`mask`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L852), [`tlp`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L853) | the current function's First Error Pointer, the bus type the printers name, its status and mask words and its logged header | [`aer_get_device_error_info()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1293) |

```c
/* drivers/pci/pci.h:812 */
#define AER_MAX_MULTI_ERR_DEVICES	5	/* Not likely to have more */

/**
 * struct aer_err_info - AER Error Information
 * @dev: Devices reporting error
 * @ratelimit_print: Flag to log or not log the devices' error. 0=NotLog/1=Log
 * @__pad1: Padding for alignment
 * @error_dev_num: Number of devices reporting an error
 * @level: printk level to use in logging
 * @id: Value from register PCI_ERR_ROOT_ERR_SRC
 * @severity: AER severity, 0-UNCOR Non-fatal, 1-UNCOR fatal, 2-COR
 * @root_ratelimit_print: Flag to log or not log the root's error. 0=NotLog/1=Log
 * @multi_error_valid: If multiple errors are reported
 * @first_error: First reported error
 * @__pad2: Padding for alignment
 * @is_cxl: Bus type error: 0-PCI Bus error, 1-CXL Bus error
 * @tlp_header_valid: Indicates if TLP field contains error information
 * @status: COR/UNCOR error status
 * @mask: COR/UNCOR mask
 * @tlp: Transaction packet information
 */
struct aer_err_info {
	struct pci_dev *dev[AER_MAX_MULTI_ERR_DEVICES];
	int ratelimit_print[AER_MAX_MULTI_ERR_DEVICES];
	int error_dev_num;
	const char *level;

	unsigned int id:16;

	unsigned int severity:2;
	unsigned int root_ratelimit_print:1;
	unsigned int __pad1:4;
	unsigned int multi_error_valid:1;

	unsigned int first_error:5;
	unsigned int __pad2:1;
	unsigned int is_cxl:1;
	unsigned int tlp_header_valid:1;

	unsigned int status;
	unsigned int mask;
	struct pcie_tlp_log tlp;
};
```

[`AER_MAX_MULTI_ERR_DEVICES`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L812), 5, sizes both arrays, so one record holds five reporting functions at most, and its comment gives as the reason that more are not likely. The bit-fields pack the ID, the class and the flags into words, with two padding fields that no code at v7.2 reads or writes. One record exists from its initializer to the return of [`aer_isr_one_error_type()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1373), and four functions write it; the strip follows its members in the order the code reaches them.

```text
    One struct aer_err_info from its initializer to the return of aer_isr_one_error()
    ─────────────────────────────────────────────────────────────────────────────────

    fields: id, severity, level, multi_error_valid, error_dev_num, dev[], the two ratelimit flags,
            status, mask, first_error, tlp_header_valid and tlp; one record, on the stack of aer_isr_one_error

    time ───────────────────────────────────────────────────────────────────────────────────────────────────────────▶
    event                 built         search      each match    pass 1, per i             pass 2, per i        return
                          ▼             ▼           ▼             ▼                         ▼                    ▼
                          ┌──────────────────────────────────────────────────────────────────────────────────────┐
    id, severity,         │«1» correctable or «2» uncorrectable values, unchanged to the end                     │
    level, multi          └──────────────────────────────────────────────────────────────────────────────────────┘
                          ┌─────────────┬───────────┬────────────────────────────────────────────────────────────┐
    error_dev_num         │0            │«3» 0      │«5» one more per match, then unchanged                      │
                          └─────────────┴───────────┴────────────────────────────────────────────────────────────┘
                          ┌─────────────────────────┬────────────────────────────────────────────────────────────┐
    dev[i]                │NULL                     │«4» the matching function, with a reference taken           │
                          └─────────────────────────┴────────────────────────────────────────────────────────────┘
                          ┌─────────────────────────┬────────────────────────────────────────────────────────────┐
    ratelimit_print[i],   │0                        │«6» «7» 1 unless ratelimited                                │
    root_ratelimit_print  └─────────────────────────┴────────────────────────────────────────────────────────────┘
                          ┌───────────────────────────────────────┬─────────────────────────┬────────────────────┐
    status                │0                                      │«8» 0, «10» or «12» read │«8» «10» «12» again │
                          └───────────────────────────────────────┴─────────────────────────┴────────────────────┘
                          ┌───────────────────────────────────────┬─────────────────────────┬────────────────────┐
    mask                  │0                                      │«11» or «13» read        │«11» «13» again     │
                          └───────────────────────────────────────┴─────────────────────────┴────────────────────┘
                          ┌───────────────────────────────────────┬─────────────────────────┬────────────────────┐
    first_error           │0                                      │«14» uncorrectable       │«14» again          │
                          └───────────────────────────────────────┴─────────────────────────┴────────────────────┘
                          ┌───────────────────────────────────────┬─────────────────────────┬────────────────────┐
    tlp_header_valid,     │0                                      │«9» 0, «15» 1 «16» log   │«9» «15» «16» again │
    tlp                   └───────────────────────────────────────┴─────────────────────────┴────────────────────┘

    «1»  aer_isr_one_error          aer.c:1418  fills the correctable record from the initializer
    «2»  aer_isr_one_error          :1431       fills the uncorrectable record from the initializer
    «3»  find_source_device         :1106       resets error_dev_num before the search
    «4»  add_error_device           :992        stores the function in dev[i] with pci_dev_get
    «5»  add_error_device           :993        counts the function in error_dev_num
    «6»  add_error_device           :1004       allows the function's log lines in ratelimit_print[i]
    «7»  add_error_device           :1005       allows the root's source line in root_ratelimit_print
    «8»  aer_get_device_error_info  :1307       clears status before reading the next function
    «9»  aer_get_device_error_info  :1308       clears tlp_header_valid before reading
    «10» aer_get_device_error_info  :1316       reads the correctable status with pci_read_config_dword
    «11» aer_get_device_error_info  :1318       reads the correctable mask with pci_read_config_dword
    «12» aer_get_device_error_info  :1328       reads the uncorrectable status with pci_read_config_dword
    «13» aer_get_device_error_info  :1330       reads the uncorrectable mask with pci_read_config_dword
    «14» aer_get_device_error_info  :1337       stores the First Error Pointer from PCI_ERR_CAP_FEP
    «15» aer_get_device_error_info  :1340       marks the header log valid when one was logged
    «16» aer_get_device_error_info  :1341       reads the logged header into tlp with pcie_read_tlp_log
```

«1» [`aer_isr_one_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1405) fills the correctable record from its initializer, which leaves the other members zero. «2» aer_isr_one_error() fills the uncorrectable record the same way. «3» [`find_source_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1099) resets [`error_dev_num`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L836) before the search. «4» [`add_error_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L985) stores a matching function in [`dev`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L834) with a reference taken by [`pci_dev_get()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L1565). «5» add_error_device() counts the function in error_dev_num. «6» add_error_device() sets [`ratelimit_print`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L835) for the function when its class passes the function's ratelimit. «7» add_error_device() sets [`root_ratelimit_print`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L842) in the same case. «8» [`aer_get_device_error_info()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1293) clears [`status`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L851) before it reads the next function. «9» aer_get_device_error_info() clears [`tlp_header_valid`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L849) the same way. «10» aer_get_device_error_info() reads the correctable status with [`pci_read_config_dword()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/access.c#L580). «11» aer_get_device_error_info() reads the correctable mask. «12» aer_get_device_error_info() reads the uncorrectable status. «13» aer_get_device_error_info() reads the uncorrectable mask. «14» aer_get_device_error_info() stores the First Error Pointer in [`first_error`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L846). «15» aer_get_device_error_info() marks a logged header valid. «16» aer_get_device_error_info() reads the logged header into [`tlp`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L853) with [`pcie_read_tlp_log()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L63).

The register members change once per function and pass, because [`aer_process_err_devices()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1352) reads each function twice and the record is shared by all of them. Two other instances of the type are filled by code this page does not show. [`dpc_get_aer_uncorrect_severity()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L236) of dpc.c fills the DPC driver's own record before that driver calls [`aer_get_device_error_info()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1293), and [`pci_print_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L926) fills a record of the firmware-first path; both belong to other paths and are left out. A record leaves [`aer_isr_one_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1405) with its class and source ID set and its function list empty, and the search fills that list.

### aer_isr_one_error_type searches before it prints the source

Each record goes through three steps, which find the functions that logged the error, print the source line the root received, and process the functions found. [`aer_isr_one_error_type()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1373) runs them, and the printing of the source depends on ratelimit flags that the search has already set.

```c
/* drivers/pci/pcie/aer.c:1367 */
/**
 * aer_isr_one_error_type - consume a Correctable or Uncorrectable Error
 *			    detected by Root Port or RCEC
 * @root: pointer to Root Port or RCEC that signaled AER interrupt
 * @info: pointer to AER error info
 */
static void aer_isr_one_error_type(struct pci_dev *root,
				   struct aer_err_info *info)
{
	bool found;

	found = find_source_device(root, info);

	/*
	 * If we're going to log error messages, we've already set
	 * "info->root_ratelimit_print" and "info->ratelimit_print[i]" to
	 * non-zero (which enables printing) because this is either an
	 * ERR_FATAL or we found a device with an error logged in its AER
	 * Capability.
	 *
	 * If we didn't find the Error Source device, at least log the
	 * Requester ID from the ERR_* Message received by the Root Port or
	 * RCEC, ratelimited by the RP or RCEC.
	 */
	if (info->root_ratelimit_print ||
	    (!found && aer_ratelimit(root, info->severity)))
		aer_print_source(root, info, found);

	if (found)
		aer_process_err_devices(info);
}
```

The search returns whether any function was found. The source line prints when the search set [`root_ratelimit_print`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L842), or when nothing was found and the root's own ratelimit lets a line of the class through. Processing runs only when a function was found, so a message whose source is not found leaves at most the source line in the log. [`aer_print_source()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L852) prints that line on the root, with the source ID decoded into domain, bus, device and function.

```c
/* drivers/pci/pcie/aer.c:852 */
static void aer_print_source(struct pci_dev *dev, struct aer_err_info *info,
			     bool found)
{
	u16 source = info->id;

	pci_info(dev, "%s%s error message received from %04x:%02x:%02x.%d%s\n",
		 info->multi_error_valid ? "Multiple " : "",
		 aer_error_severity_string[info->severity],
		 pci_domain_nr(dev->bus), PCI_BUS_NUM(source),
		 PCI_SLOT(source), PCI_FUNC(source),
		 found ? "" : " (no details found");
}
```

The line names the class and whether several messages arrived, and the suffix "(no details found" marks a record whose search found nothing. commit [1291b716bbf9](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=1291b716bbf969e101d517bfb8ba18d958f758b8) ("PCI/AER: Decode Requester ID when no error info found") added the decoded ID for that case. Whether a line passes is decided by [`aer_ratelimit()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L800), per function and per class.

```c
/* drivers/pci/pcie/aer.c:800 */
static int aer_ratelimit(struct pci_dev *dev, unsigned int severity)
{
	if (!dev->aer_info)
		return 1;

	switch (severity) {
	case AER_NONFATAL:
		return __ratelimit(&dev->aer_info->nonfatal_ratelimit);
	case AER_CORRECTABLE:
		return __ratelimit(&dev->aer_info->correctable_ratelimit);
	default:
		return 1;	/* Don't ratelimit fatal errors */
	}
}
```

Fatal errors pass every time, as the comment says, and so does every class for a function without [`aer_info`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L371). Correctable and non-fatal lines go through the function's own [`correctable_ratelimit`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L95) and [`nonfatal_ratelimit`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L96), whose sysfs files the last subsection lists. The search that these steps start comes first in the code and is read next.

### find_source_device collects the functions that logged the error

The root's source ID names one function, but the ID can be unusable, and when several messages arrived it names one source of several. The service therefore tests functions itself. [`find_source_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1099) tests the root first and then the functions that report to it, and its kerneldoc states what the caller sets and what the search fills.

```c
/* drivers/pci/pcie/aer.c:1087 */
/**
 * find_source_device - search through device hierarchy for source device
 * @parent: pointer to Root Port pci_dev data structure
 * @e_info: including detailed error information such as ID
 *
 * Return: true if found.
 *
 * Invoked by DPC when error is detected at the Root Port.
 * Caller of this function must set id, severity, and multi_error_valid of
 * struct aer_err_info pointed by @e_info properly.  This function must fill
 * e_info->error_dev_num and e_info->dev[], based on the given information.
 */
static bool find_source_device(struct pci_dev *parent,
			       struct aer_err_info *e_info)
{
	struct pci_dev *dev = parent;
	int result;

	/* Must reset in this function */
	e_info->error_dev_num = 0;

	/* Is Root Port an agent that sends error message? */
	result = find_device_iter(dev, e_info);
	if (result)
		return true;

	if (pci_pcie_type(parent) == PCI_EXP_TYPE_RC_EC)
		pcie_walk_rcec(parent, find_device_iter, e_info);
	else
		pci_walk_bus(parent->subordinate, find_device_iter, e_info);

	if (!e_info->error_dev_num)
		return false;
	return true;
}
```

The search resets [`error_dev_num`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L836) and calls the per-function step on the root itself, and a root that is the source of a single message ends the search there. Otherwise it visits the integrated endpoints of an RCEC or the hierarchy below a Root Port's secondary bus, and it reports success when it added at least one function. The kerneldoc says DPC invokes the function, but at v7.2 its one caller is [`aer_isr_one_error_type()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1373). [`find_device_iter()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1067) is the per-function step, and its return value tells the walker whether to go on.

```c
/* drivers/pci/pcie/aer.c:1067 */
static int find_device_iter(struct pci_dev *dev, void *data)
{
	struct aer_err_info *e_info = (struct aer_err_info *)data;

	if (is_error_source(dev, e_info)) {
		/* List this device */
		if (add_error_device(e_info, dev)) {
			/* We cannot handle more... Stop iteration */
			pci_err(dev, "Exceeded max supported (%d) devices with errors logged\n",
				AER_MAX_MULTI_ERR_DEVICES);
			return 1;
		}

		/* If there is only a single error, stop iteration */
		if (!e_info->multi_error_valid)
			return 1;
	}
	return 0;
}
```

A function that [`is_error_source()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1015) accepts is added. The step stops the walk in two cases. One is a full record, which prints the limit message that commit [a6f494becf09](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=a6f494becf09c9ebba72ed67d3728f6811daa634) ("PCI/AER: Add message when AER_MAX_MULTI_ERR_DEVICES limit is hit") added, and the other is a record of a single message, for which one match is the answer. A record with [`multi_error_valid`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L844) set keeps the walk going, so every function with a logged error of the class is collected, up to the limit. [`add_error_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L985) stores the function and decides whether its lines print.

```c
/* drivers/pci/pcie/aer.c:980 */
/**
 * add_error_device - list device to be handled
 * @e_info: pointer to error info
 * @dev: pointer to pci_dev to be added
 */
static int add_error_device(struct aer_err_info *e_info, struct pci_dev *dev)
{
	int i = e_info->error_dev_num;

	if (i >= AER_MAX_MULTI_ERR_DEVICES)
		return -ENOSPC;

	e_info->dev[i] = pci_dev_get(dev);
	e_info->error_dev_num++;

	/*
	 * Ratelimit AER log messages.  "dev" is either the source
	 * identified by the root's Error Source ID or it has an unmasked
	 * error logged in its own AER Capability.  Messages are emitted
	 * when "ratelimit_print[i]" is non-zero.  If we will print detail
	 * for a downstream device, make sure we print the Error Source ID
	 * from the root as well.
	 */
	if (aer_ratelimit(dev, e_info->severity)) {
		e_info->ratelimit_print[i] = 1;
		e_info->root_ratelimit_print = 1;
	}
	return 0;
}
```

The slot index is the current count, and a sixth function is refused with -ENOSPC because [`AER_MAX_MULTI_ERR_DEVICES`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L812) is 5. A stored function holds a reference from [`pci_dev_get()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L1565), which [`handle_error_source()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1196) drops with [`pci_dev_put()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L1580) after handling it. When [`aer_ratelimit()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L800) lets the function's class pass, the function's flag and the root's flag are both set, so a printed function comes with the root's source line, as the comment explains. The reference is taken on the function's embedded device.

```c
/* drivers/pci/pci-driver.c:1565 */
struct pci_dev *pci_dev_get(struct pci_dev *dev)
{
	if (dev)
		get_device(&dev->dev);
	return dev;
}
EXPORT_SYMBOL(pci_dev_get);

/**
 * pci_dev_put - release a use of the pci device structure
 * @dev: device that's been disconnected
 *
 * Must be called when a user of a device is finished with it.  When the last
 * user of the device calls this function, the memory of the device is freed.
 */
void pci_dev_put(struct pci_dev *dev)
{
	if (dev)
		put_device(&dev->dev);
}
EXPORT_SYMBOL(pci_dev_put);
```

Both helpers accept NULL and count through the function's embedded [`dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L446), so a reporting function stays allocated while the record holds it, even if it is removed meanwhile. Below an RCEC the walk treats the step's return value differently. [`pcie_walk_rcec()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L134) wraps the callback in [`walk_rcec_helper()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L56), which calls it for an integrated endpoint associated with the RCEC and returns 0 in every case.

```c
/* drivers/pci/pcie/rcec.c:56 */
static int walk_rcec_helper(struct pci_dev *dev, void *data)
{
	struct walk_rcec_data *rcec_data = data;
	struct pci_dev *rcec = rcec_data->rcec;

	if ((pci_pcie_type(dev) == PCI_EXP_TYPE_RC_END) &&
	    rcec_assoc_rciep(rcec, dev))
		rcec_data->user_callback(dev, rcec_data->user_data);

	return 0;
}
```

The callback's return value is dropped, so [`find_device_iter()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1067) cannot stop a walk below an RCEC. Every associated endpoint is tested, a single-message record can collect several functions, and a full record prints the limit message once for each further match. [`rcec_assoc_rciep()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L24) is the association test.

```c
/* drivers/pci/pcie/rcec.c:24 */
static bool rcec_assoc_rciep(struct pci_dev *rcec, struct pci_dev *rciep)
{
	unsigned long bitmap = rcec->rcec_ea->bitmap;
	unsigned int devn;

	/* An RCiEP found on a different bus in range */
	if (rcec->bus->number != rciep->bus->number)
		return true;

	/* Same bus, so check bitmap */
	for_each_set_bit(devn, &bitmap, 32)
		if (devn == PCI_SLOT(rciep->devfn))
			return true;

	return false;
}
```

An endpoint on another bus than the RCEC's is associated, because the walk reaches other buses only inside the association's bus range, and an endpoint on the RCEC's own bus is associated when the bitmap holds its device number. [`walk_rcec()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L68) decides which buses those endpoints are on.

```c
/* drivers/pci/pcie/rcec.c:68 */
static void walk_rcec(int (*cb)(struct pci_dev *dev, void *data),
		      void *userdata)
{
	struct walk_rcec_data *rcec_data = userdata;
	struct pci_dev *rcec = rcec_data->rcec;
	u8 nextbusn, lastbusn;
	struct pci_bus *bus;
	unsigned int bnr;

	if (!rcec->rcec_ea)
		return;

	/* Walk own bus for bitmap based association */
	pci_walk_bus(rcec->bus, cb, rcec_data);

	nextbusn = rcec->rcec_ea->nextbusn;
	lastbusn = rcec->rcec_ea->lastbusn;

	/* All RCiEP devices are on the same bus as the RCEC */
	if (nextbusn == 0xff && lastbusn == 0x00)
		return;

	for (bnr = nextbusn; bnr <= lastbusn; bnr++) {
		/* No association indicated (PCIe 5.0-1, 7.9.10.3) */
		if (bnr == rcec->bus->number)
			continue;

		bus = pci_find_bus(pci_domain_nr(rcec->bus), bnr);
		if (!bus)
			continue;

		/* Find RCiEP devices on the given bus ranges */
		pci_walk_bus(bus, cb, rcec_data);
	}
}
```

Both visits use [`pci_walk_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/bus.c#L461) with the wrapper, so within each bus the depth-first order of the Root Port case holds, and a range of 0xff to 0x00 means that every endpoint is on the RCEC's own bus, as the comment says. The figure follows a Root Port with a switch below it through one multiple-message search.

```text
    The search below a Root Port: functions in visiting order, and the slots of dev[] they fill
    ───────────────────────────────────────────────────────────────────────────────────────────

    visited in order      the root    01:00.0     02:00.0     02:01.0     03:00.0     02:02.0
                        ┌───────────┬───────────┬───────────┬───────────┬───────────┬───────────┐
    is_error_source     │   no      │   yes     │   no      │   yes     │   yes     │   no      │
                        └───────────┴─────┬─────┴───────────┴─────┬─────┴─────┬─────┴───────────┘
                                          ▼                       ▼           ▼
    multiple errors                     dev[0]                  dev[1]      dev[2]

    dev[] after it          [0]         [1]         [2]         [3]         [4]
                        ┌───────────┬───────────┬───────────┬───────────┬───────────┐
    error_dev_num 3     │ 01:00.0   │ 02:01.0   │ 03:00.0   │ NULL      │ NULL      │
                        └───────────┴───────────┴───────────┴───────────┴───────────┘
                        AER_MAX_MULTI_ERR_DEVICES slots, 5

    single error        the walk stops at 01:00.0, the first match: dev[0] only, error_dev_num 1
    a sixth match       add_error_device() refuses it, the message prints, the walk stops
    below an RCEC       pcie_walk_rcec() visits every associated RCiEP, whatever the callback returns
    no match at all     find_source_device() returns false: only the source line prints
```

After the search, [`dev`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L834) lists the reporting functions in the order the walk met them, each with a reference, and [`error_dev_num`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L836) counts them. The test that accepts one function is read next.

### is_error_source matches the source ID or reads the status

The test for one function has two ways to say yes. The source ID in the record can name the function directly, and when the ID cannot be used or several messages arrived, the function's own AER status registers show whether it logged an unmasked error of the record's class. [`is_error_source()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1015) is read in two pieces.

| piece | lines | stage |
|---|---|---|
| ❶ | aer.c:1015-1034 | compares the source ID with the function's Requester ID |
| ❷ | aer.c:1035-1065 | reads the function's status and mask when the ID did not decide |

❶ The first piece of [`is_error_source()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1015), after its kerneldoc, uses the ID unless its bus number is zero or the bus carries the flag that marks source IDs as unusable.

```c
/* drivers/pci/pcie/aer.c:1010 */
/**
 * is_error_source - check whether the device is source of reported error
 * @dev: pointer to pci_dev to be checked
 * @e_info: pointer to reported error info
 */
static bool is_error_source(struct pci_dev *dev, struct aer_err_info *e_info)
{
	int aer = dev->aer_cap;
	u32 status, mask;
	u16 reg16;

	/*
	 * When bus ID is equal to 0, it might be a bad ID
	 * reported by Root Port.
	 */
	if ((PCI_BUS_NUM(e_info->id) != 0) &&
	    !(dev->bus->bus_flags & PCI_BUS_FLAGS_NO_AERSID)) {
		/* Device ID match? */
		if (e_info->id == pci_dev_id(dev))
			return true;

		/* Continue ID comparing if there is no multiple error */
		if (!e_info->multi_error_valid)
			return false;
	}
```

A usable ID equal to [`pci_dev_id()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L739) of the function makes it the source. A usable ID that differs ends the test with false for a single-message record, so a single message with a usable ID is attributed by the ID alone. A multiple-message record falls through to the registers, since other functions may have logged errors too. [`pci_dev_id()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L739) builds the function's Requester ID the way the root records one, the bus number over devfn.

```c
/* include/linux/pci.h:739 */
static inline u16 pci_dev_id(struct pci_dev *dev)
{
	return PCI_DEVID(dev->bus->number, dev->devfn);
}
```

The comparison is between two 16-bit Requester IDs with the bus number in the high byte. [`PCI_BUS_FLAGS_NO_AERSID`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L276) is set by an early x86 fixup on the root buses of one kind of domain whose Root Ports change the source ID of every message, according to its comment.

```c
/* arch/x86/pci/fixup.c:681 */
/*
 * VMD-enabled root ports will change the source ID for all messages
 * to the VMD device. Rather than doing device matching with the source
 * ID, the AER driver should traverse the child device tree, reading
 * AER registers to find the faulting device.
 */
static void quirk_no_aersid(struct pci_dev *pdev)
{
	/* VMD Domain */
	if (is_vmd(pdev->bus) && pci_is_root_bus(pdev->bus))
		pdev->bus->bus_flags |= PCI_BUS_FLAGS_NO_AERSID;
}
DECLARE_PCI_FIXUP_CLASS_EARLY(PCI_VENDOR_ID_INTEL, PCI_ANY_ID,
			      PCI_CLASS_BRIDGE_PCI, 8, quirk_no_aersid);
```

For a function on such a bus the ID is never compared, and its test goes to the registers. ❷ The second piece of [`is_error_source()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1015) reads them.

```c
/* drivers/pci/pcie/aer.c:1035 */

	/*
	 * When either
	 *      1) bus ID is equal to 0. Some ports might lose the bus
	 *              ID of error source id;
	 *      2) bus flag PCI_BUS_FLAGS_NO_AERSID is set
	 *      3) There are multiple errors and prior ID comparing fails;
	 * We check AER status registers to find possible reporter.
	 */

	/* Check if AER is enabled */
	pcie_capability_read_word(dev, PCI_EXP_DEVCTL, &reg16);
	if (!(reg16 & PCI_EXP_AER_FLAGS))
		return false;

	if (!aer)
		return false;

	/* Check if error is recorded */
	if (e_info->severity == AER_CORRECTABLE) {
		pci_read_config_dword(dev, aer + PCI_ERR_COR_STATUS, &status);
		pci_read_config_dword(dev, aer + PCI_ERR_COR_MASK, &mask);
	} else {
		pci_read_config_dword(dev, aer + PCI_ERR_UNCOR_STATUS, &status);
		pci_read_config_dword(dev, aer + PCI_ERR_UNCOR_MASK, &mask);
	}
	if (status & ~mask)
		return true;

	return false;
}
```

A function whose Device Control has none of the [`PCI_EXP_AER_FLAGS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L108) enables, or which has no AER capability, is not a source, since its AER setup has not run. Otherwise the correctable pair is read for an [`AER_CORRECTABLE`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L16) record and the uncorrectable pair for the other classes, and an unmasked status bit makes the function a source. The test ignores driver binding. commit [1ab4a3c80508](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=1ab4a3c805084d752ec571efc78272295a9f2f74) ("PCI/AER: Stop ruling out unbound devices as error source") removed the check that skipped functions without a driver, because, in its message's words, errors may very well be reported by unbound devices. The flowchart sets the tests in code order with the outcome of each.

```text
    The tests is_error_source() applies to one function, in the order of the code
    ─────────────────────────────────────────────────────────────────────────────

            ┌─────────────────────────────────────────────────┐
      ┌─no──┤ bus number of id nonzero, and the bus           │
      │     │ has no PCI_BUS_FLAGS_NO_AERSID flag?            │
      │     └────────────────────────┬────────────────────────┘
      │                          yes │
      │                              ▼
      │     ┌─────────────────────────────────────────────────┐
      │     │ id equals pci_dev_id() of the function?         ├─ yes ───▶ the source
      │     └────────────────────────┬────────────────────────┘
      │                           no │
      │                              ▼
      │     ┌─────────────────────────────────────────────────┐
      │     │ multi_error_valid set?                          ├─ no ────▶ not the source
      │     └────────────────────────┬────────────────────────┘
      │                          yes │
      └──────────────────────────────┤
                                     ▼
            ┌─────────────────────────────────────────────────┐
            │ Device Control holds any of the four            ├─ no ────▶ not the source
            │ PCI_EXP_AER_FLAGS enables, and aer_cap          │
            │ is nonzero?                                     │
            └────────────────────────┬────────────────────────┘
                                 yes │
                                     ▼
            ┌─────────────────────────────────────────────────┐
            │ status & ~mask nonzero, from the correctable    ├─ yes ───▶ the source
            │ pair for AER_CORRECTABLE, else from the         │
            │ uncorrectable pair?                             ├─ no ────▶ not the source
            └─────────────────────────────────────────────────┘
```

Every function the walk visits passes through these tests, and those that pass fill the record's slots, which the processing reads next.

### aer_process_err_devices prints every function before handling any

Handling an uncorrectable error can reset the link below the root, as the reset callback shows later. If the first function were handled before the second was read, that reset could come before the second function's registers are read, and the comment of [`aer_process_err_devices()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1352) names that risk as losing records by reset. The function therefore makes two passes over the record's functions.

```c
/* drivers/pci/pcie/aer.c:1352 */
static inline void aer_process_err_devices(struct aer_err_info *e_info)
{
	int i;

	/* Report all before handling them, to not lose records by reset etc. */
	for (i = 0; i < e_info->error_dev_num && e_info->dev[i]; i++) {
		if (aer_get_device_error_info(e_info, i))
			aer_print_error(e_info, i);
	}
	for (i = 0; i < e_info->error_dev_num && e_info->dev[i]; i++) {
		if (aer_get_device_error_info(e_info, i))
			handle_error_source(e_info->dev[i], e_info);
	}
}
```

The first pass reads each function with [`aer_get_device_error_info()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1293) and prints it with [`aer_print_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L865). The second pass reads it again and hands it to [`handle_error_source()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1196), so the handling acts on the status as it stands after every function was printed. A function whose read reports nothing is skipped in either pass, and both passes stop at the count or at the first empty slot. [`aer_print_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L865) counts and traces each function before its ratelimit flag decides about the lines.

```c
/* drivers/pci/pcie/aer.c:865 */
void aer_print_error(struct aer_err_info *info, int i)
{
	struct pci_dev *dev;
	int layer, agent, id;
	const char *level = info->level;
	const char *bus_type = aer_err_bus(info);

	if (WARN_ON_ONCE(i >= AER_MAX_MULTI_ERR_DEVICES))
		return;

	dev = info->dev[i];
	id = pci_dev_id(dev);

	pci_dev_aer_stats_incr(dev, info);
	trace_aer_event(pci_name(dev), (info->status & ~info->mask),
			info->severity, info->tlp_header_valid, &info->tlp, bus_type);

	if (!info->ratelimit_print[i])
		return;

	if (!info->status) {
		pci_err(dev, "%s Bus Error: severity=%s, type=Inaccessible, (Unregistered Agent ID)\n",
			bus_type, aer_error_severity_string[info->severity]);
		goto out;
	}
```

The per-function counters of [`pci_dev_aer_stats_incr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L747) and the `ras:aer_event` tracepoint see every function of the first pass, and only the lines depend on [`ratelimit_print`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L835). A function read with status 0 is reported as an inaccessible agent, the case the register reads produce for a fatal error below a link that cannot be trusted. The other lines it prints are listed with the messages near the end of the page.

So far, a message has become a record of one class, the search has filled the record with the reporting functions and their references, and the first pass has read and printed each of them; the second pass reads each again before handing it on.

### aer_get_device_error_info reads the function's own registers

The record names the reporting functions but holds no register values for them, and each function's own AER registers say what it logged. [`aer_get_device_error_info()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1293) reads them into the shared record, one function at a time, which is why it resets the record's register members on every call. Which registers it reads depends on the record's class and on the function's type, as the table sets out.

| record severity | reporting function | registers read | return value |
|---|---|---|---|
| any | without the capability, [`aer_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370) 0 | none | 0 |
| [`AER_CORRECTABLE`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L16) | any type | [`PCI_ERR_COR_STATUS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L800) and [`PCI_ERR_COR_MASK`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L809) | 1 when a bit is set and unmasked, else 0 |
| [`AER_NONFATAL`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L14) | any type | [`PCI_ERR_UNCOR_STATUS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L772), [`PCI_ERR_UNCOR_MASK`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L796), [`PCI_ERR_CAP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L811) and a logged header | 1 when a bit is set and unmasked, else 0 |
| [`AER_FATAL`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L15) | [`PCI_EXP_TYPE_ROOT_PORT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L488), [`PCI_EXP_TYPE_RC_EC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L494) or [`PCI_EXP_TYPE_DOWNSTREAM`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L490) | [`PCI_ERR_UNCOR_STATUS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L772), [`PCI_ERR_UNCOR_MASK`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L796), [`PCI_ERR_CAP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L811) and a logged header | 1 when a bit is set and unmasked, else 0 |
| [`AER_FATAL`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L15) | any other type | none, [`status`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L851) stays 0 | 1 |

The function is read in two pieces.

| piece | lines | stage |
|---|---|---|
| Ⓐ | aer.c:1293-1313 | selects the function and resets the record's register members |
| Ⓑ | aer.c:1314-1350 | reads the registers by class and type |

Ⓐ The first piece of [`aer_get_device_error_info()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1293), with its kerneldoc, selects the function and clears what the previous function left in the record.

```c
/* drivers/pci/pcie/aer.c:1284 */
/**
 * aer_get_device_error_info - read error status from dev and store it to info
 * @info: pointer to structure to store the error record
 * @i: index into info->dev[]
 *
 * Return: 1 on success, 0 on error.
 *
 * Note that @info is reused among all error devices. Clear fields properly.
 */
int aer_get_device_error_info(struct aer_err_info *info, int i)
{
	struct pci_dev *dev;
	int type, aer;
	u32 aercc;

	if (i >= AER_MAX_MULTI_ERR_DEVICES)
		return 0;

	dev = info->dev[i];
	aer = dev->aer_cap;
	type = pci_pcie_type(dev);

	/* Must reset in this function */
	info->status = 0;
	info->tlp_header_valid = 0;
	info->is_cxl = pcie_is_cxl(dev);

	/* The device might not support AER */
	if (!aer)
		return 0;
```

An index past the arrays returns 0, and so does a function without the capability, after [`status`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L851) and [`tlp_header_valid`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L849) are cleared and [`is_cxl`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L848) is set for the printers. Ⓑ The second piece of [`aer_get_device_error_info()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1293) reads the registers.

```c
/* drivers/pci/pcie/aer.c:1314 */

	if (info->severity == AER_CORRECTABLE) {
		pci_read_config_dword(dev, aer + PCI_ERR_COR_STATUS,
			&info->status);
		pci_read_config_dword(dev, aer + PCI_ERR_COR_MASK,
			&info->mask);
		if (!(info->status & ~info->mask))
			return 0;
	} else if (type == PCI_EXP_TYPE_ROOT_PORT ||
		   type == PCI_EXP_TYPE_RC_EC ||
		   type == PCI_EXP_TYPE_DOWNSTREAM ||
		   info->severity == AER_NONFATAL) {

		/* Link is still healthy for IO reads */
		pci_read_config_dword(dev, aer + PCI_ERR_UNCOR_STATUS,
			&info->status);
		pci_read_config_dword(dev, aer + PCI_ERR_UNCOR_MASK,
			&info->mask);
		if (!(info->status & ~info->mask))
			return 0;

		/* Get First Error Pointer */
		pci_read_config_dword(dev, aer + PCI_ERR_CAP, &aercc);
		info->first_error = PCI_ERR_CAP_FEP(aercc);

		if (tlp_header_logged(info->status, aercc)) {
			info->tlp_header_valid = 1;
			pcie_read_tlp_log(dev, aer + PCI_ERR_HEADER_LOG,
					  aer + PCI_ERR_PREFIX_LOG,
					  aer_tlp_log_len(dev, aercc),
					  aercc & PCI_ERR_CAP_TLP_LOG_FLIT,
					  &info->tlp);
		}
	}

	return 1;
}
```

A correctable record reads the correctable pair and returns 0 when every set bit is masked. An uncorrectable record reads the uncorrectable pair when the comment's condition holds, that the link is still healthy for reads: the error is non-fatal, or the function is on the root's side of a link, a Root Port, an RCEC or a Downstream Port. For a fatal error at any other function the piece reads nothing and returns 1 with [`status`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L851) 0, which the printer reports as an inaccessible agent. When the uncorrectable read happens, the First Error Pointer is stored and a logged header is read into [`tlp`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L853). [`tlp_header_logged()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L815) decides whether a header was logged.

```c
/* drivers/pci/pcie/aer.c:815 */
static bool tlp_header_logged(u32 status, u32 capctl)
{
	/* Errors for which a header is always logged (PCIe r7.0 sec 6.2.7) */
	if (status & AER_LOG_TLP_MASKS)
		return true;

	/* Completion Timeout header is only logged on capable devices */
	if (status & PCI_ERR_UNC_COMP_TIME &&
	    capctl & PCI_ERR_CAP_COMP_TIME_LOG)
		return true;

	return false;
}
```

The errors of [`AER_LOG_TLP_MASKS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L99) log a header every time, citing the specification section listed above, and a completion timeout logs one only on a function that sets the capability bit for it. The mask is a macro of aer.c.

```c
/* drivers/pci/pcie/aer.c:99 */
#define AER_LOG_TLP_MASKS		(PCI_ERR_UNC_POISON_TLP|	\
					PCI_ERR_UNC_POISON_BLK |	\
					PCI_ERR_UNC_ECRC|		\
					PCI_ERR_UNC_UNSUP|		\
					PCI_ERR_UNC_COMP_ABORT|		\
					PCI_ERR_UNC_UNX_COMP|		\
					PCI_ERR_UNC_ACSV |		\
					PCI_ERR_UNC_MCBTLP |		\
					PCI_ERR_UNC_ATOMEG |		\
					PCI_ERR_UNC_DMWR_BLK |		\
					PCI_ERR_UNC_XLAT_BLK |		\
					PCI_ERR_UNC_TLPPRE |		\
					PCI_ERR_UNC_MALF_TLP |		\
					PCI_ERR_UNC_IDE_CHECK |		\
					PCI_ERR_UNC_MISR_IDE |		\
					PCI_ERR_UNC_PCRC_CHECK)
```

Poisoned TLPs, ECRC errors, unsupported requests, completer aborts, unexpected completions, malformed TLPs and several egress-blocked errors are among its bits. The length to read comes from [`aer_tlp_log_len()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L23) of drivers/pci/pcie/tlp.c.

```c
/* drivers/pci/pcie/tlp.c:16 */
/**
 * aer_tlp_log_len - Calculate AER Capability TLP Header/Prefix Log length
 * @dev: PCIe device
 * @aercc: AER Capabilities and Control register value
 *
 * Return: TLP Header/Prefix Log length
 */
unsigned int aer_tlp_log_len(struct pci_dev *dev, u32 aercc)
{
	if (aercc & PCI_ERR_CAP_TLP_LOG_FLIT)
		return FIELD_GET(PCI_ERR_CAP_TLP_LOG_SIZE, aercc);

	return PCIE_STD_NUM_TLP_HEADERLOG +
	       ((aercc & PCI_ERR_CAP_PREFIX_LOG_PRESENT) ?
		dev->eetlp_prefix_max : 0);
}
```

In Flit Mode the register states the logged size. Otherwise the length is the standard Header Log, [`PCIE_STD_NUM_TLP_HEADERLOG`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L23) dwords, plus [`eetlp_prefix_max`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L443) dwords when a prefix log is present. The DPC driver uses the same read, with [`CONFIG_PCIE_DPC`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L121) set as this page assumes: when a containment event was triggered by an uncorrectable error, [`dpc_process_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L264) fills its own record for slot 0 and prints it.

```c
/* drivers/pci/pcie/dpc.c:264 */
void dpc_process_error(struct pci_dev *pdev)
{
	u16 cap = pdev->dpc_cap, status, source, reason, ext_reason;
	struct aer_err_info info = {};

	pci_read_config_word(pdev, cap + PCI_EXP_DPC_STATUS, &status);

	reason = status & PCI_EXP_DPC_STATUS_TRIGGER_RSN;

	switch (reason) {
	case PCI_EXP_DPC_STATUS_TRIGGER_RSN_UNCOR:
		pci_warn(pdev, "containment event, status:%#06x: unmasked uncorrectable error detected\n",
			 status);
		if (dpc_get_aer_uncorrect_severity(pdev, &info) &&
		    aer_get_device_error_info(&info, 0)) {
			aer_print_error(&info, 0);
			pci_aer_clear_nonfatal_status(pdev);
			pci_aer_clear_fatal_status(pdev);
		}
		break;
```

The DPC record names the port itself in slot 0, and the read and the print are the functions the AER service uses. The DPC driver then clears the port's uncorrectable status itself, and nothing of that path goes through the queue or the search of this page. After the second read in [`aer_process_err_devices()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1352), the record holds the current function's class, status, mask and header, and the function is handed to its handling.

### handle_error_source routes each function by severity

A correctable error needs no recovery, according to the comment in [`pci_aer_handle_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1170), and the kernel clears it and tells the driver. An uncorrectable error may have left the function or its link unusable, so the PCI core's recovery asks every driver below the affected bridge what to do. [`handle_error_source()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1196) is the per-function entry for both.

```c
/* drivers/pci/pcie/aer.c:1196 */
static void handle_error_source(struct pci_dev *dev, struct aer_err_info *info)
{
	cxl_rch_handle_error(dev, info);
	pci_aer_handle_error(dev, info);
	pci_dev_put(dev);
}
```

The first call belongs to the bus topic the probe subsection set aside and is an empty inline with [`CONFIG_CXL_RAS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/cxl/Kconfig#L237) unset. The handling itself is [`pci_aer_handle_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1170), and the reference the search took on the function is dropped last.

```c
/* drivers/pci/pcie/aer.c:1163 */
/**
 * pci_aer_handle_error - handle logging error into an event log
 * @dev: pointer to pci_dev data structure of error source device
 * @info: comprehensive error information
 *
 * Invoked when an error being detected by Root Port.
 */
static void pci_aer_handle_error(struct pci_dev *dev, struct aer_err_info *info)
{
	int aer = dev->aer_cap;

	if (info->severity == AER_CORRECTABLE) {
		/*
		 * Correctable error does not need software intervention.
		 * No need to go through error recovery process.
		 */
		if (aer)
			pci_write_config_dword(dev, aer + PCI_ERR_COR_STATUS,
					info->status);
		if (pcie_aer_is_native(dev)) {
			struct pci_driver *pdrv = dev->driver;

			if (pdrv && pdrv->err_handler &&
			    pdrv->err_handler->cor_error_detected)
				pdrv->err_handler->cor_error_detected(dev);
			pcie_clear_device_status(dev);
		}
	} else if (info->severity == AER_NONFATAL)
		pcie_do_recovery(dev, pci_channel_io_normal, aer_root_reset);
	else if (info->severity == AER_FATAL)
		pcie_do_recovery(dev, pci_channel_io_frozen, aer_root_reset);
}
```

For [`AER_CORRECTABLE`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L16), the function's correctable status is cleared by writing back the bits the record read, so a bit that arrived after the read stays set. Where [`pcie_aer_is_native()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L242) grants the operating system AER for the function, the driver's [`cor_error_detected`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L960) runs when the driver has one, and the function's Device Status is cleared. [`AER_NONFATAL`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L14) and [`AER_FATAL`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L15) both start [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210), with [`pci_channel_io_normal`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L210) for a non-fatal error and [`pci_channel_io_frozen`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L213) for a fatal one, and with [`aer_root_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1667) as the reset callback. [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) belongs to drivers/pci/pcie/err.c; read the stages that choose the bridge, ask the drivers and call the reset callback.

```c
/* drivers/pci/pcie/err.c:210 */
pci_ers_result_t pcie_do_recovery(struct pci_dev *dev,
		pci_channel_state_t state,
		pci_ers_result_t (*reset_subordinates)(struct pci_dev *pdev))
{
	int type = pci_pcie_type(dev);
	struct pci_dev *bridge;
	pci_ers_result_t status = PCI_ERS_RESULT_CAN_RECOVER;
	struct pci_host_bridge *host = pci_find_host_bridge(dev->bus);
	... /* 10 lines, to :228 */
	if (type == PCI_EXP_TYPE_ROOT_PORT ||
	    type == PCI_EXP_TYPE_DOWNSTREAM ||
	    type == PCI_EXP_TYPE_RC_EC ||
	    type == PCI_EXP_TYPE_RC_END)
		bridge = dev;
	else
		bridge = pci_upstream_bridge(dev);

	pci_walk_bridge(bridge, pci_pm_runtime_get_sync, NULL);

	pci_dbg(bridge, "broadcast error_detected message\n");
	if (state == pci_channel_io_frozen)
		pci_walk_bridge(bridge, report_frozen_detected, &status);
	else
		pci_walk_bridge(bridge, report_normal_detected, &status);

	if (status == PCI_ERS_RESULT_CAN_RECOVER) {
		status = PCI_ERS_RESULT_RECOVERED;
		pci_dbg(bridge, "broadcast mmio_enabled message\n");
		pci_walk_bridge(bridge, report_mmio_enabled, &status);
	}

	if (status == PCI_ERS_RESULT_NEED_RESET ||
	    state == pci_channel_io_frozen) {
		if (reset_subordinates(bridge) != PCI_ERS_RESULT_RECOVERED) {
			pci_warn(bridge, "subordinate device reset failed\n");
			goto failed;
		}
	}

	if (status == PCI_ERS_RESULT_NEED_RESET) {
		/*
		 * TODO: Should call platform-specific
		 * functions to reset slot before calling
		 * drivers' slot_reset callbacks?
		 */
		status = PCI_ERS_RESULT_RECOVERED;
		pci_dbg(bridge, "broadcast slot_reset message\n");
		pci_walk_bridge(bridge, report_slot_reset, &status);
	}

	if (status != PCI_ERS_RESULT_RECOVERED)
		goto failed;

	pci_dbg(bridge, "broadcast resume message\n");
	pci_walk_bridge(bridge, report_resume, &status);
```

The bridge is the function itself for a Root Port, a Downstream Port, an RCEC or an integrated endpoint, and the upstream bridge for any other function. Every driver below the bridge gets [`error_detected`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L943), and [`mmio_enabled`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L947) follows when all can recover. The reset callback runs when a driver asked for a reset or the channel is frozen, so a fatal error reported by this service reaches [`aer_root_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1667) every time, and [`slot_reset`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L950) and [`resume`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L957) follow a successful reset. The four [`pci_dbg()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2896) lines are the dynamic-debug sites of the recovery, and the last subsections list them with the other messages. The swimlane shows who acts on one function of each class.

```text
    Severity decides who acts on one reporting function after it is logged
    ──────────────────────────────────────────────────────────────────────

    time ↓
    AER thread, per function    recovery core               drivers under the bridge   the root and its link
    ─────────────────────────┼───────────────────────────┼──────────────────────────┼──────────────────────────────
    AER_CORRECTABLE:         ╎                           ╎                          ╎
    COR status cleared;      ╎                           ╎                          ╎
    if native, driver ────────────────────────────────────▶ cor_error_detected,     ╎
    told, Device Status      ╎                           ╎  when it has one         ╎
    cleared                  ╎                           ╎                          ╎
                             ╎                           ╎                          ╎
    AER_NONFATAL: normal     ╎                           ╎                          ╎
    AER_FATAL: frozen ────────▶ bridge chosen            ╎                          ╎
                             ╎  error_detected ───────────▶ each driver votes       ╎
                             ╎  mmio_enabled if all      ╎                          ╎
                             ╎  can recover ──────────────▶ drivers resume MMIO     ╎
                             ╎                           ╎                          ╎
                             ╎  NEED_RESET or frozen:    ╎                          ╎
                             ╎  reset callback ──────────────────────────────────────▶ aer_root_reset:
                             ╎                           ╎                          ╎  IRQ off, link or FLR
                             ╎                           ╎                          ╎  reset, status cleared,
                             ╎  slot_reset, resume ───────▶ drivers restart         ╎  IRQ on
                             ╎                           ╎                          ╎
    next function ◀──────────── recovered or failed      ╎                          ╎
```

An uncorrectable error thus ends in the reset callback whenever the drivers need a reset or the error is fatal, and that callback is the service's own.

### aer_root_reset resets below the root with its interrupt disabled

A reset below a root makes functions drop off and come back, and the root can latch messages while it happens, which the service must not take for new errors. [`aer_root_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1667) therefore finds the root of the function, disables the root's AER interrupt, resets, clears the root's status and enables the interrupt again. It is read in two pieces.

| piece | lines | stage |
|---|---|---|
| ❶ | aer.c:1667-1694 | finds the root and disables its interrupt |
| ❷ | aer.c:1695-1717 | resets, clears the root's status and enables the interrupt |

❶ The first piece of [`aer_root_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1667), with its kerneldoc, chooses the root and disables it.

```c
/* drivers/pci/pcie/aer.c:1661 */
/**
 * aer_root_reset - reset Root Port hierarchy, RCEC, or RCiEP
 * @dev: pointer to Root Port, RCEC, or RCiEP
 *
 * Invoked by Port Bus driver when performing reset.
 */
static pci_ers_result_t aer_root_reset(struct pci_dev *dev)
{
	int type = pci_pcie_type(dev);
	struct pci_dev *root;
	int aer;
	struct pci_host_bridge *host = pci_find_host_bridge(dev->bus);
	u32 reg32;
	int rc;

	/*
	 * Only Root Ports and RCECs have AER Root Command and Root Status
	 * registers.  If "dev" is an RCiEP, the relevant registers are in
	 * the RCEC.
	 */
	if (type == PCI_EXP_TYPE_RC_END)
		root = dev->rcec;
	else
		root = pcie_find_root_port(dev);

	/*
	 * If the platform retained control of AER, an RCiEP may not have
	 * an RCEC visible to us, so dev->rcec ("root") may be NULL.  In
	 * that case, firmware is responsible for these registers.
	 */
	aer = root ? root->aer_cap : 0;

	if ((host->native_aer || pcie_ports_native) && aer)
		aer_disable_irq(root);
```

The function passed in is the bridge that [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) chose. For an integrated endpoint the root is its RCEC in [`rcec`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L375), and for anything else it is the Root Port above it, from [`pcie_find_root_port()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2690). When the operating system owns AER and the root has the capability, the root's interrupt is disabled before anything else happens; otherwise, as the comment says, firmware is responsible for the root's registers. [`pcie_find_root_port()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2690) climbs upstream bridges until it meets a Root Port.

```c
/* include/linux/pci.h:2683 */
/**
 * pcie_find_root_port - Get the PCIe root port device
 * @dev: PCI device
 *
 * Traverse up the parent chain and return the PCIe Root Port PCI Device
 * for a given PCI/PCIe Device.
 */
static inline struct pci_dev *pcie_find_root_port(struct pci_dev *dev)
{
	while (dev) {
		if (pci_is_pcie(dev) &&
		    pci_pcie_type(dev) == PCI_EXP_TYPE_ROOT_PORT)
			return dev;
		dev = pci_upstream_bridge(dev);
	}

	return NULL;
}
```

A function with no Root Port above it yields NULL, which the reset callback treats as a root with no registers to touch. ❷ The second piece of [`aer_root_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1667) resets and restores.

```c
/* drivers/pci/pcie/aer.c:1695 */

	if (type == PCI_EXP_TYPE_RC_EC || type == PCI_EXP_TYPE_RC_END) {
		rc = pcie_reset_flr(dev, PCI_RESET_DO_RESET);
		if (!rc)
			pci_info(dev, "has been reset\n");
		else
			pci_info(dev, "not reset (no FLR support: %d)\n", rc);
	} else {
		rc = pci_bus_error_reset(dev);
		pci_info(dev, "%s Port link has been reset (%d)\n",
			pci_is_root_bus(dev->bus) ? "Root" : "Downstream", rc);
	}

	if ((host->native_aer || pcie_ports_native) && aer) {
		/* Clear Root Error Status */
		pci_read_config_dword(root, aer + PCI_ERR_ROOT_STATUS, &reg32);
		pci_write_config_dword(root, aer + PCI_ERR_ROOT_STATUS, reg32);

		aer_enable_irq(root);
	}

	return rc ? PCI_ERS_RESULT_DISCONNECT : PCI_ERS_RESULT_RECOVERED;
}
```

An RCEC or an integrated endpoint is reset by a Function Level Reset through [`pcie_reset_flr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4402), and a port by [`pci_bus_error_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L5686) of the bus below it, and an info line records the outcome either way. Under the same ownership test the root's status is cleared and its enables are set again, and the return value tells the recovery whether the reset succeeded. [`pcie_reset_flr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4402) refuses a function that cannot do FLR.

```c
/* drivers/pci/pci.c:4395 */
/**
 * pcie_reset_flr - initiate a PCIe function level reset
 * @dev: device to reset
 * @probe: if true, return 0 if device can be reset this way
 *
 * Initiate a function level reset on @dev.
 */
int pcie_reset_flr(struct pci_dev *dev, bool probe)
{
	if (dev->dev_flags & PCI_DEV_FLAGS_NO_FLR_RESET)
		return -ENOTTY;

	if (!(dev->devcap & PCI_EXP_DEVCAP_FLR))
		return -ENOTTY;

	if (probe)
		return 0;

	return pcie_flr(dev);
}
```

A function flagged against FLR, or one whose cached Device Capabilities lack the FLR bit, gets -ENOTTY, which the callback logs as not reset and turns into [`PCI_ERS_RESULT_DISCONNECT`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L931). [`pci_bus_error_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L5686) resets the bridge's secondary side without restoring state.

```c
/* drivers/pci/pci.c:5682 */
/**
 * pci_bus_error_reset - reset the bridge's subordinate bus
 * @bridge: The parent device that connects to the bus to reset
 */
int pci_bus_error_reset(struct pci_dev *bridge)
{
	return pci_reset_bridge(bridge, PCI_RESET_NO_RESTORE);
}
```

[`pci_reset_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L5645) chooses between a slot reset and a secondary bus reset, a decision of the PCI core's reset code that this page does not follow. The spans show what holds for the root during one reset.

```text
    What holds while aer_root_reset() resets below the root
    ───────────────────────────────────────────────────────

    time ────────────────────────────────────────────────────────────────────────────────────────────────▶
    Root Error Command enables off    ├─────────────────────────────────────────────────────────────┤
    FLR, or reset below the port          ├───────────────────────────────────┤
    Root Error Status cleared                                                     ├─────────────┤
                                      ╎                                                             ╎
    the root's AER interrupt      on  ╎ off                                                         ╎ on
    Root Error Status        as is    ╎                                             written back    ╎ clear

    the bracket applies when native_aer or pcie_ports=native holds and the root has aer_cap;
    the root is the Root Port above the function, or the RCEC for an RCiEP
```

The same callback serves the firmware-first path, where firmware reports an error through ACPI APEI and the root's interrupt plays no part. That path is built only with [`CONFIG_ACPI_APEI_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Kconfig#L37), which depends on [`CONFIG_ACPI_APEI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Kconfig#L8), and this page assumes both unset, so the code below is not built. The block opens with its gate and the ring that carries the reports.

```c
/* drivers/pci/pcie/aer.c:1203 */
#ifdef CONFIG_ACPI_APEI_PCIEAER

#define AER_RECOVER_RING_SIZE		16

struct aer_recover_entry {
	u8	bus;
	u8	devfn;
	u16	domain;
	int	severity;
	struct aer_capability_regs *regs;
};

static DEFINE_KFIFO(aer_recover_ring, struct aer_recover_entry,
		    AER_RECOVER_RING_SIZE);
```

A [`struct aer_recover_entry`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1207) names the function by domain, bus and devfn and carries the severity and the registers firmware captured, and the ring holds [`AER_RECOVER_RING_SIZE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1205) of them. [`aer_recover_queue()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1263) puts a firmware report into that ring and schedules a work item.

```c
/* drivers/pci/pcie/aer.c:1255 */
/*
 * Mutual exclusion for writers of aer_recover_ring, reader side don't
 * need lock, because there is only one reader and lock is not needed
 * between reader and writer.
 */
static DEFINE_SPINLOCK(aer_recover_ring_lock);
static DECLARE_WORK(aer_recover_work, aer_recover_work_func);

void aer_recover_queue(int domain, unsigned int bus, unsigned int devfn,
		       int severity, struct aer_capability_regs *aer_regs)
{
	struct aer_recover_entry entry = {
		.bus		= bus,
		.devfn		= devfn,
		.domain		= domain,
		.severity	= severity,
		.regs		= aer_regs,
	};

	if (kfifo_in_spinlocked(&aer_recover_ring, &entry, 1,
				 &aer_recover_ring_lock))
		schedule_work(&aer_recover_work);
	else
		pr_err("buffer overflow in recovery for %04x:%02x:%02x.%x\n",
		       domain, bus, PCI_SLOT(devfn), PCI_FUNC(devfn));
}
EXPORT_SYMBOL_GPL(aer_recover_queue);
```

Writers take the spinlock, and a full ring prints an overflow message and drops the report. [`aer_recover_work_func()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1218) takes the reports in process context and starts the same recovery with the same callback.

```c
/* drivers/pci/pcie/aer.c:1218 */
static void aer_recover_work_func(struct work_struct *work)
{
	struct aer_recover_entry entry;
	struct pci_dev *pdev;

	while (kfifo_get(&aer_recover_ring, &entry)) {
		pdev = pci_get_domain_bus_and_slot(entry.domain, entry.bus,
						   entry.devfn);
		if (!pdev) {
			pr_err_ratelimited("%04x:%02x:%02x.%x: no pci_dev found\n",
					   entry.domain, entry.bus,
					   PCI_SLOT(entry.devfn),
					   PCI_FUNC(entry.devfn));
			continue;
		}
		pci_print_aer(pdev, entry.severity, entry.regs);

		/*
		 * Memory for aer_capability_regs(entry.regs) is being
		 * allocated from the ghes_estatus_pool to protect it from
		 * overwriting when multiple sections are present in the
		 * error status. Thus free the same after processing the
		 * data.
		 */
		ghes_estatus_pool_region_free((unsigned long)entry.regs,
					    sizeof(struct aer_capability_regs));

		if (entry.severity == AER_NONFATAL)
			pcie_do_recovery(pdev, pci_channel_io_normal,
					 aer_root_reset);
		else if (entry.severity == AER_FATAL)
			pcie_do_recovery(pdev, pci_channel_io_frozen,
					 aer_root_reset);
		pci_dev_put(pdev);
	}
}
```

The two calls of [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) mirror those of [`pci_aer_handle_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1170), so with [`CONFIG_ACPI_APEI_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Kconfig#L37) set, [`aer_root_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1667) runs for errors firmware reported as well. After a successful reset the root is enabled again with clean status, and the recovery goes on with the drivers.

### Suspend, resume and unbind disable the root's interrupt

Outside error handling, three events change whether the root may interrupt: system sleep, resume and the unbinding of the service driver. commit [5afc2f763edc](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=5afc2f763edc5daae4722ee46fea4e627d01fa90) ("PCI/AER: Disable AER service on suspend") gives the reason for the sleep case: on a link powered off for suspend, electrical noise can cause errors, and an AER interrupt that shares its vector with PME then wakes the system. [`aer_disable_rootport()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1575) is the step both sleep and unbind use.

```c
/* drivers/pci/pcie/aer.c:1569 */
/**
 * aer_disable_rootport - disable Root Port's interrupts when receiving messages
 * @rpc: pointer to a Root Port data structure
 *
 * Invoked when PCIe bus unloads AER service driver.
 */
static void aer_disable_rootport(struct aer_rpc *rpc)
{
	struct pci_dev *pdev = rpc->rpd;
	int aer = pdev->aer_cap;
	u32 reg32;

	aer_disable_irq(pdev);

	/* Clear Root's error status reg */
	pci_read_config_dword(pdev, aer + PCI_ERR_ROOT_STATUS, &reg32);
	pci_write_config_dword(pdev, aer + PCI_ERR_ROOT_STATUS, reg32);
}
```

The enables are cleared first, then the root's status is written back, so the root leaves the service with no latched message bits. The sleep callbacks reach the service through the port driver's power-management operations, which exist with [`CONFIG_PM`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L217) and call each bound service of the port.

```c
/* drivers/pci/pcie/portdrv.c:656 */
static const struct dev_pm_ops pcie_portdrv_pm_ops = {
	.suspend	= pcie_port_device_suspend,
	.resume_noirq	= pcie_port_device_resume_noirq,
	.resume		= pcie_port_device_resume,
	.freeze		= pcie_port_device_suspend,
	.thaw		= pcie_port_device_resume,
	.poweroff	= pcie_port_device_suspend,
	.restore_noirq	= pcie_port_device_resume_noirq,
	.restore	= pcie_port_device_resume,
	.runtime_suspend = pcie_port_runtime_suspend,
	.runtime_resume	= pcie_port_device_runtime_resume,
	.runtime_idle	= pcie_port_runtime_idle,
};
```

Suspend, freeze and poweroff run [`pcie_port_device_suspend()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L405), and resume, thaw and restore run [`pcie_port_device_resume()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L421). Both visit the port's service devices with an offset into the service driver.

```c
/* drivers/pci/pcie/portdrv.c:400 */
#ifdef CONFIG_PM
/**
 * pcie_port_device_suspend - suspend port services associated with a PCIe port
 * @dev: PCI Express port to handle
 */
static int pcie_port_device_suspend(struct device *dev)
{
	size_t off = offsetof(struct pcie_port_service_driver, suspend);
	return device_for_each_child(dev, &off, pcie_port_device_iter);
}

static int pcie_port_device_resume_noirq(struct device *dev)
{
	size_t off = offsetof(struct pcie_port_service_driver, resume_noirq);
	return device_for_each_child(dev, &off, pcie_port_device_iter);
}

/**
 * pcie_port_device_resume - resume port services associated with a PCIe port
 * @dev: PCI Express port to handle
 */
static int pcie_port_device_resume(struct device *dev)
{
	size_t off = offsetof(struct pcie_port_service_driver, resume);
	return device_for_each_child(dev, &off, pcie_port_device_iter);
}
```

[`pcie_port_device_iter()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L385) calls the callback at that offset in each bound service driver of the port.

```c
/* drivers/pci/pcie/portdrv.c:383 */
typedef int (*pcie_callback_t)(struct pcie_device *);

static int pcie_port_device_iter(struct device *dev, void *data)
{
	struct pcie_port_service_driver *service_driver;
	size_t offset = *(size_t *)data;
	pcie_callback_t cb;

	if ((dev->bus == &pcie_port_bus_type) && dev->driver) {
		service_driver = to_service_driver(dev->driver);
		cb = *(pcie_callback_t *)((void *)service_driver + offset);
		if (cb)
			return cb(to_pcie_device(dev));
	}
	return 0;
}
```

So [`suspend`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L82) of [`aerdriver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1719) runs on the AER service device when the port suspends, and [`resume`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L84) when it resumes. The two AER callbacks follow.

```c
/* drivers/pci/pcie/aer.c:1645 */
static int aer_suspend(struct pcie_device *dev)
{
	struct aer_rpc *rpc = get_service_data(dev);

	aer_disable_rootport(rpc);
	return 0;
}

static int aer_resume(struct pcie_device *dev)
{
	struct aer_rpc *rpc = get_service_data(dev);

	aer_enable_rootport(rpc);
	return 0;
}
```

[`aer_suspend()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1645) disables the root through [`aer_disable_rootport()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1575), and [`aer_resume()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1653) runs the whole of [`aer_enable_rootport()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1533) again. Errors latched during the sleep are therefore cleared before the enables return, on the root and, when it latched any, on the functions below it. Unbinding goes through the bus's remove callback, which the driver core calls when the port driver unregisters a service device.

```c
/* drivers/pci/pcie/portdrv.c:553 */
/**
 * pcie_port_bus_remove - detach driver from given PCI Express port service
 * @dev: PCI Express port service device to handle
 *
 * If PCI Express port service driver is registered with
 * pcie_port_service_register(), this function will be called by the driver core
 * when device_unregister() is called for the port service device associated
 * with the driver.
 */
static void pcie_port_bus_remove(struct device *dev)
{
	struct pcie_device *pciedev;
	struct pcie_port_service_driver *driver;

	pciedev = to_pcie_device(dev);
	driver = to_service_driver(dev->driver);
	if (driver && driver->remove)
		driver->remove(pciedev);

	put_device(dev);
}
```

The bus callback runs the service's remove callback and drops the reference its probe took. For AER the remove callback is [`aer_remove()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1594), with its kerneldoc.

```c
/* drivers/pci/pcie/aer.c:1588 */
/**
 * aer_remove - clean up resources
 * @dev: pointer to the pcie_dev data structure
 *
 * Invoked when PCI Express bus unloads or AER probe fails.
 */
static void aer_remove(struct pcie_device *dev)
{
	struct aer_rpc *rpc = get_service_data(dev);

	aer_disable_rootport(rpc);
}
```

The remove callback touches only the enables and the status, and the driver core frees the object and the interrupt handler after it. The kerneldoc also names a failed probe, but at v7.2 a failed [`aer_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1607) returns its error through [`pcie_port_bus_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L534) without a call to the remove callback. [`__device_release_driver()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/dd.c#L1318) of the driver core orders the remove and the release of managed resources.

```c
/* drivers/base/dd.c:1318 */
static void __device_release_driver(struct device *dev, struct device *parent)
{
	struct device_driver *drv;

	drv = dev->driver;
	if (drv) {
		... /* 19 lines, to :1343 */
		driver_sysfs_remove(dev);

		bus_notify(dev, BUS_NOTIFY_UNBIND_DRIVER);

		pm_runtime_put_sync(dev);

		device_remove(dev);

		if (dev->bus && dev->bus->dma_cleanup)
			dev->bus->dma_cleanup(dev);

		device_unbind_cleanup(dev);
		device_links_driver_cleanup(dev);
```

[`device_remove()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/dd.c#L610) runs the bus's remove callback, and [`device_unbind_cleanup()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/dd.c#L593) then releases the device's managed resources, as the two functions show.

```c
/* drivers/base/dd.c:593 */
static void device_unbind_cleanup(struct device *dev)
{
	if (dev->driver->p_cb.post_unbind_rust)
		dev->driver->p_cb.post_unbind_rust(dev);
	devres_release_all(dev);
	arch_teardown_dma_ops(dev);
	kfree(dev->dma_range_map);
	dev->dma_range_map = NULL;
	device_set_driver(dev, NULL);
	dev_set_drvdata(dev, NULL);
	dev_pm_domain_detach(dev, dev->power.detach_power_off);
	if (dev->pm_domain && dev->pm_domain->dismiss)
		dev->pm_domain->dismiss(dev);
	pm_runtime_reinit(dev);
	dev_pm_set_driver_flags(dev, 0);
}

static void device_remove(struct device *dev)
{
	device_remove_file(dev, &dev_attr_state_synced);
	device_remove_groups(dev, dev->driver->dev_groups);

	if (dev->bus && dev->bus->remove)
		dev->bus->remove(dev);
	else if (dev->driver->remove)
		dev->driver->remove(dev);
}
```

The handler installed by [`devm_request_threaded_irq()`](https://elixir.bootlin.com/linux/v7.2/source/kernel/irq/devres.c#L100) and the object from [`devm_kzalloc()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/device/devres.h#L48) are freed in that release, after the root's enables are cleared. The figure collects the transitions of the root's enables across the page.

```text
    The root's AER interrupt enables across probe, recovery, sleep and unbind
    ─────────────────────────────────────────────────────────────────────────

    ┌───────────────────┐   ➊ probe       ┌─────────────────────────┐  ➋ reset begins   ┌───────────────────────┐
    │ no AER service    ├────────────────▶│ enabled                 ├──────────────────▶│ disabled around       │
    │ device bound      │                 │ Root Error Command      │                   │ the reset             │
    └───────────────────┘                 │ COR, NONFATAL, FATAL    │◀──────────────────┤                       │
                                          └─────┬───────────────────┘  ➌ reset ends     └───────────────────────┘
                                                │             ▲
                                  ➍ suspend     │             │ ➎ resume
                                  ➏ remove      │             │
                                                ▼             │
                                          ┌───────────────────┴─────┐
                                          │ disabled, Root Error    │
                                          │ Status cleared          │
                                          └─────────────────────────┘

    ➊ aer_probe       aer.c:1640  enables through aer_enable_rootport after the IRQ is requested
    ➋ aer_root_reset  :1694       clears the enables through aer_disable_irq before the reset
    ➌ aer_root_reset  :1713       sets the enables through aer_enable_irq after clearing status
    ➍ aer_suspend     :1649       disables through aer_disable_rootport before system sleep
    ➎ aer_resume      :1657       enables again through aer_enable_rootport on resume
    ➏ aer_remove      :1598       disables through aer_disable_rootport when the driver unbinds
```

➊ [`aer_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1607) enables the root through [`aer_enable_rootport()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1533) after the handler is installed. ➋ [`aer_root_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1667) clears the enables through [`aer_disable_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1502) before the reset. ➌ aer_root_reset() sets them again through [`aer_enable_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1491) after clearing the status. ➍ [`aer_suspend()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1645) disables the root through [`aer_disable_rootport()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1575) before sleep. ➎ [`aer_resume()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1653) enables it again through aer_enable_rootport(). ➏ [`aer_remove()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1594) disables it when the service driver unbinds.

The root's enables are therefore set while a bound service can take the interrupt, outside the reset bracket and outside sleep.

### Messages, a tracepoint and hand-offs make the service visible

Watching the service means knowing which lines it prints, which event a tracer can catch and where its work changes context. The table lists each class for the paths of this page, with its sites.

| class | on these paths | sites |
|---|---|---|
| tracepoints | `ras:aer_event`, once per reporting function in the first pass, with the function's name, its unmasked status, the severity and the logged header; no tracepoint in the probe, the enabling, the two halves, the search or the reset | [`aer.c:879-880`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L879), [`ras_event.h:337`](https://elixir.bootlin.com/linux/v7.2/source/include/ras/ras_event.h#L337) |
| info and error lines | the probe's vector line and its request failure, the source line, the limit message, the per-function lines, the reset outcome and the recovery outcome | [`aer.c:1641`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1641), [`aer.c:1635`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1635), [`aer.c:857`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L857), [`aer.c:1075`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1075), [`aer.c:886`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L886), [`aer.c:894`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L894), [`aer.c:1699`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1699), [`aer.c:1704`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1704), [`err.c:253`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L253), [`err.c:288`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L288), [`err.c:296`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L296) |
| dynamic-debug sites | the four broadcasts of the recovery and the driver core's probe and bind lines; drivers/pci/pcie/aer.c holds none | [`err.c:238`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L238), [`err.c:246`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L246), [`err.c:265`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L265), [`err.c:272`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L272), [`dd.c:672`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/dd.c#L672), [`dd.c:757`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/dd.c#L757) |
| asynchronous hand-offs | the hard half wakes the interrupt thread through the queue; the firmware-first work item is not built here | [`aer.c:1485-1488`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1485), [`aer.c:1261`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1261) |
| notifier chains | the bus notifier at unbind of the service device, and at its bind | [`dd.c:1345`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/dd.c#L1345) |
| debugging surfaces | sysfs files, the interrupt's name, boot options and an injector, listed in the next subsection; no debugfs file | the next subsection |

The lines of aer.c carry a prefix, because the file defines its message format before it includes the printing headers.

```c
/* drivers/pci/pcie/aer.c:15 */
#define pr_fmt(fmt) "AER: " fmt
#define dev_fmt pr_fmt
```

The PCI printing macros pass the function's embedded device to the driver core's macros of the same level.

```c
/* include/linux/pci.h:2891 */
#define pci_err(pdev, fmt, arg...)	dev_err(&(pdev)->dev, fmt, ##arg)
#define pci_warn(pdev, fmt, arg...)	dev_warn(&(pdev)->dev, fmt, ##arg)
#define pci_warn_once(pdev, fmt, arg...) dev_warn_once(&(pdev)->dev, fmt, ##arg)
#define pci_notice(pdev, fmt, arg...)	dev_notice(&(pdev)->dev, fmt, ##arg)
#define pci_info(pdev, fmt, arg...)	dev_info(&(pdev)->dev, fmt, ##arg)
#define pci_dbg(pdev, fmt, arg...)	dev_dbg(&(pdev)->dev, fmt, ##arg)
```

Every [`pci_info()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2895) and [`pci_err()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2891) of aer.c therefore expands to a `dev_<level>()` macro, and that macro applies [`dev_fmt()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L16), so its line reads "AER: " after the device's name.

```c
/* include/linux/dev_printk.h:159 */
#define dev_info(dev, fmt, ...) \
	dev_printk_index_wrap(_dev_info, KERN_INFO, dev, dev_fmt(fmt), ##__VA_ARGS__)
```

The per-function lines of [`aer_print_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L865) go through [`aer_printk`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L41) instead, a direct [`dev_printk()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/dev_printk.h#L126) that applies no format, so they carry the device's name without the prefix.

```c
/* drivers/pci/pcie/aer.c:41 */
#define aer_printk(level, pdev, fmt, arg...) \
	dev_printk(level, &(pdev)->dev, fmt, ##arg)
```

The recovery's [`pci_dbg()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2896) lines become [`dev_dbg()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/dev_printk.h#L164) calls, and which body a dev_dbg() gets depends on the configuration.

```c
/* include/linux/dev_printk.h:162 */
#if defined(CONFIG_DYNAMIC_DEBUG) || \
	(defined(CONFIG_DYNAMIC_DEBUG_CORE) && defined(DYNAMIC_DEBUG_MODULE))
#define dev_dbg(dev, fmt, ...)						\
	dynamic_dev_dbg(dev, dev_fmt(fmt), ##__VA_ARGS__)
#elif defined(DEBUG)
#define dev_dbg(dev, fmt, ...)						\
	dev_printk(KERN_DEBUG, dev, dev_fmt(fmt), ##__VA_ARGS__)
#else
#define dev_dbg(dev, fmt, ...)						\
	dev_no_printk(KERN_DEBUG, dev, dev_fmt(fmt), ##__VA_ARGS__)
#endif
```

With [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120) set, as this page assumes, each line is a dynamic-debug site that prints after it is enabled through /sys/kernel/debug/dynamic_debug/control, for example with the query file drivers/pci/pcie/err.c +p. Enabled, the four sites print "broadcast error_detected message", "broadcast mmio_enabled message", "broadcast slot_reset message" and "broadcast resume message" on the bridge, and a reader learns which recovery steps ran and in what order. [`CONFIG_PCI_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L70), unset here, would define DEBUG for the whole directory and print them unconditionally.

```c
/* drivers/pci/Makefile:50 */
subdir-ccflags-$(CONFIG_PCI_DEBUG) := -DDEBUG
```

The interrupt thread is a kernel thread named after the vector and the name the probe gave, which [`setup_irq_thread()`](https://elixir.bootlin.com/linux/v7.2/source/kernel/irq/manage.c#L1402) builds.

```c
/* kernel/irq/manage.c:1401 */
static int
setup_irq_thread(struct irqaction *new, unsigned int irq, bool secondary)
{
	struct task_struct *t;

	if (!secondary) {
		t = kthread_create(irq_thread, new, "irq/%d-%s", irq,
				   new->name);
	} else {
		t = kthread_create(irq_thread, new, "irq/%d-s-%s", irq,
				   new->name);
	}
```

The AER thread of a root is therefore irq/N-aerdrv, with N the service device's vector, and its CPU time and scheduling show the threaded half at work. The notifier entry of the table is the `BUS_NOTIFY_UNBIND_DRIVER` call in the unbind stage shown with [`__device_release_driver()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/dd.c#L1318), and the bind side runs the same chain in the driver core.

### sysfs, boot options and an injector expose the service

User space sees the service through the service device and its driver on the `pci_express` bus, through the statistics and ratelimit files of each function, through the interrupt's name and through two boot options. The service device's name comes from [`get_descriptor_id`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L32) of portdrv.c, which [`pcie_device_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L290) passes to `dev_set_name()`.

```c
/* drivers/pci/pcie/portdrv.c:32 */
#define get_descriptor_id(type, service) (((type - 4) << 8) | service)
```

A Root Port has type 4 and the AER bit is 2, so its AER service device is named after the port with the suffix pcie002, and an RCEC, of type 0xa, gets pcie602. The statistics files that the counters feed are one attribute group of aer.c.

```c
/* drivers/pci/pcie/aer.c:608 */
static struct attribute *aer_stats_attrs[] __ro_after_init = {
	&dev_attr_aer_dev_correctable.attr,
	&dev_attr_aer_dev_fatal.attr,
	&dev_attr_aer_dev_nonfatal.attr,
	&dev_attr_aer_rootport_total_err_cor.attr,
	&dev_attr_aer_rootport_total_err_fatal.attr,
	&dev_attr_aer_rootport_total_err_nonfatal.attr,
	NULL
};
```

The root's three totals, the files ending in "err_cor", "err_fatal" and "err_nonfatal", are the counters [`pci_rootport_aer_stats_incr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L781) raises. The three device files show the per-function counters that [`aer_print_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L865) raises in the printing pass through [`pci_dev_aer_stats_incr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L747).

```c
/* drivers/pci/pcie/aer.c:747 */
static void pci_dev_aer_stats_incr(struct pci_dev *pdev,
				   struct aer_err_info *info)
{
	unsigned long status = info->status & ~info->mask;
	int i, max = -1;
	u64 *counter = NULL;
	struct aer_info *aer_info = pdev->aer_info;

	if (!aer_info)
		return;

	switch (info->severity) {
	case AER_CORRECTABLE:
		aer_info->dev_total_cor_errs++;
		counter = &aer_info->dev_cor_errs[0];
		max = AER_MAX_TYPEOF_COR_ERRS;
		break;
	case AER_NONFATAL:
		aer_info->dev_total_nonfatal_errs++;
		hwerr_log_error_type(HWERR_RECOV_PCI);
		counter = &aer_info->dev_nonfatal_errs[0];
		max = AER_MAX_TYPEOF_UNCOR_ERRS;
		break;
	case AER_FATAL:
		aer_info->dev_total_fatal_errs++;
		counter = &aer_info->dev_fatal_errs[0];
		max = AER_MAX_TYPEOF_UNCOR_ERRS;
		break;
	}

	for_each_set_bit(i, &status, max)
		counter[i]++;
}
```

Each unmasked status bit of the record raises its own counter of the class, and the class total grows once per function, so a function's files count what the first pass read from it. The ratelimit files form a second group, placed in an aer directory of the function.

```c
/* drivers/pci/pcie/aer.c:741 */
const struct attribute_group aer_attr_group = {
	.name = "aer",
	.attrs = aer_attrs,
	.is_visible = aer_attrs_are_visible,
};
```

| surface | what it shows or changes | site |
|---|---|---|
| /sys/bus/pci_express/devices/, one entry per service device | the AER service device of each root, named after the port with the suffix pcie002 for a Root Port and pcie602 for an RCEC | [`portdrv.c:307-309`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L307) |
| /sys/bus/pci_express/drivers/aer | [`aerdriver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1719) and the service devices bound to it | [`aer.c:1720`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1720) |
| "aer_rootport_total_err_cor", "aer_rootport_total_err_fatal" and "aer_rootport_total_err_nonfatal" in the root's PCI directory | the messages of each class the root received | [`aer_stats_attrs`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L608), [`aer.c:627-632`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L627) |
| "aer_dev_correctable", "aer_dev_fatal" and "aer_dev_nonfatal" in each function's PCI directory | the errors counted for the function | [`aer_stats_attrs`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L608) |
| "aer/correctable_ratelimit_interval_ms", "aer/correctable_ratelimit_burst" and their nonfatal twins | the ratelimits [`aer_ratelimit()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L800) applies to the function's lines | [`aer_attrs`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L721) |
| /proc/interrupts and the thread irq/N-aerdrv | the vector of the root's service and the count of its interrupts | [`aer.c:1632-1633`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1632) |
| pci=noaer | turns [`pci_aer_available()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L138) false, so no service driver is registered | [`pci.c:6757-6758`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L6757) |
| `pcie_ports=native`, `compat` or `dpc-native` | overrides the firmware's ownership, disables the port services, or concerns DPC alone | [`portdrv.c:622-633`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L622) |
| debugfs | no file of the service | none |
| fault injection | the software injector of [`CONFIG_PCIEAER_INJECT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L37), unset here, fakes root registers and raises the service's interrupt | [`aer_inject.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer_inject.c) |

The files of the `pci_express` bus exist while the port driver has the service device registered, and the statistics and ratelimit files exist for functions whose [`aer_info`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L371) was allocated.
