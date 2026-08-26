import sys

from app.jobs.run_once import main

argv = sys.argv[1:]
if argv and argv[0] in {"run-once", "run_once"}:
    argv = argv[1:]
raise SystemExit(main(argv))
