# AER device setup

> CAUTION: AI-GENERATED CONTENT
>
> STRICTLY DO NOT SUBMIT THIS UPSTREAM UNLESS YOU ARE AN EXPERT INTIMATELY FAMILIAR WITH THIS SUBSYSTEM.

An error that a PCIe function detects is first recorded in that function's own Advanced Error Reporting registers, and whether it is reported upstream, how it is classified and when its record is erased depend on how those registers were prepared. The PCI core prepares them for every function it enumerates, through the AER capability that the [`aer_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370) member of each [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) locates, before any driver binds and apart from the Root Port service that later collects error messages. On x86 the preparation writes registers only where ACPI _OSC has given the operating system control of AER, a grant the host bridge records in [`native_aer`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L653). This page follows one function's AER setup from enumeration to release, the clears that empty its status registers after errors and resets, and the save and restore that carry its controls across a reset.

```text
    One PCIe function's AER state: the registers it owns and the records the kernel keeps beside them
    ─────────────────────────────────────────────────────────────────────────────────────────────────

    struct pci_host_bridge                              configuration space of the function
    ┌──────────────────────────────────┐                ┌───────────────────────────────────────────────┐
    │ native_aer  1: OS owns AER       │                │ PCI Express capability                        │
    │             0: firmware owns AER │                │   Device Control  bits 3:0 reporting enables  │
    └─────────────────▲────────────────┘                │   Device Status   bits 3:0 errors detected    │
                      │ host bridge above the bus       └───────────────────────────────────────────────┘
    struct pci_dev    │                                 ┌───────────────────────────────────────────────┐
    ┌─────────────────┴────────────────┐                │ AER capability                                │
    │ bus                              │       ┌───────▶│   +0x04 Uncorrectable Error Status, RW1C      │
    │ aer_cap   offset of the block ───┼───────┘        │   +0x08 Uncorrectable Error Mask              │
    │ aer_info ─────────────────────┐  │                │   +0x0c Uncorrectable Error Severity          │
    └───────────────────────────────┼──┘                │   +0x10 Correctable Error Status, RW1C        │
                                    │                   │   +0x14 Correctable Error Mask                │
                                    │                   │   +0x18 Advanced Error Capabilities/Control   │
    struct aer_info                 ▼                   │   +0x2c Root Error Command, Root Port, RCEC   │
    ┌──────────────────────────────────┐                └───────────────────────────────────────────────┘
    │ error counters                   │
    │ correctable_ratelimit            │                save slot: struct pci_cap_saved_state
    │ nonfatal_ratelimit               │                ┌───────────────────────────────────────────────┐
    └──────────────────────────────────┘                │ the four or five control registers, saved     │
                                                        │ before a reset and written back after it      │
                                                        └───────────────────────────────────────────────┘
```

## SUMMARY

The model is one function, the AER registers it carries in configuration space and the records the kernel keeps beside them. The table settles which kernel object stands for each term of the PCIe specification, and the rest of the page uses those names.

| Specification term | Kernel representation | Written by |
|---|---|---|
| Function with an AER capability | a [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) whose [`aer_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370) holds the capability's offset | [`pci_aer_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L385) |
| Error reporting enables in Device Control | [`PCI_EXP_AER_FLAGS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L108) within [`PCI_EXP_DEVCTL`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L512) | [`pci_enable_pcie_error_reporting()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L253) |
| Error status, mask and severity registers | [`PCI_ERR_UNCOR_STATUS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L772) to [`PCI_ERR_CAP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L811), offsets from [`aer_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370) | the clears and [`pci_restore_aer_state()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L363) |
| AER control granted to the OS by _OSC | [`native_aer`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L653), tested by [`pcie_aer_is_native()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L242) | [`acpi_pci_root_create()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/pci_root.c#L995) |
| Error statistics and log ratelimits of a function | [`struct aer_info`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L60) behind [`aer_info`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L371) | [`pci_aer_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L385), [`pci_aer_exit()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L421) |
| Saved AER controls | a [`struct pci_cap_saved_state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L246) for [`PCI_EXT_CAP_ID_ERR`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L726) | [`pci_save_aer_state()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L341) |

The journey runs from [`pci_aer_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L385) at enumeration, through the status clears and the save and restore, to [`pci_aer_exit()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L421) at release. Ownership bounds it: among the functions this page shows, the ones that clear error state, set the reporting enables or change ECRC first test [`pcie_aer_is_native()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L242), so a function below a host bridge whose firmware kept AER keeps the values firmware gave it.

## SPECIFICATIONS

The registers come from the PCI Express Base Specification, which the tree cites by revision and section at the sites below; the per-function records, [`struct aer_info`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L60) and the save slot, are a kernel synthesis that no specification defines, read here from drivers/pci/pcie/aer.c, drivers/pci/pci.c and drivers/pci/probe.c.

- PCIe r6.0, sec 7.8.4.9, cited without a title by [`aer.c:404-409`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L404) in [`pci_aer_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L385) for the Root Error Command register that Root Ports and Root Complex Event Collectors implement.
- PCIe r7.0, sec 7.5.3.5, cited without a title by the message of commit [a8aeea1bf3c8](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=a8aeea1bf3c80cc87983689e0118770e019bd4f3) for the bits of the Device Status register that [`pcie_clear_device_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2240) writes.
- System Firmware Intermediary (SFI) _OSC and DPC Updates ECN, Feb 24, 2020, affecting PCI Firmware Specification, Rev. 3.2, cited by the message of commit [20e15e673b05](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=20e15e673b05a045fdbe534d40edf948e1b0b1af) as the reason [`pci_aer_raw_clear_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L308) clears without ownership.
- PCI Firmware Specification, r3.2, sec 4.5.1, table 4-5 (Downstream Port Containment Related Enhancements ECN), cited by [`pci_root.c:515-519`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/pci_root.c#L515) in [`calculate_control()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/pci_root.c#L498), the function that also asks _OSC for AER control.
- ACPI spec v6.3, sec 18.3.2.4, cited by the message of commit [708b20003624](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=708b2000362476c9c7a3571c0cc774dffb91836a) for the HEST FIRMWARE_FIRST bit, which the commit states says nothing about AER ownership.

## COVERAGE

### Per-function records (drivers/pci/pcie/aer.c, include/linux/pci.h)

- [`'struct aer_info'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L60): the per-function block of error counters and log ratelimits that [`pci_aer_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L385) allocates.
- [`'pci_dev.aer_cap'`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370): the offset of the AER capability in the function's configuration space, 0 when the kernel treats the function as having none.
- [`'pci_dev.aer_info'`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L371): the pointer to the function's [`struct aer_info`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L60).
- [`'\<pci_aer_init\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L385): locates the capability, allocates the records, clears the status, enables reporting and applies the ECRC policy.
- [`'\<pci_aer_exit\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L421): frees the [`struct aer_info`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L60) when the function is released.

### Global switches and ownership (drivers/pci/pcie/aer.c)

- [`'\<pci_no_aer\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L133): records pci=noaer.
- [`'\<pci_aer_available\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L138): true unless pci=noaer was given or MSI is disabled system-wide.
- [`'\<pcie_aer_is_native\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L242): nonzero when the function has the capability and the OS owns AER on its host bridge.

### Status clears (drivers/pci/pcie/aer.c, drivers/pci/pci.c)

- [`'\<pci_aer_raw_clear_status\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L308): clears the Correctable, Uncorrectable and, on a Root Port or RCEC, Root Error Status registers without an ownership test.
- [`'\<pci_aer_clear_status\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L333): the same clear under native ownership.
- [`'\<pci_aer_clear_nonfatal_status\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L264): clears the uncorrectable bits the Severity register leaves non-fatal.
- [`'\<pci_aer_clear_fatal_status\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L283): clears the uncorrectable bits the Severity register marks fatal.
- [`'\<pcie_clear_device_status\>':'drivers/pci/pci.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2240): clears the four error bits of Device Status and no other bit.

### Reporting enables and ECRC (drivers/pci/pcie/aer.c)

- [`'\<pci_enable_pcie_error_reporting\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L253): sets the four reporting enables in Device Control under native ownership.
- [`'\<pcie_set_ecrc_checking\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L207): applies the boot-time ECRC policy to one function.
- [`'\<enable_ecrc_checking\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L163): sets ECRC generation and checking where the function is capable of them.
- [`'\<disable_ecrc_checking\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L187): clears ECRC generation and checking.
- [`'\<pcie_ecrc_get_policy\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L230): parses the value of pci=ecrc= into the policy.

### Save and restore (drivers/pci/pcie/aer.c)

- [`'\<pci_save_aer_state\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L341): copies the AER control registers into the function's save slot.
- [`'\<pci_restore_aer_state\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L363): writes the saved control registers back.

### Device Control reporting enables (include/uapi/linux/pci_regs.h)

- [`'PCI_EXP_DEVCTL_CERE'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L513): Correctable Error Reporting Enable.
- [`'PCI_EXP_DEVCTL_NFERE'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L514): Non-Fatal Error Reporting Enable.
- [`'PCI_EXP_DEVCTL_FERE'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L515): Fatal Error Reporting Enable.
- [`'PCI_EXP_DEVCTL_URRE'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L516): Unsupported Request Reporting Enable.

### AER capability registers (include/uapi/linux/pci_regs.h)

- [`'PCI_ERR_UNCOR_STATUS'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L772): offset of the Uncorrectable Error Status register.
- [`'PCI_ERR_UNCOR_MASK'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L796): offset of the Uncorrectable Error Mask register.
- [`'PCI_ERR_UNCOR_SEVER'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L798): offset of the Uncorrectable Error Severity register.
- [`'PCI_ERR_COR_STATUS'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L800): offset of the Correctable Error Status register.
- [`'PCI_ERR_COR_MASK'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L809): offset of the Correctable Error Mask register.
- [`'PCI_ERR_CAP'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L811): offset of the Advanced Error Capabilities and Control register.

## DOCUMENTATION

- [`Documentation/PCI/pcieaer-howto.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/PCI/pcieaer-howto.rst): the AER driver depends on [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28) and [`CONFIG_PCIEPORTBUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L5), and Linux handles AER events only where firmware grants AER control through _OSC.
- [`Documentation/admin-guide/kernel-parameters.txt`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/admin-guide/kernel-parameters.txt): the pci=noaer, pci=ecrc= and pcie_ports= options, and the note that pci=ecrc= takes effect only under native AER control.

## OTHER SOURCES

### Added by Claude Opus 5.5

- [PCI/AER: Clear only error bits in PCIe Device Status (commit a8aeea1bf3c8)](https://patch.msgid.link/20260211124624.49656-1-xueshuai@linux.alibaba.com)
- [PCI/AER: Clear stale errors on reporting agents upon probe (commit e242d09b58e8)](https://patch.msgid.link/3011c2ed30c11f858e35e29939add754adea7478.1769332702.git.lukas@wunner.de)
- [PCI/AER: Fix NULL pointer access by aer_info (commit 0a27bdb14b02)](https://patch.msgid.link/20250904182527.67371-1-vernon2gm@gmail.com)
- [PCI/AER: Use bool for AER disable state tracking (commit 9890dd3fb7f9)](https://patch.msgid.link/20250516165223.125083-3-18255117159@163.com)
- [PCI/AER: Ratelimit correctable and non-fatal error logging (commit a57f2bfb4a58)](https://patch.msgid.link/20250522232339.1525671-19-helgaas@kernel.org)
- [PCI/AER: Rename struct aer_stats to aer_info (commit 09683a6184ad)](https://patch.msgid.link/20250522232339.1525671-16-helgaas@kernel.org)
- [PCI/AER: Export pcie_aer_is_native() (commit 49f776724e64)](https://lore.kernel.org/r/20230823234305.27333-3-Smita.KoralahalliChannabasappa@amd.com)
- [PCI/AER: Unexport pci_enable_pcie_error_reporting() (commit 7ec4b34be423)](https://lore.kernel.org/r/20230710232136.233034-3-helgaas@kernel.org)
- [PCI/AER: Drop unused pci_disable_pcie_error_reporting() (commit 69b264df8a41)](https://lore.kernel.org/r/20230710232136.233034-2-helgaas@kernel.org)
- [PCI/AER: Configure ECRC only if AER is native (commit bba5065963f8)](https://lore.kernel.org/r/20230112072111.20063-1-vidyas@nvidia.com)
- [PCI/AER: Enable error reporting when AER is native (commit f26e58bf6f54)](https://lore.kernel.org/r/20220125071820.2247260-4-sr@denx.de)
- [PCI/AER: Configure ECRC for every device (commit 9ffb98f144eb)](https://lore.kernel.org/r/20220125071820.2247260-2-sr@denx.de)
- [PCI/ERR: Rename pci_aer_clear_device_status() to pcie_clear_device_status() (commit 600a5b4fc8e8)](https://lore.kernel.org/r/20200717195619.766662-1-helgaas@kernel.org)
- [PCI/AER: Remove HEST/FIRMWARE_FIRST parsing for AER ownership (commit 708b20003624)](https://lore.kernel.org/r/9a37f53a4e6ff4942ff8e18dbb20b00e16c47341.1590534843.git.sathyanarayanan.kuppuswamy@linux.intel.com)
- [PCI/AER: Use only _OSC to determine AER ownership (commit c100beb9ccfb)](https://lore.kernel.org/r/67af2931705bed9a588b5a39d369cb70b9942190.1587925636.git.sathyanarayanan.kuppuswamy@linux.intel.com)
- [PCI/AER: Add pci_aer_raw_clear_status() to unconditionally clear Error Status (commit 20e15e673b05)](https://lore.kernel.org/r/c19ad28f3633cce67448609e89a75635da0da07d.1585000084.git.sathyanarayanan.kuppuswamy@linux.intel.com)
- [PCI/AER: Rationalize error status register clearing (commit 894020fdd88c)](https://lore.kernel.org/r/d1310a75dc3d28f7e8da4e99c45fbd3e60fe238e.1585000084.git.sathyanarayanan.kuppuswamy@linux.intel.com)
- [PCI/AER: Save AER Capability for suspend/resume (commit af65d1ad416b)](https://lore.kernel.org/r/92EBB4272BF81E4089A7126EC1E7B28492C3B007@IRSMSX101.ger.corp.intel.com)

## REGISTERS

The setup on this page touches two register blocks of each function, the AER capability that [`aer_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370) locates and the Device Control and Device Status registers of the PCI Express capability. The map below shows the AER block as offsets from [`aer_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370), with what the paths of this page do to each register; the status registers are cleared as whole words and the mask and severity registers are copied as whole words, so their per-error bit layouts are not drawn here.

```text
    The AER capability block: what this page's paths do to each register
    ────────────────────────────────────────────────────────────────────
    offset   ┌────────────────────────────────────────────┐
    +0x00    │ Extended Capability Header, ID 0x0001      │  located: aer_cap
             ├────────────────────────────────────────────┤
    +0x04    │ Uncorrectable Error Status    RW1C         │  cleared
             ├────────────────────────────────────────────┤
    +0x08    │ Uncorrectable Error Mask                   │  saved, restored
             ├────────────────────────────────────────────┤
    +0x0c    │ Uncorrectable Error Severity               │  read by the clears; saved, restored
             ├────────────────────────────────────────────┤
    +0x10    │ Correctable Error Status      RW1C         │  cleared
             ├────────────────────────────────────────────┤
    +0x14    │ Correctable Error Mask                     │  saved, restored
             ├────────────────────────────────────────────┤
    +0x18    │ Advanced Error Capabilities and Control    │  ECRC enables; saved, restored
             ├────────────────────────────────────────────┤
    +0x1c    │ Header Log, four dwords to +0x28           │  not touched here
             ├────────────────────────────────────────────┤
    +0x2c    │ Root Error Command    Root Port, RCEC      │  saved, restored
             ├────────────────────────────────────────────┤
    +0x30    │ Root Error Status     Root Port, RCEC      │  cleared by the raw clear
             ├────────────────────────────────────────────┤
    +0x34    │ Error Source Identification                │  not touched here
             ├────────────────────────────────────────────┤
    +0x38    │ TLP Prefix Log                             │  not touched here
             └────────────────────────────────────────────┘

    +0x04 = PCI_ERR_UNCOR_STATUS, +0x08 = PCI_ERR_UNCOR_MASK, +0x0c = PCI_ERR_UNCOR_SEVER
    +0x10 = PCI_ERR_COR_STATUS, +0x14 = PCI_ERR_COR_MASK, +0x18 = PCI_ERR_CAP, +0x1c = PCI_ERR_HEADER_LOG
    +0x2c = PCI_ERR_ROOT_COMMAND, +0x30 = PCI_ERR_ROOT_STATUS, +0x34 = PCI_ERR_ROOT_ERR_SRC, +0x38 = PCI_ERR_PREFIX_LOG
    ID 0x0001 = PCI_EXT_CAP_ID_ERR; each offset is added to aer_cap, the block's offset in configuration space
    Uncorrectable Mask and Severity repeat the Uncorrectable Status bits, Correctable Mask the Correctable Status bits
```

The two status registers are RW1C, so a clear writes ones to the bits to be cleared and zeros elsewhere. [`pci_aer_clear_nonfatal_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L264) and [`pci_aer_clear_fatal_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L283) read the Severity word to decide which uncorrectable bits to write, and [`pci_save_aer_state()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L341) copies the two mask registers, the severity register, the control register at [`PCI_ERR_CAP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L811) and, on a Root Port or an RCEC, the Root Error Command register into the save slot.

The Device Control register holds the four enables that let a function send error messages, and [`pci_enable_pcie_error_reporting()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L253) sets all four at once through the mask [`PCI_EXP_AER_FLAGS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L108). The other fields of the register belong to other paths and are left as they are.

```text
    Device Control: the four error reporting enables pci_enable_pcie_error_reporting() sets
    ─────────────────────────────────────────────────────────────────────────────────────────
    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    cap+8 │  other fields (15:4)  │U│F│N│C│
          └───────────────────────┴─┴─┴─┴─┘

    C = PCI_EXP_DEVCTL_CERE (0x0001, Correctable Error Reporting Enable)
    N = PCI_EXP_DEVCTL_NFERE (0x0002, Non-Fatal Error Reporting Enable)
    F = PCI_EXP_DEVCTL_FERE (0x0004, Fatal Error Reporting Enable)
    U = PCI_EXP_DEVCTL_URRE (0x0008, Unsupported Request Reporting Enable)
    C, N, F and U together = PCI_EXP_AER_FLAGS (drivers/pci/pci.h)
    other fields = relaxed ordering, payload and read request sizes and the rest, not written on these paths
    register = PCI_EXP_DEVCTL (0x08 into the PCI Express capability, whose offset is cap)
```

The AER service of the Root Port reads these bits back. [`is_error_source()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1015) does not search a function whose four enables are clear for the source of an error, and [`clear_status_iter()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1513) does not clear its status when the service binds.

Device Status records in four RW1C bits which error classes the function has detected, beside two read-only bits and a seventh bit that is RW1C but reports no error. [`pcie_clear_device_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2240) writes ones to the four error bits alone, [`PCI_EXP_DEVSTA_CED`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L538) to [`PCI_EXP_DEVSTA_URD`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L541), since commit [a8aeea1bf3c8](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=a8aeea1bf3c80cc87983689e0118770e019bd4f3) ("PCI/AER: Clear only error bits in PCIe Device Status").

```text
    Device Status: four RW1C error bits beside bits a clear must not touch
    ──────────────────────────────────────────────────────────────────────
    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    cap+a │ reserved (15:7) │E│T│A│U│F│N│C│
          └─────────────────┴─┴─┴─┴─┴─┴─┴─┘

    C = PCI_EXP_DEVSTA_CED (0x0001, Correctable Error Detected)
    N = PCI_EXP_DEVSTA_NFED (0x0002, Non-Fatal Error Detected)
    F = PCI_EXP_DEVSTA_FED (0x0004, Fatal Error Detected)
    U = PCI_EXP_DEVSTA_URD (0x0008, Unsupported Request Detected)
    A = PCI_EXP_DEVSTA_AUXPD (0x0010, AUX Power Detected, read-only)
    T = PCI_EXP_DEVSTA_TRPND (0x0020, Transactions Pending, read-only)
    E = Emergency Power Reduction Detected (bit 6, RW1C, no macro in pci_regs.h)
    register = PCI_EXP_DEVSTA (0x0a into the PCI Express capability)
```

The bit drawn as E is the Emergency Power Reduction Detected bit, which the message of that commit names and which pci_regs.h defines no macro for. A clear that wrote back the whole register would erase it, and the narrowed clear leaves it for the code that reads it.

The Advanced Error Capabilities and Control register pairs each ECRC enable with a capability bit. [`enable_ecrc_checking()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L163) sets the generation enable only where the generation-capable bit is set and the check enable only where the check-capable bit is set, and [`disable_ecrc_checking()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L187) clears both enables.

```text
    Advanced Error Capabilities and Control: the ECRC pairs the ECRC policy writes
    ───────────────────────────────────────────────────────────────────────────────
    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    +0x18 │       ·       │  SIZE   │L│    ·    │T│P│ · │K│k│G│g│   FEP   │
          │    (31:24)    │ (23:19) │ │ (17:13) │ │ │   │ │ │ │ │  (4:0)  │
          └───────────────┴─────────┴─┴─────────┴─┴─┴───┴─┴─┴─┴─┴─────────┘

    FEP = PCI_ERR_CAP_FEP(x) (First Error Pointer)
    g = PCI_ERR_CAP_ECRC_GENC (0x020, ECRC Generation Capable)
    G = PCI_ERR_CAP_ECRC_GENE (0x040, ECRC Generation Enable)
    k = PCI_ERR_CAP_ECRC_CHKC (0x080, ECRC Check Capable)
    K = PCI_ERR_CAP_ECRC_CHKE (0x100, ECRC Check Enable)
    P = PCI_ERR_CAP_PREFIX_LOG_PRESENT (0x800); T = PCI_ERR_CAP_COMP_TIME_LOG (0x1000)
    L = PCI_ERR_CAP_TLP_LOG_FLIT (0x40000); SIZE = PCI_ERR_CAP_TLP_LOG_SIZE (0xf80000, Flit Mode only)
    · = bits with no macro in pci_regs.h
    register = PCI_ERR_CAP (0x18 into the AER capability, whose offset is aer_cap)
```

The ECRC enables are the only bits of this register the page's paths change one by one; the save and restore copy the register as a whole word, First Error Pointer and logging bits included.

The Root Error Command register exists on Root Ports and Root Complex Event Collectors, the functions for which [`pcie_cap_has_rtctl()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/access.c#L378) is true, and its three enables decide whether the port interrupts on received error messages. This page only saves and restores it; the AER service sets the enables when it binds to the port.

```text
    Root Error Command: saved and restored only on a Root Port or an RCEC
    ─────────────────────────────────────────────────────────────────────
    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    +0x2c │         bits with no macro in pci_regs.h (31:3)         │F│N│C│
          └─────────────────────────────────────────────────────────┴─┴─┴─┘

    C = PCI_ERR_ROOT_CMD_COR_EN (0x1, Correctable Error Reporting Enable)
    N = PCI_ERR_ROOT_CMD_NONFATAL_EN (0x2, Non-Fatal Error Reporting Enable)
    F = PCI_ERR_ROOT_CMD_FATAL_EN (0x4, Fatal Error Reporting Enable)
    register = PCI_ERR_ROOT_COMMAND (0x2c into the AER capability)
```

The save slot of such a function therefore holds five dwords and that of any other function four, which is the size [`pci_aer_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L385) reserves.

## DETAILS

DETAILS first places the AER records of one function in [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) and then the conditions that gate every write to its registers, two global switches and the ownership flag of its host bridge. It follows [`pci_aer_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L385) through the scan and the records it leaves, then the clears of the two AER status registers and of Device Status. The reporting enables in Device Control and the ECRC policy come next, followed by the save and restore of the control registers across a reset. The error handlers that clear the status again, the release that frees the records, and the messages and files that make the setup visible close the page.

### Kconfig assumptions

The page documents the x86-64 defconfig resolved at v7.2, commit 8d3ae59288f1, with the PCIe port services, AER, DPC, ACPI and dynamic-debug options added, on x86-64 with ACPI. The table lists each option the prose below names and the value the page assumes for it.

| Option | Assumed value | What it decides on these paths |
|---|---|---|
| [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28) | y | compiles aer.c, the [`aer_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370) and [`aer_info`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L371) members and every helper of this page; without it the helpers are empty stubs |
| [`CONFIG_PCIEPORTBUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L5) | y | a dependency of [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28); defines [`pcie_ports_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L614) |
| [`CONFIG_PCI_MSI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L44) | y | makes [`pci_msi_enabled()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/msi/api.c#L407) report the pci=nomsi state; without it the function returns false and AER is unavailable |
| [`CONFIG_ACPI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/Kconfig#L9) | y | builds the _OSC negotiation that clears [`native_aer`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L653) and the _HPX programming of Device Control |
| [`CONFIG_PCIE_ECRC`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L55) | n | compiles the ECRC policy; unset, [`pcie_set_ecrc_checking()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L207) and [`pcie_ecrc_get_policy()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L230) are empty stubs |
| [`CONFIG_PCIE_DPC`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L121) | y | builds the DPC handlers that call the status clears |
| [`CONFIG_PCIE_EDR`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L140) | n | builds the EDR notify handler that calls the raw clear and the Device Status clear |
| [`CONFIG_PCIEAER_INJECT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L37) | n | builds the software error injector that reads [`aer_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370) |
| [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120) | y | makes the pci_dbg sites on the save and recovery paths switchable at run time |
| [`CONFIG_PCI_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L70) | n | would print those sites unconditionally |

The table indexes the prose: the effect of each option is stated again, with the option named, at the point where it applies.

### Each function keeps its own AER registers and records

Every PCIe function that implements Advanced Error Reporting carries its own copy of the AER registers, so each function records the errors it detects in registers of its own, whichever port later reports them to the operating system. The kernel therefore keeps AER state per function, in the [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) that stands for the specification's function. Two members hold it, both compiled only when [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28) is set; read the opening of the object for them.

```c
/* include/linux/pci.h:352 */
struct pci_dev {
	struct list_head bus_list;	/* Node in per-bus list */
	struct pci_bus	*bus;		/* Bus this device is on */
	struct pci_bus	*subordinate;	/* Bus this device bridges to */

	void		*sysdata;	/* Hook for sys-specific extension */
	struct proc_dir_entry *procent;	/* Device entry in /proc/bus/pci */
	struct pci_slot	*slot;		/* Physical slot this device is in */

	unsigned int	devfn;		/* Encoded device & function index */
	unsigned short	vendor;
	unsigned short	device;
	unsigned short	subsystem_vendor;
	unsigned short	subsystem_device;
	unsigned int	class;		/* 3 bytes: (base,sub,prog-if) */
	u8		revision;	/* PCI revision, low byte of class word */
	u8		hdr_type;	/* PCI header type (`multi' flag masked out) */
#ifdef CONFIG_PCIEAER
	u16		aer_cap;	/* AER capability offset */
	struct aer_info	*aer_info;	/* AER info for this device */
#endif
... /* 222 lines, to :595 */
};
```

[`aer_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370) holds the offset of the AER capability in the function's configuration space, and every register access of this page adds a register offset to it. A zero means the kernel treats the function as having no AER capability, either because the function has none or because the allocation of its records failed. [`aer_info`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L371) points at the function's [`struct aer_info`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L60), a block of error counters and log ratelimits. The members before them, the bus links, the devfn and the identity copied from the configuration header, are filled by the scan, and of them this page reads only [`bus`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L354), to find the host bridge above the function. The elided run of 222 lines, from the PCIe port service members to the end of the object, holds no AER state.

After the scan allocates the object zeroed, [`pci_aer_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L385) and [`pci_aer_exit()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L421) are the only functions in drivers/ and include/ at v7.2 that assign either member, and the lifecycle strip later on this page draws their writes. The rest of DETAILS reads the AER block through [`aer_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370) and the per-function records through [`aer_info`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L371).

### Two global switches decide whether reporting may be enabled

Before the kernel enables error reporting on any function, it asks whether AER should be used at all on this boot. The answer is global, the same for every function, and [`pci_aer_available()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L138) gives it. A false answer leaves the reporting enables of every function as they were found and keeps the Root Port service from registering, while the per-function records are still allocated.

The kernel command line sets the first switch. [`pci_setup()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L6743) parses the comma-separated values of the pci= option at early boot; read its opening stage for the two values this subsection cares about, noaer and nomsi.

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

The noaer value calls [`pci_no_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L133) and the nomsi value calls [`pci_no_msi()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/msi/msi.c#L985), each of which only records the option in a file-scope flag. Neither touches a device; later code reads the flags. The AER flag and the two functions that write and read it are defined at the top of aer.c.

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

[`pcie_aer_disable`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L130) starts false and [`pci_no_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L133) sets it, and no other function in the tree writes it. [`pci_aer_available()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L138) is true only while that flag is clear and [`pci_msi_enabled()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/msi/api.c#L407) reports MSI usable, so AER counts as unavailable when MSI is disabled system-wide as well. The second switch is the MSI state that [`pci_no_msi()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/msi/msi.c#L985) clears.

```c
/* drivers/pci/msi/msi.c:985 */
void pci_no_msi(void)
{
	pci_msi_enable = false;
}
```

[`pci_msi_enable`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/msi/msi.c#L18) is the flag both MSI functions use, and [`pci_msi_enabled()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/msi/api.c#L407) returns it to the AER code.

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
EXPORT_SYMBOL(pci_msi_enabled);
```

With [`CONFIG_PCI_MSI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L44) set, as the page assumes, the function returns the flag, which pci=nomsi and the other disabling paths named in its comment clear; without the option an inline stub in include/linux/pci.h returns false, so [`pci_aer_available()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L138) is false in every such build. Five functions in the tree ask the question at v7.2, and three of them shape the objects this page follows. The first is [`pcie_aer_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1735), which registers the Root Port service only when AER is available.

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

The second is the _OSC request of each host bridge. [`calculate_control()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/pci_root.c#L498) builds the control mask the kernel asks firmware for, and it asks for AER control only when [`pci_aer_available()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L138) is true.

```c
/* drivers/acpi/pci_root.c:498 */
static u32 calculate_control(void)
{
	u32 control;

	control = OSC_PCI_EXPRESS_CAPABILITY_CONTROL
		| OSC_PCI_EXPRESS_PME_CONTROL;

	if (IS_ENABLED(CONFIG_PCIEASPM))
		control |= OSC_PCI_EXPRESS_LTR_CONTROL;

	if (IS_ENABLED(CONFIG_HOTPLUG_PCI_PCIE))
		control |= OSC_PCI_EXPRESS_NATIVE_HP_CONTROL;

	if (IS_ENABLED(CONFIG_HOTPLUG_PCI_SHPC))
		control |= OSC_PCI_SHPC_NATIVE_HP_CONTROL;

	if (pci_aer_available())
		control |= OSC_PCI_EXPRESS_AER_CONTROL;
```

A boot with pci=noaer or pci=nomsi therefore does not ask firmware for AER control, which feeds the ownership flag of the next subsection. The third is [`pci_aer_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L385), which sets the reporting enables of a function only when [`pci_aer_available()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L138) is true, as its subsection below shows; the port driver and a second _OSC mask are the other two askers, outside this page's paths.

### The host bridge decides whether the kernel owns the registers

AER registers can be owned by the operating system or kept by platform firmware, which then handles errors itself and expects the OS to leave the registers alone. On x86 the boundary is a host bridge: firmware grants or withholds AER control through _OSC for the hierarchy below each host bridge, and every function in that hierarchy inherits the decision. The kernel records it in [`native_aer`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L653) of the [`struct pci_host_bridge`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L628), and [`pcie_aer_is_native()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L242) turns it into a per-function answer.

```text
    AER ownership is a place in the hierarchy: every function inherits its host bridge's native_aer
    ───────────────────────────────────────────────────────────────────────────────────────────────
    (pcie_ports=native not given, so pcie_ports_native is false)

             host bridge A                    ┊            host bridge B
             native_aer = 1                   ┊            native_aer = 0
             _OSC granted AER control         ┊            _OSC kept AER control in firmware
             ┌────────────────────────┐       ┊            ┌────────────────────────┐
             │ root bus               │       ┊            │ root bus               │
             └───────────┬────────────┘       ┊            └───────────┬────────────┘
                    ┌────┴──────┐             ┊                   ┌────┴──────┐
                    │ Root Port │ aer_cap ≠ 0 ┊                   │ Root Port │ aer_cap ≠ 0
                    └────┬──────┘             ┊                   └────┬──────┘
                    ┌────┴──────┐             ┊                   ┌────┴──────┐
                    │ Endpoint  │ aer_cap ≠ 0 ┊                   │ Endpoint  │ aer_cap ≠ 0
                    └───────────┘             ┊                   └───────────┘

             pcie_aer_is_native() = 1         ┊            pcie_aer_is_native() = 0
             for both functions: the helpers  ┊            for both functions: the helpers
             that test it go on to write      ┊            that test it return early

    a function whose aer_cap is 0 gets 0 under either host bridge
    pci_aer_raw_clear_status() and pcie_clear_device_status() test nothing and write on either side
```

The flag starts at 1 for every host bridge. [`pci_init_host_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L659) sets it while it initializes the bridge, together with the other native-control flags; read its opening stage for that default.

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

The comment over the assignments states the reason for the default, that the kernel assumes it may manage these features unless firmware reserves them. On the x86 ACPI path, built with [`CONFIG_ACPI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/Kconfig#L9), [`acpi_pci_root_create()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/pci_root.c#L995) then lowers each flag that _OSC did not grant; read its stage for the AER test.

```c
/* drivers/acpi/pci_root.c:995 */
struct pci_bus *acpi_pci_root_create(struct acpi_pci_root *root,
				     struct acpi_pci_root_ops *ops,
				     struct acpi_pci_root_info *info,
				     void *sysdata)
{
	int ret, busnum = root->secondary.start;
	struct acpi_device *device = root->device;
	int node = acpi_get_node(device->handle);
	struct pci_bus *bus;
	struct pci_host_bridge *host_bridge;

	... /* 18 lines, to :1024 */
	bus = pci_create_root_bus(NULL, busnum, ops->pci_ops,
				  sysdata, &info->resources);
	if (!bus)
		goto out_release_info;

	host_bridge = to_pci_host_bridge(bus->bridge);
	if (!(root->osc_control_set & OSC_PCI_EXPRESS_NATIVE_HP_CONTROL))
		host_bridge->native_pcie_hotplug = 0;
	if (!(root->osc_control_set & OSC_PCI_SHPC_NATIVE_HP_CONTROL))
		host_bridge->native_shpc_hotplug = 0;
	if (!(root->osc_control_set & OSC_PCI_EXPRESS_AER_CONTROL))
		host_bridge->native_aer = 0;
```

The function creates the root bus first and then clears [`native_aer`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L653) when the root's granted control set lacks OSC_PCI_EXPRESS_AER_CONTROL. Since [`calculate_control()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/pci_root.c#L498) asks for that bit only when [`pci_aer_available()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L138) is true, a boot with pci=noaer or pci=nomsi does not request it, and a host bridge whose _OSC grants only what was requested ends with the flag cleared. A user can override the firmware's decision with pcie_ports=native, which sets [`pcie_ports_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L614) in the port driver's option handler.

```c
/* drivers/pci/pcie/portdrv.c:609 */
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

The comment says what the option does on ACPI systems, that _OSC is ignored. The lanes below put the kernel's and the firmware's parts in the order a boot runs them, up to the setup of each function.

```text
    Ownership is settled before any function is set up: one host bridge, from the command line to the scan
    ──────────────────────────────────────────────────────────────────────────────────────────────────────

    time   kernel                                                 platform firmware
     │     ┌──────────────────────────────────────────────┐
     │     │ command line parsed: pcie_aer_disable and    │
     │     │ pci_msi_enable fixed for the boot            │
     │     └──────────────────────────────────────────────┘
     │     ┌──────────────────────────────────────────────┐       ┌──────────────────────────────────┐
     │     │ host bridge created: native_aer = 1          │       │                                  │
     │     │ _OSC control mask: AER bit only when         ├──────▶│ _OSC grants AER control,         │
     │     │ pci_aer_available() is true                  │       │ or withholds it                  │
     │     │                                              │◀──────┤                                  │
     │     │ native_aer = 0 unless AER was granted        │       │                                  │
     │     └──────────────────────────────────────────────┘       └──────────────────────────────────┘
     │     ┌──────────────────────────────────────────────┐       ┌──────────────────────────────────┐
     │     │ each function configured: _HPX Type 2        │◀──────┤ _HPX of the nearest bridge       │
     │     │ applied only where native_aer = 0            │       │ supplies Device Control and      │
     │     │                                              │       │ AER register values              │
     │     └──────────────────────────────────────────────┘       └──────────────────────────────────┘
     │     ┌──────────────────────────────────────────────┐
     │     │ each function set up: clears, enables and    │
     │     │ ECRC only where pcie_aer_is_native()         │
     ▼     └──────────────────────────────────────────────┘
```

The kernel fixes the global switches before it asks firmware anything, firmware's _OSC answer then fixes [`native_aer`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L653) for the whole hierarchy, and only afterwards does the scan configure and set up each function against that flag. With [`CONFIG_PCIEPORTBUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L5) unset, include/linux/pci.h defines [`pcie_ports_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L614) as the constant false, and the variable does not exist. [`pcie_aer_is_native()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L242) combines the two sources with the function's own capability.

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

A function without an AER capability is never native, whatever its host bridge says, and for a function with one the answer is [`pcie_ports_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L614) or the [`native_aer`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L653) of the host bridge above it. [`pci_find_host_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/host-bridge.c#L20) reaches the host bridge from any bus by climbing to the root bus.

```c
/* drivers/pci/host-bridge.c:20 */
struct pci_host_bridge *pci_find_host_bridge(struct pci_bus *bus)
{
	struct pci_bus *root_bus = find_pci_root_bus(bus);

	return to_pci_host_bridge(root_bus->bridge);
}
EXPORT_SYMBOL_GPL(pci_find_host_bridge);
```

The root bus's [`bridge`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L730) is the host bridge's embedded device, so the answer is the same for every function of one hierarchy, as the figure above draws it. The table sums up what the setup of one function writes for each combination of the global switch and the ownership answer.

| [`pci_aer_available()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L138) | [`pcie_aer_is_native()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L242) | Status registers at setup | Device Control enables | ECRC policy |
|---|---|---|---|---|
| true | 1 | cleared by [`pci_aer_clear_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L333) | set by [`pci_enable_pcie_error_reporting()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L253) | applied by [`pcie_set_ecrc_checking()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L207) when [`CONFIG_PCIE_ECRC`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L55) is set |
| false, for example under pci=noaer with pcie_ports=native | 1 | cleared | left as found | applied when [`CONFIG_PCIE_ECRC`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L55) is set |
| true or false | 0 | left to firmware | left as found | left as found |

For a function with an AER capability the records are set up in every row, because [`pci_aer_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L385) allocates them before it asks either question. The ownership answer is the condition the rest of DETAILS returns to whenever a helper writes a register.

### pci_aer_init runs once per function during the scan

Each function the PCI core enumerates passes through [`pci_device_add()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2726), which configures the function, sets up its capabilities and only then publishes it to the driver model. AER setup belongs to the capability stage, so it runs once per function, before the function's sysfs files exist and before any driver can bind. Read the stage of [`pci_device_add()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2726) for that order.

```c
/* drivers/pci/probe.c:2726 */
void pci_device_add(struct pci_dev *dev, struct pci_bus *bus)
{
	int ret;

	pci_configure_device(dev);

	... /* 18 lines, to :2750 */
	pci_init_capabilities(dev);

	/*
	 * Add the device to our list of discovered devices
	 * and the bus list for fixup functions, etc.
	 */
	down_write(&pci_bus_sem);
	list_add_tail(&dev->bus_list, &bus->devices);
	up_write(&pci_bus_sem);

	ret = pcibios_device_add(dev);
	WARN_ON(ret < 0);

	/* Set up MSI IRQ domain */
	pci_set_msi_domain(dev);

	/* Notifier could use PCI capabilities */
	ret = device_add(&dev->dev);
	WARN_ON(ret < 0);
```

[`pci_configure_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2452) at [`probe.c:2730`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2730) runs before the capabilities are set up, and it ends by applying the firmware's _HPX settings, which can write the reporting enables, as the Device Control subsection shows. [`pci_init_capabilities()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2650) follows at [`probe.c:2750`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2750), and `device_add()` at [`probe.c:2767`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2767) then creates the sysfs files, whose AER groups test the records this setup allocates. The capability stage calls each capability's setup in a fixed order; read it up to the AER line.

```c
/* drivers/pci/probe.c:2650 */
static void pci_init_capabilities(struct pci_dev *dev)
{
	pci_ea_init(dev);		/* Enhanced Allocation */
	pci_msi_init(dev);		/* Disable MSI */
	pci_msix_init(dev);		/* Disable MSI-X */

	/* Buffers for saving PCIe and PCI-X capabilities */
	pci_allocate_cap_save_buffers(dev);

	pci_imm_ready_init(dev);	/* Immediate Readiness */
	pci_pm_init(dev);		/* Power Management */
	pci_vpd_init(dev);		/* Vital Product Data */
	pci_configure_ari(dev);		/* Alternative Routing-ID Forwarding */
	pci_iov_init(dev);		/* Single Root I/O Virtualization */
	pci_ats_init(dev);		/* Address Translation Services */
	pci_pri_init(dev);		/* Page Request Interface */
	pci_pasid_init(dev);		/* Process Address Space ID */
	pci_acs_init(dev);		/* Access Control Services */
	pci_ptm_init(dev);		/* Precision Time Measurement */
	pci_aer_init(dev);		/* Advanced Error Reporting */
```

[`pci_aer_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L385) runs after the save buffers of the PCI Express capability are allocated and after Access Control Services and Precision Time Measurement are set up, and before the setup of Downstream Port Containment and of Root Complex Event Collectors. It is the only caller of [`pci_aer_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L385) at v7.2. The function works in a fixed order, and the later subsections take its steps one at a time.

```c
/* drivers/pci/pcie/aer.c:385 */
void pci_aer_init(struct pci_dev *dev)
{
	int n;

	dev->aer_cap = pci_find_ext_capability(dev, PCI_EXT_CAP_ID_ERR);
	if (!dev->aer_cap)
		return;

	dev->aer_info = kzalloc_obj(*dev->aer_info);
	if (!dev->aer_info) {
		dev->aer_cap = 0;
		return;
	}

	ratelimit_state_init(&dev->aer_info->correctable_ratelimit,
			     DEFAULT_RATELIMIT_INTERVAL, DEFAULT_RATELIMIT_BURST);
	ratelimit_state_init(&dev->aer_info->nonfatal_ratelimit,
			     DEFAULT_RATELIMIT_INTERVAL, DEFAULT_RATELIMIT_BURST);

	/*
	 * We save/restore PCI_ERR_UNCOR_MASK, PCI_ERR_UNCOR_SEVER,
	 * PCI_ERR_COR_MASK, and PCI_ERR_CAP.  Root and Root Complex Event
	 * Collectors also implement PCI_ERR_ROOT_COMMAND (PCIe r6.0, sec
	 * 7.8.4.9).
	 */
	n = pcie_cap_has_rtctl(dev) ? 5 : 4;
	pci_add_ext_cap_save_buffer(dev, PCI_EXT_CAP_ID_ERR, sizeof(u32) * n);

	pci_aer_clear_status(dev);

	if (pci_aer_available())
		pci_enable_pcie_error_reporting(dev);

	pcie_set_ecrc_checking(dev);
}
```

The function first locates the capability and returns at once for a function without one, leaving [`aer_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370) at 0 and allocating nothing. It then allocates the [`struct aer_info`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L60) and readies its two ratelimits, and on an allocation failure it resets [`aer_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370) to 0, so the rest of the kernel treats the function as having no AER capability, the behavior commit [0a27bdb14b02](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=0a27bdb14b028fed30a10cec2f945c38cb5ca4fa) ("PCI/AER: Fix NULL pointer access by aer_info") introduced. Next it reserves a save slot of five dwords for a Root Port or an RCEC and four for any other function, which the comment above the line ties to the registers saved. Only then does it touch the hardware, clearing the status registers, setting the reporting enables when [`pci_aer_available()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L138) is true, and applying the ECRC policy. A hot-added function passes through the same path, and commit [9ffb98f144eb](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=9ffb98f144ebdc9345f3b34fac35c4ff12ae4e50) ("PCI/AER: Configure ECRC for every device") moved the ECRC call here so that such functions get the policy too.

### The offset, the info block and a save slot record the setup

The first half of [`pci_aer_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L385) writes no register; it leaves three records that later code depends on. The offset tells every helper where the AER block starts, the [`struct aer_info`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L60) gives the error-handling code a place to count errors and ratelimit its messages, and the save slot gives the suspend and reset paths a place to keep the control registers. This subsection reads the helpers that produce the three and ends with the strip of their writes.

The offset comes from [`pci_find_ext_capability()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L540), which searches the function's extended capability list for an ID. Read its comment for the return value the setup relies on.

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
EXPORT_SYMBOL_GPL(pci_find_ext_capability);
```

A zero return, for a function that does not support the capability as the comment puts it, makes [`pci_aer_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L385) return early, and [`pcie_aer_is_native()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L242) later tests the same zero. The ID passed is [`PCI_EXT_CAP_ID_ERR`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L726), the Advanced Error Reporting entry of the extended capability IDs.

```c
/* include/uapi/linux/pci_regs.h:726 */
#define PCI_EXT_CAP_ID_ERR	0x01	/* Advanced Error Reporting */
```

The info block is a [`struct aer_info`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L60), private to aer.c and reached only through [`aer_info`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L371). Its members fall into three groups by who uses them; read the definition with its comments for the grouping.

```c
/* drivers/pci/pcie/aer.c:59 */
/* AER info for the device */
struct aer_info {

	/*
	 * Fields for all AER capable devices. They indicate the errors
	 * "as seen by this device". Note that this may mean that if an
	 * Endpoint is causing problems, the AER counters may increment
	 * at its link partner (e.g. Root Port) because the errors will be
	 * "seen" by the link partner and not the problematic Endpoint
	 * itself (which may report all counters as 0 as it never saw any
	 * problems).
	 */
	/* Counters for different type of correctable errors */
	u64 dev_cor_errs[AER_MAX_TYPEOF_COR_ERRS];
	/* Counters for different type of fatal uncorrectable errors */
	u64 dev_fatal_errs[AER_MAX_TYPEOF_UNCOR_ERRS];
	/* Counters for different type of nonfatal uncorrectable errors */
	u64 dev_nonfatal_errs[AER_MAX_TYPEOF_UNCOR_ERRS];
	/* Total number of ERR_COR sent by this device */
	u64 dev_total_cor_errs;
	/* Total number of ERR_FATAL sent by this device */
	u64 dev_total_fatal_errs;
	/* Total number of ERR_NONFATAL sent by this device */
	u64 dev_total_nonfatal_errs;

	/*
	 * Fields for Root Ports & Root Complex Event Collectors only; these
	 * indicate the total number of ERR_COR, ERR_FATAL, and ERR_NONFATAL
	 * messages received by the Root Port / Event Collector, INCLUDING the
	 * ones that are generated internally (by the Root Port itself)
	 */
	u64 rootport_total_cor_errs;
	u64 rootport_total_fatal_errs;
	u64 rootport_total_nonfatal_errs;

	/* Ratelimits for errors */
	struct ratelimit_state correctable_ratelimit;
	struct ratelimit_state nonfatal_ratelimit;
```

The first group, [`dev_cor_errs`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L72), [`dev_fatal_errs`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L74) and [`dev_nonfatal_errs`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L76) with their totals [`dev_total_cor_errs`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L78), [`dev_total_fatal_errs`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L80) and [`dev_total_nonfatal_errs`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L82), counts the errors this function reported, by type and in total, as the comments over the members say. The second group, [`rootport_total_cor_errs`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L90), [`rootport_total_fatal_errs`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L91) and [`rootport_total_nonfatal_errs`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L92), counts the error messages a Root Port or RCEC received, and the comment above it limits it to those functions. The error-handling path of the AER service increments both groups; the setup leaves them at the zero of the allocation. The third group, [`correctable_ratelimit`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L95) and [`nonfatal_ratelimit`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L96), throttles the log messages for correctable and non-fatal errors, and it is the only group [`pci_aer_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L385) initializes, to `DEFAULT_RATELIMIT_INTERVAL` and `DEFAULT_RATELIMIT_BURST`.

The save slot is a [`struct pci_cap_saved_state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L246), one entry of the list of saved capability states that the PCI core keeps per function. Read [`struct pci_cap_saved_data`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L239) and the [`struct pci_cap_saved_state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L246) that wraps it for the slot's shape.

```c
/* drivers/pci/pci.h:239 */
struct pci_cap_saved_data {
	u16		cap_nr;
	bool		cap_extended;
	unsigned int	size;
	u32		data[];
};

struct pci_cap_saved_state {
	struct hlist_node		next;
	struct pci_cap_saved_data	cap;
};
```

[`cap_nr`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L240) and [`cap_extended`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L241) name the capability the slot belongs to, [`size`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L242) its length in bytes, and [`data`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L243) the dwords that the save fills. [`pci_add_ext_cap_save_buffer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L3475) allocates such a slot for an extended capability; read it with [`_pci_add_cap_save_buffer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L3444), the helper it wraps.

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

The slot is allocated only when the capability is found, zeroed, labeled with the capability's ID and linked into the function's list. [`pci_aer_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L385) ignores the return value, so a failed allocation leaves the function without a slot, and the save and restore then find nothing and return. The size it asks for depends on [`pcie_cap_has_rtctl()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/access.c#L378), which is true for the two port types that implement the Root Error Command register.

```c
/* drivers/pci/access.c:378 */
bool pcie_cap_has_rtctl(const struct pci_dev *dev)
{
	int type = pci_pcie_type(dev);

	return type == PCI_EXP_TYPE_ROOT_PORT ||
	       type == PCI_EXP_TYPE_RC_EC;
}
```

A Root Port or an RCEC therefore gets five dwords and every other function four, matching the five or four registers the save copies. The strip follows the three records and the member that points at the info block from the scan to the release.

```text
    One function's AER records from the scan to the release
    ───────────────────────────────────────────────────────
    fields: aer_cap and aer_info of struct pci_dev, the struct aer_info, the AER save slot

    time ────────────────────────────────────────────────────────────────────────────────────────────────────────▶
    event        find      alloc      ratelimits   save slot   pci_save_state                      release
                 ▼         ▼          ▼            ▼           ▼                                   ▼
                 ┌────────────────────────────────────────────────────────────────────────────────────────────┐
    aer_cap      │ ① offset of the AER capability in configuration space                                      │
                 └────────────────────────────────────────────────────────────────────────────────────────────┘
                 ┌─────────┬──────────────────────────────────────────────────────────────────────────────────┐
    alloc fails  │ ① offset│ ③ 0: from here on the function is treated as having no AER capability            │
                 └─────────┴──────────────────────────────────────────────────────────────────────────────────┘
                 ┌─────────┬───────────────────────────────────────────────────────────────────────┬──────────┐
    aer_info     │ NULL    │ ② points at the struct aer_info                                       │ ⑨ NULL   │
                 └─────────┴───────────────────────────────────────────────────────────────────────┴──────────┘
                           ┌──────────┬────────────────────────────────────────────────────────────┬──────────┐
    *aer_info              │ ② zeroed │ ④ ⑤ ratelimits ready; counters grow as errors are handled  │ ⑧ freed  │
                           └──────────┴────────────────────────────────────────────────────────────┴──────────┘
                                                   ┌───────────┬───────────────────────────────────┬──────────┐
    save slot                                      │ ⑥ zeroed  │ ⑦ dwords saved, restore reads them│ ⑩ freed  │
                                                   └───────────┴───────────────────────────────────┴──────────┘

    ① pci_aer_init             aer.c:389    stores the capability offset in aer_cap
    ② pci_aer_init             :393         allocates the zeroed struct aer_info into aer_info
    ③ pci_aer_init             :395         resets aer_cap to 0 when that allocation fails
    ④ pci_aer_init             :399         initializes correctable_ratelimit through ratelimit_state_init
    ⑤ pci_aer_init             :401         initializes nonfatal_ratelimit through ratelimit_state_init
    ⑥ pci_aer_init             :412         allocates the zeroed save slot through pci_add_ext_cap_save_buffer
    ⑦ pci_save_aer_state       :355         fills the slot's dwords through pci_read_config_dword
    ⑧ pci_aer_exit             :423         frees the struct aer_info with kfree
    ⑨ pci_aer_exit             :424         sets aer_info back to NULL
    ⑩ pci_release_capabilities probe.c:2471 frees the save slot through pci_free_cap_save_buffers
```

① [`pci_aer_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L385) stores the capability offset in [`aer_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370) at [`aer.c:389`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L389). ② `pci_aer_init()` allocates the zeroed [`struct aer_info`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L60) into [`aer_info`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L371). ③ `pci_aer_init()` resets [`aer_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370) to 0 when that allocation fails. ④ `pci_aer_init()` initializes [`correctable_ratelimit`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L95) through `ratelimit_state_init()`. ⑤ `pci_aer_init()` initializes [`nonfatal_ratelimit`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L96) the same way. ⑥ `pci_aer_init()` allocates the zeroed save slot through [`pci_add_ext_cap_save_buffer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L3475). ⑦ [`pci_save_aer_state()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L341) fills the slot's dwords from the registers. ⑧ [`pci_aer_exit()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L421) frees the [`struct aer_info`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L60). ⑨ `pci_aer_exit()` sets [`aer_info`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L371) back to NULL. ⑩ [`pci_release_capabilities()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2466) frees the save slot through [`pci_free_cap_save_buffers()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L3505).

The strip leaves out writers the page does not show. The allocation of the [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) itself by [`pci_alloc_dev()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2500) at [`probe.c:2504`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2504) zeroes [`aer_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370) and [`aer_info`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L371) before the scan reaches [`pci_aer_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L385), and the page leaves that object's allocation to its own lifecycle. [`pci_dev_aer_stats_incr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L747) at [`aer.c:750`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L750) and [`pci_rootport_aer_stats_incr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L781) at [`aer.c:781`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L781) increment the counters of the [`struct aer_info`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L60), and [`aer_ratelimit()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L800) at [`aer.c:800`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L800) advances the ratelimit states through `__ratelimit()`; the sysfs store functions that [`aer_ratelimit_interval_attr`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L647) and [`aer_ratelimit_burst_attr`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L682) generate rewrite the ratelimit interval and burst. All four belong to the error-handling and logging path of the AER service, which runs after this setup and is not followed here. On the failure path [`aer_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370) is nonzero while [`aer_info`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L371) is NULL from ② to ③, and the reset at ③ closes that interval before [`pci_aer_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L385) returns.

So far, the scan has found the function's AER capability, recorded its offset in [`aer_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370) and allocated the [`struct aer_info`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L60) and the save slot, which takes the strip to its fourth column; the rest of [`pci_aer_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L385) writes the registers.

### Status registers are cleared by writing their own value back

A function's AER status registers keep an error bit set until software clears it, so bits left over from firmware or from before a reset would otherwise still be set when the error handling of a later, unrelated error reads the registers. The setup therefore clears them before it enables reporting, and the error handlers clear them again after each error. Both status registers are RW1C: writing a one clears the bit, writing a zero leaves it, so a clear reads the register and writes back the bits to be cleared. The offsets the clears add to [`aer_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370) are defined with the other AER registers in pci_regs.h; read the uncorrectable group, which starts at [`PCI_ERR_UNCOR_STATUS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L772), first.

```c
/* include/uapi/linux/pci_regs.h:771 */
/* Advanced Error Reporting */
#define PCI_ERR_UNCOR_STATUS	0x04	/* Uncorrectable Error Status */
#define  PCI_ERR_UNC_UND	0x00000001	/* Undefined */
#define  PCI_ERR_UNC_DLP	0x00000010	/* Data Link Protocol */
#define  PCI_ERR_UNC_SURPDN	0x00000020	/* Surprise Down */
#define  PCI_ERR_UNC_POISON_TLP	0x00001000	/* Poisoned TLP */
#define  PCI_ERR_UNC_FCP	0x00002000	/* Flow Control Protocol */
#define  PCI_ERR_UNC_COMP_TIME	0x00004000	/* Completion Timeout */
#define  PCI_ERR_UNC_COMP_ABORT	0x00008000	/* Completer Abort */
#define  PCI_ERR_UNC_UNX_COMP	0x00010000	/* Unexpected Completion */
#define  PCI_ERR_UNC_RX_OVER	0x00020000	/* Receiver Overflow */
#define  PCI_ERR_UNC_MALF_TLP	0x00040000	/* Malformed TLP */
#define  PCI_ERR_UNC_ECRC	0x00080000	/* ECRC Error Status */
#define  PCI_ERR_UNC_UNSUP	0x00100000	/* Unsupported Request */
#define  PCI_ERR_UNC_ACSV	0x00200000	/* ACS Violation */
#define  PCI_ERR_UNC_INTN	0x00400000	/* internal error */
#define  PCI_ERR_UNC_MCBTLP	0x00800000	/* MC blocked TLP */
#define  PCI_ERR_UNC_ATOMEG	0x01000000	/* Atomic egress blocked */
#define  PCI_ERR_UNC_TLPPRE	0x02000000	/* TLP prefix blocked */
#define  PCI_ERR_UNC_POISON_BLK	0x04000000	/* Poisoned TLP Egress Blocked */
#define  PCI_ERR_UNC_DMWR_BLK	0x08000000	/* DMWr Request Egress Blocked */
#define  PCI_ERR_UNC_IDE_CHECK	0x10000000	/* IDE Check Failed */
#define  PCI_ERR_UNC_MISR_IDE	0x20000000	/* Misrouted IDE TLP */
#define  PCI_ERR_UNC_PCRC_CHECK	0x40000000	/* PCRC Check Failed */
#define  PCI_ERR_UNC_XLAT_BLK	0x80000000	/* TLP Translation Egress Blocked */
#define PCI_ERR_UNCOR_MASK	0x08	/* Uncorrectable Error Mask */
	/* Same bits as above */
#define PCI_ERR_UNCOR_SEVER	0x0c	/* Uncorrectable Error Severity */
	/* Same bits as above */
```

[`PCI_ERR_UNCOR_STATUS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L772) at offset 0x04 records uncorrectable errors, one bit per error type from [`PCI_ERR_UNC_UND`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L773) to [`PCI_ERR_UNC_XLAT_BLK`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L795). [`PCI_ERR_UNCOR_MASK`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L796) at 0x08 and [`PCI_ERR_UNCOR_SEVER`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L798) at 0x0c carry the same bits, as their comments say, and the clears of the next subsection read the severity word to tell fatal errors from non-fatal ones. The correctable group, from [`PCI_ERR_COR_STATUS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L800), and the control register follow.

```c
/* include/uapi/linux/pci_regs.h:800 */
#define PCI_ERR_COR_STATUS	0x10	/* Correctable Error Status */
#define  PCI_ERR_COR_RCVR	0x00000001	/* Receiver Error Status */
#define  PCI_ERR_COR_BAD_TLP	0x00000040	/* Bad TLP Status */
#define  PCI_ERR_COR_BAD_DLLP	0x00000080	/* Bad DLLP Status */
#define  PCI_ERR_COR_REP_ROLL	0x00000100	/* REPLAY_NUM Rollover */
#define  PCI_ERR_COR_REP_TIMER	0x00001000	/* Replay Timer Timeout */
#define  PCI_ERR_COR_ADV_NFAT	0x00002000	/* Advisory Non-Fatal */
#define  PCI_ERR_COR_INTERNAL	0x00004000	/* Corrected Internal */
#define  PCI_ERR_COR_LOG_OVER	0x00008000	/* Header Log Overflow */
#define PCI_ERR_COR_MASK	0x14	/* Correctable Error Mask */
	/* Same bits as above */
#define PCI_ERR_CAP		0x18	/* Advanced Error Capabilities & Ctrl*/
```

[`PCI_ERR_COR_STATUS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L800) at 0x10 records correctable errors, [`PCI_ERR_COR_MASK`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L809) at 0x14 masks them with the same bits, and [`PCI_ERR_CAP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L811) at 0x18 is the Advanced Error Capabilities and Control register, which the ECRC subsection reads bit by bit. The clear that empties both status registers is [`pci_aer_raw_clear_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L308); read it with its comment.

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

The function tests only that the capability exists, then clears the Root Error Status register at [`PCI_ERR_ROOT_STATUS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L826) on a Root Port or an RCEC, and the Correctable and Uncorrectable Error Status registers on every function, each by writing back the value just read. Its comment says it clears whether firmware or the OS owns the registers, and the message of commit [20e15e673b05](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=20e15e673b05a045fdbe534d40edf948e1b0b1af) ("PCI/AER: Add pci_aer_raw_clear_status() to unconditionally clear Error Status") attributes that to the SFI _OSC and DPC Updates ECN, which the commit states expects the OS to clear AER status even without ownership. The setup calls the native version, [`pci_aer_clear_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L333), which adds the ownership test.

```c
/* drivers/pci/pcie/aer.c:333 */
int pci_aer_clear_status(struct pci_dev *dev)
{
	if (!pcie_aer_is_native(dev))
		return -EIO;

	return pci_aer_raw_clear_status(dev);
}
```

With [`pcie_aer_is_native()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L242) false the function returns -EIO and writes nothing, so a function below a firmware-owned host bridge keeps its status bits through enumeration. Its three callers at v7.2 are [`pci_aer_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L385), [`pci_restore_state()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L1826) and the AER service's [`clear_status_iter()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1513), which a later subsection shows; [`pci_aer_raw_clear_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L308) has [`pci_aer_clear_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L333), the DPC surprise-removal handler and the EDR handler as its callers. With [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28) unset, inline stubs in drivers/pci/pci.h return -EINVAL for both.

### Severity splits the uncorrectable status between two clears

An uncorrectable error is classed fatal or non-fatal per error type, and the kernel's error paths clear the two classes separately, so a path can clear the class it handled and leave the other set. The Uncorrectable Error Severity register makes the split per error type: a bit set in [`PCI_ERR_UNCOR_SEVER`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L798) classes that error as fatal. Two exported clears use it, and the figure shows the word each one writes for the same register contents, beside the raw clear of the previous subsection.

```text
    Severity divides one Uncorrectable Error Status word between the clears
    ────────────────────────────────────────────────────────────────────────
    example: three errors recorded, the Severity register marking Malformed TLP fatal

                                  bit 20      bit 18      bit 14    other bits
                                  UNSUP      MALF_TLP   COMP_TIME
                              ┌───────────┬───────────┬───────────┬───────────┐
    PCI_ERR_UNCOR_STATUS      │     1     │     1     │     1     │     0     │  read
                              ├───────────┼───────────┼───────────┼───────────┤
    PCI_ERR_UNCOR_SEVER       │     0     │     1     │     0     │   0 or 1  │  read
                              ╞═══════════╪═══════════╪═══════════╪═══════════╡
    ➊ status                  │     1     │     1     │     1     │     0     │  written: every set bit clears
                              ├───────────┼───────────┼───────────┼───────────┤
    ➋ status & ~sev           │     1     │     0     │     1     │     0     │  written: the non-fatal bits clear
                              ├───────────┼───────────┼───────────┼───────────┤
    ➌ status & sev            │     0     │     1     │     0     │     0     │  written: the fatal bit clears
                              └───────────┴───────────┴───────────┴───────────┘

    ➊ pci_aer_raw_clear_status       aer.c:328  writes back the whole status word it read
    ➋ pci_aer_clear_nonfatal_status  :275       keeps the bits the severity word leaves non-fatal
    ➌ pci_aer_clear_fatal_status     :294       keeps the bits the severity word marks fatal
```

➊ [`pci_aer_raw_clear_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L308) writes back the whole status word it read, so every set bit clears. ➋ [`pci_aer_clear_nonfatal_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L264) writes the status word with the severity bits removed, so only the non-fatal errors clear. ➌ [`pci_aer_clear_fatal_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L283) writes the status word masked by the severity bits, so only the fatal errors clear. The two functions differ in one line and in their return type; read them together.

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

Both return before any access when [`pcie_aer_is_native()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L242) is false, the non-fatal clear with -EIO and the fatal clear silently, and both skip the write when no bit of their class is set. The non-fatal clear is exported to modules and declared in include/linux/aer.h, with an inline stub returning -EINVAL when [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28) is unset, while the fatal clear is declared only in drivers/pci/pci.h. [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) calls the non-fatal clear after a successful recovery, and the DPC handler calls both when a containment event was triggered by an uncorrectable error, as the subsection on the error handlers shows. Outside drivers/pci/, two drivers call the non-fatal clear at v7.2 and none calls the fatal one.

### Device Status clears only its four error bits

Besides the AER registers, every PCIe function records the classes of error it detected in the Device Status register of its PCI Express capability, whether or not it has an AER capability. The error handlers clear those bits after an error together with the AER status, and since v7.1 the clear touches nothing else in the register. The four bits are defined with the register offset [`PCI_EXP_DEVSTA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L537); read them with the two read-only bits that follow.

```c
/* include/uapi/linux/pci_regs.h:537 */
#define PCI_EXP_DEVSTA		0x0a	/* Device Status */
#define  PCI_EXP_DEVSTA_CED	0x0001	/* Correctable Error Detected */
#define  PCI_EXP_DEVSTA_NFED	0x0002	/* Non-Fatal Error Detected */
#define  PCI_EXP_DEVSTA_FED	0x0004	/* Fatal Error Detected */
#define  PCI_EXP_DEVSTA_URD	0x0008	/* Unsupported Request Detected */
#define  PCI_EXP_DEVSTA_AUXPD	0x0010	/* AUX Power Detected */
#define  PCI_EXP_DEVSTA_TRPND	0x0020	/* Transactions Pending */
```

[`PCI_EXP_DEVSTA_CED`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L538), [`PCI_EXP_DEVSTA_NFED`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L539), [`PCI_EXP_DEVSTA_FED`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L540) and [`PCI_EXP_DEVSTA_URD`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L541) record a correctable, non-fatal, fatal and unsupported-request error, and [`PCI_EXP_DEVSTA_AUXPD`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L542) and [`PCI_EXP_DEVSTA_TRPND`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L543) report power and pending transactions. Bit 6 has no macro in pci_regs.h. [`pcie_clear_device_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2240) writes the four error bits as ones and every other bit as zero.

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

The function has no ownership test of its own, so each caller decides whether it may write, and it is compiled only with [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28) although the register is not an AER register. Up to v7.0 it read the register and wrote the value back, which also cleared any other RW1C bit that happened to be set. commit [a8aeea1bf3c8](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=a8aeea1bf3c80cc87983689e0118770e019bd4f3) ("PCI/AER: Clear only error bits in PCIe Device Status") narrowed the write to the four error bits, and its message names the bit the old write disturbed, Emergency Power Reduction Detected at bit 6, and the reserved bits the old write could set. The figure shows the two writes against the same register contents.

```text
    The word written to Device Status before and after commit a8aeea1bf3c8
    ──────────────────────────────────────────────────────────────────────

                              15:7      6       5       4      3     2     1      0
                            reserved   EPRD   TRPND   AUXPD   URD   FED   NFED   CED
                          ┌──────────┬──────┬───────┬───────┬─────┬─────┬──────┬─────┐
    Device Status         │    0     │  1   │   0   │   1   │  0  │  0  │  0   │  1  │  read: CED, AUXPD and EPRD set
                          ╞══════════╪══════╪═══════╪═══════╪═════╪═════╪══════╪═════╡
    written up to v7.0    │ as read  │  1   │   0   │   1   │  0  │  0  │  0   │  1  │  the value read: EPRD clears
                          ├──────────┼──────┼───────┼───────┼─────┼─────┼──────┼─────┤
    written at v7.2       │    0     │  0   │   0   │   0   │  1  │  1  │  1   │  1  │  the four error bits only
                          ╞══════════╪══════╪═══════╪═══════╪═════╪═════╪══════╪═════╡
    after the v7.2 write  │    0     │  1   │   0   │   1   │  0  │  0  │  0   │  0  │  EPRD survives
                          └──────────┴──────┴───────┴───────┴─────┴─────┴──────┴─────┘

    EPRD = Emergency Power Reduction Detected, RW1C, no macro; TRPND and AUXPD are read-only
    a 1 written to an RW1C bit clears it, a 0 leaves it; the v7.2 word writes 0 to the reserved bits
```

The register keeps its Emergency Power Reduction Detected bit through the v7.2 clear, and the reserved bits receive zeros. The four callers at v7.2 are the correctable-error branch of the AER service, [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210), the AER service's probe-time [`clear_status_iter()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1513) and the EDR handler; the AER service's own probe of a Root Port still clears the port's Device Status by writing back the value read, as the subsection on the error handlers shows.

### Device Control enables reporting under native ownership

Device Control carries one error reporting enable per class of error, and the AER service of the Root Port treats a function whose enables are all clear as one that does not report errors. Two writers can set them during enumeration: the firmware's _HPX settings, applied while the function is configured, and [`pci_aer_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L385), which sets them only where the kernel owns AER. The enables are four bits of [`PCI_EXP_DEVCTL`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L512); read them with the register offset.

```c
/* include/uapi/linux/pci_regs.h:512 */
#define PCI_EXP_DEVCTL		0x08	/* Device Control */
#define  PCI_EXP_DEVCTL_CERE	0x0001	/* Correctable Error Reporting En. */
#define  PCI_EXP_DEVCTL_NFERE	0x0002	/* Non-Fatal Error Reporting Enable */
#define  PCI_EXP_DEVCTL_FERE	0x0004	/* Fatal Error Reporting Enable */
#define  PCI_EXP_DEVCTL_URRE	0x0008	/* Unsupported Request Reporting En. */
```

The four bits are [`PCI_EXP_DEVCTL_CERE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L513) for correctable errors, [`PCI_EXP_DEVCTL_NFERE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L514) for non-fatal ones, [`PCI_EXP_DEVCTL_FERE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L515) for fatal ones and [`PCI_EXP_DEVCTL_URRE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L516) for unsupported requests. The PCI core groups them in one mask, [`PCI_EXP_AER_FLAGS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L108), the value every user of the enables reads or writes.

```c
/* drivers/pci/pci.h:108 */
#define PCI_EXP_AER_FLAGS	(PCI_EXP_DEVCTL_CERE | PCI_EXP_DEVCTL_NFERE | \
				 PCI_EXP_DEVCTL_FERE | PCI_EXP_DEVCTL_URRE)
```

Apart from this definition and a comment in the _HPX code, drivers/pci/ at v7.2 spells the four bits only through the mask: the setup sets it, the _HPX code confines firmware writes to it, and the AER service tests it. [`pci_enable_pcie_error_reporting()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L253) is the setter, static to aer.c since commit [7ec4b34be423](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=7ec4b34be4234599cf1241ef807cdb7c3636f6fe) ("PCI/AER: Unexport pci_enable_pcie_error_reporting()").

```c
/* drivers/pci/pcie/aer.c:253 */
static int pci_enable_pcie_error_reporting(struct pci_dev *dev)
{
	int rc;

	if (!pcie_aer_is_native(dev))
		return -EIO;

	rc = pcie_capability_set_word(dev, PCI_EXP_DEVCTL, PCI_EXP_AER_FLAGS);
	return pcibios_err_to_errno(rc);
}
```

The function refuses a function the kernel does not own with -EIO, and otherwise ORs the mask into Device Control and converts the accessor's PCIBIOS code into an errno. [`pcie_capability_set_word()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L1387) passes an empty clear mask to the clear-and-set accessor of the PCI Express capability, so it sets bits and clears none.

```c
/* include/linux/pci.h:1387 */
static inline int pcie_capability_set_word(struct pci_dev *dev, int pos,
					   u16 set)
{
	return pcie_capability_clear_and_set_word(dev, pos, 0, set);
}
```

The setup therefore never clears a bit that firmware set. The PCI core once offered drivers the opposite operation, `pci_disable_pcie_error_reporting()`, which no longer exists in the tree: commit [69b264df8a41](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=69b264df8a412820e98867dbab871c6526c5e5aa) ("PCI/AER: Drop unused pci_disable_pcie_error_reporting()") removed it because it had no callers. The firmware path runs earlier, from [`pci_configure_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2452), whose last step applies the _HPX settings of the function.

```c
/* drivers/pci/probe.c:2452 */
static void pci_configure_device(struct pci_dev *dev)
{
	pci_configure_mps(dev);
	pci_configure_extended_tags(dev, NULL);
	pci_configure_relaxed_ordering(dev);
	pci_configure_ltr(dev);
	pci_configure_aspm_l1ss(dev);
	pci_configure_eetlp_prefix(dev);
	pci_configure_serr(dev);
	pci_configure_rcb(dev);

	pci_acpi_program_hp_params(dev);
}
```

[`pci_acpi_program_hp_params()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-acpi.c#L762) at [`probe.c:2463`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2463) evaluates the _HPX method of the nearest bridge above the function that has one, and [`acpi_run_hpx()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-acpi.c#L641) hands a Type 2 record to [`program_hpx_type2()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-acpi.c#L296) at [`pci-acpi.c:697`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-acpi.c#L697). Read that function up to its Device Control write.

```c
/* drivers/pci/pci-acpi.c:296 */
static void program_hpx_type2(struct pci_dev *dev, struct hpx_type2 *hpx)
{
	int pos;
	u32 reg32;
	const struct pci_host_bridge *host;

	if (!hpx)
		return;

	if (!pci_is_pcie(dev))
		return;

	host = pci_find_host_bridge(dev->bus);

	/*
	 * Only do the _HPX Type 2 programming if OS owns PCIe native
	 * hotplug but not AER.
	 */
	if (!host->native_pcie_hotplug || host->native_aer)
		return;

	if (hpx->revision > 1) {
		pci_warn(dev, "PCIe settings rev %d not supported\n",
			 hpx->revision);
		return;
	}

	/*
	 * We only allow _HPX to program DEVCTL bits related to AER, namely
	 * PCI_EXP_DEVCTL_CERE, PCI_EXP_DEVCTL_NFERE, PCI_EXP_DEVCTL_FERE,
	 * and PCI_EXP_DEVCTL_URRE.
	 *
	 * The rest of DEVCTL is managed by the OS to make sure it's
	 * consistent with the rest of the platform.
	 */
	hpx->pci_exp_devctl_and |= ~PCI_EXP_AER_FLAGS;
	hpx->pci_exp_devctl_or &= PCI_EXP_AER_FLAGS;

	/* Initialize Device Control Register */
	pcie_capability_clear_and_set_word(dev, PCI_EXP_DEVCTL,
			~hpx->pci_exp_devctl_and, hpx->pci_exp_devctl_or);
```

The comment states the rule: _HPX Type 2 is applied only where the OS owns PCIe native hotplug and not AER, and of Device Control only the four bits in [`PCI_EXP_AER_FLAGS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L108) may change, the AND mask being widened and the OR mask narrowed to them before the write. The same function then programs the AER registers from the record, under the same ownership condition; read [`program_hpx_type2()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-acpi.c#L296) again for that stage.

```c
/* drivers/pci/pci-acpi.c:296 */
static void program_hpx_type2(struct pci_dev *dev, struct hpx_type2 *hpx)
{
	int pos;
	u32 reg32;
	const struct pci_host_bridge *host;
	... /* 46 lines, to :347 */
	/* Find Advanced Error Reporting Enhanced Capability */
	pos = pci_find_ext_capability(dev, PCI_EXT_CAP_ID_ERR);
	if (!pos)
		return;

	/* Initialize Uncorrectable Error Mask Register */
	pci_read_config_dword(dev, pos + PCI_ERR_UNCOR_MASK, &reg32);
	reg32 = (reg32 & hpx->unc_err_mask_and) | hpx->unc_err_mask_or;
	pci_write_config_dword(dev, pos + PCI_ERR_UNCOR_MASK, reg32);

	/* Initialize Uncorrectable Error Severity Register */
	pci_read_config_dword(dev, pos + PCI_ERR_UNCOR_SEVER, &reg32);
	reg32 = (reg32 & hpx->unc_err_sever_and) | hpx->unc_err_sever_or;
	pci_write_config_dword(dev, pos + PCI_ERR_UNCOR_SEVER, reg32);

	/* Initialize Correctable Error Mask Register */
	pci_read_config_dword(dev, pos + PCI_ERR_COR_MASK, &reg32);
	reg32 = (reg32 & hpx->cor_err_mask_and) | hpx->cor_err_mask_or;
	pci_write_config_dword(dev, pos + PCI_ERR_COR_MASK, reg32);

	/* Initialize Advanced Error Capabilities and Control Register */
	pci_read_config_dword(dev, pos + PCI_ERR_CAP, &reg32);
	reg32 = (reg32 & hpx->adv_err_cap_and) | hpx->adv_err_cap_or;

	/* Don't enable ECRC generation or checking if unsupported */
	if (!(reg32 & PCI_ERR_CAP_ECRC_GENC))
		reg32 &= ~PCI_ERR_CAP_ECRC_GENE;
	if (!(reg32 & PCI_ERR_CAP_ECRC_CHKC))
		reg32 &= ~PCI_ERR_CAP_ECRC_CHKE;
	pci_write_config_dword(dev, pos + PCI_ERR_CAP, reg32);
```

Each of the mask, severity and control registers is read, ANDed and ORed with the firmware's values and written back, and the ECRC enables are dropped where the function lacks the matching capability, the same guard [`enable_ecrc_checking()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L163) applies. On that path the registers start out with the values firmware chose, before [`pci_aer_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L385) runs. The figure puts the two writers of the reporting enables in the order the scan runs them.

```text
    Who sets the four reporting enables in Device Control, and when
    ──────────────────────────────────────────────────────────────

                                        15:4             3      2       1      0
                                                        URRE   FERE   NFERE   CERE
                            ┌─────────────────────────┬──────┬──────┬───────┬──────┐
    as the scan finds it    │       other fields      │  ?   │  ?   │   ?   │  ?   │  reset or firmware values
                            ├─────────────────────────┼──────┼──────┼───────┼──────┤
    _HPX Type 2             │        unchanged        │ AND  │ AND  │  AND  │ AND  │  OS hotplug, firmware AER:
                            │                         │  OR  │  OR  │   OR  │  OR  │  masks kept to bits 3:0
                            ├─────────────────────────┼──────┼──────┼───────┼──────┤
    pci_aer_init            │        unchanged        │  1   │  1   │   1   │  1   │  native and available:
                            │                         │      │      │       │      │  PCI_EXP_AER_FLAGS ORed in
                            └─────────────────────────┴──────┴──────┴───────┴──────┘

    time runs down the rows: pci_configure_device() runs _HPX, then pci_init_capabilities() runs pci_aer_init()
    _HPX Type 2 needs native_aer at 0, the enable native_aer at 1 or pcie_ports=native: both run only with that option
```

The enables matter again after enumeration, because the AER service reads them to decide whether a function took part in error reporting. [`is_error_source()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1015) runs when a Root Port reports an error whose source it cannot name, and its stage below skips a function whose four enables are all clear.

```c
/* drivers/pci/pcie/aer.c:1015 */
static bool is_error_source(struct pci_dev *dev, struct aer_err_info *e_info)
{
	int aer = dev->aer_cap;
	u32 status, mask;
	u16 reg16;
	... /* 25 lines, to :1045 */
	/* Check if AER is enabled */
	pcie_capability_read_word(dev, PCI_EXP_DEVCTL, &reg16);
	if (!(reg16 & PCI_EXP_AER_FLAGS))
		return false;
```

A function that [`pci_enable_pcie_error_reporting()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L253) never touched, because the kernel does not own it or because [`pci_aer_available()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L138) was false, is therefore never searched for the source of such an error. [`clear_status_iter()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1513) applies the same test when the AER service binds, and the subsection on the error handlers shows it.

### The ECRC policy chosen at boot is applied per function

ECRC is the transaction-layer end-to-end CRC, as the help text of [`CONFIG_PCIE_ECRC`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L55) calls it, and four bits of the AER control register say whether a function can generate and check it and whether it does. The kernel leaves those bits as firmware programmed them unless the user asks otherwise with pci=ecrc=, and then changes them only on functions it owns. The policy code is compiled only with that option, which the page assumes unset; read [`ecrc_policy`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L149) and the names of its values first.

```c
/* drivers/pci/pcie/aer.c:143 */
#ifdef CONFIG_PCIE_ECRC

#define ECRC_POLICY_DEFAULT 0		/* ECRC set by BIOS */
#define ECRC_POLICY_OFF     1		/* ECRC off for performance */
#define ECRC_POLICY_ON      2		/* ECRC on for data integrity */

static int ecrc_policy = ECRC_POLICY_DEFAULT;

static const char * const ecrc_policy_str[] = {
	[ECRC_POLICY_DEFAULT] = "bios",
	[ECRC_POLICY_OFF] = "off",
	[ECRC_POLICY_ON] = "on"
};
```

[`ecrc_policy`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L149) holds one of three values for the whole boot, starting at [`ECRC_POLICY_DEFAULT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L145), which leaves firmware's settings alone. [`ECRC_POLICY_OFF`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L146) and [`ECRC_POLICY_ON`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L147) are named for performance and data integrity in their comments, and [`ecrc_policy_str`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L151) maps each value to the word the option takes. [`pci_setup()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L6743) passes the text after pci=ecrc= to [`pcie_ecrc_get_policy()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L230); read the opening of the parser again with the ecrc line.

```c
/* drivers/pci/pci.c:6743 */
static int __init pci_setup(char *str)
{
	while (str) {
		char *k = strchr(str, ',');
		if (k)
			*k++ = 0;
		if (*str && (str = pcibios_setup(str)) && *str) {
				... /* 22 lines, to :6772 */
				resource_alignment_param = str + 19;
			} else if (!strncmp(str, "ecrc=", 5)) {
				pcie_ecrc_get_policy(str + 5);
```

The parser strips the option's prefix and hands the rest over unchanged. [`pcie_ecrc_get_policy()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L230) matches it against the names.

```c
/* drivers/pci/pcie/aer.c:226 */
/**
 * pcie_ecrc_get_policy - parse kernel command-line ecrc option
 * @str: ECRC policy from kernel command line to use
 */
void pcie_ecrc_get_policy(char *str)
{
	int i;

	i = match_string(ecrc_policy_str, ARRAY_SIZE(ecrc_policy_str), str);
	if (i < 0)
		return;

	ecrc_policy = i;
}
#endif	/* CONFIG_PCIE_ECRC */
```

A word that names no policy leaves [`ecrc_policy`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L149) as it was, and a later pci=ecrc= on the same command line overrides an earlier one, because [`pci_setup()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L6743) handles the values in order. With [`CONFIG_PCIE_ECRC`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L55) unset, as assumed here, the call in [`pci_setup()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L6743) reaches the empty inline stub at [`drivers/pci/pci.h:1119`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L1119), so the option is accepted and ignored; read the block of drivers/pci/pci.h that chooses between the declarations and the stubs.

```c
/* drivers/pci/pci.h:1114 */
#ifdef CONFIG_PCIE_ECRC
void pcie_set_ecrc_checking(struct pci_dev *dev);
void pcie_ecrc_get_policy(char *str);
#else
static inline void pcie_set_ecrc_checking(struct pci_dev *dev) { }
static inline void pcie_ecrc_get_policy(char *str) { }
#endif
```

The same stub replaces [`pcie_set_ecrc_checking()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L207), the per-function step that [`pci_aer_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L385) calls last. Its policy values and transitions are the state graph below.

```text
    The ECRC policy: one value per boot, set while the command line is parsed
    ─────────────────────────────────────────────────────────────────────────

                         ┌─────────────────────────────────┐
         initial ───────▶│ ECRC_POLICY_DEFAULT   "bios"    │
                         └───────┬─────────────────┬───────┘
                   pci=ecrc=off  │                 │  pci=ecrc=on
                                 ▼                 ▼
          ┌──────────────────────────────┐   ┌──────────────────────────────┐
          │ ECRC_POLICY_OFF   "off"      │◀─▶│ ECRC_POLICY_ON   "on"        │
          └──────────────────────────────┘   └──────────────────────────────┘
           pcie_set_ecrc_checking():          pcie_set_ecrc_checking():
           GENE and CHKE cleared              GENE set where GENC is set,
                                              CHKE set where CHKC is set

    DEFAULT: pcie_set_ecrc_checking() leaves PCI_ERR_CAP as firmware programmed it
    a later pci=ecrc= option overrides an earlier one, pci=ecrc=bios returns to DEFAULT,
    and a string that names no policy leaves the value as it was
```

The policy is fixed once the command line is parsed, and the table names what each value then does to every function the kernel owns.

| Policy | Word after pci=ecrc= | Effect on a function the kernel owns |
|---|---|---|
| [`ECRC_POLICY_DEFAULT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L145) | bios, or no option | none: [`pcie_set_ecrc_checking()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L207) returns |
| [`ECRC_POLICY_OFF`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L146) | off | [`disable_ecrc_checking()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L187) clears both ECRC enables |
| [`ECRC_POLICY_ON`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L147) | on | [`enable_ecrc_checking()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L163) sets each enable whose capability bit is set |

With [`CONFIG_PCIE_ECRC`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L55) set, [`pcie_set_ecrc_checking()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L207) first tests ownership, since commit [bba5065963f8](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=bba5065963f8ade14f3caa5b0f5b4a53d3054dfd) ("PCI/AER: Configure ECRC only if AER is native"), whose message gives the reason that the ECRC bits are part of the AER registers.

```c
/* drivers/pci/pcie/aer.c:202 */
/**
 * pcie_set_ecrc_checking - set/unset PCIe ECRC checking for a device based
 * on global policy
 * @dev: the PCI device
 */
void pcie_set_ecrc_checking(struct pci_dev *dev)
{
	if (!pcie_aer_is_native(dev))
		return;

	switch (ecrc_policy) {
	case ECRC_POLICY_DEFAULT:
		return;
	case ECRC_POLICY_OFF:
		disable_ecrc_checking(dev);
		break;
	case ECRC_POLICY_ON:
		enable_ecrc_checking(dev);
		break;
	default:
		return;
	}
}
```

The switch selects one of the two writers below, and the default policy and any unknown value return without an access. The two writers act on the control register at [`PCI_ERR_CAP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L811), whose ECRC bits are defined just below it.

```c
/* include/uapi/linux/pci_regs.h:811 */
#define PCI_ERR_CAP		0x18	/* Advanced Error Capabilities & Ctrl*/
#define  PCI_ERR_CAP_FEP(x)	((x) & 0x1f)	/* First Error Pointer */
#define  PCI_ERR_CAP_ECRC_GENC		0x00000020 /* ECRC Generation Capable */
#define  PCI_ERR_CAP_ECRC_GENE		0x00000040 /* ECRC Generation Enable */
#define  PCI_ERR_CAP_ECRC_CHKC		0x00000080 /* ECRC Check Capable */
#define  PCI_ERR_CAP_ECRC_CHKE		0x00000100 /* ECRC Check Enable */
```

Each enable bit is the bit just above its capability bit: generation capable [`PCI_ERR_CAP_ECRC_GENC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L813) and enable [`PCI_ERR_CAP_ECRC_GENE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L814), check capable [`PCI_ERR_CAP_ECRC_CHKC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L815) and enable [`PCI_ERR_CAP_ECRC_CHKE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L816). [`enable_ecrc_checking()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L163) sets an enable only where the function reports the capability.

```c
/* drivers/pci/pcie/aer.c:157 */
/**
 * enable_ecrc_checking - enable PCIe ECRC checking for a device
 * @dev: the PCI device
 *
 * Return: 0 on success, or negative on failure.
 */
static int enable_ecrc_checking(struct pci_dev *dev)
{
	int aer = dev->aer_cap;
	u32 reg32;

	if (!aer)
		return -ENODEV;

	pci_read_config_dword(dev, aer + PCI_ERR_CAP, &reg32);
	if (reg32 & PCI_ERR_CAP_ECRC_GENC)
		reg32 |= PCI_ERR_CAP_ECRC_GENE;
	if (reg32 & PCI_ERR_CAP_ECRC_CHKC)
		reg32 |= PCI_ERR_CAP_ECRC_CHKE;
	pci_write_config_dword(dev, aer + PCI_ERR_CAP, reg32);

	return 0;
}
```

A function that can generate ECRC but not check it gets generation alone, and the register's other bits are written back as read. [`disable_ecrc_checking()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L187) clears both enables without looking at the capability bits.

```c
/* drivers/pci/pcie/aer.c:181 */
/**
 * disable_ecrc_checking - disable PCIe ECRC checking for a device
 * @dev: the PCI device
 *
 * Return: 0 on success, or negative on failure.
 */
static int disable_ecrc_checking(struct pci_dev *dev)
{
	int aer = dev->aer_cap;
	u32 reg32;

	if (!aer)
		return -ENODEV;

	pci_read_config_dword(dev, aer + PCI_ERR_CAP, &reg32);
	reg32 &= ~(PCI_ERR_CAP_ECRC_GENE | PCI_ERR_CAP_ECRC_CHKE);
	pci_write_config_dword(dev, aer + PCI_ERR_CAP, reg32);

	return 0;
}
```

Both writers return -ENODEV for a function without the capability, which cannot reach them through [`pcie_set_ecrc_checking()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L207) because the ownership test already failed for it. Firmware's own ECRC settings stay in force under the default policy, and the save and restore of the next subsection carry whichever value the register holds across a reset.

### Save and restore carry the AER controls across a reset

A function can lose its configuration across a reset or a suspend, and with it the masks, severities and ECRC enables that firmware, _HPX or the kernel chose; the message of commit [af65d1ad416b](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=af65d1ad416bc6e069ccb9e649faeda224248f96) ("PCI/AER: Save AER Capability for suspend/resume") gives that loss after resume as the reason the AER registers are saved. The PCI core saves a function's configuration before such an event and restores it afterwards, and the AER capability takes part through the save slot the setup reserved. The figure shows which register lands in which dword of the slot.

```text
    The AER save slot: which register lands in which dword, in the order restore writes them back
    ─────────────────────────────────────────────────────────────────────────────────────────────

    AER capability at aer_cap                             save slot: struct pci_cap_saved_state,
                                                          cap_nr = PCI_EXT_CAP_ID_ERR
    ┌──────────────────────────────────────────┐          ┌──────────────────────────────────────────┐
    │ +0x04 Uncorrectable Error Status         │          │                                          │
    │ +0x08 Uncorrectable Error Mask           ├─────────▶│ cap.data[0]                              │
    │ +0x0c Uncorrectable Error Severity       ├─────────▶│ cap.data[1]                              │
    │ +0x10 Correctable Error Status           │          │                                          │
    │ +0x14 Correctable Error Mask             ├─────────▶│ cap.data[2]                              │
    │ +0x18 Adv. Error Capabilities/Control    ├─────────▶│ cap.data[3]                              │
    │ +0x2c Root Error Command                 ├─ ─ ─ ─ ─▶│ cap.data[4], Root Port and RCEC only     │
    └──────────────────────────────────────────┘          └──────────────────────────────────────────┘

    save copies along the arrows; restore clears both Status registers first, then copies back against them
    slot size: five dwords where pcie_cap_has_rtctl() is true, four otherwise
```

Only the control registers are kept; the two status registers are not saved, and the restore clears them instead. Both directions first look up the slot by capability ID with [`pci_find_saved_ext_cap()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L1637); read it with [`_pci_find_saved_cap()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L1620), the search it wraps.

```c
/* drivers/pci/pci.c:1620 */
static struct pci_cap_saved_state *_pci_find_saved_cap(struct pci_dev *pci_dev,
						       u16 cap, bool extended)
{
	struct pci_cap_saved_state *tmp;

	hlist_for_each_entry(tmp, &pci_dev->saved_cap_space, next) {
		if (tmp->cap.cap_extended == extended && tmp->cap.cap_nr == cap)
			return tmp;
	}
	return NULL;
}

struct pci_cap_saved_state *pci_find_saved_cap(struct pci_dev *dev, char cap)
{
	return _pci_find_saved_cap(dev, cap, false);
}

struct pci_cap_saved_state *pci_find_saved_ext_cap(struct pci_dev *dev, u16 cap)
{
	return _pci_find_saved_cap(dev, cap, true);
}
```

The search goes through the function's list of saved states and matches the ID and the extended flag, returning NULL when the setup never allocated a slot. [`pci_save_aer_state()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L341) fills the slot in the order of the figure.

```c
/* drivers/pci/pcie/aer.c:341 */
void pci_save_aer_state(struct pci_dev *dev)
{
	int aer = dev->aer_cap;
	struct pci_cap_saved_state *save_state;
	u32 *cap;

	if (!aer)
		return;

	save_state = pci_find_saved_ext_cap(dev, PCI_EXT_CAP_ID_ERR);
	if (!save_state)
		return;

	cap = &save_state->cap.data[0];
	pci_read_config_dword(dev, aer + PCI_ERR_UNCOR_MASK, cap++);
	pci_read_config_dword(dev, aer + PCI_ERR_UNCOR_SEVER, cap++);
	pci_read_config_dword(dev, aer + PCI_ERR_COR_MASK, cap++);
	pci_read_config_dword(dev, aer + PCI_ERR_CAP, cap++);
	if (pcie_cap_has_rtctl(dev))
		pci_read_config_dword(dev, aer + PCI_ERR_ROOT_COMMAND, cap++);
}
```

The save reads the four registers every AER function has, and the Root Error Command register when [`pcie_cap_has_rtctl()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/access.c#L378) says the function is a Root Port or an RCEC, matching the size the setup chose. It has no ownership test: reading the registers changes nothing, and a function below a firmware-owned host bridge gets its firmware values saved. Its one caller is [`pci_save_state()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L1747), the PCI core's general save; read the stage up to the AER call.

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
```

The configuration header is saved first, with a dynamic-debug message per dword, then the PCI Express capability, and the AER registers after Downstream Port Containment's. A failure to save the PCI Express capability returns before the AER save, which then does not run. [`pci_restore_aer_state()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L363) is the mirror image.

```c
/* drivers/pci/pcie/aer.c:363 */
void pci_restore_aer_state(struct pci_dev *dev)
{
	int aer = dev->aer_cap;
	struct pci_cap_saved_state *save_state;
	u32 *cap;

	if (!aer)
		return;

	save_state = pci_find_saved_ext_cap(dev, PCI_EXT_CAP_ID_ERR);
	if (!save_state)
		return;

	cap = &save_state->cap.data[0];
	pci_write_config_dword(dev, aer + PCI_ERR_UNCOR_MASK, *cap++);
	pci_write_config_dword(dev, aer + PCI_ERR_UNCOR_SEVER, *cap++);
	pci_write_config_dword(dev, aer + PCI_ERR_COR_MASK, *cap++);
	pci_write_config_dword(dev, aer + PCI_ERR_CAP, *cap++);
	if (pcie_cap_has_rtctl(dev))
		pci_write_config_dword(dev, aer + PCI_ERR_ROOT_COMMAND, *cap++);
}
```

The restore writes the dwords back in the order the save read them, again without an ownership test, so the values written are the ones the function held when it was saved. Its one caller is [`pci_restore_state()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L1826); read the stage up to the AER calls.

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
```

[`pci_aer_clear_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L333) runs immediately before the restore, so status bits that the reset or the event left behind are cleared, where the kernel owns the function, before the masks and severities are written back. The configuration header follows the AER registers, and MSI state after it. With [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28) unset both AER calls reach empty inline stubs in drivers/pci/pci.h.

So far, a function has its records, cleared status, reporting enables and ECRC policy from the scan, and a save slot that keeps its AER controls across resets, which takes the strip to its fifth column; what remains is the error handling that clears the status again and the release.

### Error handlers clear the status again after each error

The clears at enumeration empty a function's status registers once, but every error the function records afterwards sets bits again, and a bit nobody clears stays set for the next code that reads the register. The handlers of the AER, DPC and EDR paths therefore call the clears of this page once they have dealt with an error, each choosing the clear that matches what it handled and each deciding for itself whether to test ownership. The table lists the error-handling paths in drivers/pci/ that call them at v7.2 and what each clears; the excerpts below show the lines.

| Path | Ownership test before writing | What it clears |
|---|---|---|
| correctable error, [`pci_aer_handle_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1170) | none for the status write, [`pcie_aer_is_native()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L242) for Device Status | the reported Correctable Status bits, then the Device Status error bits |
| recovery, [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) | [`native_aer`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L653) or [`pcie_ports_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L614) | the Device Status error bits, then the non-fatal uncorrectable bits |
| DPC trigger by an uncorrectable error, [`dpc_process_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L264) | the test inside each clear | the non-fatal, then the fatal uncorrectable bits |
| DPC trigger by a surprise removal, [`dpc_handle_surprise_removal()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L328) | none | all AER status, then the Fatal Error Detected bit |
| EDR event, [`edr_handle_event()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/edr.c#L151), with [`CONFIG_PCIE_EDR`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L140) | none | all AER status, and the Device Status error bits after a successful recovery |
| AER service binding to a port, [`clear_status_iter()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1513) | reporting enables set, then the test inside each clear | all AER status and the Device Status error bits of each function below the port |

A correctable error needs no recovery, so the AER service clears it where it handles it. Read the correctable branch of [`pci_aer_handle_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1170).

```c
/* drivers/pci/pcie/aer.c:1170 */
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
```

The branch writes back only the status bits the service read for this error, whatever the ownership, and then, where the kernel owns AER, gives the driver its correctable-error callback and clears the Device Status error bits with [`pcie_clear_device_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2240). Uncorrectable errors go to [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210), whose last step after a successful recovery is the clear; read its opening and that step.

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
	... /* 57 lines, to :275 */
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
```

The recovery tests ownership itself, from the host bridge it looked up at the start and [`pcie_ports_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L614), and the comment states the reason: a platform that kept AER control is responsible for clearing the status, and the device that signaled the error may not even be visible to the OS. The clear at the end is the non-fatal one whichever channel state the recovery started from. With [`CONFIG_PCIE_DPC`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L121) set, as assumed, the DPC service handles a containment event that an uncorrectable error triggered in [`dpc_process_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L264), by logging the error and clearing both kinds of uncorrectable bits.

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

The two clears run only when the DPC code could read the error's severity and details, and each applies its own ownership test. A containment event caused by a surprise removal is handled apart by [`dpc_handle_surprise_removal()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L328), and there the DPC code clears without asking about ownership; read it with [`pci_clear_surpdn_errors()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L312), the helper above it.

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

[`dpc_handle_surprise_removal()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L328) uses the raw clear and then [`pci_clear_surpdn_errors()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L312), whose comment says Surprise Down has been observed to set the Fatal Error Detected bit; the helper writes that one bit of Device Status directly, not through [`pcie_clear_device_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2240). The EDR handler [`edr_handle_event()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/edr.c#L151), built only with [`CONFIG_PCIE_EDR`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L140), which the page assumes unset, runs when firmware notifies the OS of a containment event and also clears without an ownership test.

```c
/* drivers/pci/pcie/edr.c:151 */
static void edr_handle_event(acpi_handle handle, u32 event, void *data)
{
	struct pci_dev *pdev = data, *edev;
	pci_ers_result_t estate = PCI_ERS_RESULT_DISCONNECT;
	u16 status;

	if (event != ACPI_NOTIFY_DISCONNECT_RECOVER)
		return;
	... /* 34 lines, to :193 */
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
```

The message of commit [20e15e673b05](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=20e15e673b05a045fdbe534d40edf948e1b0b1af) states that the raw clear was intended for the EDR path alone, and here the Device Status clear follows only a successful recovery. When the AER service binds to a Root Port or an RCEC, [`aer_enable_rootport()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1533) clears the port and, if the port has recorded error messages, the functions below it; read it up to the loop over those functions.

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
```

The port's own Device Status is cleared by writing back the value read, the form [`pcie_clear_device_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2240) gave up in v7.1. The functions below the port go through [`clear_status_iter()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1513).

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

The iterator skips a function whose reporting enables are clear, which the comment ties to a function the setup has not reached yet, and clears both the AER status and Device Status of the rest, the AER part under ownership. commit [e242d09b58e8](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=e242d09b58e869f86071b7889acace4cff215935) ("PCI/AER: Clear stale errors on reporting agents upon probe") added it so that an error recorded between a function's setup and the service's binding does not surface with the next error.

### Release frees the info block and the save slot

The records a function received at the scan must go when its [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) goes, and that happens when the last reference to the object is dropped, not when the function is removed from its bus. The PCI core's release callback, [`pci_release_dev()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2482), undoes each capability's setup in one place; read its first lines.

```c
/* drivers/pci/probe.c:2482 */
static void pci_release_dev(struct device *dev)
{
	struct pci_dev *pci_dev;

	pci_dev = to_pci_dev(dev);
	pci_release_capabilities(pci_dev);
```

The callback runs from the driver model at the last put of the function's embedded device, and its first call is [`pci_release_capabilities()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2466), whose first step is the AER one. [`pci_aer_exit()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L421) only frees the info block and clears the pointer.

```c
/* drivers/pci/pcie/aer.c:421 */
void pci_aer_exit(struct pci_dev *dev)
{
	kfree(dev->aer_info);
	dev->aer_info = NULL;
}
```

`kfree()` accepts NULL, so a function whose setup returned early, with no capability or no memory, passes through the same two lines, which are ⑧ and ⑨ on the strip. [`aer_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370) keeps its offset, and no register is written: the release clears no status, resets no enable and changes no ECRC bit. The rest of [`pci_release_capabilities()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2466) takes the other capabilities apart.

```c
/* drivers/pci/probe.c:2466 */
static void pci_release_capabilities(struct pci_dev *dev)
{
	pci_aer_exit(dev);
	pci_rcec_exit(dev);
	pci_iov_release(dev);
	pci_free_cap_save_buffers(dev);
}
```

The save slots of every capability are freed last, after the RCEC and SR-IOV state, by [`pci_free_cap_save_buffers()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L3505), which marks ⑩ on the strip.

```c
/* drivers/pci/pci.c:3505 */
void pci_free_cap_save_buffers(struct pci_dev *dev)
{
	struct pci_cap_saved_state *tmp;
	struct hlist_node *n;

	hlist_for_each_entry_safe(tmp, n, &dev->saved_cap_space, next)
		kfree(tmp);
}
```

The loop frees each entry of the list of saved states, so the AER slot goes with the rest, and the strip closes with the info block, the pointer and the slot gone.

### Messages, hand-offs and tracepoints of the setup

Watching the setup means knowing which of its steps leave a trace. The setup itself is silent: none of the functions this page covers prints a message or fires a tracepoint, so its effects show in the registers and in the files of the next subsection. The paths around it leave the traces the table lists, and the debug-level ones are dynamic-debug sites that [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120), assumed set, lets a reader enable through /sys/kernel/debug/dynamic_debug/control; [`CONFIG_PCI_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L70), assumed unset, would print them unconditionally.

| Site | Message | Level | What it tells the reader |
|---|---|---|---|
| [`pci.c:1753`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L1753) | "save config %#04x: %#010x" | debug | the configuration header saved before the AER registers, one dword per line |
| [`pci.c:1783`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L1783) | "restore config %#04x: %#010x -> %#010x" | debug | a header dword that the restore after the AER registers rewrites |
| [`err.c:272`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L272) | "broadcast resume message" | debug | a recovery reached the step after which it clears the status |
| [`err.c:288`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L288) | "device recovery successful" | info | the recovery returned after its clears |
| [`edr.c:210`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/edr.c#L210) | "DPC port successfully recovered" | debug | the EDR handler is about to clear Device Status |
| [`pci-acpi.c:318`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-acpi.c#L318) | "PCIe settings rev %d not supported" | warning | _HPX Type 2 was refused, so firmware's Device Control and AER values were not applied |
| [`pci.c:6804`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L6804) | "PCI: Unknown option `%s'" | error | a pci= value that [`pci_setup()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L6743) did not recognize; noaer and ecrc= are recognized |

The message of [`pci_save_state()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L1747) is the one shown earlier at its dword loop. No tracepoint fires in [`pci_aer_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L385), in the clears, in the save and restore or in the release. The RAS tracepoint aer_event fires where the AER service prints an error, at [`aer.c:879`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L879) and [`aer.c:955`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L955); it reports errors, and no tracepoint reports their clearing.

The setup crosses no asynchronous boundary: it runs in the context that adds the function, the boot-time scan or a hot-add, and the release runs in the context of the last put. The clears after an error run inside the handlers of other services, in the contexts the table lists, and no work item, timer or notifier chain of this page's own carries a clear.

| Caller of the clears | Context | Where the context is set up |
|---|---|---|
| [`pci_aer_handle_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1170), [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) from the AER service | the threaded interrupt handler of the AER service | [`aer.c:1632`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1632) |
| [`dpc_process_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L264), [`dpc_handle_surprise_removal()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L328), [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) from DPC | the threaded interrupt handler of the DPC service | [`dpc.c:483`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L483) |
| [`edr_handle_event()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/edr.c#L151), with [`CONFIG_PCIE_EDR`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L140) | an ACPI notify handler of the port | [`edr.c:231`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/edr.c#L231) |
| [`clear_status_iter()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1513) | the probe of the AER service | [`aer.c:1533`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1533), the function that visits the functions below the port |

The clears themselves leave no trace, so a reader watches the debug sites above and the status registers themselves.

### Boot parameters and sysfs files expose the setup

The state this page sets up is visible from user space only indirectly, through the boot parameters that steer it and the sysfs files that exist because of it. The table lists them with the code that reads or creates them.

| Surface | Path or option | What it shows or changes |
|---|---|---|
| boot parameter | pci=noaer | [`pci_no_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L133) sets [`pcie_aer_disable`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L130), so [`pci_aer_available()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L138) is false: no reporting enables at setup, no AER control requested in _OSC, no Root Port service |
| boot parameter | pci=nomsi | [`pci_no_msi()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/msi/msi.c#L985) clears [`pci_msi_enable`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/msi/msi.c#L18), which makes [`pci_aer_available()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L138) false as well |
| boot parameter | pci=ecrc=bios, off or on | [`pcie_ecrc_get_policy()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L230) sets [`ecrc_policy`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L149) with [`CONFIG_PCIE_ECRC`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L55) set, and nothing without it |
| boot parameter | pcie_ports=native | [`pcie_port_setup()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L622) sets [`pcie_ports_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L614), so [`pcie_aer_is_native()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L242) is 1 for every function with the capability |
| sysfs groups of a function | /sys/bus/pci/devices/DDDD:BB:DD.F/aer_dev_*, aer_rootport_total_*, and the aer/ directory | present only when [`aer_info`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L371) is set, as the visibility test below shows |
| debugfs | none | the setup, the clears and the save and restore have no debugfs file |
| fault injection | the aer_inject module, with [`CONFIG_PCIEAER_INJECT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L37) | assumed unset; [`aer_inject()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer_inject.c#L319) refuses a function whose [`aer_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370) is 0 |

The AER attribute groups of a function decide per file whether it appears, and both tests start from the info block that [`pci_aer_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L385) allocated. Read the group that holds the ratelimit files, from [`aer_ratelimit_attrs`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L712), the macro that generates its four attributes, through [`aer_attrs_are_visible()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L729), its visibility test, to [`aer_attr_group`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L741) itself.

```c
/* drivers/pci/pcie/aer.c:712 */
#define aer_ratelimit_attrs(name)					\
	aer_ratelimit_interval_attr(name##_ratelimit_interval_ms,	\
				    name##_ratelimit)			\
	aer_ratelimit_burst_attr(name##_ratelimit_burst,		\
				 name##_ratelimit)

aer_ratelimit_attrs(correctable)
aer_ratelimit_attrs(nonfatal)

static struct attribute *aer_attrs[] = {
	&dev_attr_correctable_ratelimit_interval_ms.attr,
	&dev_attr_correctable_ratelimit_burst.attr,
	&dev_attr_nonfatal_ratelimit_interval_ms.attr,
	&dev_attr_nonfatal_ratelimit_burst.attr,
	NULL
};

static umode_t aer_attrs_are_visible(struct kobject *kobj,
				     struct attribute *a, int n)
{
	struct device *dev = kobj_to_dev(kobj);
	struct pci_dev *pdev = to_pci_dev(dev);

	if (!pdev->aer_info)
		return 0;

	return a->mode;
}

const struct attribute_group aer_attr_group = {
	.name = "aer",
	.attrs = aer_attrs,
	.is_visible = aer_attrs_are_visible,
};
```

The two invocations of the macro generate an interval file and a burst file for each of the two ratelimits that [`pci_aer_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L385) readied, and [`aer_attrs`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L721) lists the four. A function without a [`struct aer_info`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L60), one with no AER capability or one whose allocation failed, shows no file of the group, and the statistics group applies the same test in [`aer_stats_attrs_are_visible()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L618). Because `device_add()` runs after [`pci_init_capabilities()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2650) in [`pci_device_add()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2726), the test sees the pointer the setup left, and the files of a function with the capability appear together with its sysfs directory.
