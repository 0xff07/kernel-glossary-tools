"""excerpts.catalog-completeness: every catalog key appears in a source fence
body; a CONFIG key by its name or by its `config` line in a unit of a file that
is not C."""

import re

from tools.qa.inputs import violation
from tools.qa.page import MEMBER_KEY, symbol_name


def check(page, context):
    code = page.excerpted_code()
    non_c = "\n".join(
        line
        for unit in page.units
        if not page.profile.is_source(unit.path)
        for _n, line in unit.body
    )
    for key in page.catalog_keys:
        words = key.split()
        member = MEMBER_KEY.match(key)
        config = page.profile.config_re.match(key)
        if len(words) == 2 and words[0] in ("struct", "enum", "union"):
            # a tagged key spelled in the shown code, keyword and tag as whole
            # words; e.g. the key `struct pci_dev` in `struct pci_dev {`
            found = re.search(
                r"(?<!\w)"
                + words[0]
                + r"\s+"
                + re.escape(words[1])
                + r"(?!\w)",
                code,
            )
        elif member:
            # a member key's member as a whole word of the shown code; e.g.
            # error_detected for the key `pci_error_handlers.error_detected`
            found = re.search(
                r"(?<!\w)" + re.escape(member.group(2)) + r"(?!\w)", code
            )
        elif config:
            # a CONFIG key spelled in the shown code, or its option defined in
            # the shown Kconfig text; e.g. `CONFIG_PCIEAER` in `#ifdef
            # CONFIG_PCIEAER`, or the line `config PCIEAER`
            found = re.search(
                r"(?<!\w)" + re.escape(key) + r"(?!\w)", code
            ) or re.search(
                r"^[ \t]*(?:menu)?config[ \t]+"
                + re.escape(config.group(1))
                + r"[ \t]*$",
                non_c,
                re.M,
            )
        else:
            # any other key's name as a whole word of the shown code; e.g.
            # pcie_do_recovery in `pcie_do_recovery(dev, state, cb);`
            found = re.search(
                r"(?<!\w)" + re.escape(symbol_name(key)) + r"(?!\w)", code
            )
        if not found:
            yield violation(
                None, key, f"catalog symbol `{key}` appears in no source fence"
            )
