"""
verify.py - regression test: run every tool on the example inputs and compare the
results with the reference outputs in output/.

    python -m sedCompanion.verify [project_dir] [work_dir]
"""
from __future__ import annotations

import io
import os
import re
import sys
import contextlib
import tempfile

import numpy as np

from . import gpmexport, regrid, rockprops, mcstats, fitdepth, avgmaps, wells, crop

NUM = re.compile(r"^[+-]?(\d+\.?\d*([eE][+-]?\d+)?|\.\d+([eE][+-]?\d+)?|nan|inf|-inf)$")


def compare_text(a_path: str, b_path: str):
    a = open(a_path, "rb").read()
    b = open(b_path, "rb").read()
    if a == b:
        return "IDENTICAL (byte-for-byte)", 0.0
    la = a.decode("latin-1").splitlines()
    lb = b.decode("latin-1").splitlines()
    if len(la) != len(lb):
        return "DIFFERENT line count %d vs %d" % (len(la), len(lb)), None
    maxd = 0.0
    ndiff_lines = 0
    first = None
    for i, (x, y) in enumerate(zip(la, lb)):
        if x == y:
            continue
        ndiff_lines += 1
        tx, ty = x.split(), y.split()
        if len(tx) != len(ty):
            first = first or (i + 1, x[:80], y[:80])
            maxd = float("inf")
            continue
        for p, q in zip(tx, ty):
            if p == q:
                continue
            if NUM.match(p) and NUM.match(q):
                d = abs(float(p) - float(q))
                maxd = max(maxd, d)
                if d > 0 and first is None:
                    first = (i + 1, x[:80], y[:80])
            else:
                maxd = float("inf")
                first = first or (i + 1, x[:80], y[:80])
    return ("%d differing lines, max |diff| = %g, first at %s" % (ndiff_lines, maxd, first)), maxd


def compare_h5(a_path: str, b_path: str):
    import h5py
    fa, fb = h5py.File(a_path, "r"), h5py.File(b_path, "r")
    ka, kb = set(fa.keys()), set(fb.keys())
    msgs = []
    if ka != kb:
        msgs.append("dataset names differ: only-new=%s only-ref=%s" % (sorted(ka - kb)[:5], sorted(kb - ka)[:5]))
    worst = 0.0
    for k in sorted(ka & kb):
        x, y = fa[k][...], fb[k][...]
        if x.shape != y.shape:
            msgs.append("%s shape %s vs %s" % (k, x.shape, y.shape))
            continue
        if x.dtype.kind == "O" or y.dtype.kind == "O":
            def norm(v, f):
                out = []
                for e in v.ravel():
                    if isinstance(e, h5py.Reference):
                        out.append(f[e].name if e else None)
                    elif isinstance(e, bytes):
                        out.append(e.decode())
                    else:
                        out.append(e)
                return out
            if norm(x, fa) != norm(y, fb):
                msgs.append("%s object content differs" % k)
            continue
        d = np.nanmax(np.abs(x.astype(np.float64) - y.astype(np.float64))) if x.size else 0.0
        if not np.array_equal(np.isnan(x), np.isnan(y)):
            msgs.append("%s NaN pattern differs" % k)
        worst = max(worst, float(d) if np.isfinite(d) else 0.0)
    for k, v in fb.attrs.items():
        va = fa.attrs.get(k)
        sa = [e.decode() if isinstance(e, bytes) else e for e in np.atleast_1d(va)] if va is not None else None
        sb = [e.decode() if isinstance(e, bytes) else e for e in np.atleast_1d(v)]
        if sa is None or [str(e) for e in sa] != [str(e) for e in sb]:
            msgs.append("root attr %s: %s vs %s" % (k, sa, sb))
    msgs.append("max |numeric diff| over %d common datasets = %g" % (len(ka & kb), worst))
    return "; ".join(msgs), worst


def run(fn, args):
    buf_o, buf_e = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(buf_o), contextlib.redirect_stderr(buf_e):
        rc = fn(args)
    return rc, buf_o.getvalue(), buf_e.getvalue()


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    proj = os.path.abspath(argv[0] if argv else os.path.join(os.path.dirname(__file__), ".."))
    work = os.path.abspath(argv[1]) if len(argv) > 1 else tempfile.mkdtemp(prefix="sedcompanion_verify_")
    os.makedirs(work, exist_ok=True)
    I = lambda f: os.path.join(proj, "input", f)
    O = lambda f: os.path.join(proj, "output", f)
    W = lambda f: os.path.join(work, f)
    jobs = [
        ("regrid", regrid.main, ["regrid", I("dispersion_out.vvm"), I("regrid_parm.vvmp"), W("regrid.vvm")], W("regrid.vvm"), O("regrid.vvm")),
        ("rockprops", rockprops.main, ["rockprops", I("dispersion_out.vvm"), I("rockprops_parm.vvmp"), W("rockprops.vvm")], W("rockprops.vvm"), O("rockprops.vvm")),
        ("fitdepth", fitdepth.main, ["fitdepth", I("dispersion_out.vvm"), I("fitdepth_parm.vvm"), W("fitdepth.vvm")], W("fitdepth.vvm"), O("fitdepth.vvm")),
        ("avgmaps", avgmaps.main, ["avgmaps", I("dispersion_out.vvm"), W("avgmaps.vvm"), "2", "8"], W("avgmaps.vvm"), O("avgmaps.vvm")),
        ("wells", wells.main, ["wells", I("dispersion_out.vvm"), I("wells_parm.vvmp"), W("wells.xyz")], W("wells.xyz"), O("wells.xyz")),
        ("crop", crop.main, ["crop", I("dispersion_out.vvm"), W("crop.vvm"), "10", "30", "10", "30"], W("crop.vvm"), O("crop.vvm")),
    ]
    results = []
    for name, fn, args, got, ref in jobs:
        rc, so, se = run(fn, args)
        msg, _ = compare_text(got, ref) if os.path.exists(got) else ("NO OUTPUT (rc=%s) %s" % (rc, se[-300:]), None)
        results.append((name, rc, msg))
    # mcstats: reference output holds N_REALIZATIONS = 2 -> two runs of the mcstats command
    st = W("mcstats.vvm")
    if os.path.exists(st):
        os.remove(st)
    # mcstats rejects input names whose first character is not alphanumeric
    # (an absolute POSIX path starts with '/'), so pass a relative path.
    rel = os.path.relpath(I("dispersion_out.vvm"))
    run(mcstats.main, ["mcstats", st, rel])
    rc, so, se = run(mcstats.main, ["mcstats", st, rel])
    results.append(("mcstats (x2)", rc, compare_text(st, O("mcstats.vvm"))[0]))
    try:
        rc, so, se = run(gpmexport.main, ["gpmexport", I("dispersion_out.vvm"), W("gpmexport.hdf5")])
        results.append(("gpmexport", rc, compare_h5(W("gpmexport.hdf5"), O("gpmexport.hdf5"))[0]))
    except Exception as e:                       # pragma: no cover
        results.append(("gpmexport", -1, "ERROR %r" % e))
    print("work dir:", work)
    for name, rc, msg in results:
        print("%-14s rc=%-3s %s" % (name, rc, msg))


if __name__ == "__main__":
    main()
