"""
SedCompanion - companion tools for SedArch models.

Command-line dispatcher:

    python -m sedCompanion <tool> [args...]     tool = fitdepth | rockprops | wells |
                                                     crop | avgmaps | regrid |
                                                     gpmexport | mcstats
    python -m sedCompanion --lf <tool> ...      write LF instead of CRLF line ends
"""
import sys

from . import vvm
from . import fitdepth, rockprops, wells, crop, avgmaps, regrid, gpmexport, mcstats

TOOLS = {
    "fitdepth": fitdepth.main, "rockprops": rockprops.main, "wells": wells.main,
    "crop": crop.main, "avgmaps": avgmaps.main, "regrid": regrid.main,
    "gpmexport": gpmexport.main, "mcstats": mcstats.main,
}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--lf":
        vvm.set_newline("\n")
        argv = argv[1:]
    if not argv or argv[0] not in TOOLS:
        print(__doc__)
        return 1
    tool = argv[0]
    return TOOLS[tool]([tool] + argv[1:])


if __name__ == "__main__":
    sys.exit(main())
