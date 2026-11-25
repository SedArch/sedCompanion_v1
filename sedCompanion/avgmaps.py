"""
avgmaps.py - avgmaps

THICKNESS = sum of erosion-corrected layer thickness over layers m..n
<P>_AVG   = sum(P_k * thick_k) / THICKNESS      (0 where THICKNESS <= 0.001)
(All properties are averaged arithmetically, permeability included.)
"""
from __future__ import annotations

from typing import List

import numpy as np

from . import __version__
from .vvm import F32, VvmFile, VvmWriter, err, open_vvm, out, thickness_cube

USAGE = [
    "Average layers of a SedArch result file",
    "Usage: python -m sedCompanion avgmaps sedarch_out.vvm layer.vvm m n",
    "  sedarch_out.vvm is a SedArch output file",
    "  layer.vvm is the output file (need not exist)",
    "  m and n are optional numbers of the bottom and top",
    "  layers of the package to average (m <= n)",
    "  The basement is 0 and is not included in the average",
    "  If m and n are not provided, all layers are included",
]


def _stoi(s: str) -> int:
    s2 = s.strip()
    i = 0
    if i < len(s2) and s2[i] in "+-":
        i += 1
    j = i
    while j < len(s2) and s2[j].isdigit():
        j += 1
    if j == i:
        raise ValueError("invalid stoi argument")
    v = int(s2[:j])
    if not -2**31 <= v < 2**31:
        raise OverflowError("stoi argument out of range")
    return v


def main(argv: List[str]) -> int:
    out("Program: SedCompanion avgmaps %s (SedArch)" % __version__)
    argc = len(argv)
    if argc not in (3, 5):
        for l in USAGE:
            out(l)
        return 0
    fin, fout = argv[1], argv[2]
    m, n = 1, 1000000
    if argc == 5:
        try:
            m = _stoi(argv[3])
            n = _stoi(argv[4])
        except ValueError as e:
            err("Invalid argument: " + str(e))
            return -1
        except OverflowError as e:
            err("Out of range error: " + str(e))
            return -1
    if m < 1 or n < 1 or n < m:
        err("ERROR: top layer must be greater than or equal\nto bottom layer and both must be > 0")
        return -1
    inp = open_vvm(fin)
    if inp is None:
        err("Input file not found: " + fin)
        return -1
    try:
        w = VvmWriter(fout, truncate=True)
    except OSError:
        err("Unable to open output file " + fout)
        return -1
    kw = inp.keyword_counts()
    inp.rewind()
    top = VvmFile.to_cube(inp.read_all_occurrences("TOP"))
    if top is None:
        err("ERROR: 'TOP' property not found in file")
        return -1
    names = [k for k, _ in kw]
    if "TOP" not in names:
        err("ERROR: 'TOP' property not found in keywords")
        return -1
    ntop = dict(kw)["TOP"]
    nz = top.shape[0]
    last = nz - 1
    top_layer = min(n, last)
    if last < m:
        err("ERROR: Cannot process from layer %d" % m)
        err("       because there are only %d layers (not counting basement)" % last)
        return -1
    out("Processing from layer %d to layer %d" % (m, top_layer))
    out("Finding THICKNESS")
    thick = thickness_cube(top)
    if thick is None:
        return -1
    lo, hi = max(m, 0), min(top_layer, last)
    tsum = np.zeros(top.shape[1:], dtype=F32)
    for k in range(lo, hi + 1):
        tsum = (tsum + thick[k]).astype(F32)
    w.matrix("THICKNESS", tsum)
    for name, cnt in kw:
        if name in ("TOP", "TECTONICS"):
            continue
        if cnt < 2 or cnt != ntop:
            continue
        inp.rewind()
        prop = VvmFile.to_cube(inp.read_all_occurrences(name))
        if prop is None or prop.shape != top.shape:
            continue
        out("Processing '%s'" % name)
        acc = np.zeros(top.shape[1:], dtype=F32)
        for k in range(lo, min(hi, prop.shape[0] - 1) + 1):
            acc = (prop[k] * thick[k] + acc).astype(F32)
        with np.errstate(divide="ignore", invalid="ignore"):
            avg = np.where(F32(0.001) < tsum, (acc / tsum).astype(F32), F32(0.0)).astype(F32)
        w.matrix(name + "_AVG", avg)
    out("Done")
    return 0
