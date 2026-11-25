"""
gpmexport.py - gpmexport

Converts a SedArch .vvm result to a Petrel-GPM 2.0.0.0 style HDF5 file.
Requires h5py.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

import numpy as np

from . import __version__
from .vvm import F32, VvmFile, err, open_vvm, out

USAGE = [
    "Converts a vvm file to an hdf5 file",
    "Usage: python -m sedCompanion gpmexport filein fileout",
    "filein is a vvm file (usually the output of SedArch)",
    "  containing a 3D property called 'TOP' and optionally",
    "  other properties of the same dimensions as 'TOP'",
    "fileout is an hdf5 output file (that will be overwritten)",
]

PROPS = ["TOP", "SED1", "SED2", "SED3", "SED4", "ERODABILITY1", "ERODABILITY2",
         "ERODABILITY3", "ERODABILITY4", "SEALEVEL", "EROSION", "DEPODEPTH",
         "TOP_SLOPE_X", "TOP_SLOPE_Y", "TOP_SLOPE_MAG"]
DISPLAY = ["TOP", "Sand (coarse)", "Sand (fine)", "Silt", "Clay", "ERODABILITY1",
           "ERODABILITY2", "ERODABILITY3", "ERODABILITY4", "Sea level", "Erosion",
           "Depth of deposition", "TOP_SLOPE_X", "TOP_SLOPE_Y", "TOP_SLOPE_MAG"]
TEMPLATE = ["elevation depth", "fraction", "fraction", "fraction", "fraction",
            "fraction", "fraction", "fraction", "fraction", "elevation depth",
            "distance", "elevation depth", "fraction", "fraction", "fraction"]
GUIDS = ["://SedimentDataSource/59716ef2-b3bc-43d8-816a-6d8c12f3c6e1",
         "://SedimentDataSource/7c7e432f-ca79-4abd-b600-f4e009bd289b",
         "://SedimentDataSource/e9816ce4-58f4-4f3f-a0d0-6128a3ce3fd0",
         "://SedimentDataSource/96ec6892-d2ec-4637-a8c2-c39b82a8a606"]
ZNULL = F32(-1e12)


def _half_diff(z: np.ndarray, axis: int) -> np.ndarray:
    """(z[i+1]-z[i-1])*0.5 along axis,
    neighbour indices clamped to the grid (still multiplied by 0.5)."""
    n = z.shape[axis]
    lo = np.clip(np.arange(n) - 1, 0, n - 1)
    hi = np.clip(np.arange(n) + 1, 0, n - 1)
    a = np.take(z, hi, axis=axis)
    b = np.take(z, lo, axis=axis)
    return ((a - b).astype(F32) * F32(0.5)).astype(F32)


def main(argv: List[str]) -> int:
    out("Program: SedCompanion gpmexport %s (SedArch)" % __version__)
    if len(argv) != 3:
        for l in USAGE:
            out(l)
        return 0
    try:
        import h5py
    except ImportError:
        err("SedCompanion gpmexport needs the h5py package")
        return -1
    fin, fout = argv[1], argv[2]
    out("Opening '%s'" % fin)
    out("This may take a minute...")
    inp = open_vvm(fin)
    if inp is None:
        out("Unable to read: '%s'" % fin)
        return -1
    out("Done reading '%s'" % fin)
    out("Processing: This may take many minutes...")

    def cube(name):
        inp.rewind()
        return VvmFile.to_cube(inp.read_all_occurrences(name, warn=False))

    def vec(name):
        inp.rewind()
        return VvmFile.to_vector(inp.read_all_occurrences(name, warn=False))

    top = cube("TOP")
    if top is None:
        out("WARNING: Unable to find a property called 'TOP'")
        return -1
    time = vec("TIME")
    if time is None:
        out("ERROR: TIME property not found")
        return -1
    sl = vec("SEALEVEL")
    if sl is None:
        out("ERROR: SEALEVEL property not found")
        return -1
    inp.rewind()
    cs_ = inp.scalar("CELLSIDE")
    if cs_ is None:
        out("ERROR: CELLSIDE property not found")
        return -1
    cs = F32(cs_)
    diam = vec("SED_DIAMETERS")
    if diam is None:
        out("ERROR: SED_DIAMETERS property not found")
        return -1
    d4 = np.full(4, F32(0.001), dtype=F32)
    d4[:min(4, diam.size)] = diam[:4]
    d4 = (d4 * F32(0.001)).astype(F32)

    nT, nrows, ncols = top.shape          # time steps, lines (Y), values/line (X)
    data: Dict[str, Optional[np.ndarray]] = {p: (None if p in ("TOP", "SEALEVEL") else cube(p))
                                             for p in PROPS}
    data["TOP"] = top

    f = h5py.File(fout, "w")
    vstr = h5py.string_dtype("ascii")
    f.attrs.create("BASE_ERODABILITY", np.array([1.0], dtype=F32))
    f.attrs.create("COORD_SYS_REFERENCE", np.array([" "], dtype=object), dtype=vstr)
    f.attrs.create("NODORDER", np.array([0], dtype=np.int32))
    f.attrs.create("NUMROWS", np.array([nrows], dtype=np.int32))
    f.attrs.create("NUMCOLS", np.array([ncols], dtype=np.int32))
    f.attrs.create("VERSION", np.array(["2.0.0.0"], dtype=object), dtype=vstr)
    f.attrs.create("ZNULL", np.array([ZNULL], dtype=F32))

    grid_refs = []
    prop_refs = []
    stat_refs = []
    counter = [0]

    def new_grid(name: str, arr: np.ndarray):
        ds = f.create_dataset(name, data=np.asarray(arr, dtype=F32))
        grid_refs.append(ds.ref)
        counter[0] += 1
        return ds

    top_final: List[np.ndarray] = []       # local_bf0 : TOP_t as deposited
    erosion: List[Optional[np.ndarray]] = []
    slope_x: List[np.ndarray] = []
    slope_y: List[np.ndarray] = []

    for pi, pname in enumerate(PROPS):
        low = pname.lower()
        ref = np.empty((nT, nT), dtype=h5py.ref_dtype)
        const = np.full((nT, nT), np.nan, dtype=F32)
        stats = np.zeros((nT, 2), dtype=F32)
        refname = "REF_%d_%s" % (pi, pname)
        for t in range(nT):
            vals = []
            if pname == "TOP":
                prev = []                               # grids top_t.0 .. top_t.(j-1)
                for j in range(t + 1):
                    g = top[j].copy()
                    if j == t:
                        if t == 0:
                            erosion.append(None)
                        else:
                            e = (g - prev[-1][1]).astype(F32)
                            erosion.append(np.where(F32(0.0) < e, F32(0.0), e).astype(F32))
                        top_final.append(g.copy())
                    vals.append(g)
                    for k, (nm, pg) in enumerate(prev):
                        prev[k] = (nm, np.where(g < pg, g, pg).astype(F32))
                    nm = "GREF_%d_top_%d.%d" % (counter[0], t, j)
                    if t == 0 and j == 0:
                        nm = "GREF_0_TOP_base0"
                    prev.append((nm, g))
                    counter[0] += 1
                counter[0] -= len(prev)
                for j, (nm, g) in enumerate(prev):
                    ds = new_grid(nm, g)
                    ref[t, j] = ds.ref
            elif pname == "SEALEVEL":
                const[t, 0] = sl[t]
                vals.append(np.array([sl[t]], dtype=F32))
            elif pname in ("EROSION", "DEPODEPTH", "TOP_SLOPE_X", "TOP_SLOPE_Y", "TOP_SLOPE_MAG"):
                src = data.get(pname)
                if src is not None:
                    g = src[t]
                elif pname == "EROSION":
                    g = erosion[t] if t > 0 else None
                elif pname == "DEPODEPTH":
                    g = ((F32(0.0) + top_final[t]) + (-sl[t])).astype(F32)
                elif pname == "TOP_SLOPE_X":
                    g = (_half_diff(top_final[t], 1) * F32(F32(-1.0) / cs)).astype(F32)
                    slope_x.append(g)
                elif pname == "TOP_SLOPE_Y":
                    g = (_half_diff(top_final[t], 0) * F32(F32(-1.0) / cs)).astype(F32)
                    slope_y.append(g)
                else:
                    if t < len(slope_x) and t < len(slope_y):
                        sx, sy = slope_x[t], slope_y[t]
                        g = np.sqrt((sy * sy + sx * sx).astype(F32)).astype(F32)
                    else:
                        g = np.zeros((nrows, ncols), dtype=F32)
                if g is not None:
                    suffix = "%d" % t
                    ds = new_grid("GREF_%d_%s_%s" % (counter[0], low, suffix), g)
                    ref[t, 0] = ds.ref
                    vals.append(g)
            else:                                        # SEDn, ERODABILITYn
                src = data.get(pname)
                if src is not None:
                    g = src[t]
                else:
                    g = np.full((nrows, ncols), F32(1.0) if pname.startswith("ERODABILITY")
                                else F32(0.0), dtype=F32)
                ds = new_grid("GREF_%d_%s_%d.%d" % (counter[0], low, t, t), g)
                for r in range(t, nT):
                    ref[r, t] = ds.ref
                vals.append(g)
            if vals:
                allv = np.concatenate([v.reshape(-1) for v in vals])
                allv = allv[np.isfinite(allv)]
                stats[t] = (allv.min(), allv.max()) if allv.size else (0.0, 0.0)
            else:
                stats[t] = (ZNULL, ZNULL)
        cds = f.create_dataset(refname + "_CONST", data=const)
        rds = f.create_dataset(refname, data=ref, dtype=h5py.ref_dtype)
        rds.attrs.create("CONSTANTS_REF", np.array([cds.ref], dtype=h5py.ref_dtype))
        rds.attrs.create("NAME", np.array([pname], dtype=object), dtype=vstr)
        prop_refs.append(rds.ref)
        sds = f.create_dataset("STATREF_%d_%s" % (pi, pname), data=stats)
        stat_refs.append(sds.ref)

    f.create_dataset("HISTORY", data=np.array(["History"], dtype=object), dtype=vstr)
    f.create_dataset("ISNODAL", data=np.zeros(len(PROPS), dtype=np.int32))
    f.create_dataset("SED_DIAMETER", data=d4)
    f.create_dataset("SED_PROP_MAP", data=np.array([GUIDS, DISPLAY[1:5], PROPS[1:5]], dtype=object), dtype=vstr)
    f.create_dataset("PROP_DISPLAY_NAME", data=np.array([PROPS, DISPLAY], dtype=object), dtype=vstr)
    f.create_dataset("PROP_TEMPLATE_ID", data=np.array([PROPS, TEMPLATE], dtype=object), dtype=vstr)
    f.create_dataset("GRID_REFERENCES", data=np.array(grid_refs, dtype=h5py.ref_dtype))
    f.create_dataset("PROPERTIES_REFERENCES", data=np.array(prop_refs, dtype=h5py.ref_dtype))
    f.create_dataset("STATISTICS_REFERENCES", data=np.array(stat_refs, dtype=h5py.ref_dtype))
    f.create_dataset("AGESET", data=np.array([float(v) * 1000.0 for v in time[:nT]], dtype=np.float64))
    f.create_dataset("TIMESET", data=np.array([float(F32(v * F32(1000.0))) for v in time[:nT]], dtype=np.float64))
    W = F32(F32(ncols - 1) * cs)
    H = F32(F32(nrows - 1) * cs)
    f.create_dataset("XCORNERS", data=np.array([0.0, W, W, 0.0], dtype=F32))
    f.create_dataset("YCORNERS", data=np.array([0.0, 0.0, H, H], dtype=F32))
    out("Writing '%s'" % fout)
    f.close()
    out("Done")
    return 0
