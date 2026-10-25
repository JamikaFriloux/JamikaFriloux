"""Create a dashboard user. There are no default accounts.

Usage: python -m atlas.scripts.create_user <username> --role admin|operator|viewer
The password is read interactively (never pass it on the command line) or from stdin with
--password-stdin for automation.
"""

from __future__ import annotations

import argparse
import getpass
import sys

from atlas.core.models.db import Role
from atlas.core.models.session import session_scope
from atlas.core.security import audit
from atlas.core.security.auth import create_user


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("username")
    parser.add_argument("--role", choices=[r.value for r in Role], default=Role.VIEWER.value)
    parser.add_argument("--password-stdin", action="store_true")
    args = parser.parse_args(argv)

    if args.password_stdin:
        password = sys.stdin.readline().rstrip("\n")
    else:
        password = getpass.getpass("Password (min 12 chars): ")
        if password != getpass.getpass("Confirm password: "):
            print("passwords do not match", file=sys.stderr)
            return 1
    try:
        with session_scope() as s:
            create_user(s, args.username, password, Role(args.role))
            audit.record(
                s,
                actor="cli",
                action="user.create",
                target=args.username,
                details={"role": args.role},
            )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"created {args.role} user {args.username!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
