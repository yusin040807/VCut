from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .exceptions import VCutError
from .media_probe import dependency_status
from .models import Project
from .project_service import ProjectService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vcut", description="VCut local multi-camera video assistant")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check-system", help="Check Python and media dependencies")
    create = commands.add_parser("create-project", help="Create a local project")
    create.add_argument("path", type=Path)
    create.add_argument("--name", required=True)
    create.add_argument("--authorized", action="store_true")
    show = commands.add_parser("show-project", help="Print project settings")
    show.add_argument("path", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "check-system":
            status = dependency_status()
            tk_ok, tk_message = _tk_status()
            print(f"Python: {sys.version.split()[0]} (OK)")
            print(f"Tkinter: {tk_message}")
            print(f"FFmpeg: {status['ffmpeg'] or 'NOT FOUND - rendering unavailable'}")
            print(f"ffprobe: {status['ffprobe'] or 'NOT FOUND - camera inspection unavailable'}")
            return 0 if tk_ok and status["ffmpeg"] and status["ffprobe"] else 2
        service = ProjectService()
        if args.command == "create-project":
            service.create_project(args.path, Project(args.name, consent_confirmed=args.authorized))
            print(f"Created VCut project: {args.path.resolve()}")
        elif args.command == "show-project":
            print(json.dumps(service.load_project(args.path).__dict__, default=lambda value: value.__dict__, indent=2))
        return 0
    except VCutError as exc:
        print(f"VCut: {exc}", file=sys.stderr)
        return 1


def _tk_status() -> tuple[bool, str]:
    try:
        import tkinter
    except ImportError as exc:
        return False, f"UNAVAILABLE - desktop interface cannot import ({exc})"
    try:
        root = tkinter.Tk()
        root.withdraw()
        root.update_idletasks()
        root.destroy()
        return True, f"{tkinter.TkVersion} (OK)"
    except tkinter.TclError as exc:
        detail = str(exc).splitlines()[0]
        return False, f"UNAVAILABLE - desktop interface cannot open ({detail})"


if __name__ == "__main__":
    raise SystemExit(main())
