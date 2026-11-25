"""
make_figures.py - draws every figure of the SedCompanion user guide.

Usage:  python3 make_figures.py [output_dir]
Default output: ./figures next to this script.

The data figures are drawn from the example model in ../input and the example
results in ../output, read with SedCompanion's own vvm reader. Needs NumPy and
matplotlib.
"""
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.collections import PolyCollection
from matplotlib.colors import LinearSegmentedColormap, LogNorm, Normalize
from matplotlib.patches import FancyBboxPatch, Polygon, Rectangle

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(PKG))
from sedCompanion.vvm import VvmFile  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "figures")
os.makedirs(OUT, exist_ok=True)

# ---------------------------------------------------------------- style
def _register_fonts():
    """Register Avenir Next Regular/Medium/Demi Bold; fall back silently to the defaults."""
    ttc = "/System/Library/Fonts/Avenir Next.ttc"
    if not os.path.exists(ttc):
        return
    import tempfile
    from fontTools.ttLib import TTCollection
    tmp = os.path.join(tempfile.gettempdir(), "sedcompanion_fonts")
    os.makedirs(tmp, exist_ok=True)
    for idx, name in ((7, "regular"), (5, "medium"), (2, "demibold"), (4, "italic")):
        path = os.path.join(tmp, "avenir_next_%s.ttf" % name)
        if not os.path.exists(path):
            TTCollection(ttc).fonts[idx].save(path)
        fm.fontManager.addfont(path)


try:
    _register_fonts()
except Exception:
    pass
plt.rcParams.update({
    "font.family": ["Avenir Next", "Helvetica Neue", "Arial", "DejaVu Sans"],
    "font.size": 9, "axes.titlesize": 10, "axes.titleweight": "demibold",
    "axes.labelsize": 9, "xtick.labelsize": 8, "ytick.labelsize": 8,
    "axes.edgecolor": "#5b6770", "axes.linewidth": 0.6,
    "xtick.color": "#5b6770", "ytick.color": "#5b6770",
    "axes.labelcolor": "#2b3238", "text.color": "#2b3238",
    "axes.spines.top": False, "axes.spines.right": False,
    "savefig.dpi": 220, "savefig.bbox": "tight", "savefig.pad_inches": 0.04,
})

INK = "#2b3238"
MUTED = "#7b8790"
ACCENT = "#1f5f73"
ACCENT_LIGHT = "#e3eef1"
SED_COL = ["#d9a441", "#ecd58b", "#8fb39a", "#5e7896"]          # SED1..SED4
SED_NAME = ["Coarse sand (SED1)", "Fine sand (SED2)", "Silt (SED3)", "Clay (SED4)"]
SAND = LinearSegmentedColormap.from_list("sand", ["#4f6a88", "#8fb39a", "#ecd58b", "#d9a441", "#b5761e"])
BASEMENT = "#c9c4bb"
OVERBURDEN = "#dcdcdc"


def save(fig, name):
    fig.savefig(os.path.join(OUT, name))
    plt.close(fig)
    print("  ", name)


# ---------------------------------------------------------------- data
def cube(path, key):
    f = VvmFile(path)
    return VvmFile.to_cube(f.read_all_occurrences(key, warn=False))


def scalar(path, key):
    return float(VvmFile(path).scalar(key))


MODEL = os.path.join(PKG, "input", "dispersion_out.vvm")
POST = os.path.join(PKG, "output", "rockprops.vvm")
FITDEPTH = os.path.join(PKG, "output", "fitdepth.vvm")
VAVG = os.path.join(PKG, "output", "avgmaps.vvm")
XTRACT = os.path.join(PKG, "output", "crop.vvm")
REGULAR = os.path.join(PKG, "output", "regrid.vvm")
WELLS_OUT = os.path.join(PKG, "output", "wells.xyz")
POST_PARM = os.path.join(PKG, "input", "rockprops_parm.vvmp")

TOP = cube(MODEL, "TOP")                      # (n, ny, nx)
SEDS = [cube(MODEL, "SED%d" % i) for i in range(1, 5)]
SEALEVEL = cube(MODEL, "SEALEVEL").ravel()
CELL = scalar(MODEL, "CELLSIDE")
X0, Y0, ROT = scalar(MODEL, "XORIGIN"), scalar(MODEL, "YORIGIN"), scalar(MODEL, "ROTATION")
N, NY, NX = TOP.shape
ROW = NY // 2                                 # the section shown in the figures
XS = np.arange(NX) * CELL


def eroded(tops):
    """Surfaces as preserved today: each top clipped by every younger one."""
    s = tops.copy()
    for k in range(len(s) - 2, -1, -1):
        s[k] = np.minimum(s[k], s[k + 1])
    return s


def sand(seds):
    return seds[0] + seds[1]


def draw_section(ax, tops, values, cmap, norm, x=XS, basement=True, special=None, basement_values=False):
    """Draw layers k = 1..n-1 between the preserved surfaces, coloured by values[k]."""
    s = eroded(tops)
    polys, cols = [], []
    for k in range(1, len(s)):
        for i in range(len(x) - 1):
            a0, a1, b0, b1 = s[k - 1, i], s[k - 1, i + 1], s[k, i], s[k, i + 1]
            if max(b0 - a0, b1 - a1) <= 1e-6:
                continue
            polys.append([(x[i], a0), (x[i + 1], a1), (x[i + 1], b1), (x[i], b0)])
            if special is not None and k in special:
                cols.append(special[k])
            else:
                cols.append(cmap(norm(0.5 * (values[k, i] + values[k, i + 1]))))
    ax.add_collection(PolyCollection(polys, facecolors=cols, edgecolors=cols, linewidths=0.3, antialiased=True))
    for k in range(len(s)):
        ax.plot(x, s[k], color="white" if k else INK, lw=0.45 if k else 0.8, alpha=0.9 if k else 1)
    if basement:
        lo = s.min() - 0.08 * (s.max() - s.min())
        if basement_values:
            for i in range(len(x) - 1):
                c = cmap(norm(0.5 * (values[0, i] + values[0, i + 1])))
                ax.fill([x[i], x[i + 1], x[i + 1], x[i]], [lo, lo, s[0, i + 1], s[0, i]], color=c, lw=0.3)
        else:
            ax.fill_between(x, lo, s[0], color=BASEMENT, lw=0)
        ax.set_ylim(lo, s.max() + 0.06 * (s.max() - s.min()))
    ax.set_xlim(x[0], x[-1])
    return s


def colorbar(fig, ax, cmap, norm, label, ticks=None, fmt=None):
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    cb = fig.colorbar(sm, ax=ax, fraction=0.035, pad=0.015, ticks=ticks, format=fmt)
    cb.outline.set_linewidth(0.4)
    cb.ax.tick_params(labelsize=7.5, width=0.4, length=2)
    cb.set_label(label, fontsize=8)
    return cb


def box(ax, x, y, w, h, text, fc="white", ec=ACCENT, tc=INK, fs=9, weight="demibold", lw=1.0, r=0.06, sub=None):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=%g" % r,
                                fc=fc, ec=ec, lw=lw, zorder=2))
    if sub:
        ax.text(x + w / 2, y + h * 0.60, text, ha="center", va="center", fontsize=fs, weight=weight, color=tc, zorder=3)
        ax.text(x + w / 2, y + h * 0.28, sub, ha="center", va="center", fontsize=fs - 1.8, color=MUTED, zorder=3)
    else:
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, weight=weight, color=tc, zorder=3)


def file_box(ax, x, y, w, h, text, fc="#fbf6e6", ec="#c9a54a", fs=8.5):
    d = min(w, h) * 0.22
    ax.add_patch(Polygon([(x, y), (x + w, y), (x + w, y + h - d), (x + w - d, y + h), (x, y + h)],
                         closed=True, fc=fc, ec=ec, lw=0.9, zorder=2))
    ax.add_patch(Polygon([(x + w - d, y + h), (x + w - d, y + h - d), (x + w, y + h - d)],
                         closed=True, fc=ec, ec=ec, lw=0.6, alpha=0.5, zorder=3))
    ax.text(x + w / 2, y + h / 2 - d * 0.15, text, ha="center", va="center", fontsize=fs,
            family="monospace", color=INK, zorder=3)


def arrow(ax, x0, y0, x1, y1, color=MUTED, lw=1.1, rad=0.0):
    ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                arrowprops=dict(arrowstyle="-|>,head_length=0.45,head_width=0.22", color=color, lw=lw,
                                shrinkA=0, shrinkB=0, connectionstyle="arc3,rad=%g" % rad), zorder=1)


def canvas(w, h, xlim, ylim):
    fig = plt.figure(figsize=(w, h))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.axis("off")
    return fig, ax


# ======================================================================
XLIM = (2000, 6000)          # the part of the example section that holds sediment


def section_axes(ax, ylabel=True, xlabel=True):
    ax.set_xlim(*XLIM)
    if ylabel:
        ax.set_ylabel("elevation (m)")
    if xlabel:
        ax.set_xlabel("distance along i (m)")


def fig_cover():
    fig = plt.figure(figsize=(7.2, 2.4))
    ax = fig.add_axes([0, 0, 1, 1])
    draw_section(ax, TOP[:, ROW, :], sand(SEDS)[:, ROW, :], SAND, Normalize(0, 1))
    ax.set_xlim(2300, 6000)
    ax.axis("off")
    save(fig, "cover.png")


def fig_workflow():
    fig, ax = canvas(7.0, 4.4, (0, 14), (0, 8.8))
    lab = dict(fontsize=7.5, color=MUTED, weight="demibold")
    ax.text(0.2, 8.45, "SIMULATION", **lab)
    file_box(ax, 0.2, 6.9, 2.2, 1.0, "model.vvmp")
    box(ax, 3.0, 6.8, 2.4, 1.2, "SedArch", fc=ACCENT, ec=ACCENT, tc="white", fs=11)
    file_box(ax, 6.0, 6.9, 2.3, 1.0, "result.vvm")
    arrow(ax, 2.4, 7.4, 3.0, 7.4)
    arrow(ax, 5.4, 7.4, 6.0, 7.4)

    ax.text(0.2, 3.7, "DEPTH AND ROCK PROPERTIES (optional)", **lab)
    box(ax, 0.6, 4.05, 2.9, 1.1, "fitdepth", sub="fit to present-day surfaces")
    box(ax, 4.2, 4.05, 2.9, 1.1, "rockprops", sub="porosity, permeability")
    ax.plot([7.15, 7.15, 2.05], [6.9, 6.3, 6.3], color=MUTED, lw=1.1, zorder=1)
    arrow(ax, 2.05, 6.3, 2.05, 5.15)
    arrow(ax, 3.5, 4.6, 4.2, 4.6)

    ax.text(9.55, 5.75, "EXTRACT, CONVERT, SUMMARISE", **lab)
    tools = [("wells", "synthetic wells"), ("crop", "sub-model"), ("avgmaps", "vertical averages"),
             ("regrid", "regular 3-D grid"), ("gpmexport", "HDF5 export")]
    for i, (t, sub_) in enumerate(tools):
        yy = 5.0 - i * 1.02
        box(ax, 9.6, yy - 0.42, 2.6, 0.84, t, sub=sub_, fs=9)
        arrow(ax, 7.1, 4.6, 9.6, yy)
    arrow(ax, 8.3, 7.4, 9.15, 7.4, color="#b9c2c8")
    ax.plot([9.15, 9.15], [7.4, 5.0 - 4 * 1.02], color="#b9c2c8", lw=1.1, zorder=0)
    for i in range(5):
        arrow(ax, 9.15, 5.0 - i * 1.02, 9.6, 5.0 - i * 1.02, color="#b9c2c8", lw=1.1)
    ax.text(12.45, 2.95, "to other\nsoftware", fontsize=7.5, color=MUTED, va="center")
    for i in range(5):
        arrow(ax, 12.2, 5.0 - i * 1.02, 12.4, 5.0 - i * 1.02, color="#b9c2c8", lw=0.8)

    ax.text(0.2, 2.75, "MONTE CARLO", **lab)
    for i in range(3):
        file_box(ax, 0.2 + i * 0.22, 1.55 - i * 0.48, 2.3, 0.75, ("run_1.vvm", "run_2.vvm", "run_n.vvm")[i], fs=7.6)
    box(ax, 3.4, 0.75, 2.4, 1.1, "mcstats", sub="mean and std. dev.")
    file_box(ax, 6.4, 0.8, 2.2, 1.0, "stats.vvm")
    arrow(ax, 2.95, 1.3, 3.4, 1.3)
    arrow(ax, 5.8, 1.3, 6.4, 1.3)
    save(fig, "workflow.png")


def fig_model_geometry():
    fig = plt.figure(figsize=(7.0, 3.0))
    ax = fig.add_axes([0.0, 0.02, 0.43, 0.92])
    ax.set_aspect("equal")
    ax.axis("off")
    nx, ny, c, a = 6, 4, 1.0, np.radians(18)
    R = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
    o = np.array([0.7, 1.0])
    P = lambda i, j: o + R @ np.array([i * c, j * c])
    for j in range(ny):
        p0, p1 = P(0, j), P(nx - 1, j)
        ax.plot([p0[0], p1[0]], [p0[1], p1[1]], color="#b9c2c8", lw=0.7)
    for i in range(nx):
        p0, p1 = P(i, 0), P(i, ny - 1)
        ax.plot([p0[0], p1[0]], [p0[1], p1[1]], color="#b9c2c8", lw=0.7)
    pts = np.array([P(i, j) for j in range(ny) for i in range(nx)])
    ax.scatter(pts[:, 0], pts[:, 1], s=10, color=ACCENT, zorder=3)
    pa = P(0, 0)
    ax.scatter(*pa, s=36, color="#c0392b", zorder=4)
    ax.text(pa[0] - 0.55, pa[1] - 0.85, "node (0, 0) at\nXORIGIN, YORIGIN", fontsize=7.5, color="#c0392b")
    pb = P(nx - 1, 0)
    ax.annotate("", xy=pb + R @ [0.6, 0], xytext=pb, arrowprops=dict(arrowstyle="-|>", color=INK, lw=0.9))
    ax.text(*(pb + R @ [0.45, -0.45]), "i  (columns)", fontsize=7.5, rotation=np.degrees(a), va="center")
    pc = P(0, ny - 1)
    ax.annotate("", xy=pc + R @ [0, 0.6], xytext=pc, arrowprops=dict(arrowstyle="-|>", color=INK, lw=0.9))
    ax.text(*(pc + R @ [-0.55, 0.75]), "j  (rows)", fontsize=7.5, rotation=np.degrees(a))
    q0, q1 = P(2, ny - 1), P(3, ny - 1)
    m = (q0 + q1) / 2 + R @ [0, 0.22]
    ax.text(*m, "CELLSIDE", fontsize=6.8, ha="center", va="bottom", rotation=np.degrees(a), color=MUTED)
    ax.annotate("", xy=q1 + R @ [0, 0.12], xytext=q0 + R @ [0, 0.12],
                arrowprops=dict(arrowstyle="<->", color=MUTED, lw=0.6, shrinkA=0, shrinkB=0))
    ax.plot([pa[0], pa[0] + 2.4], [pa[1], pa[1]], color=MUTED, lw=0.6, ls=(0, (3, 2)))
    th = np.linspace(0, a, 20)
    ax.plot(pa[0] + 1.9 * np.cos(th), pa[1] + 1.9 * np.sin(th), color=MUTED, lw=0.6)
    ax.text(pa[0] + 2.5, pa[1] - 0.08, "ROTATION < 0\n(counter-clockwise)", fontsize=6.8, color=MUTED, va="center")
    ax.text(pa[0] + 2.5, pa[1] - 0.55, "East", fontsize=6.5, color=MUTED, alpha=0)
    ax.set_xlim(-1.1, 7.9)
    ax.set_ylim(-0.3, 6.2)
    ax.text(-1.0, 5.9, "a   Plan view of the grid", fontsize=9.5, weight="demibold")

    bx = fig.add_axes([0.48, 0.1, 0.45, 0.76])
    x = np.linspace(0, 10, 80)
    base = -2.0 - 0.15 * x + 0.3 * np.sin(x / 2)
    tops = [base]
    for k in range(1, 6):
        tops.append(tops[-1] + 0.75 + 0.35 * np.sin(x / 2.2 + k) + 0.1 * k)
    tops = np.array(tops)
    tops[4] = tops[4] - np.where((x > 4) & (x < 7), 1.6 * np.sin((x - 4) / 3 * np.pi), 0)
    vals = np.array([0, 0.85, 0.35, 0.6, 0.2, 0.75])[:, None] * np.ones_like(x)
    s = draw_section(bx, tops, vals, SAND, Normalize(0, 1), x=x)
    for k in range(len(s)):
        bx.text(10.15, s[k, -1], "TOP$_{%s}$" % ("n-1" if k == len(s) - 1 else k), fontsize=7.5, va="center")
    for k, xm in ((1, 1.2), (3, 1.2), (5, 1.4)):
        i = np.searchsorted(x, xm)
        bx.text(xm, 0.5 * (s[k - 1, i] + s[k, i]), "layer %d" % k, fontsize=7.5, ha="center", va="center")
    bx.text(8.2, s[0, -10] - 0.7, "basement (layer 0)", fontsize=7.5, color="#6b655c", ha="center")
    xe = 5.5
    ie = np.searchsorted(x, xe)
    bx.annotate("TOP$_4$ cut into\nolder layers", (xe, s[3, ie] + 0.05), xytext=(6.6, s.max() + 0.55),
                fontsize=7, color=MUTED, arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.5))
    bx.set_xlim(0, 10)
    bx.set_ylim(s.min() - 0.9, s.max() + 1.3)
    bx.axis("off")
    bx.text(0, s.max() + 1.35, "b   Section along one row", fontsize=9.5, weight="demibold")
    save(fig, "model_geometry.png")


def fig_model_section():
    fig, axs = plt.subplots(2, 1, figsize=(7.0, 4.1), sharex=True)
    draw_section(axs[0], TOP[:, ROW, :], sand(SEDS)[:, ROW, :], SAND, Normalize(0, 1))
    axs[0].set_title("Sand fraction (SED1 + SED2) of each layer", loc="left")
    colorbar(fig, axs[0], SAND, Normalize(0, 1), "fraction")
    age = np.repeat(np.arange(N, dtype=float)[:, None], NX, axis=1)
    cm = plt.get_cmap("cividis", N - 1)
    draw_section(axs[1], TOP[:, ROW, :], age, cm, Normalize(0.5, N - 0.5))
    axs[1].set_title("Layer number k (time step of deposition)", loc="left")
    colorbar(fig, axs[1], cm, Normalize(0.5, N - 0.5), "layer", ticks=range(1, N, 2))
    for ax in axs:
        section_axes(ax, xlabel=ax is axs[1])
    save(fig, "model_section.png")


def fig_gpmexport():
    fig, ax = canvas(7.0, 3.1, (0, 14), (0, 6.2))
    ax.text(0.2, 5.85, "result.vvm  (records in order)", fontsize=8.5, weight="demibold")
    recs = ["TITLE", "SED_DIAMETERS", "CELLSIDE", "TIME  × n", "SEALEVEL  × n", "TOP  × n", "SED1 … SED4  × n",
            "ERODABILITY1 … 4  (optional)"]
    for k, r in enumerate(recs):
        y = 5.2 - k * 0.6
        ax.add_patch(Rectangle((0.2, y - 0.22), 4.2, 0.44, fc="#fbf6e6" if "× n" in r else "#f4f5f6",
                               ec="#d8d2bd", lw=0.6))
        ax.text(0.35, y, r, fontsize=7.6, family="monospace", va="center")
    box(ax, 5.2, 2.5, 2.3, 1.1, "gpmexport", fc=ACCENT, ec=ACCENT, tc="white", fs=10.5)
    arrow(ax, 4.5, 3.05, 5.2, 3.05)
    arrow(ax, 7.5, 3.05, 8.2, 3.05)
    ax.text(8.3, 5.85, "result.hdf5  (one set of grids per time step)", fontsize=8.5, weight="demibold")
    props = [("TOP", "surfaces 0 … t at step t"), ("SED1 … SED4", "fractions of layer t"),
             ("ERODABILITY1 … 4", "input, or 1"), ("SEALEVEL", "one value per step"),
             ("EROSION", "derived"), ("DEPODEPTH", "derived"), ("TOP_SLOPE_X, _Y, _MAG", "derived")]
    for k, (p_, d) in enumerate(props):
        y = 5.2 - k * 0.62
        derived = d == "derived"
        ax.add_patch(Rectangle((8.3, y - 0.24), 5.5, 0.48, fc=ACCENT_LIGHT if derived else "#f4f5f6",
                               ec="#c6d8de" if derived else "#dde0e2", lw=0.6))
        ax.text(8.45, y, p_, fontsize=7.6, family="monospace", va="center")
        ax.text(13.65, y, d, fontsize=7.2, va="center", ha="right", color=ACCENT if derived else MUTED)
    ax.text(8.3, 0.55, "+ time, age, grain-size, corner and min/max tables", fontsize=7.3, color=MUTED)
    save(fig, "gpmexport.png")


def read_gslib(path):
    with open(path) as f:
        toks = f.read().split()
    return np.array([float(v) for v in toks[3:]])


def fig_regrid_result():
    vals = read_gslib(REGULAR)
    nz = vals.size // (NX * NY)
    g = vals.reshape(nz, NY, NX)
    s = eroded(TOP)
    zmin, zmax = TOP.min(), TOP.max()
    dz = (zmax - zmin) / nz
    fig, axs = plt.subplots(2, 1, figsize=(7.0, 4.0), sharex=True)
    norm = Normalize(0, 1)
    cmap = LinearSegmentedColormap.from_list("s2", ["#f7f5ee", SED_COL[1], "#a87d1f"])
    draw_section(axs[0], TOP[:, ROW, :], SEDS[1][:, ROW, :], cmap, norm, basement_values=True)
    axs[0].set_title("Input: SED2 on the SedArch layers (basement included)", loc="left")
    sec = np.ma.masked_less(g[:, ROW, :], 0)
    cm2 = cmap.copy()
    cm2.set_bad("#ffffff")
    axs[1].pcolormesh(np.arange(NX + 1) * CELL - CELL / 2, zmin + np.arange(nz + 1) * dz, sec, cmap=cm2, norm=norm,
                      edgecolors="#ffffff", linewidth=0.25)
    axs[1].plot(XS, s[-1, ROW], color=INK, lw=0.7)
    axs[1].set_title("Output: SED2 in regular cells, CELLTHICK = %g m" % round(dz), loc="left")
    for ax in axs:
        ax.set_ylim(zmin, s[-1, ROW][XS >= XLIM[0]].max() + 15)
        section_axes(ax, xlabel=ax is axs[1])
    colorbar(fig, list(axs), cmap, norm, "SED2 fraction")
    save(fig, "regrid_result.png")


def fig_regrid_concepts():
    fig = plt.figure(figsize=(7.0, 2.5))
    for m, x0 in ((1, 0.0), (2, 0.25)):
        ax = fig.add_axes([x0, 0.05, 0.22, 0.78])
        ax.set_aspect("equal")
        ax.axis("off")
        for j in range(3):
            ax.plot([0, 2], [j, j], color="#b9c2c8", lw=0.8)
            ax.plot([j, j], [0, 2], color="#b9c2c8", lw=0.8)
        if m == 2:
            for t in (0.5, 1.5):
                ax.plot([0, 2], [t, t], color=ACCENT, lw=0.6, ls=(0, (2, 2)))
                ax.plot([t, t], [0, 2], color=ACCENT, lw=0.6, ls=(0, (2, 2)))
            nn = np.arange(0, 2.01, 0.5)
            X, Y = np.meshgrid(nn, nn)
            ax.scatter(X, Y, s=14, color="white", edgecolor=ACCENT, lw=1.0, zorder=3)
        X, Y = np.meshgrid([0, 1, 2], [0, 1, 2])
        ax.scatter(X, Y, s=16, color=INK, zorder=4)
        ax.set_xlim(-0.3, 2.3)
        ax.set_ylim(-0.3, 2.3)
        ax.set_title("MULTIPLICITY = %d\n%s nodes, %s cells" % (m, "3 × 3" if m == 1 else "5 × 5",
                                                                  "2 × 2" if m == 1 else "4 × 4"), fontsize=8.5)
    fig.text(0.0, 0.95, "a", fontsize=10, weight="demibold")
    fig.text(0.53, 0.95, "b", fontsize=10, weight="demibold")
    x = np.linspace(0, 10, 60)
    base = -0.35 * x
    tops = np.array([base + k * (0.55 + 0.05 * np.sin(x + k)) for k in range(5)])
    vals = np.array([0, 0.8, 0.3, 0.65, 0.2])[:, None] * np.ones_like(x)
    lo, hi = min(tops.min(), (tops - tops[0]).min()), max(tops.max(), (tops - tops[0]).max())
    for (tt, x0, ttl) in ((tops, 0.56, "HORIZONTALIZE = 0"), (tops - tops[0], 0.8, "HORIZONTALIZE = 1")):
        ax = fig.add_axes([x0, 0.14, 0.19, 0.66])
        draw_section(ax, tt, vals, SAND, Normalize(0, 1), x=x, basement=False)
        for z in np.arange(np.floor(lo), hi + 0.5, 0.5):
            ax.axhline(z, color="#9aa5ad", lw=0.35)
        ax.set_ylim(lo - 0.2, hi + 0.2)
        ax.axis("off")
        ax.set_title(ttl, fontsize=8.5)
    fig.text(0.56, 0.03, "Grey lines: output layers. Open circles: nodes added by MULTIPLICITY = 2.",
             fontsize=7, color=MUTED)
    save(fig, "regrid_concepts.png")


def world(i, j):
    a = np.radians(ROT)
    u = i * np.cos(a) + j * np.sin(a)
    v = -i * np.sin(a) + j * np.cos(a)
    return X0 + CELL * u, Y0 + CELL * v


def read_wells(path):
    wells, cur = [], []
    for line in open(path):
        if line.startswith("#"):
            continue
        p = line.split()
        if not p:
            if cur:
                wells.append(np.array(cur))
            cur = []
            continue
        cur.append([float(v) for v in p])
    if cur:
        wells.append(np.array(cur))
    return wells


def fig_wells():
    wells = read_wells(WELLS_OUT)
    s = eroded(TOP)
    ii, jj = np.meshgrid(np.arange(NX), np.arange(NY))
    X, Y = world(ii, jj)
    fig = plt.figure(figsize=(7.0, 3.4))
    ax = fig.add_axes([0.06, 0.2, 0.42, 0.72])
    pc = ax.pcolormesh(X / 1000, Y / 1000, s[-1], cmap="terrain", shading="gouraud")
    ax.set_aspect("equal")
    cax = fig.add_axes([0.06, 0.06, 0.42, 0.025])
    cb = fig.colorbar(pc, cax=cax, orientation="horizontal")
    cb.outline.set_linewidth(0.4)
    cb.ax.tick_params(labelsize=7)
    cb.set_label("final TOP (m)", fontsize=7.5)
    for n, w in enumerate(wells, 1):
        ax.scatter(w[0, 0] / 1000, w[0, 1] / 1000, s=42, marker="v", color="#c0392b", edgecolor="white", lw=0.8, zorder=4)
        ax.text(w[0, 0] / 1000 - 0.18, w[0, 1] / 1000 + 0.12, "Well %d" % n, fontsize=8, weight="demibold", ha="right")
    bx, by = world(np.array([0, NX - 1, NX - 1, 0, 0]), np.array([0, 0, NY - 1, NY - 1, 0]))
    ax.plot(bx / 1000, by / 1000, color=INK, lw=0.6)
    ax.scatter(X0 / 1000, Y0 / 1000, s=16, color=INK, zorder=4)
    ax.annotate("node (0, 0)", (X0 / 1000, Y0 / 1000), xytext=(X0 / 1000 + 0.9, Y0 / 1000 + 0.15), fontsize=7,
                color=MUTED, arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.5))
    ax.set_xlabel("X (km)", labelpad=1)
    ax.set_ylabel("Y (km)")
    ax.set_title("Map (ROTATION = %g)" % ROT, loc="left")
    for n, w in enumerate(wells):
        lx = fig.add_axes([0.62 + n * 0.21, 0.2, 0.11, 0.72])
        z = w[:, 2]
        fr = w[:, 3:7]
        surf = z.copy()
        for k in range(len(surf) - 2, -1, -1):
            surf[k] = min(surf[k], surf[k + 1])
        for k in range(1, len(z)):
            lo, hi = surf[k - 1], surf[k]
            if hi - lo <= 1e-6:
                continue
            left = 0.0
            for q in range(4):
                lx.add_patch(Rectangle((left, lo), fr[k, q], hi - lo, fc=SED_COL[q], ec="none"))
                left += fr[k, q]
            lx.plot([0, 1], [hi, hi], color="white", lw=0.5)
        lx.set_xlim(0, 1)
        lx.set_ylim(surf[0] - 1.5, surf[-1] + 1.5)
        lx.set_xticks([0, 0.5, 1])
        lx.set_xticklabels(["0", "", "1"])
        lx.set_xlabel("fraction", fontsize=7.5, labelpad=1)
        lx.set_title("Well %d" % (n + 1), fontsize=9)
        lx.set_ylabel("elevation (m)" if n == 0 else "")
    handles = [Rectangle((0, 0), 1, 1, fc=c) for c in SED_COL]
    fig.legend(handles, SED_NAME, loc="lower left", ncol=2, fontsize=7.2, frameon=False,
               bbox_to_anchor=(0.56, -0.02), handlelength=1.0, columnspacing=1.0)
    save(fig, "wells.png")


def fig_crop():
    s = eroded(TOP)
    th = s[-1] - s[0]
    xt = cube(XTRACT, "TOP")
    xs1 = [cube(XTRACT, "SED%d" % i) for i in range(1, 3)]
    fig = plt.figure(figsize=(7.0, 2.6))
    ax = fig.add_axes([0.06, 0.17, 0.4, 0.72])
    ax.imshow(th, origin="lower", cmap="YlGnBu", extent=(-0.5, NX - 0.5, -0.5, NY - 0.5))
    ax.add_patch(Rectangle((10, 10), 20, 20, fill=False, ec="#c0392b", lw=1.4))
    ax.text(10, 31.2, "xmin–xmax = 10–30,  ymin–ymax = 10–30", color="#c0392b", fontsize=7)
    ax.set_xlabel("node i")
    ax.set_ylabel("node j")
    ax.set_title("Input: total thickness (m)", loc="left")
    bx = fig.add_axes([0.56, 0.17, 0.44, 0.72])
    r = xt.shape[1] // 2
    xx = np.arange(xt.shape[2]) * CELL
    draw_section(bx, xt[:, r, :], (xs1[0] + xs1[1])[:, r, :], SAND, Normalize(0, 1), x=xx)
    bx.set_title("Extracted model: section along its row %d" % r, loc="left")
    bx.set_xlabel("distance along i (m), from the new node 0")
    bx.set_ylabel("elevation (m)")
    save(fig, "crop.png")


def fig_fitdepth():
    t2 = cube(FITDEPTH, "TOP")
    sd2 = [cube(FITDEPTH, "SED%d" % i) for i in range(1, 5)]
    fig, axs = plt.subplots(2, 1, figsize=(7.0, 4.2), sharex=True)
    draw_section(axs[0], TOP[:, ROW, :], sand(SEDS)[:, ROW, :], SAND, Normalize(0, 1))
    axs[0].set_title("Before: SedArch result", loc="left")
    draw_section(axs[1], t2[:, ROW, :], sand(sd2)[:, ROW, :], SAND, Normalize(0, 1), special={len(t2) - 1: OVERBURDEN})
    axs[1].set_title("After fitdepth: fitted to present-day surfaces, with overburden", loc="left")
    s2 = eroded(t2[:, ROW, :])
    i = NX // 2
    axs[1].text(XS[i], 0.5 * (s2[-1, i] + s2[-2, i]), "overburden", ha="center", va="center", fontsize=8, color=MUTED)
    lo = min(axs[0].get_ylim()[0], axs[1].get_ylim()[0])
    hi = max(axs[0].get_ylim()[1], axs[1].get_ylim()[1])
    for ax in axs:
        ax.set_ylim(lo, hi)
        ax.set_ylabel("elevation (m)")
    axs[1].set_xlabel("distance along i (m)")
    colorbar(fig, list(axs), SAND, Normalize(0, 1), "sand fraction")
    save(fig, "fitdepth.png")


def read_post_parms():
    vals = {}
    for line in open(POST_PARM):
        line = line.split("!")[0]
        if "=" in line:
            k, v = line.split("=", 1)
            vals[k.strip()] = float(v.split()[0])
    return vals


def fig_rockprops():
    tp = cube(POST, "TOP")
    por = cube(POST, "POR")
    kh = cube(POST, "PERMH")
    fig = plt.figure(figsize=(7.0, 4.3))
    a = fig.add_axes([0.08, 0.58, 0.5, 0.36])
    ca = fig.add_axes([0.595, 0.58, 0.012, 0.36])
    b = fig.add_axes([0.08, 0.1, 0.5, 0.36])
    cb_ = fig.add_axes([0.595, 0.1, 0.012, 0.36])
    pn = Normalize(por.min(), por.max())
    draw_section(a, tp[:, ROW, :], por[:, ROW, :], plt.get_cmap("viridis"), pn)
    a.set_title("POR (fraction)", loc="left")
    kn = LogNorm(max(kh[kh > 0].min(), 0.5), kh.max())
    draw_section(b, tp[:, ROW, :], np.where(kh > 0, kh, kn.vmin)[:, ROW, :], plt.get_cmap("plasma"), kn)
    b.set_title("PERMH (mD)", loc="left")
    for ax, cax, cm, nn in ((a, ca, "viridis", pn), (b, cb_, "plasma", kn)):
        c_ = fig.colorbar(plt.cm.ScalarMappable(cmap=cm, norm=nn), cax=cax)
        c_.outline.set_linewidth(0.4)
        c_.ax.tick_params(labelsize=7, width=0.4, length=2)
        section_axes(ax, xlabel=ax is b)
    c = fig.add_axes([0.74, 0.27, 0.25, 0.63])
    p = read_post_parms()
    burial = np.linspace(0, 3000, 200)
    for q in range(4):
        p0, p1 = p.get("POR%d_0" % (q + 1)), p.get("POR%d_1000" % (q + 1))
        if p0 is None or p1 is None:
            continue
        phi = p0 * (p1 / p0) ** (burial / 1000.0)
        c.plot(phi, burial, color=SED_COL[q] if q != 1 else "#c9a53c", lw=1.8, label=SED_NAME[q].split(" (")[0])
        c.scatter([p0, p1], [0, 1000], s=12, color=INK, zorder=3)
    c.invert_yaxis()
    c.set_xlabel("porosity (fraction)")
    c.set_ylabel("burial (m)")
    c.set_title("Compaction of pure\nsediments (example)", loc="left")
    c.legend(fontsize=7, frameon=False, loc="upper center", bbox_to_anchor=(0.45, -0.17), ncol=2, columnspacing=0.8, handlelength=1.4)
    c.axhline(1000, color="#b9c2c8", lw=0.6, ls=(0, (3, 2)))
    save(fig, "rockprops.png")


def fig_avgmaps():
    m_, n_ = 2, 8
    th = cube(VAVG, "THICKNESS")[0][ROW]
    avg = [cube(VAVG, "SED%d_AVG" % i)[0][ROW] for i in range(1, 5)]
    fig = plt.figure(figsize=(7.0, 3.9))
    a = fig.add_axes([0.08, 0.55, 0.86, 0.38])
    vals = np.zeros((N, NX))
    for k in range(m_, n_ + 1):
        vals[k] = 1
    cm = LinearSegmentedColormap.from_list("hl", ["#e4e7ea", ACCENT])
    draw_section(a, TOP[:, ROW, :], vals, cm, Normalize(0, 1))
    a.set_title("Layers %d to %d selected (m = %d, n = %d)" % (m_, n_, m_, n_), loc="left")
    section_axes(a, xlabel=False)
    b = fig.add_axes([0.08, 0.1, 0.86, 0.32], sharex=a)
    ok = th > 0.001
    b.stackplot(XS, *[np.where(ok, v, np.nan) for v in avg], colors=SED_COL, labels=SED_NAME, lw=0)
    b.set_ylim(0, 1)
    b.set_ylabel("SEDn_AVG")
    b.set_xlabel("distance along i (m)")
    t = b.twinx()
    t.plot(XS, th, color=INK, lw=1.2, label="THICKNESS")
    t.set_ylabel("THICKNESS (m)")
    t.spines["right"].set_visible(True)
    b.legend(loc="upper left", fontsize=7, ncol=4, frameon=False, bbox_to_anchor=(0, 1.2))
    t.legend(loc="upper right", fontsize=7, frameon=False, bbox_to_anchor=(1, 1.2))
    b.set_title(" ", fontsize=4)
    save(fig, "avgmaps.png")


def fig_mcstats():
    fig, ax = canvas(7.0, 2.5, (0, 14), (0, 5.0))
    for i, label in ((0, "run_1.vvm"), (1, "run_2.vvm"), (3, "run_n.vvm")):
        y = 3.85 - i * 0.95
        file_box(ax, 0.2, y, 2.2, 0.8, label, fs=7.8)
        arrow(ax, 2.4, y + 0.4, 3.9, 2.5)
    ax.text(1.3, 3.85 - 2 * 0.95 + 0.42, "⋮", fontsize=12, ha="center", va="center", color=MUTED)
    box(ax, 3.9, 1.95, 2.4, 1.1, "mcstats", sub="merges each run")
    file_box(ax, 7.0, 1.8, 2.6, 1.4, "stats.vvm", fs=8.5)
    arrow(ax, 6.3, 2.5, 7.0, 2.5)
    items = [("TOP, SED1, … ", "mean"), ("TOP_STDV, SED1_STDV, …", "std. dev."), ("N_REALIZATIONS", "count")]
    for k, (t, d) in enumerate(items):
        ax.text(10.0, 3.0 - k * 0.5, t, fontsize=7.6, va="center", family="monospace")
        ax.text(13.9, 3.0 - k * 0.5, d, fontsize=7.6, va="center", ha="right", color=MUTED)
    ax.plot([9.8, 9.8], [1.8, 3.2], color="#c9a54a", lw=0.8)
    ax.annotate("", xy=(6.6, 1.75), xytext=(8.3, 1.75),
                arrowprops=dict(arrowstyle="-|>", color=ACCENT, lw=1.0, connectionstyle="arc3,rad=-0.6"))
    ax.text(7.45, 0.5, "an existing statistics file is\nread back and updated", fontsize=7.5, color=ACCENT, ha="center")
    save(fig, "mcstats.png")


if __name__ == "__main__":
    print("figures ->", OUT)
    for f in (fig_cover, fig_workflow, fig_model_geometry, fig_model_section, fig_gpmexport,
              fig_regrid_result, fig_regrid_concepts, fig_wells, fig_crop,
              fig_fitdepth, fig_rockprops, fig_avgmaps, fig_mcstats):
        f()
