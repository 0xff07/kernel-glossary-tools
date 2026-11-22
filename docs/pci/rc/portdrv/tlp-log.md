# TLP Header Log

> CAUTION: AI-GENERATED CONTENT
>
> STRICTLY DO NOT SUBMIT THIS UPSTREAM UNLESS YOU ARE AN EXPERT INTIMATELY FAMILIAR WITH THIS SUBSYSTEM.

A PCIe component that detects an error in a transaction can capture the header of the TLP involved, so that software learns which request or completion went wrong and not only that something did. The Advanced Error Reporting capability of a function keeps such a header in its log registers, and a Root Port with Downstream Port Containment keeps another for its own requests that failed. The kernel copies these registers into one structure when its error services report an event, and prints the copy beside the error report. This page traces that structure, the rule that sets how many dwords a log holds in Flit mode and outside it, the read, the print and the registers they use.

```text
    Three routes by which a logged TLP header reaches a struct pcie_tlp_log
    ───────────────────────────────────────────────────────────────────────
    configuration space or firmware                       kernel memory                      output

    ┌──────────────────────────────────┐
    │ AER capability of a function     │  read at error   ┌────────────────────────────┐     ┌──────────────────┐
    │ Header Log         +0x1c  4 dw   │─────────────────▶│ struct aer_err_info, .tlp  │────▶│ TLP Header line  │
    │ Prefix Log or ext  +0x38         │                  │ refilled for each function │     │ ras:aer_event    │
    └──────────────────────────────────┘                  └────────────────────────────┘     └──────────────────┘

    ┌──────────────────────────────────┐
    │ DPC capability, contained port   │  read on RP PIO  ┌────────────────────────────┐     ┌──────────────────┐
    │ RP PIO Header Log  +0x20  4 dw   │─────────────────▶│ tlp_log, a local struct    │────▶│ TLP Header line  │
    │ TLP Prefix Log     +0x34         │                  │ of the RP PIO error path   │     │ no trace record  │
    └──────────────────────────────────┘                  └────────────────────────────┘     └──────────────────┘

    ┌──────────────────────────────────┐  copied          ┌────────────────────────────┐     ┌──────────────────┐
    │ firmware error record, with      │─────────────────▶│ struct aer_capability_regs │────▶│ TLP Header line  │
    │ an image of the AER capability   │                  │ member header_log          │     │ ras:aer_event    │
    └──────────────────────────────────┘                  └────────────────────────────┘     └──────────────────┘

    each holder is a struct pcie_tlp_log: four header dwords and up to four End-End Prefixes,
    or up to fourteen header dwords when the error was logged in Flit mode
```

## SUMMARY

The object of this page is one logged header, which the kernel holds in a [`struct pcie_tlp_log`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L29) whichever register block it came from. The table settles which kernel name stands for each term of the specification, and the rest of the page uses the names in its last column.

| Specification term | Kernel representation | Name on this page |
|---|---|---|
| the header of the TLP that caused an error, as a component logged it | [`struct pcie_tlp_log`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L29), filled by [`pcie_read_tlp_log()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L63) or copied from a firmware record | the log |
| Header Log of the AER capability, RP PIO Header Log of the DPC capability | [`PCI_ERR_HEADER_LOG`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L821) and [`PCI_EXP_DPC_RP_PIO_HEADER_LOG`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1117), read into the first four entries of [`dw`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L31) | the header dwords |
| TLP Prefix Log, holding End-End TLP Prefixes | [`PCI_ERR_PREFIX_LOG`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L836) and [`PCI_EXP_DPC_RP_PIO_TLPPREFIX_LOG`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1119), read into [`prefix`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L34), as many as [`eetlp_prefix_max`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L443) allows for AER | the prefix dwords |
| a header logged in Flit mode, the Prefix Log extending the Header Log | [`flit`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L38) set, with [`header_len`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L37) up to [`PCIE_STD_MAX_TLP_HEADERLOG`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L25) | a Flit log |
| Logged TLP Size of the AER capability | [`PCI_ERR_CAP_TLP_LOG_SIZE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L820), read by [`aer_tlp_log_len()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L23) | the logged size |
| RP PIO Log Size of the DPC capability | [`dpc_rp_log_size`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L539), from [`PCI_EXP_DPC_RP_PIO_LOG_SIZE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1087) and [`PCI_EXP_DPC_RP_PIO_LOG_SIZE4`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1089) | the RP PIO size |

A read starts from a length, which [`aer_tlp_log_len()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L23) derives from the AER control dword and [`dpc_tlp_log_len()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L40) from the RP PIO size cached at enumeration. [`pcie_read_tlp_log()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L63) then fills the log, and [`pcie_print_tlp_log()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L106) prints its dwords in hexadecimal. At v7.2 the PCI core decodes no field of a logged header, so the meaning of each dword is the specification's and the printed line is raw.

## SPECIFICATIONS

The registers a log comes from are defined by the PCI Express Base Specification, which the tree cites by revision and section number in the places listed, with titles only where a commit message gives them. The structure that holds a log is the kernel's own, described here from [`aer.h`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h) and [`tlp.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c) at v7.2. The header formats inside the dwords are the specification's TLP formats, and the code on these paths copies them without decoding them.

- PCI Express Base Specification, revision 6.2, sections 7.8.4 and 7.9.14, cited without titles by the comment at [`aer.h:19-21`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L19) for the sizes of the AER and DPC TLP logging registers.
- PCI Express Base Specification, revision 7.0, section 6.2.7, cited by the comment at [`aer.c:817`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L817) for the errors after which a header is always logged.
- PCI Express Base Specification, revision 6.1, sections 7.8.4.12 and 7.9.14.13, the TLP Prefix Log registers, which become an extension of the TLP Header Log in Flit mode, cited by commit [7e077e6707b3](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=7e077e6707b3428562ba30d883ff8f54e98dc18b) ("PCI/ERR: Handle TLP Log in Flit mode").
- PCI Express Base Specification, revision 6.1, section 7.8.4.7, the Advanced Error Capabilities and Control Register, which tells whether an error was logged in Flit mode, cited by the same commit.
- PCI Express Base Specification, revision 6.1, section 7.5.3.20, Flit Mode Status, cited by the same commit for the value the DPC path uses in place of such a bit.
- PCI Express Base Specification, revision 6.2, section 7.5.3.15, the Max End-End TLP Prefixes field of the Device Capabilities Register 2, cited by commit [e5321ae10e13](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=e5321ae10e1323359a5067a26dfe98b5f44cc5e6) ("PCI: Store number of supported End-End TLP Prefixes").

## COVERAGE

### The log and its sizes (include/linux/aer.h)

- [`'struct pcie_tlp_log'`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L29): one logged header, read as up to fourteen header dwords or as four header dwords and four prefix dwords
- [`'pcie_tlp_log.dw'`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L31): the fourteen dwords as one array, every entry a header dword in a Flit log
- [`'pcie_tlp_log.prefix'`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L34): the fifth to eighth dwords read as End-End TLP Prefixes outside Flit mode
- [`'pcie_tlp_log.header_len'`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L37): the header length in dwords, four outside Flit mode
- [`'pcie_tlp_log.flit'`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L38): set when the header was logged in Flit mode
- [`'PCIE_STD_NUM_TLP_HEADERLOG'`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L23): four, the dwords of a Header Log register
- [`'PCIE_STD_MAX_TLP_PREFIXLOG'`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L24): four, the dwords of a TLP Prefix Log register
- [`'PCIE_STD_MAX_TLP_HEADERLOG'`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L25): fourteen, the most header dwords a log records

### Length, read and print (drivers/pci/pcie/tlp.c)

- [`'\<aer_tlp_log_len\>':'drivers/pci/pcie/tlp.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L23): the length of an AER log, from the AER control dword
- [`'\<dpc_tlp_log_len\>':'drivers/pci/pcie/tlp.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L40): the length of an RP PIO log, from the cached RP PIO size
- [`'\<pcie_read_tlp_log\>':'drivers/pci/pcie/tlp.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L63): fills a log from a Header Log window and a second window
- [`'\<pcie_print_tlp_log\>':'drivers/pci/pcie/tlp.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L106): prints a log as one line of hexadecimal dwords

### The AER decision (drivers/pci/pcie/aer.c, drivers/pci/pci.h)

- [`'AER_LOG_TLP_MASKS'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L99): the uncorrectable errors after which a header is always logged
- [`'\<tlp_header_logged\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L815): tests an uncorrectable status and the control dword for a logged header
- [`'aer_err_info.tlp_header_valid'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L849): set while the error information holds a log for the function being reported

### TLP log registers (include/uapi/linux/pci_regs.h)

- [`'PCI_ERR_CAP_PREFIX_LOG_PRESENT'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L817): the AER control bit that says a TLP Prefix Log exists
- [`'PCI_ERR_CAP_TLP_LOG_FLIT'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L819): the AER control bit that says the header was logged in Flit mode
- [`'PCI_ERR_CAP_TLP_LOG_SIZE'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L820): the AER control field that gives the logged size of a Flit log
- [`'PCI_ERR_HEADER_LOG'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L821): the offset of the AER Header Log
- [`'PCI_ERR_PREFIX_LOG'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L836): the offset of the AER TLP Prefix Log
- [`'PCI_EXP_DPC_RP_PIO_LOG_SIZE'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1087): the low four bits of the RP PIO size in the DPC Capability register
- [`'PCI_EXP_DPC_RP_PIO_LOG_SIZE4'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1089): the fifth bit of the RP PIO size
- [`'PCI_EXP_DPC_RP_PIO_HEADER_LOG'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1117): the offset of the RP PIO Header Log
- [`'PCI_EXP_DPC_RP_PIO_TLPPREFIX_LOG'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1119): the offset of the RP PIO TLP Prefix Log

## DOCUMENTATION

- [`Documentation/PCI/pcieaer-howto.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/PCI/pcieaer-howto.rst): the AER error output, whose TLP Header line carries the logged header in raw hexadecimal, and a decoding tool for that line

## OTHER SOURCES

### Added by Claude Opus 5.5

- [PCI/ERR: Handle TLP Log in Flit mode (commit 7e077e6707b3)](https://lore.kernel.org/r/20250207161836.2755-3-ilpo.jarvinen@linux.intel.com)
- [PCI/ERR: Add printk level to pcie_print_tlp_log() (commit 82013ff394ea)](https://patch.msgid.link/20250522232339.1525671-14-helgaas@kernel.org)
- [PCI: Add pcie_print_tlp_log() to print TLP Header and Prefix Log (commit f68ea779d98a)](https://lore.kernel.org/r/20250114170840.1633-9-ilpo.jarvinen@linux.intel.com)
- [PCI: Add TLP Prefix reading to pcie_read_tlp_log() (commit ad41ddeeac21)](https://lore.kernel.org/r/20250114170840.1633-8-ilpo.jarvinen@linux.intel.com)
- [PCI: Store number of supported End-End TLP Prefixes (commit e5321ae10e13)](https://lore.kernel.org/r/20250114170840.1633-7-ilpo.jarvinen@linux.intel.com)
- [PCI: Add defines for TLP Header/Prefix log sizes (commit ede5d5dbef6f)](https://lore.kernel.org/r/20250114170840.1633-4-ilpo.jarvinen@linux.intel.com)
- [PCI: Move TLP Log handling to its own file (commit a71c59269e51)](https://lore.kernel.org/r/20250114170840.1633-3-ilpo.jarvinen@linux.intel.com)
- [PCI/AER: Generalize TLP Header Log reading (commit 0a5a46a6a61b)](https://lore.kernel.org/r/20240206135717.8565-3-ilpo.jarvinen@linux.intel.com)
- [PCI/AER: Print TLP Log for errors introduced since PCIe r1.1 (commit c8ab5e888bb6)](https://patch.msgid.link/5f707caf1260bd8f15012bb032f7da9a9b898aba.1756712066.git.lukas@wunner.de)
- [PCI/DPC: Print all TLP Prefixes, not just the first (commit 6568d82512b0)](https://lore.kernel.org/r/20240118110815.3867-1-ilpo.jarvinen@linux.intel.com)

## REGISTERS

A log is read from one of two capabilities, and three bits of the PCI Express capability decide how long it is and whether it was logged in Flit mode. Each drawing gives offsets from the capability's base, which the kernel caches per function, and the paragraph after it says what each field decides on the paths of this page.

The AER capability of a function holds its error status, its capabilities and control dword and the two windows of its log, at offsets from [`aer_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370).

```text
    The AER capability registers on the log path, at offsets from aer_cap
    ─────────────────────────────────────────────────────────────────────
    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    +0x18 │       ·       │  size   │F│    ·    │T│P│ · │ ECRC  │   FEP   │
          │               │ (23:19) │ │         │ │ │   │ (8:5) │  (4:0)  │
          ├───────────────┴─────────┴─┴─────────┴─┴─┴───┴───────┴─────────┤
    +0x1c │                    Header Log, first dword                    │
          ├───────────────────────────────────────────────────────────────┤
    +0x20 │                   Header Log, second dword                    │
          ├───────────────────────────────────────────────────────────────┤
    +0x24 │                    Header Log, third dword                    │
          ├───────────────────────────────────────────────────────────────┤
    +0x28 │                   Header Log, fourth dword                    │
          ├───────────────────────────────────────────────────────────────┤
    +0x2c │      Root Error Command, Status and Source ID, to +0x37       │
          ├───────────────────────────────────────────────────────────────┤
    +0x38 │    TLP Prefix Log, first dword, or the fifth header dword     │
          ├───────────────────────────────────────────────────────────────┤
    +0x3c │         TLP Prefix Log, dwords two to four, to +0x47          │
          ├───────────────────────────────────────────────────────────────┤
    +0x48 │   Flit mode only: header dwords nine to fourteen, to +0x5f    │
          └───────────────────────────────────────────────────────────────┘

    +0x18 = PCI_ERR_CAP (Advanced Error Capabilities and Control, read into aercc)
    FEP = PCI_ERR_CAP_FEP() (First Error Pointer, cached in first_error); ECRC = the four ECRC bits
    P = PCI_ERR_CAP_PREFIX_LOG_PRESENT (the TLP Prefix Log is present)
    T = PCI_ERR_CAP_COMP_TIME_LOG (a Completion Timeout logs a header)
    F = PCI_ERR_CAP_TLP_LOG_FLIT (the header was logged in Flit mode)
    size = PCI_ERR_CAP_TLP_LOG_SIZE (Logged TLP Size in dwords, valid only with F set)
    · = bits with no macro in pci_regs.h, which these paths ignore
    +0x1c = PCI_ERR_HEADER_LOG (four dwords); +0x38 = PCI_ERR_PREFIX_LOG (up to four dwords)
    +0x2c = PCI_ERR_ROOT_COMMAND, +0x30 = PCI_ERR_ROOT_STATUS, +0x34 = PCI_ERR_ROOT_ERR_SRC: never read as log
```

In the dword at +0x18, P adds the prefix dwords to a log read outside Flit mode, F marks a Flit log, and size then gives its length. T lets a Completion Timeout count as an error with a logged header, and FEP is the First Error Pointer the AER path reads beside the log. The four Header Log dwords become the header dwords of the log, and the dwords from +0x38 become its prefix dwords or, in a Flit log, its later header dwords.

Whether a function logged a header at all follows from the uncorrectable error it reports, and the status register at +0x04 carries one bit per error.

```text
    Uncorrectable Error Status, and the bits after which a header is logged
    ───────────────────────────────────────────────────────────────────────
    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    +0x04 │J│S│S│S│W│G│R│A│B│n│V│U│E│M│o│X│C│T│f│P│     ·     │r│k│  ·  │u│
          └─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴───────────┴─┴─┴─────┴─┘

    +0x04 = PCI_ERR_UNCOR_STATUS; uppercase = a member of AER_LOG_TLP_MASKS
    lowercase = a bit tlp_header_logged() does not test
    P = PCI_ERR_UNC_POISON_TLP; C = PCI_ERR_UNC_COMP_ABORT; X = PCI_ERR_UNC_UNX_COMP; M = PCI_ERR_UNC_MALF_TLP
    E = PCI_ERR_UNC_ECRC; U = PCI_ERR_UNC_UNSUP; V = PCI_ERR_UNC_ACSV; B = PCI_ERR_UNC_MCBTLP; A = PCI_ERR_UNC_ATOMEG
    R = PCI_ERR_UNC_TLPPRE; G = PCI_ERR_UNC_POISON_BLK; W = PCI_ERR_UNC_DMWR_BLK; J = PCI_ERR_UNC_XLAT_BLK
    S = three more members of AER_LOG_TLP_MASKS, link-security errors this page leaves out
    T = PCI_ERR_UNC_COMP_TIME (Completion Timeout), counted only with PCI_ERR_CAP_COMP_TIME_LOG set
    u = PCI_ERR_UNC_UND; k = PCI_ERR_UNC_DLP; r = PCI_ERR_UNC_SURPDN; f = PCI_ERR_UNC_FCP
    o = PCI_ERR_UNC_RX_OVER; n = PCI_ERR_UNC_INTN; · = no macro in pci_regs.h
```

An uppercase bit set in the status makes [`tlp_header_logged()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L815) report a logged header, and T does so only with the T bit of the control dword set. The lowercase bits, among them Surprise Down and the data link errors, never cause a read of the log by themselves.

The DPC capability of a Root Port with the RP Extensions holds a second log, for requests of the port that ended in an error completion or a timeout, at offsets from [`dpc_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L537).

```text
    The DPC capability registers on the log path, at offsets from dpc_cap
    ─────────────────────────────────────────────────────────────────────
    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    +0x04 │      DPC Control (+0x06)      │ · │H│a│ size  │w│p│R│   IRQ   │
          │                               │   │ │ │(11:8) │ │ │ │  (4:0)  │
          ├───────────────────────────────┴───┴─┴─┴───────┴─┴─┴─┴─────────┤
    +0x20 │                RP PIO Header Log, first dword                 │
          ├───────────────────────────────────────────────────────────────┤
    +0x24 │        RP PIO Header Log, dwords two to four, to +0x2f        │
          ├───────────────────────────────────────────────────────────────┤
    +0x30 │                      RP PIO ImpSpec Log                       │
          ├───────────────────────────────────────────────────────────────┤
    +0x34 │ RP PIO TLP Prefix Log, first dword, or the fifth header dword │
          ├───────────────────────────────────────────────────────────────┤
    +0x38 │   further prefix dwords to +0x43, or header dwords to +0x5b   │
          └───────────────────────────────────────────────────────────────┘

    +0x04 = PCI_EXP_DPC_CAP (DPC Capability, the low half of the dword); +0x06 = PCI_EXP_DPC_CTL
    IRQ = PCI_EXP_DPC_IRQ (Interrupt Message Number); R = PCI_EXP_DPC_CAP_RP_EXT (Root Port Extensions)
    p = PCI_EXP_DPC_CAP_POISONED_TLP; w = PCI_EXP_DPC_CAP_SW_TRIGGER; a = PCI_EXP_DPC_CAP_DL_ACTIVE
    size = PCI_EXP_DPC_RP_PIO_LOG_SIZE (RP PIO Log Size bits 3:0, in dwords, cached in dpc_rp_log_size)
    H = PCI_EXP_DPC_RP_PIO_LOG_SIZE4 (RP PIO Log Size bit 4, added when the port supports Flit mode)
    · = no macro in pci_regs.h
    +0x20 = PCI_EXP_DPC_RP_PIO_HEADER_LOG; +0x30 = PCI_EXP_DPC_RP_PIO_IMPSPEC_LOG
    +0x34 = PCI_EXP_DPC_RP_PIO_TLPPREFIX_LOG
```

R tells [`pci_dpc_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L403) that the RP PIO registers exist, and size, extended by H on a port that supports Flit mode, becomes the cached RP PIO size. The four dwords from +0x20 become the header dwords of the log. The ImpSpec Log at +0x30 is counted in the size but printed on a line of its own, and the dwords from +0x34 become prefix dwords or later header dwords.

The PCI Express capability of each function adds three bits that decide the length and the form of a log without being part of it.

```text
    The PCI Express capability bits that size and date a log, at offsets from pcie_cap
    ──────────────────────────────────────────────────────────────────────────────────
    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    +0x00 │F│    other fields (30:16)     │  Next (15:8)  │   ID (7:0)    │
          ├─┴─────────────┬───┬─┬─────────┴───────────────┴───────────────┤
    +0x24 │ other (31:24) │ M │E│   other Device Capabilities 2 fields    │
          ├─────────┬─┬───┴───┴─┴─────────┬───────────────────────────────┤
    +0x30 │  other  │L│   other (25:16)   │     Link Control 2 (15:0)     │
          └─────────┴─┴───────────────────┴───────────────────────────────┘

    +0x00: bits 31:16 are PCI_EXP_FLAGS at +0x02; F = PCI_EXP_FLAGS_FLIT (Flit Mode Supported)
    +0x24 = PCI_EXP_DEVCAP2; E = PCI_EXP_DEVCAP2_EE_PREFIX (End-End TLP Prefix Supported)
    M = PCI_EXP_DEVCAP2_EE_PREFIX_MAX (Max End-End TLP Prefixes, 0 meaning 4, cached in eetlp_prefix_max)
    +0x30: bits 31:16 are PCI_EXP_LNKSTA2 at +0x32; L = PCI_EXP_LNKSTA2_FLIT (Flit Mode Status, cached in flit_mode)
    ID and Next = PCI_CAP_LIST_ID and PCI_CAP_LIST_NEXT, the capability header
```

E and M give [`eetlp_prefix_max`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L443), the number of prefix dwords an AER log adds outside Flit mode. F decides whether [`pci_dpc_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L403) reads the fifth bit of the RP PIO size. L is the Flit Mode Status that the link-speed update copies into [`flit_mode`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L734) of the bus below a port, and the DPC path passes that copy as the Flit flag of its log.

## DETAILS

DETAILS first sets out the structure that holds a log and its two readings. It then derives the length of a log, for AER from the capability's control dword and for DPC from the size checked at enumeration, and follows [`pcie_read_tlp_log()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L63) as it fills the structure from two register windows. The AER path that decides whether a header was logged and reads it for each reporting function comes next, then the DPC path that reads the RP PIO log into a local copy. The print, the copy a firmware report brings, and the trace record, messages, hand-offs and files around a log close the page.

### Kconfig assumptions

This page documents the x86-64 default configuration resolved at v7.2, with the options the campaign adds to it, on x86-64 with ACPI. The table lists each option the prose names, the value assumed for it and what it decides on these paths.

| Option | Assumed | What it decides here |
|---|---|---|
| [`CONFIG_PCIEPORTBUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L5) | y | the AER and DPC services that read a log are services of the PCIe port driver |
| [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28) | y | builds [`tlp.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c) with the AER service, and declares the log helpers in [`pci.h`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h) |
| [`CONFIG_PCIE_DPC`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L121) | y | builds [`dpc_tlp_log_len()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L40) and the RP PIO path |
| [`CONFIG_ACPI_APEI_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Kconfig#L37) | n | the firmware-first route that copies a log out of a firmware record |
| [`CONFIG_PCIE_EDR`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L140) | n | the ACPI notification that runs the DPC error report for firmware |
| [`CONFIG_PCIEAER_INJECT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L37) | n | the injector that answers Header Log reads with injected values |
| [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120) | y | dynamic debug, which finds no debug-level site on these paths |

The table only indexes the prose, which states the effect of each option at the place it applies.

### struct pcie_tlp_log holds one logged header in two readings

A logged header names the transaction an error happened on, since it is the header of the TLP that caused the error. The kernel keeps one such header in a [`struct pcie_tlp_log`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L29) whichever capability logged it, so that one reader serves the AER and DPC paths and one printer serves every report. Outside Flit mode a log is four header dwords followed by up to four End-End TLP Prefixes. In Flit mode the prefix registers carry further header dwords instead, up to fourteen dwords in all.

The dword counts come first. [`aer.h`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h) defines them as [`PCIE_STD_NUM_TLP_HEADERLOG`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L23), [`PCIE_STD_MAX_TLP_PREFIXLOG`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L24) and [`PCIE_STD_MAX_TLP_HEADERLOG`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L25), under a comment that names the specification sections; read the three macros for the values the structure is sized from.

```c
/* include/linux/aer.h:19 */
/*
 * AER and DPC capabilities TLP Logging register sizes (PCIe r6.2, sec 7.8.4
 * & 7.9.14).
 */
#define PCIE_STD_NUM_TLP_HEADERLOG     4
#define PCIE_STD_MAX_TLP_PREFIXLOG     4
#define PCIE_STD_MAX_TLP_HEADERLOG	(PCIE_STD_NUM_TLP_HEADERLOG + 10)
```

[`PCIE_STD_NUM_TLP_HEADERLOG`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L23) is the four dwords of a Header Log register, and [`PCIE_STD_MAX_TLP_PREFIXLOG`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L24) the four of a TLP Prefix Log register. [`PCIE_STD_MAX_TLP_HEADERLOG`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L25) adds ten to the first, the most header dwords the kernel records for one error.

[`struct pcie_tlp_log`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L29) holds the dwords in one array under a union, so that one storage reads as fourteen header dwords or as four header dwords and four prefix dwords. Read the definition for the union and for the two members after it.

```c
/* include/linux/aer.h:29 */
struct pcie_tlp_log {
	union {
		u32 dw[PCIE_STD_MAX_TLP_HEADERLOG];
		struct {
			u32 _do_not_use[PCIE_STD_NUM_TLP_HEADERLOG];
			u32 prefix[PCIE_STD_MAX_TLP_PREFIXLOG];
		};
	};
	u8 header_len;		/* Length of the Logged TLP Header in DWORDs */
	bool flit;		/* TLP was logged when in Flit mode */
};
```

[`dw`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L31) is the whole array, which [`pcie_read_tlp_log()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L63) fills and a Flit log prints as header dwords. The anonymous struct gives the same storage its second reading, [`_do_not_use`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L33) over the four header dwords and [`prefix`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L34) over the next four, the End-End TLP Prefixes of a log read outside Flit mode. [`header_len`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L37) is the header length in dwords, and [`flit`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L38) says which of the two readings applies.

The two readings overlay one array, and the figure draws its fourteen dwords under each, with the value [`header_len`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L37) takes in each case.

```text
    One struct pcie_tlp_log, its fourteen dwords under two readings
    ───────────────────────────────────────────────────────────────

                  ┌──────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┬─────────────────────┐
    flit = true   │dw[0] │dw[1] │dw[2] │dw[3] │dw[4] │dw[5] │dw[6] │dw[7] │ dw[8] .. dw[13]     │  header_len = tlp_len
                  └──────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┴─────────────────────┘
                  ├─────────────────── header dwords, as many as header_len ────────────────────┤

                  ┌──────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┬─────────────────────┐
    flit = false  │_d[0] │_d[1] │_d[2] │_d[3] │pre[0]│pre[1]│pre[2]│pre[3]│ not printed         │  header_len = 4
                  └──────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┴─────────────────────┘
                  ├───── header dwords ──────┤├──────── prefix[] ─────────┤

    _d[i] is _do_not_use[i], the same four dwords as dw[0] to dw[3]; pre[i] is prefix[i], the
    same dword as dw[4 + i]; both rows are one u32 array of PCIE_STD_MAX_TLP_HEADERLOG entries
```

A Flit log is thus up to fourteen header dwords and no prefix dwords, and any other log is four header dwords and up to four prefix dwords in the same storage. How many of those dwords a read fills is decided per capability, as the next two subsections show.

### AER sizes its log from the capability's control dword

A read must know how many dwords to take, because other registers follow the log and because the prefix registers can be absent outside Flit mode. For an AER log the answer lies in the Advanced Error Capabilities and Control dword, which the AER path reads beside the status into its local aercc. The table sets out the Flit-mode length rule for both capabilities, and this subsection reads its AER rows.

| Log and condition | Dwords read | Decided by |
|---|---|---|
| AER, [`PCI_ERR_CAP_TLP_LOG_FLIT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L819) clear | four, plus [`eetlp_prefix_max`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L443) when [`PCI_ERR_CAP_PREFIX_LOG_PRESENT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L817) is set | [`aer_tlp_log_len()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L23) |
| AER, [`PCI_ERR_CAP_TLP_LOG_FLIT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L819) set | the logged size in [`PCI_ERR_CAP_TLP_LOG_SIZE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L820) | [`aer_tlp_log_len()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L23) |
| DPC, either mode | the RP PIO size in [`dpc_rp_log_size`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L539), less the ImpSpec dword from five dwords up | [`dpc_tlp_log_len()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L40) |
| either, past fourteen dwords | cut to [`PCIE_STD_MAX_TLP_HEADERLOG`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L25) | [`pcie_read_tlp_log()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L63) |

The helpers that compute and read a log are in [`tlp.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c), which the port driver's [`Makefile`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Makefile) builds; read its object lines for the option the file depends on.

```c
/* drivers/pci/pcie/Makefile:5 */
pcieportdrv-y			:= portdrv.o rcec.o

obj-$(CONFIG_PCIEPORTBUS)	+= pcieportdrv.o bwctrl.o

obj-y				+= aspm.o
obj-$(CONFIG_PCIEAER)		+= aer.o err.o tlp.o
obj-$(CONFIG_CXL_RAS)		+= aer_cxl_rch.o
obj-$(CONFIG_PCIEAER_INJECT)	+= aer_inject.o
obj-$(CONFIG_PCIE_PME)		+= pme.o
obj-$(CONFIG_PCIE_DPC)		+= dpc.o
obj-$(CONFIG_PCIE_PTM)		+= ptm.o
obj-$(CONFIG_PCIE_EDR)		+= edr.o
```

The object tlp.o is built with aer.o and err.o under [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28), and dpc.o under [`CONFIG_PCIE_DPC`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L121). A kernel without AER support therefore has no log helpers at all, and their prototypes in [`pci.h`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h) are declared inside the same option's block. [`aer_tlp_log_len()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L23) turns the control dword, passed as its aercc parameter, into the length; read it for the order of its two tests.

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

A set [`PCI_ERR_CAP_TLP_LOG_FLIT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L819) makes the logged size the answer, the five-bit field that [`PCI_ERR_CAP_TLP_LOG_SIZE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L820) masks, and the prefix registers then count as header. With the bit clear the length is [`PCIE_STD_NUM_TLP_HEADERLOG`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L23), plus the function's [`eetlp_prefix_max`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L443) when [`PCI_ERR_CAP_PREFIX_LOG_PRESENT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L817) says the TLP Prefix Log exists. The function takes the size field as it stands, and a size past fourteen is cut later by the read.

[`eetlp_prefix_max`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L443) is a member of [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) that [`pci_configure_eetlp_prefix()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2373) sets when a function is configured, from the Device Capabilities 2 register. Read the function for the cases in which the member stays zero.

```c
/* drivers/pci/probe.c:2373 */
static void pci_configure_eetlp_prefix(struct pci_dev *dev)
{
	struct pci_dev *bridge;
	unsigned int eetlp_max;
	int pcie_type;
	u32 cap;

	if (!pci_is_pcie(dev))
		return;

	pcie_capability_read_dword(dev, PCI_EXP_DEVCAP2, &cap);
	if (!(cap & PCI_EXP_DEVCAP2_EE_PREFIX))
		return;

	pcie_type = pci_pcie_type(dev);

	eetlp_max = FIELD_GET(PCI_EXP_DEVCAP2_EE_PREFIX_MAX, cap);
	/* 00b means 4 */
	eetlp_max = eetlp_max ?: 4;

	if (pcie_type == PCI_EXP_TYPE_ROOT_PORT ||
	    pcie_type == PCI_EXP_TYPE_RC_END)
		dev->eetlp_prefix_max = eetlp_max;
	else {
		bridge = pci_upstream_bridge(dev);
		if (bridge && bridge->eetlp_prefix_max)
			dev->eetlp_prefix_max = eetlp_max;
	}
}
```

The member stays zero for a function that does not report End-End TLP Prefix support in [`PCI_EXP_DEVCAP2_EE_PREFIX`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L677), and otherwise takes the two-bit [`PCI_EXP_DEVCAP2_EE_PREFIX_MAX`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L678), whose zero the comment reads as four. A Root Port or a Root Complex Integrated Endpoint stores that value directly, and any other function only when the bridge above it has a nonzero value of its own. An AER log of a function below a bridge without prefix support therefore has no prefix dwords, even when the function's own register reports support.

The lengths these rules give for an AER log land on one ruler with the array that receives them.

```text
    How many dwords the AER log holds, against the fourteen entries of dw[]
    ───────────────────────────────────────────────────────────────────────
    dwords             0     2     4     6     8     10    12    14    16
                       ├─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼──▶ 31
    dw[] entries       ██████████████████████████████████████████          14 = PCIE_STD_MAX_TLP_HEADERLOG
    F clear, P clear   ████████████                                        4 = PCIE_STD_NUM_TLP_HEADERLOG
    F clear, P set     ████████████▓▓▓▓▓▓▓▓▓▓▓▓                            4 + eetlp_prefix_max, at most 8
    F set              ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░┆░░░░░▶   Logged TLP Size, 0 to 31

    P = PCI_ERR_CAP_PREFIX_LOG_PRESENT and F = PCI_ERR_CAP_TLP_LOG_FLIT, both in the aercc dword
    █ header dwords; ▓ End-End TLP Prefix dwords; ░ any length the size field can name, ┆ where reads stop
```

Outside Flit mode an AER log is four to eight dwords, inside the array. A Flit log can name more dwords than the array holds, and the read stops at fourteen.

### DPC sizes its log from a size fixed at enumeration

A Root Port with Downstream Port Containment logs a header of its own for RP PIO errors, the configuration, I/O and memory requests it issued that received an Unsupported Request or Completer Abort completion or timed out. The length of that log comes from the RP PIO Log Size of the DPC Capability register, which counts the header, the prefix registers and one implementation-specific dword, the ImpSpec Log. The DPC code computes the size once, when the capabilities of a new function are set up, and keeps it in [`dpc_rp_log_size`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L539) of [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352).

The DPC Capability register's macros in [`pci_regs.h`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h) name the Root Port Extensions bit and the two pieces of the size; read them for bits 11:8 and the separate bit 13.

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

[`PCI_EXP_DPC_CAP_RP_EXT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1084) says whether the port has the RP PIO registers at all. [`PCI_EXP_DPC_RP_PIO_LOG_SIZE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1087) holds the low four bits of the size, and [`PCI_EXP_DPC_RP_PIO_LOG_SIZE4`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1089) a fifth bit, which the kernel adds only for a port that supports Flit mode. [`pci_dpc_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L403) finds the DPC capability, notes the extensions and computes the size; read its second half for the bounds it enforces.

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

The size is computed only while [`dpc_rp_log_size`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L539) is still zero, and a port whose PCI Express Capabilities register has [`PCI_EXP_FLAGS_FLIT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L497) set adds the fifth bit as bit 4. A size below [`PCIE_STD_NUM_TLP_HEADERLOG`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L23) or above [`PCIE_STD_MAX_TLP_HEADERLOG`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L25) plus one prints "RP PIO log size %u is invalid" and is stored as zero. The upper bound is fourteen log dwords and the ImpSpec dword.

The zero test leaves room for the member's only other writer, since, according to the comment at [`dpc.c:417`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L417), quirks may set it for a buggy device or firmware. [`dpc_log_size()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/quirks.c#L6335) in [`quirks.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/quirks.c) is that quirk, a header fixup for a list of Root Ports whose firmware clears the size field; read it for its condition and its message.

```c
/* drivers/pci/quirks.c:6330 */
/*
 * Intel Ice Lake, Tiger Lake and Alder Lake BIOS has a bug that clears
 * the DPC RP PIO Log Size of the integrated Thunderbolt PCIe Root
 * Ports.
 */
static void dpc_log_size(struct pci_dev *dev)
{
	u16 dpc, val;

	dpc = pci_find_ext_capability(dev, PCI_EXT_CAP_ID_DPC);
	if (!dpc)
		return;

	pci_read_config_word(dev, dpc + PCI_EXP_DPC_CAP, &val);
	if (!(val & PCI_EXP_DPC_CAP_RP_EXT))
		return;

	if (FIELD_GET(PCI_EXP_DPC_RP_PIO_LOG_SIZE, val) == 0) {
		pci_info(dev, "Overriding RP PIO Log Size to %d\n",
			 PCIE_STD_NUM_TLP_HEADERLOG);
		dev->dpc_rp_log_size = PCIE_STD_NUM_TLP_HEADERLOG;
	}
}
```

The fixup acts only on a port with the RP Extensions whose size field reads zero, and it prints "Overriding RP PIO Log Size to %d" with four. Such a port then logs a four-dword header and no ImpSpec dword, and [`pci_dpc_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L403) skips its own computation for it. Both writers run while the function is set up, before the DPC service of the port can read a log, so the member keeps one value for the port's lifetime and the page draws no strip for it.

[`dpc_tlp_log_len()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L40) turns the cached size into the length the read takes, and exists only with [`CONFIG_PCIE_DPC`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L121) set; read it for the dword it removes.

```c
/* drivers/pci/pcie/tlp.c:33 */
#ifdef CONFIG_PCIE_DPC
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
#endif
```

From five dwords up the size includes the ImpSpec Log, which the function subtracts, as its comment says. A size of exactly four describes a header with no ImpSpec dword and is returned unchanged. The figure places the possible sizes on one axis with the lengths they produce.

```text
    Where a cached RP PIO Log Size lands, and the log length dpc_tlp_log_len() makes of it
    ──────────────────────────────────────────────────────────────────────────────────────
    size    0           4  5                             15       31
            ···░░░░░░░░░████████████████████████████████████░░░░░░░
            ┌───────────┬──┬─────────────────────────────┬───┄┄┄┄─┐
            │           │  │                             │        └─ 16 to 31, reached only through bit 4: rejected, 0
            │           │  │                             └─ 15 = PCIE_STD_MAX_TLP_HEADERLOG + 1: length 14
            │           │  └─ 5 and above: ImpSpec Log present, length = size - 1
            │           └─ 4 = PCIE_STD_NUM_TLP_HEADERLOG: length 4, no ImpSpec Log
            └─ 0: no log read; 1 to 3 rejected at enumeration, stored as 0

    █ a size pci_dpc_init() keeps; ░ a size it rejects; · no RP PIO log
```

A DPC log is therefore four to fourteen dwords whenever the port has one, and the ImpSpec dword never enters the structure.

### pcie_read_tlp_log fills the log from two register windows

With a length in hand, the reader copies the registers into a log. Both capabilities lay their log out as a Header Log of four dwords and, after other registers, a second window that holds prefix dwords or more header dwords, so [`pcie_read_tlp_log()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L63) takes the two offsets apart, as its where and where2 parameters. Its tlp_len parameter is the length, its flit parameter says whether the error was logged in Flit mode, and its log parameter is the structure to fill.

Read [`pcie_read_tlp_log()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L63) for the cut to the array size, the clearing, the split between the windows and the two members it sets last.

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

The length is first cut to the fourteen entries of [`dw`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L31), so a logged size past fourteen reads fourteen dwords. The whole structure is then cleared, and each dword below [`PCIE_STD_NUM_TLP_HEADERLOG`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L23) comes from the first window while the rest come from the second, counted from its start. [`header_len`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L37) becomes the length for a Flit log and four otherwise, because, according to the comment, the exact length outside Flit mode is known only by parsing the TLP, which no code on this path does.

Each read goes through [`pci_read_config_dword()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/access.c#L580), the configuration accessor of [`access.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/access.c); read it for what it stores when the function is gone.

```c
/* drivers/pci/access.c:580 */
int pci_read_config_dword(const struct pci_dev *dev, int where,
					u32 *val)
{
	if (pci_dev_is_disconnected(dev)) {
		PCI_SET_ERROR_RESPONSE(val);
		return PCIBIOS_DEVICE_NOT_FOUND;
	}
	return pci_bus_read_config_dword(dev->bus, dev->devfn, where, val);
}
EXPORT_SYMBOL(pci_read_config_dword);
```

A disconnected function makes the accessor store all ones in the destination and return an error. The reader then returns at once, leaving [`header_len`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L37) and [`flit`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L38) at their cleared values and the later dwords zero. Neither of its two callers, shown in the subsections that follow, checks the returned value, so such a log is printed as the reader left it.

The figure lays the offsets of each capability beside the array to show which register each dword comes from.

```text
    Where pcie_read_tlp_log() takes each dword of the log from, in each capability
    ──────────────────────────────────────────────────────────────────────────────

    AER capability, aer_cap +                    dw[]                       DPC capability, dpc_cap +
                                            ┌─────────────┐
    +0x1c  Header Log           ───────────▶│ dw[0]       │◀──────────────  +0x20  RP PIO Header Log
    +0x20                       ───────────▶│ dw[1]       │◀──────────────  +0x24
    +0x24                       ───────────▶│ dw[2]       │◀──────────────  +0x28
    +0x28                       ───────────▶│ dw[3]       │◀──────────────  +0x2c
                                            │             │
    +0x2c .. +0x37  Root Error              │             │                 +0x30  RP PIO ImpSpec Log,
    registers, skipped                      │             │                 skipped
    +0x38  TLP Prefix Log       ───────────▶│ dw[4]       │◀──────────────  +0x34  RP PIO TLP Prefix Log
    +0x3c                       ───────────▶│ dw[5]       │◀──────────────  +0x38
    +0x40                       ───────────▶│ dw[6]       │◀──────────────  +0x3c
    +0x44                       ───────────▶│ dw[7]       │◀──────────────  +0x40
    +0x48 .. +0x5c              ───────────▶│ dw[8..13]   │◀──────────────  +0x44 .. +0x58
                                            └─────────────┘

    dw[i] for i < 4 (PCIE_STD_NUM_TLP_HEADERLOG) comes from where + 4 * i, the Header Log
    dw[i] for i >= 4 comes from where2 + 4 * (i - 4), the prefix dwords, or the later header
    dwords of a Flit log; reads stop at tlp_len, at most 14 = PCIE_STD_MAX_TLP_HEADERLOG
    the array itself has no gap: the space between dw[3] and dw[4] stands for the registers skipped
```

For AER the reader skips the three Root Error registers between the windows, and for DPC the ImpSpec Log, which [`dpc_process_rp_pio_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L190) reads on its own. The same arithmetic serves both capabilities, since only the two base offsets differ.

The reader sets two members apart from the dwords, and a failed read leaves both at their cleared values. The strip follows one log through the reader, with the failed case beneath.

```text
    One struct pcie_tlp_log through pcie_read_tlp_log(), and what a failed read leaves
    ──────────────────────────────────────────────────────────────────────────────────
    fields: dw[] with prefix[] inside it, header_len, flit

    time ─────────────────────────────────────────────────────────────────────────────────────────────────────────▶
    event            the caller's copy memset          each read           lengths set           printed
                     ▼                 ▼               ▼                   ▼                     ▼
                    ┌─────────────────┬───────────────┬───────────────────┬────────────────────────────────────────┐
    dw[]            │ stale or unset  │① all zero     │② dw[0..len-1]     │ the read values                        │
                    └─────────────────┴───────────────┴───────────────────┴────────────────────────────────────────┘
                    ┌─────────────────┬───────────────────────────────────┬────────────────────────────────────────┐
    header_len      │ stale or unset  │① 0                                │③ 4, or tlp_len if flit                 │
                    └─────────────────┴───────────────────────────────────┴────────────────────────────────────────┘
                    ┌─────────────────┬───────────────────────────────────┬────────────────────────────────────────┐
    flit            │ stale or unset  │① false                            │④ the flit argument                     │
                    └─────────────────┴───────────────────────────────────┴────────────────────────────────────────┘
                    ┌─────────────────┬───────────────┬───────────────────┐
    a read fails    │ stale or unset  │① all zero     │② dw[0] .. dw[i]   │ returns early: header_len 0, flit false
                    └─────────────────┴───────────────┴───────────────────┘

    ①  pcie_read_tlp_log  tlp.c:72  clears every field of the structure with memset
    ②  pcie_read_tlp_log  tlp.c:80  reads one dword into dw[i] through pci_read_config_dword
    ③  pcie_read_tlp_log  tlp.c:89  sets header_len to 4, or to tlp_len for a Flit log
    ④  pcie_read_tlp_log  tlp.c:90  records in flit whether the error was logged in Flit mode
```

① [`pcie_read_tlp_log()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L72) clears every member with memset, whatever the caller's copy held before. ② `pcie_read_tlp_log()` reads each dword into [`dw`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L31) through [`pci_read_config_dword()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/access.c#L580), stopping at the first failure. ③ `pcie_read_tlp_log()` sets [`header_len`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L37) to four, or to the length for a Flit log. ④ `pcie_read_tlp_log()` stores its flit parameter in [`flit`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L38).

The strip draws the writes of the reader alone, and the holders of a log write it too. [`aer_isr_one_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1405) in [`aer.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c) builds the AER service's [`struct aer_err_info`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L833) with an initializer that zeroes its [`tlp`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L853), a write left out because the function belongs to the AER service and only clears the log. [`dpc_process_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L264) and [`pci_print_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L926) zero the logs of their own [`struct aer_err_info`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L833) locals the same way, and the later subsections show those lines. On the firmware-first route, [`ghes_handle_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L640) in [`ghes.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c) copies a firmware record over a whole [`struct aer_capability_regs`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L41), the log in [`header_log`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L49) included, an ACPI function this page names at the seam and does not show.

So far, a log has a structure, a length taken from its capability and a reader that fills it from two windows, and nothing yet has decided when the reader runs.

### The AER status decides whether a header was logged

A component logs a header only after some errors, so the AER path reads the Header Log only when the status says a header is there. The rule is a set of status bits in [`AER_LOG_TLP_MASKS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L99) and one bit of the control dword, and [`tlp_header_logged()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L815) applies it to the Uncorrectable Error Status the path has read. The bits it tests are drawn in REGISTERS with the register that holds them, so this subsection adds no figure of its own.

[`AER_LOG_TLP_MASKS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L99) in [`aer.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c) lists the uncorrectable errors that always come with a logged header; read it as the set the test below checks.

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

Each member is one bit of the Uncorrectable Error Status register. Completion Timeout, [`PCI_ERR_UNC_COMP_TIME`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L778), is not in the set, and the test treats it apart. [`tlp_header_logged()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L815) takes the status and the control dword; read it for the two ways it can answer true.

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

Any member of the set in the status means a header was logged, which the comment attributes to section 6.2.7 of the specification. A Completion Timeout counts only when the function sets [`PCI_ERR_CAP_COMP_TIME_LOG`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L818) in its control dword, and any other status means no header. The test reads the status as passed, so a masked member of the set counts as much as an unmasked one.

The test has two callers, the native read in the next subsection and the printer of firmware reports, and in both it decides only whether a log accompanies the report.

### The AER service reads each reporting function's log twice

A Root Port that receives an error message finds the functions that report the error and reads their AER registers, the log among them. The AER service does this in its interrupt thread, with one [`struct aer_err_info`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L833) per event that it refills for each reporting function. This subsection reads the register macros, that structure, the read and the loop that calls it.

The AER registers of the log are named in [`pci_regs.h`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h), from the control dword to the TLP Prefix Log; read the block for the offsets and for the three control bits the length depends on.

```c
/* include/uapi/linux/pci_regs.h:811 */
#define PCI_ERR_CAP		0x18	/* Advanced Error Capabilities & Ctrl*/
#define  PCI_ERR_CAP_FEP(x)	((x) & 0x1f)	/* First Error Pointer */
#define  PCI_ERR_CAP_ECRC_GENC		0x00000020 /* ECRC Generation Capable */
#define  PCI_ERR_CAP_ECRC_GENE		0x00000040 /* ECRC Generation Enable */
#define  PCI_ERR_CAP_ECRC_CHKC		0x00000080 /* ECRC Check Capable */
#define  PCI_ERR_CAP_ECRC_CHKE		0x00000100 /* ECRC Check Enable */
#define  PCI_ERR_CAP_PREFIX_LOG_PRESENT	0x00000800 /* TLP Prefix Log Present */
#define  PCI_ERR_CAP_COMP_TIME_LOG	0x00001000 /* Completion Timeout Prefix/Header Log Capable */
#define  PCI_ERR_CAP_TLP_LOG_FLIT	0x00040000 /* TLP was logged in Flit Mode */
#define  PCI_ERR_CAP_TLP_LOG_SIZE	0x00f80000 /* Logged TLP Size (only in Flit mode) */
#define PCI_ERR_HEADER_LOG	0x1c	/* Header Log Register (16 bytes) */
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
#define PCI_ERR_PREFIX_LOG	0x38	/* TLP Prefix LOG Register (up to 16 bytes) */
```

[`PCI_ERR_HEADER_LOG`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L821) at 0x1c and [`PCI_ERR_PREFIX_LOG`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L836) at 0x38 are the two windows of an AER log, with the three Root Error registers between them. [`PCI_ERR_CAP_PREFIX_LOG_PRESENT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L817), [`PCI_ERR_CAP_TLP_LOG_FLIT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L819) and [`PCI_ERR_CAP_TLP_LOG_SIZE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L820) are the control bits [`aer_tlp_log_len()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L23) reads, and [`PCI_ERR_CAP_FEP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L812) extracts the First Error Pointer read beside them.

[`struct aer_err_info`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L833) in [`pci.h`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h) is the error information the AER service fills for a reporting function, and its last members hold the log; read it for [`tlp_header_valid`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L849) and [`tlp`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L853).

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

[`dev`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L834), [`ratelimit_print`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L835) and [`error_dev_num`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L836) list the reporting functions and whether each may print, [`root_ratelimit_print`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L842) says whether the Root Port may, and [`level`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L837) is the printk level of the event. [`id`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L839), [`severity`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L841), [`multi_error_valid`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L844) and [`first_error`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L846) describe the event as the Root Port and the function recorded it, and the remaining bit-fields pad the word and pick the bus name that messages print. [`status`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L851) and [`mask`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L852) are the function's status and mask. [`tlp_header_valid`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L849) says whether [`tlp`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L853), the log itself, belongs to the function being reported.

[`aer_get_device_error_info()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1293) reads the AER registers of one reporting function into that structure, and the log read comes at its end; read the whole function for the conditions that lead to the read.

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

[`tlp_header_valid`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L849) is cleared on entry, so a log the previous function left in [`tlp`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L853) is never reported for this one. A correctable error takes the first branch and reads no log. An uncorrectable error is read for a Root Port, a Root Complex Event Collector or a Downstream Port, or when it is non-fatal, and only when an unmasked status bit is set. A fatal error of an Endpoint or an Upstream Port leaves the registers unread, and the comment inside the branch gives the reason for the cases it admits, a link still healthy for I/O reads.

The control dword then gives the First Error Pointer and, through [`tlp_header_logged()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L815), decides the read. [`tlp_header_valid`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L849) is set before [`pcie_read_tlp_log()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L63) runs, which takes the two AER windows, the length from [`aer_tlp_log_len()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L23) and the Flit bit of the same control dword. [`aer_process_err_devices()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1352) calls the read for every reporting function, twice; read it for its two loops.

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

The first loop reads and prints every function before the second reads each one again and hands it on for handling, so that, as the comment says, every record is reported before a reset can lose it. Each call refills the same [`tlp`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L853), and the print in the first loop follows its own read directly. Over one event with two reporting functions, the reads, the log they leave in the shared structure and the service's actions line up as the figure shows.

```text
    One uncorrectable event reported by two functions: each log is read once per pass
    ─────────────────────────────────────────────────────────────────────────────────

    time ────────────────────────────────────────────────────────────────────────────────────────────────────────▶
                        first pass: report every function             second pass: hand each to recovery

    function A's AER    status, log                                   status, log
    registers               │                                             │
                            │                                             │
    function B's AER        │                 status, log                 │                 status, log
    registers               │                     │                       │                     │
                            │                     │                       │                     │
                            ▼                     ▼                       ▼                     ▼
    e_info.tlp            A's log ────────────▶ B's log ──────────────▶ A's log ────────────▶ B's log
                            │                     │                       │                     │
                            │                     │                       │                     │
                            ▼                     ▼                       ▼                     ▼
    AER service         A traced              B traced                A handed to           B handed to
    thread              and printed           and printed             recovery              recovery

    A's log is read again in the second pass after B's has replaced it in e_info.tlp;
    a correctable event reads no log, and e_info.tlp_header_valid stays 0 for it
```

Each log is read from the hardware twice, and a function's log stays in [`tlp`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L853) only from its own read to the next function's. The trace record and the print of the first pass therefore describe the function they name.

### The DPC path reads its log into a local copy

When a port contains an error because one of its own requests failed, the DPC service reports the RP PIO registers before recovery starts. The log goes into a [`struct pcie_tlp_log`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L29) on the stack of the reporting function, because nothing after the report keeps it. [`dpc_process_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L264) chooses the report from the trigger reason in the DPC Status register; read its start and its last case, the cases between them printing the other trigger reasons.

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
	... /* 11 lines, to :295 */
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

An uncorrectable error the port detected itself goes through [`aer_get_device_error_info()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1293) and [`aer_print_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L865) like an AER event, so the port's AER log is read and printed there, held in a zeroed [`struct aer_err_info`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L833). The RP PIO report runs when the trigger reason extension says RP PIO error and the port has [`dpc_rp_extensions`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L538), which [`pci_dpc_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L403) set. The RP PIO registers are named at the end of the DPC block of [`pci_regs.h`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h); read them for the two windows and the dword between them.

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

[`PCI_EXP_DPC_RP_PIO_HEADER_LOG`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1117) at 0x20 and [`PCI_EXP_DPC_RP_PIO_TLPPREFIX_LOG`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1119) at 0x34 are the two windows, and [`PCI_EXP_DPC_RP_PIO_IMPSPEC_LOG`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1118) at 0x30 lies between them. The status, mask, severity, SysError and exception registers before them describe the failure itself. [`dpc_process_rp_pio_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L190) prints those registers and then the log; read its declarations and its end, where the log is read.

```c
/* drivers/pci/pcie/dpc.c:190 */
static void dpc_process_rp_pio_error(struct pci_dev *pdev)
{
	u16 cap = pdev->dpc_cap, dpc_status, first_error;
	u32 status, mask, sev, syserr, exc, log;
	struct pcie_tlp_log tlp_log;
	int i;
	... /* 22 lines, to :218 */
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

The local tlp_log of [`dpc_process_rp_pio_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L190) starts uninitialized, and the reader clears it. A cached RP PIO size below [`PCIE_STD_NUM_TLP_HEADERLOG`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L23) skips the log and the ImpSpec dword, and a size of exactly four skips only the ImpSpec dword. The read takes the two RP PIO windows and the length from [`dpc_tlp_log_len()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L40), and the log is printed at once at KERN_ERR.

The Flit flag of this read has no register behind it, because the DPC Capability does not record whether an error was logged in Flit mode, which commit [7e077e6707b3](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=7e077e6707b3428562ba30d883ff8f54e98dc18b) ("PCI/ERR: Handle TLP Log in Flit mode") calls an oversight in the specification. The read takes [`flit_mode`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L734) of the port's secondary bus instead, which [`pcie_update_link_speed()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L830) refreshes from the port's Link Status 2 register; read it for the two registers it passes on.

```c
/* drivers/pci/probe.c:830 */
void pcie_update_link_speed(struct pci_bus *bus,
			    enum pcie_link_change_reason reason)
{
	struct pci_dev *bridge = bus->self;
	u16 linksta, linksta2;

	pcie_capability_read_word(bridge, PCI_EXP_LNKSTA, &linksta);
	pcie_capability_read_word(bridge, PCI_EXP_LNKSTA2, &linksta2);

	__pcie_update_link_speed(bus, reason, linksta, linksta2);
}
```

[`__pcie_update_link_speed()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L637) stores the bus speed and the Flit Mode Status bit, [`PCI_EXP_LNKSTA2_FLIT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L714); read it for the second line, which writes [`flit_mode`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L734).

```c
/* drivers/pci/pci.h:637 */
static inline void __pcie_update_link_speed(struct pci_bus *bus,
					    enum pcie_link_change_reason reason,
					    u16 linksta, u16 linksta2)
{
	bus->cur_bus_speed = pcie_link_speed[linksta & PCI_EXP_LNKSTA_CLS];
	bus->flit_mode = (linksta2 & PCI_EXP_LNKSTA2_FLIT) ? 1 : 0;

	trace_pcie_link_event(bus,
			     reason,
			     FIELD_GET(PCI_EXP_LNKSTA_NLW, linksta),
			     linksta & PCI_EXP_LNKSTA_LINK_STATUS_MASK);
}
```

[`flit_mode`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L734) is thus the Flit Mode Status as of the link's last update. According to the same commit, the DPC path cannot read the status afresh, because containment brings the link down and the status is set only in certain link states.

So the DPC log differs from an AER log in its holder, a local copy, in its length, fixed at enumeration, and in its Flit flag, taken from the link's last known state.

### pcie_print_tlp_log prints a log as one line of dwords

Every log reaches the kernel log as one line, whichever path read it. [`pcie_print_tlp_log()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L106) formats the dwords in hexadecimal into a buffer on its stack and prints the buffer at the caller's level after the caller's prefix, interpreting none of them. Read [`EE_PREFIX_STR`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L95), the label of the prefix dwords, and the printer after it for the size of the buffer and the two branches on [`flit`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L38).

```c
/* drivers/pci/pcie/tlp.c:95 */
#define EE_PREFIX_STR " E-E Prefixes:"

/**
 * pcie_print_tlp_log - Print TLP Header / Prefix Log contents
 * @dev: PCIe device
 * @log: TLP Log structure
 * @level: Printk log level
 * @pfx: String prefix
 *
 * Prints TLP Header and Prefix Log information held by @log.
 */
void pcie_print_tlp_log(const struct pci_dev *dev,
			const struct pcie_tlp_log *log, const char *level,
			const char *pfx)
{
	/* EE_PREFIX_STR fits the extended DW space needed for the Flit mode */
	char buf[11 * PCIE_STD_MAX_TLP_HEADERLOG + 1];
	unsigned int i;
	int len;

	len = scnprintf(buf, sizeof(buf), "%#010x %#010x %#010x %#010x",
			log->dw[0], log->dw[1], log->dw[2], log->dw[3]);

	if (log->flit) {
		for (i = PCIE_STD_NUM_TLP_HEADERLOG; i < log->header_len; i++) {
			len += scnprintf(buf + len, sizeof(buf) - len,
					 " %#010x", log->dw[i]);
		}
	} else {
		if (log->prefix[0])
			len += scnprintf(buf + len, sizeof(buf) - len,
					 EE_PREFIX_STR);
		for (i = 0; i < ARRAY_SIZE(log->prefix); i++) {
			if (!log->prefix[i])
				break;
			len += scnprintf(buf + len, sizeof(buf) - len,
					 " %#010x", log->prefix[i]);
		}
	}

	dev_printk(level, &dev->dev, "%sTLP Header%s: %s\n", pfx,
		log->flit ? " (Flit)" : "", buf);
}
```

The first four dwords are always printed, whatever [`header_len`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L37) says, so a Flit log shorter than four dwords still prints four. A Flit log adds the dwords from the fifth up to [`header_len`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L37). Any other log adds the label and the prefix dwords when the first prefix dword is nonzero, stopping at the first zero one. The line names "TLP Header", with " (Flit)" after it for a Flit log, and takes its level and prefix from the caller.

The buffer is sized for the longest line the two branches can build, which the figure measures on one ruler as the comment above the declaration claims for the Flit branch.

```text
    What the TLP Header text needs from buf[], 11 * PCIE_STD_MAX_TLP_HEADERLOG + 1 = 155 bytes
    ──────────────────────────────────────────────────────────────────────────────────────────
    bytes             0                    43     57                    101                     153 155
                      ├────────────────────┼──────┼─────────────────────┼─────────────────────────┼┤
    buf[]             ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒   155
    Flit, 14 dwords   █████████████████████▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓    153 + NUL
    4 E-E Prefixes    █████████████████████░░░░░░░▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓                              101 + NUL

    █ the four dwords every line prints, 4 * 10 characters and 3 spaces; the lower bar is a log
      read outside Flit mode with all four prefix dwords nonzero
    ▓ one dword more per 11 characters, a space and ten characters of %#010x
    ░ EE_PREFIX_STR, " E-E Prefixes:", 14 characters; ▒ the array scnprintf() writes into
```

The Flit branch is the longer one, 153 characters for fourteen dwords, and the 155 bytes leave room for it and its terminating NUL. The prefix branch needs 101 characters, so its label fits in the space the extra Flit dwords would take, as the comment at the declaration says.

On the native AER path [`aer_print_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L865) prints one reporting function's error and passes the log to the printer at the end. Read its start, where the trace record is taken, and its end, where the log is printed.

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
	... /* 20 lines, to :903 */
	if (info->tlp_header_valid)
		pcie_print_tlp_log(dev, &info->tlp, level, dev_fmt("  "));

out:
	if (info->id && info->error_dev_num > 1 && info->id == id)
		pci_err(dev, "  Error of this Agent is reported first\n");
}
```

The trace record takes the log before the rate limit is checked, and the printer runs only for a function that may print, has a nonzero status and has [`tlp_header_valid`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L849) set. The level is the event's, KERN_ERR for an uncorrectable error. The prefix dev_fmt("  ") comes from the two format macros at the top of [`aer.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c); read them for its text.

```c
/* drivers/pci/pcie/aer.c:15 */
#define pr_fmt(fmt) "AER: " fmt
#define dev_fmt pr_fmt
```

dev_fmt() is pr_fmt() in this file, so the prefix is "AER:" followed by three spaces, and an AER log prints as "AER:   TLP Header: " and the dwords after the device's name. The DPC file defines its own dev_fmt() at its top; read the line for the prefix of an RP PIO log.

```c
/* drivers/pci/pcie/dpc.c:9 */
#define dev_fmt(fmt) "DPC: " fmt
```

[`dpc_process_rp_pio_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L190) passes dev_fmt(""), so an RP PIO log prints as "DPC: TLP Header: " and its dwords, and every printed log tells which service read it.

### A firmware report carries its log in a copied structure

When the platform firmware owns AER, the kernel receives a log inside an ACPI error record and reads no register for it. With [`CONFIG_ACPI_APEI_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Kconfig#L37) set, the GHES driver copies the record's image of the AER capability into a [`struct aer_capability_regs`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L41), and a work item passes it to [`pci_print_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L926). This page assumes [`CONFIG_ACPI_APEI_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Kconfig#L37) unset, which compiles the route out, and shows the route only for what it does with the log.

[`struct aer_capability_regs`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L41) in [`aer.h`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h) lays out the copied registers, with a [`struct pcie_tlp_log`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L29) where the Header Log stands; read the definition for that member.

```c
/* include/linux/aer.h:41 */
struct aer_capability_regs {
	u32 header;
	u32 uncor_status;
	u32 uncor_mask;
	u32 uncor_severity;
	u32 cor_status;
	u32 cor_mask;
	u32 cap_control;
	struct pcie_tlp_log header_log;
	u32 root_command;
	u32 root_status;
	u16 cor_err_source;
	u16 uncor_err_source;
};
```

The members before [`header_log`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L49) are the capability's dwords from its header to [`cap_control`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L48), the control dword, and the members after it are the Root Port registers and the error source identifiers. [`header_log`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L49) is a whole [`struct pcie_tlp_log`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L29), fourteen dwords and two bytes, where the capability has four Header Log dwords. Its [`header_len`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L37) and [`flit`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L38) are therefore bytes of the copied record that no reader set.

[`pci_print_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L926) prints such a record. Read its start for where the validity of the log comes from and its end for the print.

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
	... /* 17 lines, to :974 */
	if (tlp_header_valid)
		pcie_print_tlp_log(dev, &aer->header_log, info.level,
				   dev_fmt("  "));
}
```

The local tlp_header_valid of [`pci_print_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L926) is set only for an uncorrectable error, and only when [`tlp_header_logged()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L815) finds a header in the copied status and control dword. The trace record takes [`header_log`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L49) whole, and the printer runs at the error's level with the same "AER: " prefix as the native path. The info local, zeroed by its initializer apart from the two members it names, holds the status for the messages and never a log.

A firmware log is therefore printed by the same function as a native one, while its Flit flag and its length are whatever the record holds at those bytes.

So far, a log has been read by the AER service for each reporting function, by the DPC service for a port's own request, or copied from a firmware record, and printed as one line with the prefix of the path that holds it.

### The trace record and the kernel log show a log

A reader who wants to see a log has two places to look, the trace record of an AER error and the TLP Header line of the kernel log. The trace event [`aer_event`](https://elixir.bootlin.com/linux/v7.2/source/include/ras/ras_event.h#L337) of [`ras_event.h`](https://elixir.bootlin.com/linux/v7.2/source/include/ras/ras_event.h), which user space sees as ras:aer_event, fires from [`aer_print_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L865) and [`pci_print_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L926) and copies the log into the record; read the definition for the copy and the output format.

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

	TP_STRUCT__entry(
		__string(	dev_name,	dev_name	)
		__field(	u32,		status		)
		__field(	u8,		severity	)
		__field(	u8, 		tlp_header_valid)
		__array(	u32, 		tlp_header, PCIE_STD_MAX_TLP_HEADERLOG)
		__string(	bus_type,	bus_type	)
	),

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

The event copies all [`PCIE_STD_MAX_TLP_HEADERLOG`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L25) dwords when the log is valid, the prefix dwords of a non-Flit log included, and records neither [`header_len`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L37) nor [`flit`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L38). Its output prints "Not available" for an error without a log. The DPC RP PIO path fires no tracepoint at v7.2, so its log appears only in the kernel log.

The messages of these paths print at the sites in the table. All of them use pci_err(), pci_info() or dev_printk() at a caller's level of KERN_ERR or KERN_WARNING, so with [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120) set no dynamic-debug site lies on these paths and there is nothing to enable through /sys/kernel/debug/dynamic_debug/control.

| Site | Message | When it prints |
|---|---|---|
| [`tlp.c:135-136`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L135) | "%sTLP Header%s: %s\n", after "AER:   " or "DPC: " and with " (Flit)" for a Flit log | [`pcie_print_tlp_log()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L106) prints a log for [`aer_print_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L865), [`pci_print_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L926) or [`dpc_process_rp_pio_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L190) |
| [`dpc.c:434-435`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L434) | "RP PIO log size %u is invalid\n" | [`pci_dpc_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L403) rejects an RP PIO size and stores zero |
| [`quirks.c:6348-6349`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/quirks.c#L6348) | "Overriding RP PIO Log Size to %d\n" | [`dpc_log_size()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/quirks.c#L6335) sets the size of a listed Root Port to four |
| [`dpc.c:230`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L230) | "RP PIO ImpSpec Log %#010x\n" | [`dpc_process_rp_pio_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L190) prints the ImpSpec dword of a size of five or more |

The TLP Header line is the one a reader decodes, and the documentation of AER output names a tool that turns its dwords back into header fields.

### Interrupt threads and a work item lead to the log

The reader and the printer run in the context of their caller and defer nothing themselves. The paths that call them start from the hand-offs in the first table, and the second table lists the surfaces that change or show what a read returns.

| Hand-off | Site | What runs after it |
|---|---|---|
| the AER interrupt thread | [`aer.c:1632-1633`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1632) | [`aer_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1449), from which [`aer_get_device_error_info()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1293) reads each reporting function |
| the DPC interrupt thread | [`dpc.c:483-485`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L483) | [`dpc_handler()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L363), which calls [`dpc_process_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L264) |
| the firmware-first work item, with [`CONFIG_ACPI_APEI_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Kconfig#L37) | [`aer.c:1261`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1261) | [`aer_recover_work_func()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1218), which calls [`pci_print_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L926) |
| the EDR notification, with [`CONFIG_PCIE_EDR`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L140) | [`edr.c:193`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/edr.c#L193) | [`dpc_process_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L264) for the port the firmware names, from [`edr_handle_event()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/edr.c#L151) |

The error injector is the one surface that changes what the reader returns. With [`CONFIG_PCIEAER_INJECT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L37) set, a user writes an error to /dev/aer_inject, and the injector's configuration accessor answers reads of the registers it simulates; read [`find_pci_config_dword()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer_inject.c#L138) for the registers its cases simulate.

```c
/* drivers/pci/pcie/aer_inject.c:138 */
static u32 *find_pci_config_dword(struct aer_error *err, int where,
				  int *prw1cs)
{
	int rw1cs = 0;
	u32 *target = NULL;

	if (err->pos_cap_err == -1)
		return NULL;

	switch (where - err->pos_cap_err) {
	case PCI_ERR_UNCOR_STATUS:
		target = &err->uncor_status;
		rw1cs = 1;
		break;
	case PCI_ERR_COR_STATUS:
		target = &err->cor_status;
		rw1cs = 1;
		break;
	case PCI_ERR_HEADER_LOG:
		target = &err->header_log0;
		break;
	case PCI_ERR_HEADER_LOG+4:
		target = &err->header_log1;
		break;
	case PCI_ERR_HEADER_LOG+8:
		target = &err->header_log2;
		break;
	case PCI_ERR_HEADER_LOG+12:
		target = &err->header_log3;
		break;
	case PCI_ERR_ROOT_STATUS:
		target = &err->root_status;
		rw1cs = 1;
		break;
	case PCI_ERR_ROOT_ERR_SRC:
		target = &err->source_id;
		break;
	}
	if (prw1cs)
		*prw1cs = rw1cs;
	return target;
}
```

Reads of the four Header Log dwords return the values the user injected, while the control dword and the TLP Prefix Log are not among the simulated registers, so they come from the function as it stands.

| Surface | Path | What it shows or changes |
|---|---|---|
| error injection, with [`CONFIG_PCIEAER_INJECT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L37) | /dev/aer_inject | the four header dwords of the next AER log, through [`aer_inj_read_config()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer_inject.c#L217) |
| boot parameter | pci=noaer | [`pci_no_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L133) turns off the native AER service and the reads its interrupt thread makes |
| sysfs, procfs, debugfs | none | no file shows a log, its length or its Flit flag |
| fault injection | none | no fault-injection point covers the reader or the printer |

A log is therefore visible only in the kernel log and, on the AER paths, in the trace record, at the moment its error is reported.
