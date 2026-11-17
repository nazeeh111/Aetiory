"""Aetiory CLI."""
import argparse
import json
import sys
from . import engine, __version__


def main():
    if sys.argv[1:] == ["--version"]:
        print(__version__)
        return 0
    if not sys.argv[1:] or sys.argv[1:] in (["--help"], ["-h"]):
        parser = argparse.ArgumentParser(description="Choose an output. Test upstream returns in paired live Python execution.")
        parser.add_argument("--version", action="version", version=__version__)
        sub = parser.add_subparsers(dest="command")
        for name, help_text in (("diagnose", "Find a return that changes a failure into a requested successful outcome"),
                                ("observe", "Pin sources and require plain/instrumented byte parity"),
                                ("search", "Find a return that changes a stable selected output"),
                                ("replay", "Repeat a pinned paired intervention and fresh undo"),
                                ("export", "Export retained evidence to portable HTML and JSON"),
                                ("mcp", "Expose trusted local tools over MCP stdio")):
            sub.add_parser(name, help=help_text)
        parser.print_help()
        return 0
    if sys.argv[1:2] == ["diagnose"]:
        from .diagnose import main as diagnose
        return diagnose(sys.argv[2:])
    if sys.argv[1:2] == ["mcp"]:
        from .mcp import main as mcp
        return mcp(sys.argv[2:])
    if sys.argv[1:2] == ["export"]:
        from .export import experiment, export_record, export_partial, read_report
        parser = argparse.ArgumentParser(prog=f"{argparse.ArgumentParser().prog} export", description="Export confirmed evidence to HTML and JSON, or unresolved evidence to investigation.json.")
        parser.add_argument("--observation", required=True)
        parser.add_argument("--search", required=True)
        parser.add_argument("--out", required=True)
        parser.add_argument("--replay", help="Optional retained fresh intervention replay receipt")
        parser.add_argument("--title", default="A paired return experiment")
        args = parser.parse_args(sys.argv[2:])
        report = read_report(args.search)
        if report.get("status") == "unresolved":
            if args.replay is not None:
                raise engine.Refusal("Unresolved search cannot include a confirmed replay")
            result = export_partial(args.observation, args.search, args.title, args.out)
        else:
            result = export_record({"schema": "experiment-view/1", "experiments": [experiment(args.observation, args.search, args.title, args.replay)]}, args.out)
        print(json.dumps(result))
        return 0
    if sys.argv[1:2] not in (["observe"], ["search"], ["replay"], ["_worker"]):
        parser = argparse.ArgumentParser(description="Test a different return in a trusted Python run.")
        parser.add_argument("command", choices=("diagnose", "observe", "search", "replay", "export", "mcp"))
        parser.parse_args(sys.argv[1:2])
    return engine.main()


def cli():
    """Apply the same refusal contract to module and installed entry points."""
    try:
        return main()
    except (engine.Refusal, OSError, ValueError, KeyError, TypeError, RecursionError) as error:
        print(json.dumps({"status": "refused", "error": type(error).__name__, "message": str(error)[:1000]}))
        return 3


if __name__ == "__main__":
    raise SystemExit(cli())
