# Downstream Port Containment

> CAUTION: AI-GENERATED CONTENT
>
> STRICTLY DO NOT SUBMIT THIS UPSTREAM UNLESS YOU ARE AN EXPERT INTIMATELY FAMILIAR WITH THIS SUBSYSTEM.

An uncorrectable error below a PCIe port can leave the link carrying corrupt or stalled traffic toward drivers that trust it. Downstream Port Containment lets the port itself disable that link as the error arrives, record why in its DPC capability and raise an interrupt. Software then has to log the cause, let the drivers below the port recover and release the port, and on x86 with ACPI that software is the DPC service of the PCIe port driver, built from drivers/pci/pcie/dpc.c. This page traces how enumeration finds the capability, how the service arms it, and how one containment event travels from the interrupt through logging and recovery until the port leaves containment.

```text
    One containment event, from the trigger to the released port
    ────────────────────────────────────────────────────────────

    time ↓
    port hardware         ╎ hard IRQ              ╎ IRQ thread              ╎ error recovery
    ──────────────────────┼───────────────────────┼─────────────────────────┼──────────────────────────
    error contained:      ╎                       ╎                         ╎
    link disabled,        ╎                       ╎                         ╎
    Trigger Status 1,     ╎                       ╎                         ╎
    Interrupt Status 1    ╎                       ╎                         ╎
      MSI ──────────────▶ ╎ DPC Status read,      ╎                         ╎
                          ╎ Interrupt Status      ╎                         ╎
                          ╎ cleared by writing 1  ╎                         ╎
                          ╎   wake ──────────────▶╎ port held by a          ╎
                          ╎                       ╎ reference, reason       ╎
                          ╎                       ╎ logged                  ╎
                          ╎                       ╎   frozen ──────────────▶╎ drivers below told
                          ╎                       ╎                         ╎ the channel is frozen
    link down seen ◀───────────────────────────────────────────────────────── reset callback waits
                          ╎                       ╎                         ╎ for the link to drop
    Trigger Status 0 ◀─────────────────────────────────────────────────────── Trigger Status cleared
    port leaves           ╎                       ╎                         ╎ by writing 1
    containment,          ╎                       ╎                         ╎ secondary bus waited,
    link trains again     ╎                       ╎                         ╎ drivers below resumed
                          ╎                       ╎ reference dropped ◀────── result returned

    the thread runs only when the hard handler saw Trigger Status set; a trigger that a surprise
    removal caused is cleared in the thread without logging or recovery
```

## SUMMARY

The kernel keeps a port's DPC state in its [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) and drives the capability from a port service. The service binds to a [`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59), which is portdrv's service instance for one port and one service, and the table settles the names the rest of the page uses.

| DPC term | Kernel representation | Written or read by |
|---|---|---|
| DPC Extended Capability of a port | [`dpc_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L537), its offset in configuration space | [`pci_dpc_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L403) at enumeration |
| Root Port extensions, the RP PIO registers | [`dpc_rp_extensions`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L538) and [`dpc_rp_log_size`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L539) | [`pci_dpc_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L403) |
| the DPC service of a port | [`dpcdriver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L523) bound to the port's [`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59) | [`dpc_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L473) |
| containment in effect | [`PCI_EXP_DPC_STATUS_TRIGGER`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1097) in DPC Status | [`dpc_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L386), cleared by [`dpc_reset_link()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L148) |
| why the port triggered | [`PCI_EXP_DPC_STATUS_TRIGGER_RSN`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1098) in DPC Status | [`dpc_process_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L264) |
| recovery after a trigger | [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) with [`dpc_reset_link()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L148) as its reset callback | [`dpc_handler()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L363) |

A trigger reaches the hard interrupt handler, which wakes a thread that logs the reason and runs error recovery for a frozen channel. The port stays contained until the reset callback clears Trigger Status, which it does after the link has gone down and, on a port with the Root Port extensions, after Root Port Busy has cleared.

## SPECIFICATIONS

No source comment in drivers/pci/pcie/dpc.c names the section that defines the DPC capability, so the register drawings follow the macros of `include/uapi/linux/pci_regs.h`. The documents the tree does cite on these paths are listed with the site that cites them.

- PCI Express Base Specification r7.0, sec 6.2.11, cited without a title by [`pci-error-recovery.rst:125-128`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/PCI/pci-error-recovery.rst#L125) for Downstream Port Containment disabling the link to the sub-hierarchy of the faulting device.
- PCIe r6.0, sec 6.7.6, cited without a title by the comment in [`dpc_handler()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L363) at [`dpc.c:367-370`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L367) for errors as an expected side effect of async removal.
- PCIe r6.0, sec 6.6.1, cited without a title by the comment above [`PCI_RESET_WAIT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L74) at [`pci.c:70-73`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L70) for the readiness of devices after Conventional Reset, which bounds the wait for the secondary bus.
- PCI Firmware Specification r3.2 with the Downstream Port Containment Related Enhancements ECN, sec 4.5.1, table 4-5, cited by the comment in [`calculate_control()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/pci_root.c#L498) at [`pci_root.c:517-522`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/pci_root.c#L517) for the `_OSC` control bit that covers DPC and EDR.
- PCI Firmware r3.3, sec 4.6.13, and ACPI r6.5, sec 5.6.6, cited by [`edr_handle_event()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/edr.c#L151) at [`edr.c:160-170`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/edr.c#L160) for the firmware notification that hands a contained port to the OS.

## COVERAGE

### Capability state of the port (include/linux/pci.h, drivers/pci/pcie/dpc.c)

- [`'pci_dev.dpc_cap'`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L537): the offset of the DPC Extended Capability, 0 for a function without one.
- [`'pci_dev.dpc_rp_extensions'`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L538): set when the port implements the Root Port extensions.
- [`'pci_dev.dpc_rp_log_size'`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L539): the dwords of RP PIO log the port provides, 0 when the size is unusable.
- [`'\<pci_dpc_init\>':'drivers/pci/pcie/dpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L403): finds the capability at enumeration and fills the three members.

### The port service and its lifecycle (drivers/pci/pcie/dpc.c)

- [`'\<dpcdriver\>':'drivers/pci/pcie/dpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L523): the port service driver for the DPC service bit of any port type.
- [`'\<pcie_dpc_init\>':'drivers/pci/pcie/dpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L533): registers the service driver with the port bus at boot.
- [`'\<dpc_probe\>':'drivers/pci/pcie/dpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L473): refuses a port without AER ownership or dpc-native, installs both handlers, arms the port and adds the save buffer.
- [`'\<dpc_enable\>':'drivers/pci/pcie/dpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L441): clears Interrupt Status, then sets the `ERR_FATAL` trigger and the interrupt enable in DPC Control.
- [`'\<dpc_disable\>':'drivers/pci/pcie/dpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L460): clears the `ERR_FATAL` trigger and the interrupt enable.
- [`'\<dpc_suspend\>':'drivers/pci/pcie/dpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L506): disarms the port on the way into a sleep state.
- [`'\<dpc_resume\>':'drivers/pci/pcie/dpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L512): arms the port again on resume.
- [`'\<dpc_remove\>':'drivers/pci/pcie/dpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L518): disarms the port when the service is unbound.
- [`'\<pci_save_dpc_state\>':'drivers/pci/pcie/dpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L46): copies DPC Control into the save buffer.
- [`'\<pci_restore_dpc_state\>':'drivers/pci/pcie/dpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L62): writes the saved copy back into DPC Control.

### Interrupt and logging (drivers/pci/pcie/dpc.c)

- [`'\<dpc_irq\>':'drivers/pci/pcie/dpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L386): the hard handler that claims, acknowledges and passes on a DPC interrupt.
- [`'\<dpc_handler\>':'drivers/pci/pcie/dpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L363): the threaded handler that holds the port, logs the reason and runs recovery.
- [`'\<dpc_process_error\>':'drivers/pci/pcie/dpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L264): logs the trigger by its reason.
- [`'\<dpc_get_aer_uncorrect_severity\>':'drivers/pci/pcie/dpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L236): builds the one-device AER record of an uncorrectable trigger.
- [`'\<dpc_process_rp_pio_error\>':'drivers/pci/pcie/dpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L190): prints and clears the RP PIO registers of a Root Port.
- [`'\<rp_pio_error_string\>':'drivers/pci/pcie/dpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L24): the names of the RP PIO Status bits.

### Reset, completion and surprise removal (drivers/pci/pcie/dpc.c)

- [`'\<dpc_reset_link\>':'drivers/pci/pcie/dpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L148): the reset callback that releases the port and reports whether the bus came back.
- [`'\<dpc_wait_rp_inactive\>':'drivers/pci/pcie/dpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L130): polls Root Port Busy for up to one second.
- [`'\<dpc_completed_waitqueue\>':'drivers/pci/pcie/dpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L78): the wait queue the hotplug driver sleeps on during recovery.
- [`'\<dpc_completed\>':'drivers/pci/pcie/dpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L81): the wake-up condition, trigger clear and recovery finished.
- [`'\<dpc_is_surprise_removal\>':'drivers/pci/pcie/dpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L349): tests a hotplug bridge for a Surprise Down error.
- [`'\<dpc_handle_surprise_removal\>':'drivers/pci/pcie/dpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L328): clears the errors of a surprise removal and releases the port without recovery.
- [`'\<pci_clear_surpdn_errors\>':'drivers/pci/pcie/dpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L312): clears the status bits a Surprise Down leaves outside AER.

### DPC capability registers (include/uapi/linux/pci_regs.h)

- [`'PCI_EXP_DPC_CAP'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1082): offset 0x04, DPC Capability.
- [`'PCI_EXP_DPC_CTL'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1091): offset 0x06, DPC Control.
- [`'PCI_EXP_DPC_STATUS'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1096): offset 0x08, DPC Status.
- [`'PCI_EXP_DPC_STATUS_TRIGGER'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1097): bit 0 of DPC Status, Trigger Status.
- [`'PCI_EXP_DPC_STATUS_TRIGGER_RSN'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1098): bits 2:1 of DPC Status, Trigger Reason.
- [`'PCI_EXP_DPC_SOURCE_ID'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1110): offset 0x0A, the Requester ID of the error message that triggered the port.
- [`'PCI_EXP_DPC_RP_PIO_STATUS'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1112): offset 0x0C, the first RP PIO register.

## DOCUMENTATION

- [`Documentation/PCI/pci-error-recovery.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/PCI/pci-error-recovery.rst): the recovery steps a driver sees after a trigger, with the link disabled until the reset step and re-enabled there.
- [`Documentation/PCI/pcieaer-howto.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/PCI/pcieaer-howto.rst): the AER ratelimits, which exempt fatal errors and DPC errors.
- [`Documentation/admin-guide/kernel-parameters.txt`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/admin-guide/kernel-parameters.txt): the `pcie_ports=native`, `pcie_ports=dpc-native` and `pcie_ports=compat` boot options that decide whether the DPC service runs.

## OTHER SOURCES

### Added by Claude Opus 5.5

- [PCI/DPC: Log AER error info for DPC/EDR uncorrectable errors (commit 97970e7c6943)](https://patch.msgid.link/20260318170449.2733581-1-sathyanarayanan.kuppuswamy@linux.intel.com)
- [PCI/AER: Convert aer_get_device_error_info(), aer_print_error() to index (commit 94bc15c3484a)](https://patch.msgid.link/20250522232339.1525671-17-helgaas@kernel.org)
- [PCI/DPC: Log Error Source ID only when valid (commit a0b62cc31023)](https://patch.msgid.link/20250522232339.1525671-3-helgaas@kernel.org)
- [PCI/DPC: Initialize aer_err_info before using it (commit a424b598e6a6)](https://patch.msgid.link/20250522232339.1525671-2-helgaas@kernel.org)
- [PCI/ERR: Handle TLP Log in Flit mode (commit 7e077e6707b3)](https://lore.kernel.org/r/20250207161836.2755-3-ilpo.jarvinen@linux.intel.com)
- [PCI/DPC: Disable DPC service on suspend (commit 75c47c790f43)](https://lore.kernel.org/r/20240416043225.1462548-3-kai.heng.feng@canonical.com)
- [PCI/DPC: Ignore Surprise Down error on hot removal (commit 2ae8fbbe1cd4)](https://lore.kernel.org/r/20240207181854.121335-1-Smita.KoralahalliChannabasappa@amd.com)
- [PCI/DPC: Print all TLP Prefixes, not just the first (commit 6568d82512b0)](https://lore.kernel.org/r/20240118110815.3867-1-ilpo.jarvinen@linux.intel.com)
- [PCI/DPC: Use defines with DPC reason fields (commit 74f0b5ffe172)](https://lore.kernel.org/r/20231018113254.17616-7-ilpo.jarvinen@linux.intel.com)
- [PCI/DPC: Use defined fields with DPC_CTL register (commit f00e8dbdedfb)](https://lore.kernel.org/r/20231018113254.17616-6-ilpo.jarvinen@linux.intel.com)
- [PCI/DPC: Await readiness of secondary bus after reset (commit 53b54ad074de)](https://lore.kernel.org/r/9f5ff00e1593d8d9a4b452398b98aa14d23fca11.1673769517.git.lukas@wunner.de)
- [PCI/DPC: Use PCI_POSSIBLE_ERROR() to check config reads (commit 0242132da26a)](https://lore.kernel.org/r/9b0632f1f183432149f495cf12bdd5a72cc597a4.1637243717.git.naveennaidu479@gmail.com)
- [PCI: pciehp: Ignore Link Down/Up caused by DPC (commit a97396c6eb13)](https://lore.kernel.org/r/0be565d97438fe2a6d57354b3aa4e8626952a00b.1619857124.git.lukas@wunner.de)
- [PCI/DPC: Print IRQ number used by port (commit 9103aaf9b40c)](https://lore.kernel.org/r/1589018214-52752-1-git-send-email-yangyicong@hisilicon.com)
- [PCI/DPC: Expose dpc_process_error(), dpc_reset_link() for use by EDR (commit aea47413e7ce)](https://lore.kernel.org/r/e9000bb15b3a4293e81d98bb29ead7c84a6393c9.1585000084.git.sathyanarayanan.kuppuswamy@linux.intel.com)
- [PCI/DPC: Cache DPC capabilities in pci_init_capabilities() (commit 27005618178e)](https://lore.kernel.org/r/5888380657c8b9551675b5dbd48e370e4fd2703d.1585000084.git.sathyanarayanan.kuppuswamy@linux.intel.com)
- [PCI/DPC: Move DPC data into struct pci_dev (commit be06c1b42eea)](https://lore.kernel.org/r/98323eaa18080adbe5bb30846862f09f8722d4b3.1585000084.git.sathyanarayanan.kuppuswamy@linux.intel.com)
- [PCI/DPC: Add "pcie_ports=dpc-native" to allow DPC without AER control (commit 35a0b2378c19)](https://lore.kernel.org/r/20191023192205.97024-1-olof@lixom.net)

## REGISTERS

The DPC paths reach the port's DPC Extended Capability through the offset [`dpc_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L537) holds, and every access adds a fixed displacement to it. The map shows where each register of the capability stands relative to that offset.

```text
    The DPC Extended Capability, at offset dpc_cap of extended configuration space
    ──────────────────────────────────────────────────────────────────────────────

          bits 31:16                bits 15:0
          ┌───────────────────────────────────────────────────┐
    +0x00 │ extended capability header, PCI_EXT_CAP_ID_DPC    │
          ├─────────────────────────┬─────────────────────────┤
    +0x04 │ DPC Control             │ DPC Capability          │
          ├─────────────────────────┼─────────────────────────┤
    +0x08 │ DPC Source ID           │ DPC Status              │
          ├─────────────────────────┴─────────────────────────┤
    +0x0C │ RP PIO Status                                     │
    +0x10 │ RP PIO Mask                                       │
    +0x14 │ RP PIO Severity                                   │
    +0x18 │ RP PIO SysError                                   │
    +0x1C │ RP PIO Exception                                  │
    +0x20 │ RP PIO Header Log, four dwords to +0x2C           │
    +0x30 │ RP PIO ImpSpec Log                                │
    +0x34 │ RP PIO TLP Prefix Log, the dwords that follow     │
          │ the Header Log when dpc_rp_log_size is over 5     │
          └───────────────────────────────────────────────────┘

    +0x04 = PCI_EXP_DPC_CAP, +0x06 = PCI_EXP_DPC_CTL, +0x08 = PCI_EXP_DPC_STATUS,
    +0x0A = PCI_EXP_DPC_SOURCE_ID, +0x0C = PCI_EXP_DPC_RP_PIO_STATUS, +0x10 = PCI_EXP_DPC_RP_PIO_MASK,
    +0x14 = PCI_EXP_DPC_RP_PIO_SEVERITY, +0x18 = PCI_EXP_DPC_RP_PIO_SYSERROR,
    +0x1C = PCI_EXP_DPC_RP_PIO_EXCEPTION, +0x20 = PCI_EXP_DPC_RP_PIO_HEADER_LOG,
    +0x30 = PCI_EXP_DPC_RP_PIO_IMPSPEC_LOG, +0x34 = PCI_EXP_DPC_RP_PIO_TLPPREFIX_LOG
    +0x0C and beyond belong to the Root Port extensions and are read only when dpc_rp_extensions is 1
```

[`pci_dpc_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L403) reads the Capability register once, [`dpc_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L441) and [`dpc_disable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L460) write Control, and the interrupt, logging and reset paths read and write Status. [`dpc_process_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L264) reads Source ID for an error message the port received, and [`dpc_process_rp_pio_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L190) reads the registers from +0x0C on, which the capability carries on a port whose Capability register reports the Root Port extensions.

```text
    DPC Capability and DPC Control, at dpc_cap + 0x04 and dpc_cap + 0x06
    ────────────────────────────────────────────────────────────────────

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    +0x04 │ · │4│D│  SIZE │S│P│R│   IRQ   │
          │   │ │ │ (11:8)│ │ │ │  (4:0)  │
          ├───┴─┴─┴───────┴─┴─┴─┴─┬─┬─┬─┬─┤
    +0x06 │    no macro (15:4)    │I│·│N│F│
          └───────────────────────┴─┴─┴─┴─┘

    IRQ = PCI_EXP_DPC_IRQ (Interrupt Message Number); R = PCI_EXP_DPC_CAP_RP_EXT (Root Port Extensions)
    P = PCI_EXP_DPC_CAP_POISONED_TLP (Poisoned TLP Egress Blocking Supported)
    S = PCI_EXP_DPC_CAP_SW_TRIGGER (Software Triggering Supported)
    SIZE = PCI_EXP_DPC_RP_PIO_LOG_SIZE (RP PIO Log Size bits 3:0); 4 = PCI_EXP_DPC_RP_PIO_LOG_SIZE4 (its bit 4)
    D = PCI_EXP_DPC_CAP_DL_ACTIVE (ERR_COR signal on DL_Active supported); bits 15:14 have no macro
    F = PCI_EXP_DPC_CTL_EN_FATAL (trigger on ERR_FATAL); N = PCI_EXP_DPC_CTL_EN_NONFATAL (trigger on ERR_NONFATAL)
    I = PCI_EXP_DPC_CTL_INT_EN (DPC Interrupt Enable); bit 2 and bits 15:4 have no macro
    R and SIZE are cached in dpc_rp_extensions and dpc_rp_log_size; no member caches Control
```

On these paths the Capability register decides two things. R decides whether [`pci_dpc_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L403) sets [`dpc_rp_extensions`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L538), which gates every access dpc.c makes to the registers from +0x0C on, and SIZE with its bit 4 gives [`dpc_rp_log_size`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L539). IRQ is the vector [`pcie_message_numbers()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L57) reads to size the port's MSI or MSI-X allocation, and P, S and D appear in the capability line [`dpc_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L473) prints and steer nothing else here. In Control, F and I are the bits the service sets to arm the port and clears to disarm it, and N is cleared when the port is armed, so a port the kernel arms triggers on `ERR_FATAL` messages and not on `ERR_NONFATAL` ones.

```text
    DPC Status and DPC Source ID, at dpc_cap + 0x08 and dpc_cap + 0x0A
    ──────────────────────────────────────────────────────────────────

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    +0x08 │  ·  │   FEP   │·│EXT│B│I│RSN│T│
          │     │  (12:8) │ │   │ │ │   │ │
          ├─────┴─────────┼─┴───┴─┴─┼───┴─┤
    +0x0A │   bus (15:8)  │  device │  fn │
          │               │  (7:3)  │(2:0)│
          └───────────────┴─────────┴─────┘

    T = PCI_EXP_DPC_STATUS_TRIGGER (Trigger Status); I = PCI_EXP_DPC_STATUS_INTERRUPT (Interrupt Status)
    RSN = PCI_EXP_DPC_STATUS_TRIGGER_RSN (Trigger Reason, 2:1): 0x0000 _UNCOR, 0x0002 _NFE, 0x0004 _FE,
          0x0006 _IN_EXT (reason in the extension field)
    B = PCI_EXP_DPC_RP_BUSY (Root Port Busy)
    EXT = PCI_EXP_DPC_STATUS_TRIGGER_RSN_EXT (6:5): 0x0000 _RP_PIO, 0x0020 _SW_TRIGGER
    FEP = PCI_EXP_DPC_RP_PIO_FEP (RP PIO First Error Pointer); bits 15:13 and bit 7 have no macro
    bus, device, fn = PCI_BUS_NUM(), PCI_SLOT() and PCI_FUNC() of the PCI_EXP_DPC_SOURCE_ID word
    no member caches either register
```

T decides whether the hard interrupt handler wakes the thread, and writing it as 1 releases the port from containment. I marks a pending DPC interrupt, which the hard handler tests to claim the shared vector and clears by writing 1. RSN selects the branch of [`dpc_process_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L264), and for the value [`PCI_EXP_DPC_STATUS_TRIGGER_RSN_IN_EXT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1102) EXT names the extended reason. B is the bit [`dpc_wait_rp_inactive()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L130) polls, and FEP marks which RP PIO Status bit [`dpc_process_rp_pio_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L190) prints as the first error. Source ID is read for the [`PCI_EXP_DPC_STATUS_TRIGGER_RSN_NFE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1100) and [`PCI_EXP_DPC_STATUS_TRIGGER_RSN_FE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1101) reasons and printed as a bus, device and function.

```text
    RP PIO Status, at dpc_cap + 0x0C, with the bit positions rp_pio_error_string[] names
    ─────────────────────────────────────────────────────────────────────────────────────

    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    +0x0C │            ·            │M│M│M│    ·    │I│I│I│    ·    │C│C│C│
          └─────────────────────────┴─┴─┴─┴─────────┴─┴─┴─┴─────────┴─┴─┴─┘

    C = a Configuration Request completion error: bit 0 UR Completion, bit 1 CA Completion, bit 2 Completion Timeout
    I = an I/O Request completion error: bit 8 UR, bit 9 CA, bit 10 Completion Timeout
    M = a Memory Request completion error: bit 16 UR, bit 17 CA, bit 18 Completion Timeout
    PCI_EXP_DPC_RP_PIO_STATUS = 0x0C; pci_regs.h names no bit of it, the names are the strings of
    rp_pio_error_string[] in dpc.c; the code reads RP PIO Mask at +0x10 with the same bit positions
```

The RP PIO Status bits name completion errors of requests the Root Port sent, and [`dpc_process_rp_pio_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L190) prints the name of each set bit that RP PIO Mask leaves unmasked, then writes the value it read back to clear those bits. [`pci_clear_surpdn_errors()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L312) writes all ones to the register when it cleans up after a surprise removal.

```text
    Uncorrectable Error Status of the port, at aer_cap + 0x04
    ─────────────────────────────────────────────────────────

    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    +0x04 │       other uncorrectable error bits (31:6)       │S│  other  │
          │                                                   │ │  (4:0)  │
          └───────────────────────────────────────────────────┴─┴─────────┘

    S = PCI_ERR_UNC_SURPDN (Surprise Down); the register is PCI_ERR_UNCOR_STATUS (0x04), read whole;
    Mask (PCI_ERR_UNCOR_MASK, 0x08) and Severity (PCI_ERR_UNCOR_SEVER, 0x0c) use the same bit positions
```

[`dpc_is_surprise_removal()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L349) reads Uncorrectable Error Status and tests S alone, which tells a surprise removal under a hotplug bridge from an error. [`dpc_get_aer_uncorrect_severity()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L236) reads Status, Mask and Severity whole and combines them bitwise into the severity of the record it builds.

```text
    Device Status of the port, at offset 0x0a of the PCI Express capability
    ───────────────────────────────────────────────────────────────────────

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    +0x0a │  no macro (15:6)  │T│P│U│F│N│C│
          └───────────────────┴─┴─┴─┴─┴─┴─┘

    C = PCI_EXP_DEVSTA_CED, N = PCI_EXP_DEVSTA_NFED, F = PCI_EXP_DEVSTA_FED (Fatal Error Detected),
    U = PCI_EXP_DEVSTA_URD, P = PCI_EXP_DEVSTA_AUXPD, T = PCI_EXP_DEVSTA_TRPND
    PCI_EXP_DEVSTA = 0x0a; the DPC paths write F alone, and no member caches the register
```

[`pci_clear_surpdn_errors()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L312) writes F to Device Status through [`pcie_capability_write_word()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/access.c#L490), which clears the Fatal Error Detected bit a Surprise Down leaves set. It also writes 0xffff to the Status register of the configuration header, which clears whichever of its error bits the removal set.

## DETAILS

The page first follows enumeration as it records the capability in the port's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352), then the port driver as it decides which ports get the DPC service, and the probe that installs the handlers and arms the port. The service's suspend, resume, removal and the save and restore of DPC Control come next, followed by one containment event: the hard interrupt handler, the thread that holds the port, the logging chosen by the Trigger Reason, the AER record and the Root Port PIO registers. Recovery then hands the port to the reset callback, whose bounded waits decide how long the port stays contained, and a surprise removal takes a shorter path through the same waits. The page ends with the wait queue through which the hotplug driver learns that recovery finished, and with the messages, hand-offs and files that expose all of this.

### Kconfig assumptions

The page documents the x86-64 defconfig resolved at the pinned v7.2 commit with the options of this campaign added, on x86-64 with ACPI. The table indexes the options the prose names, with the value the page assumes.

| Option | Assumed value | What it decides on these paths |
|---|---|---|
| [`CONFIG_PCIE_DPC`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L121) | y | builds dpc.c, the DPC members of [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) and the service registration |
| [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28) | y | a dependency of [`CONFIG_PCIE_DPC`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L121); builds the AER helpers the logging path calls |
| [`CONFIG_PCIEPORTBUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L5) | y | builds the port driver that creates the DPC service instance |
| [`CONFIG_PCI_MSI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L44) | y | lets [`pci_aer_available()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L138) answer true, which the DPC service bit needs |
| [`CONFIG_PM`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L217) | y | builds the port driver's PM callbacks that call the service's suspend and resume |
| [`CONFIG_HOTPLUG_PCI_PCIE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L16) | y | builds [`dpc_completed()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L81) and [`pci_dpc_recovered()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L103), through which the hotplug driver waits for recovery |
| [`CONFIG_PCIE_EDR`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L140) | unset | would request DPC control through `_OSC` and build the firmware-first caller of the logging and reset functions |
| [`CONFIG_ACPI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/Kconfig#L9) | y | the `_OSC` negotiation that sets the host bridge's [`native_aer`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L653) and [`native_dpc`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L658) bits |
| [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120) | y | makes the [`pci_dbg()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2896) sites on the recovery path dynamic-debug sites |
| [`CONFIG_PCI_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L70) | unset | would turn the same [`pci_dbg()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2896) sites on at build time |

The table is an index of the prose: each option is named again, with its effect, where it applies in the subsections below.

### Enumeration records the capability in the port's object

Every later DPC path needs the offset of the port's DPC capability and needs to know whether the port has the Root Port extensions, the RP PIO registers. The PCI core finds both once, while it sets up a function's capabilities, and keeps them in three members of the function's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) that exist under [`CONFIG_PCIE_DPC`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L121). The reader holds one object per function with three DPC members that enumeration writes and that every later path in dpc.c reads.

[`pci_device_add()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2726) runs the header fixups before it initializes the capabilities, and one fixup on the page's paths writes a DPC member. The lines below show that order.

```c
/* drivers/pci/probe.c:2726 */
void pci_device_add(struct pci_dev *dev, struct pci_bus *bus)
{
	... /* 15 lines, to :2743 */
	pcie_failed_link_retrain(dev);

	/* Fix up broken headers */
	pci_fixup_device(pci_fixup_header, dev);

	pci_reassigndev_resource_alignment(dev);

	pci_init_capabilities(dev);
```

The fixups of class header run at [`probe.c:2746`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2746), before [`pci_init_capabilities()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2650) at [`probe.c:2750`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2750), so a value a header fixup stores in a DPC member is already there when the DPC setup reads it. [`pci_init_capabilities()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2650) calls the DPC setup right after the AER setup, which the stage below shows.

```c
/* drivers/pci/probe.c:2650 */
static void pci_init_capabilities(struct pci_dev *dev)
{
	pci_ea_init(dev);		/* Enhanced Allocation */
	... /* 15 lines, to :2668 */
	pci_ptm_init(dev);		/* Precision Time Measurement */
	pci_aer_init(dev);		/* Advanced Error Reporting */
	pci_dpc_init(dev);		/* Downstream Port Containment */
	pci_rcec_init(dev);		/* Root Complex Event Collector */
```

[`pci_aer_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L385) has run when [`pci_dpc_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L403) starts, so [`aer_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370) of the same function is set by the time DPC code reads the port's AER registers through it. The DPC setup reads the DPC Capability register, whose fields `include/uapi/linux/pci_regs.h` defines as masks below the register's offset; read the block for the masks the setup and the probe test.

```c
/* include/uapi/linux/pci_regs.h:1081 */
/* Downstream Port Containment */
#define PCI_EXP_DPC_CAP			0x04	/* DPC Capability */
#define PCI_EXP_DPC_IRQ			0x001F	/* Interrupt Message Number */
#define  PCI_EXP_DPC_CAP_RP_EXT		0x0020	/* Root Port Extensions */
#define  PCI_EXP_DPC_CAP_POISONED_TLP	0x0040	/* Poisoned TLP Egress Blocking Supported */
#define  PCI_EXP_DPC_CAP_SW_TRIGGER	0x0080	/* Software Triggering Supported */
#define  PCI_EXP_DPC_RP_PIO_LOG_SIZE	0x0F00	/* RP PIO Log Size [3:0] */
#define  PCI_EXP_DPC_CAP_DL_ACTIVE	0x1000	/* ERR_COR signal on DL_Active supported */
#define  PCI_EXP_DPC_RP_PIO_LOG_SIZE4	0x2000	/* RP PIO Log Size [4] */
```

[`PCI_EXP_DPC_CAP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1082) is the offset of the register from the start of the capability, and the masks below it select fields of the 16-bit value read there. [`PCI_EXP_DPC_CAP_RP_EXT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1084) marks the Root Port extensions, and [`PCI_EXP_DPC_RP_PIO_LOG_SIZE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1087) and [`PCI_EXP_DPC_RP_PIO_LOG_SIZE4`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1089) hold the low four bits and the fifth bit of the RP PIO log size. The setup stores what it learns in [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352), which declares the three DPC members after a long run of members this page does not use.

```c
/* include/linux/pci.h:352 */
struct pci_dev {
... /* 183 lines, to :536 */
#ifdef CONFIG_PCIE_DPC
	u16		dpc_cap;
	unsigned int	dpc_rp_extensions:1;
	u8		dpc_rp_log_size;
#endif
```

[`dpc_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L537) holds the offset of the DPC capability in extended configuration space, and every DPC register access in dpc.c adds a register offset to it. [`dpc_rp_extensions`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L538) is a one-bit flag that the logging and surprise-removal paths test before they touch the RP PIO registers. [`dpc_rp_log_size`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L539) counts the dwords of RP PIO log the port provides, the header log plus an implementation-specific dword plus any prefix dwords. [`pci_dpc_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L403) fills them; read it for its three exits, a function without the capability, a port without the extensions, and a log size a fixup already set.

```c
/* drivers/pci/pcie/dpc.c:403 */
void pci_dpc_init(struct pci_dev *pdev)
{
	u16 cap;

	pdev->dpc_cap = pci_find_ext_capability(pdev, PCI_EXT_CAP_ID_DPC);
	if (!pdev->dpc_cap)
		return;

	pci_read_config_word(pdev, pdev->dpc_cap + PCI_EXP_DPC_CAP, &cap);
	if (!(cap & PCI_EXP_DPC_CAP_RP_EXT))
		return;

	pdev->dpc_rp_extensions = true;

	/* Quirks may set dpc_rp_log_size if device or firmware is buggy */
	if (!pdev->dpc_rp_log_size) {
		u16 flags;
		int ret;

		ret = pcie_capability_read_word(pdev, PCI_EXP_FLAGS, &flags);
		if (ret)
			return;

		pdev->dpc_rp_log_size =
				FIELD_GET(PCI_EXP_DPC_RP_PIO_LOG_SIZE, cap);
		if (FIELD_GET(PCI_EXP_FLAGS_FLIT, flags))
			pdev->dpc_rp_log_size += FIELD_GET(PCI_EXP_DPC_RP_PIO_LOG_SIZE4,
							   cap) << 4;

		if (pdev->dpc_rp_log_size < PCIE_STD_NUM_TLP_HEADERLOG ||
		    pdev->dpc_rp_log_size > PCIE_STD_MAX_TLP_HEADERLOG + 1) {
			pci_err(pdev, "RP PIO log size %u is invalid\n",
				pdev->dpc_rp_log_size);
			pdev->dpc_rp_log_size = 0;
		}
	}
}
```

[`pci_find_ext_capability()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L540) returns 0 for a function without the capability, and the setup then returns with [`dpc_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L537) at 0, the value [`pci_dpc_recovered()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L103) and [`edr_handle_event()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/edr.c#L151) test later. A port whose Capability register lacks [`PCI_EXP_DPC_CAP_RP_EXT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1084) keeps [`dpc_rp_extensions`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L538) at 0. On a port with the extensions, the log size is read from the Capability register in the local `cap` unless a fixup has already set it, and the fifth bit counts only when the PCI Express Capabilities register reports [`PCI_EXP_FLAGS_FLIT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L497). A size below [`PCIE_STD_NUM_TLP_HEADERLOG`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L23) or above [`PCIE_STD_MAX_TLP_HEADERLOG`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L25) + 1, outside 4 to 15 dwords at v7.2, is printed with [`pci_err()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2891) and replaced by 0, which the RP PIO path later reads as no log.

The capability search is the PCI core's [`pci_find_ext_capability()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L540), whose comment states what it returns for a function without the capability; read it for that result.

```c
/* drivers/pci/pci.c:526 */
/**
 * pci_find_ext_capability - Find an extended capability
 * @dev: PCI device to query
 * @cap: capability code
 *
 * Returns the address of the requested extended capability structure
 * within the device's PCI configuration space or 0 if the device does
 * not support it.  Possible values for @cap include:
 *
 *  %PCI_EXT_CAP_ID_ERR		Advanced Error Reporting
 *  %PCI_EXT_CAP_ID_VC		Virtual Channel
 *  %PCI_EXT_CAP_ID_DSN		Device Serial Number
 *  %PCI_EXT_CAP_ID_PWR		Power Budgeting
 */
u16 pci_find_ext_capability(struct pci_dev *dev, int cap)
{
	return pci_find_next_ext_capability(dev, 0, cap);
}
```

The function returns the offset of the capability with the requested ID in the extended list, or 0, and [`pci_dpc_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L403) stores that value as it is. The strip follows the three members from the allocation of the object to the end of [`pci_dpc_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L403), with a mark at each write the page shows.

```text
    The DPC members of one port's struct pci_dev, from allocation to the end of enumeration
    ────────────────────────────────────────────────────────────────────────────────────────
    fields: dpc_cap, dpc_rp_extensions and dpc_rp_log_size, members only under CONFIG_PCIE_DPC

    time ────────────────────────────────────────────────────────────────────────────────────────────────────▶
    event               allocation   header fixup     capability      RP_EXT        log size
                                                      search          tested        read
                        ▼            ▼                ▼               ▼             ▼
                        ┌─────────────────────────────┬────────────────────────────────────────────────────────
    dpc_cap             │ 0                           │① offset of the capability, 0 if none
                        └─────────────────────────────┴────────────────────────────────────────────────────────
                        ┌─────────────────────────────────────────────┬────────────────────────────────────────
    dpc_rp_extensions   │ 0                                           │② 1 when RP_EXT is set
                        └─────────────────────────────────────────────┴────────────────────────────────────────
                        ┌────────────┬──────────────────────────────────────────────┬──────────────────────────
    dpc_rp_log_size     │ 0          │ 0, or 4 where a fixup                        │③ SIZE
                        │            │ overrides the field                          │④ + bit 4 << 4
                        │            │ firmware left at 0                           │⑤ 0 if out of 4..15
                        └────────────┴──────────────────────────────────────────────┴──────────────────────────

    ① pci_dpc_init  dpc.c:407  stores the offset the extended capability search returns
    ② pci_dpc_init  :415  records that the port implements the Root Port extensions
    ③ pci_dpc_init  :426  takes RP PIO Log Size bits 3:0 when no fixup set a size
    ④ pci_dpc_init  :429  adds bit 4 of the size, shifted, on a port that supports Flit Mode
    ⑤ pci_dpc_init  :436  stores 0 after reporting a size outside 4 to 15
```

① [`pci_dpc_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L403) stores the offset of the capability in [`dpc_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L537) at [`dpc.c:407`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L407). ② `pci_dpc_init()` sets [`dpc_rp_extensions`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L538) at [`dpc.c:415`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L415) once the Capability register reports the extensions. ③ `pci_dpc_init()` takes the low four bits of the size into [`dpc_rp_log_size`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L539) at [`dpc.c:426`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L426) when no fixup set one. ④ `pci_dpc_init()` adds the fifth bit at [`dpc.c:429`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L429) on a port that supports Flit Mode. ⑤ `pci_dpc_init()` stores 0 at [`dpc.c:436`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L436) after it reports a size outside 4 to 15. Two writers of these members are not shown: [`pci_alloc_dev()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2500) in probe.c allocates the object zeroed, which belongs to the object's allocation on another page, and the header fixup [`dpc_log_size()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/quirks.c#L6335) in quirks.c stores 4 for a set of ports whose firmware leaves the size at 0, which the page leaves out as a device-specific mechanism.

After enumeration the three members are settled for the life of the object, with no writer in the tree past [`pci_dpc_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L403) at v7.2, and the next question is which ports get a service that uses them.

### The port driver gives DPC service where AER is owned

Containment needs a driver that takes the port's interrupt and runs recovery, and on x86 the PCIe port driver provides it as one of the services it splits a port into. The port driver creates a service device, a [`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59), for each service bit a port qualifies for, and service drivers bind to those devices by bit. The reader holds the port's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) as the parent, one service device per bit as its children, and the DPC service driver bound to the child for the DPC bit; whether that child exists decides whether anything below runs.

A service driver is described by [`struct pcie_port_service_driver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L78), which pairs the service bit and port type it matches with the callbacks the port driver calls. Read the type for the callbacks the DPC driver fills and the ones it leaves empty.

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
```

[`name`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L79) names the driver, and [`service`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L91) and [`port_type`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L90) are the two values the port bus matches against a service device. [`probe`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L80) and [`remove`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L81) run at bind and unbind, and [`suspend`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L82), [`resume`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L84) and [`resume_noirq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L83) run from the port's system sleep callbacks. [`runtime_suspend`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L85) and [`runtime_resume`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L86) run from the port's runtime PM and [`slot_reset`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L88) from its error-recovery slot reset, and [`driver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L93) is the embedded driver-model driver that registration fills. The DPC driver is one instance of the type; read [`dpcdriver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L523) for the values it supplies.

```c
/* drivers/pci/pcie/dpc.c:523 */
static struct pcie_port_service_driver dpcdriver = {
	.name		= "dpc",
	.port_type	= PCIE_ANY_PORT,
	.service	= PCIE_PORT_SERVICE_DPC,
	.probe		= dpc_probe,
	.suspend	= dpc_suspend,
	.resume		= dpc_resume,
	.remove		= dpc_remove,
};
```

[`dpcdriver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L523) matches [`PCIE_PORT_SERVICE_DPC`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L22) on any port type, since [`PCIE_ANY_PORT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L57) is all ones, and supplies [`dpc_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L473), [`dpc_suspend()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L506), [`dpc_resume()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L512) and [`dpc_remove()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L518). It leaves [`resume_noirq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L83), the runtime pair and [`slot_reset`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L88) NULL, which the port driver tests before it calls a callback, as the PM subsection below shows. [`pcie_dpc_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L533) registers the driver; read it with [`pcie_port_service_register()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L586), which it calls.

```c
/* drivers/pci/pcie/dpc.c:533 */
int __init pcie_dpc_init(void)
{
	return pcie_port_service_register(&dpcdriver);
}
```

```c
/* drivers/pci/pcie/portdrv.c:586 */
int pcie_port_service_register(struct pcie_port_service_driver *new)
{
	if (pcie_ports_disabled)
		return -ENODEV;

	new->driver.name = new->name;
	new->driver.bus = &pcie_port_bus_type;

	return driver_register(&new->driver);
}
```

Registration fails with -ENODEV when [`pcie_ports_disabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L607) is set, the value the `pcie_ports=compat` boot option gives it, and otherwise registers the embedded driver on [`pcie_port_bus_type`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L575). [`pcie_init_services()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L830) calls the registration at boot together with those of the other services, as the lines below show.

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
```

The DPC driver registers after the AER and PME drivers, and the port bus then binds it to service devices with [`pcie_port_bus_match()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L511); read it for the two tests a service device must pass.

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

A service device binds to [`dpcdriver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L523) when its [`service`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L62) is [`PCIE_PORT_SERVICE_DPC`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L22), and the port-type test passes for every port because the driver's type is [`PCIE_ANY_PORT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L57). Which ports get such a device is decided when the port driver probes the port, in [`pcie_port_device_register()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L331), which the stage below shows.

```c
/* drivers/pci/pcie/portdrv.c:331 */
static int pcie_port_device_register(struct pci_dev *dev)
{
	... /* 9 lines, to :342 */
	capabilities = get_port_device_capability(dev);
	if (!capabilities)
		return 0;
	... /* 9 lines, to :354 */
	status = pcie_init_service_irqs(dev, irqs, capabilities);
	if (status) {
		capabilities &= PCIE_PORT_SERVICE_HP;
		if (!capabilities)
			goto error_disable;
	}
	... /* 4 lines, to :364 */
	for (i = 0; i < PCIE_PORT_DEVICE_MAXSERVICES; i++) {
		int service = 1 << i;
		if (!(capabilities & service))
			continue;
		if (!pcie_device_init(dev, service, irqs[i]))
			nr_service++;
	}
```

The port driver asks [`get_port_device_capability()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L218) for the service bits, sets up interrupts for them in [`pcie_init_service_irqs()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L177), and creates one service device for each bit through [`pcie_device_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L290). When interrupt setup fails, only the hotplug bit survives, so a port without a usable vector gets no DPC service device. The DPC bit itself is decided by the stage of [`get_port_device_capability()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L218) below, which needs the AER bit first.

```c
/* drivers/pci/pcie/portdrv.c:218 */
static int get_port_device_capability(struct pci_dev *dev)
{
	struct pci_host_bridge *host = pci_find_host_bridge(dev->bus);
	int services = 0;
... /* 17 lines, to :239 */
#ifdef CONFIG_PCIEAER
	if ((pci_pcie_type(dev) == PCI_EXP_TYPE_ROOT_PORT ||
             pci_pcie_type(dev) == PCI_EXP_TYPE_RC_EC) &&
	    dev->aer_cap && pci_aer_available() &&
	    (pcie_ports_native || host->native_aer))
		services |= PCIE_PORT_SERVICE_AER;
#endif
	... /* 15 lines, to :261 */
	/*
	 * With dpc-native, allow Linux to use DPC even if it doesn't have
	 * permission to use AER.
	 */
	if (pci_find_ext_capability(dev, PCI_EXT_CAP_ID_DPC) &&
	    pci_aer_available() &&
	    (pcie_ports_dpc_native || (services & PCIE_PORT_SERVICE_AER)))
		services |= PCIE_PORT_SERVICE_DPC;
```

The AER bit is set for a Root Port or a Root Complex Event Collector with an AER capability when [`pci_aer_available()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L138) answers true and the OS owns AER, through [`pcie_ports_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L614) or the host bridge's [`native_aer`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L653). The DPC bit then needs a DPC capability, AER availability, and either the AER bit of the same port or [`pcie_ports_dpc_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L620). At v7.2 a Switch Downstream Port never gets the AER bit from this function, so it gets the DPC service only under dpc-native. [`pci_aer_available()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L138) carries the two global conditions; read it for them.

```c
/* drivers/pci/pcie/aer.c:138 */
bool pci_aer_available(void)
{
	return !pcie_aer_disable && pci_msi_enabled();
}
```

AER is available unless [`pci_no_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L133) has set the flag and as long as [`pci_msi_enabled()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/msi/api.c#L407) answers true, which needs [`CONFIG_PCI_MSI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L44). The dpc-native override comes from the `pcie_ports=` boot option, which [`pcie_port_setup()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L622) parses; read it with the comment above the flag.

```c
/* drivers/pci/pcie/portdrv.c:616 */
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

`pcie_ports=dpc-native` sets [`pcie_ports_dpc_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L620), which gives a port the DPC service without the AER bit and, as the probe shows next, also lets the probe bind without AER ownership. `pcie_ports=native` sets [`pcie_ports_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L614), which makes the OS own AER and therefore DPC on Root Ports, and `pcie_ports=compat` sets [`pcie_ports_disabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L607), which stops the service drivers from registering. The figure places these rules on a hierarchy.

```text
    Where in a hierarchy portdrv gives a port the DPC service
    ─────────────────────────────────────────────────────────
    (every port drawn has a DPC capability, and pci_aer_available() is true)

                ┌─────────────────────────── host bridge ────────────────────────────┐
                │ native_aer: granted through _OSC, or forced by pcie_ports=native   │
                └─────────┬───────────────────────────────────────────┬──────────────┘
                          │ native_aer 1                              │ native_aer 0
                   ┌──────┴──────┐                             ┌──────┴──────┐
    Root Ports     │  Root Port  │ AER service, so             │  Root Port  │ no AER service: DPC
                   │             │ DPC service                 │             │ service only with
                   └──────┬──────┘                             └─────────────┘ pcie_ports=dpc-native
                          │
                   ┌──────┴──────┐
    switch         │   Upstream  │
                   │     Port    │
                   └──┬───────┬──┘
     ─ ─ ─ ─ ─ ─ ─ ─ ─┼─ ─ ─ ─┼─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  below the Root Ports: no AER service
                   ┌──┴──┐ ┌──┴──┐
    Downstream     │ DSP │ │ DSP │  DPC service only with pcie_ports=dpc-native
    Ports          └─────┘ └─────┘

    portdrv gives the AER service bit to Root Ports and Root Complex Event Collectors alone, and
    pcie_ports=dpc-native sets pcie_ports_dpc_native, which also lets dpc_probe() bind without AER
```

A Root Port or Root Complex Event Collector that the OS owns AER for gets the DPC service by default, and a Switch Downstream Port, or a Root Port whose AER the firmware keeps, needs `pcie_ports=dpc-native`. The host bridge's [`native_dpc`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L658) bit plays no part in this decision; the hotplug subsection shows where dpc.c reads it.

### The probe installs two handlers and arms the port

Once the service device exists, its probe has to confirm that the kernel may handle errors on the port, connect the port's interrupt to a two-stage handler, and only then let the port trigger, so that no trigger arrives before a handler can take it. The probe receives the service device, a [`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59), portdrv's service instance for one port and one service; read it for the three members the DPC code uses.

```c
/* drivers/pci/pcie/portdrv.h:59 */
struct pcie_device {
	int		irq;	    /* Service IRQ/MSI/MSI-X Vector */
	struct pci_dev *port;	    /* Root/Upstream/Downstream Port */
	u32		service;    /* Port service this device represents */
	void		*priv_data; /* Service Private Data */
	struct device	device;     /* Generic Device Interface */
};
```

[`port`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L61) points at the port's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352), the object whose DPC members enumeration filled, and [`irq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L60) is the Linux interrupt number portdrv assigned to the DPC service. [`device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L64) is the embedded driver-model device, which owns the device-managed interrupt the probe requests, and [`service`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L62) is the bit the port bus matched. [`priv_data`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L63) stays unused by DPC. The probe's first test is [`pcie_aer_is_native()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L242); read it for the two conditions it adds to the service bit's.

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

The port must have an AER capability, and the OS must own AER through [`pcie_ports_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L614) or the host bridge's [`native_aer`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L653). [`dpc_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L473) accepts a port that passes this test or any port under dpc-native; read the whole probe for the order of the request, the arming and the save buffer, with the [`FLAG()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L472) helper macro above it that turns a capability bit into a plus or a minus.

```c
/* drivers/pci/pcie/dpc.c:472 */
#define FLAG(x, y) (((x) & (y)) ? '+' : '-')
static int dpc_probe(struct pcie_device *dev)
{
	struct pci_dev *pdev = dev->port;
	struct device *device = &dev->device;
	int status;
	u16 cap;

	if (!pcie_aer_is_native(pdev) && !pcie_ports_dpc_native)
		return -ENOTSUPP;

	status = devm_request_threaded_irq(device, dev->irq, dpc_irq,
					   dpc_handler, IRQF_SHARED,
					   "pcie-dpc", pdev);
	if (status) {
		pci_warn(pdev, "request IRQ%d failed: %d\n", dev->irq,
			 status);
		return status;
	}

	pci_read_config_word(pdev, pdev->dpc_cap + PCI_EXP_DPC_CAP, &cap);
	dpc_enable(dev);

	pci_info(pdev, "enabled with IRQ %d\n", dev->irq);
	pci_info(pdev, "error containment capabilities: Int Msg #%d, RPExt%c PoisonedTLP%c SwTrigger%c RP PIO Log %d, DL_ActiveErr%c\n",
		 cap & PCI_EXP_DPC_IRQ, FLAG(cap, PCI_EXP_DPC_CAP_RP_EXT),
		 FLAG(cap, PCI_EXP_DPC_CAP_POISONED_TLP),
		 FLAG(cap, PCI_EXP_DPC_CAP_SW_TRIGGER), pdev->dpc_rp_log_size,
		 FLAG(cap, PCI_EXP_DPC_CAP_DL_ACTIVE));

	pci_add_ext_cap_save_buffer(pdev, PCI_EXT_CAP_ID_DPC, sizeof(u16));
	return status;
}
```

The probe refuses the port with -ENOTSUPP when neither condition holds. It then requests the interrupt on the service's vector with [`dpc_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L386) as the hard handler and [`dpc_handler()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L363) as the threaded one, shared with the other services of the port through `IRQF_SHARED` and named "pcie-dpc", with the port's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) as the context both handlers receive. A failed request prints "request IRQ%d failed" and returns the error before the port is armed. The probe reads the Capability register into the local `cap`, arms the port with [`dpc_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L441), prints two [`pci_info()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2895) lines, and adds a save buffer for one 16-bit value, which the next subsection reads. [`dpc_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L441) works on DPC Control, whose bits `pci_regs.h` defines below the register's offset.

```c
/* include/uapi/linux/pci_regs.h:1091 */
#define PCI_EXP_DPC_CTL			0x06	/* DPC control */
#define  PCI_EXP_DPC_CTL_EN_FATAL	0x0001	/* Enable trigger on ERR_FATAL message */
#define  PCI_EXP_DPC_CTL_EN_NONFATAL	0x0002	/* Enable trigger on ERR_NONFATAL message */
#define  PCI_EXP_DPC_CTL_INT_EN		0x0008	/* DPC Interrupt Enable */
```

[`PCI_EXP_DPC_CTL_EN_FATAL`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1092) and [`PCI_EXP_DPC_CTL_EN_NONFATAL`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1093) select the error messages that trigger the port, and [`PCI_EXP_DPC_CTL_INT_EN`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1094) lets a trigger raise the DPC interrupt. dpc.c groups the two trigger bits in one mask, which the arming clears before it sets the bit it wants.

```c
/* drivers/pci/pcie/dpc.c:21 */
#define PCI_EXP_DPC_CTL_EN_MASK	(PCI_EXP_DPC_CTL_EN_FATAL | \
				 PCI_EXP_DPC_CTL_EN_NONFATAL)
```

[`dpc_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L441) clears a stale interrupt first and then arms the port; read it for the order of the two writes.

```c
/* drivers/pci/pcie/dpc.c:441 */
static void dpc_enable(struct pcie_device *dev)
{
	struct pci_dev *pdev = dev->port;
	int dpc = pdev->dpc_cap;
	u16 ctl;

	/*
	 * Clear DPC Interrupt Status so we don't get an interrupt for an
	 * old event when setting DPC Interrupt Enable.
	 */
	pci_write_config_word(pdev, dpc + PCI_EXP_DPC_STATUS,
			      PCI_EXP_DPC_STATUS_INTERRUPT);

	pci_read_config_word(pdev, dpc + PCI_EXP_DPC_CTL, &ctl);
	ctl &= ~PCI_EXP_DPC_CTL_EN_MASK;
	ctl |= PCI_EXP_DPC_CTL_EN_FATAL | PCI_EXP_DPC_CTL_INT_EN;
	pci_write_config_word(pdev, dpc + PCI_EXP_DPC_CTL, ctl);
}
```

The first write clears Interrupt Status in DPC Status, which the comment explains, so that setting the interrupt enable does not deliver an old event. The second is a read-modify-write of DPC Control that clears both trigger bits through [`PCI_EXP_DPC_CTL_EN_MASK`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L21) and then sets [`PCI_EXP_DPC_CTL_EN_FATAL`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1092) and [`PCI_EXP_DPC_CTL_INT_EN`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1094). The figure shows what the write leaves in the register.

```text
    What the probe leaves in DPC Control, whatever firmware left there
    ──────────────────────────────────────────────────────────────────

    bit                 15 ... 4       3     2     1     0
                    ┌───────────────┬─────┬─────┬─────┬─────┐
    as read         │       a       │  i  │  b  │  n  │  f  │
                    └───────────────┴─────┴─────┴─────┴─────┘
                            ▼          ▼     ▼     ▼     ▼    ctl &= ~PCI_EXP_DPC_CTL_EN_MASK, then
                                                              ctl |= EN_FATAL | INT_EN
                    ┌───────────────┬─────┬─────┬─────┬─────┐
    as written      │       a       │  1  │  b  │  0  │  1  │
                    └───────────────┴─────┴─────┴─────┴─────┘

    bit 0 = PCI_EXP_DPC_CTL_EN_FATAL, bit 1 = PCI_EXP_DPC_CTL_EN_NONFATAL, bit 3 = PCI_EXP_DPC_CTL_INT_EN
    a and b are written back as read; Interrupt Status in DPC Status is cleared before this write
```

An armed port triggers on `ERR_FATAL` with the interrupt enabled, which the comment in [`dpc_handler()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L363) states as "We configure DPC so it only triggers on `ERR_FATAL`", and keeps the other bits of DPC Control as firmware left them.

### Suspend and removal disarm the port, resume arms it

An armed port can trigger whenever an error arrives, also while the port is suspended and after the service is gone. The message of commit commit [75c47c790f43](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=75c47c790f43c438761fc049fb9d438144a9db45) ("PCI/DPC: Disable DPC service on suspend") reports that a link powered off during suspend can see electrical noise that triggers DPC, and a DPC interrupt that shares the vector with PME then wakes the system. The DPC driver therefore disarms the port on the way into a sleep state and at unbind, arms it again on resume, and lets the PCI core save and restore DPC Control with the rest of the port's configuration. The reader holds DPC Control as a register that moves between armed and disarmed under these callbacks, with one saved copy beside it.

The port driver reaches the service callbacks from its own PM callbacks in [`pcie_portdrv_pm_ops`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L656), which map the system sleep transitions onto two functions of the port driver; read the table for which transition calls which.

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

Suspend, freeze and poweroff call [`pcie_port_device_suspend()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L405), and resume, thaw and restore call [`pcie_port_device_resume()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L421), so the DPC driver disarms the port before a system sleep transition and arms it after one. Both functions, built under [`CONFIG_PM`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L217), apply one callback offset to the port's child service devices; read them with the iterator they hand the offset to.

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

[`pcie_port_device_iter()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L385) reads the callback at the given offset of the bound service driver and calls it only when it is not NULL, which is why [`dpcdriver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L523) can leave [`resume_noirq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L83) and the runtime callbacks empty. The DPC callbacks themselves are wrappers around [`dpc_disable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L460) and [`dpc_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L441); read the disarm first.

```c
/* drivers/pci/pcie/dpc.c:460 */
static void dpc_disable(struct pcie_device *dev)
{
	struct pci_dev *pdev = dev->port;
	int dpc = pdev->dpc_cap;
	u16 ctl;

	/* Disable DPC triggering and DPC interrupts */
	pci_read_config_word(pdev, dpc + PCI_EXP_DPC_CTL, &ctl);
	ctl &= ~(PCI_EXP_DPC_CTL_EN_FATAL | PCI_EXP_DPC_CTL_INT_EN);
	pci_write_config_word(pdev, dpc + PCI_EXP_DPC_CTL, ctl);
}
```

[`dpc_disable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L460) clears [`PCI_EXP_DPC_CTL_EN_FATAL`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1092) and [`PCI_EXP_DPC_CTL_INT_EN`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1094) in a read-modify-write and leaves [`PCI_EXP_DPC_CTL_EN_NONFATAL`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1093) as it was, which arming had cleared. The three callbacks call it or [`dpc_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L441).

```c
/* drivers/pci/pcie/dpc.c:506 */
static int dpc_suspend(struct pcie_device *dev)
{
	dpc_disable(dev);
	return 0;
}

static int dpc_resume(struct pcie_device *dev)
{
	dpc_enable(dev);
	return 0;
}

static void dpc_remove(struct pcie_device *dev)
{
	dpc_disable(dev);
}
```

[`dpc_suspend()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L506) and [`dpc_remove()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L518) disarm and [`dpc_resume()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L512) arms, and since [`dpc_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L441) clears Interrupt Status first, an error that set it during the sleep raises no interrupt on resume. Removal reaches [`dpc_remove()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L518) through the port bus when the service device is unregistered; read the bus's remove callback for that call.

```c
/* drivers/pci/pcie/portdrv.c:562 */
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

The interrupt the probe requested is device-managed on the service device, so the driver core releases it when the device is unbound, after [`dpc_remove()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L518) has disarmed the port. Whenever the PCI core restores the port's saved state it also writes DPC Control back, from a copy in a save buffer that [`dpc_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L473) added with [`pci_add_ext_cap_save_buffer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L3475); read the buffer's allocation.

```c
/* drivers/pci/pci.c:3444 */
static int _pci_add_cap_save_buffer(struct pci_dev *dev, u16 cap,
				    bool extended, unsigned int size)
{
	int pos;
	struct pci_cap_saved_state *save_state;

	if (extended)
		pos = pci_find_ext_capability(dev, cap);
	else
		pos = pci_find_capability(dev, cap);

	if (!pos)
		return 0;

	save_state = kzalloc(sizeof(*save_state) + size, GFP_KERNEL);
	if (!save_state)
		return -ENOMEM;

	save_state->cap.cap_nr = cap;
	save_state->cap.cap_extended = extended;
	save_state->cap.size = size;
	pci_add_saved_cap(dev, save_state);

	return 0;
}

int pci_add_cap_save_buffer(struct pci_dev *dev, char cap, unsigned int size)
{
	return _pci_add_cap_save_buffer(dev, cap, false, size);
}

int pci_add_ext_cap_save_buffer(struct pci_dev *dev, u16 cap, unsigned int size)
{
	return _pci_add_cap_save_buffer(dev, cap, true, size);
}
```

The buffer is a [`struct pci_cap_saved_state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L246) tagged with the extended capability ID [`PCI_EXT_CAP_ID_DPC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L753) and sized for the 16-bit value the probe asked for, and it exists only when the function has the capability. [`pci_save_dpc_state()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L46) and [`pci_restore_dpc_state()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L62) look the buffer up by that ID and copy DPC Control into and out of its first word.

```c
/* drivers/pci/pcie/dpc.c:46 */
void pci_save_dpc_state(struct pci_dev *dev)
{
	struct pci_cap_saved_state *save_state;
	u16 *cap;

	if (!pci_is_pcie(dev))
		return;

	save_state = pci_find_saved_ext_cap(dev, PCI_EXT_CAP_ID_DPC);
	if (!save_state)
		return;

	cap = (u16 *)&save_state->cap.data[0];
	pci_read_config_word(dev, dev->dpc_cap + PCI_EXP_DPC_CTL, cap);
}

void pci_restore_dpc_state(struct pci_dev *dev)
{
	struct pci_cap_saved_state *save_state;
	u16 *cap;

	if (!pci_is_pcie(dev))
		return;

	save_state = pci_find_saved_ext_cap(dev, PCI_EXT_CAP_ID_DPC);
	if (!save_state)
		return;

	cap = (u16 *)&save_state->cap.data[0];
	pci_write_config_word(dev, dev->dpc_cap + PCI_EXP_DPC_CTL, *cap);
}
```

Both return early for a function that is not PCIe or has no buffer, and a buffer exists only after [`dpc_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L473) ran on the port, so the PCI core saves and restores DPC Control only for ports the service armed. [`pci_save_state()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L1747) calls the save after the config header and the PCIe capability.

```c
/* drivers/pci/pci.c:1747 */
int pci_save_state(struct pci_dev *dev)
{
	int i;
	/* XXX: 100% dword access ok here? */
	for (i = 0; i < 16; i++) {
		pci_read_config_dword(dev, i * 4, &dev->saved_config_space[i]);
		pci_dbg(dev, "save config %#04x: %#010x\n",
			i * 4, dev->saved_config_space[i]);
	}
	dev->state_saved = true;

	i = pci_save_pcie_state(dev);
	if (i != 0)
		return i;

	i = pci_save_pcix_state(dev);
	if (i != 0)
		return i;

	pci_save_dpc_state(dev);
	pci_save_aer_state(dev);
	pci_save_ptm_state(dev);
	pci_save_tph_state(dev);
	return pci_save_vc_state(dev);
}
```

[`pci_restore_state()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L1826) calls the restore with the other extended capabilities, before it clears and restores AER and before it writes the config header back.

```c
/* drivers/pci/pci.c:1826 */
void pci_restore_state(struct pci_dev *dev)
{
	pci_restore_pcie_state(dev);
	pci_restore_pasid_state(dev);
	pci_restore_pri_state(dev);
	pci_restore_ats_state(dev);
	pci_restore_vc_state(dev);
	pci_restore_rebar_state(dev);
	pci_restore_dpc_state(dev);
	pci_restore_ptm_state(dev);
	pci_restore_tph_state(dev);

	pci_aer_clear_status(dev);
	pci_restore_aer_state(dev);

	pci_restore_config_space(dev);

	pci_restore_pcix_state(dev);
	pci_restore_msi_state(dev);

	/* Restore ACS and IOV configuration state */
	pci_enable_acs(dev);
	pci_restore_iov_state(dev);

	dev->state_saved = false;
}
```

The port driver saves the port's state right after it creates the service devices, so the first copy holds DPC Control as [`dpc_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L473) left it; read the stage of [`pcie_portdrv_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L685) for that order.

```c
/* drivers/pci/pcie/portdrv.c:685 */
static int pcie_portdrv_probe(struct pci_dev *dev,
					const struct pci_device_id *id)
{
	... /* 10 lines, to :698 */
	if (type == PCI_EXP_TYPE_RC_EC)
		pcie_link_rcec(dev);

	status = pcie_port_device_register(dev);
	if (status)
		return status;

	pci_save_state(dev);
```

[`pcie_port_device_register()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L331) creates and probes the service devices, and [`pci_save_state()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L1747) runs after it, so the saved copy is the armed register. The figure gathers the transitions of DPC Control.

```text
    DPC Control of one port across the life of its DPC service
    ──────────────────────────────────────────────────────────

    ┌──────────────────────┐    probe ➊     ┌──────────────────────┐    save ➎    ┌──────────────────────┐
    │ as firmware left it  ├───────────────▶│ armed                ├─────────────▶│ saved copy, one u16  │
    │ no service bound     │                │ EN_FATAL 1, INT_EN 1 │              │ in the buffer the    │
    └──────────────────────┘                │ EN_NONFATAL 0        │◀─────────────┤ probe added          │
                                            └─────┬──────────▲─────┘  restore ➏   └──────────────────────┘
                                                  │          │
                                       suspend ➋  │          │  resume ➌
                                       remove ➍   │          │
                                                  ▼          │
                                            ┌────────────────┴─────┐
                                            │ disarmed             │
                                            │ EN_FATAL 0, INT_EN 0 │
                                            │ EN_NONFATAL 0        │
                                            └──────────────────────┘

    ➊ dpc_probe              dpc.c:493  arms Control once both handlers are installed
    ➋ dpc_suspend            :508  disarms Control when the port is suspended or frozen
    ➌ dpc_resume             :514  arms Control again when the port resumes or thaws
    ➍ dpc_remove             :520  disarms Control when the service is unbound
    ➎ pci_save_dpc_state     :59   copies Control into the buffer, from whichever state it is in
    ➏ pci_restore_dpc_state  :75   writes the saved copy back into Control
```

➊ [`dpc_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L473) arms the port at [`dpc.c:493`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L493) once both handlers are installed. ➋ [`dpc_suspend()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L506) disarms it at [`dpc.c:508`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L508) on suspend, freeze and poweroff. ➌ [`dpc_resume()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L512) arms it again at [`dpc.c:514`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L514) on resume, thaw and restore. ➍ [`dpc_remove()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L518) disarms it at [`dpc.c:520`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L520) when the service is unbound. ➎ [`pci_save_dpc_state()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L46) copies Control into the buffer at [`dpc.c:59`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L59), from whichever state the register is in. ➏ [`pci_restore_dpc_state()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L62) writes the saved copy back at [`dpc.c:75`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L75).

So far, the port's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) holds the capability offset and the extension facts, a DPC service device is bound on a port the OS owns AER for, and the port is armed with both handlers installed and a saved copy of DPC Control behind it.

### The hard handler claims, acknowledges and passes on the interrupt

When an armed port triggers, it raises the DPC interrupt on a vector it can share with the port's other services, and the handler that runs first is in hard interrupt context, where it cannot sleep through the waits recovery needs. The hard handler therefore decides whether the interrupt is a DPC one, acknowledges it, and passes a trigger to the thread. The reader holds DPC Status as the one register both questions are asked of, with Interrupt Status saying the port raised an interrupt and Trigger Status saying the port is contained.

DPC Status holds both bits the handler tests, and `pci_regs.h` defines them together with the Trigger Reason fields the thread reads later; read the block for the bit positions and the reason values.

```c
/* include/uapi/linux/pci_regs.h:1096 */
#define PCI_EXP_DPC_STATUS		0x08	/* DPC Status */
#define  PCI_EXP_DPC_STATUS_TRIGGER	    0x0001 /* Trigger Status */
#define  PCI_EXP_DPC_STATUS_TRIGGER_RSN	    0x0006 /* Trigger Reason */
#define  PCI_EXP_DPC_STATUS_TRIGGER_RSN_UNCOR  0x0000 /* Uncorrectable error */
#define  PCI_EXP_DPC_STATUS_TRIGGER_RSN_NFE    0x0002 /* Rcvd ERR_NONFATAL */
#define  PCI_EXP_DPC_STATUS_TRIGGER_RSN_FE     0x0004 /* Rcvd ERR_FATAL */
#define  PCI_EXP_DPC_STATUS_TRIGGER_RSN_IN_EXT 0x0006 /* Reason in Trig Reason Extension field */
#define  PCI_EXP_DPC_STATUS_INTERRUPT	    0x0008 /* Interrupt Status */
#define  PCI_EXP_DPC_RP_BUSY		    0x0010 /* Root Port Busy */
#define  PCI_EXP_DPC_STATUS_TRIGGER_RSN_EXT 0x0060 /* Trig Reason Extension */
#define  PCI_EXP_DPC_STATUS_TRIGGER_RSN_RP_PIO		0x0000	/* RP PIO error */
#define  PCI_EXP_DPC_STATUS_TRIGGER_RSN_SW_TRIGGER	0x0020	/* DPC SW Trigger bit */
#define  PCI_EXP_DPC_RP_PIO_FEP		    0x1f00 /* RP PIO First Err Ptr */
```

[`PCI_EXP_DPC_STATUS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1096) is the register's offset, [`PCI_EXP_DPC_STATUS_TRIGGER`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1097) is bit 0, Trigger Status, and [`PCI_EXP_DPC_STATUS_INTERRUPT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1103) is bit 3, Interrupt Status. [`PCI_EXP_DPC_STATUS_TRIGGER_RSN`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1098) masks bits 2:1, the Trigger Reason, with the four values the thread compares it against, and [`PCI_EXP_DPC_STATUS_TRIGGER_RSN_EXT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1105) masks the extension field bits 6:5 with its two named values. [`PCI_EXP_DPC_RP_BUSY`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1104) is Root Port Busy, which the reset callback polls, and [`PCI_EXP_DPC_RP_PIO_FEP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1108) is the RP PIO First Error Pointer the logging prints. [`dpc_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L386) reads the register once and acts on two of these bits; read it for its three return values.

```c
/* drivers/pci/pcie/dpc.c:386 */
static irqreturn_t dpc_irq(int irq, void *context)
{
	struct pci_dev *pdev = context;
	u16 cap = pdev->dpc_cap, status;

	pci_read_config_word(pdev, cap + PCI_EXP_DPC_STATUS, &status);

	if (!(status & PCI_EXP_DPC_STATUS_INTERRUPT) || PCI_POSSIBLE_ERROR(status))
		return IRQ_NONE;

	pci_write_config_word(pdev, cap + PCI_EXP_DPC_STATUS,
			      PCI_EXP_DPC_STATUS_INTERRUPT);
	if (status & PCI_EXP_DPC_STATUS_TRIGGER)
		return IRQ_WAKE_THREAD;
	return IRQ_HANDLED;
}
```

The handler reads DPC Status through [`dpc_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L537) of the port, which arrives as the `context` argument registered by the probe. An interrupt without Interrupt Status, or a read that returns all ones, which [`PCI_POSSIBLE_ERROR()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L175) tests, gets `IRQ_NONE`, so the other handlers on a shared vector still run. Otherwise the handler writes Interrupt Status back as 1 to clear it and wakes the thread when Trigger Status is set, or returns `IRQ_HANDLED` for an interrupt that carries no trigger. The all-ones test is [`PCI_POSSIBLE_ERROR()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L175) in include/linux/pci.h; read it with the comment above it for what the test can tell.

```c
/* include/linux/pci.h:168 */
/*
 * Reading from a device that doesn't respond typically returns ~0.  A
 * successful read from a device may also return ~0, so you need additional
 * information to reliably identify errors.
 */
#define PCI_ERROR_RESPONSE		(~0ULL)
#define PCI_SET_ERROR_RESPONSE(val)	(*(val) = ((typeof(*(val))) PCI_ERROR_RESPONSE))
#define PCI_POSSIBLE_ERROR(val)		((val) == ((typeof(val)) PCI_ERROR_RESPONSE))
```

The macro compares the value with all ones of its own type, and the comment notes that a read that succeeds can return all ones too. In [`dpc_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L386) the test sits beside the Interrupt Status test, so a DPC Status of all ones gets `IRQ_NONE` whatever its bits say. The swimlane follows the bits between the port and the two handlers.

```text
    How the hard handler answers an interrupt on the shared DPC vector
    ──────────────────────────────────────────────────────────────────

    time ↓
    port hardware           ╎ hard IRQ                      ╎ IRQ thread
    ────────────────────────┼───────────────────────────────┼──────────────────────
    Trigger Status 1,       ╎                               ╎
    Interrupt Status 1      ╎                               ╎
      MSI or MSI-X ────────▶╎ «1» DPC Status read           ╎
                            ╎ «2» Interrupt Status 0, or    ╎
                            ╎     all ones: IRQ_NONE, not   ╎
                            ╎     a DPC interrupt           ╎
    Interrupt Status 0 ◀───── «3» written 1 to clear it     ╎
                            ╎ «4» Trigger Status 1:         ╎
                            ╎     IRQ_WAKE_THREAD ────────▶ ╎ woken: logging and
                            ╎                               ╎ recovery start
                            ╎ «5» Trigger Status 0:         ╎
                            ╎     IRQ_HANDLED, no thread    ╎

    «1» dpc_irq  dpc.c:391  reads DPC Status through the cached capability offset
    «2» dpc_irq  :393  returns IRQ_NONE when Interrupt Status is clear or the read returned all ones
    «3» dpc_irq  :396  clears Interrupt Status by writing the bit back as 1
    «4» dpc_irq  :398  returns IRQ_WAKE_THREAD while Trigger Status is set
    «5» dpc_irq  :400  returns IRQ_HANDLED for an interrupt that carries no trigger
```

«1» [`dpc_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L391) reads DPC Status through the cached offset at [`dpc.c:391`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L391). «2» `dpc_irq()` returns `IRQ_NONE` at [`dpc.c:393-394`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L393) when Interrupt Status is clear or the read returned all ones. «3» `dpc_irq()` clears Interrupt Status by writing it as 1 at [`dpc.c:396-397`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L396). «4» `dpc_irq()` returns `IRQ_WAKE_THREAD` at [`dpc.c:398-399`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L398) while Trigger Status is set. «5» `dpc_irq()` returns `IRQ_HANDLED` at [`dpc.c:400`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L400) for an interrupt that carries no trigger.

The hard handler leaves Trigger Status set, so the port stays contained when the thread starts, and clearing it is left to the reset callback.

### The thread holds the port across logging and recovery

The thread runs the slow part of a containment event: it separates a surprise removal from an error, logs the reason, and runs error recovery, which sleeps for as long as the link and the devices below need. Since commit commit [a1ed752bc7cb](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=a1ed752bc7cb77b740cee671567d9508ae74becd) ("PCI/DPC: Hold pci_dev reference during error recovery"), merged for v7.1, it holds a reference on the port's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) for the logging and the recovery, and the commit's message gives the reason as matching the AER and EDR paths, which hold one already. The reader holds the port object, the thread's reference on it, and a recovery that calls back into DPC to reset the link.

[`dpc_handler()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L363) is the threaded handler the probe registered; read it for the surprise-removal exit before the reference and for the frozen channel state it passes to recovery.

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

A trigger that [`dpc_is_surprise_removal()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L349) attributes to a hot-removed device is cleaned up by [`dpc_handle_surprise_removal()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L328) and the thread returns without a reference, without logging and without recovery, which the comment grounds in PCIe r6.0 sec 6.7.6. Any other trigger is logged by [`dpc_process_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L264) and then recovered by [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) with [`pci_channel_io_frozen`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L213) as the channel state and [`dpc_reset_link()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L148) as the reset callback, between [`pci_dev_get()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L1565) and [`pci_dev_put()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L1580). The recovery function belongs to the error-recovery core; the stage below shows where a frozen channel makes it call the reset callback.

```c
/* drivers/pci/pcie/err.c:210 */
pci_ers_result_t pcie_do_recovery(struct pci_dev *dev,
		pci_channel_state_t state,
		pci_ers_result_t (*reset_subordinates)(struct pci_dev *pdev))
{
	... /* 14 lines, to :228 */
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
```

For a Root Port or a Switch Downstream Port, recovery runs on the port itself, `bridge` being the port, and on the devices below it, whose drivers hear of the frozen channel first through [`report_frozen_detected()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L101). Because the state is [`pci_channel_io_frozen`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L213), the reset callback runs whatever the drivers answered, and a result other than [`PCI_ERS_RESULT_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L934) ends recovery with "subordinate device reset failed". The reference the thread holds around these steps is taken and dropped by [`pci_dev_get()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L1565) and [`pci_dev_put()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L1580); read them for what they count.

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
```

Both accept NULL and count through the port's embedded driver-model device, and the comment above [`pci_dev_put()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L1580) states that the last put frees the object. The figure shows how the reference brackets the logging and the recovery.

```text
    What the thread holds while it handles one containment event
    ────────────────────────────────────────────────────────────

    time ───────────────────────────────────────────────────────────────────────────────────────────────────▶
                          «A»     «B»     «C»           «D»                                           «E»
                           ╎       ╎       ╎             ╎                                             ╎
    surprise test          ├─────┤ ╎       ╎             ╎                                             ╎
    reference held         ╎       ├───────────────────────────────────────────────────────────────────┤
    reason logged          ╎       ╎       ├────────────┤╎                                             ╎
    recovery runs          ╎       ╎       ╎             ├───────────────────────────────────────────┤ ╎
                           ╎       ╎       ╎             ╎                                             ╎
    port refcount        n           n + 1                                                               n

    a surprise removal is handled at «A» and returns before «B»; the reset callback runs inside «D»

    «A» dpc_handler  dpc.c:371  tests for a surprise removal before it takes anything
    «B» dpc_handler  :376  takes a reference on the port's struct pci_dev through pci_dev_get
    «C» dpc_handler  :377  logs the trigger reason while the reference is held
    «D» dpc_handler  :380  runs recovery for a frozen channel with dpc_reset_link as reset callback
    «E» dpc_handler  :382  drops the reference through pci_dev_put after recovery returns
```

«A» [`dpc_handler()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L371) tests for a surprise removal at [`dpc.c:371-374`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L371) before it takes anything. «B» `dpc_handler()` takes a reference on the port at [`dpc.c:376`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L376) through [`pci_dev_get()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L1565). «C» `dpc_handler()` logs the trigger reason at [`dpc.c:377`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L377) while the reference is held. «D» `dpc_handler()` runs recovery for a frozen channel at [`dpc.c:380`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L380), and the reset callback runs inside that span. «E» `dpc_handler()` drops the reference at [`dpc.c:382`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L382) through [`pci_dev_put()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L1580) after recovery returns.

With the reference held, the port object outlives a removal that recovery may trigger below it, and the thread's next step is the log line that names the cause.

### The Trigger Reason selects what the thread logs

A port can trigger for an error it detected itself, for an error message a device below it sent, or for a reason it reports in the extension field, and each cause keeps its detail in a different register. [`dpc_process_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L264) reads the Trigger Reason and logs from the register that reason points to, before recovery changes anything. The table pairs each reason with what the function reads and prints.

| Trigger Reason | Cause | What the function reads | What it prints |
|---|---|---|---|
| [`PCI_EXP_DPC_STATUS_TRIGGER_RSN_UNCOR`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1099) | an unmasked uncorrectable error the port detected | the port's AER Uncorrectable registers, through [`dpc_get_aer_uncorrect_severity()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L236) | a warning, then the port's AER record through [`aer_print_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L865) |
| [`PCI_EXP_DPC_STATUS_TRIGGER_RSN_NFE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1100) | an `ERR_NONFATAL` message the port received | DPC Source ID, [`PCI_EXP_DPC_SOURCE_ID`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1110) | a warning naming `ERR_NONFATAL` and the requester |
| [`PCI_EXP_DPC_STATUS_TRIGGER_RSN_FE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1101) | an `ERR_FATAL` message the port received | DPC Source ID, [`PCI_EXP_DPC_SOURCE_ID`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1110) | a warning naming `ERR_FATAL` and the requester |
| [`PCI_EXP_DPC_STATUS_TRIGGER_RSN_IN_EXT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1102) | a reason in the extension field | [`PCI_EXP_DPC_STATUS_TRIGGER_RSN_EXT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1105), then the RP PIO registers through [`dpc_process_rp_pio_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L190) | a warning naming RP PIO error, software trigger or reserved error, then the RP PIO detail |

The Source ID register follows DPC Status in the capability, at the offset `pci_regs.h` gives it.

```c
/* include/uapi/linux/pci_regs.h:1110 */
#define PCI_EXP_DPC_SOURCE_ID		 0x0A	/* DPC Source Identifier */
```

[`PCI_EXP_DPC_SOURCE_ID`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1110) is a 16-bit register at offset 0x0A that holds the Requester ID of the error message, which the code splits with [`PCI_BUS_NUM()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L74), [`PCI_SLOT()`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci.h#L32) and [`PCI_FUNC()`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci.h#L33). [`dpc_process_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L264) is 47 lines long at v7.2 and is read in three pieces, one per group of reasons.

| Piece | Lines | Stage |
|---|---|---|
| ❶ | dpc.c:264-283 | reads DPC Status, takes the reason and logs an uncorrectable trigger through AER |
| ❷ | dpc.c:284-294 | names the requester of a received `ERR_NONFATAL` or `ERR_FATAL` |
| ❸ | dpc.c:295-310 | names the extended reason and reads the RP PIO registers of a Root Port |

Piece ❶ of [`dpc_process_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L264) reads DPC Status into the local `status`, masks the reason with [`PCI_EXP_DPC_STATUS_TRIGGER_RSN`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1098), and handles the uncorrectable reason, with the AER record zeroed in the local `info`.

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

For [`PCI_EXP_DPC_STATUS_TRIGGER_RSN_UNCOR`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1099) the function warns with the raw DPC Status, and when [`dpc_get_aer_uncorrect_severity()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L236) finds an unmasked error and [`aer_get_device_error_info()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1293) reads it into the record, it prints the record with [`aer_print_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L865) and clears the port's non-fatal and fatal uncorrectable status. Piece ❷ of [`dpc_process_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L264) handles the two received-message reasons with one branch.

```c
/* drivers/pci/pcie/dpc.c:284 */
	case PCI_EXP_DPC_STATUS_TRIGGER_RSN_NFE:
	case PCI_EXP_DPC_STATUS_TRIGGER_RSN_FE:
		pci_read_config_word(pdev, cap + PCI_EXP_DPC_SOURCE_ID,
				     &source);
		pci_warn(pdev, "containment event, status:%#06x, %s received from %04x:%02x:%02x.%d\n",
			 status,
			 (reason == PCI_EXP_DPC_STATUS_TRIGGER_RSN_FE) ?
				"ERR_FATAL" : "ERR_NONFATAL",
			 pci_domain_nr(pdev->bus), PCI_BUS_NUM(source),
			 PCI_SLOT(source), PCI_FUNC(source));
		break;
```

For [`PCI_EXP_DPC_STATUS_TRIGGER_RSN_NFE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1100) and [`PCI_EXP_DPC_STATUS_TRIGGER_RSN_FE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1101) the function reads DPC Source ID into the local `source` and prints it as domain, bus, device and function, with the domain from [`pci_domain_nr()`](https://elixir.bootlin.com/linux/v7.2/source/arch/x86/include/asm/pci.h#L43) of the port's bus. No AER register is read in this branch. Piece ❸ of [`dpc_process_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L264) handles the extension reasons.

```c
/* drivers/pci/pcie/dpc.c:295 */
	case PCI_EXP_DPC_STATUS_TRIGGER_RSN_IN_EXT:
		ext_reason = status & PCI_EXP_DPC_STATUS_TRIGGER_RSN_EXT;
		pci_warn(pdev, "containment event, status:%#06x: %s detected\n",
			 status,
			 (ext_reason == PCI_EXP_DPC_STATUS_TRIGGER_RSN_RP_PIO) ?
			 "RP PIO error" :
			 (ext_reason == PCI_EXP_DPC_STATUS_TRIGGER_RSN_SW_TRIGGER) ?
			 "software trigger" :
			 "reserved error");
		/* show RP PIO error detail information */
		if (ext_reason == PCI_EXP_DPC_STATUS_TRIGGER_RSN_RP_PIO &&
		    pdev->dpc_rp_extensions)
			dpc_process_rp_pio_error(pdev);
		break;
	}
}
```

The local `ext_reason` takes [`PCI_EXP_DPC_STATUS_TRIGGER_RSN_EXT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1105) from the same status word, and the warning names an RP PIO error for [`PCI_EXP_DPC_STATUS_TRIGGER_RSN_RP_PIO`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1106), a software trigger for [`PCI_EXP_DPC_STATUS_TRIGGER_RSN_SW_TRIGGER`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1107), and a reserved error otherwise. The RP PIO registers are read only for an RP PIO reason on a port whose [`dpc_rp_extensions`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L538) is set. With [`CONFIG_PCIE_EDR`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L140) set, [`edr_handle_event()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/edr.c#L151) calls the same function and the same reset callback for a port that firmware contained and handed over through an ACPI notification; the option is unset here, and the stage shows the calls.

```c
/* drivers/pci/pcie/edr.c:151 */
static void edr_handle_event(acpi_handle handle, u32 event, void *data)
{
	struct pci_dev *pdev = data, *edev;
	... /* 32 lines, to :186 */
	/* Check if there is a valid DPC trigger */
	pci_read_config_word(edev, edev->dpc_cap + PCI_EXP_DPC_STATUS, &status);
	if (!(status & PCI_EXP_DPC_STATUS_TRIGGER)) {
		pci_err(edev, "Invalid DPC trigger %#010x\n", status);
		goto send_ost;
	}

	dpc_process_error(edev);
	pci_aer_raw_clear_status(edev);

	/*
	 * Irrespective of whether the DPC event is triggered by ERR_FATAL
	 * or ERR_NONFATAL, since the link is already down, use the FATAL
	 * error recovery path for both cases.
	 */
	estate = pcie_do_recovery(edev, pci_channel_io_frozen, dpc_reset_link);
```

The EDR handler checks Trigger Status itself, logs through [`dpc_process_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L264), clears the AER status with [`pci_aer_raw_clear_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L308) and runs [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) with [`dpc_reset_link()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L148), the same pair the DPC thread uses. The figure shows which register each reason feeds into the log.

```text
    What each Trigger Reason feeds into the log
    ───────────────────────────────────────────

                           ┌──────────────────────────────────────────┐
                           │ DPC Status, Trigger Reason (2:1)         │
                           └────┬─────────────┬─────────────────────┬─┘
                       _UNCOR   │     _NFE or │ _FE                 │ _IN_EXT
                                ▼             ▼                     ▼
    ┌───────────────────────────────┐ ┌───────────────────┐ ┌────────────────────────────┐
    │ port's AER Uncorrectable      │ │ DPC Source ID     │ │ DPC Status, Trigger Reason │
    │ Status, Mask and Severity     │ │ bus, device, fn   │ │ Extension (6:5)            │
    └───────────────┬───────────────┘ └─────────┬─────────┘ └──────┬──────────────┬──────┘
                    ▼                           ▼        _RP_PIO,  │              │ _SW_TRIGGER
    ┌───────────────────────────────┐ ┌───────────────────┐ RP ext ▼              ▼ or other
    │ one-device AER record of the  │ │ requester named   │ ┌───────────────┐ ┌──────────────┐
    │ port, printed and cleared     │ │ in the warning    │ │ RP PIO        │ │ the warning  │
    └───────────────────────────────┘ └───────────────────┘ │ registers and │ │ names it,    │
                                                            │ logs printed  │ │ nothing more │
                                                            └───────────────┘ └──────────────┘

    each branch first prints a "containment event" warning with the raw DPC Status
```

Trigger Status is still set when [`dpc_process_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L264) returns, and the writes on its branches are the AER status clears of the uncorrectable branch and the RP PIO Status clear that the next subsections show.

### Uncorrectable triggers are logged through AER past its ratelimit

An uncorrectable error the port detected itself has its detail in the port's own AER registers, so the DPC thread borrows the AER printer, which expects a record of the devices involved and their error words. [`dpc_get_aer_uncorrect_severity()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L236) builds that record for one device, the port, and since commit commit [97970e7c6943](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=97970e7c694356e3386a10e3b936d61eafd06bce) ("PCI/DPC: Log AER error info for DPC/EDR uncorrectable errors"), merged for v7.1, it marks the record to print past the AER ratelimit. The reader holds a record, [`struct aer_err_info`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L833), that DPC fills partly and the AER helpers complete and print.

[`struct aer_err_info`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L833) is the record the AER printer reads, defined in drivers/pci/pci.h; read it for the members DPC writes and the ones the AER helpers fill.

```c
/* drivers/pci/pci.h:833 */
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

[`dev`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L834) lists the devices of the record and [`ratelimit_print`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L835) holds a print decision per device, and [`error_dev_num`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L836) counts the devices filled. [`level`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L837) is the printk level and [`severity`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L841) one of [`AER_NONFATAL`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L14), [`AER_FATAL`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L15) or the correctable value. [`first_error`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L846), [`tlp_header_valid`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L849), the bus-type bit beside it, [`status`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L851), [`mask`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L852) and [`tlp`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L853) are filled by [`aer_get_device_error_info()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1293) from the device. [`id`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L839), [`root_ratelimit_print`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L842) and [`multi_error_valid`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L844) belong to the Root Port's own AER message and stay 0 in the record DPC builds, and the pad bits fill the bit-field words. [`dpc_get_aer_uncorrect_severity()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L236) fills the first five; read it for the masking that decides the severity.

```c
/* drivers/pci/pcie/dpc.c:236 */
static int dpc_get_aer_uncorrect_severity(struct pci_dev *dev,
					  struct aer_err_info *info)
{
	int pos = dev->aer_cap;
	u32 status, mask, sev;

	pci_read_config_dword(dev, pos + PCI_ERR_UNCOR_STATUS, &status);
	pci_read_config_dword(dev, pos + PCI_ERR_UNCOR_MASK, &mask);
	status &= ~mask;
	if (!status)
		return 0;

	pci_read_config_dword(dev, pos + PCI_ERR_UNCOR_SEVER, &sev);
	status &= sev;
	if (status)
		info->severity = AER_FATAL;
	else
		info->severity = AER_NONFATAL;

	info->level = KERN_ERR;

	info->dev[0] = dev;
	info->error_dev_num = 1;
	info->ratelimit_print[0] = 1;

	return 1;
}
```

The function reads Uncorrectable Error Status, Mask and Severity of the port through [`aer_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370) in the local `pos`, and returns 0 without a record when no unmasked bit is set. An unmasked bit that Severity marks fatal makes the record [`AER_FATAL`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L15), and otherwise it is [`AER_NONFATAL`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L14). The level is `KERN_ERR`, the port is the record's single device, and [`ratelimit_print`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L835) of that device is 1. [`aer_get_device_error_info()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1293) then reads the device's words into the record; the stage shows the uncorrectable branch a Root Port or a Downstream Port takes.

```c
/* drivers/pci/pcie/aer.c:1293 */
int aer_get_device_error_info(struct aer_err_info *info, int i)
{
	struct pci_dev *dev;
	int type, aer;
	u32 aercc;

	if (i >= AER_MAX_MULTI_ERR_DEVICES)
		return 0;

	dev = info->dev[i];
	... /* 19 lines, to :1322 */
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

For a port the branch reads Uncorrectable Error Status and Mask into the record, returns 0 when no unmasked bit is set, and otherwise records the First Error Pointer and, when the header was logged, the TLP header log, returning 1. [`aer_print_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L865) then prints the record, and the stage shows the test that the record's [`ratelimit_print`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L835) decides.

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
```

The counters and the [`aer_event`](https://elixir.bootlin.com/linux/v7.2/source/include/ras/ras_event.h#L337) tracepoint are updated before the test, so they record a DPC event whatever the ratelimit says. The test at [`aer.c:882-883`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L882) returns before any line prints when the device's [`ratelimit_print`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L835) is 0, which the native AER path sets through its ratelimit and which the DPC record before v7.1 left at 0, the commit message reports. With the flag set to 1, a DPC record reaches the printing lines whatever the ratelimit state. After printing, [`dpc_process_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L264) clears the logged uncorrectable bits with two AER helpers; read them for the severity split.

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
EXPORT_SYMBOL_GPL(pci_aer_clear_nonfatal_status);

void pci_aer_clear_fatal_status(struct pci_dev *dev)
{
	int aer = dev->aer_cap;
	u32 status, sev;

	if (!pcie_aer_is_native(dev))
		return;

	/* Clear status bits for ERR_FATAL errors only */
	pci_read_config_dword(dev, aer + PCI_ERR_UNCOR_STATUS, &status);
	pci_read_config_dword(dev, aer + PCI_ERR_UNCOR_SEVER, &sev);
	status &= sev;
	if (status)
		pci_write_config_dword(dev, aer + PCI_ERR_UNCOR_STATUS, status);
}
```

[`pci_aer_clear_nonfatal_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L264) writes back the logged bits whose Severity bit is 0 and [`pci_aer_clear_fatal_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L283) the ones whose Severity bit is 1, so together they clear the logged uncorrectable bits, both only when [`pcie_aer_is_native()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L242) answers true. The figure shows how the three registers feed the record.

```text
    The port's AER registers feed the one-device record DPC hands to the AER printer
    ────────────────────────────────────────────────────────────────────────────────

    Uncorrectable Status    Uncorrectable Mask      Uncorrectable Severity
    aer_cap + 0x04          aer_cap + 0x08          aer_cap + 0x0c
    ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
    │ status           │    │ mask             │    │ sev              │
    └────────┬─────────┘    └────────┬─────────┘    └────────┬─────────┘
             └──────────┬────────────┘                       │
                        ▼ @1 status & ~mask                  │
                        │ none left: return 0, no record     │
                        │                                    │
                        ▼ @2 & sev ◀─────────────────────────┘
                        │ nonzero: fatal, zero: non-fatal
                        │
                        ▼ populates
    ┌────────────────────────────────────────────────────────────────┐
    │ struct aer_err_info info, zeroed by the caller                 │
    │   severity             @3 AER_FATAL, or AER_NONFATAL           │
    │   level                @4 KERN_ERR                             │
    │   dev[0]               @5 the DPC port itself                  │
    │   error_dev_num        1                                       │
    │   ratelimit_print[0]   @6 1: the record prints past the limit  │
    └────────────────────────────────────────────────────────────────┘

    @1 dpc_get_aer_uncorrect_severity  dpc.c:244  drops the masked bits and returns 0 when none is left
    @2 dpc_get_aer_uncorrect_severity  :249  keeps the unmasked bits that Severity marks fatal
    @3 dpc_get_aer_uncorrect_severity  :251  sets AER_FATAL when a fatal bit is left, AER_NONFATAL at :253
    @4 dpc_get_aer_uncorrect_severity  :255  sets the printk level of the record to KERN_ERR
    @5 dpc_get_aer_uncorrect_severity  :257  makes the DPC port the record's only device
    @6 dpc_get_aer_uncorrect_severity  :259  sets ratelimit_print[0] so aer_print_error prints it
```

@1 [`dpc_get_aer_uncorrect_severity()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L244) drops the masked bits at [`dpc.c:244-246`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L244) and returns 0 when none is left. @2 `dpc_get_aer_uncorrect_severity()` keeps the unmasked bits Severity marks fatal at [`dpc.c:249`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L249). @3 `dpc_get_aer_uncorrect_severity()` sets [`AER_FATAL`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L15) at [`dpc.c:251`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L251) when a fatal bit is left, and [`AER_NONFATAL`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L14) at [`dpc.c:253`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L253) otherwise. @4 `dpc_get_aer_uncorrect_severity()` sets the level to `KERN_ERR` at [`dpc.c:255`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L255). @5 `dpc_get_aer_uncorrect_severity()` makes the port the record's single device at [`dpc.c:257`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L257). @6 `dpc_get_aer_uncorrect_severity()` sets [`ratelimit_print`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L835) of that device at [`dpc.c:259`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L259), which lets [`aer_print_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L865) print the record.

An uncorrectable trigger therefore leaves an AER record in the log at `KERN_ERR`, a count and a trace event, with the port's uncorrectable status cleared and Trigger Status still set.

### Root Port PIO errors are read from the extension registers

A Root Port with the extensions can trigger for a PIO error, a completion error of a request the Root Port itself sent, and its RP PIO registers say which kind of request failed and hold the logged TLP. [`dpc_process_rp_pio_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L190) prints those registers, names each unmasked error bit, prints the logged TLP when the port's log size allows it, and clears the status. The reader holds a block of RP PIO registers above DPC Source ID, a table of names indexed by bit, and the log size enumeration stored in [`dpc_rp_log_size`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L539).

`pci_regs.h` gives the RP PIO registers fixed offsets in the capability; read the block for the offsets the function adds to [`dpc_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L537).

```c
/* include/uapi/linux/pci_regs.h:1112 */
#define PCI_EXP_DPC_RP_PIO_STATUS	 0x0C	/* RP PIO Status */
#define PCI_EXP_DPC_RP_PIO_MASK		 0x10	/* RP PIO Mask */
#define PCI_EXP_DPC_RP_PIO_SEVERITY	 0x14	/* RP PIO Severity */
#define PCI_EXP_DPC_RP_PIO_SYSERROR	 0x18	/* RP PIO SysError */
#define PCI_EXP_DPC_RP_PIO_EXCEPTION	 0x1C	/* RP PIO Exception */
#define PCI_EXP_DPC_RP_PIO_HEADER_LOG	 0x20	/* RP PIO Header Log */
#define PCI_EXP_DPC_RP_PIO_IMPSPEC_LOG	 0x30	/* RP PIO ImpSpec Log */
#define PCI_EXP_DPC_RP_PIO_TLPPREFIX_LOG 0x34	/* RP PIO TLP Prefix Log */
```

[`PCI_EXP_DPC_RP_PIO_STATUS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1112), [`PCI_EXP_DPC_RP_PIO_MASK`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1113) and [`PCI_EXP_DPC_RP_PIO_SEVERITY`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1114) hold the error bits, their mask and their severity, and [`PCI_EXP_DPC_RP_PIO_SYSERROR`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1115) and [`PCI_EXP_DPC_RP_PIO_EXCEPTION`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1116) hold two more bit words the function prints raw. [`PCI_EXP_DPC_RP_PIO_HEADER_LOG`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1117), [`PCI_EXP_DPC_RP_PIO_IMPSPEC_LOG`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1118) and [`PCI_EXP_DPC_RP_PIO_TLPPREFIX_LOG`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1119) start the header log, the implementation-specific dword and the prefix log. The names of the error bits come from [`rp_pio_error_string`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L24), an array indexed by bit position; read it for the positions that have a name.

```c
/* drivers/pci/pcie/dpc.c:24 */
static const char * const rp_pio_error_string[] = {
	"Configuration Request received UR Completion",	 /* Bit Position 0  */
	"Configuration Request received CA Completion",	 /* Bit Position 1  */
	"Configuration Request Completion Timeout",	 /* Bit Position 2  */
	NULL,
	NULL,
	NULL,
	NULL,
	NULL,
	"I/O Request received UR Completion",		 /* Bit Position 8  */
	"I/O Request received CA Completion",		 /* Bit Position 9  */
	"I/O Request Completion Timeout",		 /* Bit Position 10 */
	NULL,
	NULL,
	NULL,
	NULL,
	NULL,
	"Memory Request received UR Completion",	 /* Bit Position 16 */
	"Memory Request received CA Completion",	 /* Bit Position 17 */
	"Memory Request Completion Timeout",		 /* Bit Position 18 */
};
```

Bits 0 to 2 name the completion errors of Configuration Requests, bits 8 to 10 of I/O Requests and bits 16 to 18 of Memory Requests, each an Unsupported Request completion, a Completer Abort completion or a Completion Timeout, and the entries between the groups are NULL. The array has 19 entries, so bits 19 to 31 have no name. [`dpc_process_rp_pio_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L190) is 45 lines long at v7.2 and is read in three pieces.

| Piece | Lines | Stage |
|---|---|---|
| Ⓐ | dpc.c:190-206 | prints the status, mask and the three other bit words |
| Ⓑ | dpc.c:207-216 | names each unmasked error bit and marks the first one |
| Ⓒ | dpc.c:217-234 | prints the logged TLP and ImpSpec dword the log size allows, then clears the status |

Piece Ⓐ of [`dpc_process_rp_pio_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L190) reads the RP PIO words into locals and prints them as two [`pci_err()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2891) lines.

```c
/* drivers/pci/pcie/dpc.c:190 */
static void dpc_process_rp_pio_error(struct pci_dev *pdev)
{
	u16 cap = pdev->dpc_cap, dpc_status, first_error;
	u32 status, mask, sev, syserr, exc, log;
	struct pcie_tlp_log tlp_log;
	int i;

	pci_read_config_dword(pdev, cap + PCI_EXP_DPC_RP_PIO_STATUS, &status);
	pci_read_config_dword(pdev, cap + PCI_EXP_DPC_RP_PIO_MASK, &mask);
	pci_err(pdev, "rp_pio_status: %#010x, rp_pio_mask: %#010x\n",
		status, mask);

	pci_read_config_dword(pdev, cap + PCI_EXP_DPC_RP_PIO_SEVERITY, &sev);
	pci_read_config_dword(pdev, cap + PCI_EXP_DPC_RP_PIO_SYSERROR, &syserr);
	pci_read_config_dword(pdev, cap + PCI_EXP_DPC_RP_PIO_EXCEPTION, &exc);
	pci_err(pdev, "RP PIO severity=%#010x, syserror=%#010x, exception=%#010x\n",
		sev, syserr, exc);
```

The locals `status` and `mask` keep RP PIO Status and Mask for the next piece, and `sev`, `syserr` and `exc` are printed and not used again. Piece Ⓑ of [`dpc_process_rp_pio_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L190) reads the First Error Pointer from DPC Status and loops over the names.

```c
/* drivers/pci/pcie/dpc.c:207 */

	/* Get First Error Pointer */
	pci_read_config_word(pdev, cap + PCI_EXP_DPC_STATUS, &dpc_status);
	first_error = FIELD_GET(PCI_EXP_DPC_RP_PIO_FEP, dpc_status);

	for (i = 0; i < ARRAY_SIZE(rp_pio_error_string); i++) {
		if ((status & ~mask) & (1 << i))
			pci_err(pdev, "[%2d] %s%s\n", i, rp_pio_error_string[i],
				first_error == i ? " (First)" : "");
	}
```

The loop prints the index and the name of each bit set in `status & ~mask`, for indexes below the 19 entries of [`rp_pio_error_string`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L24), and appends " (First)" to the bit [`PCI_EXP_DPC_RP_PIO_FEP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1108) points at. Piece Ⓒ of [`dpc_process_rp_pio_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L190) reads the logs as far as [`dpc_rp_log_size`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L539) says they exist.

```c
/* drivers/pci/pcie/dpc.c:217 */

	if (pdev->dpc_rp_log_size < PCIE_STD_NUM_TLP_HEADERLOG)
		goto clear_status;
	pcie_read_tlp_log(pdev, cap + PCI_EXP_DPC_RP_PIO_HEADER_LOG,
			  cap + PCI_EXP_DPC_RP_PIO_TLPPREFIX_LOG,
			  dpc_tlp_log_len(pdev),
			  pdev->subordinate->flit_mode,
			  &tlp_log);
	pcie_print_tlp_log(pdev, &tlp_log, KERN_ERR, dev_fmt(""));

	if (pdev->dpc_rp_log_size < PCIE_STD_NUM_TLP_HEADERLOG + 1)
		goto clear_status;
	pci_read_config_dword(pdev, cap + PCI_EXP_DPC_RP_PIO_IMPSPEC_LOG, &log);
	pci_err(pdev, "RP PIO ImpSpec Log %#010x\n", log);

 clear_status:
	pci_write_config_dword(pdev, cap + PCI_EXP_DPC_RP_PIO_STATUS, status);
}
```

A log size below [`PCIE_STD_NUM_TLP_HEADERLOG`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L23), which after [`pci_dpc_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L403) means 0, skips both logs. A larger size reads the TLP log with [`pcie_read_tlp_log()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L63) over a length [`dpc_tlp_log_len()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L40) computes, in Flit Mode when the port's secondary bus records [`flit_mode`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L734), and prints it with [`pcie_print_tlp_log()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L106) at `KERN_ERR`; a size of 5 or more also reads and prints the ImpSpec dword. Each path through the piece ends at the `clear_status` label, which writes the status value read in piece Ⓐ back to RP PIO Status and so clears the bits it reported. The length comes from [`dpc_tlp_log_len()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L40) in tlp.c; read it for the dword it removes.

```c
/* drivers/pci/pcie/tlp.c:34 */
/**
 * dpc_tlp_log_len - Calculate DPC RP PIO TLP Header/Prefix Log length
 * @dev: PCIe device
 *
 * Return: TLP Header/Prefix Log length
 */
unsigned int dpc_tlp_log_len(struct pci_dev *dev)
{
	/* Remove ImpSpec Log register from the count */
	if (dev->dpc_rp_log_size >= PCIE_STD_NUM_TLP_HEADERLOG + 1)
		return dev->dpc_rp_log_size - 1;

	return dev->dpc_rp_log_size;
}
```

The ImpSpec dword counts in [`dpc_rp_log_size`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L539) but stands outside the TLP log, so the function subtracts it from a size of 5 or more. [`pcie_read_tlp_log()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L63) then places the dwords; read it for where it finds the ones past the header log.

```c
/* drivers/pci/pcie/tlp.c:63 */
int pcie_read_tlp_log(struct pci_dev *dev, int where, int where2,
		      unsigned int tlp_len, bool flit, struct pcie_tlp_log *log)
{
	unsigned int i;
	int off, ret;

	if (tlp_len > ARRAY_SIZE(log->dw))
		tlp_len = ARRAY_SIZE(log->dw);

	memset(log, 0, sizeof(*log));

	for (i = 0; i < tlp_len; i++) {
		if (i < PCIE_STD_NUM_TLP_HEADERLOG)
			off = where + i * 4;
		else
			off = where2 + (i - PCIE_STD_NUM_TLP_HEADERLOG) * 4;

		ret = pci_read_config_dword(dev, off, &log->dw[i]);
		if (ret)
			return pcibios_err_to_errno(ret);
	}

	/*
	 * Hard-code non-Flit mode to 4 DWORDs, for now. The exact length
	 * can only be known if the TLP is parsed.
	 */
	log->header_len = flit ? tlp_len : 4;
	log->flit = flit;

	return 0;
}
```

The first [`PCIE_STD_NUM_TLP_HEADERLOG`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L23) dwords come from the header log at the parameter `where` and the rest from the prefix log at the parameter `where2`, which for DPC are [`PCI_EXP_DPC_RP_PIO_HEADER_LOG`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1117) and [`PCI_EXP_DPC_RP_PIO_TLPPREFIX_LOG`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1119), skipping the ImpSpec dword between them. The first figure pairs the status bits with the names, and the second places the log sizes on one scale.

```text
    One index i selects both a bit of RP PIO Status and an entry of rp_pio_error_string[]
    ──────────────────────────────────────────────────────────────────────────────────────

                ┌───┬───┬───┬──────┬───┬───┬────┬────────┬────┬────┬────┐  ┌─────────┐
    status      │ UR│ CA│CTO│  ·   │ UR│ CA│CTO │   ·    │ UR │ CA │CTO │  │ 19..31  │
    bit i       │ 0 │ 1 │ 2 │ 3..7 │ 8 │ 9 │ 10 │ 11..15 │ 16 │ 17 │ 18 │  │    ·    │
                └───┴───┴───┴──────┴───┴───┴────┴────────┴────┴────┴────┘  └─────────┘
                ┌───┬───┬───┬──────┬───┬───┬────┬────────┬────┬────┬────┐
    string[i]   │ s │ s │ s │ NULL │ s │ s │ s  │  NULL  │ s  │ s  │ s  │  no entry, never
                └───┴───┴───┴──────┴───┴───┴────┴────────┴────┴────┴────┘  printed
                 Configuration      I/O Request           Memory Request

    s = a string naming the completion error: UR Completion, CA Completion or Completion Timeout
    the loop takes i from 0 to ARRAY_SIZE(rp_pio_error_string) - 1, which is 18, and prints entry i
    when bit i of status & ~mask is set, adding " (First)" when i equals the First Error Pointer
```

The names cover 9 of the 32 bits at v7.2; a set bit at a NULL entry is printed without a name, a set bit from 19 up is not printed, and the final write clears both. Where the log size lands decides which of the logs the piece reads, as the scale shows.

```text
    Where dpc_rp_log_size can land, and what the RP PIO path reads at each size
    ────────────────────────────────────────────────────────────────────────────

    dwords    0    1    2    3    4    5    6    7    8    9    10   11   12   13   14   15   16   ... 31
              ├────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼──────▶
              ├──────────────┤    ├──────────────────────────────────────────────────────┤    ├──────────┤
              stored as 0         kept by pci_dpc_init()                                      stored as 0
              after the error                                                                 after the error

                                  │    │
                                  │    └─ 5 and up: ImpSpec Log read; the TLP log is size − 1 dwords
                                  └─ 4 and up: Header Log read; at 4 the TLP log is 4 dwords

    4 = PCIE_STD_NUM_TLP_HEADERLOG; 15 = PCIE_STD_MAX_TLP_HEADERLOG + 1; sizes from 16 come from bit 4,
    which pci_dpc_init() adds on a port with Flit Mode; dpc_tlp_log_len() subtracts the ImpSpec dword
```

So far, a trigger has been taken by the hard handler, passed to the thread, and logged by its reason, through the AER record or the RP PIO registers or a single warning line. The port is still contained, with Trigger Status set, when the thread calls recovery.

### Recovery calls the reset callback, which releases the port

The port leaves containment when software clears Trigger Status, and the DPC driver does that from the reset callback recovery calls, after the drivers below have been told that their channel is frozen. The callback must not release the port while the link is still up from before the trigger or while a Root Port is still busy, and it must report whether the devices below came back, which decides whether recovery succeeds. Two bits of the port's [`priv_flags`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L585) tell the hotplug driver that a recovery is running and how it ended.

Recovery passes the port to the callback in the lines of [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) shown below again, where a frozen channel always takes the reset branch.

```c
/* drivers/pci/pcie/err.c:210 */
pci_ers_result_t pcie_do_recovery(struct pci_dev *dev,
		pci_channel_state_t state,
		pci_ers_result_t (*reset_subordinates)(struct pci_dev *pdev))
{
	... /* 36 lines, to :250 */
	if (status == PCI_ERS_RESULT_NEED_RESET ||
	    state == pci_channel_io_frozen) {
		if (reset_subordinates(bridge) != PCI_ERS_RESULT_RECOVERED) {
			pci_warn(bridge, "subordinate device reset failed\n");
			goto failed;
		}
	}
```

The parameter `reset_subordinates` is [`dpc_reset_link()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L148) here and `bridge` is the port, and a result other than [`PCI_ERS_RESULT_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L934) fails the recovery. The bits the callback writes are defined among the private flags of drivers/pci/pci.h.

```c
/* drivers/pci/pci.h:767 */
/* pci_dev priv_flags */
#define PCI_DEV_ADDED 0
#define PCI_DPC_RECOVERED 1
#define PCI_DPC_RECOVERING 2
#define PCI_DEV_REMOVED 3
#define PCI_LINK_CHANGED 4
#define PCI_LINK_CHANGING 5
#define PCI_LINK_LBMS_SEEN	6
#define PCI_DEV_ALLOW_BINDING 7
```

[`PCI_DPC_RECOVERING`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L770) says a reset callback is running on the port, and [`PCI_DPC_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L769) says the last DPC recovery of the port succeeded; both are bit numbers in [`priv_flags`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L585), which other mechanisms share, and the callback changes them with atomic bit operations. [`dpc_reset_link()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L148) is 41 lines long at v7.2 and is read in two pieces.

| Piece | Lines | Stage |
|---|---|---|
| ⓐ | dpc.c:148-172 | marks the recovery, waits for the link to go down and for the Root Port to go idle |
| ⓑ | dpc.c:173-188 | clears Trigger Status, waits for the secondary bus and reports the result |

Piece ⓐ of [`dpc_reset_link()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L148) sets [`PCI_DPC_RECOVERING`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L770) and waits before it touches DPC Status.

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
```

The comment states that the hardware has disabled the link already, so the callback starts by waiting for the Data Link Layer Link Active bit to clear through [`pcie_wait_for_link()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4678) with `false`, and a timeout only prints "Data Link Layer Link Active not cleared in 1000 msec". On a port with the extensions it then waits for Root Port Busy through [`dpc_wait_rp_inactive()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L130), and a port still busy ends the callback with [`PCI_ERS_RESULT_DISCONNECT`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L931), [`PCI_DPC_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L769) cleared and Trigger Status left set. Piece ⓑ of [`dpc_reset_link()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L148) releases the port and decides the result.

```c
/* drivers/pci/pcie/dpc.c:173 */

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

Writing [`PCI_EXP_DPC_STATUS_TRIGGER`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1097) as 1 clears Trigger Status, which the comment in piece ⓐ calls allowing the port to leave DPC. [`pci_bridge_wait_for_secondary_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4724) with the reset type "DPC" then waits for the first device below to answer, and its result sets [`PCI_DPC_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L769) with [`PCI_ERS_RESULT_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L934) or clears it with [`PCI_ERS_RESULT_DISCONNECT`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L931). Every exit clears [`PCI_DPC_RECOVERING`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L770) at the `out` label and wakes every sleeper on [`dpc_completed_waitqueue`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L78). The strip follows the two bits through a run and through the paths that read them later.

```text
    The DPC bits of one port's priv_flags through a containment event and its readers
    ──────────────────────────────────────────────────────────────────────────────────
    fields: the PCI_DPC_RECOVERING and PCI_DPC_RECOVERED bits of priv_flags in struct pci_dev

    time ─────────────────────────────────────────────────────────────────────────────────────────────────────────▶
    event                   callback   Root Port  trigger    bus        callback   surprise     pciehp
                            entered    busy test  cleared    waited     returns    removal      reads
                            ▼          ▼          ▼          ▼          ▼          ▼            ▼
                            ┌───────────────────────────────────────────┬──────────────────────────────────────────
    RECOVERING              │ @A 1, set on entry                        │ @E 0, on every exit
                            └───────────────────────────────────────────┴──────────────────────────────────────────
                            ┌────────────────────────────────┬──────────────────────────────────┬──────────────────
    RECOVERED, bus ready    │ as an earlier event left it    │ @D 1                             │ @G 0
                            └────────────────────────────────┴──────────────────────────────────┴──────────────────
                            ┌──────────┬───────────────────────────────────────────────────────────────────────────
    RECOVERED, RP busy      │ as left  │ @B 0, the callback gives up
                            └──────────┴───────────────────────────────────────────────────────────────────────────
                            ┌────────────────────────────────┬─────────────────────────────────────────────────────
    RECOVERED, bus fails    │ as left                        │ @C 0
                            └────────────────────────────────┴─────────────────────────────────────────────────────
                            ┌──────────────────────────────────────────────────────┬───────────────────────────────
    RECOVERED, surprise     │ as left                                              │ @F 0
                            └──────────────────────────────────────────────────────┴───────────────────────────────

    the RP busy row needs the Root Port extensions; the surprise row is the thread's other path

    @A dpc_reset_link  dpc.c:153  sets PCI_DPC_RECOVERING through set_bit on entry
    @B dpc_reset_link  :169  clears PCI_DPC_RECOVERED through clear_bit when the Root Port stays busy
    @C dpc_reset_link  :178  clears PCI_DPC_RECOVERED when the secondary bus does not come back
    @D dpc_reset_link  :181  sets PCI_DPC_RECOVERED once the secondary bus is ready
    @E dpc_reset_link  :185  clears PCI_DPC_RECOVERING on every exit, before the waiters wake
    @F dpc_handle_surprise_removal  :345  clears PCI_DPC_RECOVERED after the surprise-removal cleanup
    @G pci_dpc_recovered  :126  returns PCI_DPC_RECOVERED and clears it through test_and_clear_bit
```

@A [`dpc_reset_link()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L153) sets [`PCI_DPC_RECOVERING`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L770) at [`dpc.c:153`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L153) on entry. @B `dpc_reset_link()` clears [`PCI_DPC_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L769) at [`dpc.c:169`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L169) when the Root Port stays busy. @C `dpc_reset_link()` clears it at [`dpc.c:178`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L178) when the secondary bus does not come back. @D `dpc_reset_link()` sets it at [`dpc.c:181`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L181) once the secondary bus is ready. @E `dpc_reset_link()` clears [`PCI_DPC_RECOVERING`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L770) at [`dpc.c:185`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L185) on every exit, before it wakes the waiters. @F [`dpc_handle_surprise_removal()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L328) clears [`PCI_DPC_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L769) at [`dpc.c:345`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L345) after the cleanup of a surprise removal. @G [`pci_dpc_recovered()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L103) returns [`PCI_DPC_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L769) and clears it at [`dpc.c:126`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L126). The tree has no other writer of the two bits at v7.2, and the other bits of [`priv_flags`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L585) belong to other mechanisms and are not drawn.

From the write of Trigger Status at [`dpc.c:174-175`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L174) until @E, the port has left containment while [`PCI_DPC_RECOVERING`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L770) is still set, and in that interval [`dpc_completed()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L81) keeps a waiter asleep until the result is recorded.

### Bounded waits decide how long the port stays contained

The reset callback waits three times, for the link to go down, for the Root Port to go idle and for the devices below to answer, and each wait has a bound so that a broken port cannot hold recovery forever. These bounds decide how long the port stays contained and how long the drivers below see a frozen channel. The reader holds three intervals on one time axis, the first two before Trigger Status is cleared and the third after.

[`dpc_wait_rp_inactive()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L130) is the DPC driver's own wait; read it for its bound and its polling interval.

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

The local `timeout` is one second, `jiffies + HZ`, and the loop reads DPC Status every 10 ms while [`PCI_EXP_DPC_RP_BUSY`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1104) is set. A port still busy after the bound prints "root port still busy" and returns -EBUSY, which makes both callers give up without clearing Trigger Status. The wait for the link to go down is the PCI core's [`pcie_wait_for_link()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4678), which adds a 100 ms settle delay to its inner wait.

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

The DPC callers pass `active` as false, and the delay only applies after a link comes up, as [`pcie_wait_for_link_delay()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4629) shows in the lines below, where the comment block between them is folded.

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

A port without Data Link Layer Link Active reporting, [`link_active_reporting`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L507) clear, sleeps 1000 ms plus the delay and reports success. Otherwise the inactive wait is [`pcie_wait_for_link_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4535) on the Data Link Layer Link Active bit, whose bound is [`PCIE_LINK_RETRAIN_TIMEOUT_MS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L22).

```c
/* drivers/pci/pci.c:4535 */
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

The loop reads Link Status every millisecond until the bit matches or [`PCIE_LINK_RETRAIN_TIMEOUT_MS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L22) has passed, the 1000 ms that the message in [`dpc_reset_link()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L148) names.

```c
/* drivers/pci/pci.h:22 */
#define PCIE_LINK_RETRAIN_TIMEOUT_MS	1000
```

The third wait follows the release of the port and belongs to [`pci_bridge_wait_for_secondary_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4724); the stage shows its first early returns, the test that separates ports of 5 GT/s or less, and the lines a faster port runs.

```c
/* drivers/pci/pci.c:4724 */
int pci_bridge_wait_for_secondary_bus(struct pci_dev *dev, char *reset_type)
{
	struct pci_dev *child __free(pci_dev_put) = NULL;
	int delay;

	if (pci_dev_is_disconnected(dev))
		return 0;

	if (!pci_is_bridge(dev))
		return 0;
	... /* 50 lines, to :4784 */
	if (!pcie_downstream_port(dev))
		return 0;

	if (pcie_get_speed_cap(dev) <= PCIE_SPEED_5_0GT) {
		u16 status;

		pci_dbg(dev, "waiting %d ms for downstream link\n", delay);
		msleep(delay);
	... /* 20 lines, to :4812 */
	pci_dbg(dev, "waiting %d ms for downstream link, after activation\n",
		delay);
	if (!pcie_wait_for_link_delay(dev, true, delay)) {
		/* Did not train, no need to wait any further */
		pci_info(dev, "Data Link Layer Link Active not set in %d msec\n", delay);
		return -ENOTTY;
	}

	return pci_dev_wait(child, reset_type,
			    PCIE_RESET_READY_POLL_MS - delay);
}
```

The wait returns 0 at once for a disconnected port or a function that is not a bridge. A port of 5 GT/s or less sleeps the delay and continues in the folded lines, and a faster port waits for the link to come up again, giving up with "Data Link Layer Link Active not set in %d msec" and -ENOTTY, and then polls the first device below with [`pci_dev_wait()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L1195) for up to [`PCIE_RESET_READY_POLL_MS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L82) less the delay. The two readiness constants are defined in pci.c with the comments that ground them.

```c
/* drivers/pci/pci.c:70 */
 * Following exit from Conventional Reset, devices must be ready within 1 sec
 * (PCIe r6.0 sec 6.6.1).  A D3cold to D0 transition implies a Conventional
 * Reset (PCIe r6.0 sec 5.8).
 */
#define PCI_RESET_WAIT 1000 /* msec */

/*
 * Devices may extend the 1 sec period through Request Retry Status
 * completions (PCIe r6.0 sec 2.3.1).  The spec does not provide an upper
 * limit, but 60 sec ought to be enough for any device to become
 * responsive.
 */
#define PCIE_RESET_READY_POLL_MS 60000 /* msec */
```

[`PCI_RESET_WAIT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L74) is 1000 ms and [`PCIE_RESET_READY_POLL_MS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L82) is 60000 ms, so on a faster port the third wait can keep the drivers below waiting for up to 60000 ms less the delay, after the link wait, while the port itself is already released. The figure places the three waits on one axis.

```text
    How long the reset callback can keep the port contained, wait by wait
    ─────────────────────────────────────────────────────────────────────

    time ─────────────────────────────────────────────────────────────────────────────────────────────────────▶
              callback              link down               port idle       trigger 0           bus answers
                  ╎                     ╎                       ╎               ╎                         ╎
    contained     ├─────────────────────────────────────────────────────────────┤                         ╎
    link wait     ├─────────────────────┤                       ╎               ╎                         ╎
    busy wait     ╎                     ├───────────────────────┤               ╎                         ╎
    bus wait      ╎                     ╎                       ╎               ├─────────────────────────┤
                  ╎                     ╎                       ╎               ╎                         ╎

    link wait: Data Link Layer Link Active polled every 1 ms for up to PCIE_LINK_RETRAIN_TIMEOUT_MS,
               1000 ms; a port without Link Active reporting sleeps 1000 + 100 ms instead
    busy wait: Root Port Busy polled every 10 ms for up to HZ jiffies, one second, and only on a
               port with the Root Port extensions; a timeout ends the callback, trigger still set
    bus wait:  on a port faster than 5 GT/s, the link coming up, then the first device answering,
               which pci_dev_wait() polls for up to PCIE_RESET_READY_POLL_MS (60 000 ms) less the delay
```

The port is contained from the trigger until the write in piece ⓑ, and the two waits of the callback before that write are bounded at v7.2 by 1100 ms and one second. The drivers below wait through the third interval as well before recovery resumes them.

### A surprise removal is cleared without logging or recovery

Pulling a device out of a hotplug slot takes the link down without warning, and a port with DPC can see a Surprise Down error and trigger. Logging that as an error and running recovery would treat an ordinary removal as a fault, and the comment in [`dpc_handler()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L363) cites PCIe r6.0 sec 6.7.6 for software ignoring such errors. Since commit commit [2ae8fbbe1cd4](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=2ae8fbbe1cd42a6624d345151859982cba89bbd3) ("PCI/DPC: Ignore Surprise Down error on hot removal") the thread tests for this case before anything else and, when it holds, clears the error state and releases the port itself with the same two waits the reset callback uses.

[`dpc_is_surprise_removal()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L349) makes the decision from two facts about the port; read it for both.

```c
/* drivers/pci/pcie/dpc.c:349 */
static bool dpc_is_surprise_removal(struct pci_dev *pdev)
{
	u16 status;

	if (!pdev->is_hotplug_bridge)
		return false;

	if (pci_read_config_word(pdev, pdev->aer_cap + PCI_ERR_UNCOR_STATUS,
				 &status))
		return false;

	return status & PCI_ERR_UNC_SURPDN;
}
```

The port must be a hotplug bridge, [`is_hotplug_bridge`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L483) set, and its Uncorrectable Error Status, read through [`aer_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370), must carry [`PCI_ERR_UNC_SURPDN`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L775). A failed read answers false, which sends the trigger down the error path. [`dpc_handle_surprise_removal()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L328) then does the cleanup; read it for the two waits it shares with the reset callback and for what it clears.

```c
/* drivers/pci/pcie/dpc.c:328 */
static void dpc_handle_surprise_removal(struct pci_dev *pdev)
{
	if (!pcie_wait_for_link(pdev, false)) {
		pci_info(pdev, "Data Link Layer Link Active not cleared in 1000 msec\n");
		goto out;
	}

	if (pdev->dpc_rp_extensions && dpc_wait_rp_inactive(pdev))
		goto out;

	pci_aer_raw_clear_status(pdev);
	pci_clear_surpdn_errors(pdev);

	pci_write_config_word(pdev, pdev->dpc_cap + PCI_EXP_DPC_STATUS,
			      PCI_EXP_DPC_STATUS_TRIGGER);

out:
	clear_bit(PCI_DPC_RECOVERED, &pdev->priv_flags);
	wake_up_all(&dpc_completed_waitqueue);
}
```

A link that does not go down within the bound prints "Data Link Layer Link Active not cleared in 1000 msec" and skips the clearing, and so does a Root Port that stays busy. Otherwise the function clears the port's AER status with [`pci_aer_raw_clear_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L308), clears what the Surprise Down left elsewhere with [`pci_clear_surpdn_errors()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L312), and writes Trigger Status as 1, which releases the port. Both exits clear [`PCI_DPC_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L769) and wake the waiters on [`dpc_completed_waitqueue`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L78), so a hotplug thread that waits learns that no recovery succeeded. [`pci_aer_raw_clear_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L308) clears the AER words whatever owns AER, as its comment says; read it for the registers it clears.

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
```

The function returns -EIO for a port without an AER capability, and otherwise writes back the Root Error Status of a Root Port or Root Complex Event Collector and the Correctable and Uncorrectable Error Status of any port, which clears every bit it read as set. [`pci_clear_surpdn_errors()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L312) clears the bits outside AER that a Surprise Down leaves, as its comment reports.

```c
/* drivers/pci/pcie/dpc.c:312 */
static void pci_clear_surpdn_errors(struct pci_dev *pdev)
{
	if (pdev->dpc_rp_extensions)
		pci_write_config_dword(pdev, pdev->dpc_cap +
				       PCI_EXP_DPC_RP_PIO_STATUS, ~0);

	/*
	 * In practice, Surprise Down errors have been observed to also set
	 * error bits in the Status Register as well as the Fatal Error
	 * Detected bit in the Device Status Register.
	 */
	pci_write_config_word(pdev, PCI_STATUS, 0xffff);

	pcie_capability_write_word(pdev, PCI_EXP_DEVSTA, PCI_EXP_DEVSTA_FED);
}
```

On a port with the extensions it writes all ones to [`PCI_EXP_DPC_RP_PIO_STATUS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1112), and on every port it writes 0xffff to [`PCI_STATUS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L53) and [`PCI_EXP_DEVSTA_FED`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L540) to Device Status through [`pcie_capability_write_word()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/access.c#L490), clearing the bits that read as set. The flowchart follows a trigger through the tests and the cleanup.

```text
    How the thread tells a surprise removal from an error, and what it clears for one
    ──────────────────────────────────────────────────────────────────────────────────

    ┌────────────────────────────────┐  no
    │ ① port is a hotplug bridge?    ├──────▶ error path: reference taken, reason logged,
    └───────────────┬────────────────┘        recovery run
                    │ yes
    ┌───────────────▼────────────────┐  read fails
    │ ② AER Uncorrectable Status     ├──────▶ error path
    │    read from the port          │
    └───────────────┬────────────────┘
                    │ read
    ┌───────────────▼────────────────┐  no
    │ ③ Surprise Down bit set?       ├──────▶ error path
    └───────────────┬────────────────┘
                    │ yes: no reason logged, no recovery
    ┌───────────────▼────────────────┐  no
    │ ④ link inactive within the     ├──────────────────────────┐
    │    link wait?                  │                          │
    └───────────────┬────────────────┘                          │
                    │ yes                                       │
    ┌───────────────▼────────────────┐  busy past one second    │
    │ ⑤ Root Port idle, or no Root   ├──────────────────────────┤
    │    Port extensions?            │                          │ nothing cleared,
    └───────────────┬────────────────┘                          │ port stays contained
                    │ yes                                       │
    ┌───────────────▼────────────────┐                          │
    │ AER status of the port cleared │                          │
    │ ⑥ RP PIO Status, Status and    │                          │
    │    Fatal Error Detected cleared│                          │
    │ ⑦ Trigger Status cleared       │                          │
    └───────────────┬────────────────┘                          │
                    ▼                                           │
    ┌────────────────────────────────┐                          │
    │ ⑧ RECOVERED cleared, waiters   │◀─────────────────────────┘
    │    woken                       │
    └────────────────────────────────┘

    ① dpc_is_surprise_removal  dpc.c:353  answers no for a port that is not a hotplug bridge
    ② dpc_is_surprise_removal  :356  reads Uncorrectable Error Status and answers no if the read fails
    ③ dpc_is_surprise_removal  :360  answers with the Surprise Down bit of that status
    ④ dpc_handle_surprise_removal  :330  waits for the link to go inactive and skips the clearing if not
    ⑤ dpc_handle_surprise_removal  :335  waits for Root Port Busy to clear on a port with the extensions
    ⑥ dpc_handle_surprise_removal  :339  clears the errors a Surprise Down leaves, through pci_clear_surpdn_errors
    ⑦ dpc_handle_surprise_removal  :341  writes Trigger Status, which releases the port
    ⑧ dpc_handle_surprise_removal  :345  clears PCI_DPC_RECOVERED on both exits before waking waiters
```

① [`dpc_is_surprise_removal()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L353) answers no at [`dpc.c:353-354`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L353) for a port that is not a hotplug bridge. ② `dpc_is_surprise_removal()` reads Uncorrectable Error Status at [`dpc.c:356-358`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L356) and answers no when the read fails. ③ `dpc_is_surprise_removal()` answers with the Surprise Down bit at [`dpc.c:360`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L360). ④ [`dpc_handle_surprise_removal()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L330) waits for the link to go down at [`dpc.c:330-333`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L330) and skips the clearing on a timeout. ⑤ `dpc_handle_surprise_removal()` waits for Root Port Busy at [`dpc.c:335-336`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L335) on a port with the extensions. ⑥ `dpc_handle_surprise_removal()` clears the Surprise Down leftovers at [`dpc.c:339`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L339) through [`pci_clear_surpdn_errors()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L312). ⑦ `dpc_handle_surprise_removal()` writes Trigger Status at [`dpc.c:341-342`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L341), which releases the port. ⑧ `dpc_handle_surprise_removal()` clears [`PCI_DPC_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L769) at [`dpc.c:345`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L345) on both exits before it wakes the waiters.

A surprise removal therefore ends with the port released and its error bits clear, no log line from the DPC thread, no recovery and [`PCI_DPC_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L769) clear; a port that failed a wait stays contained.

### The hotplug driver waits on the queue for recovery

A trigger takes the link down and recovery brings it back, and the hotplug driver of the same port sees both as Link Down and Link Up events. Handling them as a removal and an insertion would tear down the devices recovery is saving, so dpc.c gives the hotplug driver a way to wait for a running recovery and to learn whether it succeeded, built under [`CONFIG_HOTPLUG_PCI_PCIE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L16). The reader holds two threads of one port, the DPC thread and the hotplug thread, a wait queue between them, and the two bits of [`priv_flags`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L585) as the message.

The queue is a file-scope wait queue of dpc.c, and the wake-up condition is [`dpc_completed()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L81); read both for what a waiter waits for.

```c
/* drivers/pci/pcie/dpc.c:78 */
static DECLARE_WAIT_QUEUE_HEAD(dpc_completed_waitqueue);

#ifdef CONFIG_HOTPLUG_PCI_PCIE
static bool dpc_completed(struct pci_dev *pdev)
{
	u16 status;

	pci_read_config_word(pdev, pdev->dpc_cap + PCI_EXP_DPC_STATUS, &status);
	if ((!PCI_POSSIBLE_ERROR(status)) && (status & PCI_EXP_DPC_STATUS_TRIGGER))
		return false;

	if (test_bit(PCI_DPC_RECOVERING, &pdev->priv_flags))
		return false;

	return true;
}
```

[`dpc_completed_waitqueue`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L78) is declared for every build of dpc.c, since the reset callback and the surprise-removal path wake it, while [`dpc_completed()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L81) exists under [`CONFIG_HOTPLUG_PCI_PCIE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L16). The condition holds once Trigger Status reads clear, or reads as all ones from a port that has gone, and [`PCI_DPC_RECOVERING`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L770) is clear. The waiter is [`pci_dpc_recovered()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L103), a function of dpc.c that the hotplug driver calls; the page shows it for the DPC state it reads and leaves the hotplug driver's handling of the answer as a seam.

```c
/* drivers/pci/pcie/dpc.c:95 */
/**
 * pci_dpc_recovered - whether DPC triggered and has recovered successfully
 * @pdev: PCI device
 *
 * Return true if DPC was triggered for @pdev and has recovered successfully.
 * Wait for recovery if it hasn't completed yet.  Called from the PCIe hotplug
 * driver to recognize and ignore Link Down/Up events caused by DPC.
 */
bool pci_dpc_recovered(struct pci_dev *pdev)
{
	struct pci_host_bridge *host;

	if (!pdev->dpc_cap)
		return false;

	/*
	 * Synchronization between hotplug and DPC is not supported
	 * if DPC is owned by firmware and EDR is not enabled.
	 */
	host = pci_find_host_bridge(pdev->bus);
	if (!host->native_dpc && !IS_ENABLED(CONFIG_PCIE_EDR))
		return false;

	/*
	 * Need a timeout in case DPC never completes due to failure of
	 * dpc_wait_rp_inactive().  The spec doesn't mandate a time limit,
	 * but reports indicate that DPC completes within 4 seconds.
	 */
	wait_event_timeout(dpc_completed_waitqueue, dpc_completed(pdev),
			   msecs_to_jiffies(4000));

	return test_and_clear_bit(PCI_DPC_RECOVERED, &pdev->priv_flags);
}
```

The function answers false at once for a function without the DPC capability and for a host bridge without [`native_dpc`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L658) when [`CONFIG_PCIE_EDR`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L140) is unset. Otherwise it sleeps on [`dpc_completed_waitqueue`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L78) until [`dpc_completed()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L81) holds or 4000 ms pass, the bound the comment explains, and returns [`PCI_DPC_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L769) while clearing it. The hotplug interrupt thread calls it for a Data Link Layer State Changed or Presence Detect Changed event, as the stage of [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728) shows.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:728 */
static irqreturn_t pciehp_ist(int irq, void *dev_id)
{
	... /* 34 lines, to :764 */
	/*
	 * Ignore Link Down/Up events caused by Downstream Port Containment
	 * if recovery succeeded, or caused by Secondary Bus Reset,
	 * suspend to D3cold, firmware update, FPGA reconfiguration, etc.
	 */
	if ((events & (PCI_EXP_SLTSTA_PDC | PCI_EXP_SLTSTA_DLLSC)) &&
	    (pci_dpc_recovered(pdev) || pci_hp_spurious_link_change(pdev)) &&
	    ctrl->state == ON_STATE) {
		u16 ignored_events = PCI_EXP_SLTSTA_DLLSC;

		if (!ctrl->inband_presence_disabled)
			ignored_events |= PCI_EXP_SLTSTA_PDC;

		events &= ~ignored_events;
		pciehp_ignore_link_change(ctrl, pdev, irq, ignored_events);
	}
```

When [`pci_dpc_recovered()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L103) answers true and the slot is on, the thread removes the link-change events from the set it goes on to handle. [`pci_hp_spurious_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L552) is the other test on the line and belongs to the hotplug side of the seam. The [`native_dpc`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L658) bit that the first test reads starts at 1 for every host bridge, in [`pci_init_host_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L659).

```c
/* drivers/pci/probe.c:659 */
static void pci_init_host_bridge(struct pci_host_bridge *bridge)
{
	... /* 4 lines, to :665 */
	/*
	 * We assume we can manage these PCIe features.  Some systems may
	 * reserve these for use by the platform itself, e.g., an ACPI BIOS
	 * may implement its own AER handling and use _OSC to prevent the
	 * OS from interfering.
	 */
	bridge->native_aer = 1;
	bridge->native_pcie_hotplug = 1;
	bridge->native_shpc_hotplug = 1;
	bridge->native_pme = 1;
	bridge->native_ltr = 1;
	bridge->native_dpc = 1;
```

On the x86 ACPI path the bit is then settled by the `_OSC` negotiation, where [`calculate_control()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/pci_root.c#L498) decides whether the request carries DPC control; read the stage for the condition.

```c
/* drivers/acpi/pci_root.c:498 */
static u32 calculate_control(void)
{
	u32 control;
	... /* 13 lines, to :514 */
	if (pci_aer_available())
		control |= OSC_PCI_EXPRESS_AER_CONTROL;

	/*
	 * Per the Downstream Port Containment Related Enhancements ECN to
	 * the PCI Firmware Spec, r3.2, sec 4.5.1, table 4-5,
	 * OSC_PCI_EXPRESS_DPC_CONTROL indicates the OS supports both DPC
	 * and EDR.
	 */
	if (IS_ENABLED(CONFIG_PCIE_DPC) && IS_ENABLED(CONFIG_PCIE_EDR))
		control |= OSC_PCI_EXPRESS_DPC_CONTROL;

	return control;
```

The request carries [`OSC_PCI_EXPRESS_DPC_CONTROL`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/acpi.h#L646) when both [`CONFIG_PCIE_DPC`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L121) and [`CONFIG_PCIE_EDR`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L140) are set, which the comment ties to the firmware specification's meaning of the bit. [`acpi_pci_root_create()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/pci_root.c#L995) then clears the host bridge's bit when the negotiated set lacks it.

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
	if (!(root->osc_control_set & OSC_PCI_EXPRESS_PME_CONTROL))
		host_bridge->native_pme = 0;
	if (!(root->osc_control_set & OSC_PCI_EXPRESS_LTR_CONTROL))
		host_bridge->native_ltr = 0;
	if (!(root->osc_control_set & OSC_PCI_EXPRESS_DPC_CONTROL))
		host_bridge->native_dpc = 0;
```

With [`CONFIG_PCIE_EDR`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L140) unset, as this page assumes, the request carries no DPC bit, so on a host bridge whose controls come from the negotiation [`native_dpc`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L658) ends at 0 and [`pci_dpc_recovered()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L103) answers false at its second test. The hotplug thread then handles the link events of a DPC recovery like any other unless [`pci_hp_spurious_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L552) claims them. With the option set, the second test passes on every host bridge, and the wait runs. The swimlane shows the hand-off when the wait runs.

```text
    How the hotplug thread of the same port waits for a DPC recovery
    ────────────────────────────────────────────────────────────────

    time ↓
    DPC IRQ thread                ╎ dpc_completed_waitqueue   ╎ pciehp IRQ thread
    ──────────────────────────────┼───────────────────────────┼──────────────────────────────────
    recovery running:             ╎                           ╎ Link Down or Presence Detect
    RECOVERING 1, Trigger 1       ╎                           ╎ Changed seen on the port
                                  ╎                           ╎ ➍ DPC owned natively, or EDR
                                  ╎                           ╎    built: wait; else answer no
                                  ╎ waiter asleep ◀──────────── ➎ sleep for up to 4000 ms
    Trigger 0, RECOVERED 1,       ╎                           ╎
    RECOVERING 0                  ╎                           ╎
      ➊ wake every waiter ───────▶╎ waiter woken ────────────▶╎ ➋ Trigger Status 0 and
                                  ╎                           ╎ ➌ RECOVERING 0: condition true
                                  ╎                           ╎ ➏ RECOVERED read and cleared
                                  ╎                           ╎ ➐ 1: the link change is ignored

    a timeout ends the sleep as well; the condition is evaluated again before the bit is read

    ➊ dpc_reset_link  dpc.c:186  wakes every waiter after both bits are final
    ➋ dpc_completed  :86  answers false while Trigger Status reads set
    ➌ dpc_completed  :89  answers false while PCI_DPC_RECOVERING is set
    ➍ pci_dpc_recovered  :115  answers false without native_dpc on the host bridge and CONFIG_PCIE_EDR
    ➎ pci_dpc_recovered  :123  sleeps on the queue until dpc_completed() holds or 4000 ms pass
    ➏ pci_dpc_recovered  :126  returns PCI_DPC_RECOVERED and clears it
    ➐ pciehp_ist  pciehp_hpc.c:770  drops the link events when pci_dpc_recovered() answers true
```

➊ [`dpc_reset_link()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L186) wakes every waiter at [`dpc.c:186`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L186) after both bits are final. ➋ [`dpc_completed()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L86) answers false at [`dpc.c:86-87`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L86) while Trigger Status reads set. ➌ `dpc_completed()` answers false at [`dpc.c:89-90`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L89) while [`PCI_DPC_RECOVERING`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L770) is set. ➍ [`pci_dpc_recovered()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L115) answers false at [`dpc.c:115-116`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L115) without [`native_dpc`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L658) and [`CONFIG_PCIE_EDR`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L140). ➎ `pci_dpc_recovered()` sleeps at [`dpc.c:123-124`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L123) until the condition holds or 4000 ms pass. ➏ `pci_dpc_recovered()` returns [`PCI_DPC_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L769) and clears it at [`dpc.c:126`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L126). ➐ [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L770) drops the link events at [`pciehp_hpc.c:769-779`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L769) when the answer is true.

So far, the port has triggered, been logged, been released by the reset callback or the surprise-removal path, and told any waiting hotplug thread how the recovery ended through [`PCI_DPC_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L769) and the wait queue.

### Messages, hand-offs and files expose a containment event

A containment event leaves traces in the kernel log, in the AER counters and trace events, and in the interrupt and uevent interfaces, while its state between those points is held in registers and bits no file exposes. The lists below gather where each kind of trace comes from on the paths of this page.

No tracepoint is defined in dpc.c. On the uncorrectable branch, [`aer_print_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L865) fires [`aer_event`](https://elixir.bootlin.com/linux/v7.2/source/include/ras/ras_event.h#L337) at [`aer.c:879-880`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L879) with the port's name, the unmasked status and the severity, before its ratelimit test, as the AER subsection showed. A link that does not come back during the wait for the secondary bus can be retrained by [`pcie_failed_link_retrain()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/quirks.c#L95), which the link wait calls at [`pci.c:4657`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4657), and a retrain records [`pcie_link_event`](https://elixir.bootlin.com/linux/v7.2/source/include/trace/events/pci.h#L81) through the link-speed update; that tracepoint belongs to the link code, and the DPC paths fire no other.

The DPC messages print through [`pci_warn()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2892), [`pci_info()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2895) and [`pci_err()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2891), and the first line of dpc.c after its header comment defines [`dev_fmt`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L9), which those printers apply to the format; read it for the prefix every DPC message carries.

```c
/* drivers/pci/pcie/dpc.c:9 */
#define dev_fmt(fmt) "DPC: " fmt
```

Every message of dpc.c therefore starts with "DPC: " after the device name, at the sites in the table.

| Site | Message | What it reports |
|---|---|---|
| [`dpc.c:495`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L495) | "enabled with IRQ %d" | the probe armed the port on that interrupt |
| [`dpc.c:496`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L496) | "error containment capabilities: Int Msg #%d, RPExt%c PoisonedTLP%c SwTrigger%c RP PIO Log %d, DL_ActiveErr%c" | the Capability fields and [`dpc_rp_log_size`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L539) |
| [`dpc.c:487`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L487) | "request IRQ%d failed: %d" | the probe could not install its handlers |
| [`dpc.c:434`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L434) | "RP PIO log size %u is invalid" | enumeration discarded the log size |
| [`dpc.c:275`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L275) | "containment event, status:%#06x: unmasked uncorrectable error detected" | an uncorrectable trigger, before the AER record |
| [`dpc.c:288`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L288) | "containment event, status:%#06x, %s received from %04x:%02x:%02x.%d" | a received `ERR_FATAL` or `ERR_NONFATAL` and its requester |
| [`dpc.c:297`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L297) | "containment event, status:%#06x: %s detected" | an RP PIO error, a software trigger or a reserved reason |
| [`dpc.c:199`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L199), [`dpc.c:205`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L205) | "rp_pio_status: ...", "RP PIO severity=..." | the RP PIO words of a Root Port |
| [`dpc.c:214`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L214) | "[%2d] %s%s" | one named RP PIO error, " (First)" for the first |
| [`dpc.c:225`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L225), [`dpc.c:230`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L230) | the TLP log, "RP PIO ImpSpec Log %#010x" | the logged TLP and the implementation-specific dword |
| [`dpc.c:166`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L166), [`dpc.c:331`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L331) | "Data Link Layer Link Active not cleared in 1000 msec" | the link did not go down within the bound |
| [`dpc.c:142`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L142) | "root port still busy" | Root Port Busy outlasted one second |
| [`aer.c:894`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L894) | "%s Bus Error: severity=%s, type=%s, (%s)" and the lines after it | the AER record of an uncorrectable trigger |
| [`err.c:253`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L253), [`err.c:288`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L288), [`err.c:296`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L296) | "subordinate device reset failed", "device recovery successful", "device recovery failed" | the outcome of the recovery around the reset callback |
| [`pci.c:4816`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4816) | "Data Link Layer Link Active not set in %d msec" | the link did not come back after the release |
| [`pci.c:1247`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L1247), [`pci.c:1260`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L1260), [`pci.c:1269`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L1269) | "not ready %dms after %s; giving up", "not ready %dms after %s; waiting", "ready %dms after %s" | the first device below, with "DPC" as the reset type |

dpc.c holds no [`pci_dbg()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2896) site. With [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120) set, the paths this page follows reach the dynamic-debug sites of the table below, which `/sys/kernel/debug/dynamic_debug/control` turns on per site; [`CONFIG_PCI_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L70), unset here, would turn them on at build time.

| Site | Message | What enabling it shows |
|---|---|---|
| [`err.c:238`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L238) | "broadcast error_detected message" | recovery started telling the drivers below that the channel is frozen |
| [`err.c:246`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L246) | "broadcast mmio_enabled message" | the drivers voted to recover without a reset, which a frozen channel overrides |
| [`err.c:265`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L265) | "broadcast slot_reset message" | the drivers asked for a reset and the reset callback has run |
| [`err.c:272`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L272) | "broadcast resume message" | recovery succeeded and the drivers resume |
| [`pci.c:4790`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4790), [`pci.c:4812`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4812) | "waiting %d ms for downstream link", "waiting %d ms for downstream link, after activation" | which branch of the wait for the secondary bus ran and the delay it used |
| [`pci.c:1232`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L1232) | "disconnected; not waiting" | the device below was marked disconnected during the readiness poll |
| [`pci.c:1753`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L1753), [`pci.c:1783`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L1783) | "save config %#04x: %#010x", "restore config %#04x: %#010x -> %#010x" | the config header words saved after the probe and written back on a restore, beside which DPC Control travels |

Enabling the error-recovery sites shows where in recovery the reset callback ran and which vote the drivers gave, and the wait sites show how long the drivers below waited after the port was released.

The hand-offs the event crosses are few, and dpc.c uses no work item, timer, RCU or notifier chain. The hard handler hands the event to the IRQ thread through `IRQ_WAKE_THREAD`, and the IRQ core creates that thread in [`setup_irq_thread()`](https://elixir.bootlin.com/linux/v7.2/source/kernel/irq/manage.c#L1401); read it for the name the thread carries.

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

The DPC thread is named after the Linux interrupt number and the name "pcie-dpc" that the probe passed, and recovery runs inside it. Recovery reports its progress to user space through [`pci_uevent_ers()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L1625), which the error-recovery core calls for each device below the port; read it for the variables each uevent carries.

```c
/* drivers/pci/pci-driver.c:1625 */
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
```

A vote of none, can-recover or need-reset sends `ERROR_EVENT=BEGIN_RECOVERY` with `DEVICE_ONLINE=0`, a recovered result sends `SUCCESSFUL_RECOVERY` with `DEVICE_ONLINE=1`, and a disconnect sends `FAILED_RECOVERY` with `DEVICE_ONLINE=0`, each as a `KOBJ_CHANGE` uevent of the device. The DPC thread hands the outcome to the hotplug thread through [`dpc_completed_waitqueue`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L78), and with [`CONFIG_PCIE_EDR`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L140) set an ACPI notification enters through [`edr_handle_event()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/edr.c#L151). The device-managed interrupt is released by the driver core when the service device is unbound.

| Surface | Path or parameter | What it shows or changes |
|---|---|---|
| interrupt list | `/proc/interrupts` | the vector the probe requested, under the name "pcie-dpc" |
| boot parameter | `pcie_ports=dpc-native` | sets [`pcie_ports_dpc_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L620), so DPC binds without AER ownership |
| boot parameter | `pcie_ports=native`, `pcie_ports=compat` | [`pcie_ports_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L614) makes the OS own AER and DPC, and [`pcie_ports_disabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L607) stops the services from registering |
| boot parameter | `pci=noaer` | [`pci_no_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L133), at [`pci.c:6757-6758`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L6757), makes [`pci_aer_available()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L138) false, which removes the DPC service bit |
| sysfs | the AER statistics files of the port, [`Documentation/ABI/testing/sysfs-bus-pci-devices-aer`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/ABI/testing/sysfs-bus-pci-devices-aer) | the counters [`aer_print_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L865) increments through [`pci_dev_aer_stats_incr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L747) for an uncorrectable trigger |
| uevent | `KOBJ_CHANGE` with `ERROR_EVENT` | the recovery state of each device below the port |
| debugfs | none | dpc.c creates no debugfs file |
| fault injection | none | dpc.c has no injection point, and the AER injector of [`CONFIG_PCIEAER_INJECT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L37) feeds the AER service without touching the DPC capability |

Between these traces, Trigger Status and the reason are visible only through configuration-space reads of the port's DPC capability at the offsets the REGISTERS section draws, and the two bits of [`priv_flags`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L585) through no file.
