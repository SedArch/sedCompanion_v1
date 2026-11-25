"""
vvm.py - reader and writer for vvm / vvmp files ("keyword = value" lists),
shared by all SedCompanion tools.

Data layout
-----------
In a file, one text line holds the values of one row of nodes (X, west->east),
successive lines are successive rows (Y, south->north), and blank lines separate
layers (Z / time step). Grids are held as NumPy float32 arrays of shape
    (n_layers, n_lines, n_values) == (z, y, x).
"""
from __future__ import annotations

import math
import os
import re
import sys
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

F32 = np.float32
NEWLINE = "\r\n"          # default line ending (CRLF); --lf switches to LF


def set_newline(nl: str) -> None:
    global NEWLINE
    NEWLINE = nl


def err(msg: str) -> None:
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


def out(msg: str = "") -> None:
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()


# --------------------------------------------------------------------------
# C strtod emulation (numeric-token test)
# --------------------------------------------------------------------------
_DEC = r"[+-]?(?:\d+\.?\d*(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?)"
_HEX = r"[+-]?0[xX](?:[0-9a-fA-F]+\.?[0-9a-fA-F]*|\.[0-9a-fA-F]+)(?:[pP][+-]?\d+)?"
_SPC = r"[+-]?(?:[iI][nN][fF](?:[iI][nN][iI][tT][yY])?|[nN][aA][nN](?:\([0-9A-Za-z_]*\))?)"
_NUM_RE = re.compile(r"(?:%s|%s|%s)\Z" % (_HEX, _DEC, _SPC))


def c_strtod_full(tok: str) -> Tuple[bool, float]:
    """True when strtod() consumes the whole token (endptr points at '\\0')."""
    if tok == "":
        return True, 0.0          # strtod("") -> endptr=="" -> treated as number
    if not _NUM_RE.match(tok):
        return False, 0.0
    t = tok.lower()
    sign = -1.0 if t.startswith("-") else 1.0
    body = t.lstrip("+-")
    if body.startswith("0x"):
        if "p" not in body:
            body += "p0"
        return True, sign * float.fromhex(body)
    if body.startswith("inf"):
        return True, sign * math.inf
    if body.startswith("nan"):
        return True, math.nan
    return True, float(tok)


# --------------------------------------------------------------------------
# Line pre-processing
#   1. truncate at the first '!'   (comment)
#   2. strip leading  ' ' and '\t'
#   3. strip trailing ' ' and '\t'
# --------------------------------------------------------------------------
def _prep(line: str) -> str:
    p = line.find("!")
    if p >= 0:
        line = line[:p]
    return line.strip(" \t")


def _is_keyword_line_for_strings(line: str) -> bool:
    """'=' present and (no '"' or '=' appears before first '"')."""
    q = line.find('"')
    e = line.find("=")
    if q >= 0:
        return e != -1 and e < q
    return e != -1


@dataclass
class Record:
    name: str
    strings: List[str] = field(default_factory=list)
    cubes: List[np.ndarray] = field(default_factory=list)   # each (z, y, x) float32
    ok: bool = True
    line: int = 0


class VvmFile:
    """Sequential VVM reader with a read cursor (keywords are found from the current position).

    rewind()               (back to the start; prime current/lookahead)
    find(name)             (scan forward for keyword line == name)
    next_record()          (streaming: next keyword + its value)
    """

    def __init__(self, path: str):
        with open(path, "rb") as f:
            data = f.read()
        text = data.decode("latin-1")
        text = text.replace("\r\n", "\n")       # accept CRLF and LF files
        raw = text.split("\n")
        if text.endswith("\n"):
            raw.pop()
        self.path = path
        self.lines = [_prep(l) for l in raw]
        self.pos = 0
        self.cur: Optional[str] = None           # current buffer (rest of keyword line)

    # -- cursor ---------------------------------------------------------
    def rewind(self) -> None:
        self.pos = 0
        self.cur = None

    def _line(self, i: int) -> Optional[str]:
        return self.lines[i] if 0 <= i < len(self.lines) else None

    def _current(self) -> Optional[str]:
        return self.cur if self.cur is not None else self._line(self.pos)

    def _advance(self) -> None:
        self.cur = None
        self.pos += 1

    # -- keyword scan -------------------------------------
    def next_keyword(self) -> Optional[str]:
        while True:
            line = self._current()
            if line is None:
                return None
            p = line.find("=")
            if p >= 0:
                key = line[:p].strip(" \t")
                self.cur = line[p + 1:]
                return key
            self._advance()

    def find(self, name: str) -> bool:
        while True:
            key = self.next_keyword()
            if key is None:
                return False
            if key == name:
                return True
            self._advance()

    # -- value-type test ----------------------------------
    def _value_is_numeric(self) -> bool:
        cur = self.cur if self.cur is not None else ""
        if cur != "":
            probe = cur
        else:
            nxt = self._line(self.pos + 1)
            if nxt is None or nxt == "":
                return False
            probe = nxt
        toks = probe.split()
        tok = toks[0] if toks else ""
        ok, _ = c_strtod_full(tok)
        return ok

    # -- numeric block reader -----------------------------
    def read_numeric(self) -> Tuple[bool, List[np.ndarray]]:
        groups: List[List[List[List[float]]]] = []
        layers: List[List[List[float]]] = []
        rows: List[List[float]] = []
        blanks = 0
        row_len = -1
        rows_per_layer = -1
        layers_per_group = -1
        first = True
        while True:
            if first:
                line = self.cur if self.cur is not None else ""
                first = False
            else:
                self._advance()
                line = self._line(self.pos)
                if line is None:
                    break
            toks = line.split()
            if not toks:
                blanks += 1
                continue
            vals: List[float] = []
            stop = False
            for t in toks:
                ok, v = c_strtod_full(t)
                if not ok:
                    stop = True
                    break
                vals.append(v)
            if blanks:
                if blanks >= 3:
                    err("ERROR: Too many embedded blank lines")
                    return False, []
                if blanks == 2 and rows:
                    layers.append(rows)
                    if rows_per_layer > 0 and len(rows) != rows_per_layer:
                        err("ERROR: (2) Irregular number of rows in a layer")
                        return False, []
                    rows_per_layer = len(rows)
                    groups.append(layers)
                    if layers_per_group > 0 and len(layers) != layers_per_group:
                        err("ERROR: (2) Irregular number of layers in a group")
                        return False, []
                    layers_per_group = len(layers)
                    layers, rows = [], []
                elif blanks == 1 and rows:
                    layers.append(rows)
                    if rows_per_layer > 0 and len(rows) != rows_per_layer:
                        err("ERROR: (3) Irregular number of rows in a layer")
                        return False, []
                    rows_per_layer = len(rows)
                    rows = []
                blanks = 0
            if vals:
                if row_len > 0 and len(vals) != row_len and not stop:
                    err("ERROR: Irregular number of elements in a row")
                    return False, []
                if not stop:
                    row_len = len(vals)
                rows.append(vals)
            if stop:
                # line is pushed back: it becomes the current line again
                self.cur = None
                break
        if rows:
            layers.append(rows)
            if rows_per_layer > 0 and len(rows) != rows_per_layer:
                err("ERROR: (1) Irregular number of rows in a layer")
                return False, []
        if layers:
            groups.append(layers)
            if layers_per_group > 0 and len(layers) != layers_per_group:
                err("ERROR: (1) Irregular number of layers in a group")
                return False, []
        cubes = []
        for g in groups:
            try:
                cubes.append(np.array(g, dtype=np.float64).astype(F32))
            except ValueError:
                err("ERROR: Irregular number of elements in a row")
                return False, []
        return True, cubes

    # -- string reader ------------------------------------
    def read_strings(self) -> Tuple[bool, List[str]]:
        out_: List[str] = []
        line = self.cur if self.cur is not None else ""
        while True:
            i = 0
            n = len(line)
            while i < n:
                while i < n and line[i] in " \t":
                    i += 1
                if i >= n:
                    break
                if line[i] == '"':
                    j = line.find('"', i + 1)
                    if j < 0:
                        err("ERROR: Unclosed quote")
                        return False, out_
                    out_.append(line[i + 1:j])
                    i = j + 1
                else:
                    j = i
                    while j < n and line[j] not in " \t":
                        j += 1
                    out_.append(line[i:j])
                    i = j
            nxt = self._line(self.pos + 1)
            if nxt is None or _is_keyword_line_for_strings(nxt):
                self._advance()
                return True, out_
            self._advance()
            line = self._line(self.pos) or ""

    # -- read value of a keyword already found ----------------------------
    def read_value(self, name: str) -> Record:
        rec = Record(name=name, line=self.pos)
        if self._value_is_numeric():
            ok, cubes = self.read_numeric()
            rec.ok, rec.cubes = ok, cubes
        else:
            ok, s = self.read_strings()
            rec.ok, rec.strings = ok, s
        return rec

    def next_record(self) -> Optional[Record]:
        key = self.next_keyword()
        if key is None:
            return None
        return self.read_value(key)

    def all_records(self) -> List[Record]:
        self.rewind()
        recs = []
        while True:
            r = self.next_record()
            if r is None:
                return recs
            recs.append(r)

    def keyword_counts(self) -> List[Tuple[str, int]]:
        """Distinct keywords in order + occurrence count."""
        self.rewind()
        names: List[str] = []
        counts: List[int] = []
        while True:
            key = self.next_keyword()
            if key is None:
                break
            if key in names:
                counts[names.index(key)] += 1
            else:
                names.append(key)
                counts.append(1)
            self._advance()
        return list(zip(names, counts))

    # -- composite readers --------------------------------------------------
    def read_all_occurrences(self, name: str, warn: bool = True) -> Optional[List[np.ndarray]]:
        """Every occurrence of a keyword, from the current position."""
        acc: List[np.ndarray] = []
        count = 0
        while self.find(name):
            rec = self.read_value(name)
            if not rec.ok:
                if warn:
                    err("WARNING: Unable to read '%s'" % name)
                return None
            if rec.cubes:
                if acc and acc[0].size != rec.cubes[0].size:
                    err("ERROR: Attempting to append unequal models")
                    err("       Probably repeated parameter with different dimensions")
                    err("ERROR: Unable to append '%s'" % name)
                    return None
                acc.extend(rec.cubes)
            count += 1
        if count == 0:
            if warn:
                err("WARNING: Unable to find keyword '%s'" % name)
            return None
        return acc

    def read_first(self, name: str) -> Optional[List[np.ndarray]]:
        """First occurrence of a keyword only."""
        if not self.find(name):
            err("WARNING: Unable to find keyword '%s'" % name)
            return None
        rec = self.read_value(name)
        if not rec.ok:
            err("WARNING: Unable to read '%s'" % name)
            return None
        return rec.cubes

    def scalar(self, name: str) -> Optional[F32]:
        """First occurrence of a keyword, as a single value."""
        if not self.find(name):
            return None
        rec = self.read_value(name)
        cubes = rec.cubes
        if not cubes:
            return None
        n = len(cubes)
        c = cubes[0]
        zz, yy, xx = c.shape
        if xx * yy * zz * n < 1 or (n < 2 and zz < 2 and yy < 2 and xx < 2):
            return F32(c.reshape(-1)[0])
        return None

    @staticmethod
    def to_vector(cubes: Optional[List[np.ndarray]]) -> Optional[np.ndarray]:
        """Vector from list of cubes."""
        if not cubes:
            return None
        n = len(cubes)
        zz, yy, xx = cubes[0].shape
        prod = xx * yy * zz * n
        if prod < 1:
            return cubes[0][0, 0, :].copy()
        if n < 2:
            if zz > 1:
                return None
            if yy < 2:
                return cubes[0][0, 0, :].copy()
        if zz == 1 and yy == 1 and xx == 1:
            return np.array([c.reshape(-1)[0] for c in cubes], dtype=F32)
        return None

    @staticmethod
    def to_cube(cubes: Optional[List[np.ndarray]]) -> Optional[np.ndarray]:
        """One cube; several single-slice occurrences are stacked."""
        if not cubes:
            return None
        n = len(cubes)
        zz, yy, xx = cubes[0].shape
        if xx * yy * zz * n < 1 or n < 2:
            return cubes[0].copy()
        if zz != 1:
            return None
        return np.concatenate(cubes, axis=0).astype(F32)


# --------------------------------------------------------------------------
# Writers
# --------------------------------------------------------------------------
def fmt_g(v) -> str:
    """ostream << float with default flags/precision (== printf %g)."""
    v = float(v)
    if math.isnan(v):
        return "nan"
    if math.isinf(v):
        return "inf" if v > 0 else "-inf"
    return "%g" % v


def _arma_format(vals: np.ndarray) -> Tuple[str, int]:
    """Choose the number format for an array (see user guide, Numbers in output files)."""
    big = False
    for v in vals.reshape(-1):
        f = float(v)
        if not math.isfinite(f):
            continue
        if f >= 100.0 or f <= -100.0 or (0.0 < f <= 0.0001) or (-0.0001 <= f < 0.0):
            return "e", 13
        if f >= 10.0 or f <= -10.0:
            big = True
    return "f", (10 if big else 9)


def arma_print(m2d: np.ndarray) -> str:
    """Write a 2-D array: matrix rows == text lines."""
    m2d = np.asarray(m2d, dtype=F32)
    if m2d.ndim == 1:
        m2d = m2d.reshape(1, -1)
    if m2d.size == 0:
        return "[matrix size: %dx%d]\n" % (m2d.shape[1], m2d.shape[0])
    kind, w = _arma_format(m2d)
    lines = []
    for row in m2d:
        parts = []
        for v in row:
            f = float(v)
            if f == 0.0:
                s = "0"
            elif math.isnan(f):
                s = "nan"
            elif math.isinf(f):
                s = "inf" if f > 0 else "-inf"
            elif kind == "e":
                s = "%.4e" % f
            else:
                s = "%.4f" % f
            parts.append(s.rjust(w))
        lines.append("".join(parts))
    return NEWLINE.join(lines) + NEWLINE


class VvmWriter:
    """Every write re-opens the file in append mode (ios::out|ios::app)."""

    def __init__(self, path: str, truncate: bool = True):
        self.path = path
        if truncate:
            open(path, "wb").close()

    def _w(self, s: str) -> None:
        with open(self.path, "ab") as f:
            f.write(s.encode("latin-1"))

    def raw(self, s: str) -> None:
        self._w(s)

    def scalar(self, name: str, v) -> None:
        self._w("%s = %s%s" % (name, fmt_g(v), NEWLINE))

    def vector(self, name: str, vec) -> None:
        self._w("%s = %s%s" % (name, "".join(" " + fmt_g(v) for v in vec), NEWLINE))

    def matrix(self, name: str, m2d) -> None:
        self._w("%s =%s%s" % (name, NEWLINE, arma_print(m2d)))

    def strings(self, name: str, lst: List[str], one_per_line: bool = False) -> None:
        s = name + " = "
        if not lst:
            s += NEWLINE + NEWLINE
        elif not one_per_line:
            s += "".join('"%s" ' % x for x in lst) + NEWLINE + NEWLINE
        else:
            s += "".join('"%s"%s' % (x, NEWLINE) for x in lst) + NEWLINE
        self._w(s)

    def title(self, name: str, s: str) -> None:
        self._w('%s = "%s"%s' % (name, s, NEWLINE))


def open_vvm(path: str) -> Optional[VvmFile]:
    try:
        return VvmFile(path)
    except OSError:
        return None


# --------------------------------------------------------------------------
# Shared numerical helpers
# --------------------------------------------------------------------------
def thickness_cube(top: np.ndarray) -> Optional[np.ndarray]:
    """Preserved (erosion-aware) thickness of every layer.

    thick[0] = 0
    running   = TOP[n-1]
    for k = n-1 .. 1:
        thick[k] = max(0, running - TOP[k-1])      (erosion-aware thickness)
        running  = min(running, TOP[k-1])
    """
    n = top.shape[0]
    if n < 2:
        err("ERROR: Cannot find thicknesses. Insufficient number of tops")
        return None
    th = np.zeros_like(top, dtype=F32)
    run = top[n - 1].copy()
    for k in range(n - 1, 0, -1):
        d = (run - top[k - 1]).astype(F32)
        d = np.where(d <= F32(0.0), F32(0.0), d).astype(F32)
        th[k] = d
        below = top[k - 1]
        run = np.where((below <= run) & (run != below), below, run).astype(F32)
    return th
