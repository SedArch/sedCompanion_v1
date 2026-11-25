"""
rockprops.py - rockprops

Adds END_THICK, DEPO_LEVEL, BURIAL, POR, PERMH, PERMV to a SedArch result.
All arithmetic is single precision (float32).
"""
from __future__ import annotations

import math
import shutil
from typing import List, Optional, Tuple

import numpy as np

from . import __version__
from .vvm import F32, VvmWriter, err, open_vvm, out, thickness_cube
from .model import read_model, write_model

USAGE = [
    "Post processes a SedArch result file to calculate:",
    "layer thicknesses, depth of deposition, overburden, porosity,",
    "horizontal permeablity, vertical permeability",
    "Porosities and permeabilities are approximate estimates.",
    "Usage: python -m sedCompanion rockprops sedarch_out.vvm params.vvmp sedarch_post.vvm",
    "  sedarch_out.vvm is the output of SedArch",
    "  params.vvmp is a file containing parameters (see below)",
    "  sedarch_post.vvm is the output file",
    "The params.vvmp file must contain, for each sediment type:",
    "  porosity and permeability at the surface and at",
    "  1000 m depth, and horizontal to vertical permeability ratio",
    "These values must be for pure components (lab or literature): ",
    "The program will calculate the values for mixtures,",
    "  using an advanced algorithm that applies sorting and compaction",
    "  (NOT simple interpolations)",
    "Example parameter file : ",
    " POR1_0 = 0.40    ! SED1 porosity (fraction) at deposition",
    " POR1_1000 = 0.15 ! SED1 porosity (fraction) at 1000 m",
    " PERM1_0 = 1000   ! SED1 horiz. permeability (mD) at deposition",
    " PERM1_1000 = 100 ! SED1 horiz. permeability (mD) at 1000 m",
    " PERMRATIO1 = 100 ! SED1 permeability ratio (hor/vert) after burial",
    "",
    " POR2_0 = 0.18    ! SED2 porosity (fraction) at deposition",
    " POR2_1000 = 0.05 ! SED2 porosity (fraction) at 1000 m",
    " PERM2_0 = 200    ! SED2 horiz. permeability (mD) at deposition",
    " PERM2_1000 = 32  ! SED2 horiz. permeability (mD) at 1000 m",
    " PERMRATIO2 = 100 ! SED2 permeability ratio (hor/vert) after burial",
    "",
    " ! ...etc., for other sediment types",
]


# ---------------------------------------------------------------- helpers
def dot(a: List[F32], b: List[F32]) -> F32:
    """Float dot product, 4-way unrolled summation order."""
    if len(a) != len(b):
        err("Error: Vectors must have the same size.")
        return F32(0.0)
    n = len(a)
    s = F32(0.0)
    i = 0
    if n >= 4:
        while i + 4 <= n:
            s = F32(F32(F32(F32(F32(a[i] * b[i]) + s) + F32(a[i + 1] * b[i + 1]))
                        + F32(a[i + 2] * b[i + 2])) + F32(a[i + 3] * b[i + 3]))
            i += 4
    while i < n:
        s = F32(s + F32(a[i] * b[i]))
        i += 1
    return s


def harmonic(vals: List[F32], frac: List[F32]) -> F32:
    """1 / sum(f_i / v_i) over f_i > 0 ; 0 if any such v_i <= 0."""
    if len(vals) != len(frac):
        err("Error: Vectors must have the same size.")
        return F32(0.0)
    s = F32(0.0)
    for v, f in zip(vals, frac):
        if F32(0.0) < f:
            if v <= F32(0.0):
                return F32(0.0)
            s = F32(s + F32(f / v))
    with np.errstate(divide="ignore"):
        return F32(F32(1.0) / s)


def sort_order(diam: List[F32]) -> List[int]:
    """Order in which fractions are added: selection by descending diameter.

    NOTE: the maximum is searched over the WHOLE vector at every step (not over
    the unsorted tail); see the rockprops porosity note in the user guide.
    """
    idx = list(range(len(diam)))
    work = list(diam)
    for i in range(len(work) - 1):
        m = 0
        best = -math.inf
        for j, v in enumerate(work):          # first maximum
            if v > best:
                best, m = v, j
        work[i], work[m] = work[m], work[i]
        idx[i], idx[m] = idx[m], idx[i]
    return idx


def mix_porosity(por: List[F32], frac: List[F32], diam: List[F32], k: F32 = F32(0.5)) -> F32:
    """Porosity of a sediment mixture (sorting model)."""
    idx = sort_order(diam)
    i0 = idx[0]
    p = por[i0]
    V = F32(F32(p * frac[i0]) / F32(F32(1.0) - p))
    for i in range(1, len(por)):
        m, prev = idx[i], idx[i - 1]
        fm = frac[m]
        if F32(0.0) < fm:
            avail = F32(F32(V - F32(F32(V * diam[m]) / diam[prev])) * k)
            pm = por[m]
            vn = F32(F32(pm * fm) / F32(F32(1.0) - pm))
            tot = F32(vn + fm)
            if tot <= avail:
                V = F32(V - fm)
            else:
                r = F32(F32(tot - avail) / tot)
                V = F32(F32(V - F32(F32(F32(1.0) - r) * fm)) + F32(r * vn))
    return F32(V / F32(V + F32(1.0)))


def _logf(v) -> F32:
    """Natural logarithm in single precision."""
    with np.errstate(all="ignore"):
        return F32(np.log(F32(v)))


def perm_regression(p0: F32, p1: F32, k0: F32, k1: F32, d: F32) -> Tuple[F32, F32]:
    """K = C * phi^x through (p0,k0),(p1,k1); C divided by d^2."""
    if k0 <= 0 or k1 <= 0 or p0 <= 0 or p1 <= 0 or d <= 0 or p0 == p1:
        return F32(0.0), F32(0.0)
    lk0 = _logf(k0)
    lp0 = _logf(p0)
    ld = _logf(d)
    lp1 = _logf(p1)
    x = F32(0.0)
    if F32(lp0 - lp1) != 0.0:
        lk1 = _logf(k1)
        x = F32(F32(lk0 - lk1) / F32(lp0 - lp1))
        lk0 = F32(lk0 - F32(x * lp0))
    C = F32(math.exp(F32(lk0 - F32(ld + ld))))
    return C, x


def _powf(a: F32, b: F32) -> F32:
    """a**b evaluated in double precision and rounded once to float."""
    try:
        return F32(math.pow(float(a), float(b)))
    except (OverflowError, ValueError):
        with np.errstate(all="ignore"):
            return F32(np.power(np.float64(a), np.float64(b)))


def _expf(a: F32) -> F32:
    try:
        return F32(math.exp(float(a)))
    except OverflowError:
        return F32(math.inf)


# ---------------------------------------------------------------- main
def main(argv: List[str]) -> int:
    out("Program: SedCompanion rockprops %s (SedArch)" % __version__)
    if len(argv) != 4:
        for l in USAGE:
            out(l)
        return 0
    fin, fpar, fout = argv[1], argv[2], argv[3]
    inp = open_vvm(fin)
    if inp is None:
        err("ERROR: Input file not found: '%s'" % fin)
        return -1
    out("Opening '%s'" % fpar)
    par = open_vvm(fpar)
    if par is None:
        if fpar:
            err("ERROR: Parameter file 1: '%s' not found or unable to open" % fpar)
            return -1
        err("Parameter file not given")

    model = read_model(inp, stats=False)

    # ---- parameters (param-file cursor is never rewound) ----
    por0, por1, k0, k1, ratio = [], [], [], [], []
    nsed = 0
    for n in range(1, 11):
        if n == 10:
            out("WARNING: Cannot use more than 9 sediment types")
            break
        if par is None:
            break
        inp.rewind()
        vals = []
        for key in ("POR%d_0" % n, "POR%d_1000" % n, "PERM%d_0" % n,
                    "PERM%d_1000" % n, "PERMRATIO%d" % n):
            v = par.scalar(key)
            if v is None:
                break
            vals.append(v)
        lists = (por0, por1, k0, k1, ratio)
        for lst, v in zip(lists, vals):
            lst.append(v)
        if len(vals) < 5:
            break
        nsed += 1
    por0, por1, k0, k1, ratio = (l[:nsed] for l in (por0, por1, k0, k1, ratio))
    kv0 = [F32(a / b) for a, b in zip(k0, ratio)]          # PERM0 / PERMRATIO

    out("     " + "    PORn_0 " + " PORn_1000 " + " PERMn_0" + " PERMn_1000" + " PERMRATIOn")
    for i in range(nsed):
        out("SED%d: %10.4f %10.4f %10.4f %10.4f %10.4f" %
            (i + 1, por0[i], por1[i], k0[i], k1[i], ratio[i]))
        if por0[i] <= por1[i]:
            err("ERROR: in parameter file sediment %d" % (i + 1))
            err("       POR0 must be greater than POR1000")
        if k0[i] <= k1[i]:
            err("ERROR: in parameter file sediment %d" % (i + 1))
            err("       PERM0 must be greater than PERM1000")
    # decay length so that phi(1000 m)/phi(0) = POR1000/POR0
    with np.errstate(divide="ignore", invalid="ignore"):
        L = [F32(F32(16382.701) / F32(F32(math.log(a)) - F32(math.log(b))))
             for a, b in zip(por0, por1)]

    ns_model = len(model.seds)
    if nsed != ns_model:
        err("ERROR: Number of sediments in parameter file (%d)" % nsed)
        err("       does not agree with number of sediments in input file (%d)" % ns_model)

    out("Processing: This may take many minutes...")
    try:
        shutil.copyfile(fin, fout)
    except OSError:
        err("Failed to open destination file: " + fout)
        return -1

    top = model.top
    if top is None:
        err("ERROR: Cannot find thicknesses. Insufficient number of tops")
        return -1
    nz, ny, nx = top.shape
    thick = thickness_cube(top)
    if thick is None:
        return -1
    depo = np.zeros_like(top)
    burial = np.zeros_like(top)
    por = np.zeros_like(top)
    permh = np.zeros_like(top)
    permv = np.zeros_like(top)
    diam = list(model.sed_diam) if model.sed_diam is not None else []
    have_tect = model.tect is not None and model.tect.size > 0
    sl = model.sealevel

    for k in range(nz):
        for y in range(ny):
            for x in range(nx):
                d = F32(sl[k] - top[k, y, x])
                if have_tect:
                    d = F32(d - model.tect[k, y, x])
                depo[k, y, x] = d
                b = F32(0.0) if k == 0 else F32(thick[k, y, x] * F32(0.5))
                for m in range(k + 1, nz):
                    b = F32(b + thick[m, y, x])
                burial[k, y, x] = b
                f = [model.seds[s][k, y, x] for s in range(ns_model)]
                mixp = mix_porosity(por0, f, diam, F32(0.5))
                Lm = dot(L, f)
                phi = F32(_expf(F32(F32(F32(b * F32(-1.67)) * F32(9.81)) / Lm)) * mixp)
                por[k, y, x] = phi
                p0 = dot(por0, f)
                p1 = dot(por1, f)
                kk0 = dot(k0, f)
                kk1 = dot(k1, f)
                dd = dot(diam, f)
                C, xx = perm_regression(p0, p1, kk0, kk1, dd)
                permh[k, y, x] = F32(_powf(phi, xx) * C)
                kh = harmonic(k0, f)
                kv = harmonic(kv0, f)
                C2, x2 = perm_regression(p0, p1, kh, kv, dd)
                permv[k, y, x] = F32(_powf(phi, x2) * C2)

    model.post["END_THICK"] = thick
    model.post["DEPO_LEVEL"] = depo
    model.post["BURIAL"] = burial
    model.post["POR"] = por
    model.post["PERMH"] = permh
    model.post["PERMV"] = permv
    w = VvmWriter(fout, truncate=False)        # appended to the copied input
    write_model(model, w, post_only=True)
    out("Done")
    return 0
