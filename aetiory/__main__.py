"""Aetiory CLI."""
import argparse
import json
import sys
from . import engine


def main():
    if not sys.argv[1:] or sys.argv[1:] in (["--help"], ["-h"]):
        parser = argparse.ArgumentParser(description="Choose an output. Test upstream returns in paired live Python execution.")
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
        from .export import experiment, export_record
        parser = argparse.ArgumentParser(description="Export retained confirmed evidence to one portable HTML viewer and JSON")
        parser.add_argument("--observation", required=True)
        parser.add_argument("--search", required=True)
        parser.add_argument("--out", required=True)
        parser.add_argument("--replay", help="Optional retained fresh intervention replay receipt")
        parser.add_argument("--title", default="A paired return experiment")
        args = parser.parse_args(sys.argv[2:])
        result = export_record({"schema": "experiment-view/1", "experiments": [experiment(args.observation, args.search, args.title, args.replay)]}, args.out)
        print(json.dumps(result))
        return 0
    return engine.main()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (engine.Refusal, OSError, ValueError, KeyError, TypeError, RecursionError) as error:
        print(json.dumps({"status": "refused", "error": type(error).__name__, "message": str(error)[:1000]}))
        raise SystemExit(3)
