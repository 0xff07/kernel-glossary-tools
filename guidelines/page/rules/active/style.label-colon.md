---
qa: off
---

# Label colon

A relation is one declarative sentence with its own verb; a quotation is introduced as "According to the comment <quote>,...", and a paragraph ends in a colon only to introduce the fence that follows it.

| Pattern | Kind | Scope | Unless | Exception |
|---|---|---|---|---|
| a `:` followed by whitespace and a letter, a digit or `§`, the text from the start of its sentence, or of its heading, to the colon holding 1 to 8 words; one candidate per sentence, its first such label, and the quote is that label with its colon | candidate | rows in the lead, SUMMARY and DETAILS that are not catalog rows, table rows or section-six list items, heading rows of every level included | | none |
| a prose line ending in `:` whose next non-blank line opens no fence | candidate | prose lines in the lead, SUMMARY and DETAILS; the quote is the line's last sentence | | none |
