"""Display-cell geometry for figure bodies
(guidelines/page/rules/active/geometry.layout.md, the inspection procedure); no
page state or source-tree access."""

from collections import defaultdict
from functools import lru_cache
import re
import unicodedata

UP, DOWN, LEFT, RIGHT = 1, 2, 4, 8
OPPOSITE = {UP: DOWN, DOWN: UP, LEFT: RIGHT, RIGHT: LEFT}
NAMES = {UP: "up", DOWN: "down", LEFT: "left", RIGHT: "right"}
STEPS = {UP: (-1, 0), DOWN: (1, 0), LEFT: (0, -1), RIGHT: (0, 1)}


def cells(text):
    """One entry per display cell; None is the continuation of a wide
    character."""
    row = []
    for char in text:
        if char == "\t":
            row.extend(" " * (8 - len(row) % 8))
        elif unicodedata.category(char) not in ("Mn", "Me", "Cf"):
            row.append(char)
            if unicodedata.east_asian_width(char) in ("W", "F"):
                row.append(None)
    return row


@lru_cache(maxsize=256)
def ports(char):
    if not char or not "\u2500" <= char <= "\u257f":
        return 0
    name = unicodedata.name(char, "")
    if "DIAGONAL" in name:
        return 0
    directions = set(name.split())
    result = 0
    for word, direction in (
        ("UP", UP),
        ("DOWN", DOWN),
        ("LEFT", LEFT),
        ("RIGHT", RIGHT),
        ("VERTICAL", UP | DOWN),
        ("HORIZONTAL", LEFT | RIGHT),
    ):
        if word in directions:
            result |= direction
    return result


@lru_cache(maxsize=256)
def arrow(char):
    """Tip directions; a two-headed arrow has both bits on its axis."""
    if not char:
        return 0
    if char in "▲△▴▵":
        return UP
    if char in "▼▽▾▿":
        return DOWN
    if char in "◀◁◂◃◄◅":
        return LEFT
    if char in "▶▷▸▹►▻":
        return RIGHT
    if not "\u2190" <= char <= "\u21ff":
        return 0
    name = unicodedata.name(char, "")
    if "DIAGONAL" in name or any(
        word in name for word in ("NORTH", "SOUTH", "HOOK", "CURV", "TURN")
    ):
        return 0
    directions = 0
    for word, direction in (
        ("UP", UP),
        ("DOWN", DOWN),
        ("LEFT", LEFT),
        ("RIGHT", RIGHT),
    ):
        # a direction the arrow's Unicode name states, as a word with or
        # without WARDS; e.g. RIGHT in `RIGHTWARDS ARROW`, and UP and DOWN in
        # `UP DOWN ARROW`
        if re.search(r"\b" + word + r"(?:WARDS)?\b", name):
            directions |= direction
    return (
        directions
        if directions in (UP, DOWN, LEFT, RIGHT, UP | DOWN, LEFT | RIGHT)
        else 0
    )


def dashed(char):
    return bool(char and "DASH" in unicodedata.name(char, ""))


def graphic(char):
    return bool(
        char
        and (
            char == "·"
            or "\u2500" <= char <= "\u259f"
            or "\u2190" <= char <= "\u21ff"
            or "\u25a0" <= char <= "\u25ff"
            or "\u2460" <= char <= "\u24ff"
            or "\u2776" <= char <= "\u2793"
        )
    )


class Drawing:
    """The display cells of one figure body, and the issues its checks find:
    grouped by zero-based body row, columns and related coordinates
    1-based."""

    def __init__(self, body):
        self.grid = [cells(line) for line in body]
        self.issues = defaultdict(list)
        self.seen = set()
        self.caps = self.span_caps()

    def at(self, row, column):
        grid = self.grid
        return (
            grid[row][column]
            if 0 <= row < len(grid) and 0 <= column < len(grid[row])
            else " "
        )

    def add(self, row, column, kind, message, other=None, expected=None):
        key = (row, column, kind, other, expected)
        if key in self.seen:
            return
        self.seen.add(key)
        item = {"kind": kind, "column": column + 1, "message": message}
        if other is not None:
            item["neighbor_row"], item["neighbor_column"] = (
                other[0] + 1,
                other[1] + 1,
            )
        if expected is not None:
            item["expected_column"] = expected + 1
        self.issues[row].append(item)

    def span_caps(self):
        """The cells of span-bar endcaps, whose short vertical strokes stand
        even when no vertical path joins them."""
        at = self.at
        caps = set()
        for row, line in enumerate(self.grid):
            left = None
            for column, char in enumerate(line):
                p = ports(char)
                if (
                    p == UP | DOWN | RIGHT
                    and ports(at(row, column + 1)) & LEFT
                ):
                    left = column
                elif (
                    left is not None
                    and p == UP | DOWN | LEFT
                    and ports(at(row, column - 1)) & RIGHT
                ):
                    caps.update(((row, left), (row, column)))
                    if not any(
                        ports(ch) for ch in line[:left] + line[column + 1 :]
                    ):
                        caps.update(
                            (row, c)
                            for c in range(left + 1, column)
                            if ports(line[c]) & (LEFT | RIGHT) == LEFT | RIGHT
                            and ports(line[c]) & (UP | DOWN)
                        )
                    left = None
        return caps

    def connected_ports(self, row, column):
        at = self.at
        p = ports(at(row, column))
        if (row, column) in self.caps:
            p &= (
                (LEFT | RIGHT)
                | (UP if ports(at(row - 1, column)) & DOWN else 0)
                | (DOWN if ports(at(row + 1, column)) & UP else 0)
            )
        return p

    def check_joins(self, row, column, char, outgoing):
        """A port that faces the cell to its right or below it, where only
        one of the two connects."""
        for direction in (RIGHT, DOWN):
            dr, dc = STEPS[direction]
            nr, nc = row + dr, column + dc
            neighbor = self.at(nr, nc)
            incoming = self.connected_ports(nr, nc)
            if not incoming:
                continue
            a, b = bool(outgoing & direction), bool(
                incoming & OPPOSITE[direction]
            )
            if a == b:
                continue
            if (dashed(char) and outgoing in (UP | DOWN, LEFT | RIGHT)) or (
                dashed(neighbor) and incoming in (UP | DOWN, LEFT | RIGHT)
            ):
                if outgoing in (UP | DOWN, LEFT | RIGHT) and incoming in (
                    UP | DOWN,
                    LEFT | RIGHT,
                ):
                    continue
            bad_r, bad_c, bad, missing, other = (
                (nr, nc, neighbor, OPPOSITE[direction], (row, column))
                if a
                else (row, column, char, direction, (nr, nc))
            )
            self.add(
                bad_r,
                bad_c,
                "join",
                f"{bad} lacks the {NAMES[missing]} connection",
                other,
            )

    def check_arrows(self, row, column, outgoing):
        """An arrowhead beside the cell whose shaft meets only its tip side.
        An arrow's tip can touch a transverse boundary without a junction."""
        at = self.at
        for direction, (dr, dc) in STEPS.items():
            tips = arrow(at(row + dr, column + dc))
            if not tips or not outgoing & direction or tips & direction:
                continue
            axis = UP | DOWN if direction in (UP, DOWN) else LEFT | RIGHT
            if not tips & axis:
                continue
            head_r, head_c = row + dr, column + dc
            # A head inside a continuous shaft is allowed. Only a head whose
            # shaft lies solely in front of its tip is an orientation
            # candidate.
            supported = False
            for tip, (tr, tc) in STEPS.items():
                if tips & tip and ports(at(head_r - tr, head_c - tc)) & tip:
                    supported = True
            if supported:
                continue
            transverse = LEFT | RIGHT if direction in (UP, DOWN) else UP | DOWN
            if not outgoing & transverse:
                self.add(
                    head_r,
                    head_c,
                    "arrow",
                    "the shaft meets only the arrowhead's tip side",
                    (row, column),
                )

    def check_ports(self):
        """The joins and the arrows of every cell that has a port, cell by
        cell."""
        for row, line in enumerate(self.grid):
            for column, char in enumerate(line):
                outgoing = self.connected_ports(row, column)
                if not outgoing:
                    continue
                self.check_joins(row, column, char, outgoing)
                self.check_arrows(row, column, outgoing)

    def check_shifts(self):
        """A vertical that continues one or two columns aside on the next
        row. Only isolated neighboring endpoints pair, not parallel trunks
        that are already connected."""
        grid, at = self.grid, self.at
        for row in range(len(grid) - 1):
            downs = [
                c
                for c in range(len(grid[row]))
                if self.connected_ports(row, c) & DOWN
                and at(row + 1, c) == " "
            ]
            ups = [
                c
                for c in range(len(grid[row + 1]))
                if self.connected_ports(row + 1, c) & UP and at(row, c) == " "
            ]
            for column in downs:
                candidates = [c for c in ups if 0 < abs(c - column) <= 2]
                if len(candidates) != 1:
                    continue
                target = candidates[0]
                if sum(0 < abs(c - target) <= 2 for c in downs) == 1:
                    self.add(
                        row + 1,
                        target,
                        "shift",
                        "the vertical changes display column",
                        (row, column),
                        column,
                    )

    def horizontal(self, row, left, right):
        return right > left and all(
            ports(self.at(row, c)) & (LEFT | RIGHT) == LEFT | RIGHT
            for c in range(left + 1, right)
        )

    def right_corner(self, row, left, direction):
        for column in range(left + 1, len(self.grid[row])):
            p = ports(self.at(row, column))
            if p == direction:
                return column if self.horizontal(row, left, column) else None
            if p & (LEFT | RIGHT) != LEFT | RIGHT:
                return None
        return None

    def check_box(self, row, left, right):
        """The frame whose top runs from `left` to `right` on `row`: its
        bottom corner and its walls keep the top's columns."""
        at = self.at
        for bottom in range(row + 1, len(self.grid)):
            p = ports(at(bottom, left))
            if p == DOWN | RIGHT:
                break
            if p == UP | LEFT | RIGHT:
                end = (
                    right
                    if (
                        ports(at(bottom, right))
                        in (UP | LEFT, UP | LEFT | RIGHT)
                        and self.horizontal(bottom, left, right)
                    )
                    else None
                )
            elif p == UP | RIGHT:
                end = self.right_corner(bottom, left, UP | LEFT)
            else:
                continue
            if end is None:
                break
            if end != right:
                self.add(
                    bottom,
                    end,
                    "box",
                    "the bottom corner differs from the top's right column",
                    (row, right),
                    right,
                )
            for middle in range(row + 1, bottom):
                for column in (left, right):
                    if ports(at(middle, column)) & (UP | DOWN) != UP | DOWN:
                        self.add(
                            middle,
                            column,
                            "box",
                            "the box wall leaves its fixed column",
                            (row, column),
                            column,
                        )
            break

    def check_boxes(self):
        """Every closed frame against its own top, bottom and side
        columns."""
        for row, line in enumerate(self.grid):
            for left, char in enumerate(line):
                if ports(char) != DOWN | RIGHT:
                    continue
                right = self.right_corner(row, left, DOWN | LEFT)
                if right is not None:
                    self.check_box(row, left, right)

    def check_floating_verticals(self):
        """A bare vertical run that reaches nothing at either end; labelled
        axes and dashed guides keep their open ends."""
        grid, at = self.grid, self.at
        used = set()
        for row, line in enumerate(grid):
            for column, char in enumerate(line):
                if (
                    (row, column) in used
                    or ports(char) != UP | DOWN
                    or dashed(char)
                ):
                    continue
                end = row
                while ports(at(end + 1, column)) == UP | DOWN and not dashed(
                    at(end + 1, column)
                ):
                    end += 1
                used.update((r, column) for r in range(row, end + 1))
                above, below = at(row - 1, column), at(end + 1, column)
                if (
                    graphic(above)
                    or graphic(below)
                    or (above and above.strip())
                    or (below and below.strip())
                ):
                    continue
                if any(
                    any(c and c.isalnum() for c in grid[r])
                    for r in range(row, end + 1)
                ):
                    continue
                self.add(
                    row,
                    column,
                    "vertical",
                    "the unlabelled vertical run reaches nothing at either"
                    " end",
                )


def analyze(body):
    """Issues grouped by zero-based body row; columns and related coordinates
    are 1-based."""
    drawing = Drawing(body)
    drawing.check_ports()
    drawing.check_shifts()
    drawing.check_boxes()
    drawing.check_floating_verticals()
    return dict(drawing.issues)
