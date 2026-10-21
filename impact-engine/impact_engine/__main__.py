"""Run the engine on the team's demo data:

    python -m impact_engine [--scenario NAME] [--json | --contract]
"""
from __future__ import annotations

import argparse
import json

from .analyzer import analyze_impact
from .report import format_report
from .scenarios import SCENARIOS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m impact_engine", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="main")
    parser.add_argument("--json", action="store_true", help="full ImpactResult JSON (with extension fields)")
    parser.add_argument("--contract", action="store_true", help="JSON containing only contract v0.1 fields")
    args = parser.parse_args(argv)

    snapshot, incident = SCENARIOS[args.scenario]()
    result = analyze_impact(incident, snapshot)
    if args.contract:
        print(json.dumps(result.to_contract(), indent=2))
    elif args.json:
        print(result.model_dump_json(indent=2))
    else:
        print(format_report(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
