"""
fitdepth.py - fitdepth

Re-positions / stretches a SedArch model between present-day surfaces and
optionally adds a homogeneous overburden layer.
"""
from __future__ import annotations

import math
from typing import List, Optional

import numpy as np

from . import __version__
from .vvm import F32, VvmFile, VvmWriter, err, open_vvm, out

USAGE = [
    "fitdepth adjusts the thickness and vertical position of a\nSedArch output model to fit a given top, base, or isopach\n(any two of these three surfaces should be provided)",
    "Usage: python -m sedCompanion fitdepth sedarch_out.vvm parmfile1.vvm (parmfile2.vvm) result.vvm",
    "where:",
    "  sedarch_out.vvm is the SedArch result file",
    "  parmfile1.vvm is a parameter file containing one or both required surfaces",
    "  (parmfile2.vvm) is an optional parameter file containing the second required surface",
    "  result.vvm is the result file containing the corrected SedArch model",
    "Notes: The names of the provided surfaces in the parameter file must be:\nPRESENT_TOP, PRESENT_BASE, and PRESENT_ISOPACH",
    "Additionally, the parameter file may contain overburden\n information as one of 2 simple numbers: OVB_LEVEL or OVBD_THICK",
]


def _matrix(f: VvmFile, name: str) -> Optional[np.ndarray]:
    """First slice of the (appended) property."""
    c = VvmFile.to_cube(f.read_all_occurrences(name, warn=True))
    if c is None or c.size == 0:
        return None
    return c[0].copy()


def _mean_sd(a: np.ndarray):
    """Mean and sample standard deviation (float32 pairwise)."""
    v = a.reshape(-1).astype(F32)
    n = v.size
    s_even = F32(0.0)
    s_odd = F32(0.0)
    for i in range(0, n - 1, 2):
        s_even = F32(s_even + v[i])
        s_odd = F32(s_odd + v[i + 1])
    if n % 2 == 1:
        s_even = F32(s_even + v[n - 1])
    tot = float(F32(s_odd + s_even))
    if n < 0x21:
        q_even = F32(0.0)
        q_odd = F32(0.0)
        for i in range(0, n - 1, 2):
            q_even = F32(q_even + F32(v[i] * v[i]))
            q_odd = F32(q_odd + F32(v[i + 1] * v[i + 1]))
        if n % 2 == 1:
            q_even = F32(q_even + F32(v[n - 1] * v[n - 1]))
        ss = float(F32(q_odd + q_even))
    else:
        # OpenBLAS sdot_: single precision; summation order not reproducible here
        ss = float(F32(np.dot(v.astype(np.float64), v.astype(np.float64))))
    mean = F32(tot / n)
    var = (ss - tot * tot / n) / (n - 1) if n > 1 else float("nan")
    sd = F32(math.sqrt(var)) if var >= 0 else F32(float("nan"))
    return mean, sd


def main(argv: List[str]) -> int:
    out("Program: SedCompanion fitdepth %s (SedArch)" % __version__)
    argc = len(argv)
    if argc not in (4, 5):
        for l in USAGE:
            out(l)
        return 0
    fin = argv[1]
    fout = argv[argc - 1]
    fp1 = argv[2]
    fp2 = argv[3] if argc == 5 else ""

    inp = open_vvm(fin)
    if inp is None:
        err("ERROR: Input file not found: '%s'" % fin)
        return -1
    p1 = open_vvm(fp1)
    if p1 is None:
        err("ERROR: Parameter file 1: '%s' not found or unable to open" % fp1)
        return -1
    p2 = open_vvm(fp2) if fp2 else None
    if p2 is None:
        if not fp2:
            err("Parameter file 2 not given")
        else:
            err("ERROR: Parameter file 2: '%s' not found or unable to open" % fp2)
            return -1

    out("Reading TOP")
    inp.rewind()
    top = VvmFile.to_cube(inp.read_all_occurrences("TOP"))
    if top is None:
        err("ERROR: 'TOP' not found")
        return -1
    nz, ny, nx = top.shape
    out("Reading TECTONICS, if present")
    inp.rewind()
    tect = VvmFile.to_cube(inp.read_all_occurrences("TECTONICS"))
    if tect is None:
        out("  Not using TECTONICS")
    else:
        out("  Applying TECTONICS")
        if tect.shape != top.shape:
            err("error: addition: incompatible cube dimensions")
            return -1
        top = (top + tect).astype(F32)

    # base0 = min( TOP[0] , flat-element(k) of TOP for k = 1..nz-1 )
    #   (a single value: element k of the flattened array, not slice k)
    flat = top.reshape(-1)
    base0 = top[0].copy()
    for k in range(1, nz):
        base0 = np.minimum(base0, flat[k]).astype(F32)
    thick0 = (top[nz - 1] - base0).astype(F32)
    thick0 = np.where(F32(0.0) <= thick0, thick0, F32(0.0)).astype(F32)
    out("Reading surfaces")
    names = ("PRESENT_TOP", "PRESENT_BASE", "PRESENT_ISOPACH")
    surf = {}
    for nm in names:
        p1.rewind()
        surf[nm] = _matrix(p1, nm)
    if p2 is not None:
        for nm in names:
            if surf[nm] is None:
                p2.rewind()
                surf[nm] = _matrix(p2, nm)
        if surf["PRESENT_TOP"] is not None:
            out("Found PRESENT_TOP")
        if surf["PRESENT_BASE"] is not None:
            out("Found PRESENT_BASE")
        if surf["PRESENT_ISOPACH"] is not None:
            out("Found ISOPACH")
    ptop, pbase, piso = surf["PRESENT_TOP"], surf["PRESENT_BASE"], surf["PRESENT_ISOPACH"]

    new_base: Optional[np.ndarray] = None
    new_iso: Optional[np.ndarray] = None
    if ptop is None:
        if pbase is not None:
            new_base = pbase                        # iso left empty
        elif piso is not None:
            new_base = base0.copy()
            new_iso = piso
        else:
            err("ERROR: No PRESENT_TOP, PRESENT_BASE, or ISOPACH found")
            return -1
    else:
        if piso is None:
            if pbase is not None:
                # iso = PRESENT_TOP ; base = PRESENT_BASE - PRESENT_TOP (see user guide note)
                new_iso = ptop.copy()
                new_base = (pbase - new_iso).astype(F32)
            else:
                new_iso = thick0.copy()
                new_base = (ptop - new_iso).astype(F32)
        else:
            if pbase is not None:
                err("ERROR: Redundant information: All 3 of\n  PRESENT_TOP, PRESENT_BASE, and ISOPACH were given.\n  Only 2 of these must be given")
                return -1
            new_base = (ptop - piso).astype(F32)
            new_iso = piso

    p1.rewind()
    ovb_top = p1.scalar("OVBD_TOP")
    p1.rewind()
    ovb_thick = p1.scalar("OVBD_THICK")
    if ovb_top is not None and ovb_thick is not None:
        err("ERROR: Redundant information:\n  Both OVBD_TOP and OVBD_THICK were given.\n  At most 1 of these must be given")
        return -1

    w = VvmWriter(fout, truncate=True)
    inp.rewind()
    itop = 0
    maxsed = 0
    denom = F32(nz - 1)
    while True:
        rec = inp.next_record()
        if rec is None:
            break
        name = rec.name
        if rec.strings:
            w.strings(name, rec.strings, False)
            continue
        if not rec.cubes or rec.cubes[0].size == 0:
            continue
        if name == "TECTONICS":
            continue
        if name in ("SEALEVEL", "TIME"):
            w.scalar(name, F32(0.0))                 # written as 0
            continue
        if name == "TOP":
            if itop == 0:
                w.matrix("TOP", new_base)
            elif itop > 0:
                if new_iso is None or new_iso.shape != thick0.shape:
                    err("error: subtraction: incompatible matrix dimensions")
                    return -1
                frac = F32(F32(itop) / denom)
                #   TOP'_k = (TOP_k + newBase - base0) + (newIso - thick0) * k/(n-1)
                top[itop] = (((top[itop] + new_base) - base0)
                             + (new_iso - thick0) * frac).astype(F32)
                w.matrix("TOP", top[itop])
            itop += 1
            continue
        if name.startswith("SED") and len(name) > 3 and name[3].isdigit():
            digits = ""
            for ch in name[3:]:
                if ch.isdigit():
                    digits += ch
                else:
                    break
            maxsed = max(maxsed, int(digits))
        w.matrix(name, rec.cubes[0][0])

    if ovb_top is not None or ovb_thick is not None:
        lay = top[nz - 1].copy()
        if ovb_thick is None:
            lay = np.full((ny, nx), ovb_top, dtype=F32)
        else:
            lay = (lay + ovb_thick).astype(F32)
        w.matrix("TOP", lay)
        with np.errstate(divide="ignore"):
            frac = F32(F32(1.0) / F32(maxsed))
        lay = np.full((ny, nx), frac, dtype=F32)
        for s in range(1, maxsed + 1):
            w.matrix("SED%d" % s, lay)

    # error estimates
    if new_iso is not None:
        m_iso, _ = _mean_sd(new_iso)
        diff = (new_iso - thick0).astype(F32)
        m_d, s_d = _mean_sd(diff)
        out(" Mean thickness error = %g %%" % (float(m_d / m_iso) * 100.0))
        out("   (if positive: model exceeds target")
        out("    if negative: model does not reach target)")
        out(" Mean shape error = %g %%" % (float(s_d / m_iso) * 100.0))
        out("   (always positive: root mean square of thickness")
        out("    differences relative to target thickness)")
    return 0
