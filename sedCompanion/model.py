"""
model.py - The SedArch "model" structure shared by rockprops and mcstats.

read_model / write_model read and write it; init_stats prepares a statistics model.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

from .vvm import F32, VvmFile, VvmWriter

# property slots in write order
POST_PROPS = ["END_THICK", "DEPO_LEVEL", "BURIAL", "POR", "PERMH", "PERMV"]
# keyword actually used by the *reader* for each slot (stats mode)
READ_KEY = {"END_THICK": None,            # never read
            "DEPO_LEVEL": "DEPO_LEVEL",
            "BURIAL": "BURIAL_X_TIME",    # read under this name (written as BURIAL)
            "POR": "POR", "PERMH": "PERMH", "PERMV": "PERMV"}


class Model:
    def __init__(self):
        self.n_real = 0
        self.sed_diam: Optional[np.ndarray] = None
        self.time: Optional[np.ndarray] = None
        self.sealevel: Optional[np.ndarray] = None
        self.top: Optional[np.ndarray] = None
        self.seds: List[Optional[np.ndarray]] = []
        self.tect: Optional[np.ndarray] = None
        self.post: Dict[str, Optional[np.ndarray]] = {k: None for k in POST_PROPS}
        # standard deviations (mcstats)
        self.sed_diam_sd: Optional[np.ndarray] = None
        self.time_sd: Optional[np.ndarray] = None
        self.sealevel_sd: Optional[np.ndarray] = None
        self.top_sd: Optional[np.ndarray] = None
        self.seds_sd: List[Optional[np.ndarray]] = []
        self.tect_sd: Optional[np.ndarray] = None
        self.post_sd: Dict[str, Optional[np.ndarray]] = {k: None for k in POST_PROPS}

    @property
    def nsteps(self) -> int:
        return 0 if self.top is None else self.top.shape[0]


def _cube(f: VvmFile, name: str) -> Optional[np.ndarray]:
    f.rewind()
    return VvmFile.to_cube(f.read_all_occurrences(name))


def _vec(f: VvmFile, name: str) -> Optional[np.ndarray]:
    f.rewind()
    return VvmFile.to_vector(f.read_all_occurrences(name))


def read_model(f: VvmFile, stats: bool) -> Model:
    m = Model()
    f.rewind()
    v = f.scalar("N_REALIZATIONS")
    if v is not None and v > 0:
        m.n_real = int(v)
    m.sed_diam = _vec(f, "SED_DIAMETERS")
    m.time = _vec(f, "TIME")
    m.sealevel = _vec(f, "SEALEVEL")
    m.top = _cube(f, "TOP")
    for n in range(1, 10):
        c = _cube(f, "SED%d" % n)
        if c is None:
            break
        m.seds.append(c)
    m.tect = _cube(f, "TECTONICS")
    if stats:
        for k in POST_PROPS:
            if READ_KEY[k]:
                m.post[k] = _cube(f, READ_KEY[k])
        m.sed_diam_sd = _vec(f, "SED_DIAMETERS_STDV")
        m.time_sd = _vec(f, "TIME_STDV")
        m.sealevel_sd = _vec(f, "SEALEVEL_STDV")
        m.top_sd = _cube(f, "TOP_STDV")
        for n in range(1, 10):
            c = _cube(f, "SED%d_STDV" % n)
            if c is None:
                break
            m.seds_sd.append(c)
        m.tect_sd = _cube(f, "TECTONICS_STDV")
        for k in POST_PROPS:
            if READ_KEY[k]:
                m.post_sd[k] = _cube(f, READ_KEY[k] + "_STDV")
    return m


def init_stats(m: Model) -> None:
    """Make m a statistics model: N=1 and every *_STDV set to zeros of the right size."""
    m.n_real = 1
    z = lambda a: None if a is None or a.size == 0 else np.zeros_like(a, dtype=F32)
    m.sed_diam_sd = z(m.sed_diam)
    m.time_sd = z(m.time)
    m.sealevel_sd = z(m.sealevel)
    m.top_sd = z(m.top)
    m.seds_sd = [z(c) for c in m.seds]
    m.tect_sd = z(m.tect)
    for k in POST_PROPS:
        m.post_sd[k] = z(m.post[k])


def _nonempty(a) -> bool:
    return a is not None and a.size > 0


def write_model(m: Model, w: VvmWriter, post_only: bool) -> None:
    """Write a model; with post_only, only the rockprops properties of each step."""
    if m.n_real > 0:
        w.scalar("N_REALIZATIONS", F32(m.n_real))
    if _nonempty(m.sed_diam_sd):
        w.vector("SED_DIAMETERS_STDV", m.sed_diam_sd)
    for k in range(m.nsteps):
        if not post_only:
            if _nonempty(m.time):
                w.scalar("TIME", m.time[k])
            if _nonempty(m.sealevel):
                w.scalar("SEALEVEL", m.sealevel[k])
            if _nonempty(m.top):
                w.matrix("TOP", m.top[k])
            for i, c in enumerate(m.seds):
                if _nonempty(c):
                    w.matrix("SED%d" % (i + 1), c[k])
            if _nonempty(m.tect):
                w.matrix("TECTONICS", m.tect[k])
        for name in POST_PROPS:
            c = m.post[name]
            if _nonempty(c):
                w.matrix(name, c[k])
        if not post_only:
            if _nonempty(m.time_sd):
                w.scalar("TIME_STDV", m.time_sd[k])
            if _nonempty(m.sealevel_sd):
                w.scalar("SEALEVEL_STDV", m.sealevel_sd[k])
            if _nonempty(m.top_sd):
                w.matrix("TOP_STDV", m.top_sd[k])
            for i, c in enumerate(m.seds_sd):
                if _nonempty(c):
                    w.matrix("SED%d_STDV" % (i + 1), c[k])
            if _nonempty(m.tect_sd):
                w.matrix("TECTONICS_STDV", m.tect_sd[k])
            for name in POST_PROPS:
                c = m.post_sd[name]
                if _nonempty(c):
                    w.matrix(name + "_STDV", c[k])
