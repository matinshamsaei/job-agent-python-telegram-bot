import sys

COMMANDS = {
    "run-once": "app.jobs.run_once",
    "run_once": "app.jobs.run_once",
    "coverage": "app.jobs.coverage",
    "discover-sources": "app.jobs.discover_sources",
    "discover_sources": "app.jobs.discover_sources",
    "sync-seed-sources": "app.jobs.sync_seed_sources",
    "sync_seed_sources": "app.jobs.sync_seed_sources",
}

argv = sys.argv[1:]
module = "app.jobs.run_once"
if argv and argv[0] in COMMANDS:
    module = COMMANDS[argv[0]]
    argv = argv[1:]
elif argv and argv[0] in {"-h", "--help"}:
    print("Commands: run-once, coverage, discover-sources, sync-seed-sources")
    raise SystemExit(0)

command = __import__(module, fromlist=["main"])
raise SystemExit(command.main(argv))
