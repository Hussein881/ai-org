"""aiorgctl: stop | resume | status. Works without the dashboard."""

import argparse
import sys

from sqlalchemy.orm import Session

from app.core import control
from app.db.models import WorkerStatus
from app.db.session import engine

ACTOR = "aiorgctl"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="aiorgctl")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("stop", help="emergency stop").add_argument("--reason", default="aiorgctl stop")
    sub.add_parser("resume", help="allow work again")
    sub.add_parser("status", help="show stop flag and worker heartbeat")
    args = ap.parse_args(argv)
    with Session(engine()) as db:
        if args.cmd == "stop":
            n = control.request_stop(db, ACTOR, args.reason)
            print(f"stopped; {n} running task(s) cancelled")
        elif args.cmd == "resume":
            control.resume(db, ACTOR)
            print("resumed")
        else:
            state = control.get(db)
            beat = db.get(WorkerStatus, 1)
            print(f"stopped={state.stopped} reason={state.reason if state.stopped else '-'}")
            print(f"worker_heartbeat={beat.heartbeat_at if beat else None}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
