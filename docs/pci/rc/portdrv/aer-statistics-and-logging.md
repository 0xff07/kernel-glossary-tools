# AER statistics and logging

> CAUTION: AI-GENERATED CONTENT
>
> STRICTLY DO NOT SUBMIT THIS UPSTREAM UNLESS YOU ARE AN EXPERT INTIMATELY FAMILIAR WITH THIS SUBSYSTEM.

Errors that PCIe functions report through Advanced Error Reporting can arrive in floods, and the kernel needs an exact count of them while the kernel log stays readable. The AER code of the PCIe port driver keeps those counts per function, records the reports it counts in a tracepoint, and prints a report while a per-function limiter allows it. The same counting, limiting and printing serve the AER interrupt of a Root Port or Root Complex Event Collector, a Downstream Port Containment trigger and a report that firmware forwards. This page traces the counters, the limiter, the printed lines, the tracepoint and the sysfs files that expose them, on x86-64 with ACPI.

```text
    The records that carry a report, the object that counts and limits it, and where it shows
    ─────────────────────────────────────────────────────────────────────────────────────────

                                               struct aer_info of one function
    ┌────────────────────────────────┐         ┌───────────────────────────────────┐
    │ struct aer_err_source, one per │ counts  │ rootport_total_cor_errs           │
    │ message the root queued        ├────────▶│ rootport_total_fatal_errs         ├──▶ aer_rootport_total_err_*
    │ status: Root Error Status      │         │ rootport_total_nonfatal_errs      │
    │ id: the two Source IDs         │         │ (read on a Root Port or RCEC)     │
    └───────────────┬────────────────┘         │                                   │
                    │                          │ dev_cor_errs[16]                  │
                    │ one record per class     │ dev_fatal_errs[32]                ├──▶ aer_dev_correctable,
                    ▼                          │ dev_nonfatal_errs[32]             │    aer_dev_fatal, aer_dev_nonfatal
    ┌────────────────────────────────┐         │ dev_total_cor/fatal/nonfatal_errs │
    │ struct aer_err_info            │ counts  │                                   │
    │ severity, status, mask         ├────────▶│                                   │
    │ dev[i]: the functions found    │ limiter │                                   │
    │ ratelimit_print[i]             │◀────────┤ correctable_ratelimit             │◀─▶ aer/correctable_ratelimit_*
    │ root_ratelimit_print           │ sets 1  │ nonfatal_ratelimit                │◀─▶ aer/nonfatal_ratelimit_*
    │ first_error, tlp               │         │   interval, burst, window         │
    │                                │         │                                   │    sysfs files of the function
    └───────────────┬────────────────┘         └───────────────────────────────────┘
                    │
                    │  every report
                    ├───────────────────────▶ tracepoint ras:aer_event
                    │  print flag is 1
                    └───────────────────────▶ kernel log, lines that begin "AER: "
```

## SUMMARY

A function's AER state is a [`struct aer_info`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L60) that [`aer_info`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L371) points at, holding per-bit and total counters, the Root Port totals and two limiters. A report travels in a [`struct aer_err_info`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L833), one record per error class that the interrupt, the DPC trigger or the firmware path fills, and the specification's terms map onto it as the table shows.

| specification term | kernel representation | filled from |
|---|---|---|
| ERR_COR, ERR_NONFATAL or ERR_FATAL Message at the root | [`PCI_ERR_ROOT_COR_RCV`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L827), [`PCI_ERR_ROOT_UNCOR_RCV`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L829) and [`PCI_ERR_ROOT_FATAL_RCV`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L833) in [`status`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L50) | Root Error Status |
| error severity | [`severity`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L841), one of [`AER_CORRECTABLE`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L16), [`AER_NONFATAL`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L14) and [`AER_FATAL`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L15) | the root's message class, or the Uncorrectable Error Severity register on a DPC trigger |
| errors a function detected | [`status`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L851) with [`mask`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L852) | Correctable or Uncorrectable Error Status and Mask |
| Error Source Identification | [`id`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L839) | the root's Error Source ID register |
| First Error Pointer | [`first_error`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L846) | Advanced Error Capabilities and Control |
| Header Log | [`tlp`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L853), valid when [`tlp_header_valid`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L849) is 1 | Header Log and TLP Prefix Log |

On these paths a report is counted and traced first, and a line is printed only when the record's print flag or the limiter allows it. Suppression therefore touches the log alone, and the counters and the trace also see the reports that the limiter holds back.

## SPECIFICATIONS

The registers and message classes are defined by the PCI Express Base Specification, which aer.c and dpc.c name by revision and section in comments, without section titles. The counters, the limiter and the printed format are a kernel synthesis that no specification defines, read here from drivers/pci/pcie/aer.c, drivers/pci/pci.h, include/ras/ras_event.h and kernel/vmcore_info.c.

- PCIe r7.0, sec 6.2.7, cited by [`aer.c:817`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L817) for the errors whose TLP header a function always logs.
- PCIe r6.0, sec 7.8.4.9, cited by [`aer.c:404-409`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L404) for the Root Error Command register that Root Ports and RCECs implement.
- PCIe r6.0, sec 6.7.6, cited by [`dpc.c:366-369`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L366) for the errors that an asynchronous removal causes on a DPC trigger.

## COVERAGE

### Counting

- [`'\<struct aer_info\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L60): the per-function object holding the counters and the two limiters.
- [`'\<pci_dev_aer_stats_incr\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L747): counts one record in a function's total and per-bit counters.
- [`'\<pci_rootport_aer_stats_incr\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L781): counts the message classes a Root Port or RCEC received.
- [`'\<hwerr_log_error_type\>':'kernel/vmcore_info.c'`](https://elixir.bootlin.com/linux/v7.2/source/kernel/vmcore_info.c#L130): records a recoverable hardware error in the array a crash dump reads.

### Limiting

- [`'\<aer_ratelimit\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L800): asks a function's limiter whether a correctable or non-fatal report may print.
- [`'aer_info.correctable_ratelimit'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L95): the limiter state for correctable reports.
- [`'aer_info.nonfatal_ratelimit'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L96): the limiter state for non-fatal reports.
- [`'aer_err_info.ratelimit_print'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L835): per found function, whether its details print.
- [`'aer_err_info.root_ratelimit_print'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L842): whether the root's source line prints.

### Printing and tracing

- [`'\<aer_print_error\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L865): counts, traces and, when the record's flag allows, prints one function's report.
- [`'\<__aer_print_error\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L829): prints one line per unmasked status bit.
- [`'\<aer_print_source\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L852): prints the root's line naming the Source ID it received.
- [`'\<tlp_header_logged\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L815): decides whether the Header Log holds a TLP for the status bits.
- [`'\<aer_err_bus\>':'drivers/pci/pci.h'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L859): the bus-type word a record's lines and trace entry carry.
- [`'\<aer_correctable_error_string\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L477): the name of each Correctable Error Status bit.
- [`'\<aer_uncorrectable_error_string\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L512): the name of each Uncorrectable Error Status bit.
- [`'AER_GET_LAYER_ERROR'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L457): classifies a record's status bits by protocol layer.
- [`'AER_GET_AGENT'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L439): classifies a record's status bits by the agent that detected them.
- [`'trace_aer_event'`](https://elixir.bootlin.com/linux/v7.2/source/include/ras/ras_event.h#L337): the `ras:aer_event` tracepoint a counted record fires.

### sysfs files

- [`'aer_stats_dev_attr'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L554): generates the show function of a per-function counter file.
- [`'aer_stats_rootport_attr'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L591): generates the show function of a Root Port total file.
- [`'\<aer_stats_attrs_are_visible\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L618): hides the counter files where they do not apply.
- [`'\<aer_stats_attr_group\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L637): the attribute group of the counter files.
- [`'aer_ratelimit_interval_attr'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L647): generates the show and store functions of a limiter's interval file.
- [`'aer_ratelimit_burst_attr'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L682): generates the show and store functions of a limiter's burst file.
- [`'\<aer_attrs_are_visible\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L729): hides the limiter files of a function without AER state.
- [`'\<aer_attr_group\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L741): the attribute group of the aer directory and its limiter files.

## DOCUMENTATION

- [`Documentation/PCI/pcieaer-howto.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/PCI/pcieaer-howto.rst): the format of the printed report, the default limit of ten messages in five seconds per function and class, and the statement that fatal and DPC reports are not limited.
- [`Documentation/ABI/testing/sysfs-bus-pci-devices-aer`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/ABI/testing/sysfs-bus-pci-devices-aer): the counter files and the four limiter files; its sample output shows longer bit names than the ones [`aer_correctable_error_string`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L477) holds at v7.2.
- [`Documentation/driver-api/hw-recoverable-errors.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/driver-api/hw-recoverable-errors.rst): the recoverable-error counts and timestamps that a crash dump carries.

## OTHER SOURCES

### Added by Claude Opus 5.5

- [PCI/AER: Ratelimit correctable and non-fatal error logging (commit a57f2bfb4a58)](https://patch.msgid.link/20250522232339.1525671-19-helgaas@kernel.org)
- [PCI/AER: Add sysfs attributes for log ratelimits (commit b4fe7398def6)](https://patch.msgid.link/20250522232339.1525671-21-helgaas@kernel.org)
- [PCI/AER: Update statistics before ratelimiting (commit 88a7765e62b9)](https://patch.msgid.link/20250522232339.1525671-11-helgaas@kernel.org)
- [PCI/AER: Trace error event before ratelimiting (commit 6bb4befbd65f)](https://patch.msgid.link/20250522232339.1525671-12-helgaas@kernel.org)
- [PCI/AER: Check log level once and remember it (commit c8f6791e33a7)](https://patch.msgid.link/20250522232339.1525671-13-helgaas@kernel.org)
- [PCI/AER: Reduce pci_print_aer() correctable error level to KERN_WARNING (commit 36c5932074aa)](https://patch.msgid.link/20250522232339.1525671-15-helgaas@kernel.org)
- [PCI/AER: Rename struct aer_stats to aer_info (commit 09683a6184ad)](https://patch.msgid.link/20250522232339.1525671-16-helgaas@kernel.org)
- [PCI/AER: Simplify add_error_device() (commit d72bae423004)](https://patch.msgid.link/20250522232339.1525671-18-helgaas@kernel.org)
- [PCI/AER: Consolidate Error Source ID logging in aer_isr_one_error_type() (commit 6a1eda745967)](https://patch.msgid.link/20250522232339.1525671-5-helgaas@kernel.org)
- [PCI/AER: Rename aer_print_port_info() to aer_print_source() (commit 99c3fd0de8eb)](https://patch.msgid.link/20250522232339.1525671-7-helgaas@kernel.org)
- [PCI/AER: Decode Requester ID when no error info found (commit 1291b716bbf9)](https://lore.kernel.org/r/20231206224231.732765-3-helgaas@kernel.org)
- [PCI/AER: Add message when AER_MAX_MULTI_ERR_DEVICES limit is hit (commit a6f494becf09)](https://patch.msgid.link/20250619185041.73240-1-akshayaj.lkd@gmail.com)
- [tracing, AER: Hide PCIe AER event when PCIEAER is not configured (commit a3b366dbf468)](https://lore.kernel.org/20250612094932.4a08abd6@batman.local.home)
- [PCI/AER: Support errors introduced by PCIe r6.0 (commit 6633875250b3)](https://patch.msgid.link/21f1875b18d4078c99353378f37dcd6b994f6d4e.1756301211.git.lukas@wunner.de)
- [PCI/AER: Print TLP Log for errors introduced since PCIe r1.1 (commit c8ab5e888bb6)](https://patch.msgid.link/5f707caf1260bd8f15012bb032f7da9a9b898aba.1756712066.git.lukas@wunner.de)
- [PCI/AER: Fix NULL pointer access by aer_info (commit 0a27bdb14b02)](https://patch.msgid.link/20250904182527.67371-1-vernon2gm@gmail.com)
- [PCI/AER: Avoid NULL pointer dereference in aer_ratelimit() (commit deb2f228388f)](https://patch.msgid.link/20250929-aer_crash_2-v1-1-68ec4f81c356@debian.org)
- [vmcoreinfo: track and log recoverable hardware errors (commit 3fa805c37dd4)](https://lkml.kernel.org/r/20251010-vmcore_hw_error-v5-1-636ede3efe44@debian.org)

## REGISTERS

The values this page counts and prints come from the AER capability of a function that logged an error and, for the message counts, from the root registers of the Root Port or RCEC that received the message. [`aer_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370) holds the capability's offset in configuration space, and each register below is read at an offset from it. The grid draws the capability's dwords with the macros that name them.

```text
    The AER capability's dwords, offsets from aer_cap
    ─────────────────────────────────────────────────

    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    +0x00 │    Next Capability    │  Ver  │     Capability ID (15:0)      │
          │    Offset (31:20)     │(19:16)│                               │
          ├───────────────────────┴───────┴───────────────────────────────┤
    +0x04 │               Uncorrectable Error Status (31:0)               │
          ├───────────────────────────────────────────────────────────────┤
    +0x08 │                Uncorrectable Error Mask (31:0)                │
          ├───────────────────────────────────────────────────────────────┤
    +0x0c │              Uncorrectable Error Severity (31:0)              │
          ├───────────────────────────────────────────────────────────────┤
    +0x10 │                Correctable Error Status (31:0)                │
          ├───────────────────────────────────────────────────────────────┤
    +0x14 │                 Correctable Error Mask (31:0)                 │
          ├───────────────────────────────────────────────────────────────┤
    +0x18 │        Advanced Error Capabilities and Control (31:0)         │
          ├───────────────────────────────────────────────────────────────┤
    +0x1c │         Header Log, four dwords to +0x28 (31:0 each)          │
          ├───────────────────────────────────────────────────────────────┤
    +0x2c │                   Root Error Command (31:0)                   │
          ├───────────────────────────────────────────────────────────────┤
    +0x30 │                   Root Error Status (31:0)                    │
          ├───────────────────────────────┬───────────────────────────────┤
    +0x34 │      ERR_FATAL/NONFATAL       │       ERR_COR Source ID       │
          │       Source ID (31:16)       │            (15:0)             │
          ├───────────────────────────────┴───────────────────────────────┤
    +0x38 │         TLP Prefix Log, up to four dwords (31:0 each)         │
          └───────────────────────────────────────────────────────────────┘

    Capability ID = PCI_EXT_CAP_ID (PCI_EXT_CAP_ID_ERR, 0x01); Ver = PCI_EXT_CAP_VER; Next = PCI_EXT_CAP_NEXT
    Uncorrectable Error Status/Mask/Severity = PCI_ERR_UNCOR_STATUS (0x04), PCI_ERR_UNCOR_MASK (0x08),
      PCI_ERR_UNCOR_SEVER (0x0c), read into aer_err_info.status and .mask for an uncorrectable record
    Correctable Error Status/Mask = PCI_ERR_COR_STATUS (0x10), PCI_ERR_COR_MASK (0x14), read into .status and .mask
    Advanced Error Capabilities and Control = PCI_ERR_CAP (0x18): First Error Pointer and the log flags
    Header Log = PCI_ERR_HEADER_LOG (0x1c), read into aer_err_info.tlp; TLP Prefix Log = PCI_ERR_PREFIX_LOG (0x38)
    Root Error Command = PCI_ERR_ROOT_COMMAND (0x2c); Root Error Status = PCI_ERR_ROOT_STATUS (0x30),
      read into aer_err_source.status
    Source IDs = PCI_ERR_ROOT_ERR_SRC (0x34), into aer_err_source.id; ERR_COR_ID() and ERR_UNCOR_ID() split it
    +0x30 and +0x34 are read only on a Root Port or RCEC, the functions the AER service binds to
```

A status register and its mask become [`status`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L851) and [`mask`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L852) of a record, and the bits that are set in the status and clear in the mask are the ones counted, traced and named. The Correctable Error Status register holds one bit per correctable error the function detected.

```text
    Correctable Error Status at +0x10, one bit per error the function detected
    ──────────────────────────────────────────────────────────────────────────
    (bits 31:16 have no macro; the Correctable Error Mask at +0x14 has the same layout)

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
          │O│I│A│T│·│·│·│N│D│B│·│·│·│·│·│R│
          └┬┴┬┴┬┴┬┴─┴─┴─┴┬┴┬┴┬┴─┴─┴─┴─┴─┴┬┘
           │ │ │ │       │ │ │           │
           │ │ │ │       │ │ │           └─ R = PCI_ERR_COR_RCVR (Receiver Error, RxErr)
           │ │ │ │       │ │ └───────────── B = PCI_ERR_COR_BAD_TLP (Bad TLP, BadTLP)
           │ │ │ │       │ └─────────────── D = PCI_ERR_COR_BAD_DLLP (Bad DLLP, BadDLLP)
           │ │ │ │       └───────────────── N = PCI_ERR_COR_REP_ROLL (REPLAY_NUM Rollover, Rollover)
           │ │ │ └───────────────────────── T = PCI_ERR_COR_REP_TIMER (Replay Timer Timeout, Timeout)
           │ │ └─────────────────────────── A = PCI_ERR_COR_ADV_NFAT (Advisory Non-Fatal Error, NonFatalErr)
           │ └───────────────────────────── I = PCI_ERR_COR_INTERNAL (Corrected Internal Error, CorrIntErr)
           └─────────────────────────────── O = PCI_ERR_COR_LOG_OVER (Header Log Overflow, HeaderOF)

    · = no macro in pci_regs.h; the name after each macro is the one aer_correctable_error_string prints
```

Each named bit has a counter at the same index in [`dev_cor_errs`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L72), and a set bit prints one line with the name from [`aer_correctable_error_string`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L477). The Uncorrectable Error Status register carries the bits of the non-fatal and fatal classes, with the same layout in its Mask and Severity registers.

```text
    Uncorrectable Error Status at +0x04, one bit per error the function detected
    ────────────────────────────────────────────────────────────────────────────
    (the Uncorrectable Error Mask at +0x08 and Severity at +0x0c have the same layout)

    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
          │X│P│M│I│W│K│F│G│B│N│V│U│E│L│O│Y│A│T│C│Q│·│·│·│·│·│·│S│D│·│·│·│Z│
          └┬┴┬┴┬┴┬┴┬┴┬┴┬┴┬┴┬┴┬┴┬┴┬┴┬┴┬┴┬┴┬┴┬┴┬┴┬┴┬┴─┴─┴─┴─┴─┴─┴┬┴┬┴─┴─┴─┴┬┘
           │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │             │ │       │
           │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │             │ │       └─ Z = PCI_ERR_UNC_UND, Undefined
           │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │             │ └───────── D = PCI_ERR_UNC_DLP, DLP
           │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │             └─────────── S = PCI_ERR_UNC_SURPDN, SDES
           │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ └───────────────────────── Q = PCI_ERR_UNC_POISON_TLP, TLP
           │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ └─────────────────────────── C = PCI_ERR_UNC_FCP, FCP
           │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ └───────────────────────────── T = PCI_ERR_UNC_COMP_TIME, CmpltTO
           │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ └─────────────────────────────── A = PCI_ERR_UNC_COMP_ABORT, CmpltAbrt
           │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ └───────────────────────────────── Y = PCI_ERR_UNC_UNX_COMP, UnxCmplt
           │ │ │ │ │ │ │ │ │ │ │ │ │ │ └─────────────────────────────────── O = PCI_ERR_UNC_RX_OVER, RxOF
           │ │ │ │ │ │ │ │ │ │ │ │ │ └───────────────────────────────────── L = PCI_ERR_UNC_MALF_TLP, MalfTLP
           │ │ │ │ │ │ │ │ │ │ │ │ └─────────────────────────────────────── E = PCI_ERR_UNC_ECRC, ECRC
           │ │ │ │ │ │ │ │ │ │ │ └───────────────────────────────────────── U = PCI_ERR_UNC_UNSUP, UnsupReq
           │ │ │ │ │ │ │ │ │ │ └─────────────────────────────────────────── V = PCI_ERR_UNC_ACSV, ACSViol
           │ │ │ │ │ │ │ │ │ └───────────────────────────────────────────── N = PCI_ERR_UNC_INTN, UncorrIntErr
           │ │ │ │ │ │ │ │ └─────────────────────────────────────────────── B = PCI_ERR_UNC_MCBTLP, BlockedTLP
           │ │ │ │ │ │ │ └───────────────────────────────────────────────── G = PCI_ERR_UNC_ATOMEG, AtomicOpBlocked
           │ │ │ │ │ │ └─────────────────────────────────────────────────── F = PCI_ERR_UNC_TLPPRE, TLPBlockedErr
           │ │ │ │ │ └───────────────────────────────────────────────────── K = PCI_ERR_UNC_POISON_BLK, PoisonTLPBlocked
           │ │ │ │ └─────────────────────────────────────────────────────── W = PCI_ERR_UNC_DMWR_BLK, DMWrReqBlocked
           │ │ │ └───────────────────────────────────────────────────────── I = PCI_ERR_UNC_IDE_CHECK, IDECheck
           │ │ └─────────────────────────────────────────────────────────── M = PCI_ERR_UNC_MISR_IDE, MisIDETLP
           │ └───────────────────────────────────────────────────────────── P = PCI_ERR_UNC_PCRC_CHECK, PCRC_CHECK
           └─────────────────────────────────────────────────────────────── X = PCI_ERR_UNC_XLAT_BLK, TLPXlatBlocked

    · = no macro in pci_regs.h; after each macro, the name aer_uncorrectable_error_string prints
    a set Severity bit makes an unmasked error fatal; a DPC trigger reads it into aer_err_info.severity
```

An uncorrectable record counts its bits in [`dev_nonfatal_errs`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L76) or [`dev_fatal_errs`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L74), chosen by the record's severity, and names them with [`aer_uncorrectable_error_string`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L512). On a DPC trigger the Severity register sets that class, while the native path takes it from the message the root received. The capability's control register supplies the First Error Pointer and the bit that says whether a Completion Timeout logged its TLP header.

```text
    Advanced Error Capabilities and Control at +0x18, the low 24 bits
    ─────────────────────────────────────────────────────────────────
    (bits 31:24 have no macro in pci_regs.h)

    bit    2 2 2 2 1 1 1 1 1 1 1 1 1 1
           3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
          │  SIZE   │L│·│·│·│·│·│T│P│·│·│e│c│g│G│   FEP   │
          └────┬────┴┬┴─┴─┴─┴─┴─┴┬┴┬┴─┴─┴┬┴┬┴┬┴┬┴────┬────┘
               │     │           │ │     │ │ │ │     │
               │     │           │ │     │ │ │ │     └─ FEP = PCI_ERR_CAP_FEP() (4:0, First Error Pointer)
               │     │           │ │     │ │ │ └─────── G = PCI_ERR_CAP_ECRC_GENC
               │     │           │ │     │ │ └───────── g = PCI_ERR_CAP_ECRC_GENE
               │     │           │ │     │ └─────────── c = PCI_ERR_CAP_ECRC_CHKC
               │     │           │ │     └───────────── e = PCI_ERR_CAP_ECRC_CHKE
               │     │           │ └─────────────────── P = PCI_ERR_CAP_PREFIX_LOG_PRESENT
               │     │           └───────────────────── T = PCI_ERR_CAP_COMP_TIME_LOG (Completion Timeout logged)
               │     └───────────────────────────────── L = PCI_ERR_CAP_TLP_LOG_FLIT (logged in Flit Mode)
               └─────────────────────────────────────── SIZE = PCI_ERR_CAP_TLP_LOG_SIZE (23:19)

    · = no macro in pci_regs.h; FEP is read into aer_err_info.first_error, T decides tlp_header_valid
    for a Completion Timeout, L is passed on to the TLP Log reader; the ECRC bits belong to ECRC setup
```

[`first_error`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L846) holds the First Error Pointer, the bit number that the printed report marks "(First)", and bit T joins the status bits in deciding [`tlp_header_valid`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L849). The root registers are read in the hard interrupt handler of a Root Port or RCEC, and the Root Error Status bits choose the message counters.

```text
    Root Error Status at +0x30, the messages a Root Port or RCEC received
    ─────────────────────────────────────────────────────────────────────

    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
          │   IRQ   │·│·│·│·│·│·│·│·│·│·│·│·│·│·│·│·│·│·│·│·│F│N│1│M│U│m│C│
          └────┬────┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴┬┴┬┴┬┴┬┴┬┴┬┴┬┘
               │                                             │ │ │ │ │ │ │
               │                                             │ │ │ │ │ │ └─ C = PCI_ERR_ROOT_COR_RCV (ERR_COR)
               │                                             │ │ │ │ │ └─── m = PCI_ERR_ROOT_MULTI_COR_RCV (several)
               │                                             │ │ │ │ └───── U = PCI_ERR_ROOT_UNCOR_RCV (either kind)
               │                                             │ │ │ └─────── M = PCI_ERR_ROOT_MULTI_UNCOR_RCV (several)
               │                                             │ │ └───────── 1 = PCI_ERR_ROOT_FIRST_FATAL (first fatal)
               │                                             │ └─────────── N = PCI_ERR_ROOT_NONFATAL_RCV (ERR_NONFATAL)
               │                                             └───────────── F = PCI_ERR_ROOT_FATAL_RCV (ERR_FATAL)
               └─────────────────────────────────────────────────────────── IRQ = PCI_ERR_ROOT_AER_IRQ (31:27)

    · = no macro in pci_regs.h; the register is read into aer_err_source.status and written back to clear it
    C, U and F choose which rootport_total_* counter grows; m and M set aer_err_info.multi_error_valid
```

A set C bit counts one ERR_COR in [`rootport_total_cor_errs`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L90), and a set U bit counts a fatal or non-fatal message, the F bit deciding which. The Error Source Identification register at +0x34 holds two Source IDs, and [`ERR_COR_ID`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L122) and [`ERR_UNCOR_ID`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L123) take the half that matches a record's class.

```text
    One 16-bit Source ID, split into the name the source line prints
    ────────────────────────────────────────────────────────────────

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    ID    │  Bus (15:8)   │ Device  │ Fn  │
          │               │  (7:3)  │(2:0)│
          └───────────────┴─────────┴─────┘

    Bus = PCI_BUS_NUM() (bits 15:8); Device = PCI_SLOT() (bits 7:3); Fn = PCI_FUNC() (bits 2:0)
    the ID is ERR_COR_ID() or ERR_UNCOR_ID() of the Error Source register, held in aer_err_info.id
```

[`PCI_BUS_NUM`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L74), [`PCI_SLOT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci.h#L32) and [`PCI_FUNC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci.h#L33) split the ID into the bus, device and function numbers that the root's source line prints after the domain. The split matches the Requester ID that [`pci_dev_id()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L739) builds for a function, and [`aer_print_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L865) compares the two to mark the function that the root's message named.

## DETAILS

The first subsections build the object that holds a function's counters and limiters and follow it from allocation to release. The middle subsections follow one native AER interrupt, from the root's message counts and the limiter through the search that sets the print flags and the status read, to the printer's counting, its tracepoint and the lines it prints. The DPC trigger and the report that firmware forwards are then read as variants of the same route. The last subsections cover the sysfs files that show the counters and set the limiters, and the messages, hand-offs and surfaces that make these paths visible.

### Kconfig assumptions

The page documents the x86-64 default configuration resolved at v7.2 with the PCI options of the campaign added, on x86-64 with ACPI. The table lists the options the prose below names and the value each assumes.

| option | assumed value | what it decides here |
|---|---|---|
| [`CONFIG_PCIEPORTBUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L5) | y | the port driver that binds the AER service to a Root Port or RCEC |
| [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28) | y | [`struct aer_info`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L60), the counters, the limiters, the printers, the two sysfs groups and the `ras:aer_event` tracepoint are built |
| [`CONFIG_PCIE_DPC`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L121) | y | a DPC trigger prints its record through [`aer_print_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L865) |
| [`CONFIG_ACPI_APEI_GHES`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Kconfig#L20) | unset | the firmware-first source of reports and of the firmware slots in the crash-dump array |
| [`CONFIG_ACPI_APEI_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Kconfig#L37) | unset | the queue that hands a firmware report to [`pci_print_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L926) |
| [`CONFIG_PROC_KCORE`](https://elixir.bootlin.com/linux/v7.2/source/fs/proc/Kconfig#L32) | y | selects [`CONFIG_VMCORE_INFO`](https://elixir.bootlin.com/linux/v7.2/source/kernel/Kconfig.kexec#L8) |
| [`CONFIG_VMCORE_INFO`](https://elixir.bootlin.com/linux/v7.2/source/kernel/Kconfig.kexec#L8) | y | [`hwerr_log_error_type()`](https://elixir.bootlin.com/linux/v7.2/source/kernel/vmcore_info.c#L130) records into the crash-dump array; unset, it is an empty stub |
| [`CONFIG_HZ_1000`](https://elixir.bootlin.com/linux/v7.2/source/kernel/Kconfig.hz#L43) | y | an interval file reads back the milliseconds written to it |
| [`CONFIG_TRACEPOINTS`](https://elixir.bootlin.com/linux/v7.2/source/init/Kconfig#L2254) | y | [`trace_aer_event()`](https://elixir.bootlin.com/linux/v7.2/source/include/ras/ras_event.h#L337) records an entry |
| [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120) | y | no debug site lies on these paths |
| [`CONFIG_PCIEAER_INJECT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L37) | unset | the software error injector that feeds the native path |

The table indexes the prose below, where each option's effect is stated at the point it applies.

### struct aer_info holds a function's counters and limiters

Counting and limiting need state that outlives one interrupt and belongs to one function. With [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28) the kernel keeps that state in a [`struct aer_info`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L60), which [`aer_info`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L371) of the function's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) points at, beside [`aer_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370), the offset of the function's AER capability. A function without that capability has no such object, so the counting and limiting functions test the pointer before they use it.

The per-bit arrays are sized by two limits that match the status registers, [`AER_MAX_TYPEOF_COR_ERRS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L46) for the correctable bits and [`AER_MAX_TYPEOF_UNCOR_ERRS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L47) for the uncorrectable bits:

```c
/* drivers/pci/pcie/aer.c:46 */
#define AER_MAX_TYPEOF_COR_ERRS		16	/* as per PCI_ERR_COR_STATUS */
#define AER_MAX_TYPEOF_UNCOR_ERRS	32	/* as per PCI_ERR_UNCOR_STATUS*/
```

The object groups its members by whose view they record, and the table names each group with the functions that write it on these paths.

| members | what they hold | written by |
|---|---|---|
| [`dev_cor_errs`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L72), [`dev_fatal_errs`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L74), [`dev_nonfatal_errs`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L76) | one counter per status bit position of each class, for the errors this function logged | [`pci_dev_aer_stats_incr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L747) |
| [`dev_total_cor_errs`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L78), [`dev_total_fatal_errs`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L80), [`dev_total_nonfatal_errs`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L82) | one count per record of each class, whatever its bits | [`pci_dev_aer_stats_incr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L747) |
| [`rootport_total_cor_errs`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L90), [`rootport_total_fatal_errs`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L91), [`rootport_total_nonfatal_errs`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L92) | the messages of each class that this function received as a Root Port or RCEC | [`pci_rootport_aer_stats_incr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L781) |
| [`correctable_ratelimit`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L95), [`nonfatal_ratelimit`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L96) | the limiter of the correctable class and of the non-fatal class | [`pci_aer_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L385), [`aer_ratelimit()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L800) and the sysfs store functions |

[`struct aer_info`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L60) is defined in aer.c and nowhere else, so its members are reachable from that file alone; read the definition for the two comments that say whose view each counter group records.

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
};
```

The first group counts errors "as seen by this device", in the comment's words, so a link partner can count errors that a faulty Endpoint caused while the Endpoint's own counters stay at 0. The second group exists in each object but grows on a Root Port or RCEC alone, and it counts messages, the ones the root generates for its own errors included. The two [`struct ratelimit_state`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/ratelimit_types.h#L16) members are the limiters, and no member limits fatal reports.

Several functions write these fields at different times, from the capability setup to the release of the function, as the strip shows.

```text
    One struct aer_info from capability setup to release, and the writes to its fields
    ──────────────────────────────────────────────────────────────────────────────────

    fields: the object, the dev_* and rootport_total_* counters, correctable_ratelimit, nonfatal_ratelimit

    time ────────────────────────────────────────────────────────────────────────────────────────────────────────▶

    event                  setup       root message   source found   printed         sysfs write   release
                           ▼           ▼              ▼              ▼               ▼             ▼
                           ┌───────────────────────────────────────────────────────────────────────┬───────────┐
    object                 │① zeroed, reached through pci_dev.aer_info                             │④ freed    │
                           └───────────────────────────────────────────────────────────────────────┴───────────┘
                           ┌───────────┬───────────────────────────────────────────────────────────┐
    rootport_total_*       │ 0         │⑤ +1 per message class at the root                         │
                           └───────────┴───────────────────────────────────────────────────────────┘
                           ┌─────────────────────────────────────────┬─────────────────────────────┐
    dev_* counters         │ 0                                       │⑧ +1 per report and set bit  │
                           └─────────────────────────────────────────┴─────────────────────────────┘
                           ┌──────────────────────────┬──────────────────────────────┬─────────────┐
    correctable_ratelimit  │② 5 s, burst 10           │⑦ window and budget advance   │⑨ ⑩ rewritten│
                           └──────────────────────────┴──────────────────────────────┴─────────────┘
                           ┌──────────────────────────┬──────────────────────────────┬─────────────┐
    nonfatal_ratelimit     │③ 5 s, burst 10           │⑥ window and budget advance   │⑨ ⑩ rewritten│
                           └──────────────────────────┴──────────────────────────────┴─────────────┘

    ①  pci_aer_init                 aer.c:393  allocates aer_info zeroed through kzalloc_obj
    ②  pci_aer_init                 :399       gives correctable_ratelimit the default interval and burst
    ③  pci_aer_init                 :401       gives nonfatal_ratelimit the same defaults
    ④  pci_aer_exit                 :423       frees aer_info with kfree when the function is released
    ⑤  pci_rootport_aer_stats_incr  :790       counts a received message class in rootport_total_*
    ⑥  aer_ratelimit                :807       consults nonfatal_ratelimit through __ratelimit, which advances it
    ⑦  aer_ratelimit                :809       consults correctable_ratelimit through __ratelimit as well
    ⑧  pci_dev_aer_stats_incr       :760       counts a report in a total and each unmasked bit's counter
    ⑨  aer_ratelimit_interval_attr  :676       stores an interval written through sysfs
    ⑩  aer_ratelimit_burst_attr     :706       stores a burst written through sysfs
```

① [`pci_aer_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L385) allocates the object zeroed through `kzalloc_obj()`. ② `pci_aer_init()` gives [`correctable_ratelimit`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L95) the default interval and burst. ③ `pci_aer_init()` gives [`nonfatal_ratelimit`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L96) the same defaults. ④ [`pci_aer_exit()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L421) frees the object with `kfree()` when the function is released, which the next subsection shows beside the allocation although it is the strip's last event. ⑤ [`pci_rootport_aer_stats_incr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L781) adds one to a message counter of the root's object. ⑥ [`aer_ratelimit()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L800) consults the non-fatal limiter through [`__ratelimit`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/ratelimit_types.h#L46), which advances its window and budget. ⑦ `aer_ratelimit()` consults the correctable limiter the same way. ⑧ [`pci_dev_aer_stats_incr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L747) adds one to a total and to the counter of each unmasked bit. ⑨ The store function that [`aer_ratelimit_interval_attr`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L647) generates writes a new interval. ⑩ The store function that [`aer_ratelimit_burst_attr`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L682) generates writes a new burst.

At v7.2 these are the writers of the drawn fields, because the definition is private to aer.c and no other line of that file assigns them; the generic [`___ratelimit()`](https://elixir.bootlin.com/linux/v7.2/source/lib/ratelimit.c#L27) behind marks ⑥ and ⑦ and [`ratelimit_state_init()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/ratelimit.h#L9) behind ② and ③ are shown in the subsections that read them.

### pci_aer_init attaches aer_info when the capability exists

The object is created while the PCI core sets a newly found function up. [`pci_init_capabilities()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2650) calls the AER initializer among the other capability initializers; read the stage for the call.

```c
/* drivers/pci/probe.c:2650 */
static void pci_init_capabilities(struct pci_dev *dev)
{
	... /* 15 lines, to :2667 */
	pci_acs_init(dev);		/* Access Control Services */
	pci_ptm_init(dev);		/* Precision Time Measurement */
	pci_aer_init(dev);		/* Advanced Error Reporting */
```

[`pci_aer_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L385) runs for each function that [`pci_init_capabilities()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2650) sets up, with or without an AER capability. It looks the capability up and allocates the object only when the capability is present; read its first stage for the allocation and the two limiter initializations, which ends before the save buffer and the enabling of error reporting.

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
```

A missing capability returns with [`aer_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370) at 0 and [`aer_info`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L371) NULL, and a failed allocation sets `aer_cap` back to 0, the handling that commit [0a27bdb14b02](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=0a27bdb14b028fed30a10cec2f945c38cb5ca4fa) ("PCI/AER: Fix NULL pointer access by aer_info") added. The two calls of [`ratelimit_state_init()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/ratelimit.h#L9) give each limiter [`DEFAULT_RATELIMIT_INTERVAL`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/ratelimit_types.h#L9) and [`DEFAULT_RATELIMIT_BURST`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/ratelimit_types.h#L10). [`ratelimit_state_init()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/ratelimit.h#L9) is the generic initializer of a [`struct ratelimit_state`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/ratelimit_types.h#L16); read it for the state a new limiter starts in.

```c
/* include/linux/ratelimit.h:9 */
static inline void ratelimit_state_init(struct ratelimit_state *rs,
					int interval, int burst)
{
	memset(rs, 0, sizeof(*rs));

	raw_spin_lock_init(&rs->lock);
	rs->interval	= interval;
	rs->burst	= burst;
}
```

The initializer zeroes the whole state, so a new limiter has no window open and no misses counted, and it stores the interval in jiffies and the burst as a count. The defaults, [`DEFAULT_RATELIMIT_INTERVAL`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/ratelimit_types.h#L9) and [`DEFAULT_RATELIMIT_BURST`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/ratelimit_types.h#L10), are defined beside the structure in include/linux/ratelimit_types.h:

```c
/* include/linux/ratelimit_types.h:9 */
#define DEFAULT_RATELIMIT_INTERVAL	(5 * HZ)
#define DEFAULT_RATELIMIT_BURST		10
```

With these defaults a limiter allows ten reports in a window of five seconds, `5 * HZ` jiffies, that the first report opens; the limiter subsection reads that rule in the code. The object is freed with the function. The release callback of the function's embedded device, [`pci_release_dev()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2482), calls [`pci_release_capabilities()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2466), whose first call is [`pci_aer_exit()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L421); read the two for that order.

```c
/* drivers/pci/probe.c:2466 */
static void pci_release_capabilities(struct pci_dev *dev)
{
	pci_aer_exit(dev);
	pci_rcec_exit(dev);
	pci_iov_release(dev);
	pci_free_cap_save_buffers(dev);
}

/**
 * pci_release_dev - Free a PCI device structure when all users of it are
 *		     finished
 * @dev: device that's been disconnected
 *
 * Will be called only by the device core when all users of this PCI device are
 * done.
 */
static void pci_release_dev(struct device *dev)
{
	struct pci_dev *pci_dev;

	pci_dev = to_pci_dev(dev);
	pci_release_capabilities(pci_dev);
```

The AER state is the first capability state released, before the function's memory is freed. [`pci_aer_exit()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L421) frees the object and clears the pointer:

```c
/* drivers/pci/pcie/aer.c:421 */
void pci_aer_exit(struct pci_dev *dev)
{
	kfree(dev->aer_info);
	dev->aer_info = NULL;
}
```

Clearing [`aer_info`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L371) after `kfree()` leaves the NULL that the readers test. The object therefore lasts from the capability setup to the release of the function, and in between the counting, limiting and sysfs code of aer.c is all that touches its fields.

### The AER interrupt hands the root's status to a thread

A Root Port or RCEC reports an error message it received from below, or one it generated for itself, by setting bits in its Root Error Status register and raising the AER interrupt. The AER service of the port driver takes that interrupt, bound through the [`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59) that portdrv creates as the service's instance, and it splits the work between a hard handler and an IRQ thread. [`aer_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1607) registers the two halves with `devm_request_threaded_irq()`; read the stage for the handler, the thread function and the thread's name.

```c
/* drivers/pci/pcie/aer.c:1607 */
static int aer_probe(struct pcie_device *dev)
{
	int status;
	struct aer_rpc *rpc;
	struct device *device = &dev->device;
	struct pci_dev *port = dev->port;
	... /* 19 lines, to :1632 */
	status = devm_request_threaded_irq(device, dev->irq, aer_irq, aer_isr,
					   IRQF_SHARED, "aerdrv", dev);
	if (status) {
		pci_err(port, "request AER IRQ %d failed\n", dev->irq);
		return status;
	}
```

[`aer_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1470) runs in hard interrupt context, and [`aer_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1449) runs in the IRQ thread named "aerdrv", which the hard handler wakes. Their hand-off is [`aer_fifo`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L56), a fifo of [`struct aer_err_source`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L49) entries inside the service's [`struct aer_rpc`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L54):

```c
/* drivers/pci/pcie/aer.c:44 */
#define AER_ERROR_SOURCES_MAX		128
... /* 4 lines, to :49 */
struct aer_err_source {
	u32 status;			/* PCI_ERR_ROOT_STATUS */
	u32 id;				/* PCI_ERR_ROOT_ERR_SRC */
};

struct aer_rpc {
	struct pci_dev *rpd;		/* Root Port device */
	DECLARE_KFIFO(aer_fifo, struct aer_err_source, AER_ERROR_SOURCES_MAX);
};
```

An entry holds the Root Error Status in [`status`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L50) and the Error Source Identification register in [`id`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L51), and the fifo holds [`AER_ERROR_SOURCES_MAX`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L44) entries, 128. The hard handler tests the status against [`AER_ERR_STATUS_MASK`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L125), the four received bits:

```c
/* drivers/pci/pcie/aer.c:125 */
#define AER_ERR_STATUS_MASK		(PCI_ERR_ROOT_UNCOR_RCV |	\
					PCI_ERR_ROOT_COR_RCV |		\
					PCI_ERR_ROOT_MULTI_COR_RCV |	\
					PCI_ERR_ROOT_MULTI_UNCOR_RCV)
```

[`aer_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1470) fills one entry per interrupt; read it for what it reads, what it clears and what happens when the fifo is full.

```c
/* drivers/pci/pcie/aer.c:1470 */
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

The handler returns `IRQ_NONE` when none of the four received bits is set, and it writes the status back, which clears the bits it read. When `kfifo_put()` fails on a full fifo, the handler returns `IRQ_HANDLED` without waking the thread, and the message that interrupt carried reaches no counter. [`aer_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1449) drains the fifo in the thread:

```c
/* drivers/pci/pcie/aer.c:1449 */
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

Each entry goes to [`aer_isr_one_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1405) with [`rpd`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L55), the root's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352), so the root's counters and the root's limiter are the ones this route charges. The hand-off between the two contexts is drawn below.

```text
    The root's status crosses from the hard interrupt handler to the IRQ thread through aer_fifo
    ───────────────────────────────────────────────────────────────────────────────────────────

    time ↓
    Root Port or RCEC          ╎ hard interrupt handler     ╎ aer_fifo, 128 entries    ╎ IRQ thread "aerdrv"
    ───────────────────────────┼────────────────────────────┼──────────────────────────┼────────────────────────────────
    an ERR_* message arrives;  ╎                            ╎                          ╎
    Root Error Status bits     ╎                            ╎                          ╎
    set, interrupt raised ──────▶                           ╎                          ╎
                               ╎ status and Source IDs read ╎                          ╎
                               ╎ into one aer_err_source    ╎                          ╎
    status bits cleared  ◀────────                          ╎                          ╎
                               ╎ status written back        ╎                          ╎
                               ╎ entry queued ───────────────▶                         ╎
                               ╎                            ╎ one entry more; when     ╎
                               ╎                            ╎ full, the new entry      ╎
                               ╎                            ╎ is dropped               ╎
                               ╎ IRQ_WAKE_THREAD returned   ╎                          ╎
                               ╎                            ╎                          ╎ thread woken
                               ╎                            ╎ entry taken ──────────────▶
                               ╎                            ╎                          ╎ the root's counters
                               ╎                            ╎                          ╎ count the entry, then each
                               ╎                            ╎                          ╎ class is searched and printed
                               ╎                            ╎                          ╎ aer_fifo empty: IRQ_HANDLED
```

The hard handler does the register work and the queueing, and the thread does the counting, the search and the printing, so the counters on this route change in the thread of the root that received the message.

### The root counts each message class it receives

The thread turns one entry into the root's message counts and into up to two records, one for the correctable class and one for the uncorrectable class. A record is a [`struct aer_err_info`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L833), defined in drivers/pci/pci.h under [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28); the table groups its members by the step that fills them.

| members | what they hold | written on these paths by |
|---|---|---|
| [`dev`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L834), [`error_dev_num`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L836) | the functions the search listed, at most [`AER_MAX_MULTI_ERR_DEVICES`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L812) | [`add_error_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L985), [`find_source_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1099), [`dpc_get_aer_uncorrect_severity()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L236) |
| [`ratelimit_print`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L835), [`root_ratelimit_print`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L842) | whether a listed function's details and the root's source line print | [`add_error_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L985), [`dpc_get_aer_uncorrect_severity()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L236) |
| [`level`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L837), [`severity`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L841) | the printk level of the record's lines and its class | [`aer_isr_one_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1405), [`dpc_get_aer_uncorrect_severity()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L236), [`pci_print_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L926) |
| [`id`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L839), [`multi_error_valid`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L844) | the Source ID the root received and whether several messages of the class arrived | [`aer_isr_one_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1405) |
| [`status`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L851), [`mask`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L852), [`first_error`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L846), [`tlp_header_valid`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L849), [`tlp`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L853) | the AER registers of the listed function being printed | [`aer_get_device_error_info()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1293), [`pci_print_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L926) |
| [`is_cxl`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L848) and the two padding fields | the selector of a bus type this page leaves out, and alignment | [`aer_get_device_error_info()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1293), [`pci_print_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L926) |

Read [`struct aer_err_info`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L833) for the two print flags beside the fields the printer reads.

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

The arrays [`dev`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L834) and [`ratelimit_print`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L835) share one index, the slot of a listed function, while [`root_ratelimit_print`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L842) is one bit for the whole record. The fields from [`status`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L851) down describe one function at a time, since the status read reuses the record for each slot. [`aer_isr_one_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1405) counts at the root and then builds the records; read it for the order of the two steps and for the fields a record starts with.

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

[`pci_rootport_aer_stats_incr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L781) runs before either record exists, so the root's counts do not depend on finding a source. Each record is a designated initializer, which leaves the members it does not name at 0, the print flags among them, and it sets the Source ID half, the class, the printk level and [`multi_error_valid`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L844). The level is `KERN_WARNING` for the correctable record and `KERN_ERR` for the uncorrectable one, and the halves come from two macros:

```c
/* drivers/pci/pcie/aer.c:122 */
#define ERR_COR_ID(d)			(d & 0xffff)
#define ERR_UNCOR_ID(d)			(d >> 16)
```

[`ERR_COR_ID`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L122) keeps the low 16 bits of the Error Source Identification register and [`ERR_UNCOR_ID`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L123) the high 16 bits. [`pci_rootport_aer_stats_incr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L781) maps the received bits onto the three message counters of the root's object; read it for the mapping and the NULL test.

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

A set [`PCI_ERR_ROOT_COR_RCV`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L827) adds one to [`rootport_total_cor_errs`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L90), and a set [`PCI_ERR_ROOT_UNCOR_RCV`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L829) adds one to [`rootport_total_fatal_errs`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L91) or [`rootport_total_nonfatal_errs`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L92), chosen by [`PCI_ERR_ROOT_FATAL_RCV`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L833). An entry therefore adds at most one per class, however many messages the root received, because [`PCI_ERR_ROOT_MULTI_COR_RCV`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L828) and [`PCI_ERR_ROOT_MULTI_UNCOR_RCV`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L830) set the record's [`multi_error_valid`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L844) and add nothing to the counts. The root's counts and a function's own counts see different things, as the comment in [`struct aer_info`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L60) warns and the figure shows for one correctable error.

```text
    Where one correctable error is counted: the root counts messages, a function its own bits
    ─────────────────────────────────────────────────────────────────────────────────────────

    (a) the Endpoint logs a correctable error and sends ERR_COR
    (b) the Root Port's receiver sees a Bad TLP on the link and logs it itself

                                                               counted for (a) and (b)
    Root Port   ┌──────────────────────────────────────────┐
    or RCEC     │ rootport_total_cor_errs  (messages)      │   (a) +1 at the interrupt; (b) +1 as well
                │ dev_cor_errs[], dev_total_cor_errs       │   (a) unchanged; (b) +1 in total and in [6]
                └────────────────────┬─────────────────────┘
                                     │
                                     │ link  ▲ (a) ERR_COR carrying the Endpoint's ID
                                     │
                ┌────────────────────┴─────────────────────┐
    Endpoint    │ dev_cor_errs[], dev_total_cor_errs       │   (a) +1 per bit it logged; (b) unchanged
                └──────────────────────────────────────────┘
```

In case (a) the root counts the message and the Endpoint counts its bit, while in case (b) the Endpoint's counters stay at 0 and the Root Port's grow, the pattern the counter files' documentation describes for a faulty Endpoint. The root's totals are thus counts of messages, and a function's counters are counts of the errors it logged itself.

### Each limiter passes a burst and counts the rest

A function that keeps reporting can fill the log, and commit commit [a57f2bfb4a58](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=a57f2bfb4a5863f83087867c0e671f2418212d23) ("PCI/AER: Ratelimit correctable and non-fatal error logging") added a limiter per function and class after a flood of reports caused RCU stall and CSD-lock warnings, as its message records. [`aer_ratelimit()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L800) answers for one function and one class whether a report may print; read it for which class uses which limiter.

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

[`aer_ratelimit()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L800) never limits a fatal report, since its default branch returns 1. A function without [`aer_info`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L371) also gets 1, and commit commit [deb2f228388f](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=deb2f228388ff3a9d0623e3b59a053e9235c341d) ("PCI/AER: Avoid NULL pointer dereference in aer_ratelimit()") added that test after a firmware report named a function with no AER capability. [`__ratelimit`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/ratelimit_types.h#L46) passes the caller's name on to [`___ratelimit()`](https://elixir.bootlin.com/linux/v7.2/source/lib/ratelimit.c#L27):

```c
/* include/linux/ratelimit_types.h:45 */
extern int ___ratelimit(struct ratelimit_state *rs, const char *func);
#define __ratelimit(state) ___ratelimit(state, __func__)
```

The limiter's state is a [`struct ratelimit_state`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/ratelimit_types.h#L16), whose members hold the settings and the current window:

```c
/* include/linux/ratelimit_types.h:16 */
struct ratelimit_state {
	raw_spinlock_t	lock;		/* protect the state */

	int		interval;
	int		burst;
	atomic_t	rs_n_left;
	atomic_t	missed;
	unsigned int	flags;
	unsigned long	begin;
};
```

[`interval`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/ratelimit_types.h#L19) and [`burst`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/ratelimit_types.h#L20) are the two settings, the window length in jiffies and the reports allowed in it. [`rs_n_left`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/ratelimit_types.h#L21) holds the part of the burst left in the current window, [`missed`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/ratelimit_types.h#L22) counts the refusals, [`begin`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/ratelimit_types.h#L24) is the jiffies value at which the window opened, [`flags`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/ratelimit_types.h#L23) records whether a window has been opened, and [`lock`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/ratelimit_types.h#L17) serializes the updates. [`___ratelimit()`](https://elixir.bootlin.com/linux/v7.2/source/lib/ratelimit.c#L27) reads the two settings once and handles the cases that switch the limiter off or close it; read its first stage for those cases.

```c
/* lib/ratelimit.c:27 */
int ___ratelimit(struct ratelimit_state *rs, const char *func)
{
	/* Paired with WRITE_ONCE() in .proc_handler().
	 * Changing two values separately could be inconsistent
	 * and some message could be lost.  (See: net_ratelimit_state).
	 */
	int interval = READ_ONCE(rs->interval);
	int burst = READ_ONCE(rs->burst);
	unsigned long flags;
	int ret = 0;

	/*
	 * Zero interval says never limit, otherwise, non-positive burst
	 * says always limit.
	 */
	if (interval <= 0 || burst <= 0) {
		WARN_ONCE(interval < 0 || burst < 0, "Negative interval (%d) or burst (%d): Uninitialized ratelimit_state structure?\n", interval, burst);
		ret = interval == 0 || burst > 0;
		if (!(READ_ONCE(rs->flags) & RATELIMIT_INITIALIZED) || (!interval && !burst) ||
		    !raw_spin_trylock_irqsave(&rs->lock, flags))
			goto nolock_ret;

		/* Force re-initialization once re-enabled. */
		rs->flags &= ~RATELIMIT_INITIALIZED;
		goto unlock_ret;
	}
```

An interval of 0 passes every call, and a positive interval with a burst of 0 or less refuses every call; a negative setting also triggers a warning once. The second stage of [`___ratelimit()`](https://elixir.bootlin.com/linux/v7.2/source/lib/ratelimit.c#L27), with the lock-contention stretch folded, opens a window at the first call, restarts it once the interval has passed and spends the burst; read it for the restart message and the miss count.

```c
/* lib/ratelimit.c:27 */
int ___ratelimit(struct ratelimit_state *rs, const char *func)
{
	... /* 38 lines, to :67 */
	if (!(rs->flags & RATELIMIT_INITIALIZED)) {
		rs->begin = jiffies;
		rs->flags |= RATELIMIT_INITIALIZED;
		atomic_set(&rs->rs_n_left, rs->burst);
	}

	if (time_is_before_jiffies(rs->begin + interval)) {
		int m;

		/*
		 * Reset rs_n_left ASAP to reduce false positives
		 * in parallel calls, see above.
		 */
		atomic_set(&rs->rs_n_left, rs->burst);
		rs->begin = jiffies;

		if (!(rs->flags & RATELIMIT_MSG_ON_RELEASE)) {
			m = ratelimit_state_reset_miss(rs);
			if (m) {
				printk_deferred(KERN_WARNING
						"%s: %d callbacks suppressed\n", func, m);
			}
		}
	}

	/* Note that the burst might be taken by a parallel call. */
	if (atomic_read(&rs->rs_n_left) > 0 && atomic_dec_return(&rs->rs_n_left) >= 0)
		ret = 1;

unlock_ret:
	raw_spin_unlock_irqrestore(&rs->lock, flags);

nolock_ret:
	if (!ret)
		ratelimit_state_inc_miss(rs);

	return ret;
}
```

The first call after initialization sets [`begin`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/ratelimit_types.h#L24) and fills [`rs_n_left`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/ratelimit_types.h#L21) with the burst. A call after `begin + interval` refills the budget, restarts the window and prints "%s: %d callbacks suppressed" when misses were counted, with the name its caller passed. A call passes while the budget lasts, and a refused call adds one to the misses through [`ratelimit_state_inc_miss()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/ratelimit.h#L25). Because [`__ratelimit`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/ratelimit_types.h#L46) passes `__func__`, the log line names [`aer_ratelimit()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L800) and no device, so it reads "aer_ratelimit: N callbacks suppressed" at `KERN_WARNING`, printed through `printk_deferred()`. The figure lays one window out to scale with the default settings.

```text
    A limiter's window lets the burst through, then holds reports until the interval ends
    ─────────────────────────────────────────────────────────────────────────────────────

    (interval 5 s, burst 10; one column is 0.1 s; twelve reports in 1.2 s, a thirteenth at 5.6 s)

    seconds     0         1         2         3         4         5         6
                ├─────────┼─────────┼─────────┼─────────┼─────────┼─────────┤
                              first window: begin set at the first report
    window      ├─────────────────────────────────────────────────┤     ├──────▶

    passes      ●●●●●●●●●●                                              ●         pass, rs_n_left 10 down to 0
    suppressed            ○○                                            │         suppressed, missed 1 then 2
                                                                        │
                                                                        ▼
    log                                       at 5.6 s: "aer_ratelimit: 2 callbacks suppressed",
                                              then a new window opens with a budget of 10
```

So far, a function's [`struct aer_info`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L60) exists from its capability setup to its release, the root has counted the message classes of an interrupt, and each limiter can answer whether one more report of its class may print, holding back the rest of a window once the burst is spent.

### The search lists functions and asks their limiters once

A record names a class and a Source ID, and the functions whose registers hold the details are found by a search below the root. The limiter is asked during that search, once per listed function, and the answers travel to the printer as the record's print flags. [`aer_isr_one_error_type()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1373) handles one record; read it for the search, the condition of the root's source line and the hand-off to the status reads.

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

The source line prints when [`root_ratelimit_print`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L842) is 1, or when the search found nothing and the root's own limiter passes, as the comment explains. The details of the listed functions follow in [`aer_process_err_devices()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1352) only when the search found one. [`find_source_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1099) tries the root first and then the functions below it:

```c
/* drivers/pci/pcie/aer.c:1099 */
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

An RCEC's search covers the endpoints associated with it, a Root Port's search covers its subordinate bus, and [`find_device_iter()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1067) decides at each function whether to list it. [`find_device_iter()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1067) lists a function that passes the source test and stops the search when the record carries a single message or the list is full:

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

A listed function ends the search unless [`multi_error_valid`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L844) is set, and a full list ends it with the "Exceeded max supported" message. The list holds [`AER_MAX_MULTI_ERR_DEVICES`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L812) functions, defined in drivers/pci/pci.h:

```c
/* drivers/pci/pci.h:812 */
#define AER_MAX_MULTI_ERR_DEVICES	5	/* Not likely to have more */
```

With five slots, a sixth function with a logged error is not listed, so this route neither counts nor prints it. [`add_error_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L985) lists a function with a reference taken by [`pci_dev_get()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L1565) and asks the function's limiter; read it for the two flags.

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

[`ratelimit_print`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L835) of slot i becomes 1 when [`aer_ratelimit()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L800) passes for the listed function, and the same branch sets [`root_ratelimit_print`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L842), so the source line prints whenever the details of a listed function print. The budget is spent here, when the function is listed, so a listed function whose status read later yields no record has still used one report of its window. The two flags of a record are written when the record starts, during the search and, for a DPC record, by DPC's own setup, as the strip shows.

```text
    One record's print flags, from the record's start to the two lines they gate
    ────────────────────────────────────────────────────────────────────────────

    fields: root_ratelimit_print and ratelimit_print[i] of one struct aer_err_info

    time ────────────────────────────────────────────────────────────────────────────────────────────────▶

    event                    record built    function found      source line       details
                             ▼               ▼                   ▼                 ▼
                             ┌───────────────┬───────────────────────────────────────────────────────┐
    root_ratelimit_print     │➊ 0            │➌ 1 once any found function's limiter passes           │
                             └───────────────┴───────────────────────────────────────────────────────┘
                             ┌───────────────┬───────────────────────────────────────────────────────┐
    ratelimit_print[i]       │➊ 0            │➋ 1 when function i's limiter passes                   │
                             └───────────────┴───────────────────────────────────────────────────────┘
                             ┌───────────────────────────────────────────────────────────────────────┐
    a DPC record's [0]       │➍ 1, set with no limiter                                               │
                             └───────────────────────────────────────────────────────────────────────┘
                                                                 ▲ read: the source line
                                                                                   ▲ read: function i's details

    ➊  aer_isr_one_error               aer.c:1418  starts the correctable record with every print flag 0
    ➋  add_error_device                :1004       sets ratelimit_print[i] when aer_ratelimit() passes
    ➌  add_error_device                :1005       sets root_ratelimit_print in the same branch
    ➍  dpc_get_aer_uncorrect_severity  dpc.c:259   sets ratelimit_print[0] for the DPC record
```

➊ [`aer_isr_one_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1405) starts the correctable record with every print flag 0, and its uncorrectable record at [`aer.c:1431`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1431) starts the same way. ➋ [`add_error_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L985) sets [[ratelimit_print[i]|aer_err_info.ratelimit_print]] when [`aer_ratelimit()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L800) passes for the listed function. ➌ `add_error_device()` sets [`root_ratelimit_print`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L842) in the same branch. ➍ [`dpc_get_aer_uncorrect_severity()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L236) sets slot 0's flag for the one record of a DPC trigger, which a later subsection reads.

No other line of the tree writes the two flags at v7.2; [`pci_print_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L926) builds its own record without them, and [`dpc_process_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L264) starts its record zeroed with `= {}`. After the search, each listed slot carries its own decision, and the root's flag is 1 exactly when one of them is.

### The root's source line names the requester it received

The source line is the root's report of what arrived, the class of the message and the Requester ID it carried, printed before the details of the listed functions. It names the sending function even when the search finds no logged error. [`aer_print_source()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L852) prints it from the record and the root; read it for the fields it formats and its level.

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

The line is printed at `KERN_INFO` through [`pci_info()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2895) whatever the record's class, and it starts with "Multiple " when [`multi_error_valid`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L844) is set. It names the requester by the root's domain from [`pci_domain_nr()`](https://elixir.bootlin.com/linux/v7.2/source/arch/x86/include/asm/pci.h#L43) and by the bus, device and function that [`PCI_BUS_NUM`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L74), [`PCI_SLOT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci.h#L32) and [`PCI_FUNC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci.h#L33) split from `source`, a local of [`aer_print_source()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L852) that holds [`id`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L839). When the search found nothing, the line ends with " (no details found", and the format string carries no closing parenthesis for it. The class word comes from [`aer_error_severity_string`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L465), indexed by [`severity`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L841):

```c
/* drivers/pci/pcie/aer.c:462 */
/*
 * AER error strings
 */
static const char * const aer_error_severity_string[] = {
	"Uncorrectable (Non-Fatal)",
	"Uncorrectable (Fatal)",
	"Correctable"
};
```

The order of the entries follows the class values that include/linux/aer.h defines, so [`AER_NONFATAL`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L14), [`AER_FATAL`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L15) and [`AER_CORRECTABLE`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L16) index the three strings in turn:

```c
/* include/linux/aer.h:14 */
#define AER_NONFATAL			0
#define AER_FATAL			1
#define AER_CORRECTABLE			2
```

A correctable message from 01:00.0 under a root in domain 0 thus prints "Correctable error message received from 0000:01:00.0" at the root's name, and the lines that follow report what each listed function logged.

### The status read fills the record for each listed function

The root's message says that an error happened, and the listed function's AER registers say which. [`aer_process_err_devices()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1352) reads and prints the listed functions before it handles any of them, to not lose records by reset, as its comment says; read it for the two passes.

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

The first pass calls [`aer_get_device_error_info()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1293) and [`aer_print_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L865) per slot, and the second pass reads the registers again before [`handle_error_source()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1196) takes the function into recovery, which this page leaves to the recovery code. [`aer_get_device_error_info()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1293) fills the record's register fields for one slot, and the outline gives its two pieces.

| piece | lines | stage |
|---|---|---|
| ⓐ | aer.c:1293-1321 | clears the fields the record reuses and reads the correctable pair |
| ⓑ | aer.c:1322-1350 | reads the uncorrectable pair, the First Error Pointer and the TLP log |

ⓐ The first piece of [`aer_get_device_error_info()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1293) clears the per-function fields and reads the correctable Status and Mask:

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

	if (info->severity == AER_CORRECTABLE) {
		pci_read_config_dword(dev, aer + PCI_ERR_COR_STATUS,
			&info->status);
		pci_read_config_dword(dev, aer + PCI_ERR_COR_MASK,
			&info->mask);
		if (!(info->status & ~info->mask))
			return 0;
```

[`status`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L851) and [`tlp_header_valid`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L849) are reset for each slot because the record is shared. A function without [`aer_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370), or a correctable pair with no unmasked bit, ends the slot with 0, which skips its print. ⓑ The second piece of [`aer_get_device_error_info()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1293) reads the uncorrectable pair when the link can still be read, and then the capability's control register:

```c
/* drivers/pci/pcie/aer.c:1322 */
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

For a fatal record the uncorrectable pair is read on a Root Port, RCEC or Downstream Port, the types whose link the comment calls still healthy, and for a non-fatal record on any type. A fatal record of any other function keeps [`status`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L851) at 0 and returns 1, and the printer then reports it as inaccessible. [`first_error`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L846) comes from [`PCI_ERR_CAP_FEP()`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L812), and [`tlp_header_logged()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L815) decides whether the TLP log is read. It tests the status against [`AER_LOG_TLP_MASKS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L99), the errors whose header a function always logs:

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

The mask holds the TLP-related uncorrectable errors that the comment in [`tlp_header_logged()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L815) ties to section 6.2.7 of PCIe r7.0; read the function for the second condition.

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

A Completion Timeout has a logged header only on a function whose control register sets [`PCI_ERR_CAP_COMP_TIME_LOG`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L818), which `capctl`, a parameter of [`tlp_header_logged()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L815), carries. The registers the status read takes and the record fields they fill are drawn below.

```text
    The source function's AER registers feed the record the printer reads
    ─────────────────────────────────────────────────────────────────────

    AER capability of function dev[i]                                struct aer_err_info, record i's fields
    ┌───────────────────────────────────────┐                        ┌─────────────────────────────────────────────┐
    │ Correctable Error Status, Mask        ├───────────────────────▶│ status, mask: a correctable record          │
    │   at +0x10 and +0x14                  │ unmasked bits          │                                             │
    │                                       │ none: no record        │                                             │
    │ Uncorrectable Error Status, Mask      ├───────────────────────▶│ status, mask: a fatal or non-fatal          │
    │   at +0x04 and +0x08                  │                        │ record, when the link can be read           │
    │                                       │                        │                                             │
    │ Capabilities and Control at +0x18     │                        │                                             │
    │   First Error Pointer (4:0)           ├───────────────────────▶│ first_error                                 │
    │   bit T, Completion Timeout logged    ├───────────────────────▶│ tlp_header_valid: a status bit that         │
    │                                       │                        │ always logs, or Completion Timeout and T    │
    │ Header Log, TLP Prefix Log            │                        │                                             │
    │   at +0x1c and +0x38                  ├───────────────────────▶│ tlp, read only when tlp_header_valid is 1   │
    └───────────────────────────────────────┘                        └─────────────────────────────────────────────┘

    a pair with no unmasked bit ends record i before printing; for ERR_FATAL from a function that is
    no Root Port, RCEC or Downstream Port the pair is not read, and status stays 0
```

After the read, the slot's record holds the function's status and mask, its First Error Pointer and, when valid, its TLP header, the register values the printer formats.

### aer_print_error counts and traces before reading the flag

The printer counts and traces a record before it decides to print, so a suppressed report still reaches the counters and the tracepoint, the order established by commit [88a7765e62b9](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=88a7765e62b9e4c79c7ca2c7b749ae04f54a5668) ("PCI/AER: Update statistics before ratelimiting") and commit [6bb4befbd65f](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=6bb4befbd65fa7f99688fb707e376637e5acfe36) ("PCI/AER: Trace error event before ratelimiting"). [`aer_print_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L865) handles one slot of a record for the native path and for DPC, and the outline gives its two pieces.

| piece | lines | stage |
|---|---|---|
| ❶ | aer.c:865-884 | checks the slot, counts and traces the record, and reads the print flag |
| ❷ | aer.c:885-909 | prints the header, the device line, the bit lines, the TLP header and the first-agent line |

❶ The first piece of [`aer_print_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L865) checks the slot index, counts, traces and reads the flag:

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

`WARN_ON_ONCE()` rejects a slot index of [`AER_MAX_MULTI_ERR_DEVICES`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L812) or more. [`pci_dev_aer_stats_incr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L747) counts the record and [`trace_aer_event()`](https://elixir.bootlin.com/linux/v7.2/source/include/ras/ras_event.h#L337) records it with the unmasked status, both before the flag is read, and a slot whose [`ratelimit_print`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L835) is 0 returns before any line. `id`, a local of [`aer_print_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L865), holds the function's Requester ID from [`pci_dev_id()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L739) for the second piece, and `bus_type`, another local, comes from [`aer_err_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L859):

```c
/* drivers/pci/pci.h:859 */
static inline const char *aer_err_bus(struct aer_err_info *info)
{
	return info->is_cxl ? "CXL" : "PCIe";
}
```

For a PCIe function the word is "PCIe", and the other value names a bus type that this page leaves out; the word starts the header line and fills the tracepoint's bus_type field. The native route, the DPC route and the firmware route pass through the same stops in one order, each skipping or answering some of them differently, as the map shows.

```text
    Three routes through the same stops: what each route counts, traces and limits
    ──────────────────────────────────────────────────────────────────────────────

                 root counts      limiter at       function        trace           print           lines
                 the message      discovery        counts          event           decision        printed

    native   N ───◉────────────────◉────────────────◉───────────────◉───────────────◉───────────────◉─────────▶
                 «1» class        «2» flags set    «3» +1 per      «4» always      «5» flag read   header, bits,
                 counted          if it passes     set bit                         0: stop         TLP Header

    DPC      D ───╳────────────────╳────────────────◉───────────────◉───────────────◉───────────────◉─────────▶
                 not counted      «6» flag preset  «3» as N        «4» as N        «5» reads 1     as N
                                  to 1

    firmware F ───╳────────────────╳────────────────◉───────────────◉───────────────◉───────────────◉─────────▶
                 not counted      no flags         «7» +1 per      «8» always      «9» limiter     status, bits,
                                                   set bit                         0: stop         layer, agent

    «1»  aer_isr_one_error               aer.c:1410  counts the message class in the root's counters
    «2»  add_error_device                :1003       consults the found function's limiter and sets the flags
    «3»  aer_print_error                 :878        counts the record in the function's own counters
    «4»  aer_print_error                 :879        traces the record before any print decision
    «5»  aer_print_error                 :882        returns before printing when the record's flag is 0
    «6»  dpc_get_aer_uncorrect_severity  dpc.c:259   presets the flag for the one DPC record
    «7»  pci_print_aer                   aer.c:954   counts the firmware's record in the function's counters
    «8»  pci_print_aer                   :955        traces the firmware's record before the print decision
    «9»  pci_print_aer                   :958        consults the limiter and returns when it refuses
```

«1» [`aer_isr_one_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1405) counts the message class at the root, a stop the other two routes skip. «2» [`add_error_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L985) asks the listed function's limiter and sets the record's flags. «3» [`aer_print_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L865) counts the record in the function's own counters on the native and DPC routes. «4» `aer_print_error()` traces the record before any print decision. «5» `aer_print_error()` returns before printing when the slot's flag is 0. «6» [`dpc_get_aer_uncorrect_severity()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L236) presets the flag of the DPC record, so the DPC route meets no limiter. «7» [`pci_print_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L926) counts the firmware's record in the function's counters. «8» `pci_print_aer()` traces that record before its print decision. «9» `pci_print_aer()` asks the limiter itself and returns when it refuses.

On the three routes the count and the trace come first, and the routes differ in who makes the print decision, the search's flags, DPC's preset or the limiter at print time.

### pci_dev_aer_stats_incr counts the record and each set bit

A function's counters answer two questions, how many reports of a class it logged and which errors those reports carried. [`pci_dev_aer_stats_incr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L747) updates both for one record, choosing the arrays by the record's class; read it for the choice, the bound of the per-bit loop and the crash-dump call.

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

`status`, a local of [`pci_dev_aer_stats_incr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L747), holds the unmasked bits, so a masked bit is not counted. The class total grows by one per record, and the loop adds one to the counter of each set bit below `max`, which is [`AER_MAX_TYPEOF_COR_ERRS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L46) or [`AER_MAX_TYPEOF_UNCOR_ERRS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L47). A non-fatal record also calls [`hwerr_log_error_type()`](https://elixir.bootlin.com/linux/v7.2/source/kernel/vmcore_info.c#L130) with [`HWERR_RECOV_PCI`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/vmcore.h#L21), the next subsection's subject, and a function without [`aer_info`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L371) returns before any count. One bit position indexes the status, the counter array and the name table, as the figure shows for a correctable record.

```text
    One bit position indexes the status, the counter array and the name table
    ─────────────────────────────────────────────────────────────────────────

    (correctable class, a record whose unmasked status has bits 6 and 12 set)

    index i                    0   1   2   3   4   5   6   7   8   9  10  11  12  13  14  15
                             ┌───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┐
    status & ~mask           │ 0 │ 0 │ 0 │ 0 │ 0 │ 0 │ 1 │ 0 │ 0 │ 0 │ 0 │ 0 │ 1 │ 0 │ 0 │ 0 │  one bit a cell
                             └───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───┘
                                                       │ +1                    │ +1
                                                       ▼                       ▼
                             ┌───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┐
    dev_cor_errs[]           │   │   │   │   │   │   │   │   │   │   │   │   │   │   │   │   │  a u64 a cell
                             └───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───┘

                             ┌───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┐
    aer_correctable_         │ R │ · │ · │ · │ · │ · │ B │ D │ N │ · │ · │ · │ T │ A │ I │ O │  a name a cell
    error_string[]           └───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───┘

    dev_total_cor_errs: +1 for the record, whatever its bits

    R RxErr  B BadTLP  D BadDLLP  N Rollover  T Timeout  A NonFatalErr  I CorrIntErr  O HeaderOF  · NULL
    the counter loop stops at AER_MAX_TYPEOF_COR_ERRS (16); the printer walks all 32 bits of status & ~mask
```

The printer and the counter files read the same position of [`aer_correctable_error_string`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L477), so a bit's printed name and its line in the counter file agree. A record with two bits set therefore adds one to the class total and one to each of the two bit counters, which is why a total can be smaller than the sum of the bit counts.

### Non-fatal reports also mark the crash-dump record

A crash dump can show whether recoverable hardware errors came shortly before a panic, and with [`CONFIG_VMCORE_INFO`](https://elixir.bootlin.com/linux/v7.2/source/kernel/Kconfig.kexec#L8) the kernel keeps a count and a timestamp per error source for tools that read the dump, as the message of commit commit [3fa805c37dd4](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=3fa805c37dd4d3e72ae5c58800f3f46ab3ca1f70) ("vmcoreinfo: track and log recoverable hardware errors") explains. The AER code contributes its non-fatal reports. [`hwerr_log_error_type()`](https://elixir.bootlin.com/linux/v7.2/source/kernel/vmcore_info.c#L130) records one error of a source; read it for the bound check and the two writes.

```c
/* kernel/vmcore_info.c:130 */
void hwerr_log_error_type(enum hwerr_error_type src)
{
	if (src < 0 || src >= HWERR_RECOV_MAX)
		return;

	atomic_inc(&hwerr_data[src].count);
	WRITE_ONCE(hwerr_data[src].timestamp, ktime_get_real_seconds());
}
```

An out-of-range source is ignored, the count grows through `atomic_inc()` and the timestamp takes the wall-clock seconds through `WRITE_ONCE()`. The array it writes, [`hwerr_data`](https://elixir.bootlin.com/linux/v7.2/source/kernel/vmcore_info.c#L41), holds one [`struct hwerr_info`](https://elixir.bootlin.com/linux/v7.2/source/kernel/vmcore_info.c#L32) per source:

```c
/* kernel/vmcore_info.c:32 */
struct hwerr_info {
	atomic_t count;
	time64_t timestamp;
};

/*
 * The hwerr_data[] array is declared with global scope so that it remains
 * accessible to vmcoreinfo even when Link Time Optimization (LTO) is enabled.
 */
struct hwerr_info hwerr_data[HWERR_RECOV_MAX];
```

The comment gives the reason for the global scope, that vmcoreinfo can reach the array under Link Time Optimization. The sources are numbered by [`enum hwerr_error_type`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/vmcore.h#L18):

```c
/* include/uapi/linux/vmcore.h:18 */
enum hwerr_error_type {
	HWERR_RECOV_CPU,
	HWERR_RECOV_MEMORY,
	HWERR_RECOV_PCI,
	HWERR_RECOV_CXL,
	HWERR_RECOV_OTHERS,
	HWERR_RECOV_MAX,
};
```

[`HWERR_RECOV_PCI`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/vmcore.h#L21) is the slot the AER code writes, and [`HWERR_RECOV_MAX`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/vmcore.h#L24) sizes the array and bounds the check. Without [`CONFIG_VMCORE_INFO`](https://elixir.bootlin.com/linux/v7.2/source/kernel/Kconfig.kexec#L8) the header replaces the function with an empty stub:

```c
/* include/linux/vmcore_info.h:82 */
#ifdef CONFIG_VMCORE_INFO
void hwerr_log_error_type(enum hwerr_error_type src);
#else
static inline void hwerr_log_error_type(enum hwerr_error_type src) {};
#endif
```

[`CONFIG_PROC_KCORE`](https://elixir.bootlin.com/linux/v7.2/source/fs/proc/Kconfig#L32), set in the x86-64 defconfig, selects the option, so the AER call records into the array:

```c
/* fs/proc/Kconfig:32 */
config PROC_KCORE
	bool "/proc/kcore support" if !ARM
	depends on PROC_FS && MMU
	select VMCORE_INFO
```

The other writers of the array are the x86 machine-check handler and the firmware-first error handler, and the figure places the AER slot among them.

```text
    Recoverable hardware errors from several sources share one array a crash dump reads
    ───────────────────────────────────────────────────────────────────────────────────

    (each slot is a struct hwerr_info, a count and the time of the last report)

                                                   hwerr_data[], indexed by enum hwerr_error_type
                                                 ┌─────────────────────────┬───────────────────────────────────┐
    firmware processor section ─────────────────▶│ [0] HWERR_RECOV_CPU     │ count, timestamp                  │
    firmware memory section ────────────────────▶│ [1] HWERR_RECOV_MEMORY  │ count, timestamp                  │
    AER non-fatal report ───────────────────┬───▶│ [2] HWERR_RECOV_PCI     │ count, timestamp ◀ +1, now        │
    firmware PCIe section ──────────────────┘    │ [3] ·                   │ count, timestamp                  │
    machine check, other sections ──────────────▶│ [4] HWERR_RECOV_OTHERS  │ count, timestamp                  │
                                                 └─────────────────────────┴───────────────────────────────────┘

    · = a slot of a bus this page leaves out; the firmware sources need CONFIG_ACPI_APEI_GHES;
    correctable and fatal AER reports take no slot
```

Within the AER code only non-fatal reports reach the slot, since [`pci_dev_aer_stats_incr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L747) calls the function in its [`AER_NONFATAL`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L14) branch alone. [`ghes_log_hwerr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L878) writes the same slot for a firmware PCIe section under [`CONFIG_ACPI_APEI_GHES`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Kconfig#L20), and [`do_machine_check()`](https://elixir.bootlin.com/linux/v7.2/source/arch/x86/kernel/cpu/mce/core.c#L1528) writes [`HWERR_RECOV_OTHERS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/vmcore.h#L23) for a machine check that did not panic; neither is shown here, because their sources are outside PCIe.

So far, a native report has been counted at the root, listed with its limiter's answer, read from the function's registers, and counted per bit in the function's object and, when non-fatal, in the crash-dump array; the tracepoint and the printed lines come next.

### The aer_event tracepoint records each counted report

The trace event records a report whatever the limiter decides, so a tool that reads it sees the reports the counters count, each with its bits and its TLP header. The event belongs to the ras trace system that [`ras_event.h:2-3`](https://elixir.bootlin.com/linux/v7.2/source/include/ras/ras_event.h#L2) names:

```c
/* include/ras/ras_event.h:2 */
#undef TRACE_SYSTEM
#define TRACE_SYSTEM ras
```

Its full name is therefore `ras:aer_event`, and with [`CONFIG_TRACEPOINTS`](https://elixir.bootlin.com/linux/v7.2/source/init/Kconfig#L2254), which [`CONFIG_BLK_DEV_IO_TRACE`](https://elixir.bootlin.com/linux/v7.2/source/kernel/trace/Kconfig#L731) of the x86-64 defconfig selects, the call in [`aer_print_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L865) records an entry. The definition is compiled under [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28), a guard that commit [a3b366dbf468](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=a3b366dbf468788baa2e0ccdccd8482ac277e47b) ("tracing, AER: Hide PCIe AER event when PCIEAER is not configured") added, and a comment above it describes the fields:

```c
/* include/ras/ras_event.h:293 */
#ifdef CONFIG_PCIEAER
/*
 * PCIe AER Trace event
 *
 * These events are generated when hardware detects a corrected or
 * uncorrected event on a PCIe device. The event report has
 * the following structure:
 *
 * char * dev_name -	The name of the slot where the device resides
 *			([domain:]bus:device.function).
 * u32 status -		Either the correctable or uncorrectable register
 *			indicating what error or errors have been seen
 * u8 severity -	error severity 0:NONFATAL 1:FATAL 2:CORRECTED
 */
```

The two tables at [`ras_event.h:308-335`](https://elixir.bootlin.com/linux/v7.2/source/include/ras/ras_event.h#L308) name the status bits in a read entry; they follow the comment:

```c
/* include/ras/ras_event.h:308 */
#define aer_correctable_errors					\
	{PCI_ERR_COR_RCVR,	"Receiver Error"},		\
	{PCI_ERR_COR_BAD_TLP,	"Bad TLP"},			\
	{PCI_ERR_COR_BAD_DLLP,	"Bad DLLP"},			\
	{PCI_ERR_COR_REP_ROLL,	"RELAY_NUM Rollover"},		\
	{PCI_ERR_COR_REP_TIMER,	"Replay Timer Timeout"},	\
	{PCI_ERR_COR_ADV_NFAT,	"Advisory Non-Fatal Error"},	\
	{PCI_ERR_COR_INTERNAL,	"Corrected Internal Error"},	\
	{PCI_ERR_COR_LOG_OVER,	"Header Log Overflow"}

#define aer_uncorrectable_errors				\
	{PCI_ERR_UNC_UND,	"Undefined"},			\
	{PCI_ERR_UNC_DLP,	"Data Link Protocol Error"},	\
	{PCI_ERR_UNC_SURPDN,	"Surprise Down Error"},		\
	{PCI_ERR_UNC_POISON_TLP,"Poisoned TLP"},		\
	{PCI_ERR_UNC_FCP,	"Flow Control Protocol Error"},	\
	{PCI_ERR_UNC_COMP_TIME,	"Completion Timeout"},		\
	{PCI_ERR_UNC_COMP_ABORT,"Completer Abort"},		\
	{PCI_ERR_UNC_UNX_COMP,	"Unexpected Completion"},	\
	{PCI_ERR_UNC_RX_OVER,	"Receiver Overflow"},		\
	{PCI_ERR_UNC_MALF_TLP,	"Malformed TLP"},		\
	{PCI_ERR_UNC_ECRC,	"ECRC Error"},			\
	{PCI_ERR_UNC_UNSUP,	"Unsupported Request Error"},	\
	{PCI_ERR_UNC_ACSV,	"ACS Violation"},		\
	{PCI_ERR_UNC_INTN,	"Uncorrectable Internal Error"},\
	{PCI_ERR_UNC_MCBTLP,	"MC Blocked TLP"},		\
	{PCI_ERR_UNC_ATOMEG,	"AtomicOp Egress Blocked"},	\
	{PCI_ERR_UNC_TLPPRE,	"TLP Prefix Blocked Error"}
```

The correctable table names the eight bits that [`aer_correctable_error_string`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L477) names. The uncorrectable table stops at [`PCI_ERR_UNC_TLPPRE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L789), bit 25, so the six defined bits above it have no name in a read entry. `TRACE_EVENT(aer_event, ...)` at [`ras_event.h:337`](https://elixir.bootlin.com/linux/v7.2/source/include/ras/ras_event.h#L337) generates [`trace_aer_event()`](https://elixir.bootlin.com/linux/v7.2/source/include/ras/ras_event.h#L337), and the outline gives its four pieces.

| piece | lines | stage |
|---|---|---|
| Ⓐ | ras_event.h:337-347 | the prototype and the argument list |
| Ⓑ | ras_event.h:348-356 | the fields of an entry |
| Ⓒ | ras_event.h:357-370 | the copy of the arguments into an entry |
| Ⓓ | ras_event.h:371-382 | the format of an entry read back |

Ⓐ The first piece of the event at [`ras_event.h:337-347`](https://elixir.bootlin.com/linux/v7.2/source/include/ras/ras_event.h#L337) declares the six arguments that [`aer_print_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L865) and [`pci_print_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L926) pass:

```c
/* include/ras/ras_event.h:337 */
TRACE_EVENT(aer_event,
	TP_PROTO(const char *dev_name,
		 const u32 status,
		 const u8 severity,
		 const u8 tlp_header_valid,
		 struct pcie_tlp_log *tlp,
		 const char *bus_type),


	TP_ARGS(dev_name, status, severity, tlp_header_valid, tlp, bus_type),

```

The arguments are the function's name, the unmasked status, the class, the validity of the TLP header, the logged TLP and the bus-type word. Ⓑ The second piece at [`ras_event.h:348-356`](https://elixir.bootlin.com/linux/v7.2/source/include/ras/ras_event.h#L348) lays out an entry:

```c
/* include/ras/ras_event.h:348 */
	TP_STRUCT__entry(
		__string(	dev_name,	dev_name	)
		__field(	u32,		status		)
		__field(	u8,		severity	)
		__field(	u8, 		tlp_header_valid)
		__array(	u32, 		tlp_header, PCIE_STD_MAX_TLP_HEADERLOG)
		__string(	bus_type,	bus_type	)
	),

```

The entry keeps the two strings, the status, the class and the validity, and a fixed array of [`PCIE_STD_MAX_TLP_HEADERLOG`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L25) dwords for the TLP, a size that include/linux/aer.h derives from the four dwords of a standard header:

```c
/* include/linux/aer.h:23 */
#define PCIE_STD_NUM_TLP_HEADERLOG     4
#define PCIE_STD_MAX_TLP_PREFIXLOG     4
#define PCIE_STD_MAX_TLP_HEADERLOG	(PCIE_STD_NUM_TLP_HEADERLOG + 10)
```

The array thus holds fourteen dwords, room for a TLP logged in Flit Mode. Ⓒ The third piece at [`ras_event.h:357-370`](https://elixir.bootlin.com/linux/v7.2/source/include/ras/ras_event.h#L357) copies the arguments:

```c
/* include/ras/ras_event.h:357 */
	TP_fast_assign(
		__assign_str(dev_name);
		__assign_str(bus_type);
		__entry->status		= status;
		__entry->severity	= severity;
		__entry->tlp_header_valid = tlp_header_valid;
		if (tlp_header_valid) {
			int i;

			for (i = 0; i < PCIE_STD_MAX_TLP_HEADERLOG; i++)
				__entry->tlp_header[i] = tlp->dw[i];
		}
	),

```

The TLP is copied only when `tlp_header_valid`, an argument of the event, is set, and then all fourteen dwords of [`dw`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L31) are copied. Ⓓ The fourth piece at [`ras_event.h:371-382`](https://elixir.bootlin.com/linux/v7.2/source/include/ras/ras_event.h#L371) formats an entry when tracefs reads it:

```c
/* include/ras/ras_event.h:371 */
	TP_printk("%s %s Bus Error: severity=%s, %s, TLP Header=%s\n",
		__get_str(dev_name), __get_str(bus_type),
		__entry->severity == AER_CORRECTABLE ? "Corrected" :
			__entry->severity == AER_FATAL ?
			"Fatal" : "Uncorrected, non-fatal",
		__entry->severity == AER_CORRECTABLE ?
		__print_flags(__entry->status, "|", aer_correctable_errors) :
		__print_flags(__entry->status, "|", aer_uncorrectable_errors),
		__entry->tlp_header_valid ?
			__print_array(__entry->tlp_header, PCIE_STD_MAX_TLP_HEADERLOG, 4) :
			"Not available")
);
```

The class becomes "Corrected", "Fatal" or "Uncorrected, non-fatal", the status is named through [`__print_flags`](https://elixir.bootlin.com/linux/v7.2/source/include/trace/stages/stage3_trace_output.h#L67) with the table of the class, and the TLP prints as fourteen dwords or "Not available". [`__print_flags`](https://elixir.bootlin.com/linux/v7.2/source/include/trace/stages/stage3_trace_output.h#L67) hands the table to [`trace_print_flags_seq()`](https://elixir.bootlin.com/linux/v7.2/source/kernel/trace/trace_output.c#L70):

```c
/* include/trace/stages/stage3_trace_output.h:66 */
#undef __print_flags
#define __print_flags(flag, delim, flag_array...)					\
	({										\
		static const struct trace_print_flags __flags[] =			\
			{ flag_array };							\
		trace_print_flags_seq(p, delim, flag, __flags, ARRAY_SIZE(__flags));	\
	})
```

[`trace_print_flags_seq()`](https://elixir.bootlin.com/linux/v7.2/source/kernel/trace/trace_output.c#L70) names each table entry whose mask is set and prints what remains as a hexadecimal value; read the stage that handles the remainder.

```c
/* kernel/trace/trace_output.c:70 */
trace_print_flags_seq(struct trace_seq *p, const char *delim,
		      unsigned long flags,
		      const struct trace_print_flags *flag_array,
		      size_t flag_array_size)
	... /* 21 lines, to :95 */
	/* check for left over flags */
	if (flags) {
		if (!first && delim)
			trace_seq_puts(p, delim);
		trace_seq_printf(p, "0x%lx", flags);
	}

	trace_seq_putc(p, 0);

	return ret;
}
```

A set bit without a table entry, bits 26 to 31 of an uncorrectable status, therefore reaches the reader as a number after the names. The figure lines the caller's values up with the entry's fields.

```text
    The tracepoint copies a record into a fixed entry and names its bits when the entry is read
    ───────────────────────────────────────────────────────────────────────────────────────────

    what the caller passes                       the entry ras:aer_event stores
    ┌────────────────────────────────┐           ┌─────────────────────────────────┐
    │ the function's name            ├──────────▶│ dev_name     string             │
    │ status & ~mask                 ├──────────▶│ status       u32                │
    │ severity                       ├──────────▶│ severity     u8                 │
    │ tlp_header_valid               ├──────────▶│ tlp_header_valid  u8            │
    │ the logged TLP, dw[0] to dw[13]├──────────▶│ tlp_header[14]  u32 each        │  ◀ copied only when
    │ "PCIe"                         ├──────────▶│ bus_type     string             │    tlp_header_valid is 1
    └────────────────────────────────┘           └─────────────────────────────────┘

    read back through tracefs, one entry prints as
      <dev_name> <bus_type> Bus Error: severity=<Corrected | Fatal | Uncorrected, non-fatal>,
      <status bits named and joined by |>, TLP Header=<fourteen dwords | Not available>
```

An entry is written in the thread or work item that handled the report, so its timestamp is the report's time, and reading it needs tracefs only, under `/sys/kernel/tracing/events/ras/aer_event`.

### Status bits decide the printed layer and agent

The header line of a report names the protocol layer and the agent that detected the error, two facts the AER registers hold in no field of their own. aer.c derives both from the status bits with two macros that test masks in a fixed order, and the table gives the outcome of each test.

| class | layer, first test that matches | agent, first test that matches |
|---|---|---|
| correctable | Physical Layer on [`PCI_ERR_COR_RCVR`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L801); Data Link Layer on [`PCI_ERR_COR_BAD_TLP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L802), [`PCI_ERR_COR_BAD_DLLP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L803), [`PCI_ERR_COR_REP_ROLL`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L804) or [`PCI_ERR_COR_REP_TIMER`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L805); Transaction Layer otherwise | Transmitter ID on [`PCI_ERR_COR_REP_ROLL`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L804) or [`PCI_ERR_COR_REP_TIMER`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L805); Receiver ID otherwise |
| non-fatal or fatal | Data Link Layer on [`PCI_ERR_UNC_DLP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L774); Transaction Layer otherwise | Completer ID on [`PCI_ERR_UNC_COMP_ABORT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L779); Requester ID on [`PCI_ERR_UNC_COMP_TIME`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L778) or [`PCI_ERR_UNC_UNSUP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L784); Receiver ID otherwise |

[`AER_GET_AGENT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L439) tests the completer mask, then the requester mask, then the transmitter mask, each built for the record's class by the macros above it:

```c
/* drivers/pci/pcie/aer.c:427 */
#define AER_AGENT_RECEIVER		0
#define AER_AGENT_REQUESTER		1
#define AER_AGENT_COMPLETER		2
#define AER_AGENT_TRANSMITTER		3

#define AER_AGENT_REQUESTER_MASK(t)	((t == AER_CORRECTABLE) ?	\
	0 : (PCI_ERR_UNC_COMP_TIME|PCI_ERR_UNC_UNSUP))
#define AER_AGENT_COMPLETER_MASK(t)	((t == AER_CORRECTABLE) ?	\
	0 : PCI_ERR_UNC_COMP_ABORT)
#define AER_AGENT_TRANSMITTER_MASK(t)	((t == AER_CORRECTABLE) ?	\
	(PCI_ERR_COR_REP_ROLL|PCI_ERR_COR_REP_TIMER) : 0)

#define AER_GET_AGENT(t, e)						\
	((e & AER_AGENT_COMPLETER_MASK(t)) ? AER_AGENT_COMPLETER :	\
	(e & AER_AGENT_REQUESTER_MASK(t)) ? AER_AGENT_REQUESTER :	\
	(e & AER_AGENT_TRANSMITTER_MASK(t)) ? AER_AGENT_TRANSMITTER :	\
	AER_AGENT_RECEIVER)
```

A mask that does not apply to the class is 0, so its test fails and the next one runs, and a record that matches none is attributed to the receiver. [`AER_GET_LAYER_ERROR`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L457) follows the same pattern with two masks, and [`aer_error_layer`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L471) holds the names its values index:

```c
/* drivers/pci/pcie/aer.c:445 */
#define AER_PHYSICAL_LAYER_ERROR	0
#define AER_DATA_LINK_LAYER_ERROR	1
#define AER_TRANSACTION_LAYER_ERROR	2

#define AER_PHYSICAL_LAYER_ERROR_MASK(t) ((t == AER_CORRECTABLE) ?	\
	PCI_ERR_COR_RCVR : 0)
#define AER_DATA_LINK_LAYER_ERROR_MASK(t) ((t == AER_CORRECTABLE) ?	\
	(PCI_ERR_COR_BAD_TLP|						\
	PCI_ERR_COR_BAD_DLLP|						\
	PCI_ERR_COR_REP_ROLL|						\
	PCI_ERR_COR_REP_TIMER) : PCI_ERR_UNC_DLP)

#define AER_GET_LAYER_ERROR(t, e)					\
	((e & AER_PHYSICAL_LAYER_ERROR_MASK(t)) ? AER_PHYSICAL_LAYER_ERROR : \
	(e & AER_DATA_LINK_LAYER_ERROR_MASK(t)) ? AER_DATA_LINK_LAYER_ERROR : \
	AER_TRANSACTION_LAYER_ERROR)
... /* 10 lines, to :471 */
static const char *aer_error_layer[] = {
	"Physical Layer",
	"Data Link Layer",
	"Transaction Layer"
};
```

The agent's names are in [`aer_agent_string`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L547), indexed by the values of [`AER_AGENT_RECEIVER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L427) and its three companions:

```c
/* drivers/pci/pcie/aer.c:547 */
static const char *aer_agent_string[] = {
	"Receiver ID",
	"Requester ID",
	"Completer ID",
	"Transmitter ID"
};
```

A record whose bits fall into several kinds is named after the first test that matches, so the header names one layer and one agent for the whole record.

### A report prints its header, bits and TLP header

A reader of the kernel log meets a report as its lines, which come in a fixed order for each slot whose flag is 1. ❷ The second piece of [`aer_print_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L865) prints them:

```c
/* drivers/pci/pcie/aer.c:885 */
	if (!info->status) {
		pci_err(dev, "%s Bus Error: severity=%s, type=Inaccessible, (Unregistered Agent ID)\n",
			bus_type, aer_error_severity_string[info->severity]);
		goto out;
	}

	layer = AER_GET_LAYER_ERROR(info->severity, info->status);
	agent = AER_GET_AGENT(info->severity, info->status);

	aer_printk(level, dev, "%s Bus Error: severity=%s, type=%s, (%s)\n",
		   bus_type, aer_error_severity_string[info->severity],
		   aer_error_layer[layer], aer_agent_string[agent]);

	aer_printk(level, dev, "  device [%04x:%04x] error status/mask=%08x/%08x\n",
		   dev->vendor, dev->device, info->status, info->mask);

	__aer_print_error(dev, info);

	if (info->tlp_header_valid)
		pcie_print_tlp_log(dev, &info->tlp, level, dev_fmt("  "));

out:
	if (info->id && info->error_dev_num > 1 && info->id == id)
		pci_err(dev, "  Error of this Agent is reported first\n");
}
```

A record whose [`status`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L851) is 0, the fatal case the status read could not read, prints one "Inaccessible" line through [`pci_err()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2891). Otherwise the header names the bus type, the class from [`aer_error_severity_string`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L465) and the layer and agent, which the two macros compute from the status with its masked bits included. The device line prints [`vendor`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L362), [`device`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L363) and the raw status and mask, [`__aer_print_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L829) adds the bit lines, the TLP header follows when [`tlp_header_valid`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L849) is 1, and a last line marks the function the root's message named when the search listed more than one. The lines go through [`aer_printk`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L41) with the record's level, and aer.c sets the prefix of every message it prints with [`pr_fmt`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L15) and [`dev_fmt`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L16):

```c
/* drivers/pci/pcie/aer.c:15 */
#define pr_fmt(fmt) "AER: " fmt
#define dev_fmt pr_fmt
```

[`dev_fmt`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L16) makes the device printing helpers add the same "AER: " prefix after the function's name. [`aer_printk`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L41) wraps `dev_printk()` with the level as its first argument:

```c
/* drivers/pci/pcie/aer.c:41 */
#define aer_printk(level, pdev, fmt, arg...) \
	dev_printk(level, &(pdev)->dev, fmt, ##arg)
```

[`__aer_print_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L829) prints the bit lines of one record; read it for the name lookup and the "(First)" marker.

```c
/* drivers/pci/pcie/aer.c:829 */
static void __aer_print_error(struct pci_dev *dev, struct aer_err_info *info)
{
	const char **strings;
	unsigned long status = info->status & ~info->mask;
	const char *level = info->level;
	const char *errmsg;
	int i;

	if (info->severity == AER_CORRECTABLE)
		strings = aer_correctable_error_string;
	else
		strings = aer_uncorrectable_error_string;

	for_each_set_bit(i, &status, 32) {
		errmsg = strings[i];
		if (!errmsg)
			errmsg = "Unknown Error Bit";

		aer_printk(level, dev, "   [%2d] %-22s%s\n", i, errmsg,
				info->first_error == i ? " (First)" : "");
	}
}
```

The loop visits the unmasked set bits of all 32 positions and prints the bit number, the name from [`aer_correctable_error_string`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L477) or [`aer_uncorrectable_error_string`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L512), or "Unknown Error Bit" for a NULL entry, and "(First)" on the bit that [`first_error`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L846) points at. The correctable table names the bits of the Correctable Error Status register:

```c
/* drivers/pci/pcie/aer.c:477 */
static const char *aer_correctable_error_string[] = {
	"RxErr",			/* Bit Position 0	*/
	NULL,
	NULL,
	NULL,
	NULL,
	NULL,
	"BadTLP",			/* Bit Position 6	*/
	"BadDLLP",			/* Bit Position 7	*/
	"Rollover",			/* Bit Position 8	*/
	NULL,
	NULL,
	NULL,
	"Timeout",			/* Bit Position 12	*/
	"NonFatalErr",			/* Bit Position 13	*/
	"CorrIntErr",			/* Bit Position 14	*/
	"HeaderOF",			/* Bit Position 15	*/
	NULL,				/* Bit Position 16	*/
	NULL,				/* Bit Position 17	*/
	NULL,				/* Bit Position 18	*/
	NULL,				/* Bit Position 19	*/
	NULL,				/* Bit Position 20	*/
	NULL,				/* Bit Position 21	*/
	NULL,				/* Bit Position 22	*/
	NULL,				/* Bit Position 23	*/
	NULL,				/* Bit Position 24	*/
	NULL,				/* Bit Position 25	*/
	NULL,				/* Bit Position 26	*/
	NULL,				/* Bit Position 27	*/
	NULL,				/* Bit Position 28	*/
	NULL,				/* Bit Position 29	*/
	NULL,				/* Bit Position 30	*/
	NULL,				/* Bit Position 31	*/
};
```

[`aer_uncorrectable_error_string`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L512) names the bits of the Uncorrectable Error Status register, the fatal and non-fatal classes sharing it:

```c
/* drivers/pci/pcie/aer.c:512 */
static const char *aer_uncorrectable_error_string[] = {
	"Undefined",			/* Bit Position 0	*/
	NULL,
	NULL,
	NULL,
	"DLP",				/* Bit Position 4	*/
	"SDES",				/* Bit Position 5	*/
	NULL,
	NULL,
	NULL,
	NULL,
	NULL,
	NULL,
	"TLP",				/* Bit Position 12	*/
	"FCP",				/* Bit Position 13	*/
	"CmpltTO",			/* Bit Position 14	*/
	"CmpltAbrt",			/* Bit Position 15	*/
	"UnxCmplt",			/* Bit Position 16	*/
	"RxOF",				/* Bit Position 17	*/
	"MalfTLP",			/* Bit Position 18	*/
	"ECRC",				/* Bit Position 19	*/
	"UnsupReq",			/* Bit Position 20	*/
	"ACSViol",			/* Bit Position 21	*/
	"UncorrIntErr",			/* Bit Position 22	*/
	"BlockedTLP",			/* Bit Position 23	*/
	"AtomicOpBlocked",		/* Bit Position 24	*/
	"TLPBlockedErr",		/* Bit Position 25	*/
	"PoisonTLPBlocked",		/* Bit Position 26	*/
	"DMWrReqBlocked",		/* Bit Position 27	*/
	"IDECheck",			/* Bit Position 28	*/
	"MisIDETLP",			/* Bit Position 29	*/
	"PCRC_CHECK",			/* Bit Position 30	*/
	"TLPXlatBlocked",		/* Bit Position 31	*/
};
```

Both tables have 32 entries with NULL at the positions no macro defines, which is where "Unknown Error Bit" comes from. The TLP header line is printed by [`pcie_print_tlp_log()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L106), which formats the logged dwords and prints them with the level and prefix it is given; read the stage that prints.

```c
/* drivers/pci/pcie/tlp.c:106 */
void pcie_print_tlp_log(const struct pci_dev *dev,
			const struct pcie_tlp_log *log, const char *level,
			const char *pfx)
	... /* 26 lines, to :135 */
	dev_printk(level, &dev->dev, "%sTLP Header%s: %s\n", pfx,
		log->flit ? " (Flit)" : "", buf);
}
```

The line reads "TLP Header", or "TLP Header (Flit)" for a TLP logged in Flit Mode, at the record's level. The figure maps the record's fields onto the lines in their order.

```text
    A function's report reads the record field by field, one line or group of lines each
    ────────────────────────────────────────────────────────────────────────────────────

    fields of record i             lines of one function's report, in print order
    ┌───────────────────────┐      ┌─────────────────────────────────────────────────────────────────────────────┐
    │ severity, status      ├─────▶│ PCIe Bus Error: severity=<class>, type=<layer>, (<agent>)                   │
    │                       │      ├─────────────────────────────────────────────────────────────────────────────┤
    │ status, mask          ├─────▶│   device [<vendor>:<device>] error status/mask=<status>/<mask>              │
    │                       │      ├─────────────────────────────────────────────────────────────────────────────┤
    │ first_error           ├─────▶│    [<i>] <name of bit i>  (First)                one line per unmasked bit  │
    │                       │      ├─────────────────────────────────────────────────────────────────────────────┤
    │ tlp_header_valid, tlp ├─────▶│   TLP Header: <dwords>                               when tlp_header_valid  │
    │                       │      ├─────────────────────────────────────────────────────────────────────────────┤
    │ id, error_dev_num     ├─────▶│   Error of this Agent is reported first           when the Source ID is it  │
    └───────────────────────┘      └─────────────────────────────────────────────────────────────────────────────┘

    each line begins with the function's name and "AER: "; the first four rows print at the record's
    level, KERN_WARNING for a correctable record and KERN_ERR otherwise, the last row at KERN_ERR;
    a record whose status is 0 prints "... type=Inaccessible, (Unregistered Agent ID)" instead of rows 1 to 4
```

Each slot with its flag set thus prints a header, a device line, one line per unmasked bit and the optional TLP and first-agent lines, all at the record's level except the first-agent line, which [`pci_err()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2891) prints at `KERN_ERR`.

### A DPC trigger prints its record without the limiter

Downstream Port Containment stops the traffic below a port when an uncorrectable error is detected, and with [`CONFIG_PCIE_DPC`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L121) the DPC handler prints the port's own AER registers through the same printer. [`dpc_handler()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L363) runs in the IRQ thread of the DPC service; read it for the order of printing and recovery and for the comment that DPC is set to trigger on ERR_FATAL.

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

[`dpc_process_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L264) prints before [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) recovers the hierarchy with [`dpc_reset_link()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L148) as the reset, a step this page leaves to the recovery code. [`dpc_process_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L264) reads the trigger reason and prints an uncorrectable error that the port detected itself; read the stage for that branch.

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

The record starts zeroed, and [`dpc_get_aer_uncorrect_severity()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L236) fills it before the status read and [`aer_print_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L865) with slot 0; read it for the class and the preset flag.

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

The class is fatal when an unmasked status bit is also set in the Uncorrectable Error Severity register and non-fatal otherwise, the port itself takes slot 0, and its [`ratelimit_print`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L835) is set to 1. The DPC route consults no limiter, counts nothing at the root and prints no source line, since [`aer_print_source()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L852) is not called on it. A DPC report is therefore counted, traced and printed in full each time, the behavior the AER documentation states for fatal and DPC errors.

### Firmware-first reports reach the same counters and limiter

With firmware-first error handling the platform firmware reads a function's AER registers and passes them to the kernel in a record, and [`pci_print_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L926) turns such a record into the same counts, trace entry and limited lines. [`CONFIG_ACPI_APEI_GHES`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Kconfig#L20) and [`CONFIG_ACPI_APEI_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Kconfig#L37), both unset in the x86-64 defconfig, compile this route in; with them set, the work item [`aer_recover_work_func()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1218) calls [`pci_print_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L926) for each record that [`aer_recover_queue()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1263) queued. Read the stage for that call.

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
```

The work item finds the function by domain, bus and devfn, prints the record and then recovers the function, which this page leaves to the recovery code. The registers arrive in a [`struct aer_capability_regs`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L41), and the outline gives the two pieces of [`pci_print_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L926).

| piece | lines | stage |
|---|---|---|
| ⒜ | aer.c:926-958 | builds a record, counts, traces and asks the limiter |
| ⒝ | aer.c:959-977 | prints the status line, the bits, the layer and agent, the severity register and the TLP header |

⒜ The first piece of [`pci_print_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L926) builds a record from the firmware's registers, counts, traces and asks the limiter:

```c
/* drivers/pci/pcie/aer.c:926 */
void pci_print_aer(struct pci_dev *dev, int aer_severity,
		   struct aer_capability_regs *aer)
{
	const char *bus_type;
	int layer, agent, tlp_header_valid = 0;
	u32 status, mask;
	struct aer_err_info info = {
		.severity = aer_severity,
		.first_error = PCI_ERR_CAP_FEP(aer->cap_control),
	};

	if (aer_severity == AER_CORRECTABLE) {
		status = aer->cor_status;
		mask = aer->cor_mask;
		info.level = KERN_WARNING;
	} else {
		status = aer->uncor_status;
		mask = aer->uncor_mask;
		info.level = KERN_ERR;
		tlp_header_valid = tlp_header_logged(status, aer->cap_control);
	}

	info.status = status;
	info.mask = mask;
	info.is_cxl = pcie_is_cxl(dev);

	bus_type = aer_err_bus(&info);

	pci_dev_aer_stats_incr(dev, &info);
	trace_aer_event(pci_name(dev), (status & ~mask), aer_severity,
			tlp_header_valid, &aer->header_log, bus_type);

	if (!aer_ratelimit(dev, info.severity))
```

A correctable record takes [`cor_status`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L46) and [`cor_mask`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L47) with `KERN_WARNING`, the level that commit [36c5932074aa](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=36c5932074aaedebf905374dba2399a529215aa1) ("PCI/AER: Reduce pci_print_aer() correctable error level to KERN_WARNING") set, and the other classes take the uncorrectable pair with `KERN_ERR` and ask [`tlp_header_logged()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L815) with [`cap_control`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L48). The record is counted and traced before [`aer_ratelimit()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L800) is asked, so on this route the limiter is consulted at print time, once per record. ⒝ The second piece of [`pci_print_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L926) prints the lines:

```c
/* drivers/pci/pcie/aer.c:959 */
		return;

	layer = AER_GET_LAYER_ERROR(aer_severity, status);
	agent = AER_GET_AGENT(aer_severity, status);

	aer_printk(info.level, dev, "aer_status: 0x%08x, aer_mask: 0x%08x\n",
		   status, mask);
	__aer_print_error(dev, &info);
	aer_printk(info.level, dev, "aer_layer=%s, aer_agent=%s\n",
		   aer_error_layer[layer], aer_agent_string[agent]);

	if (aer_severity != AER_CORRECTABLE)
		aer_printk(info.level, dev, "aer_uncor_severity: 0x%08x\n",
			   aer->uncor_severity);

	if (tlp_header_valid)
		pcie_print_tlp_log(dev, &aer->header_log, info.level,
				   dev_fmt("  "));
}
```

The firmware route prints a status line, the bit lines of [`__aer_print_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L829), a layer and agent line, the [`uncor_severity`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L45) register for an uncorrectable record and the TLP header, all at the record's level. Commit commit [deb2f228388f](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=deb2f228388ff3a9d0623e3b59a053e9235c341d) ("PCI/AER: Avoid NULL pointer dereference in aer_ratelimit()") records why a function without [`aer_info`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L371) reaches this code, and such a function is neither counted nor limited.

So far, the three routes have been followed to their counters, their trace entry and their lines: the native route counts at the root and limits during the search, DPC prints without a limiter, and firmware records meet the limiter at print time.

### Counter files print each array with its total

The counters reach user space as read-only sysfs files of the function, generated by two macros and shown or hidden per function. [`aer_stats_dev_attr`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L554) generates the show function of a per-function counter file; read it for the lines a file prints.

```c
/* drivers/pci/pcie/aer.c:554 */
#define aer_stats_dev_attr(name, stats_array, strings_array,		\
			   total_string, total_field)			\
	static ssize_t							\
	name##_show(struct device *dev, struct device_attribute *attr,	\
		     char *buf)						\
{									\
	unsigned int i;							\
	struct pci_dev *pdev = to_pci_dev(dev);				\
	u64 *stats = pdev->aer_info->stats_array;			\
	size_t len = 0;							\
									\
	for (i = 0; i < ARRAY_SIZE(pdev->aer_info->stats_array); i++) {	\
		if (strings_array[i])					\
			len += sysfs_emit_at(buf, len, "%s %llu\n",	\
					     strings_array[i],		\
					     stats[i]);			\
		else if (stats[i])					\
			len += sysfs_emit_at(buf, len,			\
					     #stats_array "_bit[%d] %llu\n",\
					     i, stats[i]);		\
	}								\
	len += sysfs_emit_at(buf, len, "TOTAL_%s %llu\n", total_string,	\
			     pdev->aer_info->total_field);		\
	return len;							\
}									\
static DEVICE_ATTR_RO(name)
```

The loop runs over the counter array and prints "<name> <count>" for each position with a name, and "<array>_bit[<i>] <count>" for an unnamed position whose count is not 0, followed by a "TOTAL_<class> <total>" line. The names come from [`aer_correctable_error_string`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L477) or [`aer_uncorrectable_error_string`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L512), and [`aer_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1607) checks at build time that each table is at least as long as its counter array:

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
```

The two `BUILD_BUG_ON()` lines fail the build when a name table is shorter than its counter array, so the show loop cannot index past a table. Three invocations of [`aer_stats_dev_attr`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L554) make the per-function files:

```c
/* drivers/pci/pcie/aer.c:581 */
aer_stats_dev_attr(aer_dev_correctable, dev_cor_errs,
		   aer_correctable_error_string, "ERR_COR",
		   dev_total_cor_errs);
aer_stats_dev_attr(aer_dev_fatal, dev_fatal_errs,
		   aer_uncorrectable_error_string, "ERR_FATAL",
		   dev_total_fatal_errs);
aer_stats_dev_attr(aer_dev_nonfatal, dev_nonfatal_errs,
		   aer_uncorrectable_error_string, "ERR_NONFATAL",
		   dev_total_nonfatal_errs);
```

The invocations create `/sys/bus/pci/devices/<function>/aer_dev_correctable` and the files "aer_dev_fatal" and "aer_dev_nonfatal" beside it, and the fatal and non-fatal files share the uncorrectable names. [`aer_stats_rootport_attr`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L591) generates the show function of a Root Port total, which prints one number:

```c
/* drivers/pci/pcie/aer.c:591 */
#define aer_stats_rootport_attr(name, field)				\
	static ssize_t							\
	name##_show(struct device *dev, struct device_attribute *attr,	\
		     char *buf)						\
{									\
	struct pci_dev *pdev = to_pci_dev(dev);				\
	return sysfs_emit(buf, "%llu\n", pdev->aer_info->field);	\
}									\
static DEVICE_ATTR_RO(name)
```

Three more invocations make the Root Port files, and [`aer_stats_attrs`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L608) lists all six:

```c
/* drivers/pci/pcie/aer.c:601 */
aer_stats_rootport_attr(aer_rootport_total_err_cor,
			 rootport_total_cor_errs);
aer_stats_rootport_attr(aer_rootport_total_err_fatal,
			 rootport_total_fatal_errs);
aer_stats_rootport_attr(aer_rootport_total_err_nonfatal,
			 rootport_total_nonfatal_errs);

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

[`aer_stats_attrs_are_visible()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L618) decides per function which of the six files appear; read it for the two conditions.

```c
/* drivers/pci/pcie/aer.c:618 */
static umode_t aer_stats_attrs_are_visible(struct kobject *kobj,
					   struct attribute *a, int n)
{
	struct device *dev = kobj_to_dev(kobj);
	struct pci_dev *pdev = to_pci_dev(dev);

	if (!pdev->aer_info)
		return 0;

	if ((a == &dev_attr_aer_rootport_total_err_cor.attr ||
	     a == &dev_attr_aer_rootport_total_err_fatal.attr ||
	     a == &dev_attr_aer_rootport_total_err_nonfatal.attr) &&
	    ((pci_pcie_type(pdev) != PCI_EXP_TYPE_ROOT_PORT) &&
	     (pci_pcie_type(pdev) != PCI_EXP_TYPE_RC_EC)))
		return 0;

	return a->mode;
}
```

A function without [`aer_info`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L371) shows none of the files, and a function whose [`pci_pcie_type()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2678) is neither [`PCI_EXP_TYPE_ROOT_PORT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L488) nor [`PCI_EXP_TYPE_RC_EC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L494) shows the three per-function files alone. The show functions read the counters without a NULL test because a hidden file cannot be read. [`aer_stats_attr_group`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L637) joins the list and the visibility test:

```c
/* drivers/pci/pcie/aer.c:637 */
const struct attribute_group aer_stats_attr_group = {
	.attrs  = aer_stats_attrs,
	.is_visible = aer_stats_attrs_are_visible,
};
```

With [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28) the group enters [`pci_dev_attr_groups`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-sysfs.c#L1892), the attribute groups of every PCI function's sysfs directory:

```c
/* drivers/pci/pci-sysfs.c:1892 */
const struct attribute_group *pci_dev_attr_groups[] = {
	&pci_dev_attr_group,
	&pci_dev_hp_attr_group,
#ifdef CONFIG_PCI_IOV
	&sriov_pf_dev_attr_group,
	&sriov_vf_dev_attr_group,
#endif
	&pci_bridge_attr_group,
	&pcie_dev_attr_group,
#ifdef CONFIG_PCIEAER
	&aer_stats_attr_group,
	&aer_attr_group,
#endif
#ifdef CONFIG_PCIEASPM
	&aspm_ctrl_attr_group,
#endif
#ifdef CONFIG_PCI_DOE
	&pci_doe_sysfs_group,
#endif
#ifdef CONFIG_PCI_TSM
	&pci_tsm_auth_attr_group,
	&pci_tsm_attr_group,
#endif
	NULL,
};
```

The device type that the PCI core gives each function, [`pci_dev_type`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2496), carries that list:

```c
/* drivers/pci/probe.c:2496 */
static const struct device_type pci_dev_type = {
	.groups = pci_dev_attr_groups,
};
```

The files therefore appear when the function's device is registered and disappear with it, as the figure shows by function type.

```text
    Which counter and limiter files a function shows, by its place and its aer_info
    ───────────────────────────────────────────────────────────────────────────────

    (the files of /sys/bus/pci/devices/<function>/ that the two AER attribute groups add)

             ┌───────────────────────────────────────────────────────────────────┐
    root     │ Root Port or RCEC, aer_info allocated                             │
             │ aer_dev_correctable  aer_dev_fatal  aer_dev_nonfatal              │
             │ aer_rootport_total_err_cor  _fatal  _nonfatal                     │
             │ aer/  correctable_ and nonfatal_ratelimit_interval_ms, _burst     │
             └───────────────┬───────────────────────────────────┬───────────────┘
                             │                                   │                 below the root: no
       ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┼ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┼ ─ ─ ─ ─ ─ ─ ─   aer_rootport_total_err_*
                             │                                   │                 files
                             │                                   │
             ┌───────────────┴─────────────────────┐   ┌─────────┴─────────────────────────────┐
    below    │ Endpoint or Switch Port,            │   │ a function with no AER                │
             │ aer_info allocated                  │   │ capability, aer_info NULL             │
             │ aer_dev_*  aer/ with four files     │   │ no aer_dev_*, no aer/                 │
             └─────────────────────────────────────┘   └───────────────────────────────────────┘
```

A counter file reads the arrays without a lock while the IRQ thread or a work item may be adding to them, so a read can return counts from just before or just after one report.

### Limiter files read and set each interval and burst

The limiters can be tuned per function through four files in an aer directory, which commit [b4fe7398def6](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=b4fe7398def6df344442b884d2288f80205cbd2d) ("PCI/AER: Add sysfs attributes for log ratelimits") added. [`aer_ratelimit_interval_attr`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L647) generates the show and store functions of an interval file; read it for the permission check and the unit conversion.

```c
/* drivers/pci/pcie/aer.c:642 */
/*
 * Ratelimit interval
 * <=0: disabled with ratelimit.interval = 0
 * >0: enabled with ratelimit.interval in ms
 */
#define aer_ratelimit_interval_attr(name, ratelimit)			\
	static ssize_t							\
	name##_show(struct device *dev, struct device_attribute *attr,	\
					 char *buf)			\
	{								\
		struct pci_dev *pdev = to_pci_dev(dev);			\
									\
		return sysfs_emit(buf, "%d\n",				\
				  pdev->aer_info->ratelimit.interval);	\
	}								\
									\
	static ssize_t							\
	name##_store(struct device *dev, struct device_attribute *attr, \
		     const char *buf, size_t count) 			\
	{								\
		struct pci_dev *pdev = to_pci_dev(dev);			\
		int interval;						\
									\
		if (!capable(CAP_SYS_ADMIN))				\
			return -EPERM;					\
									\
		if (kstrtoint(buf, 0, &interval) < 0)			\
			return -EINVAL;					\
									\
		if (interval <= 0)					\
			interval = 0;					\
		else							\
			interval = msecs_to_jiffies(interval); 		\
									\
		pdev->aer_info->ratelimit.interval = interval;		\
									\
		return count;						\
	}								\
	static DEVICE_ATTR_RW(name);
```

Writing needs `CAP_SYS_ADMIN`, a value of 0 or less stores 0, which switches the limiter off, and a positive value is converted from milliseconds to jiffies with `msecs_to_jiffies()`. The show function prints the stored jiffies, so with [`CONFIG_HZ_1000`](https://elixir.bootlin.com/linux/v7.2/source/kernel/Kconfig.hz#L43), set in the x86-64 defconfig, the file reads back the milliseconds written, and under another tick rate it reads back a different number. [`aer_ratelimit_burst_attr`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L682) generates the burst file's functions:

```c
/* drivers/pci/pcie/aer.c:682 */
#define aer_ratelimit_burst_attr(name, ratelimit)			\
	static ssize_t							\
	name##_show(struct device *dev, struct device_attribute *attr,	\
		    char *buf)						\
	{								\
		struct pci_dev *pdev = to_pci_dev(dev);			\
									\
		return sysfs_emit(buf, "%d\n",				\
				  pdev->aer_info->ratelimit.burst);	\
	}								\
									\
	static ssize_t							\
	name##_store(struct device *dev, struct device_attribute *attr,	\
		     const char *buf, size_t count)			\
	{								\
		struct pci_dev *pdev = to_pci_dev(dev);			\
		int burst;						\
									\
		if (!capable(CAP_SYS_ADMIN))				\
			return -EPERM;					\
									\
		if (kstrtoint(buf, 0, &burst) < 0)			\
			return -EINVAL;					\
									\
		pdev->aer_info->ratelimit.burst = burst;		\
									\
		return count;						\
	}								\
	static DEVICE_ATTR_RW(name);
```

The burst is stored as written, with no lower bound, and while the interval is positive a burst of 0 or less refuses every report of the class, a negative value also warning once. Both stores write the settings with plain assignments, while [`___ratelimit()`](https://elixir.bootlin.com/linux/v7.2/source/lib/ratelimit.c#L27) reads them with `READ_ONCE()`. [`aer_ratelimit_attrs`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L712) instantiates both macros for one limiter, two invocations make the four files that [`aer_attrs`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L721) lists, and [`aer_attrs_are_visible()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L729) decides whether they appear; read the unit for the instantiation and the visibility test.

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
```

The `name##_ratelimit` argument picks [`correctable_ratelimit`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L95) or [`nonfatal_ratelimit`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L96), so each pair of files acts on one limiter. [`aer_attrs_are_visible()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L729) hides the four files of a function without [`aer_info`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L371) and shows them on any other function, whatever its type.

[`aer_attr_group`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L741) names the directory "aer", which places the four files under `/sys/bus/pci/devices/<function>/aer/`:

```c
/* drivers/pci/pcie/aer.c:741 */
const struct attribute_group aer_attr_group = {
	.name = "aer",
	.attrs = aer_attrs,
	.is_visible = aer_attrs_are_visible,
};
```

The interval's two units are drawn below for the default value.

```text
    An interval written in milliseconds is stored and read back in jiffies
    ──────────────────────────────────────────────────────────────────────

    (the rulers share one scale, one column is 100 ms; the worked value is the default, 5000 ms)

                             0                  2000                          5000
    written, in ms           ├─────────┼─────────┼─────────┼─────────┼─────────┬─────────┤
                                                                               │
                                                                               │ the store converts ms to jiffies
                                                                               ▼
                             0                  2000                          5000
    stored, HZ=1000          ├─────────┼─────────┼─────────┼─────────┼─────────┼─────────┤  read back: 5000

                             0                  500                           1250
    stored, HZ=250           ├─────────┼─────────┼─────────┼─────────┼─────────┼─────────┤  read back: 1250

    the interval file shows the stored jiffies; with CONFIG_HZ_1000, set in the x86-64 defconfig,
    the number read back equals the milliseconds written; a written 0 or less stores 0
```

A write takes effect at the limiter's next consultation, and a new burst is applied when the current window ends and the budget is refilled.

### Messages, a tracepoint and files expose these paths

The paths of this page leave lines in the kernel log, entries of one tracepoint, sysfs files and a crash-dump record, and they cross three hand-offs. The first table lists each class with its sites, a class absent from these paths named as absent.

| class | on these paths | sites |
|---|---|---|
| tracepoints | `ras:aer_event`, fired for each record that [`aer_print_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L865) or [`pci_print_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L926) counts; no other tracepoint lies on these paths | [`aer.c:879-880`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L879), [`aer.c:955-956`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L955) |
| debug and dynamic-debug sites | none, aer.c holds no [`pci_dbg()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2896), `dev_dbg()` or `pr_debug()` call at v7.2, so [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120) and [`CONFIG_PCI_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L70) add no line here | none |
| hand-offs | the AER IRQ thread fed through [`aer_fifo`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L56), the DPC IRQ thread, and with [`CONFIG_ACPI_APEI_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Kconfig#L37) the [`aer_recover_work`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1261) item fed through a fifo of firmware records | [`aer.c:1632-1633`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1632), [`aer.c:1215-1216`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1215) |
| debugging surfaces | the counter files and the aer directory in sysfs, the tracefs event, the crash-dump array, the pci=noaer boot parameter and, with [`CONFIG_PCIEAER_INJECT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L37), the error injector of [`aer_inject.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer_inject.c); no debugfs or procfs file | the sysfs subsections above, [`pci.c:6757-6758`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L6757) |

The second table lists the lines these paths print, each with its level.

| line | level | site |
|---|---|---|
| "[Multiple ]<class> error message received from <domain>:<bus>:<dev>.<fn>[ (no details found]" | `KERN_INFO` | [`aer.c:857-862`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L857) |
| "PCIe Bus Error: severity=<class>, type=<layer>, (<agent>)" | the record's level | [`aer.c:894-896`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L894) |
| "PCIe Bus Error: severity=<class>, type=Inaccessible, (Unregistered Agent ID)" | `KERN_ERR` | [`aer.c:886-887`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L886) |
| "  device [<vendor>:<device>] error status/mask=<status>/<mask>" | the record's level | [`aer.c:898-899`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L898) |
| "   [<bit>] <name>  (First)", one per unmasked bit | the record's level | [`aer.c:847-848`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L847) |
| "  TLP Header: <dwords>" | the record's level | [`tlp.c:135-136`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L135) |
| "  Error of this Agent is reported first" | `KERN_ERR` | [`aer.c:908`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L908) |
| "Exceeded max supported (5) devices with errors logged" | `KERN_ERR` | [`aer.c:1075-1076`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1075) |
| "aer_ratelimit: <n> callbacks suppressed" | `KERN_WARNING` | [`ratelimit.c:86-87`](https://elixir.bootlin.com/linux/v7.2/source/lib/ratelimit.c#L86) |
| "aer_status: ...", "aer_layer=...", "aer_uncor_severity: ..." of a firmware record | the record's level | [`aer.c:964-972`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L964) |
| "containment event, status:<status>: unmasked uncorrectable error detected" | `KERN_WARNING` | [`dpc.c:275-276`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L275) |

The record's level is `KERN_WARNING` for a correctable record and `KERN_ERR` for the others, so a console log level that hides warnings hides the correctable reports and keeps the rest. The boot parameter pci=noaer reaches the AER code through [`pci_setup()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L6743), the "pci=" parser; read the stage that handles it.

```c
/* drivers/pci/pci.c:6743 */
static int __init pci_setup(char *str)
{
	while (str) {
				... /* 10 lines, to :6756 */
				pcie_ats_disabled = true;
			} else if (!strcmp(str, "noaer")) {
				pci_no_aer();
```

[`pci_no_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L133) sets [`pcie_aer_disable`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L130), and [`pci_aer_available()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L138) reports AER as available only when that flag is clear and MSI is enabled:

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

The port driver asks [`pci_aer_available()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L138) before it gives a Root Port or RCEC the AER service; read the stage of [`get_port_device_capability()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L218) for the condition.

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
```

With pci=noaer the AER interrupt is not requested, so the root counts nothing and the native route prints nothing, while [`pci_aer_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L385) still allocates [`struct aer_info`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L60) and the counter files stay present. The service also needs the firmware's grant in [`native_aer`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L653) unless the port driver runs in native mode, so on a platform whose firmware keeps AER the native route is absent and reports arrive through firmware-first handling instead.
