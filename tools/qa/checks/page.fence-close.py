"""page.fence-close: a closing line that holds more than backticks and spaces,
or no closing line."""


def check(page, context):
    return [
        {"line": p["line"], "quote": p["quote"], "message": p["message"]}
        for p in page.problems
    ]
