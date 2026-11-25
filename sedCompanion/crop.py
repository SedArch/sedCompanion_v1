"""
crop.py - crop
"""
from __future__ import annotations

from typing import List

import numpy as np

from . import __version__
from .vvm import F32, VvmFile, VvmWriter, err, open_vvm, out
from .avgmaps import _stoi

USAGE = [
    "crop extracts the final model from a SedArch result file",
    "Usage: python -m sedCompanion crop sedarch_out.vvm sedarch_out_ex.vvm xmin xmax ymin ymax",
    "where:",
    "  sedarch_out.vvm is the SedArch result file",
    "  sedarch_out_ex.vvm is the extracted result file",
    "  'xmin, xmax, ymin, ymax' are optional limits ",
    "  (in cell units starting at 0) of a rectangular area to extract",
    "  If no limits are given, the extracted model will be the same size as the input,",
    "  but the file will be reduced by showing only last state after tectonics",
    "Two additional parameters may be given: zmin, zmax",
    "  to extract only selected layers",
]


def main(argv: List[str]) -> int:
    out("Program: SedCompanion crop %s (SedArch)" % __version__)
    argc = len(argv)
    if argc not in (3, 7, 9):
        for l in USAGE:
            out(l)
        return 0
    fin, fout = argv[1], argv[2]
    xmin = ymin = zmin = 0
    xmax = ymax = zmax = 10000000
    try:
        if argc >= 7:
            xmin, xmax, ymin, ymax = (_stoi(a) for a in argv[3:7])
        if argc == 9:
            zmin, zmax = _stoi(argv[7]), _stoi(argv[8])
    except ValueError:
        err("Error: Invalid numerical argument or arguments out of order")
        return -1
    except OverflowError as e:
        err("Error: Out of range - " + str(e))
        return -1
    inp = open_vvm(fin)
    if inp is None:
        err("Input file not found: " + fin)
        return -1
    out("Reading TOP")
    inp.rewind()
    top = VvmFile.to_cube(inp.read_all_occurrences("TOP"))
    if top is None:
        out("ERROR: 'TOP' not found")
        return -1
    nz, ny, nx = top.shape
    x0, y0, z0 = max(0, xmin), max(0, ymin), max(0, zmin)
    x1, y1, z1 = min(xmax, nx - 1), min(ymax, ny - 1), min(zmax, nz - 1)
    out("Limits:")
    out("  X from %d to %d" % (x0, x1))
    out("  Y from %d to %d" % (y0, y1))
    out("  Z from %d to %d" % (z0, z1))
    if not (x0 <= x1 and y0 <= y1 and z0 <= z1):
        err("ERROR: Invalid limits")
        return -1
    if x1 - x0 < 1 or y1 - y0 < 1 or z1 - z0 < 1:
        err("ERROR: Need at least a range of 2 elements along each axis")
        return -1
    sub = top[z0:z1 + 1, y0:y1 + 1, x0:x1 + 1].copy()
    # TOP is written as stored, without the erosion clip.
    out("Reading TECTONICS")
    inp.rewind()
    tect = VvmFile.to_cube(inp.read_all_occurrences("TECTONICS"))
    if tect is None:
        out("'TECTONICS' not found, continuing")
    else:
        tsub = tect[z0:z1 + 1, y0:y1 + 1, x0:x1 + 1]
        if tsub.size == 0:
            out("ERROR: Unable to extract TECTONICS")
            return -1
        for s in range(z1 - z0 + 1):
            sub[s] = (sub[s] + tsub[tsub.shape[0] - 1]).astype(F32)

    w = VvmWriter(fout, truncate=True)
    inp.rewind()
    nt = ns = ntop = 0
    while True:
        rec = inp.next_record()
        if rec is None:
            break
        name = rec.name
        if rec.strings and name == "TITLE":
            w.title(name, rec.strings[0])
            continue
        if name == "TIME":
            nt += 1
        if name == "SEALEVEL":
            ns += 1
        if name == "TOP":
            ntop += 1
        if not (zmin <= nt and zmin <= ns and zmin <= ntop):
            continue
        if z1 < nt or z1 < ns or z1 < ntop:
            break
        if rec.strings:
            w.strings(name, rec.strings, False)
            continue
        if not rec.cubes:
            continue
        c0 = rec.cubes[0]
        if c0.size != 0:
            if name == "TECTONICS":
                continue
            if name in ("SEALEVEL", "TIME"):
                w.vector(name, c0[0, 0, :])
                continue
            if name == "TOP":
                if ntop - 1 >= sub.shape[0]:
                    err("Cube::slice(): index out of bounds")
                    return -1
                w.matrix("TOP", sub[ntop - 1])
                continue
        if c0.shape[2] == nx and c0.shape[1] == ny:
            w.matrix(name, c0[0, y0:y1 + 1, x0:x1 + 1])
        else:
            w.matrix(name, c0[0])
    out("Done")
    return 0
