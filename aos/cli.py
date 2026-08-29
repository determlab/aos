"""``aos`` — run a processor, list what exists, show a run record.

The trigger runner stays plain cron (spec §7): this command is what the crontab
line calls. It exits non-zero on a denial or a failure so a scheduler notices,
and prints where the record landed either way.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

from aos.engine import run
from aos.store import REPO_ROOT, Store

EXIT_OK, EXIT_DENIED, EXIT_FAILED = 0, 2, 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aos", description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT,
                        help="estate root holding processors/ grants/ runs/")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="run one processor once")
    p_run.add_argument("processor")
    p_run.add_argument("--date", type=date.fromisoformat, default=None,
                       help="ISO run date (default: today, UTC). The blueprint "
                            "takes this as an input, so a past date replays.")
    p_run.add_argument("--lab", default=None, help="topology override")
    p_run.add_argument("-v", "--verbose", action="store_true")

    sub.add_parser("processors", help="list processors")
    sub.add_parser("grants", help="list grants")

    p_record = sub.add_parser("record", help="print a run record")
    p_record.add_argument("run_id")

    args = parser.parse_args(argv)
    store = Store(root=args.root)

    if args.command == "processors":
        return _list(store.processors, "processor")
    if args.command == "grants":
        return _list(store.grants, "grant")
    if args.command == "record":
        path = store.runs / f"{args.run_id}.yaml"
        if not path.exists():
            print(f"no run record at {path}", file=sys.stderr)
            return EXIT_FAILED
        print(path.read_text(encoding="utf-8"), end="")
        return EXIT_OK

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING,
                        format="%(name)s %(message)s")
    record = run(args.processor, root=args.root, lab=args.lab, on_date=args.date)
    print(f"[{record.status}] {record.run} -> "
          f"{store.runs / (record.run + '.yaml')}", file=sys.stderr)
    if record.error:
        print(record.error, file=sys.stderr)
    return {"success": EXIT_OK, "denied": EXIT_DENIED}.get(record.status, EXIT_FAILED)


def _list(directory: Path, what: str) -> int:
    paths = sorted(directory.glob("*.yaml"))
    if not paths:
        print(f"no {what}s in {directory}", file=sys.stderr)
    for path in paths:
        print(path.stem)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
