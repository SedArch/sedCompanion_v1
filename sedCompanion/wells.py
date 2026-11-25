"""
wells.py - wells

Wells are snapped to the NEAREST grid node (roundf), without interpolation.
"""
from __future__ import annotations

import math
from typing import List

import numpy as np

from . import __version__
from .vvm import F32, VvmFile, VvmWriter, NEWLINE, err, open_vvm, out
from . import vvm as _vvm

USAGE = [
    "wells extracts virtual wells from a SedArch result file",
    "For results corrected to present day, the file should have\n been processed by fitdepth.\n Grid parameters should have been provided in the input file",
    "Usage: python -m sedCompanion wells sedarch_out.vvm wells.vvm result.xyz",
    "where:",
    "  sedarch_out.vvm is the SedArch result file (after processing by fitdepth)",
    "  wells.vvm is a vvm file containing xy well locations as follows:",
    "    XYWELLS = two columns containing X and Y world coordinates of wells",
    "              or, if a single well, two numbers (X and Y)",
    "  result.xyz is the output file containing X Y Z coordinates and values in columns",
    "  Results for all wells will be in a single file",
    "  For results in separate files, perform separate runs",
    "  with a single well in each run",
]


def _roundf(v: F32) -> float:
    v = float(v)
    return math.floor(v + 0.5) if v >= 0 else -math.floor(-v + 0.5)


def main(argv: List[str]) -> int:
    out("Program: SedCompanion wells %s (SedArch)" % __version__)
    if len(argv) != 4:
        for l in USAGE:
            out(l)
        return 0
    fin, fpar, fout = argv[1], argv[2], argv[3]
    inp = open_vvm(fin)
    if inp is None:
        err("ERROR: Input file not found: '%s'" % fin)
        return -1
    par = open_vvm(fpar)
    if par is None:
        if fpar:
            err("ERROR: Parameter file 1: '%s' not found or unable to open" % fpar)
            return -1
        err("Parameter file not given")

    # grid parameters come from the INPUT model file
    def sc(name, default):
        inp.rewind()
        v = inp.scalar(name)
        return default if v is None else v
    cs = sc("CELLSIDE", F32(1.0))
    x0 = sc("XORIGIN", F32(0.0))
    y0 = sc("YORIGIN", F32(0.0))
    rot = sc("ROTATION", F32(0.0))
    xy = None
    if par is not None:
        par.rewind()
        c = VvmFile.to_cube(par.read_all_occurrences("XYWELLS"))
        if c is not None:
            xy = c[0]                        # (nwells, 2)
    if xy is None or xy.shape[1] != 2:
        err("ERROR: XYWELLS does not have two columns")
        return -1
    nw = xy.shape[0]
    if not cs > 0:
        err("ERROR: cellside must be > 0")
        return -1
    out("Grid parameters:")
    out("  CELLSIDE = %g" % cs)
    out("  XORIGIN = %g" % x0)
    out("  YORIGIN = %g" % y0)
    out("  ROTATION = %g" % rot)
    out("Reading TOP")
    inp.rewind()
    top = VvmFile.to_cube(inp.read_all_occurrences("TOP"))
    if top is None:
        err("ERROR: 'TOP' not found")
        return -1
    nz, ny, nx = top.shape
    if nx < 2 or ny < 2 or nz < 2:
        err("ERROR: TOP has insufficient dimensions")
        return -1
    # TOP is used as stored, without the erosion clip.
    out("Reading TECTONICS, if present")
    inp.rewind()
    tect = VvmFile.to_cube(inp.read_all_occurrences("TECTONICS"))
    if tect is None:
        out("  Not using TECTONICS")
    elif tect.shape == top.shape:
        out("  Applying TECTONICS")
        top = (top + tect).astype(F32)
    else:
        err("ERROR: TECTONICS dimensions do not match TOP")
        return -1

    # world -> grid
    a = F32(F32(rot * F32(3.1415925)) / F32(180.0))
    sa, ca = F32(math.sin(a)), F32(math.cos(a))
    idx = []
    for i in range(nw):
        u = F32(F32(xy[i, 0] - x0) / cs)
        v = F32(F32(xy[i, 1] - y0) / cs)
        gx = F32(F32(u * ca) - F32(v * sa))
        gy = F32(F32(v * ca) + F32(u * sa))
        idx.append([float(F32(int(_roundf(gx)))), float(F32(int(_roundf(gy))))])
    for i in range(nw - 1, -1, -1):
        ix, iy = idx[i]
        if ix < 0 or ix > nx - 1 or iy < 0 or iy > ny - 1:
            err("WARNING: Well %d is out of bounds: removing" % (i + 1))
            del idx[i]
    if not idx:
        err("ERROR: No wells to process")
        return -1

    names: List[str] = []
    rows: List[List[List[float]]] = [[] for _ in idx]
    ntop = 0
    col = 0
    gdims = (0, 0, 0)
    inp.rewind()
    while True:
        rec = inp.next_record()
        if rec is None:
            break
        if rec.strings or not rec.cubes or rec.cubes[0].size == 0:
            continue
        if rec.name == "TECTONICS":
            continue
        if rec.name == "TOP":
            for r in rows:
                r.append([0.0] * len(names))
            ntop += 1
            col = 0
            continue
        c0 = rec.cubes[0]
        gdims = (c0.shape[2], c0.shape[1], c0.shape[0])
        if c0.shape[2] == nx and c0.shape[1] == ny:
            if ntop == 1:
                names.append(rec.name)
                for r in rows:
                    for row in r:
                        row.append(0.0)
            for w_i, (ix, iy) in enumerate(idx):
                rows[w_i][-1][col] = float(c0[0, int(iy), int(ix)])
            col += 1

    out_ = VvmWriter(fout, truncate=True)
    hdr = ["# Type: scattered data", "# Version: 6", "# Description: No description",
           "# Format: free", "# Field: 1 x", "# Field: 2 y", "# Field: 3 z meters"]
    hdr += ["# Field: %d %s" % (i + 4, n) for i, n in enumerate(names)]
    hdr += ["# Projection: Local Rectangular", "# Units: meters", "# End:",
            "# Information from grid:",
            "# Grid_size: %d x %d x %d" % gdims,
            "# Grid_space: 0, 1, 1, 0, 0, 1",
            "# Scattered data : Not_available", "# Z_field : z",
            "# Vertical_faults : Not_available", "# History : No history",
            "# Z_units : unspecified"]
    out_.raw("".join(h + _vvm.NEWLINE for h in hdr))
    body = []
    for w_i, (ix, iy) in enumerate(idx):
        X, Y = float(xy[w_i, 0]), float(xy[w_i, 1])     # XYWELLS order (see user guide note)
        for r_i, row in enumerate(rows[w_i]):
            z = float(top[r_i, int(iy), int(ix)])
            s = " " + ("%.1f" % X).rjust(9) + " ".rjust(9) + "%.1f" % Y
            s += " " + ("%.3f" % z).rjust(9)
            s += "".join(" " + ("%.3f" % v).rjust(9) for v in row)
            body.append(s + _vvm.NEWLINE)
        body.append(_vvm.NEWLINE)
    out_.raw("".join(body))
    out("Done")
    return 0
