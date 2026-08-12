"""Produce the secrets.toml block for an account.

  py -3.12 tools_hashpw.py                       prompts for username and password
  py -3.12 tools_hashpw.py --user ajit --name "Ajit Gosavi" --role Owner

The password is never echoed and never written to disk by this script. Paste the
printed block into .streamlit/secrets.toml locally, or into Settings > Secrets on
Streamlit Community Cloud.
"""

import argparse
import getpass
import sys

from core import auth


def main() -> int:
    ap = argparse.ArgumentParser(description="Hash a password for secrets.toml")
    ap.add_argument("--user", help="username used to sign in")
    ap.add_argument("--name", help="display name shown in the sidebar")
    ap.add_argument("--role", default="Consultant", help="label shown under the name")
    ap.add_argument("--password", help="skip the prompt (visible in shell history)")
    args = ap.parse_args()

    username = args.user or input("Username: ").strip()
    if not username:
        print("A username is required.", file=sys.stderr)
        return 1

    password = args.password
    if not password:
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Repeat password: "):
            print("Passwords do not match.", file=sys.stderr)
            return 1
    if len(password) < 8:
        print("Use at least 8 characters.", file=sys.stderr)
        return 1

    digest = auth.hash_password(password)
    assert auth.verify_password(password, digest), "hash failed to verify"

    print()
    print(f'[auth.users.{username}]')
    print(f'name = "{args.name or username}"')
    print(f'role = "{args.role}"')
    print(f'password_hash = "{digest}"')
    print()
    print(f"Verified. {auth.ITERATIONS:,} PBKDF2-HMAC-SHA256 iterations.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
