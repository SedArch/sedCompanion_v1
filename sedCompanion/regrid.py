"""
regrid.py - regrid
"""
from __future__ import annotations

import math
from typing import List

import numpy as np

from . import __version__
from .vvm import F32, VvmFile, VvmWriter, arma_print, err, fmt_g, open_vvm, out
from . import vvm as _vvm

USAGE = [
    "Regrids (rasterizes) one property of a vvm file",
    "Usage: python -m sedCompanion regrid filein fileparam fileout",
    "filein is a vvm file (usually the output of SedArch)",
    "  containing a 3D property called 'TOP' and one or more",
    "  properties to be regridded, of the same dimensions as 'TOP'",
    "fileparam is an optional input file containing parameters",
    "fileout is an output file (that will be overwritten)",
    "Example parameter file : ",
    ' PROPERTY = "SED2"  ! Name of property to regrid',
    " MULTIPLICITY = 1   ! Multiplicity (integer) old cell side / new cell side",
    " HORIZONTALIZE = 0  ! Whether to horizontalize base (0: NO, 1: YES)",
    " CELLTHICK = 10     ! Cell thickness (m)",
    " EMPTYVALUE = -1    ! Empty value",
    " HEADERS = 2        ! Headers: 0: None (plain grid), 1:vvm (SedArchView), 2:GsLib (SGeMS)",
]


def bilinear(m: np.ndarray, x: F32, y: F32) -> F32:
    """Bilinear interpolation (x along a text line, y across lines)."""
    ny, nx = m.shape
    i = int(math.floor(float(x)))
    j = int(math.floor(float(y)))
    u = F32(x - F32(i))
    v = F32(y - F32(j))
    if i < 0:
        u, i = F32(0.0), 0
    elif nx - 2 < i:
        u, i = F32(1.0), nx - 2
    if j < 0:
        v, j = F32(0.0), 0
    elif ny - 2 < j:
        v, j = F32(1.0), ny - 2
    q0 = m[j, i]
    q1 = m[j, i + 1]
    q2 = m[j + 1, i + 1]
    q3 = m[j + 1, i]
    one = F32(1.0)
    a = F32(F32(F32(one - u) * q0) + F32(q1 * u))
    b = F32(F32(F32(one - u) * q3) + F32(q2 * u))
    return F32(F32(a * F32(one - v)) + F32(b * v))


def main(argv: List[str]) -> int:
    out("Program: SedCompanion regrid %s (SedArch)" % __version__)
    if len(argv) != 4:
        for l in USAGE:
            out(l)
        out()
        return 0
    fin, fpar, fout = argv[1], argv[2], argv[3]
    inp = open_vvm(fin)
    if inp is None:
        err("ERROR: Input file not found: '%s'" % fin)
        return -1
    par = open_vvm(fpar)
    if par is None:
        err("ERROR: Parameter file not found: '%s'" % fpar)
        return -1

    inp.rewind()
    top = VvmFile.to_cube(inp.read_all_occurrences("TOP"))
    if top is None:
        err("ERROR: Unable to read 'TOP'")
        return -1
    if top.size == 0:
        err("ERROR: 'TOP' does not appear to have 3 regular dimensions ")
        return -1
    nz, ny, nx = top.shape
    out("'TOP' dimensions = %d * %d * %d" % (nx, ny, nz))
    if nx < 2 or ny < 2:
        err("ERROR: 'TOP' needs at least 2 elements in each horizontal dimension")
        return -1
    out("Tops have been read successfully.")
    inp.rewind()
    tect = VvmFile.to_cube(inp.read_all_occurrences("TECTONICS"))
    if tect is None:
        err("No TECTONICS present, continuing")
    else:
        last = tect[tect.shape[0] - 1]
        if last.shape != top.shape[1:]:
            err("error: addition: incompatible matrix dimensions")
            return -1
        top = (top + last[None, :, :]).astype(F32)

    par.rewind()
    if not par.find("PROPERTY"):
        err("ERROR: Unable to find PROP (name of property to regrid) in parameter file")
        return -1
    rec = par.read_value("PROPERTY")
    if not rec.strings:
        err("ERROR: Unable to read PROPERTY (name of property to regrid) in parameter file")
        return -1
    pname = rec.strings[0]
    inp.rewind()
    prop = VvmFile.to_cube(inp.read_all_occurrences(pname))
    if prop is None:
        err("ERROR: '%s' not found " % pname)
        return -1
    if prop.size == 0:
        err("Error: '%s' does not appear to have 3 regular dimensions " % pname)
        return -1
    out("'%s' dimensions = %d * %d * %d" % (pname, prop.shape[2], prop.shape[1], prop.shape[0]))
    if prop.size != top.size:
        err("Error: '%s has different dimensions than 'TOP'" % pname)
        return -1

    def pscalar(name):
        par.rewind()
        return par.scalar(name)

    mult = pscalar("MULTIPLICITY")
    if mult is None:
        err("ERROR: Unable to read MULTIPLICITY in parameter file")
        return -1
    m = int(mult)
    nxn = (nx - 1) * m + 1
    nyn = (ny - 1) * m + 1
    out("New number of nodes in x and y direction: %d * %d" % (nxn, nyn))
    zmin, zmax = F32(np.min(top)), F32(np.max(top))
    if F32(zmax - zmin) <= 0:
        err("Warning: There is no vertical thickness")
    out("Minimum TOP = %g" % zmin)
    out("Maximum TOP = %g" % zmax)
    hz = pscalar("HORIZONTALIZE")
    if hz is None:
        err("ERROR: Unable to read HORIZONTALIZE in parameter file")
        return -1
    if hz == 0.0:
        err("Basement will not be horizontalized")
    else:
        err("Basement will be horizontalized")
        base = top[0].copy()
        for k in range(1, nz):
            top[k] = (top[k] - base).astype(F32)
        top[0] = 0.0
        zmin, zmax = F32(np.min(top)), F32(np.max(top))
        if F32(zmax - zmin) <= 0:
            err("Warning: There is no vertical thickness")
        out()
        out("Horizontalized minimum TOP = %g" % zmin)
        out("Horizontalized maximum TOP = %g" % zmax)
    th = pscalar("CELLTHICK")
    if th is None:
        err("ERROR: Unable to read CELLTHICK in parameter file")
        return -1
    err("Cell thickness = %g" % th)
    if th <= 0:
        err("ERROR: Cell thickness must be > 0")
        return -1
    rng = F32(zmax - zmin)
    if rng <= 0:
        rng = F32(1.0)
    q = F32(rng / th)
    nl = int(F32(math.floor(float(q) + 0.5)))
    if nl < 1:
        nl = 1
    out()
    out("Number of output layers: %d" % nl)
    empty = pscalar("EMPTYVALUE")
    if empty is None:
        err("WARNING: Unable to read EMPTYVALUE in parameter file; will use default")
        empty = F32(-999.0)
    err("Empty value = %g" % empty)
    hd = pscalar("HEADERS")
    if hd is None:
        err("ERROR: Unable to read HEADERS in parameter file")
        return -1
    hd = int(hd)
    sys_txt = {0: " None (plain grid)", 1: " vvm (SedArchView)", 2: " GsLib (SGems)"}
    if hd not in sys_txt:
        err("Headers = %d" % hd)
        err("ERROR: Invalid HEADERS value; must be 0, 1 or 2")
        return -1
    err("Headers = %d%s" % (hd, sys_txt[hd]))

    cube = np.zeros((nl, nyn, nxn), dtype=F32)
    mf = F32(m)
    for iy in range(nyn):
        y = F32(F32(iy) / mf)
        for ix in range(nxn):
            x = F32(F32(ix) / mf)
            k = nz
            for iz in range(nl - 1, -1, -1):
                zc = F32(F32(F32(iz) + F32(0.5)) * th)
                while k > 0:
                    if bilinear(top[k - 1], x, y) < F32(zc + zmin):
                        break
                    k -= 1
                cube[iz, iy, ix] = bilinear(prop[k], x, y) if k < nz else empty

    nl_ = _vvm.NEWLINE
    w = VvmWriter(fout, truncate=True)
    if hd in (0, 1):
        s = "" if hd == 0 else pname + " =" + nl_
        for iz in range(nl):
            s += arma_print(cube[iz]) + nl_
        w.raw(s)
    else:
        parts = ['"TITLE"' + nl_, '"1"' + nl_, '"%s"' % pname + nl_]
        parts.extend(fmt_g(v) + nl_ for v in cube.reshape(-1))
        w.raw("".join(parts))
    out("DONE")
    return 0
