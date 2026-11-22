# A list marker followed by a tab

## DETAILS

### Two lines a tab after the hyphen

The two lines below begin with a hyphen and a tab, which is no list marker, so they are two prose lines in a row.

-	item one
-	item two

The paragraph after them closes the subsection.

<!-- kg:expect
only:
- page.one-line-paragraphs
findings:
- - page.one-line-paragraphs
  - FAIL
  - 10
  - "-\titem two"
incomplete: []
-->
