"""
mcstats.py - mcstats

Running (pooled) mean / standard deviation of every property over many
SedArch realisations.
"""
from __future__ import annotations

import math
import os
from typing import List, Optional

import numpy as np

from . import __version__
from .vvm import F32, VvmWriter, err, open_vvm, out
from .model import POST_PROPS, Model, init_stats, read_model, write_model

USAGE = [
    "Generate mean and standard deviation for all properties",
    "  of multiple SedArch output models",
    "Usage: python -m sedCompanion mcstats stats_out.vvm sedarch_out*.vvm",
    "  mcstats_out.vvm is the output file containing statistics",
    "  sedarch_out*.vvm is one or more SedArch result files",
    "If the output file already exist, the SedArch result file(s) will be merged into it",
]

GEO_CLAMP = 1e-10        # double at 0x140019888


def _merge_arith(n1, m1, s1, n2, m2, s2):
    """Pooled mean / sample s.d. (mixed float/double arithmetic)."""
    m1 = m1.astype(F32); s1 = s1.astype(F32); m2 = m2.astype(F32); s2 = s2.astype(F32)
    S1 = (F32(n1) * m1).astype(np.float64)
    A = (s1 * s1 * F32(n1 - 1)).astype(np.float64) + S1 * S1 / float(n1)
    S2 = (F32(n2) * m2).astype(np.float64)
    T = S2 + S1
    N = float(n1 + n2)
    mean = (T / N).astype(F32)
    B = (s2 * s2 * F32(n2 - 1)).astype(np.float64)
    var = (((B + S2 * S2 / float(n2)) + A) - T * T / N) / float(n1 + n2 - 1)
    with np.errstate(invalid="ignore"):
        sd = np.where(var > 0.0, np.sqrt(np.where(var > 0, var, 0)), 0.0).astype(F32)
    return mean, sd


def _fmin(a: float, x: np.ndarray) -> np.ndarray:
    x = x.astype(np.float64)
    return np.where(np.isnan(x), a, np.minimum(a, x))


def _merge_geo(n1, m1, s1, n2, m2, s2):
    """Geometric merge (PERMH, PERMV).  NOTE: values are limited with fmin(1e-10, v),
    so every positive input collapses to 1e-10 (see user guide)."""
    with np.errstate(divide="ignore", invalid="ignore"):
        a = np.log(_fmin(GEO_CLAMP, m1.astype(F32)))
        b = np.log(_fmin(GEO_CLAMP, s1.astype(F32)))
        c = np.log(_fmin(GEO_CLAMP, m2.astype(F32)))
        d = np.log(_fmin(GEO_CLAMP, s2.astype(F32)))
        A1 = a * float(n1)
        X10 = b * b * float(n1 - 1) + A1 * A1 / float(n1)
        A2 = c * float(n2)
        T = A2 + A1
        N = float(n1 + n2)
        mean = np.exp(T / N).astype(F32)
        var = ((d * d * float(n2 - 1) + A2 * A2 / float(n2)) + X10 - T * T / N) / float(n1 + n2 - 1)
        sdl = np.where(var > 0.0, np.sqrt(np.where(var > 0, var, 0)).astype(F32), F32(0.0))
        sd = np.exp(sdl.astype(np.float64)).astype(F32)
    return mean, sd


def _merge(n1, a, asd, n2, b, bsd, geo=False):
    if a is None or a.size == 0:
        return True, a, asd
    if any(x is None or x.size != a.size for x in (asd, b, bsd)):
        return False, a, asd
    f = _merge_geo if geo else _merge_arith
    m, s = f(n1, a, asd, n2, b, bsd)
    return True, m.reshape(a.shape), s.reshape(a.shape)


def merge_models(st: Model, md: Model) -> bool:
    """Merge the runs in md into the statistics model st."""
    n1 = max(st.n_real, 1)
    n2 = max(md.n_real, 1)
    ok, st.sed_diam, st.sed_diam_sd = _merge(n1, st.sed_diam, st.sed_diam_sd, n2, md.sed_diam, md.sed_diam_sd)
    if not ok: return False
    ok, st.time, st.time_sd = _merge(n1, st.time, st.time_sd, n2, md.time, md.time_sd)
    if not ok: return False
    ok, st.sealevel, st.sealevel_sd = _merge(n1, st.sealevel, st.sealevel_sd, n2, md.sealevel, md.sealevel_sd)
    if not ok: return False
    ok, st.top, st.top_sd = _merge(n1, st.top, st.top_sd, n2, md.top, md.top_sd)
    if not ok: return False
    for i in range(len(st.seds)):
        if st.seds[i] is None or st.seds[i].size == 0:
            continue
        if i >= len(md.seds) or i >= len(st.seds_sd) or i >= len(md.seds_sd):
            return False
        ok, st.seds[i], st.seds_sd[i] = _merge(n1, st.seds[i], st.seds_sd[i], n2, md.seds[i], md.seds_sd[i])
        if not ok: return False
    ok, st.tect, st.tect_sd = _merge(n1, st.tect, st.tect_sd, n2, md.tect, md.tect_sd)
    if not ok: return False
    for k in POST_PROPS:
        geo = k in ("PERMH", "PERMV")
        ok, st.post[k], st.post_sd[k] = _merge(n1, st.post[k], st.post_sd[k], n2, md.post[k], md.post_sd[k], geo)
        if not ok: return False
    st.n_real += md.n_real
    return True


def main(argv: List[str]) -> int:
    out("Program: SedCompanion mcstats %s (SedArch)" % __version__)
    if len(argv) < 3:
        for l in USAGE:
            out(l)
        return 0
    fstats = argv[1]
    for fin in argv[2:]:
        if not fin or not fin[0].isalnum():
            err("ERROR: Invalid input file name: " + fin)
            return -1
        if fin == fstats:
            err("ERROR: Input file name: " + fin)
            err("       cannot be the same as output file name: " + fstats)
            return -1
        out("Input file = " + fin)
        exists = os.path.isfile(fstats)
        inp = open_vvm(fin)
        if inp is None:
            err("ERROR: Input file not found: '%s'" % fin)
            return -1
        md = read_model(inp, stats=True)
        if md.n_real == 0:
            init_stats(md)
        if not exists:
            write_model(md, VvmWriter(fstats, truncate=False), post_only=False)
        else:
            sf = open_vvm(fstats)
            if sf is None:
                err("Unable to open stats file")
                err("ERROR: Unable to read stats file " + fstats)
                return -1
            st = read_model(sf, stats=True)
            if st.n_real == 0:
                err("WARNING: file %s does not contain a valid entry for N_REALIZATIONS" % fstats)
                err("         Assuming 1 realization")
                init_stats(st)
            out("Previous number of realizations = %d" % st.n_real)
            out("Added number of realizations = %d" % md.n_real)
            if not merge_models(st, md):
                err("ERROR: Unable to merge files, possible dimensional inconsistency")
                return -1
            write_model(st, VvmWriter(fstats, truncate=True), post_only=False)
    out("Done")
    return 0
