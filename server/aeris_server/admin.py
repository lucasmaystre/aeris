"""`aeris-admin`: maintenance commands, run against the database in `AERIS_DATABASE_URL`."""

import argparse

from aeris_server import db
from aeris_server.migrate import migrate


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="aeris-admin")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate", help="Apply pending database migrations.")
    args = parser.parse_args(argv)

    if args.command == "migrate":
        applied = migrate(db.engine())
        for version in applied:
            print(f"Applied {version}.")
        if not applied:
            print("Up to date.")
