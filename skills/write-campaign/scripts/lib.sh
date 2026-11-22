#!/bin/bash
# Sourced by the scripts beside it. The kernel tree is found one way, the same as tools/checkout.py:
#   TREE=$(kg_tree "$CHECKOUT") || exit 1     $KG_TREE when set, else the kernel checkout whose .claude directory holds the checkout
kg_tree_of() { local d; d=$(cd "$1" && pwd) || return 1; while [ "$(basename "$d")" != .claude ]; do [ "$d" = / ] && return 1; d=$(dirname "$d"); done; dirname "$d"; }
kg_tree() { if [ -n "${KG_TREE:-}" ]; then echo "$KG_TREE"; else kg_tree_of "$1" || { echo "no .claude directory above $1; set KG_TREE to the kernel checkout" >&2; return 1; }; fi; }
# kg_campaign_field <spec> <key>: one scalar of the spec's yaml kg:campaign block, empty when absent; run from the checkout
# its regex takes the body of the fence that opens with ```yaml kg:campaign, up to the line that closes it, e.g. the lines `campaign: v7.2-pci` to `section6: REGISTERS`
kg_campaign_field() { "${KG_PYTHON:-.venv/bin/python}" -c "import re,sys,yaml; t=open(sys.argv[1],encoding='utf-8').read(); m=re.search(r'^\`\`\`yaml kg:campaign\n(.*?)\n\`\`\`', t, re.S|re.M); b=yaml.safe_load(m.group(1)) if m else {}; v=b.get(sys.argv[2]); print('' if v is None else v)" "$1" "$2"; }
