"""links.site-text: a location link names its file by base name, by its path
only where two cited files share the base name."""

import collections

from tools.qa.inputs import candidate


def check(page, context):
    cited = page.cited_files()
    by_base = collections.Counter(c.rsplit("/", 1)[-1] for c in cited)
    for link in page.location_links():
        file, first, _last = link.location
        base = file.rsplit("/", 1)[-1]
        if base in ("Kconfig", "Makefile"):
            continue
        if "/" in file and by_base.get(base, 0) < 2:
            yield candidate(
                link.line,
                link.text,
                "a site named by its path while no other cited file is called"
                f" {base}; name it `{base}:{first}`",
            )
        elif "/" not in file and by_base.get(base, 0) >= 2:
            yield candidate(
                link.line,
                link.text,
                f"a bare base name while two cited files are called {base};"
                " name it from the tree root",
            )
