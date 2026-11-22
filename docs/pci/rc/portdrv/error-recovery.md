# PCIe error recovery

> CAUTION: AI-GENERATED CONTENT
>
> STRICTLY DO NOT SUBMIT THIS UPSTREAM UNLESS YOU ARE AN EXPERT INTIMATELY FAMILIAR WITH THIS SUBSYSTEM.

When a PCIe function or link reports an uncorrectable error, the drivers of the functions below the affected Port must stop their I/O, let the hardware be reset and start again, or learn that their device is gone. The PCI core runs that exchange in one place for the error services of the PCIe port driver, which detect the error and name the function to blame. Every Port and Endpoint function is a [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352), and a driver takes part through the [`err_handler`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L1032) table of its [`struct pci_driver`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L1021). This page traces how recovery chooses the functions it involves, collects their drivers' votes, tracks each function's channel state, resets the hierarchy, and ends in success or in permanent failure.

```text
    How pcie_do_recovery() moves the subtree from an error to a verdict
    ───────────────────────────────────────────────────────────────────

    ┌──────────────────────────────────────────────────┐
    │ a service reports an error on dev, with a        │
    │ channel state and a reset callback               │
    └───────────┬──────────────────────────────────────┘
                │
                ▼
    ┌──────────────────────────────────────────────────┐
    │ every function below the bridge is resumed       │
    │ and held; each driver is told error_detected     │
    │ and its vote is merged into the status           │
    └───────────┬──────────────────────────────────────┘
                │
                ▼
    ┌────────────────────────┐  yes    ┌──────────────────────────────────────┐
    │ status CAN_RECOVER?    ├────────▶│ status = RECOVERED; each driver is   │
    └───────────┬────────────┘         │ told mmio_enabled, votes merged      │
                │ no                   └──────────────┬───────────────────────┘
                │                                     │
                ├─────────────────────────────────────┘
                │
                │
                ▼
    ┌────────────────────────┐  yes    ┌──────────────────────────────────────┐
    │ status NEED_RESET,     ├────────▶│ the reset callback resets the        ├─────┐
    │ or state frozen?       │         │ hierarchy below the bridge           │     │
    └───────────┬────────────┘         └──────────────┬───────────────────────┘     │
                │ no                                  │ RECOVERED                   │ any other
                ├─────────────────────────────────────┘                             │ result
                │                                                                   │
                │                                                                   │
                ▼                                                                   │
    ┌────────────────────────┐  yes    ┌──────────────────────────────────────┐     │
    │ status NEED_RESET?     ├────────▶│ status = RECOVERED; each driver is   │     │
    └───────────┬────────────┘         │ told slot_reset, votes merged        │     │
                │ no                   └──────────────┬───────────────────────┘     │
                │                                     │                             │
                ├─────────────────────────────────────┘                             │
                │                                                                   │
                │                                                                   │
                ▼                                                                   │
    ┌────────────────────────┐  yes    ┌──────────────────────────────────────┐     │
    │ status RECOVERED?      ├────────▶│ each driver is told resume; error    │     │
    └───────────┬────────────┘         │ status cleared; runtime PM released; │     │
                │ no                   │ RECOVERED returned                   │     │
                │                      └──────────────────────────────────────┘     │
                │                                                                   │
                ▼                                                                   │
    ┌───────────────────────────────────────┐                                       │
    │ runtime PM released; each driver is   │◀──────────────────────────────────────┘
    │ told perm_failure; status returned    │
    └───────────────────────────────────────┘
```

## SUMMARY

Recovery acts on the functions below one Port, and the kernel represents each term of the recovery steps by an object or value it already keeps. The table settles the terms the rest of the page uses.

| term | kernel representation | meaning |
|---|---|---|
| the reporting device | `dev`, the [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) passed to [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) | the function a service blames for the error |
| the bridge | `bridge`, `dev` itself or [`pci_upstream_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L819) of it | the Port, RCEC or RCiEP whose subtree recovers |
| the subtree | the functions [`pci_walk_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L200) visits | the functions on the bridge's subordinate bus and below it |
| a vote | a [`pci_ers_result_t`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L918) that a driver callback returns | one driver's answer at one step |
| the status | the local `status` of [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210), combined by [`merge_result()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L24) | the subtree's answer so far |
| the channel state | [`error_state`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L445), a [`pci_channel_state_t`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L206) | whether the function can be reached |

The journey follows the steps that [`Documentation/PCI/pci-error-recovery.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/PCI/pci-error-recovery.rst) names, notification through [`error_detected`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L943), MMIO enabled, link reset, slot reset and resume, with permanent failure when recovery fails. A step runs when the status or the channel state asks for it, and the status can only climb, so one driver that needs a reset or has no callback decides for the subtree. Recovery succeeds when the status reads [`PCI_ERS_RESULT_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L934) before the resume step, and any other outcome tells every driver that has an [`error_detected`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L943) callback that its function has failed permanently.

## SPECIFICATIONS

The callback sequence and the vote values are a kernel synthesis that no specification defines, read here from drivers/pci/pcie/err.c, include/linux/pci.h and the Port services that call it. The specifications the tree cites on these paths name the error signaling, the containment and the firmware notification that start a recovery.

- PCI Express Specification, named without a section by [`include/linux/pci.h:14-20`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L14), the header that defines [`struct pci_error_handlers`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L941), [`enum pci_ers_result`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L920) and [`pci_channel_state_t`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L206).
- PCIe r6.0, sec 6.7.6, cited without a title by the comment at [`dpc.c:367-369`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L367) in [`dpc_handler()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L363), for the errors a surprise removal causes.
- ACPI r6.5, sec 5.6.6, cited without a title by the comment at [`edr.c:160-163`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/edr.c#L160) in [`edr_handle_event()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/edr.c#L151), for the notification that a Port has contained an error.

## COVERAGE

### The recovery sequence

- [`'\<pcie_do_recovery\>':'drivers/pci/pcie/err.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210): runs the steps of recovery over the subtree of the bridge and returns the final status.
- [`'\<pci_walk_bridge\>':'drivers/pci/pcie/err.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L200): calls a callback on every function below the bridge, or on an RCEC or RCiEP itself.
- [`'\<pci_pm_runtime_get_sync\>':'drivers/pci/pcie/err.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L89): resumes a function and raises its runtime PM usage count for the length of recovery.
- [`'\<pci_pm_runtime_put\>':'drivers/pci/pcie/err.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L95): drops that usage count when recovery ends.

### The broadcasts and the votes

- [`'\<report_frozen_detected\>':'drivers/pci/pcie/err.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L101): tells one function's driver of an error with the channel frozen.
- [`'\<report_normal_detected\>':'drivers/pci/pcie/err.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L106): tells one function's driver of an error with the channel still normal.
- [`'\<report_error_detected\>':'drivers/pci/pcie/err.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L49): sets the channel state, calls [`error_detected`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L943) or decides the vote itself, and merges the vote.
- [`'\<report_mmio_enabled\>':'drivers/pci/pcie/err.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L129): calls [`mmio_enabled`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L947) and merges its vote.
- [`'\<report_slot_reset\>':'drivers/pci/pcie/err.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L148): returns the channel to normal, calls [`slot_reset`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L950) and merges its vote.
- [`'\<report_resume\>':'drivers/pci/pcie/err.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L168): returns the channel to normal, calls [`resume`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L957) and announces success.
- [`'\<report_perm_failure_detected\>':'drivers/pci/pcie/err.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L111): tells a driver its function failed permanently and announces the failure.
- [`'\<merge_result\>':'drivers/pci/pcie/err.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L24): combines the status with one vote, letting the status only climb.
- [`'\<pci_uevent_ers\>':'drivers/pci/pci-driver.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L1625): sends user space a change uevent for a function's recovery event.

### The driver interface and the states

- [`'\<struct pci_error_handlers\>':'include/linux/pci.h'`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L941): the callbacks a driver supplies for recovery and for function resets.
- [`'\<enum pci_ers_result\>':'include/linux/pci.h'`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L920): the votes a callback returns and the status recovery carries.
- [`'\<pci_channel_state_t\>':'include/linux/pci.h'`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L206): the type of a function's channel state.
- [`'pci_channel_io_normal'`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L210): the channel state of a reachable function.
- [`'pci_channel_io_frozen'`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L213): the channel state of a function whose I/O is blocked.
- [`'pci_channel_io_perm_failure'`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L216): the channel state of a function that is gone.
- [`'\<pci_dev_set_io_state\>':'drivers/pci/pci.h'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L737): moves a function's channel state along the transitions it allows.

### The reset callbacks

- [`'aer_root_reset'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1667): the AER reset callback, which resets the hierarchy below a Root Port or the RCEC or RCiEP itself.
- [`'\<dpc_reset_link\>':'drivers/pci/pcie/dpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L148): the DPC reset callback, which waits for the contained link and releases the Port from containment.

## DOCUMENTATION

- [`Documentation/PCI/pci-error-recovery.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/PCI/pci-error-recovery.rst): the recovery steps, the channel states a driver receives and the votes it may return.
- [`Documentation/PCI/pcieaer-howto.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/PCI/pcieaer-howto.rst): how the AER driver calls the recovery callbacks, and when it resets the link for fatal and non-fatal errors.
- [`Documentation/admin-guide/kernel-parameters.txt`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/admin-guide/kernel-parameters.txt): the `pcie_ports=` and `pci=noaer` parameters that decide whether the OS handles AER at all.

## OTHER SOURCES

### Added by Claude Opus 5.5

- [PCI/ERR: Update device error_state already after reset (commit 45bc82563d55)](https://patch.msgid.link/4517af6359ffb9d66152b827a5d2833459144e3f.1755008151.git.lukas@wunner.de)
- [PCI/ERR: Notify drivers on failure to recover (commit 9011f0667c93)](https://patch.msgid.link/ec212d4d4f5c65d29349df33acdc9768ff8279d1.1755008151.git.lukas@wunner.de)
- [PCI/ERR: Fix uevent on failure to recover (commit 1cbc5e25fb70)](https://patch.msgid.link/68fc527a380821b5d861dd554d2ce42cb739591c.1755008151.git.lukas@wunner.de)
- [PCI/AER: Allow drivers to opt in to Bus Reset on Non-Fatal Errors (commit d0a2dee7d458)](https://patch.msgid.link/28fd805043bb57af390168d05abb30898cf4fc58.1755008151.git.lukas@wunner.de)
- [PCI/AER: Block runtime suspend when handling errors (commit 002bf2fbc00e)](https://lore.kernel.org/r/20240212120135.146068-1-stanislaw.gruszka@linux.intel.com)
- [PCI/ERR: Recognize disconnected devices in report_error_detected() (commit 5e69a33c5cec)](https://lore.kernel.org/r/20220601074024.3481035-1-hch@lst.de)
- [PCI/ERR: Retain status from error notification (commit 387c72cdd7fb)](https://lore.kernel.org/r/20210104230300.1277180-4-kbusch@kernel.org)
- [PCI/ERR: Clear status of the reporting device (commit 7d7cbeaba5b7)](https://lore.kernel.org/r/20210104230300.1277180-2-kbusch@kernel.org)
- [PCI/ERR: Recover from RCiEP AER errors (commit 579086225502)](https://lore.kernel.org/r/20201121001036.8560-13-sean.v.kelley@intel.com)
- [PCI/ERR: Add pci_walk_bridge() to pcie_do_recovery() (commit 05e9ae19ab83)](https://lore.kernel.org/r/20201121001036.8560-10-sean.v.kelley@intel.com)
- [PCI/ERR: Rename reset_link() to reset_subordinates() (commit 8f1bbfbc3596)](https://lore.kernel.org/r/20201121001036.8560-5-sean.v.kelley@intel.com)
- [PCI/ERR: Clear PCIe Device Status errors only if OS owns AER (commit 068c29a248b6)](https://lore.kernel.org/r/20200622113523.891666-1-Jonathan.Cameron@huawei.com)
- [PCI/ERR: Return status of pcie_do_recovery() (commit e8e5ff2aeec1)](https://lore.kernel.org/r/eb60ec89448769349c6722954ffbf2de163155b5.1585000084.git.sathyanarayanan.kuppuswamy@linux.intel.com)
- [PCI/ERR: Remove service dependency in pcie_do_recovery() (commit b6cf1a42f916)](https://lore.kernel.org/r/60e02b87b526cdf2930400059d98704bf0a147d1.1585000084.git.sathyanarayanan.kuppuswamy@linux.intel.com)
- [PCI/AER: Log which device prevents error recovery (commit 01daacfb9035)](https://lore.kernel.org/r/1576237474-32021-1-git-send-email-yangyicong@hisilicon.com)

## REGISTERS

The code of err.c reads and writes no register itself: it works on votes and channel states, and the registers on its paths are touched by the status clearing at the end of a successful run and by the two reset callbacks. Each drawing holds one of those registers with the macros the code uses, and the paragraph after it says what the fields decide on these paths.

```text
    Device Status, at offset 0x0a of the PCI Express capability
    ───────────────────────────────────────────────────────────

    bit        1 1 1 1 1 1
               5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
              ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    +0x0a     │  no macro (15:6)  │T│P│U│F│N│C│
              └───────────────────┴─┴─┴─┴─┴─┴─┘

    C = PCI_EXP_DEVSTA_CED (Correctable Error Detected)
    N = PCI_EXP_DEVSTA_NFED (Non-Fatal Error Detected)
    F = PCI_EXP_DEVSTA_FED (Fatal Error Detected)
    U = PCI_EXP_DEVSTA_URD (Unsupported Request Detected)
    P = PCI_EXP_DEVSTA_AUXPD (AUX Power Detected); T = PCI_EXP_DEVSTA_TRPND (Transactions Pending)
    PCI_EXP_DEVSTA = 0x0a; pcie_clear_device_status() writes C, N, F and U, and no member caches the register
```

[`pcie_clear_device_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2240) writes C, N, F and U to Device Status of the reporting device when recovery succeeds and the OS controls AER, which clears the error-detected bits the error left set. The value it writes holds 0 in P and T, so the write changes neither of them.

```text
    Uncorrectable Error Status against Uncorrectable Error Severity, for an error bit n
    ───────────────────────────────────────────────────────────────────────────────────

    bit       31                   n                   0
              ┌───────────────────┬─┬───────────────────┐
    +0x04     │        ...        │1│        ...        │  Status: error n is logged
              ├───────────────────┼─┼───────────────────┤
    +0x0c     │        ...        │0│        ...        │  Severity: 0 makes error n Non-Fatal
              └───────────────────┴─┴───────────────────┘

    Status = PCI_ERR_UNCOR_STATUS (0x04); Severity = PCI_ERR_UNCOR_SEVER (0x0c, the same bits)
    pci_aer_clear_nonfatal_status() writes status & ~severity back to +0x04: bit n is written 1,
    and a logged error whose severity bit is 1 is written 0 and stays logged
```

[`pci_aer_clear_nonfatal_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L264) runs on the same success path and reads both words of the reporting device's AER capability. It writes back only the logged errors whose severity bit is 0, the errors the comment in the function calls "ERR_NONFATAL errors", so an error marked Fatal stays logged.

```text
    Root Error Command and Root Error Status, in the AER capability of a Root Port or RCEC
    ──────────────────────────────────────────────────────────────────────────────────────

    bit        3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
               1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
              ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    +0x2c     │                     no macro (31:3)                     │F│N│C│
              ├─────────┬───────────────────────────────────────┬─┬─┬─┬─┼─┼─┼─┤
    +0x30     │   IRQ   │            no macro (26:7)            │A│B│P│X│U│Y│E│
              │ (31:27) │                                       │ │ │ │ │ │ │ │
              └─────────┴───────────────────────────────────────┴─┴─┴─┴─┴─┴─┴─┘

    C = PCI_ERR_ROOT_CMD_COR_EN, N = PCI_ERR_ROOT_CMD_NONFATAL_EN, F = PCI_ERR_ROOT_CMD_FATAL_EN
        (PCI_ERR_ROOT_COMMAND = 0x2c; ROOT_PORT_INTR_ON_MESG_MASK = C | N | F)
    E = PCI_ERR_ROOT_COR_RCV, Y = PCI_ERR_ROOT_MULTI_COR_RCV, U = PCI_ERR_ROOT_UNCOR_RCV,
    X = PCI_ERR_ROOT_MULTI_UNCOR_RCV, P = PCI_ERR_ROOT_FIRST_FATAL, B = PCI_ERR_ROOT_NONFATAL_RCV,
    A = PCI_ERR_ROOT_FATAL_RCV, IRQ = PCI_ERR_ROOT_AER_IRQ (Advanced Error Interrupt Message Number)
        (PCI_ERR_ROOT_STATUS = 0x30); the offsets add to aer_cap, which no other member caches
```

[`aer_root_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1667) clears C, N and F of Root Error Command through [`aer_disable_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1502) before it resets anything, the step whose comment reads "Disable Root Port's interrupt in response to error messages", and sets them again through [`aer_enable_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1491) afterwards. Between the two it reads Root Error Status and writes the value back, the step its comment calls clearing Root Error Status. Both steps run only when the OS controls AER and the root has an AER capability, [`aer_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370) nonzero.

```text
    DPC Status, at offset 0x08 of the DPC capability
    ────────────────────────────────────────────────

    bit        1 1 1 1 1 1
               5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
              ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    +0x08     │  ·  │   FEP   │·│EXT│R│I│RSN│T│
              │     │ (12:8)  │ │   │ │ │   │ │
              └─────┴─────────┴─┴───┴─┴─┴───┴─┘

    T = PCI_EXP_DPC_STATUS_TRIGGER (Trigger Status)
    RSN = PCI_EXP_DPC_STATUS_TRIGGER_RSN (Trigger Reason, 2:1)
    I = PCI_EXP_DPC_STATUS_INTERRUPT (Interrupt Status); R = PCI_EXP_DPC_RP_BUSY (Root Port Busy)
    EXT = PCI_EXP_DPC_STATUS_TRIGGER_RSN_EXT (Trigger Reason Extension, 6:5)
    FEP = PCI_EXP_DPC_RP_PIO_FEP (RP PIO First Error Pointer); bits 15:13 and 7 have no macro
    PCI_EXP_DPC_STATUS = 0x08, added to dpc_cap
```

[`dpc_reset_link()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L148) writes T to DPC Status once the link is down, which releases the Port from containment, and on a Root Port with RP extensions it first polls R through [`dpc_wait_rp_inactive()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L130). The reset callback reads or writes no other field of DPC Status.

```text
    Link Status, at offset 0x12 of the PCI Express capability
    ─────────────────────────────────────────────────────────

    bit        1 1 1 1 1 1
               5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
              ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    +0x12     │B│M│D│S│T│·│    NLW    │  CLS  │
              │ │ │ │ │ │ │   (9:4)   │ (3:0) │
              └─┴─┴─┴─┴─┴─┴───────────┴───────┘

    D = PCI_EXP_LNKSTA_DLLLA (Data Link Layer Link Active)
    CLS = PCI_EXP_LNKSTA_CLS (Current Link Speed); NLW = PCI_EXP_LNKSTA_NLW (Negotiated Link Width)
    T = PCI_EXP_LNKSTA_LT (Link Training); S = PCI_EXP_LNKSTA_SLC (Slot Clock Configuration)
    M = PCI_EXP_LNKSTA_LBMS; B = PCI_EXP_LNKSTA_LABS; bit 10 has no macro
    PCI_EXP_LNKSTA = 0x12; dpc_reset_link() waits for D to read 0 through pcie_wait_for_link()
```

[`pcie_wait_for_link_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4535) reads Link Status and compares D with 0 while [`dpc_reset_link()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L148) waits for the link to go down. A Port whose [`link_active_reporting`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L507) bit is clear never has D read on this path, and the wait sleeps instead.

## DETAILS

The first subsections set up the terms of recovery: the callbacks a driver supplies in [`struct pci_error_handlers`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L941) and those the port driver supplies for the Ports, the votes they return and how [`merge_result()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L24) combines them, and the channel state every function carries. The services that start recovery come next, each with the channel state and the reset callback it passes to [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210). The reading of [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) then follows the bridge that bounds the subtree, the runtime PM hold over the subtree, the detection round, and the decision between the MMIO round and a reset. The two reset callbacks, the slot reset and resume rounds and the failure path complete the run, and the last subsection lists the messages, uevents and hand-offs that make a recovery visible.

### Kconfig assumptions

The page documents an x86-64 kernel built from `x86_64_defconfig` at the pinned commit with the PCIe options of this knowledge base set, running on an ACPI platform. The table lists the options the prose names, with the value each assumes.

| option | assumed value | what it decides here |
|---|---|---|
| [`CONFIG_PCIEPORTBUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L5) | y | builds the port driver, whose services start recovery and whose callbacks serve the Ports below the bridge |
| [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28) | y | builds err.c beside aer.c, and with it [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) and [`pci_uevent_ers()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L1625) |
| [`CONFIG_PCIE_DPC`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L121) | y | builds dpc.c, the DPC caller and [`dpc_reset_link()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L148) |
| [`CONFIG_PCIE_EDR`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L140) | not set | builds edr.c, the EDR caller, which the page reads for a kernel built with it |
| [`CONFIG_ACPI_APEI_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Kconfig#L37) | not set | compiles [`aer_recover_work_func()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1218), the caller for errors firmware reports |
| [`CONFIG_PM`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L217) | y, selected by [`CONFIG_PM_SLEEP`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L140) | makes the runtime PM hold resume the functions and keep them out of runtime suspend |
| [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120) | y | turns the [`pci_dbg()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2896) sites of these paths into dynamic-debug callsites |
| [`CONFIG_PCI_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L70) | not set | would define `DEBUG` for drivers/pci and print those sites unconditionally |
| [`CONFIG_PCIEAER_INJECT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L37) | not set | builds the software injector that starts AER recovery on demand |
| [`CONFIG_HOTPLUG_PCI_ACPI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/Kconfig#L55) | not set | builds the ACPI hotplug driver, a writer of the channel state outside recovery |

The table indexes the prose, and the effect of each option is stated again in the subsection where it applies.

### Drivers join recovery through a table of error callbacks

Recovery needs the driver of every function below the failing Port, because the driver is the code that can stop its device's I/O and bring it back. The PCI core asks for that help through a table of callbacks, [`struct pci_error_handlers`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L941), which a driver points at from the [`err_handler`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L1032) member of its [`struct pci_driver`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L1021). The reader follows one function below the bridge, its [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352), whose [`driver`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L388) member leads to that table.

The table below says when recovery calls each member of [`struct pci_error_handlers`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L941) and what the member returns; the excerpt after it is the definition in include/linux/pci.h, which shows the argument each callback receives.

| member | when it runs | what it returns |
|---|---|---|
| [`error_detected`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L943) | first, for every function below the bridge, with the channel state | a vote |
| [`mmio_enabled`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L947) | when the votes so far allow recovery without a reset | a vote |
| [`slot_reset`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L950) | after the reset callback has reset the hierarchy, when a vote asked for a reset | a vote |
| [`reset_prepare`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L953) and [`reset_done`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L954) | around a function reset the reset code performs, outside recovery | nothing |
| [`resume`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L957) | last, when recovery has succeeded | nothing |
| [`cor_error_detected`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L960) | from AER for a correctable error, which starts no recovery | nothing |

[`struct pci_error_handlers`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L941) is defined in include/linux/pci.h with a comment of one line above each member, and the excerpt shows the argument each callback receives.

```c
/* include/linux/pci.h:940 */
/* PCI bus error event callbacks */
struct pci_error_handlers {
	/* PCI bus error detected on this device */
	pci_ers_result_t (*error_detected)(struct pci_dev *dev,
					   pci_channel_state_t error);

	/* MMIO has been re-enabled, but not DMA */
	pci_ers_result_t (*mmio_enabled)(struct pci_dev *dev);

	/* PCI slot has been reset */
	pci_ers_result_t (*slot_reset)(struct pci_dev *dev);

	/* PCI function reset prepare or completed */
	void (*reset_prepare)(struct pci_dev *dev);
	void (*reset_done)(struct pci_dev *dev);

	/* Device driver may resume normal operations */
	void (*resume)(struct pci_dev *dev);

	/* Allow device driver to record more details of a correctable error */
	void (*cor_error_detected)(struct pci_dev *dev);
};
```

Each callback receives the function's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) and nothing more, so a driver finds its own state through the driver data it attached at probe time. The three members that return [`pci_ers_result_t`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L918) vote on what happens next, while [`resume`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L957) and the reset pair only inform the driver. A member left NULL is allowed, and every caller of a member on these paths tests it before the call.

The NVMe driver is a class driver that fills the table. Its [`nvme_err_handler`](https://elixir.bootlin.com/linux/v7.2/source/drivers/nvme/host/pci.c#L4089) sets five of the seven members, and its [`nvme_driver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/nvme/host/pci.c#L4293) registration points [`err_handler`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L1032) at that table; the two excerpts show the table and the registration.

```c
/* drivers/nvme/host/pci.c:4089 */
static const struct pci_error_handlers nvme_err_handler = {
	.error_detected	= nvme_error_detected,
	.slot_reset	= nvme_slot_reset,
	.resume		= nvme_error_resume,
	.reset_prepare	= nvme_reset_prepare,
	.reset_done	= nvme_reset_done,
};
```

The table leaves [`mmio_enabled`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L947) and [`cor_error_detected`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L960) NULL, so the NVMe driver takes part in detection, slot reset and resume, and in the function resets of the reset code. The registration below makes the table reachable from every NVMe function the driver binds.

```c
/* drivers/nvme/host/pci.c:4293 */
static struct pci_driver nvme_driver = {
	.name		= "nvme",
	.id_table	= nvme_id_table,
	.probe		= nvme_probe,
	.remove		= nvme_remove,
	.shutdown	= nvme_shutdown,
	.driver		= {
		.probe_type	= PROBE_PREFER_ASYNCHRONOUS,
#ifdef CONFIG_PM_SLEEP
		.pm		= &nvme_dev_pm_ops,
#endif
	},
	.sriov_configure = pci_sriov_configure_simple,
	.err_handler	= &nvme_err_handler,
};
```

The `.err_handler` initializer is the pointer recovery follows from a bound function to the table. [`nvme_error_detected()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/nvme/host/pci.c#L4041), the first callback, shows what the channel state means to a driver and how the driver turns it into a vote.

```c
/* drivers/nvme/host/pci.c:4041 */
static pci_ers_result_t nvme_error_detected(struct pci_dev *pdev,
						pci_channel_state_t state)
{
	struct nvme_dev *dev = pci_get_drvdata(pdev);

	/*
	 * A frozen channel requires a reset. When detected, this method will
	 * shutdown the controller to quiesce. The controller will be restarted
	 * after the slot reset through driver's slot_reset callback.
	 */
	switch (state) {
	case pci_channel_io_normal:
		return PCI_ERS_RESULT_CAN_RECOVER;
	case pci_channel_io_frozen:
		dev_warn(dev->ctrl.device,
			"frozen state error detected, reset controller\n");
		if (!nvme_change_ctrl_state(&dev->ctrl, NVME_CTRL_RESETTING)) {
			nvme_dev_disable(dev, true);
			return PCI_ERS_RESULT_DISCONNECT;
		}
		nvme_dev_disable(dev, false);
		return PCI_ERS_RESULT_NEED_RESET;
	case pci_channel_io_perm_failure:
		dev_warn(dev->ctrl.device,
			"failure state error detected, request disconnect\n");
		return PCI_ERS_RESULT_DISCONNECT;
	}
	return PCI_ERS_RESULT_NEED_RESET;
}
```

The NVMe driver votes [`PCI_ERS_RESULT_CAN_RECOVER`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L925) for a normal channel and keeps its controller running. For a frozen channel it quiesces the controller and votes [`PCI_ERS_RESULT_NEED_RESET`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L928), or [`PCI_ERS_RESULT_DISCONNECT`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L931) when the controller cannot enter its resetting state, and a permanently failed channel gets `PCI_ERS_RESULT_DISCONNECT` at once. The two callbacks after the reset restart what detection stopped.

```c
/* drivers/nvme/host/pci.c:4071 */
static pci_ers_result_t nvme_slot_reset(struct pci_dev *pdev)
{
	struct nvme_dev *dev = pci_get_drvdata(pdev);

	dev_info(dev->ctrl.device, "restart after slot reset\n");
	pci_restore_state(pdev);
	if (nvme_try_sched_reset(&dev->ctrl))
		nvme_unquiesce_io_queues(&dev->ctrl);
	return PCI_ERS_RESULT_RECOVERED;
}

static void nvme_error_resume(struct pci_dev *pdev)
{
	struct nvme_dev *dev = pci_get_drvdata(pdev);

	flush_work(&dev->ctrl.reset_work);
}
```

[`nvme_slot_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/nvme/host/pci.c#L4071) restores the function's saved configuration space with [`pci_restore_state()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L1826) and schedules the controller reset, voting [`PCI_ERS_RESULT_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L934). [`nvme_error_resume()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/nvme/host/pci.c#L4082) waits for that reset work to finish, so the function is back in service when recovery returns. The figure draws the chain of pointers that leads from one function below the bridge to the callbacks of its driver, for an NVMe function.

```text
    How the recovery code reaches a driver's callbacks
    ──────────────────────────────────────────────────

    struct pci_dev (a function below the bridge)
    ┌──────────────────────────────────────────────────────┐
    │ error_state  the channel state                       │
    │ driver ─────────────────────────────────────────┐    │
    └─────────────────────────────────────────────────┼────┘
                                                      │
                                                      │
    struct pci_driver (nvme_driver)                   ▼
    ┌──────────────────────────────────────────────────────┐
    │ err_handler ────────────────────────────────────┐    │
    └─────────────────────────────────────────────────┼────┘
                                                      │
                                                      │
    struct pci_error_handlers (nvme_err_handler)      ▼
    ┌──────────────────────────────────────────────────────┐
    │ error_detected ──────────────────────────────────────┼─────▶ nvme_error_detected  detection, every function
    │ mmio_enabled         NULL                            │                            MMIO round: skipped
    │ slot_reset ──────────────────────────────────────────┼─────▶ nvme_slot_reset      after the reset
    │ reset_prepare ───────────────────────────────────────┼─────▶ nvme_reset_prepare   function resets only
    │ reset_done ──────────────────────────────────────────┼─────▶ nvme_reset_done      function resets only
    │ resume ──────────────────────────────────────────────┼─────▶ nvme_error_resume    success
    │ cor_error_detected   NULL                            │                            correctable errors only
    └──────────────────────────────────────────────────────┘
```

A function below the bridge thus reaches recovery through two pointers, [`driver`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L388) and [`err_handler`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L1032), and a NULL at either one leaves the function without a driver to call. The Ports among the functions below the bridge have a driver of their own, the PCIe port driver.

### The port driver answers for the Ports below the bridge

A Switch below the bridge contributes functions of its own, its Upstream Port and its Downstream Ports, and they take part in recovery like any Endpoint. The PCIe port driver, built with [`CONFIG_PCIEPORTBUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L5), binds them, as it binds Root Ports and RCECs, and its callbacks vote for the Port and pass the slot reset on to the Port's services. The three callbacks are defined together in portdrv.c.

```c
/* drivers/pci/pcie/portdrv.c:750 */
static pci_ers_result_t pcie_portdrv_error_detected(struct pci_dev *dev,
					pci_channel_state_t error)
{
	if (error == pci_channel_io_frozen)
		return PCI_ERS_RESULT_NEED_RESET;
	return PCI_ERS_RESULT_CAN_RECOVER;
}

static pci_ers_result_t pcie_portdrv_slot_reset(struct pci_dev *dev)
{
	size_t off = offsetof(struct pcie_port_service_driver, slot_reset);
	device_for_each_child(&dev->dev, &off, pcie_port_device_iter);

	pci_restore_state(dev);
	return PCI_ERS_RESULT_RECOVERED;
}

static pci_ers_result_t pcie_portdrv_mmio_enabled(struct pci_dev *dev)
{
	return PCI_ERS_RESULT_RECOVERED;
}
```

[`pcie_portdrv_error_detected()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L750) votes [`PCI_ERS_RESULT_NEED_RESET`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L928) for a frozen channel and [`PCI_ERS_RESULT_CAN_RECOVER`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L925) otherwise, and [`pcie_portdrv_mmio_enabled()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L767) always votes [`PCI_ERS_RESULT_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L934). [`pcie_portdrv_slot_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L758) hands the offset of the [`slot_reset`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L88) member of [`struct pcie_port_service_driver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L78) to [`pcie_port_device_iter()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L385) for every child of the Port's device, and then restores the Port's configuration space. The children are the Port's service devices, each a [`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59), portdrv's service instance, and the iterator decides which of them get the call.

```c
/* drivers/pci/pcie/portdrv.c:385 */
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

[`pcie_port_device_iter()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L385) calls the member only for a child on [`pcie_port_bus_type`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L575) with a service driver bound, and only when that driver sets it; at v7.2 the PCIe hotplug service sets [`slot_reset`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L88), at [`pciehp_core.c:371`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L371), and no other port service does. The table and the registration that carry the port driver's callbacks follow.

```c
/* drivers/pci/pcie/portdrv.c:785 */
static const struct pci_error_handlers pcie_portdrv_err_handler = {
	.error_detected = pcie_portdrv_error_detected,
	.slot_reset = pcie_portdrv_slot_reset,
	.mmio_enabled = pcie_portdrv_mmio_enabled,
};

static struct pci_driver pcie_portdriver = {
	.name		= "pcieport",
	.id_table	= port_pci_ids,

	.probe		= pcie_portdrv_probe,
	.remove		= pcie_portdrv_remove,
	.shutdown	= pcie_portdrv_shutdown,

	.err_handler	= &pcie_portdrv_err_handler,

	.driver_managed_dma = true,

	.driver.pm	= PCIE_PORTDRV_PM_OPS,
};

```

[`pcie_portdrv_err_handler`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L785) leaves [`resume`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L957) NULL, so a Port below the bridge has nothing to restart after the reset beyond what its slot reset restored. A Port therefore votes for a reset whenever the channel is frozen, and what recovery does with such answers, and with the functions that give none, is the subject of the votes.

### Callbacks return votes that merge_result folds into one status

A subtree holds many functions, and recovery needs one decision for all of them: whether a reset is needed and whether recovery can go on at all. Each callback answers with a value of [`enum pci_ers_result`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L920), the vote, and [`merge_result()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L24) folds each vote into the status that [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) carries from one function to the next. The definition names the answers, and its comments say what each one means to the driver that returns it.

```c
/* include/linux/pci.h:911 */
/*
 * PCI Error Recovery System (PCI-ERS).  If a PCI device driver provides
 * a set of callbacks in struct pci_error_handlers, that device driver
 * will be notified of PCI bus errors, and will be driven to recovery
 * when an error occurs.
 */

typedef unsigned int __bitwise pci_ers_result_t;

enum pci_ers_result {
	/* No result/none/not supported in device driver */
	PCI_ERS_RESULT_NONE = (__force pci_ers_result_t) 1,

	/* Device driver can recover without slot reset */
	PCI_ERS_RESULT_CAN_RECOVER = (__force pci_ers_result_t) 2,

	/* Device driver wants slot to be reset */
	PCI_ERS_RESULT_NEED_RESET = (__force pci_ers_result_t) 3,

	/* Device has completely failed, is unrecoverable */
	PCI_ERS_RESULT_DISCONNECT = (__force pci_ers_result_t) 4,

	/* Device driver is fully recovered and operational */
	PCI_ERS_RESULT_RECOVERED = (__force pci_ers_result_t) 5,

	/* No AER capabilities registered for the driver */
	PCI_ERS_RESULT_NO_AER_DRIVER = (__force pci_ers_result_t) 6,
};
```

[`pci_ers_result_t`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L918) is a `__bitwise` integer type, so sparse rejects a vote mixed with a plain integer, and the enumerators start at 1. [`PCI_ERS_RESULT_NONE`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L922) is a vote with no opinion, which the core also casts itself for a bridge function without a callback. [`PCI_ERS_RESULT_CAN_RECOVER`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L925) and [`PCI_ERS_RESULT_NEED_RESET`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L928) ask to go on without or with a reset, [`PCI_ERS_RESULT_DISCONNECT`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L931) gives the function up, and [`PCI_ERS_RESULT_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L934) reports that the driver is working again. [`PCI_ERS_RESULT_NO_AER_DRIVER`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L937) is cast by the core for a function whose driver has no [`error_detected`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L943) member, as the detection subsection shows.

The table states what one more vote does to the status [`merge_result()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L24) holds; the excerpt after it is the function, whose switch is the table's rows.

| status held | a [`PCI_ERS_RESULT_NONE`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L922) vote | a [`PCI_ERS_RESULT_NO_AER_DRIVER`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L937) vote | a [`PCI_ERS_RESULT_NEED_RESET`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L928) vote | any other vote |
|---|---|---|---|---|
| [`PCI_ERS_RESULT_CAN_RECOVER`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L925) or [`PCI_ERS_RESULT_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L934) | kept | replaced | replaced | replaced |
| [`PCI_ERS_RESULT_DISCONNECT`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L931) | kept | replaced | replaced | kept |
| [`PCI_ERS_RESULT_NEED_RESET`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L928) | kept | replaced | kept | kept |
| [`PCI_ERS_RESULT_NO_AER_DRIVER`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L937) | kept | kept | kept | kept |

[`merge_result()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L24) implements the table with two tests before a switch on the status it holds.

```c
/* drivers/pci/pcie/err.c:24 */
static pci_ers_result_t merge_result(enum pci_ers_result orig,
				  enum pci_ers_result new)
{
	if (new == PCI_ERS_RESULT_NO_AER_DRIVER)
		return PCI_ERS_RESULT_NO_AER_DRIVER;

	if (new == PCI_ERS_RESULT_NONE)
		return orig;

	switch (orig) {
	case PCI_ERS_RESULT_CAN_RECOVER:
	case PCI_ERS_RESULT_RECOVERED:
		orig = new;
		break;
	case PCI_ERS_RESULT_DISCONNECT:
		if (new == PCI_ERS_RESULT_NEED_RESET)
			orig = PCI_ERS_RESULT_NEED_RESET;
		break;
	default:
		break;
	}

	return orig;
}
```

The first test of [`merge_result()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L24) makes [`PCI_ERS_RESULT_NO_AER_DRIVER`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L937) win over anything, and the second makes a [`PCI_ERS_RESULT_NONE`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L922) vote change nothing. The switch then replaces a status of [`PCI_ERS_RESULT_CAN_RECOVER`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L925) or [`PCI_ERS_RESULT_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L934) with the vote, lets [`PCI_ERS_RESULT_DISCONNECT`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L931) give way only to [`PCI_ERS_RESULT_NEED_RESET`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L928), and keeps `PCI_ERS_RESULT_NEED_RESET` against every vote the first test does not catch. The figure ranks the status values by what can replace them.

```text
    How merge_result() lets the status climb and never fall
    ───────────────────────────────────────────────────────

      rank   status held                          votes that move it      up
             ┌──────────────────────────────────┐
        4    │ PCI_ERS_RESULT_NO_AER_DRIVER     │  none                   ▲
             ├──────────────────────────────────┤                         │
        3    │ PCI_ERS_RESULT_NEED_RESET        │  NO_AER_DRIVER          │
             ├──────────────────────────────────┤                         │
        2    │ PCI_ERS_RESULT_DISCONNECT        │  NEED_RESET,            │
             │                                  │  NO_AER_DRIVER          │
             ├──────────────────────────────────┤                         │
        1    │ PCI_ERS_RESULT_CAN_RECOVER       │  every vote but NONE,   │
             │ PCI_ERS_RESULT_RECOVERED         │  which replaces it      │
             └──────────────────────────────────┘

      a vote of PCI_ERS_RESULT_NONE leaves every rank as it is
      a vote of CAN_RECOVER or RECOVERED moves rank 1 within rank 1 and no other rank
      the status starts each round at rank 1: CAN_RECOVER before detection, RECOVERED before
      the MMIO and slot-reset rounds
```

A vote can therefore raise the status and never lower it, apart from the moves between [`PCI_ERS_RESULT_CAN_RECOVER`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L925) and [`PCI_ERS_RESULT_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L934) at the bottom rank. Once one vote asks for a reset, the status stays at [`PCI_ERS_RESULT_NEED_RESET`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L928) or above for the rest of the round, and a function other than a bridge whose driver lacks [`error_detected`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L943) fails the whole run, as the decision subsection reads from the code.

### Channel state records whether a function can be reached

Votes describe the subtree's plan, while drivers and the core also need to know, outside any callback, whether a function can be reached at all. The kernel keeps that answer in [`error_state`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L445) of every [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352), a value of type [`pci_channel_state_t`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L206); recovery writes it before it calls a driver, so the driver and any code it calls see the same state. The definition gives the type and its three values.

```c
/* include/linux/pci.h:199 */
/**
 * typedef pci_channel_state_t
 *
 * The pci_channel state describes connectivity between the CPU and
 * the PCI device.  If some PCI bus between here and the PCI device
 * has crashed or locked up, this info is reflected here.
 */
typedef unsigned int __bitwise pci_channel_state_t;

enum {
	/* I/O channel is in normal state */
	pci_channel_io_normal = (__force pci_channel_state_t) 1,

	/* I/O to channel is blocked */
	pci_channel_io_frozen = (__force pci_channel_state_t) 2,

	/* PCI card is dead */
	pci_channel_io_perm_failure = (__force pci_channel_state_t) 3,
};
```

[`pci_channel_io_normal`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L210) means I/O to the function works, [`pci_channel_io_frozen`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L213) that it is blocked, as after a fatal error or a DPC trigger, and [`pci_channel_io_perm_failure`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L216) that the function is gone. The type is `__bitwise` like the votes, so it is passed to [`error_detected`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L943) as a typed value. Two helpers in include/linux/pci.h turn the state into the questions callers ask, whether the channel is offline and whether the function is gone.

```c
/* include/linux/pci.h:613 */
static inline int pci_channel_offline(struct pci_dev *pdev)
{
	return (pdev->error_state != pci_channel_io_normal);
}
```

[`pci_channel_offline()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L613) is true for every state but [`pci_channel_io_normal`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L210), so a driver that tests it stops touching a frozen function as well as a dead one. The second helper reads the field without a lock, and its comment says why that is safe.

```c
/* include/linux/pci.h:2702 */
static inline bool pci_dev_is_disconnected(const struct pci_dev *dev)
{
	/*
	 * error_state is set in pci_dev_set_io_state() using xchg/cmpxchg()
	 * and read w/o common lock. READ_ONCE() ensures compiler cannot cache
	 * the value (e.g. inside the loop in pci_dev_wait()).
	 */
	return READ_ONCE(dev->error_state) == pci_channel_io_perm_failure;
}
```

[`pci_dev_is_disconnected()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2702) tests for [`pci_channel_io_perm_failure`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L216) alone, under `READ_ONCE()`, and its comment gives the reason, that the writers change the field with xchg and cmpxchg and readers take no common lock. The writer that recovery uses is [`pci_dev_set_io_state()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L737) in drivers/pci/pci.h; its kerneldoc states the rule that a permanently failed function stays failed.

```c
/* drivers/pci/pci.h:726 */
/**
 * pci_dev_set_io_state - Set the new error state if possible.
 *
 * @dev: PCI device to set new error_state
 * @new: the state we want dev to be in
 *
 * If the device is experiencing perm_failure, it has to remain in that state.
 * Any other transition is allowed.
 *
 * Returns true if state has been changed to the requested state.
 */
static inline bool pci_dev_set_io_state(struct pci_dev *dev,
					pci_channel_state_t new)
{
	pci_channel_state_t old;

	switch (new) {
	case pci_channel_io_perm_failure:
		xchg(&dev->error_state, pci_channel_io_perm_failure);
		return true;
	case pci_channel_io_frozen:
		old = cmpxchg(&dev->error_state, pci_channel_io_normal,
			      pci_channel_io_frozen);
		return old != pci_channel_io_perm_failure;
	case pci_channel_io_normal:
		old = cmpxchg(&dev->error_state, pci_channel_io_frozen,
			      pci_channel_io_normal);
		return old != pci_channel_io_perm_failure;
	default:
		return false;
	}
}
```

A request for [`pci_channel_io_perm_failure`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L216) is an unconditional `xchg()`, so any state can become permanent failure. A request for frozen or normal is a `cmpxchg()` that moves only from the other one of the two. For those two requests the function returns false only when it found [`pci_channel_io_perm_failure`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L216), so a request for the state the function already has succeeds and stores nothing. The figure draws the three states with every write recovery makes to the field.

```text
    How error_state moves between the three channel states
    ──────────────────────────────────────────────────────

                    ┌───────────────────────────────┐
      setup ───────▶│ pci_channel_io_normal         │◀────────┐
          ┌─────────┤                               │         │
          │         └─────────┬─────────────────────┘         │
          │                   │ ② ④                           │ ③ ④ ⑤ ⑥
          │                   │                               │
          │                   ▼                               │
          │         ┌───────────────────────────────┐         │
          │ ①       │ pci_channel_io_frozen         ├─────────┘
          │         └─────────┬─────────────────────┘
          │                   │ ①
          │                   │
          │                   ▼
          │         ┌───────────────────────────────┐  no edge leaves: both cmpxchg
          └────────▶│ pci_channel_io_perm_failure   │  calls find perm_failure and
                    └───────────────────────────────┘  store nothing


    ① pci_dev_set_io_state drivers/pci/pci.h:744  xchg stores perm_failure from any state
    ② pci_dev_set_io_state drivers/pci/pci.h:747  cmpxchg moves normal to frozen only
    ③ pci_dev_set_io_state drivers/pci/pci.h:751  cmpxchg moves frozen to normal only
    ④ report_error_detected err.c:61  asks for the state the caller passed in
    ⑤ report_slot_reset err.c:156  asks for normal before a driver's slot_reset
    ⑥ report_resume err.c:175  asks for normal before a driver's resume
```

① is the `xchg()` in [`pci_dev_set_io_state()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L737) that stores [`pci_channel_io_perm_failure`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L216) whatever the state was. ② is the first `cmpxchg()` in `pci_dev_set_io_state()`, which moves a normal function to frozen and leaves any other state alone. ③ is the second `cmpxchg()` in `pci_dev_set_io_state()`, which moves a frozen function back to normal. ④ is the call in [`report_error_detected()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L49) that asks for the state the service passed, frozen for a fatal error and normal for a non-fatal one. ⑤ is the call in [`report_slot_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L148) that asks for normal once the hierarchy has been reset. ⑥ is the call in [`report_resume()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L168) that asks for normal again before the driver resumes. Two writers that this page does not show also store into the field on x86 at v7.2. [`pci_setup_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2016) sets [`pci_channel_io_normal`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L210) at [`probe.c:2032`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2032) when the scan sets a function up, which belongs to enumeration, and [`pci_dev_set_disconnected()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L759) stores [`pci_channel_io_perm_failure`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L216) through [`pci_dev_set_io_state()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L737) for a function found gone, which belongs to the removal and resume paths that call it.

Four functions use [`pci_dev_set_disconnected()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L759) at v7.2, three as the callback of a [`pci_walk_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/bus.c#L461) and one by a direct call: [`pciehp_unconfigure_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_pci.c#L95) at [`pciehp_pci.c:105`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_pci.c#L105), [`pciehp_resume_noirq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L288) at [`pciehp_core.c:309`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L309), [`pci_pm_bridge_power_up_actions()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L596) at [`pci-driver.c:607`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L607), and, with [`CONFIG_HOTPLUG_PCI_ACPI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/Kconfig#L55) set, [`trim_stale_devices()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/acpiphp_glue.c#L653) at [`acpiphp_glue.c:670`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/acpiphp_glue.c#L670).

The channel state is thus one field per function that, on x86, only [`pci_dev_set_io_state()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L737) moves once the function is set up, and that recovery moves from normal to frozen and back. The services that start a recovery decide which of the two it requests first.

### Port services start recovery with a channel state and a reset

Recovery begins in a Port service that has found an error and knows which function to blame, and the service hands three things to [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210): the reporting device, the channel state and the reset callback. The state is frozen when the link below the Port can no longer be trusted, and the callback is the service's own way to reset the hierarchy. The table lists the callers at v7.2, four functions in aer.c, dpc.c and edr.c, with the context each one runs in.

| caller | runs in | channel state passed | reset callback |
|---|---|---|---|
| [`pci_aer_handle_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1170) | the threaded interrupt handler of the AER service, [`aer_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1449) | normal for a non-fatal error, frozen for a fatal one | [`aer_root_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1667) |
| [`aer_recover_work_func()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1218) | a work item that drains errors firmware reported, with [`CONFIG_ACPI_APEI_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Kconfig#L37) | normal or frozen by the same rule | [`aer_root_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1667) |
| [`dpc_handler()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L363) | the threaded interrupt handler of the DPC service | frozen | [`dpc_reset_link()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L148) |
| [`edr_handle_event()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/edr.c#L151) | the ACPI notify handler of the EDR support, with [`CONFIG_PCIE_EDR`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L140) | frozen | [`dpc_reset_link()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L148) |

For a function the AER service has found to be the source of an error, [`pci_aer_handle_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1170) picks the channel state from the severity; its kerneldoc and body follow.

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

A correctable error never reaches recovery, because the AER service clears the logged status, calls the driver's [`cor_error_detected`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L960) when the OS controls AER, and returns. A non-fatal error starts recovery with [`pci_channel_io_normal`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L210) and a fatal error with [`pci_channel_io_frozen`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L213), both with [`aer_root_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1667) as the reset. The second AER caller, for errors that firmware reports, is compiled only with [`CONFIG_ACPI_APEI_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Kconfig#L37), which the x86_64 defconfig leaves unset.

```c
/* drivers/pci/pcie/aer.c:1203 */
#ifdef CONFIG_ACPI_APEI_PCIEAER
... /* 14 lines, to :1218 */
static void aer_recover_work_func(struct work_struct *work)
{
	struct aer_recover_entry entry;
	struct pci_dev *pdev;

	while (kfifo_get(&aer_recover_ring, &entry)) {
		pdev = pci_get_domain_bus_and_slot(entry.domain, entry.bus,
						   entry.devfn);
		... /* 19 lines, to :1245 */
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

[`aer_recover_work_func()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1218) looks the function up by the domain, bus and devfn of each queued entry and makes the same two calls as the interrupt path for the entry's severity. The DPC service, built with [`CONFIG_PCIE_DPC`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L121), needs no severity test, because it starts recovery only for a contained link.

```c
/* drivers/pci/pcie/dpc.c:363 */
static irqreturn_t dpc_handler(int irq, void *context)
{
	struct pci_dev *pdev = context;

	/*
	 * According to PCIe r6.0 sec 6.7.6, errors are an expected side effect
	 * of async removal and should be ignored by software.
	 */
	if (dpc_is_surprise_removal(pdev)) {
		dpc_handle_surprise_removal(pdev);
		return IRQ_HANDLED;
	}

	pci_dev_get(pdev);
	dpc_process_error(pdev);

	/* We configure DPC so it only triggers on ERR_FATAL */
	pcie_do_recovery(pdev, pci_channel_io_frozen, dpc_reset_link);

	pci_dev_put(pdev);
	return IRQ_HANDLED;
}
```

[`dpc_handler()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L363) passes [`pci_channel_io_frozen`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L213) unconditionally, the comment saying that DPC is configured so that it "only triggers on ERR_FATAL", and passes [`dpc_reset_link()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L148) as the reset. A trigger that a surprise removal caused is handled apart and never reaches recovery. The EDR support, compiled only with [`CONFIG_PCIE_EDR`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L140), which the x86_64 defconfig leaves unset, reuses the DPC reset for a containment that firmware reports through an ACPI notification.

```c
/* drivers/pci/pcie/edr.c:151 */
static void edr_handle_event(acpi_handle handle, u32 event, void *data)
{
	struct pci_dev *pdev = data, *edev;
	pci_ers_result_t estate = PCI_ERS_RESULT_DISCONNECT;
	u16 status;

	if (event != ACPI_NOTIFY_DISCONNECT_RECOVER)
		return;

	/*
	 * pdev is a Root Port or Downstream Port that is still present and
	 * has triggered a containment event, e.g., DPC, so its child
	 * devices have been disconnected (ACPI r6.5, sec 5.6.6).
	 */
	pci_info(pdev, "EDR event received\n");
	... /* 27 lines, to :193 */
	dpc_process_error(edev);
	pci_aer_raw_clear_status(edev);

	/*
	 * Irrespective of whether the DPC event is triggered by ERR_FATAL
	 * or ERR_NONFATAL, since the link is already down, use the FATAL
	 * error recovery path for both cases.
	 */
	estate = pcie_do_recovery(edev, pci_channel_io_frozen, dpc_reset_link);

send_ost:

	/*
	 * If recovery is successful, send _OST(0xF, BDF << 16 | 0x80)
	 * to firmware. If not successful, send _OST(0xF, BDF << 16 | 0x81).
	 */
	if (estate == PCI_ERS_RESULT_RECOVERED) {
		pci_dbg(edev, "DPC port successfully recovered\n");
		pcie_clear_device_status(edev);
		acpi_send_edr_status(pdev, edev, EDR_OST_SUCCESS);
	} else {
		pci_dbg(edev, "DPC port recovery failed\n");
		acpi_send_edr_status(pdev, edev, EDR_OST_FAILED);
	}

	pci_dev_put(edev);
}
```

[`edr_handle_event()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/edr.c#L151) is the one caller that uses the result: it reports success or failure back to firmware through [`acpi_send_edr_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/edr.c#L132), the `_OST` evaluation its comment names, and clears the Port's Device Status after a success. Its comment explains why it passes [`pci_channel_io_frozen`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L213) for any trigger, since the link is already down. The figure follows one fatal error through the actors these callers set in motion.

```text
    One fatal error from report to verdict, across the actors
    ─────────────────────────────────────────────────────────

    time ↓                ╎                        ╎                        ╎                    ╎
    AER, DPC or EDR       ╎ recovery core          ╎ each driver below      ╎ reset callback     ╎ udev
                          ╎                        ╎ the bridge             ╎ on the bridge      ╎
    ──────────────────────┼────────────────────────┼────────────────────────┼────────────────────┼────────────────────
    error logged on dev   ╎                        ╎                        ╎                    ╎
    frozen, reset cb ─────▶ subtree resumed,       ╎                        ╎                    ╎
                          ╎ status CAN_RECOVER     ╎                        ╎                    ╎
                          ╎ error_detected ────────▶ told frozen;           ╎                    ╎
                          ╎                        ╎ I/O stopped            ╎                    ╎
                          ╎ votes merged ◀────────── vote NEED_RESET        ╎                    ╎
                          ╎ uevent per function ─────────────────────────────────────────────────▶ BEGIN_RECOVERY
                          ╎ status NEED_RESET      ╎                        ╎                    ╎
                          ╎ reset ──────────────────────────────────────────▶ hierarchy reset,   ╎
                          ╎ RECOVERED ◀────────────────────────────────────── RECOVERED          ╎
                          ╎ slot_reset ────────────▶ state normal;          ╎                    ╎
                          ╎                        ╎ config restored        ╎                    ╎
                          ╎ resume ────────────────▶ I/O restarted          ╎                    ╎
                          ╎ uevent per function ─────────────────────────────────────────────────▶ SUCCESSFUL_
                          ╎                        ╎                        ╎                    ╎ RECOVERY
                          ╎ status cleared,        ╎                        ╎                    ╎
    RECOVERED returned ◀─── runtime PM released    ╎                        ╎                    ╎
    EDR answers _OST      ╎                        ╎                        ╎                    ╎
```

Every caller waits for [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) to return before it goes on, so a recovery runs in the context of the service that started it, a threaded interrupt handler, a work item or the ACPI notify work. The reporting device and the state the caller chose are where the reading of [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) begins.

So far, a driver has supplied its callbacks through [`err_handler`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L1032), its votes merge into a status that only climbs, and every function carries a channel state that [`pci_dev_set_io_state()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L737) moves. A service has decided to recover and passes the reporting device, the channel state and its reset callback to [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210).

### The bridge bounds the subtree that recovers

The first decision of [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) is which functions take part. An error that a Port reports concerns the Port and the hierarchy below it, and an error that an Endpoint reports can disturb the link it shares with the other functions below the same Port, so recovery always acts on the subtree below one bridge. The function is long, and the outline names its pieces in the order the following subsections read them.

| piece | lines | stage |
|---|---|---|
| ❶ | err.c:210-235 | finds the bridge whose subtree recovers |
| ❷ | err.c:236-237 | raises the runtime PM usage count of the subtree |
| ❸ | err.c:238-243 | tells every driver of the error with the caller's channel state |
| ❹ | err.c:244-249 | runs the MMIO round when the status is CAN_RECOVER |
| ❺ | err.c:250-257 | calls the reset callback for NEED_RESET or a frozen channel |
| ❻ | err.c:258-268 | runs the slot reset round when the status is NEED_RESET |
| ❼ | err.c:269-290 | resumes the drivers, clears the error status and returns success |
| ❽ | err.c:291-299 | drops the usage count and reports permanent failure |

Piece ❶ of [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) holds the signature, the locals and the choice of the bridge, which its comment explains.

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

	/*
	 * If the error was detected by a Root Port, Downstream Port, RCEC,
	 * or RCiEP, recovery runs on the device itself.  For Ports, that
	 * also includes any subordinate devices.
	 *
	 * If it was detected by another device (Endpoint, etc), recovery
	 * runs on the device and anything else under the same Port, i.e.,
	 * everything under "bridge".
	 */
	if (type == PCI_EXP_TYPE_ROOT_PORT ||
	    type == PCI_EXP_TYPE_DOWNSTREAM ||
	    type == PCI_EXP_TYPE_RC_EC ||
	    type == PCI_EXP_TYPE_RC_END)
		bridge = dev;
	else
		bridge = pci_upstream_bridge(dev);

```

The Device/Port Type that [`pci_pcie_type()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2678) returns decides the bridge. A Root Port, a Downstream Port, an RCEC or an RCiEP, the types [`PCI_EXP_TYPE_ROOT_PORT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L488), [`PCI_EXP_TYPE_DOWNSTREAM`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L490), [`PCI_EXP_TYPE_RC_EC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L494) and [`PCI_EXP_TYPE_RC_END`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L493), is its own bridge, and any other function, an Endpoint or an Upstream Port, takes the bridge above it from [`pci_upstream_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L819). The local `host` is the [`struct pci_host_bridge`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L628) above the reporting device, which [`pci_find_host_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/host-bridge.c#L20) finds now and piece ❼ reads. [`pci_upstream_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L819) is a short inline helper of include/linux/pci.h.

```c
/* include/linux/pci.h:819 */
static inline struct pci_dev *pci_upstream_bridge(struct pci_dev *dev)
{
	dev = pci_physfn(dev);
	if (pci_is_root_bus(dev->bus))
		return NULL;

	return dev->bus->self;
}
```

After the [`pci_physfn()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L597) step, which returns an ordinary function unchanged, the helper returns the [`self`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L707) of the function's bus, the bridge function above it, and NULL on a root bus. Every later step reaches the subtree through [`pci_walk_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L200), whose kerneldoc states its two cases.

```c
/* drivers/pci/pcie/err.c:187 */
/**
 * pci_walk_bridge - walk bridges potentially AER affected
 * @bridge:	bridge which may be a Port, an RCEC, or an RCiEP
 * @cb:		callback to be called for each device found
 * @userdata:	arbitrary pointer to be passed to callback
 *
 * If the device provided is a bridge, walk the subordinate bus, including
 * any bridged devices on buses under this bus.  Call the provided callback
 * on each device found.
 *
 * If the device provided has no subordinate bus, e.g., an RCEC or RCiEP,
 * call the callback on the device itself.
 */
static void pci_walk_bridge(struct pci_dev *bridge,
			    int (*cb)(struct pci_dev *, void *),
			    void *userdata)
{
	if (bridge->subordinate)
		pci_walk_bus(bridge->subordinate, cb, userdata);
	else
		cb(bridge, userdata);
}
```

A bridge with a [`subordinate`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L355) bus hands that bus to [`pci_walk_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/bus.c#L461), so the callback runs for every function on the bus and below it and never for the bridge itself. An RCEC or an RCiEP has no bus below it, and the callback runs on that function alone. The traversal and its lock come from the bus code in bus.c.

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

[`pci_walk_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/bus.c#L461) holds [`pci_bus_sem`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/search.c#L17) for reading over the whole traversal, so the bus lists it follows cannot change while one round runs, and it leaves the order to [`__pci_walk_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/bus.c#L408).

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

The callback runs on a function before the traversal descends into the bus behind it, so an Upstream Port comes before its Downstream Ports and each Downstream Port before the functions below it. A nonzero return would stop the traversal, and every callback that err.c passes returns 0, so each round reaches every function of the subtree. The figure places the two cases on one hierarchy.

```text
    The place of the bridge decides which functions one recovery visits
    ───────────────────────────────────────────────────────────────────

                              ┌───────────────────────────┐
                              │    Root Port 00:1c.0      │
                              └─────────────┬─────────────┘
                                            │
    ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ──┼── ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  A: the walk starts below
                                            │                                     the Root Port
                                ┌───────────┴───────────┐
                                │ Upstream Port 01:00.0 │
                                │ pcieport              │
                                └───────────┬───────────┘
                                            │
                        ┌───────────────────┴───────────────────┐
                        │                                       │
            ┌───────────┴───────────┐               ┌───────────┴───────────┐
            │ Downstream 02:01.0    │               │ Downstream 02:02.0    │
            │ pcieport              │               │ pcieport              │
            └───────────┬───────────┘               └───────────┬───────────┘
                        │                                       │
                        │                       ─ ─ ─ ─ ─ ─ ─ ──┼── ─ ─ ─ ─ ─  B: the walk starts below
                        │                                       │                 Downstream 02:02.0
            ┌───────────┴───────────┐               ┌───────────┴───────────┐
            │ Endpoint 03:00.0      │               │ Endpoint 04:00.0      │
            │ nvme                  │               │ nvme                  │
            └───────────────────────┘               └───────────────────────┘

    A  the Root Port reports: the bridge is 00:1c.0, and the walk visits 01:00.0,
       02:01.0, 03:00.0, 02:02.0 and 04:00.0 in that order, never 00:1c.0 itself
    B  Endpoint 04:00.0 reports: the bridge is the Port above it, 02:02.0, and the
       walk visits 04:00.0 alone
       an RCEC or an RCiEP has no bus below it, and is visited alone
```

The boundary under the bridge is the same for every round of one recovery, because each round calls [`pci_walk_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L200) with the same `bridge`, and the reset callback receives that `bridge` too. The subtree below the chosen bridge is the set of functions that every following step of [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) visits.

### Runtime PM keeps the subtree resumed for the whole recovery

A function below the bridge can be runtime-suspended when the error arrives, or become idle while recovery runs, and the steps that follow need it powered to answer its driver and the reset. Recovery therefore resumes every function of the subtree before it calls any driver and keeps each function's runtime PM usage count raised until it ends. Piece ❷ of [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) is that step.

```c
/* drivers/pci/pcie/err.c:236 */
	pci_walk_bridge(bridge, pci_pm_runtime_get_sync, NULL);

```

The round calls [`pci_pm_runtime_get_sync()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L89) on every function of the subtree through [`pci_walk_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L200), with no data. The two functions of the hold are defined together in err.c.

```c
/* drivers/pci/pcie/err.c:89 */
static int pci_pm_runtime_get_sync(struct pci_dev *pdev, void *data)
{
	pm_runtime_get_sync(&pdev->dev);
	return 0;
}

static int pci_pm_runtime_put(struct pci_dev *pdev, void *data)
{
	pm_runtime_put(&pdev->dev);
	return 0;
}
```

Both are adapters that give [`pm_runtime_get_sync()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pm_runtime.h#L511) and [`pm_runtime_put()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pm_runtime.h#L549) the signature [`pci_walk_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/bus.c#L461) expects, and both return 0 so that the traversal goes on. The runtime PM helpers are inline wrappers in [`pm_runtime.h`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pm_runtime.h), and the kerneldoc of the first states what it does to the usage count.

```c
/* include/linux/pm_runtime.h:497 */
/**
 * pm_runtime_get_sync - Bump up usage counter of a device and resume it.
 * @dev: Target device.
 *
 * Bump up the runtime PM usage counter of @dev and carry out runtime-resume of
 * it synchronously.
 *
 * The possible return values of this function are the same as for
 * pm_runtime_resume() and the runtime PM usage counter of @dev remains
 * incremented in all cases, even if it returns an error code.
 * Consider using pm_runtime_resume_and_get() instead of it, especially
 * if its return value is checked by the caller, as this is likely to result
 * in cleaner code.
 */
static inline int pm_runtime_get_sync(struct device *dev)
{
	return __pm_runtime_resume(dev, RPM_GET_PUT);
}
```

[`pm_runtime_get_sync()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pm_runtime.h#L511) raises the usage count and resumes the device synchronously, and the count stays raised whatever the resume returned. Commit commit [002bf2fbc00e](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=002bf2fbc00e5c4b95fb167287e2ae7d1973281e) ("PCI/AER: Block runtime suspend when handling errors") added the hold, and its message says the raised count prevents any later request to runtime-suspend the device and resumes a device left in D3hot. The hold depends on [`CONFIG_PM`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L217), which [`CONFIG_PM_SLEEP`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L140) selects. The release is the second wrapper.

```c
/* include/linux/pm_runtime.h:542 */
/**
 * pm_runtime_put - Drop device usage counter and queue up "idle check" if 0.
 * @dev: Target device.
 *
 * Decrement the runtime PM usage counter of @dev and if it turns out to be
 * equal to 0, queue up a work item for @dev like in pm_request_idle().
 */
static inline void pm_runtime_put(struct device *dev)
{
	__pm_runtime_idle(dev, RPM_GET_PUT | RPM_ASYNC);
}
```

[`pm_runtime_put()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pm_runtime.h#L549) drops the count and, when it reaches zero, queues an idle check as a work item, so the release returns at once and the function may suspend again later. [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) calls [`pci_pm_runtime_put()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L95) on both of its exits, after the resume round on success and before the failure notices on failure, as pieces ❼ and ❽ show. The figure draws the brackets that hold during one recovery.

```text
    What holds while one recovery runs
    ──────────────────────────────────

    time ──────────────────────────────────────────────────────────────────────────────────────────▶
    runtime PM usage count raised       ├───────────────────────────────────────────────────────┤
                                         detect     mmio    reset     slot_reset   resume
    a round holds pci_bus_sem to read    ├────────┤ ├────┤            ├────────┤   ├──────┤
    the reset callback                                      ├──────┤
    one callback holds device_lock        ├┤ ├┤ ├┤
                                        ╎                                                       ╎
    a function below the bridge         ╎ resumed first, then kept from runtime suspend         ╎ idle check
                                                                                                  queued

    mmio runs when detection leaves CAN_RECOVER, the reset when the status is NEED_RESET or the
    state frozen, slot_reset when the status is NEED_RESET; a failure ends the count at once
```

Inside the hold, each round of callbacks takes [`pci_bus_sem`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/search.c#L17) for reading and each callback the device lock of its function, while the reset callback runs between rounds with neither lock taken by err.c. The first round inside the hold is detection.

### Detection asks every function below the bridge for a vote

Detection tells each driver about the error and collects its first vote, and every later step depends on the status it leaves. Piece ❸ of [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) prints a dynamic-debug message and runs one round with the callback that matches the channel state the service passed.

```c
/* drivers/pci/pcie/err.c:238 */
	pci_dbg(bridge, "broadcast error_detected message\n");
	if (state == pci_channel_io_frozen)
		pci_walk_bridge(bridge, report_frozen_detected, &status);
	else
		pci_walk_bridge(bridge, report_normal_detected, &status);

```

A frozen channel selects [`report_frozen_detected()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L101) and any other state [`report_normal_detected()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L106), each passed to [`pci_walk_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L200) with the address of the local `status` as its data. The two are one-line adapters around the function that does the work.

```c
/* drivers/pci/pcie/err.c:101 */
static int report_frozen_detected(struct pci_dev *dev, void *data)
{
	return report_error_detected(dev, pci_channel_io_frozen, data);
}

static int report_normal_detected(struct pci_dev *dev, void *data)
{
	return report_error_detected(dev, pci_channel_io_normal, data);
}
```

Each adapter fixes the channel state that [`report_error_detected()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L49) receives, because the traversal hands a callback one data pointer, and that pointer carries the status. The table lists what [`report_error_detected()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L49) decides for one function, in the order its code tests the conditions.

| condition on the function | vote | what else happens |
|---|---|---|
| it is gone, [`pci_dev_is_disconnected()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2702) true | [`PCI_ERS_RESULT_DISCONNECT`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L931) | its driver is not called |
| [`pci_dev_set_io_state()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L737) refuses the requested state | [`PCI_ERS_RESULT_NONE`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L922) | "can't recover (state transition ...)" is printed |
| no driver, no table or no [`error_detected`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L943), and no bridge header | [`PCI_ERS_RESULT_NO_AER_DRIVER`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L937) | "can't recover (no error_detected callback)" is printed |
| no callback, on a bridge function | [`PCI_ERS_RESULT_NONE`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L922) | nothing |
| its driver has [`error_detected`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L943) | the driver's vote | the driver runs with the channel state already set |

[`report_error_detected()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L49) makes that decision under the device lock of the function and then reports and merges the vote.

```c
/* drivers/pci/pcie/err.c:49 */
static int report_error_detected(struct pci_dev *dev,
				 pci_channel_state_t state,
				 enum pci_ers_result *result)
{
	struct pci_driver *pdrv;
	pci_ers_result_t vote;
	const struct pci_error_handlers *err_handler;

	device_lock(&dev->dev);
	pdrv = dev->driver;
	if (pci_dev_is_disconnected(dev)) {
		vote = PCI_ERS_RESULT_DISCONNECT;
	} else if (!pci_dev_set_io_state(dev, state)) {
		pci_info(dev, "can't recover (state transition %u -> %u invalid)\n",
			dev->error_state, state);
		vote = PCI_ERS_RESULT_NONE;
	} else if (!pdrv || !pdrv->err_handler ||
		   !pdrv->err_handler->error_detected) {
		/*
		 * If any device in the subtree does not have an error_detected
		 * callback, PCI_ERS_RESULT_NO_AER_DRIVER prevents subsequent
		 * error callbacks of "any" device in the subtree, and will
		 * exit in the disconnected error state.
		 */
		if (dev->hdr_type != PCI_HEADER_TYPE_BRIDGE) {
			vote = PCI_ERS_RESULT_NO_AER_DRIVER;
			pci_info(dev, "can't recover (no error_detected callback)\n");
		} else {
			vote = PCI_ERS_RESULT_NONE;
		}
	} else {
		err_handler = pdrv->err_handler;
		vote = err_handler->error_detected(dev, state);
	}
	pci_uevent_ers(dev, vote);
	*result = merge_result(*result, vote);
	device_unlock(&dev->dev);
	return 0;
}
```

[`report_error_detected()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L49) takes the device lock of the function first, which keeps the driver bound while it votes. The [`hdr_type`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L368) test spares a bridge function without a callback, whose [`PCI_ERS_RESULT_NONE`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L922) leaves the status alone, while any other function without one votes [`PCI_ERS_RESULT_NO_AER_DRIVER`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L937), which the comment says prevents the later callbacks of every function in the subtree. Every outcome ends in [`pci_uevent_ers()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L1625) with the vote and in [`merge_result()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L24), so user space hears of each function and the status sees each vote in the traversal order. [`pci_uevent_ers()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L1625) turns a vote into a change uevent and is compiled with [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28); the other conditions of its `#if` belong to other architectures.

```c
/* drivers/pci/pci-driver.c:1619 */
#if defined(CONFIG_PCIEAER) || defined(CONFIG_EEH) || defined(CONFIG_S390)
/**
 * pci_uevent_ers - emit a uevent during recovery path of PCI device
 * @pdev: PCI device undergoing error recovery
 * @err_type: type of error event
 */
void pci_uevent_ers(struct pci_dev *pdev, enum pci_ers_result err_type)
{
	int idx = 0;
	char *envp[3];

	switch (err_type) {
	case PCI_ERS_RESULT_NONE:
	case PCI_ERS_RESULT_CAN_RECOVER:
	case PCI_ERS_RESULT_NEED_RESET:
		envp[idx++] = "ERROR_EVENT=BEGIN_RECOVERY";
		envp[idx++] = "DEVICE_ONLINE=0";
		break;
	case PCI_ERS_RESULT_RECOVERED:
		envp[idx++] = "ERROR_EVENT=SUCCESSFUL_RECOVERY";
		envp[idx++] = "DEVICE_ONLINE=1";
		break;
	case PCI_ERS_RESULT_DISCONNECT:
		envp[idx++] = "ERROR_EVENT=FAILED_RECOVERY";
		envp[idx++] = "DEVICE_ONLINE=0";
		break;
	default:
		break;
	}

	if (idx > 0) {
		envp[idx++] = NULL;
		kobject_uevent_env(&pdev->dev.kobj, KOBJ_CHANGE, envp);
	}
}
#endif
```

A vote of [`PCI_ERS_RESULT_NONE`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L922), [`PCI_ERS_RESULT_CAN_RECOVER`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L925) or [`PCI_ERS_RESULT_NEED_RESET`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L928) announces "ERROR_EVENT=BEGIN_RECOVERY" with "DEVICE_ONLINE=0", [`PCI_ERS_RESULT_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L934) announces "ERROR_EVENT=SUCCESSFUL_RECOVERY" with "DEVICE_ONLINE=1", and [`PCI_ERS_RESULT_DISCONNECT`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L931) announces "ERROR_EVENT=FAILED_RECOVERY". [`PCI_ERS_RESULT_NO_AER_DRIVER`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L937) matches no case, so a function without a callback produces no uevent during detection. [`kobject_uevent_env()`](https://elixir.bootlin.com/linux/v7.2/source/lib/kobject_uevent.c#L476) sends the event as `KOBJ_CHANGE` on the function's device. The figure follows one detection round over the hierarchy of the topology figure, for a fatal error the Root Port reported, with no driver bound to 04:00.0.

```text
    What the detection round leaves on each function, for a fatal error at the Root Port
    ────────────────────────────────────────────────────────────────────────────────────

    walk order        01:00.0      02:01.0      03:00.0      02:02.0      04:00.0
                    ┌────────────┬────────────┬────────────┬────────────┬────────────┐
    driver          │ pcieport   │ pcieport   │ nvme       │ pcieport   │ none       │
                    └─────┬──────┴─────┬──────┴─────┬──────┴─────┬──────┴─────┬──────┘
    visited               ▼            ▼            ▼            ▼            ▼
    error_state       frozen       frozen       frozen       frozen       frozen
    vote              NEED_RESET   NEED_RESET   NEED_RESET   NEED_RESET   NO_AER_DRIVER
    uevent            BEGIN_       BEGIN_       BEGIN_       BEGIN_       none
                      RECOVERY     RECOVERY     RECOVERY     RECOVERY
    status after      NEED_RESET   NEED_RESET   NEED_RESET   NEED_RESET   NO_AER_DRIVER

    the status is CAN_RECOVER before the first function; with a driver bound to 04:00.0 that votes
    NEED_RESET, the round ends at NEED_RESET and recovery goes on to the reset
```

Detection thus leaves every reachable function of the subtree in the channel state the service asked for, every driver informed and one status for the next step to read. A single function without a driver has turned that status into [`PCI_ERS_RESULT_NO_AER_DRIVER`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L937), which no later vote changes.

### The status decides between MMIO re-enabling and a reset

After detection the status says what the drivers need. When every vote allowed recovery without a reset, the drivers may access their device registers again before anything else happens, and when one vote asked for a reset, or the service said the channel is frozen, the hierarchy is reset first. Piece ❹ of [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) is the MMIO round.

```c
/* drivers/pci/pcie/err.c:244 */
	if (status == PCI_ERS_RESULT_CAN_RECOVER) {
		status = PCI_ERS_RESULT_RECOVERED;
		pci_dbg(bridge, "broadcast mmio_enabled message\n");
		pci_walk_bridge(bridge, report_mmio_enabled, &status);
	}

```

The status starts the round at [`PCI_ERS_RESULT_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L934), so a subtree whose drivers have no [`mmio_enabled`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L947) member, which then casts no vote, counts as recovered. [`report_mmio_enabled()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L129) is the callback of the round for each function.

```c
/* drivers/pci/pcie/err.c:129 */
static int report_mmio_enabled(struct pci_dev *dev, void *data)
{
	struct pci_driver *pdrv;
	pci_ers_result_t vote, *result = data;
	const struct pci_error_handlers *err_handler;

	device_lock(&dev->dev);
	pdrv = dev->driver;
	if (!pdrv || !pdrv->err_handler || !pdrv->err_handler->mmio_enabled)
		goto out;

	err_handler = pdrv->err_handler;
	vote = err_handler->mmio_enabled(dev);
	*result = merge_result(*result, vote);
out:
	device_unlock(&dev->dev);
	return 0;
}
```

The callback calls the driver's [`mmio_enabled`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L947) under the device lock and merges the vote, and a function without the member is skipped. Unlike detection, it writes no channel state and sends no uevent. Piece ❺ of [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) decides on the reset.

```c
/* drivers/pci/pcie/err.c:250 */
	if (status == PCI_ERS_RESULT_NEED_RESET ||
	    state == pci_channel_io_frozen) {
		if (reset_subordinates(bridge) != PCI_ERS_RESULT_RECOVERED) {
			pci_warn(bridge, "subordinate device reset failed\n");
			goto failed;
		}
	}

```

The reset runs when the status is [`PCI_ERS_RESULT_NEED_RESET`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L928) or the channel is frozen, so a fatal error always resets the hierarchy, whatever the drivers voted. The callback is the one the service passed, called once with the bridge, and any result but [`PCI_ERS_RESULT_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L934) prints "subordinate device reset failed" and jumps to the failure path. According to its message, commit commit [d0a2dee7d458](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=d0a2dee7d4585a7ebab45bf63eebeb8b6944e88f) ("PCI/AER: Allow drivers to opt in to Bus Reset on Non-Fatal Errors") added the `PCI_ERS_RESULT_NEED_RESET` test so that a driver can ask for a reset after a non-fatal error. The status is written in several places across these rounds, by [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) and by the callbacks through their data pointer, and the figure draws one run in which every round takes place.

```text
    How the status changes across the rounds of one recovery
    ────────────────────────────────────────────────────────

    time ────────────────────────────────────────────────────────────────────────────────────────────▶
    event        start         detect   MMIO                 reset  slot                 test
                 ▼             ▼        ▼           ▼        ▼      ▼           ▼        ▼
                ┌─────────────┬────────┬───────────┬────────┬──────┬───────────┬────────┬───────────
    status      │ CAN_RECOVER │ merged │ RECOVERED │ merged │ kept │ RECOVERED │ merged │ RECOVERED?
                └─────────────┴────────┴───────────┴────────┴──────┴───────────┴────────┴───────────
                 ➊             ➋        ➌           ➍               ➎           ➏

    ➊ pcie_do_recovery err.c:216  starts the status at CAN_RECOVER
    ➋ report_error_detected err.c:84  merges each function's detection vote
    ➌ pcie_do_recovery err.c:245  restarts at RECOVERED when detection left CAN_RECOVER
    ➍ report_mmio_enabled err.c:142  merges each mmio_enabled vote
    ➎ pcie_do_recovery err.c:264  restarts at RECOVERED when the status is NEED_RESET
    ➏ report_slot_reset err.c:162  merges each slot_reset vote

    one run in which every round takes place; a round that does not run leaves its segment out
```

➊ is the initializer in [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) that starts the status at [`PCI_ERS_RESULT_CAN_RECOVER`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L925). ➋ is the merge in [`report_error_detected()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L49) that folds each detection vote into it. ➌ is the assignment in `pcie_do_recovery()` that restarts it at [`PCI_ERS_RESULT_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L934) for the MMIO round. ➍ is the merge in [`report_mmio_enabled()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L129) for each [`mmio_enabled`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L947) vote. ➎ is the assignment in `pcie_do_recovery()` that restarts it at `PCI_ERS_RESULT_RECOVERED` for the slot reset round. ➏ is the merge in [`report_slot_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L148) for each [`slot_reset`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L950) vote.

The status is a local variable of [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210), and the report functions reach it through their `data` argument, named `result` in their bodies, so no other code writes it. Between ➍ and ➎ the reset callback runs and leaves the status as it was; the next two subsections read the callbacks the services pass.

### aer_root_reset resets the hierarchy with the AER interrupt masked

The AER service has no containment of its own, so its reset callback resets the hierarchy itself, and it keeps the root's error interrupt masked while the reset makes the link go down and come back. [`aer_root_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1667) serves the three kinds of bridge that AER recovers, which its kerneldoc names. The outline gives its pieces.

| piece | lines | stage |
|---|---|---|
| Ⓐ | aer.c:1667-1685 | finds the function that holds the AER root registers |
| Ⓑ | aer.c:1686-1707 | masks the root's error interrupt and resets the hierarchy or the function |
| Ⓒ | aer.c:1708-1717 | clears Root Error Status, unmasks the interrupt and returns the verdict |

Piece Ⓐ of [`aer_root_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1667) looks for the root, the function whose AER capability has Root Error Command and Root Error Status.

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

```

For an RCiEP the root is the RCEC that collects its errors, [`rcec`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L375), which the comment allows to be NULL when firmware keeps control of AER. For any other bridge the root is the Root Port that [`pcie_find_root_port()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2690) finds at the function or above it, and the local `aer` is the root's [`aer_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370), or 0 without a root. The helper climbs with [`pci_upstream_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L819).

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

The loop returns the first function of type Root Port on the way up and NULL when it leaves the root bus without one. An RCEC belongs to the Root Complex and is no Root Port, so the loop leaves its root bus without a match, and for an RCEC the local `root` is NULL, `aer` is 0, and the interrupt steps below are skipped. Piece Ⓑ of [`aer_root_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1667) masks the interrupt and resets.

```c
/* drivers/pci/pcie/aer.c:1686 */
	/*
	 * If the platform retained control of AER, an RCiEP may not have
	 * an RCEC visible to us, so dev->rcec ("root") may be NULL.  In
	 * that case, firmware is responsible for these registers.
	 */
	aer = root ? root->aer_cap : 0;

	if ((host->native_aer || pcie_ports_native) && aer)
		aer_disable_irq(root);

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

```

When the OS controls AER, through [`native_aer`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L653) or [`pcie_ports_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L614), and the root has an AER capability, [`aer_disable_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1502) masks the root's interrupt. An RCEC or an RCiEP is reset by itself with a Function Level Reset from [`pcie_reset_flr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4402), and a Root Port or Downstream Port has the bus below it reset by [`pci_bus_error_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L5686); both outcomes are printed. The two interrupt helpers are a pair in aer.c.

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

[`aer_enable_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1491) and [`aer_disable_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1502) set and clear the three reporting enables of Root Error Command, the bits [`ROOT_PORT_INTR_ON_MESG_MASK`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L119) collects, with a read and a write of the whole register. The two reset helpers come from the reset code of pci.c.

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

[`pcie_reset_flr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4402) refuses with `-ENOTTY` a function that a quirk marked or whose cached Device Capabilities lack FLR, and otherwise performs the reset through [`pcie_flr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4362). The bus reset for a Port is a thin wrapper.

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

int pci_try_reset_bridge(struct pci_dev *bridge)
{
	return pci_reset_bridge(bridge, PCI_RESET_RESTORE);
}
```

[`pci_bus_error_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L5686) resets the bus below the bridge through [`pci_reset_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L5645), which the reset code owns, with [`PCI_RESET_NO_RESTORE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L5634), where its sibling [`pci_try_reset_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L5691) asks for [`PCI_RESET_RESTORE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L5633). Restoring the functions' configuration therefore falls to the drivers' [`slot_reset`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L950) callbacks, as the NVMe and port driver callbacks do with [`pci_restore_state()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L1826). Piece Ⓒ of [`aer_root_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1667) undoes the masking and gives the verdict.

```c
/* drivers/pci/pcie/aer.c:1708 */
	if ((host->native_aer || pcie_ports_native) && aer) {
		/* Clear Root Error Status */
		pci_read_config_dword(root, aer + PCI_ERR_ROOT_STATUS, &reg32);
		pci_write_config_dword(root, aer + PCI_ERR_ROOT_STATUS, reg32);

		aer_enable_irq(root);
	}

	return rc ? PCI_ERS_RESULT_DISCONNECT : PCI_ERS_RESULT_RECOVERED;
}
```

The root's Root Error Status is read and written back, which the comment calls clearing it, so the status the reset left latched is cleared before the interrupt is unmasked. A zero result from the reset makes the verdict [`PCI_ERS_RESULT_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L934), and any error [`PCI_ERS_RESULT_DISCONNECT`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L931), which sends [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) to its failure path. The figure draws what holds around the reset.

```text
    What aer_root_reset() holds around the reset, when the OS controls AER
    ──────────────────────────────────────────────────────────────────────

    time ──────────────────────────────────────────────────────────────────────────────────────▶
    Root Error Command enables cleared          ├───────────────────────────────────────┤
    the reset of the hierarchy, or the FLR          ├─────────────────────────┤
                                                ╎                                       ╎
    Root Error Status                           ╎ messages received stay latched        ╎ written back
                                                                                          to clear it
```

The AER callback thus resets the whole hierarchy below a Port, or one RCEC or RCiEP, with the root silenced, and it leaves the functions' configuration to their drivers.

### dpc_reset_link waits for the contained link and releases it

DPC has contained the error by the time its reset callback runs, because the Port has taken its link down in hardware. The callback's work is to wait for that link to be down, release the Port from containment and wait for the functions below it to answer again, while other code can wait for its verdict. [`dpc_reset_link()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L148) does that in one function.

```c
/* drivers/pci/pcie/dpc.c:148 */
pci_ers_result_t dpc_reset_link(struct pci_dev *pdev)
{
	pci_ers_result_t ret;
	u16 cap;

	set_bit(PCI_DPC_RECOVERING, &pdev->priv_flags);

	/*
	 * DPC disables the Link automatically in hardware, so it has
	 * already been reset by the time we get here.
	 */
	cap = pdev->dpc_cap;

	/*
	 * Wait until the Link is inactive, then clear DPC Trigger Status
	 * to allow the Port to leave DPC.
	 */
	if (!pcie_wait_for_link(pdev, false))
		pci_info(pdev, "Data Link Layer Link Active not cleared in 1000 msec\n");

	if (pdev->dpc_rp_extensions && dpc_wait_rp_inactive(pdev)) {
		clear_bit(PCI_DPC_RECOVERED, &pdev->priv_flags);
		ret = PCI_ERS_RESULT_DISCONNECT;
		goto out;
	}

	pci_write_config_word(pdev, cap + PCI_EXP_DPC_STATUS,
			      PCI_EXP_DPC_STATUS_TRIGGER);

	if (pci_bridge_wait_for_secondary_bus(pdev, "DPC")) {
		clear_bit(PCI_DPC_RECOVERED, &pdev->priv_flags);
		ret = PCI_ERS_RESULT_DISCONNECT;
	} else {
		set_bit(PCI_DPC_RECOVERED, &pdev->priv_flags);
		ret = PCI_ERS_RESULT_RECOVERED;
	}
out:
	clear_bit(PCI_DPC_RECOVERING, &pdev->priv_flags);
	wake_up_all(&dpc_completed_waitqueue);
	return ret;
}
```

[`dpc_reset_link()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L148) sets [`PCI_DPC_RECOVERING`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L770) in [`priv_flags`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L585) first and clears it last, waking every waiter on [`dpc_completed_waitqueue`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L78). Between the two it waits for the link to go down, gives up with [`PCI_ERS_RESULT_DISCONNECT`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L931) when a Root Port with [`dpc_rp_extensions`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L538) stays busy, writes Trigger Status, [`PCI_EXP_DPC_STATUS_TRIGGER`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1097), to release the Port, and waits for the bus below. [`PCI_DPC_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L769) records the verdict for [`pci_dpc_recovered()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L103), whose kerneldoc says the PCIe hotplug driver calls it to ignore the link events DPC causes; the bits and their other writers belong to DPC and hotplug and are not drawn here. The link wait is [`pcie_wait_for_link()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4678) with `active` false.

```c
/* drivers/pci/pci.c:4671 */
/**
 * pcie_wait_for_link - Wait until link is active or inactive
 * @pdev: Bridge device
 * @active: waiting for active or inactive?
 *
 * Use this to wait till link becomes active or inactive.
 */
bool pcie_wait_for_link(struct pci_dev *pdev, bool active)
{
	return pcie_wait_for_link_delay(pdev, active, 100);
}
```

The wrapper passes a delay of 100 ms and leaves the work to [`pcie_wait_for_link_delay()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4629).

```c
/* drivers/pci/pci.c:4629 */
static bool pcie_wait_for_link_delay(struct pci_dev *pdev, bool active,
				     int delay)
{
	int rc;

	/*
	 * Some controllers might not implement link active reporting. In this
	 * case, we wait for 1000 ms + any delay requested by the caller.
	 */
	if (!pdev->link_active_reporting) {
		msleep(PCIE_LINK_RETRAIN_TIMEOUT_MS + delay);
		return true;
	}
	... /* 10 lines, to :4652 */
	if (active)
		msleep(20);
	rc = pcie_wait_for_link_status(pdev, false, active);
	if (active) {
		if (rc)
			rc = pcie_failed_link_retrain(pdev);
		if (rc)
			return false;

		msleep(delay);
		return true;
	}

	if (rc)
		return false;

	return true;
}
```

A Port whose [`link_active_reporting`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L507) bit is clear cannot report the link state, so the function sleeps [`PCIE_LINK_RETRAIN_TIMEOUT_MS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L22) plus the delay and reports success. For a Port that reports it, a wait for an inactive link goes straight to [`pcie_wait_for_link_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4535) with the Data Link Layer Link Active bit, [`PCI_EXP_LNKSTA_DLLLA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L593), selected, and a timeout there makes the function return false.

```c
/* drivers/pci/pci.c:4526 */
/**
 * pcie_wait_for_link_status - Wait for link status change
 * @pdev: Device whose link to wait for.
 * @use_lt: Use the LT bit if TRUE, or the DLLLA bit if FALSE.
 * @active: Waiting for active or inactive?
 *
 * Return 0 if successful, or -ETIMEDOUT if status has not changed within
 * PCIE_LINK_RETRAIN_TIMEOUT_MS milliseconds.
 */
static int pcie_wait_for_link_status(struct pci_dev *pdev,
				     bool use_lt, bool active)
{
	u16 lnksta_mask, lnksta_match;
	unsigned long end_jiffies;
	u16 lnksta;

	lnksta_mask = use_lt ? PCI_EXP_LNKSTA_LT : PCI_EXP_LNKSTA_DLLLA;
	lnksta_match = active ? lnksta_mask : 0;

	end_jiffies = jiffies + msecs_to_jiffies(PCIE_LINK_RETRAIN_TIMEOUT_MS);
	do {
		pcie_capability_read_word(pdev, PCI_EXP_LNKSTA, &lnksta);
		if ((lnksta & lnksta_mask) == lnksta_match)
			return 0;
		msleep(1);
	} while (time_before(jiffies, end_jiffies));

	return -ETIMEDOUT;
}
```

The poll reads Link Status every millisecond until Data Link Layer Link Active reads 0 or [`PCIE_LINK_RETRAIN_TIMEOUT_MS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L22) has passed. The limit is defined in drivers/pci/pci.h.

```c
/* drivers/pci/pci.h:22 */
#define PCIE_LINK_RETRAIN_TIMEOUT_MS	1000
```

[`PCIE_LINK_RETRAIN_TIMEOUT_MS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L22) is 1000, so a link that stays up for a second only prints "Data Link Layer Link Active not cleared in 1000 msec" in [`dpc_reset_link()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L148), which goes on to the release. The busy check that comes next runs only on a Root Port with RP extensions.

```c
/* drivers/pci/pcie/dpc.c:130 */
static int dpc_wait_rp_inactive(struct pci_dev *pdev)
{
	unsigned long timeout = jiffies + HZ;
	u16 cap = pdev->dpc_cap, status;

	pci_read_config_word(pdev, cap + PCI_EXP_DPC_STATUS, &status);
	while (status & PCI_EXP_DPC_RP_BUSY &&
					!time_after(jiffies, timeout)) {
		msleep(10);
		pci_read_config_word(pdev, cap + PCI_EXP_DPC_STATUS, &status);
	}
	if (status & PCI_EXP_DPC_RP_BUSY) {
		pci_warn(pdev, "root port still busy\n");
		return -EBUSY;
	}
	return 0;
}
```

[`dpc_wait_rp_inactive()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L130) polls DPC Status every 10 ms for up to `HZ` jiffies, one second, while Root Port Busy, [`PCI_EXP_DPC_RP_BUSY`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1104), is set, and a Port still busy after that prints "root port still busy" and fails the reset. After the release, [`pci_bridge_wait_for_secondary_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4724) waits for the bus below; its kerneldoc states what it waits for.

```c
/* drivers/pci/pci.c:4708 */
/**
 * pci_bridge_wait_for_secondary_bus - Wait for secondary bus to be accessible
 * @dev: PCI bridge
 * @reset_type: reset type in human-readable form
 *
 * Handle necessary delays before access to the devices on the secondary
 * side of the bridge are permitted after D3cold to D0 transition
 * or Conventional Reset.
 *
 * For PCIe this means the delays in PCIe 5.0 section 6.6.1. For
 * conventional PCI it means Tpvrh + Trhfa specified in PCI 3.0 section
 * 4.3.2.
 *
 * Return 0 on success or -ENOTTY if the first device on the secondary bus
 * failed to become accessible.
 */
int pci_bridge_wait_for_secondary_bus(struct pci_dev *dev, char *reset_type)
{
	struct pci_dev *child __free(pci_dev_put) = NULL;
	int delay;

	if (pci_dev_is_disconnected(dev))
		return 0;
```

The wait covers the delays the kerneldoc names before the functions on the secondary side may be accessed after a Conventional Reset, and a nonzero result, the first function failing to become accessible, makes the verdict [`PCI_ERS_RESULT_DISCONNECT`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L931). The figure draws the spans of the callback against the two flag bits.

```text
    What dpc_reset_link() holds while the Port leaves containment
    ─────────────────────────────────────────────────────────────

    time ──────────────────────────────────────────────────────────────────────────────────────▶
    PCI_DPC_RECOVERING in priv_flags        ├───────────────────────────────────────────────┤
    wait for the link to go down              ├────────────┤
    wait while the Root Port is busy                        ├─────┤
    Trigger Status written, DPC released                           ├──┤
    wait for the secondary bus                                         ├──────────────────┤
                                            ╎                                               ╎
    PCI_DPC_RECOVERED                       ╎ unchanged                                     ╎ set when the
                                                                                              bus answered,
                                                                                              else cleared;
                                                                                              waiters woken

    the busy wait runs only on a Root Port with RP extensions, and a busy timeout ends the span early
```

The DPC callback thus resets nothing itself, since the hardware reset the link when it contained the error, and the callback ends containment and checks that the functions answer, with the verdict published to the hotplug driver as well as returned.

So far, the subtree below the bridge has been held resumed, told of the error and asked for votes, and reset by the service's callback when a vote or a frozen channel asked for it. The status that the rounds left now decides between the slot reset and resume rounds and the failure path.

### Slot reset and resume return the drivers to service

Once the reset callback has returned [`PCI_ERS_RESULT_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L934), the functions below the bridge have been reset, and their drivers must restore them before normal I/O resumes. Piece ❻ of [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) runs the slot reset round when a vote asked for the reset.

```c
/* drivers/pci/pcie/err.c:258 */
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

```

Only a status of [`PCI_ERS_RESULT_NEED_RESET`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L928) runs the round, so a reset that ran because the channel was frozen is followed by [`slot_reset`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L950) only when a vote asked for it. The comment asks whether a platform reset of the slot should come before the callbacks, and the code performs none. The status restarts at [`PCI_ERS_RESULT_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L934), and [`report_slot_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L148) runs for each function.

```c
/* drivers/pci/pcie/err.c:148 */
static int report_slot_reset(struct pci_dev *dev, void *data)
{
	struct pci_driver *pdrv;
	pci_ers_result_t vote, *result = data;
	const struct pci_error_handlers *err_handler;

	device_lock(&dev->dev);
	pdrv = dev->driver;
	if (!pci_dev_set_io_state(dev, pci_channel_io_normal) ||
	    !pdrv || !pdrv->err_handler || !pdrv->err_handler->slot_reset)
		goto out;

	err_handler = pdrv->err_handler;
	vote = err_handler->slot_reset(dev);
	*result = merge_result(*result, vote);
out:
	device_unlock(&dev->dev);
	return 0;
}
```

[`report_slot_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L148) moves the channel back to normal before it calls the driver. According to its message, commit commit [45bc82563d55](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=45bc82563d5505327d97963bc54d3709939fa8f8) ("PCI/ERR: Update device error_state already after reset") moved the update here so that a driver that tests [`pci_channel_offline()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L613) in its [`slot_reset`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L950) sees a reachable function. A permanently failed function, or a driver without the member, is skipped without a vote. Piece ❼ of [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) checks the status, resumes the drivers, clears the error status and returns.

```c
/* drivers/pci/pcie/err.c:269 */
	if (status != PCI_ERS_RESULT_RECOVERED)
		goto failed;

	pci_dbg(bridge, "broadcast resume message\n");
	pci_walk_bridge(bridge, report_resume, &status);

	/*
	 * If we have native control of AER, clear error status in the device
	 * that detected the error.  If the platform retained control of AER,
	 * it is responsible for clearing this status.  In that case, the
	 * signaling device may not even be visible to the OS.
	 */
	if (host->native_aer || pcie_ports_native) {
		pcie_clear_device_status(dev);
		pci_aer_clear_nonfatal_status(dev);
	}

	pci_walk_bridge(bridge, pci_pm_runtime_put, NULL);

	pci_info(bridge, "device recovery successful\n");
	return status;

```

Any status other than [`PCI_ERS_RESULT_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L934) here goes to the failure path. The resume round runs [`report_resume()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L168) for each function, and then the reporting device, not the bridge, has its Device Status and its non-fatal AER status cleared when the OS controls AER through [`native_aer`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L653) or the `pcie_ports=native` parameter that sets [`pcie_ports_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L614). The usage count is dropped and "device recovery successful" is printed on the bridge before the status returns. [`report_resume()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L168) is the callback of the last round.

```c
/* drivers/pci/pcie/err.c:168 */
static int report_resume(struct pci_dev *dev, void *data)
{
	struct pci_driver *pdrv;
	const struct pci_error_handlers *err_handler;

	device_lock(&dev->dev);
	pdrv = dev->driver;
	if (!pci_dev_set_io_state(dev, pci_channel_io_normal) ||
	    !pdrv || !pdrv->err_handler || !pdrv->err_handler->resume)
		goto out;

	err_handler = pdrv->err_handler;
	err_handler->resume(dev);
out:
	pci_uevent_ers(dev, PCI_ERS_RESULT_RECOVERED);
	device_unlock(&dev->dev);
	return 0;
}
```

[`report_resume()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L168) sets the channel to normal again, which covers a run that skipped the slot reset round, and calls the driver's [`resume`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L957) under the device lock. The uevent at its `out` label reports [`PCI_ERS_RESULT_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L934) for every function, the skipped ones included. The two clearing helpers belong to the AER device setup in pci.c and aer.c, and their bodies show what the success path writes.

```c
/* drivers/pci/pci.c:2239 */
#ifdef CONFIG_PCIEAER
void pcie_clear_device_status(struct pci_dev *dev)
{
	pcie_capability_write_word(dev, PCI_EXP_DEVSTA,
				   PCI_EXP_DEVSTA_CED | PCI_EXP_DEVSTA_NFED |
				   PCI_EXP_DEVSTA_FED | PCI_EXP_DEVSTA_URD);
}
#endif
```

[`pcie_clear_device_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2240), compiled with [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28), writes the four error-detected bits of Device Status in one write through the PCI Express capability. The AER status is cleared under a test of its own.

```c
/* drivers/pci/pcie/aer.c:264 */
int pci_aer_clear_nonfatal_status(struct pci_dev *dev)
{
	int aer = dev->aer_cap;
	u32 status, sev;

	if (!pcie_aer_is_native(dev))
		return -EIO;

	/* Clear status bits for ERR_NONFATAL errors only */
	pci_read_config_dword(dev, aer + PCI_ERR_UNCOR_STATUS, &status);
	pci_read_config_dword(dev, aer + PCI_ERR_UNCOR_SEVER, &sev);
	status &= ~sev;
	if (status)
		pci_write_config_dword(dev, aer + PCI_ERR_UNCOR_STATUS, status);

	return 0;
}
```

[`pci_aer_clear_nonfatal_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L264) returns `-EIO` unless the OS controls AER for the function, and otherwise writes back the logged uncorrectable errors whose severity bit is clear. Its test is [`pcie_aer_is_native()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L242), the per-function form of the condition piece ❼ tests.

```c
/* drivers/pci/pcie/aer.c:242 */
int pcie_aer_is_native(struct pci_dev *dev)
{
	struct pci_host_bridge *host = pci_find_host_bridge(dev->bus);

	if (!dev->aer_cap)
		return 0;

	return pcie_ports_native || host->native_aer;
}
```

[`pcie_aer_is_native()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L242) also requires an AER capability on the function, [`aer_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370) nonzero, which the test in piece ❼ does not. The figure follows the slot reset and resume rounds over the subtree of the topology figure, now with a driver bound to 04:00.0.

```text
    What slot reset and resume leave on each function, after a reset that succeeded
    ───────────────────────────────────────────────────────────────────────────────

    walk order        01:00.0      02:01.0      03:00.0      02:02.0      04:00.0
                    ┌────────────┬────────────┬────────────┬────────────┬────────────┐
    driver          │ pcieport   │ pcieport   │ nvme       │ pcieport   │ nvme       │
                    └─────┬──────┴─────┬──────┴─────┬──────┴─────┬──────┴─────┬──────┘
    visited               ▼            ▼            ▼            ▼            ▼
    error_state       normal       normal       normal       normal       normal
    slot_reset        RECOVERED    RECOVERED    RECOVERED    RECOVERED    RECOVERED
    resume            skipped      skipped      called       skipped      called
    uevent            SUCCESSFUL_  SUCCESSFUL_  SUCCESSFUL_  SUCCESSFUL_  SUCCESSFUL_
                      RECOVERY     RECOVERY     RECOVERY     RECOVERY     RECOVERY

    each round visits every function; a driver without the member is skipped, the state and the
    uevent are written all the same; pcieport has no resume member, nvme has both
```

A successful recovery has thus reset the hierarchy, returned every function of the subtree that was not lost to [`pci_channel_io_normal`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L210), called each driver's [`slot_reset`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L950) and [`resume`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L957) where it has them, cleared the reporting device's error status and released the runtime PM hold. Every function has announced "ERROR_EVENT=SUCCESSFUL_RECOVERY", and [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) returns [`PCI_ERS_RESULT_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L934) to the service.

### A failed recovery tells the drivers their functions are lost

Recovery fails when the reset callback reports anything but [`PCI_ERS_RESULT_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L934), or when the status is not `PCI_ERS_RESULT_RECOVERED` before the resume round, and the drivers must then learn that their functions will not come back. Piece ❽ of [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) is the failure path that both jumps reach.

```c
/* drivers/pci/pcie/err.c:291 */
failed:
	pci_walk_bridge(bridge, pci_pm_runtime_put, NULL);

	pci_walk_bridge(bridge, report_perm_failure_detected, NULL);

	pci_info(bridge, "device recovery failed\n");

	return status;
}
```

The usage count is dropped first, so the functions may runtime-suspend again, and then every driver with an [`error_detected`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L943) callback is told of the permanent failure through [`report_perm_failure_detected()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L111) before "device recovery failed" is printed on the bridge. The status returned is the one the run left, and a reset that fails after the MMIO round left [`PCI_ERS_RESULT_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L934) returns that value from the failure path. [`edr_handle_event()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/edr.c#L151) compares the result with `PCI_ERS_RESULT_RECOVERED` for its report to firmware, and the AER and DPC callers ignore it. The callback of this round is the last report function.

```c
/* drivers/pci/pcie/err.c:111 */
static int report_perm_failure_detected(struct pci_dev *dev, void *data)
{
	struct pci_driver *pdrv;
	const struct pci_error_handlers *err_handler;

	device_lock(&dev->dev);
	pdrv = dev->driver;
	if (!pdrv || !pdrv->err_handler || !pdrv->err_handler->error_detected)
		goto out;

	err_handler = pdrv->err_handler;
	err_handler->error_detected(dev, pci_channel_io_perm_failure);
out:
	pci_uevent_ers(dev, PCI_ERS_RESULT_DISCONNECT);
	device_unlock(&dev->dev);
	return 0;
}
```

[`report_perm_failure_detected()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L111) calls [`error_detected`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L943) with [`pci_channel_io_perm_failure`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L216) but writes no channel state, so [`error_state`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L445) keeps the value detection set and [`pci_dev_is_disconnected()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2702) stays false as far as recovery is concerned. Every function, with or without a driver, gets an "ERROR_EVENT=FAILED_RECOVERY" uevent through [`PCI_ERS_RESULT_DISCONNECT`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L931). According to their messages, commit commit [9011f0667c93](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=9011f0667c93df2034f2ff33eae37ddf9bdd0ef9) ("PCI/ERR: Notify drivers on failure to recover") added the notification to follow pci-error-recovery.rst, and commit commit [1cbc5e25fb70](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=1cbc5e25fb70e942a7a735a1f3d6dd391afc9b29) ("PCI/ERR: Fix uevent on failure to recover") moved the failure uevent from the bridge to the functions below it. The figure follows the failure that the detection round of the earlier figure set up.

```text
    What a failed recovery leaves on each function, after the detection round above
    ───────────────────────────────────────────────────────────────────────────────

    walk order        01:00.0      02:01.0      03:00.0      02:02.0      04:00.0
                    ┌────────────┬────────────┬────────────┬────────────┬────────────┐
    driver          │ pcieport   │ pcieport   │ nvme       │ pcieport   │ none       │
                    └─────┬──────┴─────┬──────┴─────┬──────┴─────┬──────┴─────┬──────┘
    visited               ▼            ▼            ▼            ▼            ▼
    error_state       frozen       frozen       frozen       frozen       frozen
    told              perm_        perm_        perm_        perm_        skipped
                      failure      failure      failure      failure
    uevent            FAILED_      FAILED_      FAILED_      FAILED_      FAILED_
                      RECOVERY     RECOVERY     RECOVERY     RECOVERY     RECOVERY

    error_state keeps the value detection left: the failure path writes no channel state, and
    a driver learns of the failure from its error_detected callback alone
```

After a failure the functions stay enumerated with their channel frozen or normal, and what becomes of them is up to their drivers and to the code that removes devices, which recovery does not call.

### Messages, uevents and hand-offs expose a recovery

A recovery shows in the kernel log, in uevents on each function and in the runtime PM state of the subtree, and it runs in the context of the service that started it. The table lists each class for the paths of this page, with its sites.

| class | on these paths | sites |
|---|---|---|
| tracepoints | none in err.c, [`aer_root_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1667) or [`dpc_reset_link()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L148); the RAS event `ras:aer_event` fires when AER logs the error, before its handler starts recovery | [`aer.c:879`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L879), [`aer.c:955`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L955) |
| messages always printed | the four outcomes of recovery and the resets, at the info and warning levels, listed below | err.c, aer.c, dpc.c, edr.c |
| dynamic-debug sites | the four broadcast messages, the EDR messages and the secondary-bus waits, listed below | err.c, edr.c, pci.c |
| uevents | a `KOBJ_CHANGE` per function with "ERROR_EVENT" and "DEVICE_ONLINE" from [`pci_uevent_ers()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L1625) | [`pci-driver.c:1651`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L1651) |
| deferred hand-offs | the threaded interrupt handlers of AER and DPC, the ACPI notify work of EDR, the work item of firmware-first AER, and the idle check that [`pm_runtime_put()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pm_runtime.h#L549) queues | [`aer.c:1632`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1632), [`dpc.c:483`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L483), [`osl.c:1141`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/osl.c#L1141), [`aer.c:1276`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1276) |
| debugging surfaces | the `pcie_ports=` and `pci=noaer` boot parameters, the AER injector with [`CONFIG_PCIEAER_INJECT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L37), and the dynamic-debug control file; no sysfs, procfs or debugfs file shows [`error_state`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L445) | [`portdrv.c:622`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L622), [`drivers/pci/pci.c:6757`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L6757), [`aer_inject.c:512`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer_inject.c#L512) |

The messages of err.c carry the prefix "AER: " whichever service started the recovery, because the file defines its own message format.

```c
/* drivers/pci/pcie/err.c:13 */
#define dev_fmt(fmt) "AER: " fmt
```

[`dev_fmt`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L13) prefixes every `dev_*` message the file prints. The PCI message macros of include/linux/pci.h reach those `dev_*` calls.

```c
/* include/linux/pci.h:2895 */
#define pci_info(pdev, fmt, arg...)	dev_info(&(pdev)->dev, fmt, ##arg)
#define pci_dbg(pdev, fmt, arg...)	dev_dbg(&(pdev)->dev, fmt, ##arg)
```

[`pci_info()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2895) and [`pci_dbg()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2896) pass the function's embedded device to [`dev_info()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/dev_printk.h#L159) and [`dev_dbg()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/dev_printk.h#L164), so every message names the function it is about. The messages these paths print are listed by site, with the level, the text and what each one tells a reader.

| site | level | message | what it reports |
|---|---|---|---|
| [`err.c:62`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L62) | info | "can't recover (state transition %u -> %u invalid)" | a function's channel state refused the requested move |
| [`err.c:75`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L75) | info | "can't recover (no error_detected callback)" | a function without a callback, which fails the run |
| [`err.c:238`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L238) | debug | "broadcast error_detected message" | the detection round starts on the bridge |
| [`err.c:246`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L246) | debug | "broadcast mmio_enabled message" | the MMIO round starts |
| [`err.c:253`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L253) | warning | "subordinate device reset failed" | the reset callback did not return RECOVERED |
| [`err.c:265`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L265) | debug | "broadcast slot_reset message" | the slot reset round starts |
| [`err.c:272`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L272) | debug | "broadcast resume message" | the resume round starts |
| [`err.c:288`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L288) | info | "device recovery successful" | the run returns RECOVERED |
| [`err.c:296`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L296) | info | "device recovery failed" | the run took the failure path |
| [`aer.c:1699`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1699), [`aer.c:1701`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1701), [`aer.c:1704`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1704) | info | "has been reset", "not reset (no FLR support: %d)", "%s Port link has been reset (%d)" | the outcome of the AER reset |
| [`dpc.c:166`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L166), [`dpc.c:142`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L142) | info, warning | "Data Link Layer Link Active not cleared in 1000 msec", "root port still busy" | a DPC link wait that timed out, a busy timeout |
| [`edr.c:178`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/edr.c#L178), [`edr.c:210`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/edr.c#L210), [`edr.c:214`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/edr.c#L214) | debug | "Reported EDR dev: %s", "DPC port successfully recovered", "DPC port recovery failed" | the Port firmware named and the verdict sent back |
| [`drivers/pci/pci.c:4790`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4790), [`drivers/pci/pci.c:4812`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4812) | debug | "waiting %d ms for downstream link", "waiting %d ms for downstream link, after activation" | the wait after the DPC release, by the Port's link speed |

The debug sites go through [`dev_dbg()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/dev_printk.h#L164), whose definition decides what a site compiles to.

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

With [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120) set, every debug site of the table is a dynamic-debug callsite, off until a reader enables it, for example with "file drivers/pci/pcie/err.c +p" written to `/sys/kernel/debug/dynamic_debug/control`. Enabled, the err.c sites mark the start of each round on the bridge, so a reader sees which rounds a run took between the "AER: " lines that report its outcome. With `DEBUG` defined the sites print at the debug level, and [`CONFIG_PCI_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L70), which this page assumes unset, defines it for the PCI directory in its Makefile.

```c
/* drivers/pci/Makefile:50 */
subdir-ccflags-$(CONFIG_PCI_DEBUG) := -DDEBUG
```

The line adds `-DDEBUG` to every file under drivers/pci when [`CONFIG_PCI_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L70) is set, which makes each debug site of the table print without the control file.

The uevents are the user-space view of a run: a udev monitor sees "ERROR_EVENT=BEGIN_RECOVERY" for each function as detection reaches it and "ERROR_EVENT=SUCCESSFUL_RECOVERY" or "ERROR_EVENT=FAILED_RECOVERY" at the end, and a function other than a bridge without a callback is silent until the failure. The channel state itself has no file, and drivers read it through [`pci_channel_offline()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L613) and [`pci_dev_is_disconnected()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2702). The software error injector that the Kconfig help of [`CONFIG_PCIEAER_INJECT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L37) describes, which this page assumes unset, registers [`aer_inject_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer_inject.c#L512) for user space to start AER recovery without a hardware error.
