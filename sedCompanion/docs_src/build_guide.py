"""
build_guide.py - builds the SedCompanion user guide (PDF).

Usage:  python3 build_guide.py [figures_dir] [output.pdf]
Defaults: figures in ./figures (made by make_figures.py), PDF written next to the package
as SedCompanion_userdoc.pdf. Needs reportlab and Pillow, and the macOS fonts
Avenir Next, Georgia and Menlo.
"""
import os
import re
import sys

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.fonts import addMapping
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Flowable, Frame, Image, KeepTogether,
                                NextPageTemplate, PageBreak, PageTemplate, Paragraph, Spacer, Table,
                                TableStyle)
from reportlab.platypus.tableofcontents import TableOfContents

HERE = os.path.dirname(os.path.abspath(__file__))
FIG = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "figures")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "..", "SedCompanion_userdoc.pdf")

# ---------------------------------------------------------------- fonts
SYS = "/System/Library/Fonts/"
SUP = SYS + "Supplemental/"
for name, path, idx in [("Sans", SYS + "Avenir Next.ttc", 7), ("Sans-Medium", SYS + "Avenir Next.ttc", 5),
                        ("Sans-Demi", SYS + "Avenir Next.ttc", 2), ("Sans-Italic", SYS + "Avenir Next.ttc", 4),
                        ("Sans-Bold", SYS + "Avenir Next.ttc", 0), ("Mono", SYS + "Menlo.ttc", 0),
                        ("Mono-Bold", SYS + "Menlo.ttc", 1)]:
    pdfmetrics.registerFont(TTFont(name, path, subfontIndex=idx))
for name, f in [("Serif", "Georgia.ttf"), ("Serif-Bold", "Georgia Bold.ttf"),
                ("Serif-Italic", "Georgia Italic.ttf"), ("Serif-BoldItalic", "Georgia Bold Italic.ttf")]:
    pdfmetrics.registerFont(TTFont(name, SUP + f))
addMapping("Serif", 0, 0, "Serif"); addMapping("Serif", 1, 0, "Serif-Bold")
addMapping("Serif", 0, 1, "Serif-Italic"); addMapping("Serif", 1, 1, "Serif-BoldItalic")
addMapping("Sans", 0, 0, "Sans"); addMapping("Sans", 1, 0, "Sans-Demi")
addMapping("Sans", 0, 1, "Sans-Italic"); addMapping("Sans", 1, 1, "Sans-Demi")
addMapping("Mono", 0, 0, "Mono"); addMapping("Mono", 1, 0, "Mono-Bold")
addMapping("Mono", 0, 1, "Mono"); addMapping("Mono", 1, 1, "Mono-Bold")

# ---------------------------------------------------------------- palette and styles
ACCENT = colors.HexColor("#1f5f73")
ACCENT_LIGHT = colors.HexColor("#e8f1f3")
INK = colors.HexColor("#2b3238")
MUTED = colors.HexColor("#6b7780")
RULE = colors.HexColor("#d5dadd")
CODE_BG = colors.HexColor("#f5f6f7")
NOTE_BG = colors.HexColor("#fbf6e6")
NOTE_BAR = colors.HexColor("#c9a54a")

body = ParagraphStyle("body", fontName="Serif", fontSize=9.8, leading=14.6, textColor=INK, spaceAfter=7)
lead = ParagraphStyle("lead", parent=body, fontSize=11, leading=16.5, textColor=INK, spaceAfter=10)
small = ParagraphStyle("small", parent=body, fontSize=8.2, leading=11.5, textColor=MUTED)
h1 = ParagraphStyle("h1", fontName="Sans-Demi", fontSize=24, leading=29, textColor=INK, spaceAfter=14)
h1num = ParagraphStyle("h1num", fontName="Sans-Demi", fontSize=11, leading=14, textColor=ACCENT, spaceAfter=2)
h2 = ParagraphStyle("h2", fontName="Sans-Demi", fontSize=13, leading=17, textColor=ACCENT, spaceBefore=14,
                    spaceAfter=5, keepWithNext=1)
h3 = ParagraphStyle("h3", fontName="Sans-Demi", fontSize=10.2, leading=13.5, textColor=INK, spaceBefore=9,
                    spaceAfter=3, keepWithNext=1)
bul = ParagraphStyle("bul", parent=body, leftIndent=15, bulletIndent=3, spaceAfter=3.5)
code = ParagraphStyle("code", fontName="Mono", fontSize=8.1, leading=11.4, textColor=INK)
eq = ParagraphStyle("eq", fontName="Serif-Italic", fontSize=10, leading=15, alignment=TA_CENTER,
                    spaceBefore=1, spaceAfter=7, textColor=INK)
cap = ParagraphStyle("cap", fontName="Sans", fontSize=8.2, leading=11.4, textColor=MUTED, spaceAfter=12)
cell = ParagraphStyle("cell", fontName="Serif", fontSize=8.7, leading=11.8, textColor=INK)
cellh = ParagraphStyle("cellh", fontName="Sans-Demi", fontSize=8.2, leading=11, textColor=ACCENT)
cellm = ParagraphStyle("cellm", fontName="Mono", fontSize=7.9, leading=11.2, textColor=INK)
notelab = ParagraphStyle("notelab", fontName="Sans-Demi", fontSize=8.2, leading=11, textColor=colors.HexColor("#8a6a12"))
notetxt = ParagraphStyle("notetxt", parent=body, fontSize=9.0, leading=13, spaceAfter=0)
glance_k = ParagraphStyle("gk", fontName="Sans-Demi", fontSize=8.2, leading=11.5, textColor=ACCENT)
glance_v = ParagraphStyle("gv", fontName="Serif", fontSize=8.9, leading=12.2, textColor=INK)
toc1 = ParagraphStyle("toc1", fontName="Sans-Medium", fontSize=10.5, leading=15, leftIndent=0, textColor=INK,
                      spaceBefore=5)
toc2 = ParagraphStyle("toc2", fontName="Sans", fontSize=9, leading=12.5, leftIndent=18, textColor=MUTED)

S = []
FIGNO = [0]
CHAPTER = [0]


def M(t):
    """Inline monospace."""
    return "<font name='Mono' size='8.4'>%s</font>" % t


class Anchor(Flowable):
    """Zero-size marker that reports a heading to the table of contents and running header."""

    def __init__(self, level, text, key):
        super().__init__()
        self.level, self.text, self.key = level, text, key
        self.width = self.height = 0

    def draw(self):
        self.canv.bookmarkPage(self.key)
        self.canv.addOutlineEntry(self.text, self.key, level=self.level)


class Title(Flowable):
    """Zero-size marker that sets the running header without a contents entry."""

    def __init__(self, text):
        super().__init__()
        self.text = text
        self.width = self.height = 0

    def draw(self):
        pass


class Doc(BaseDocTemplate):
    chapter_title = ""

    def beforeDocument(self):
        Doc.chapter_title = ""

    def afterFlowable(self, f):
        if isinstance(f, Title):
            Doc.chapter_title = f.text
        if isinstance(f, Anchor):
            if f.level == 0:
                Doc.chapter_title = f.text
            self.notify("TOCEntry", (f.level, f.text, self.page, f.key))


TOOL_RE = re.compile(r"(?<![\w/.\-])(fitdepth|rockprops|crop|avgmaps|regrid|gpmexport|mcstats)(?![\w\-])(?!\.\w)")


def T(t):
    """Set tool names in prose in the tool style; {wells} marks the wells tool."""
    parts = re.split(r"(<font name='Mono'.*?</font>)", t)
    for i in range(0, len(parts), 2):
        p = TOOL_RE.sub(lambda m: TOOLFMT % m.group(1), parts[i])
        parts[i] = p.replace("{wells}", TOOLFMT % "wells")
    return "".join(parts)


TOOLFMT = "<font name='Sans-Demi' color='#1f5f73'>%s</font>"


def P(t, st=body):
    if st not in (h1, h1num, h2, h3, code):
        t = T(t)
    S.append(Paragraph(t, st))


def CHAP(title, appendix=None):
    S.append(NextPageTemplate("body"))
    S.append(PageBreak())
    if appendix is not None:
        label = ("APPENDIX %s" % appendix).strip()
        full = ("Appendix %s" % appendix).strip() + "  " + title
    else:
        CHAPTER[0] += 1
        label, full = "CHAPTER %d" % CHAPTER[0], "%d  %s" % (CHAPTER[0], title)
    S.append(Anchor(0, full, "c%s" % (CHAPTER[0] if appendix is None else "app" + appendix)))
    S.append(Spacer(1, 6))
    P(label, h1num)
    P(title, h1)
    S.append(Rule(ACCENT, 1.4, 0.55 * inch, after=14))


def H2(t):
    key = "s%d" % len(S)
    S.append(CondPageBreak(1.3 * inch))
    S.append(Anchor(1, t, key))
    P(t, h2)


def H3(t):
    P(t, h3)


def B(items):
    for t in items:
        S.append(Paragraph(T(t), bul, bulletText="•"))


def NUM(items):
    for i, t in enumerate(items, 1):
        S.append(Paragraph(T(t), bul, bulletText="%d." % i))


def EQ(t):
    P(t, eq)


class Rule(Flowable):
    def __init__(self, color=RULE, width=0.5, length=None, after=6):
        super().__init__()
        self.color, self.lw, self.length, self.after = color, width, length, after

    def wrap(self, aw, ah):
        self.aw = aw
        return aw, self.lw + self.after

    def draw(self):
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(self.lw)
        self.canv.line(0, self.after, self.length or self.aw, self.after)


def CODE(text):
    lines = text.strip("\n").split("\n")
    para = Paragraph("<br/>".join(l.replace("&", "&amp;").replace("<", "&lt;").replace(" ", "&nbsp;") for l in lines), code)
    t = Table([[para]], colWidths=["100%"])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), CODE_BG),
                           ("LINEBEFORE", (0, 0), (0, -1), 2, ACCENT),
                           ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                           ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    S.append(t)
    S.append(Spacer(1, 9))


def NOTE(text, label="Note"):
    t = Table([[Paragraph(label.upper(), notelab)], [Paragraph(T(text), notetxt)]], colWidths=["100%"])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), NOTE_BG),
                           ("LINEBEFORE", (0, 0), (0, -1), 2, NOTE_BAR),
                           ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                           ("TOPPADDING", (0, 0), (0, 0), 7), ("BOTTOMPADDING", (0, 0), (0, 0), 1),
                           ("TOPPADDING", (0, 1), (0, 1), 1), ("BOTTOMPADDING", (0, 1), (0, 1), 8)]))
    S.append(KeepTogether([t, Spacer(1, 9)]))


def GLANCE(rows):
    data = [[Paragraph(k.upper(), glance_k), Paragraph(T(v), glance_v)] for k, v in rows]
    t = Table(data, colWidths=[0.95 * inch, None])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), ACCENT_LIGHT),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                           ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                           ("TOPPADDING", (0, 0), (-1, 0), 9), ("BOTTOMPADDING", (0, -1), (-1, -1), 9)]))
    S.append(t)
    S.append(Spacer(1, 12))


def TABLE(rows, widths, mono=(0,)):
    data = []
    for r, row in enumerate(rows):
        out = []
        for c, v in enumerate(row):
            st = cellh if r == 0 else (cellm if c in mono else cell)
            out.append(Paragraph(v if st is not cell else T(v), st))
        data.append(out)
    t = Table(data, colWidths=[w * inch for w in widths], repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 0.9, ACCENT),
                           ("LINEBELOW", (0, 1), (-1, -1), 0.35, RULE),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                           ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5)]))
    S.append(t)
    S.append(Spacer(1, 11))


def FIGURE(fname, caption, w=6.0):
    FIGNO[0] += 1
    from PIL import Image as PI
    p = os.path.join(FIG, fname)
    im = PI.open(p)
    h = w * im.size[1] / im.size[0]
    S.append(KeepTogether([Spacer(1, 4), Image(p, width=w * inch, height=h * inch), Spacer(1, 6),
                           Paragraph("<font name='Sans-Demi' color='#2b3238'>Figure %d.</font>  %s" % (FIGNO[0], T(caption)),
                                     cap)]))


def ARGS(rows):
    TABLE([["Argument", "Description"]] + rows, [1.75, 4.65])


# ======================================================================
# Cover
S.append(Spacer(1, 1.35 * inch))
P("SedCompanion", ParagraphStyle("ct", fontName="Sans-Demi", fontSize=44, leading=50, textColor=INK))
S.append(Spacer(1, 4))
P("Companion tools for SedArch models", ParagraphStyle("cs", fontName="Sans", fontSize=17, leading=22,
                                                       textColor=ACCENT))
S.append(Spacer(1, 30))
S.append(Image(os.path.join(FIG, "cover.png"), width=6.5 * inch, height=6.5 * inch * 2.4 / 7.2))
S.append(Spacer(1, 30))
P("USER GUIDE", ParagraphStyle("cu", fontName="Sans-Demi", fontSize=10, leading=13, textColor=MUTED))
P("November 2026", ParagraphStyle("cd", fontName="Sans", fontSize=10, leading=13, textColor=MUTED))

# Contents
S.append(NextPageTemplate("body"))
S.append(PageBreak())
S.append(Title("Contents"))
P("Contents", h1)
S.append(Rule(ACCENT, 1.4, 0.55 * inch, after=14))
toc = TableOfContents()
toc.levelStyles = [toc1, toc2]
toc.dotsMinLevel = 0
S.append(toc)

# ======================================================================
CHAP("Introduction")
P("SedCompanion is a set of command-line tools for working with SedArch models. SedArch simulates the "
  "deposition and erosion of sediment through time and writes the result as a vvm file: a stack of surfaces, "
  "one per time step, with the sediment composition of every layer between them. SedCompanion takes that file "
  "further. It places the model at its present-day depth, adds porosity and permeability, extracts wells and "
  "sub-models, computes averages and statistics, and converts the model to the formats used by other "
  "geological and geostatistical software.", lead)
P("None of the tools is needed to run SedArch. Each one does a single job, reads and writes plain files, and "
  "can be combined with the others in scripts.")

H2("A typical workflow")
P("Figure 1 shows how the tools fit together. A SedArch result is usually first placed in depth with fitdepth "
  "and given rock properties with rockprops. The result is then sampled, cut, averaged, regridded or converted "
  "for use elsewhere. When SedArch is run many times with varied input (a Monte Carlo study), mcstats "
  "summarises the runs. Every tool except mcstats also accepts a SedArch result directly, so the order can "
  "be adapted to the data available and the purpose of the study.")
FIGURE("workflow.png", "How the SedCompanion tools are used with SedArch. Grey arrows: every tool on the right "
       "also accepts the SedArch result directly.", w=5.5)

H2("The tools")
TABLE([["Tool", "What it does", "Writes"],
       ["fitdepth", "Fits a model to present-day base, top or isopach surfaces and optionally adds an overburden.",
        "vvm model"],
       ["rockprops", "Adds layer thickness, depth of deposition, burial, porosity and permeability.", "vvm model"],
       ["wells", "Extracts synthetic vertical wells at given X–Y locations.", "xyz text"],
       ["crop", "Cuts out a rectangular part of a model, optionally a range of layers.", "vvm model"],
       ["avgmaps", "Computes thickness-weighted vertical averages over a range of layers.", "vvm maps"],
       ["regrid", "Resamples one property onto a regular 3-D grid of equal cells.", "grid text"],
       ["gpmexport", "Converts a model to an HDF5 file with derived properties.", "HDF5"],
       ["mcstats", "Combines many model runs into mean and standard-deviation models.", "vvm model"]],
      [0.95, 4.35, 1.1])

# ======================================================================
CHAP("Getting started")
H2("Requirements")
B(["Python 3.9 or later.",
   "NumPy.",
   "h5py, for gpmexport only."])
P("SedCompanion is a Python package. It needs no installation step: the folder " + M("sedCompanion") +
  " only has to be on Python’s module search path.")

H2("Running a tool")
P("Every tool is started through the package, followed by the tool name and its arguments:")
CODE("python3 -m sedCompanion <tool> <arguments ...>")
P("Python finds the package when the current folder contains the " + M("sedCompanion") + " folder, or when "
  "the folder that contains it is listed in the " + M("PYTHONPATH") + " environment variable. Setting "
  + M("PYTHONPATH") + " once lets you run the tools from any working folder:")
CODE("export PYTHONPATH=/path/to/folder/containing/sedCompanion\n"
     "python3 -m sedCompanion fitdepth model.vvm surfaces.vvm model_depth.vvm")
P("Running " + M("python3 -m sedCompanion") + " without a tool name lists the available tools.")

H2("Conventions shared by all tools")
B(["<b>Arguments.</b> Each tool accepts a fixed number of arguments, given in its chapter. With any other "
   "number, it prints a short help text and stops without reading or writing anything.",
   "<b>Messages.</b> Each tool starts by printing a one-line banner with its name. Progress messages go to "
   "standard output; warnings and errors go to standard error and start with " + M("WARNING:") + " or "
   + M("ERROR:") + ".",
   "<b>Output files</b> are overwritten without asking. The one exception is mcstats, which merges new runs "
   "into an existing statistics file.",
   "<b>Line endings.</b> Text files are written with Windows line endings (CR LF), which every tool and most "
   "software accept. Put " + M("--lf") + " before the tool name to write Unix line endings instead:"])
CODE("python3 -m sedCompanion --lf fitdepth model.vvm surfaces.vvm model_depth.vvm")

H2("Quick start with the example model")
P("The folder " + M("sedCompanion/input") + " contains a small SedArch result, " + M("dispersion_out.vvm") +
  " (61 × 41 nodes, 100 m apart, 11 time steps), and a parameter file for each tool. The commands below "
  "run every tool on it and write the results to a new folder " + M("work") + ". Run them from inside the "
  + M("sedCompanion") + " folder.")
CODE('export PYTHONPATH="$PWD/.."\n'
     'sc() { python3 -m sedCompanion "$@"; }      # shorthand for this session\n'
     "mkdir -p work\n"
     "sc fitdepth  input/dispersion_out.vvm input/fitdepth_parm.vvm   work/depth.vvm\n"
     "sc rockprops input/dispersion_out.vvm input/rockprops_parm.vvmp work/post.vvm\n"
     "sc wells     input/dispersion_out.vvm input/wells_parm.vvmp     work/wells.xyz\n"
     "sc crop      input/dispersion_out.vvm work/part.vvm 10 30 10 30\n"
     "sc avgmaps   input/dispersion_out.vvm work/average.vvm 2 8\n"
     "sc regrid    input/dispersion_out.vvm input/regrid_parm.vvmp    work/grid.txt\n"
     "sc gpmexport input/dispersion_out.vvm work/model.hdf5\n"
     "sc mcstats   work/stats.vvm input/dispersion_out.vvm")
P("The figures in this guide were made from this example model and these results.")

# ======================================================================
CHAP("Models and vvm files")
P("All tools work on SedArch models stored in vvm files. This chapter describes how a model is organised, "
  "how the tools read vvm and vvmp files, and the conventions used for numbers in the files they write.",
  lead)

H2("The model grid")
P("A model is defined on a regular grid of nodes (Figure 2a). The nodes are numbered i = 0, 1, … along each "
  "row and j = 0, 1, … from row to row. Every surface and every property is stored as a 2-D array with one "
  "value per node.")
TABLE([["Keyword", "Meaning"],
       ["CELLSIDE", "Distance between neighbouring nodes, in both directions."],
       ["XORIGIN, YORIGIN", "Map coordinates of node (0, 0)."],
       ["ROTATION", "Rotation of the grid about node (0, 0), in degrees. Positive values turn the rows "
                    "clockwise, negative values counter-clockwise. With ROTATION = 0, rows run West to East "
                    "and successive rows go South to North."]],
      [1.5, 4.9])
FIGURE("model_geometry.png", "(a) The model grid in plan view. (b) Surfaces and layers in a section along one "
       "row of nodes. Each surface TOP<sub>k</sub> is the top of the model at the end of time step k; layer k "
       "is the sediment deposited during that step. A later surface can cut into older layers.")

H2("Surfaces, layers and time steps")
P("A SedArch result holds one surface " + M("TOP") + " for every time step. " + M("TOP") + " number 0 is the "
  "basement; the space between TOP<sub>k−1</sub> and TOP<sub>k</sub> is layer k. The composition of layer k is "
  "given by the sediment fractions " + M("SED1") + ", " + M("SED2") + ", …, which add up to 1. Sediment types "
  "are ordered by grain size, given in " + M("SED_DIAMETERS") + ". The fractions stored with " + M("TOP") +
  " number 0 describe the basement.")
P("Because a later step can erode earlier deposits, a surface as it exists today is the original surface "
  "clipped by all younger ones. The preserved thickness of layer k is therefore")
EQ("thick<sub>k</sub> = max( 0, min( TOP<sub>k</sub>, TOP<sub>k+1</sub>, …, TOP<sub>n−1</sub> ) − "
   "TOP<sub>k−1</sub> ),&nbsp;&nbsp;&nbsp; thick<sub>0</sub> = 0")
P("where n is the number of surfaces. rockprops and avgmaps use this definition. Figure 3 shows the example "
  "model in section.")
FIGURE("model_section.png", "The example model along row 20. Top: sand fraction (SED1 + SED2) of each layer. "
       "Bottom: the layer number, which is also the time step in which the sediment was deposited. The "
       "basement is shown in grey.")

H2("Other records in a model file")
TABLE([["Keyword", "Occurs", "Content"],
       ["TITLE", "once", "Name of the model."],
       ["SED_DIAMETERS", "once", "Grain diameter of each sediment type, coarsest first."],
       ["TIME", "per step", "Time at the end of the step."],
       ["SEALEVEL", "per step", "Sea level at the end of the step."],
       ["TECTONICS", "per step", "Optional. Cumulative vertical movement. Where a tool works with present "
                                 "positions, the last TECTONICS array is added to every TOP."]],
      [1.4, 0.85, 4.15])

H2("Reading vvm and vvmp files")
P("Model files (" + M(".vvm") + ") and parameter files (" + M(".vvmp") + ", or " + M(".vvm") + ") have the "
  "same syntax: a list of keywords, each followed by a value. The rules below matter mostly when you write a "
  "parameter file by hand.")
NUM(["Everything from the first " + M("!") + " on a line is a comment, even inside quotes. Spaces and tabs at "
     "either end of a line are ignored.",
     "A line containing " + M("=") + " starts a keyword. The keyword is the text before the " + M("=") + "; "
     "the value starts after it and can continue on the following lines.",
     "A value is numeric if its first item is a number, otherwise it is a list of words or quoted strings. "
     "The first item is looked for after the " + M("=") + ", or on the next line if nothing follows the "
     + M("=") + ". A blank line directly after " + M("KEY =") + " therefore makes the value a list of "
     "strings: start numeric arrays on the keyword line or the line just below it.",
     "A numeric value ends at the first line that does not start with a number, normally the next keyword. "
     "Inside it, one blank line separates the layers of a 3-D array and two blank lines separate groups. "
     "More than two consecutive blank lines are an error. All rows must have the same number of values.",
     "In a 2-D array, each line is one row of nodes (i increasing to the right) and the lines follow each "
     "other with increasing j.",
     "Keywords that occur once per time step (" + M("TOP") + ", " + M("SED1") + ", …) are read by collecting "
     "every occurrence in the file, in order. Occurrence k becomes layer k.",
     M("INCLUDE") + " directives are not supported."])

H2("Numbers in output files")
P("Arrays are written in a fixed layout so that columns line up. If any value v in an array has |v| ≥ 100 or "
  "0 &lt; |v| ≤ 0.0001, all values are written as " + M("%13.4e") + ". Otherwise they are written as "
  + M("%9.4f") + ", or " + M("%10.4f") + " when some |v| ≥ 10. Zeros are written as " + M("0") + " in the "
  "same width. Single values are written as " + M("NAME = value") + " with six significant digits.")

# ======================================================================
CHAP("fitdepth")
P("fitdepth places a SedArch model at its present-day position. It moves and stretches the sequence so that it "
  "matches a given base, top or isopach, and can add an overburden above it. It also reports how much the "
  "thickness had to change, as a check on the model.", lead)
GLANCE([("Command", M("python3 -m sedCompanion fitdepth model.vvm surfaces1.vvm [surfaces2.vvm] result.vvm")),
        ("Reads", "A model, and two of PRESENT_BASE, PRESENT_TOP and PRESENT_ISOPACH."),
        ("Writes", "The model with new surfaces, and optionally an overburden layer.")])
FIGURE("fitdepth.png", "The example model before and after fitdepth, with PRESENT_TOP, PRESENT_ISOPACH and "
       "OVBD_TOP = 100 m. Colour: sand fraction.")

H2("Command line")
ARGS([[M("model.vvm"), "The model to adjust."],
      [M("surfaces1.vvm"), "Parameter file with one or both present-day surfaces, and optionally the "
                           "overburden value."],
      [M("surfaces2.vvm"), "Optional second parameter file, with a surface not given in the first."],
      [M("result.vvm"), "The adjusted model."]])

H2("Parameter files")
P("Together, the parameter files must give exactly two of the following surfaces. Each is a 2-D array with the "
  "same number of nodes as the model.")
TABLE([["Keyword", "Meaning"],
       ["PRESENT_BASE", "Present-day elevation of the base of the model (positive upward)."],
       ["PRESENT_TOP", "Present-day elevation of the top of the model."],
       ["PRESENT_ISOPACH", "Present-day thickness of the model."]], [1.6, 4.8])
P("The first parameter file can also give one of these single values:")
TABLE([["Keyword", "Meaning"],
       ["OVBD_TOP", "Elevation of the top of a flat overburden."],
       ["OVBD_THICK", "Thickness of an overburden above the new top of the model."]], [1.6, 4.8])
CODE("PRESENT_TOP =\n  -14.1  -15.3  -16.8 ...      ! one row of nodes per line\n  ...\n"
     "PRESENT_ISOPACH =\n  ...\nOVBD_TOP = 100")
NOTE("The help text printed by fitdepth names the overburden keyword OVB_LEVEL; the keyword read from the "
     "file is " + M("OVBD_TOP") + ". Giving both OVBD_TOP and OVBD_THICK is an error.")

H2("How it works")
P("Let TOP<sub>0</sub> … TOP<sub>n−1</sub> be the surfaces of the model, with TECTONICS added if present. "
  "fitdepth first finds the base B<sub>0</sub> and thickness T<sub>0</sub> of the model as it is:")
EQ("B<sub>0</sub> = TOP<sub>0</sub>,&nbsp;&nbsp;&nbsp; T<sub>0</sub> = max( 0, TOP<sub>n−1</sub> − B<sub>0</sub> )")
P("It then works out the new base B and the new thickness I from the surfaces given:")
TABLE([["Surfaces given", "New base B", "New thickness I"],
       ["PRESENT_TOP and PRESENT_ISOPACH", "TOP − ISOPACH", "ISOPACH"],
       ["PRESENT_TOP only", "TOP − T<sub>0</sub>", "T<sub>0</sub> (unchanged)"],
       ["PRESENT_ISOPACH only", "B<sub>0</sub> (unchanged)", "ISOPACH"],
       ["PRESENT_TOP and PRESENT_BASE", "BASE − TOP", "TOP"]], [2.5, 1.95, 1.95], mono=())
P("Every surface k = 1 … n−1 is moved by the change of base plus a share of the change of thickness that "
  "grows with k, and the basement is replaced by the new base:")
EQ("TOP′<sub>k</sub> = TOP<sub>k</sub> + ( B − B<sub>0</sub> ) + ( I − T<sub>0</sub> ) · k / (n − 1),"
   "&nbsp;&nbsp;&nbsp; TOP′<sub>0</sub> = B")
P("The result is a copy of the model with the new surfaces. TECTONICS is left out, because it is now included "
  "in the surfaces, and TIME and SEALEVEL are written as 0. If an overburden is requested, one more layer is "
  "added: its top is OVBD_TOP everywhere, or TOP′<sub>n−1</sub> + OVBD_THICK, and it contains equal fractions "
  "of every sediment type.")
NOTE("With PRESENT_TOP and PRESENT_BASE, fitdepth uses BASE − TOP as the new base and TOP as the thickness, "
     "which does not place the model between the two surfaces. To fit a model between a known top and base, "
     "give PRESENT_TOP and PRESENT_ISOPACH = TOP − BASE instead. PRESENT_BASE on its own is not enough. "
     "In the thickness T<sub>0</sub>, B<sub>0</sub> is also limited by the basement values at nodes 2 … n of "
     "the first row, which can make T<sub>0</sub> larger than the true thickness where the basement is high "
     "along that row.")

H2("Thickness check")
P("At the end of a run fitdepth prints two percentages, computed from d = I − T<sub>0</sub> at every node:")
B(["<b>Mean thickness error</b> = mean(d) / mean(I) × 100. A positive value means the model was thinner than "
   "the target.",
   "<b>Mean shape error</b> = standard deviation(d) / mean(I) × 100."])
P("Both are 0 when only the top or the base is changed. As a guide, the thickness error should stay below "
  "about 10 % and the shape error below about 20 %. Compaction can legitimately make the present-day "
  "thickness smaller than the deposited one, so the values should be judged against the aims of the study.")

# ======================================================================
CHAP("rockprops")
P("rockprops adds rock properties to a model: the preserved thickness of every layer, the water depth at "
  "deposition, the burial depth, porosity, and horizontal and vertical permeability. Run fitdepth first when "
  "the properties should reflect present-day burial, including an overburden.", lead)
GLANCE([("Command", M("python3 -m sedCompanion rockprops model.vvm parameters.vvmp result.vvm")),
        ("Reads", "A model, and porosity and permeability parameters for each sediment type."),
        ("Writes", "The model followed by END_THICK, DEPO_LEVEL, BURIAL, POR, PERMH and PERMV for every "
                   "time step.")])
FIGURE("rockprops.png", "Porosity and horizontal permeability of the example model, and the compaction curves "
       "of the four pure sediments defined in the example parameter file.")

H2("Command line")
ARGS([[M("model.vvm"), "The model, usually after fitdepth."],
      [M("parameters.vvmp"), "Porosity and permeability parameters."],
      [M("result.vvm"), "A copy of the model with the new properties added."]])

H2("Parameter file")
P("For each sediment type n, starting with 1, the file gives five values for the <i>pure</i> sediment:")
TABLE([["Keyword", "Meaning"],
       ["PORn_0", "Porosity (fraction) at deposition."],
       ["PORn_1000", "Porosity at 1000 m burial. Must be smaller than PORn_0."],
       ["PERMn_0", "Horizontal permeability (mD) at deposition."],
       ["PERMn_1000", "Horizontal permeability at 1000 m burial. Must be smaller than PERMn_0."],
       ["PERMRATIOn", "Ratio of horizontal to vertical permeability."]], [1.4, 5.0])
CODE("POR1_0 = 0.40      ! coarse sand: porosity at deposition\n"
     "POR1_1000 = 0.35   !              porosity at 1000 m\n"
     "PERM1_0 = 1000     !              permeability (mD) at deposition\n"
     "PERM1_1000 = 900   !              permeability (mD) at 1000 m\n"
     "PERMRATIO1 = 1     !              horizontal / vertical\n"
     "POR2_0 = 0.30\n...")
NOTE("The file is read from top to bottom: the five keywords must appear in the order shown, sediment 1 "
     "first, then sediment 2, and so on. The first missing keyword ends the list. The number of sediment types "
     "should match the model; a difference is reported, and processing continues.")

H2("Thickness, depth and burial")
P("For every node and time step k, with f<sub>i</sub> the fraction of sediment i:")
B(["<b>END_THICK</b> = thick<sub>k</sub>, the preserved thickness of the layer.",
   "<b>DEPO_LEVEL</b> = SEALEVEL<sub>k</sub> − TOP<sub>k</sub> (minus TECTONICS<sub>k</sub> if present): the "
   "water depth at deposition, positive below sea level.",
   "<b>BURIAL</b> = ½ thick<sub>k</sub> + Σ<sub>m&gt;k</sub> thick<sub>m</sub>: the thickness of sediment above "
   "the middle of the layer, including any overburden. It is 0 for the basement."])

H2("Porosity")
P("The porosity of a mixture at deposition is found by filling the pores of coarser grains with finer ones. "
  "Starting with the coarsest fraction, whose pore volume is V = f<sub>1</sub>p<sub>1</sub> / (1 − "
  "p<sub>1</sub>), each finer fraction f with pure porosity p and diameter d is added in turn:")
NUM(["The space it can fill is A = ½ ( V − V · d / d<sub>prev</sub> ), where d<sub>prev</sub> is the diameter "
     "of the previous fraction. Its own volume is f plus its pores, V<sub>n</sub> = f p / (1 − p).",
     "If f + V<sub>n</sub> ≤ A, it fits in the pores: V becomes V − f.",
     "Otherwise, with r = ( f + V<sub>n</sub> − A ) / ( f + V<sub>n</sub> ), V becomes "
     "V − (1 − r) f + r V<sub>n</sub>."])
P("The porosity at deposition is φ<sub>0</sub> = V / (1 + V). It then decreases exponentially with burial:")
EQ("φ = φ<sub>0</sub> · exp( −1.67 · 9.81 · BURIAL / L ),&nbsp;&nbsp;&nbsp; L = Σ f<sub>i</sub> L<sub>i</sub>")
EQ("L<sub>i</sub> = 1.67 · 9.81 · 1000 / ln( PORi_0 / PORi_1000 )")
P("so that a pure sediment buried 1000 m deep has porosity PORi_1000.")
NOTE("The fractions are taken coarsest first, but the selection restarts from the whole list at every step. "
     "With SED_DIAMETERS = 20, 10, 5, 1 the order used is 10, 5, 20, 1.")

H2("Permeability")
P("Horizontal permeability follows a power law of porosity through two points of the mixture, at deposition "
  "and at 1000 m. The mixture values are weighted by fraction:")
EQ("p<sub>0</sub> = Σ f<sub>i</sub> PORi_0,&nbsp; p<sub>1</sub> = Σ f<sub>i</sub> PORi_1000,&nbsp; "
   "k<sub>0</sub> = Σ f<sub>i</sub> PERMi_0,&nbsp; k<sub>1</sub> = Σ f<sub>i</sub> PERMi_1000,&nbsp; "
   "d = Σ f<sub>i</sub> d<sub>i</sub>")
EQ("x = ln( k<sub>0</sub> / k<sub>1</sub> ) / ln( p<sub>0</sub> / p<sub>1</sub> ),&nbsp;&nbsp;&nbsp; "
   "C = k<sub>0</sub> / ( p<sub>0</sub><super>x</super> d<super>2</super> ),&nbsp;&nbsp;&nbsp; "
   "PERMH = C φ<super>x</super>")
P("PERMH is 0 if any of p<sub>0</sub>, p<sub>1</sub>, k<sub>0</sub>, k<sub>1</sub> and d is zero or negative, "
  "or if p<sub>0</sub> = p<sub>1</sub>. Vertical permeability uses the same law with harmonic averages:")
EQ("k<sub>0</sub>′ = 1 / Σ ( f<sub>i</sub> / PERMi_0 ),&nbsp;&nbsp;&nbsp; "
   "k<sub>1</sub>′ = 1 / Σ ( f<sub>i</sub> PERMRATIOi / PERMi_0 ),&nbsp;&nbsp;&nbsp; PERMV = C′ φ<super>x′</super>")
P("where C′ and x′ come from the points (p<sub>0</sub>, k<sub>0</sub>′) and (p<sub>1</sub>, k<sub>1</sub>′). "
  "A sediment present with zero permeability makes PERMV 0. The law has the form proposed by Wyllie and Rose, "
  "without the irreducible water saturation term. Because all parameters describe pure sediments, mixtures "
  "come out with lower porosity and permeability than their components.")
NOTE("The constant C is divided by the square of the mean grain diameter d, in the units of SED_DIAMETERS, so "
     "a pure sediment at deposition gets PERM0 / d<super>2</super> rather than PERM0. For PERMV, the second "
     "point uses PERM0 / PERMRATIO.")

# ======================================================================
CHAP("wells")
P("{wells} extracts synthetic vertical wells from a model. For each well location it lists, for every time "
  "step, the elevation of the surface and the value of every property. Use a model processed by fitdepth to get "
  "present-day depths.", lead)
GLANCE([("Command", M("python3 -m sedCompanion wells model.vvm wells.vvmp result.xyz")),
        ("Reads", "A model, and a list of well coordinates."),
        ("Writes", "One text file containing all the wells.")])
FIGURE("wells.png", "The two wells of the example in map view (left) and the sediment fractions found in "
       "each well, layer by layer (right).")

H2("Command line")
ARGS([[M("model.vvm"), "The model. The grid position (CELLSIDE, XORIGIN, YORIGIN, ROTATION) is read from "
                       "this file; missing values default to 1, 0, 0 and 0."],
      [M("wells.vvmp"), "Parameter file with the well coordinates."],
      [M("result.xyz"), "The output file."]])

H2("Parameter file")
P("The file contains " + M("XYWELLS") + ": the X and Y map coordinates of one well per line. A single well "
  "can also be given as two numbers on the keyword line.")
CODE("XYWELLS =\n3159  4661\n4989  3096")

H2("How it works")
P("Each well is converted to grid units and moved to the nearest node:")
EQ("u = ( X − XORIGIN ) / CELLSIDE,&nbsp;&nbsp; v = ( Y − YORIGIN ) / CELLSIDE,&nbsp;&nbsp; a = ROTATION")
EQ("i = round( u cos a − v sin a ),&nbsp;&nbsp;&nbsp; j = round( v cos a + u sin a )")
P("A well outside the grid is skipped with a warning. If TECTONICS is present it is added to TOP. For every "
  "time step, one line is written with the elevation of that step’s surface at node (i, j) and the values "
  "there of every property that has one value per node.")
NOTE("Values are taken at the nearest node, without interpolation. When a well is skipped, the X and Y written "
     "for the wells after it are shifted by one entry; remove wells outside the grid from XYWELLS before "
     "running.")

H2("Output file")
P("The file starts with an EarthVision-style header (" + M("# Type: scattered data") + ", one "
  + M("# Field:") + " line per column, the grid size, and so on). Each data line holds X and Y (1 decimal), "
  "Z (3 decimals) and the property values (3 decimals), in columns 10 characters wide. Wells are separated by "
  "a blank line.")
CODE("    3159.0         4661.0   -33.167     0.250     0.250     0.250     0.250\n"
     "    3159.0         4661.0   -35.679     0.366     0.634     0.000     0.000\n"
     "    ...")

# ======================================================================
CHAP("crop")
P("crop cuts a smaller model out of a larger one: a rectangle of nodes and, optionally, a range of "
  "layers. Use it to trim the edges of a model or to work on the part that matters.", lead)
GLANCE([("Command", M("python3 -m sedCompanion crop model.vvm result.vvm [xmin xmax ymin ymax [zmin zmax]]")),
        ("Reads", "A model."),
        ("Writes", "A model of the same form, cropped.")])
FIGURE("crop.png", "Extracting nodes 10–30 in both directions from the example model. Right: a section "
       "through the extracted model; node numbers start again from 0.")

H2("Command line")
ARGS([[M("model.vvm"), "The model."],
      [M("result.vvm"), "The extracted model."],
      [M("xmin xmax ymin ymax"), "Optional. First and last node, counted from 0, along i and along j. Values "
                                 "beyond the grid are moved to its edge. Without them, the whole area is kept."],
      [M("zmin zmax"), "Optional, only together with the four previous values. First and last time step to "
                       "keep."]])
P("Each range must contain at least two nodes or steps after it has been fitted to the grid.")

H2("How it works")
P("The model is copied record by record. TITLE and single values are copied as they are. Every array with one "
  "value per node is cut to the rectangle. If TECTONICS is present, its last array is added to every TOP and "
  "TECTONICS itself is left out. Records are counted by time step and written while the step is within "
  "zmin … zmax. TOP is written as stored, without the erosion correction.")
NOTE("The last time step of the range is not written. With the default range, the extracted model therefore "
     "has one step fewer than the input (10 of 11 in the example). Setting zmin above 0 misaligns TOP with the "
     "other properties; keep zmin at 0.")

# ======================================================================
CHAP("avgmaps")
P("avgmaps computes thickness-weighted vertical averages of every property over a range of layers. The result "
  "is a set of maps: the total thickness of the range, and the average of each property.", lead)
GLANCE([("Command", M("python3 -m sedCompanion avgmaps model.vvm result.vvm [m n]")),
        ("Reads", "A model."),
        ("Writes", "THICKNESS and one NAME_AVG map per property.")])
FIGURE("avgmaps.png", "Averaging layers 2 to 8 of the example model. Top: the selected layers. Bottom: the "
       "average sediment fractions (stacked) and the thickness of the interval along the section.")

H2("Command line")
ARGS([[M("model.vvm"), "The model."],
      [M("result.vvm"), "The output file."],
      [M("m n"), "Optional. First and last layer to include, 1 ≤ m ≤ n. The basement (layer 0) is never "
                 "included, and n is limited to the last layer. Without them, all layers are averaged."]])

H2("How it works")
P("For every node, with thick<sub>k</sub> the preserved thickness of layer k and P<sub>k</sub> the value of a "
  "property in it:")
EQ("THICKNESS = Σ<sub>k=m…n</sub> thick<sub>k</sub>,&nbsp;&nbsp;&nbsp;&nbsp; "
   "NAME_AVG = Σ<sub>k=m…n</sub> P<sub>k</sub> thick<sub>k</sub> / THICKNESS")
P("NAME_AVG is 0 where THICKNESS ≤ 0.001. Every property that occurs once per time step with one value per "
  "node is averaged, except TOP and TECTONICS.")
NOTE("All properties, permeability included, are averaged arithmetically. For flow across layers, a harmonic "
     "average of PERMV would be more appropriate and has to be computed separately.")

# ======================================================================
CHAP("regrid")
P("regrid resamples one property of a model onto a regular 3-D grid of equal box-shaped cells. SedArch "
  "layers vary in thickness and can be cut by erosion; geostatistical, image-analysis and flow programs "
  "usually need a regular grid instead.", lead)
GLANCE([("Command", M("python3 -m sedCompanion regrid model.vvm parameters.vvmp result.txt")),
        ("Reads", "A model, and the grid parameters."),
        ("Writes", "A plain, vvm or GSLIB grid file.")])
FIGURE("regrid_result.png", "SED2 of the example model on the SedArch layers (top) and after regridding "
       "with 10 m cells (bottom). Cells above the model surface get the empty value and are left blank.")

H2("Command line")
ARGS([[M("model.vvm"), "The model. It must contain TOP and the property to resample."],
      [M("parameters.vvmp"), "Parameter file (required)."],
      [M("result.txt"), "The output grid."]])

H2("Parameter file")
TABLE([["Keyword", "Meaning", "Default"],
       ["PROPERTY", "Name of the property to resample, for example " + M('"SED2"') + ".", "required"],
       ["MULTIPLICITY", "Whole number m ≥ 1: number of new node intervals per original interval.", "required"],
       ["HORIZONTALIZE", "0: keep the basement as it is. Any other value: flatten the basement.", "required"],
       ["CELLTHICK", "Thickness of the output cells, in the units of TOP. Must be greater than 0.", "required"],
       ["EMPTYVALUE", "Value written for cells above the top of the model.", "−999"],
       ["HEADERS", "Output layout: 0 plain grid, 1 vvm, 2 GSLIB.", "required"]],
      [1.35, 4.15, 0.9])
CODE('PROPERTY = "SED2"   ! property to resample\n'
     "MULTIPLICITY = 1    ! original node spacing / new node spacing\n"
     "HORIZONTALIZE = 0   ! 0: no, 1: yes\n"
     "CELLTHICK = 10      ! cell thickness (m)\n"
     "EMPTYVALUE = -1     ! value above the model\n"
     "HEADERS = 2         ! 0: plain, 1: vvm, 2: GSLIB")
FIGURE("regrid_concepts.png", "(a) MULTIPLICITY refines the grid in plan view: with nx × ny original nodes "
       "the output has ((nx−1)m+1) × ((ny−1)m+1) nodes. (b) HORIZONTALIZE flattens the basement, so that a "
       "thin tilted sequence does not fill only a small part of the regular grid.")

H2("How it works")
NUM(["If TECTONICS is present, its last array is added to every TOP.",
     "If HORIZONTALIZE is set, the basement is subtracted from every surface, so that it becomes the plane 0.",
     "The grid spans zmin = min(TOP) to zmax = max(TOP) over all surfaces, in nl = round((zmax − zmin) / "
     "CELLTHICK) layers (at least 1).",
     "At each output node and each cell centre z<sub>c</sub> = zmin + (iz + ½) · CELLTHICK, the program "
     "searches down from the top for the layer k whose base lies below z<sub>c</sub>, and writes the value "
     "of the property in that layer. Above the model surface it writes EMPTYVALUE; below the base of layer 1 "
     "it writes the basement value.",
     "Surfaces and property values between original nodes are found by bilinear interpolation. Each value "
     "is taken at a point; there is no averaging over the cell."])

H2("Output file")
TABLE([["HEADERS", "Layout"],
       ["0", "The layers from bottom to top, each a block of lines (one line per row of nodes), separated by "
             "blank lines."],
       ["1", "A line " + M("NAME =") + " followed by the same blocks, so the file can be read as a vvm file."],
       ["2", "GSLIB: the lines " + M('"TITLE"') + ", " + M('"1"') + " and the property name, then one value "
             "per line, with i varying fastest, then j, then the layer from the bottom up."]],
      [0.9, 5.5])

# ======================================================================
CHAP("gpmexport")
P("gpmexport converts a model to an HDF5 file in the layout used by Petrel-GPM 2.0.0.0, so it can be imported into "
  "software that reads that format. Besides the model itself, it computes erosion, depth of deposition and "
  "surface slopes for every time step.", lead)
GLANCE([("Command", M("python3 -m sedCompanion gpmexport model.vvm result.hdf5")),
        ("Reads", "A model with TOP, TIME, SEALEVEL, CELLSIDE and SED_DIAMETERS."),
        ("Writes", "An HDF5 file. Requires the h5py package.")])
FIGURE("gpmexport.png", "What gpmexport reads and writes. Shaded properties are computed by gpmexport.")

H2("Command line")
ARGS([[M("model.vvm"), "The model."],
      [M("result.hdf5"), "The HDF5 file."]])
P("If the model has no property called TOP, gpmexport asks for the name of the surface property, or 0 to stop.")

H2("Properties written")
P("Every time step t = 0 … n−1 of the model becomes one time step in the file. Each property is stored as 2-D "
  "grids with one row per row of nodes. The same 15 properties are always written, in this order:")
TABLE([["Property", "Grid written for time step t"],
       ["TOP", "One grid per surface j = 0 … t: the surface as it existed at time t, min(TOP<sub>j</sub>, …, "
               "TOP<sub>t</sub>)."],
       ["SED1 … SED4", "Fractions of layer t. A missing SEDn is written as zeros."],
       ["ERODABILITY1 … 4", "Copied from the model if present, otherwise 1."],
       ["SEALEVEL", "No grid; the value for step t is stored in the property’s constants table."],
       ["EROSION", "min(0, TOP<sub>t</sub> − TOP<sub>t−1</sub>) for t ≥ 1: the amount eroded in step t, as a "
                   "negative number."],
       ["DEPODEPTH", "TOP<sub>t</sub> − SEALEVEL<sub>t</sub>, positive above sea level."],
       ["TOP_SLOPE_X", "−(TOP<sub>t</sub>[i+1] − TOP<sub>t</sub>[i−1]) / (2 CELLSIDE) along a row. At the edges "
                       "the missing neighbour is replaced by the node itself."],
       ["TOP_SLOPE_Y", "The same between rows."],
       ["TOP_SLOPE_MAG", "√( TOP_SLOPE_X<super>2</super> + TOP_SLOPE_Y<super>2</super> )."]],
      [1.5, 4.9])
P("A property called EROSION, DEPODEPTH or TOP_SLOPE_… that already exists in the model is copied instead of "
  "computed. Other properties, such as POR or PERMH, are not converted.")

H2("Other contents")
B(["<b>File attributes</b>: BASE_ERODABILITY = 1, NODORDER = 0, NUMROWS and NUMCOLS, VERSION = “2.0.0.0”, "
   "ZNULL = −1e12.",
   "<b>Times</b>: AGESET and TIMESET = TIME × 1000.",
   "<b>Sediments</b>: SED_DIAMETER = SED_DIAMETERS / 1000, padded to four types; the sediment table names them "
   "“Sand (coarse)”, “Sand (fine)”, “Silt” and “Clay”.",
   "<b>Corners</b>: XCORNERS and YCORNERS give the four corners of the grid with node (0, 0) at (0, 0).",
   "<b>Ranges</b>: STATREF tables give the minimum and maximum of every property at every step."])
NOTE("The grid is always placed with node (0, 0) at the coordinates (0, 0): XORIGIN, YORIGIN and ROTATION are "
     "not used. Only four sediment types are written.")
P("For viewing alone, SedArchView displays vvm files directly and shows details that the HDF5 layout cannot "
  "hold, such as local erosional features; the conversion is mainly useful to combine the model with other "
  "data. Petrel and GPM are trademarks of SLB.", small)

# ======================================================================
CHAP("mcstats")
P("mcstats combines many runs of a model into a statistics model holding the mean and standard deviation of "
  "every property at every node and time step. It is meant for Monte Carlo studies, where SedArch is run many "
  "times with varied input.", lead)
GLANCE([("Command", M("python3 -m sedCompanion mcstats stats.vvm run1.vvm [run2.vvm ...]")),
        ("Reads", "One or more models with the same dimensions and properties."),
        ("Writes", "A statistics model, created or updated.")])
FIGURE("mcstats.png", "mcstats merges each run into the statistics file, so runs can be added at any time.",
       w=5.6)

H2("Command line")
ARGS([[M("stats.vvm"), "The statistics file. If it exists, the new runs are merged into it; delete it to "
                       "start again."],
      [M("run*.vvm"), "One or more models, listed or given with a wildcard such as " + M("run_*.vvm") + "."]])
NOTE("Each model file name must begin with a letter or a digit, so names such as " + M("./run1.vvm") + " or "
     "absolute paths are rejected; run mcstats from the folder that holds the runs or a folder above it. "
     "A model file must not have the same name as the statistics file.")

H2("How it works")
P("Each model counts as N runs, where N is its N_REALIZATIONS value, or 1 with all standard deviations 0 if it "
  "has none. The first model becomes the statistics file. Every further model (n<sub>2</sub> runs, mean "
  "m<sub>2</sub>, standard deviation s<sub>2</sub>) is merged into the file (n<sub>1</sub>, m<sub>1</sub>, "
  "s<sub>1</sub>) at every node:")
EQ("m = ( n<sub>1</sub>m<sub>1</sub> + n<sub>2</sub>m<sub>2</sub> ) / ( n<sub>1</sub> + n<sub>2</sub> )")
EQ("s<super>2</super> = [ (n<sub>1</sub>−1) s<sub>1</sub><super>2</super> + n<sub>1</sub>m<sub>1</sub><super>2</super>"
   " + (n<sub>2</sub>−1) s<sub>2</sub><super>2</super> + n<sub>2</sub>m<sub>2</sub><super>2</super>"
   " − (n<sub>1</sub>+n<sub>2</sub>) m<super>2</super> ] / ( n<sub>1</sub> + n<sub>2</sub> − 1 )")
P("This gives exactly the sample mean and standard deviation of all runs, whatever the order in which they "
  "are added.")

H2("Output file")
P("Statistics are computed for SED_DIAMETERS, TIME, SEALEVEL, TOP, SED1 … SED9, TECTONICS, DEPO_LEVEL, POR, "
  "PERMH and PERMV, where present. Means keep the property name; standard deviations get the suffix "
  + M("_STDV") + ", as in " + M("SED2_STDV") + ". The file also holds " + M("N_REALIZATIONS") + ". TITLE, "
  "CELLSIDE, XORIGIN, YORIGIN and ROTATION are not written.")
NOTE("PERMH and PERMV are averaged geometrically, but every value is first limited to at most 1e-10, so their "
     "means come out as 1e-10 and their standard deviations as 1: do not use these two results. BURIAL and "
     "END_THICK from rockprops are not included.")

# ======================================================================
CHAP("Reference", appendix="")
H2("Commands")
P("All commands start with " + M("python3 -m sedCompanion") + " (add " + M("--lf") + " before the tool name for "
  "Unix line endings). Square brackets mark optional arguments.")
TABLE([["Tool", "Arguments"],
       ["fitdepth", "model.vvm surfaces1.vvm [surfaces2.vvm] result.vvm"],
       ["rockprops", "model.vvm parameters.vvmp result.vvm"],
       ["wells", "model.vvm wells.vvmp result.xyz"],
       ["crop", "model.vvm result.vvm [xmin xmax ymin ymax [zmin zmax]]"],
       ["avgmaps", "model.vvm result.vvm [m n]"],
       ["regrid", "model.vvm parameters.vvmp result.txt"],
       ["gpmexport", "model.vvm result.hdf5"],
       ["mcstats", "stats.vvm run1.vvm [run2.vvm ...]"]],
      [1.1, 5.3], mono=(0, 1))

H2("Parameter-file keywords")
TABLE([["Keyword", "Tool", "Meaning"],
       ["PRESENT_BASE", "fitdepth", "Present-day base of the model (2-D)."],
       ["PRESENT_TOP", "fitdepth", "Present-day top of the model (2-D)."],
       ["PRESENT_ISOPACH", "fitdepth", "Present-day thickness of the model (2-D)."],
       ["OVBD_TOP", "fitdepth", "Elevation of a flat overburden top."],
       ["OVBD_THICK", "fitdepth", "Thickness of overburden above the model."],
       ["PORn_0, PORn_1000", "rockprops", "Porosity of sediment n at 0 and 1000 m burial."],
       ["PERMn_0, PERMn_1000", "rockprops", "Horizontal permeability (mD) at 0 and 1000 m."],
       ["PERMRATIOn", "rockprops", "Horizontal / vertical permeability."],
       ["XYWELLS", "{wells}", "Well coordinates, one X Y pair per line."],
       ["PROPERTY", "regrid", "Property to resample."],
       ["MULTIPLICITY", "regrid", "Refinement of the node spacing."],
       ["HORIZONTALIZE", "regrid", "Flatten the basement (non-zero) or not (0)."],
       ["CELLTHICK", "regrid", "Output cell thickness."],
       ["EMPTYVALUE", "regrid", "Value above the model (default −999)."],
       ["HEADERS", "regrid", "0 plain, 1 vvm, 2 GSLIB."]],
      [1.75, 0.95, 3.7])
H2("Properties added to models")
TABLE([["Keyword", "Tool", "Meaning"],
       ["END_THICK", "rockprops", "Preserved thickness of the layer."],
       ["DEPO_LEVEL", "rockprops", "Water depth at deposition (positive below sea level)."],
       ["BURIAL", "rockprops", "Sediment thickness above the middle of the layer."],
       ["POR", "rockprops", "Porosity (fraction)."],
       ["PERMH, PERMV", "rockprops", "Horizontal and vertical permeability (mD)."],
       ["THICKNESS", "avgmaps", "Thickness of the averaged interval."],
       ["NAME_AVG", "avgmaps", "Thickness-weighted average of property NAME."],
       ["NAME_STDV", "mcstats", "Standard deviation of property NAME."],
       ["N_REALIZATIONS", "mcstats", "Number of runs combined."]],
      [1.75, 0.95, 3.7])


# ======================================================================
def cover_page(canv, doc):
    canv.saveState()
    canv.setFillColor(ACCENT)
    canv.rect(0, letter[1] - 0.32 * inch, letter[0], 0.32 * inch, stroke=0, fill=1)
    canv.restoreState()


def body_page(canv, doc):
    canv.saveState()
    w, h = letter
    canv.setStrokeColor(RULE)
    canv.setLineWidth(0.5)
    canv.line(doc.leftMargin, h - 0.62 * inch, w - doc.rightMargin, h - 0.62 * inch)
    canv.setFont("Sans-Demi", 7.8)
    canv.setFillColor(ACCENT)
    canv.drawString(doc.leftMargin, h - 0.55 * inch, "SEDCOMPANION USER GUIDE")
    canv.setFont("Sans", 7.8)
    canv.setFillColor(MUTED)
    canv.drawRightString(w - doc.rightMargin, h - 0.55 * inch, Doc.chapter_title)
    canv.setFont("Sans-Medium", 8.5)
    canv.setFillColor(INK)
    canv.drawRightString(w - doc.rightMargin, 0.55 * inch, str(doc.page))
    canv.restoreState()


doc = Doc(OUT, pagesize=letter, leftMargin=1.05 * inch, rightMargin=1.05 * inch,
          topMargin=0.95 * inch, bottomMargin=0.9 * inch,
          title="SedCompanion User Guide", author="SedCompanion",
          subject="Companion tools for SedArch models")
frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f", leftPadding=0, rightPadding=0)
doc.addPageTemplates([PageTemplate(id="cover", frames=[frame], onPage=cover_page),
                      PageTemplate(id="body", frames=[frame], onPageEnd=body_page)])
doc.multiBuild(S)
print("written", os.path.abspath(OUT))
