"""Tests for the sign-in gate: hashing, tokens, lockout, and the rendered cover.

Run with:  py -3.12 tools_authtest.py     (exit code 1 on any failure)
"""

import json
import os
import sys
import time

from core import auth

RESULTS = []


def check(name: str, condition: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(condition), detail))


# --------------------------------------------------------------------------
def test_hashing() -> None:
    digest = auth.hash_password("correct horse battery staple")
    check("hash is self-describing", digest.startswith("pbkdf2_sha256$240000$"), digest[:28])
    check("correct password verifies",
          auth.verify_password("correct horse battery staple", digest))
    check("wrong password is rejected",
          not auth.verify_password("correct horse battery stapl", digest))
    check("two hashes of one password differ (salted)",
          auth.hash_password("hunter2") != auth.hash_password("hunter2"))
    check("a truncated hash is rejected, not an error",
          not auth.verify_password("hunter2", digest[:-6]))
    check("garbage is rejected", not auth.verify_password("hunter2", "not-a-hash"))
    check("empty stored secret is rejected", not auth.verify_password("hunter2", ""))
    check("plaintext record still verifies", auth.verify_password("hunter2", "hunter2"))
    check("plaintext record rejects the wrong password",
          not auth.verify_password("hunter3", "hunter2"))


def test_user_store() -> None:
    os.environ.pop("APP_USERS", None)
    users = auth.load_users()
    check("no configuration yields the demo account", list(users) == [auth.DEMO_USER],
          str(list(users)))
    check("demo account is flagged as such", auth.using_demo_account())

    os.environ["APP_USERS"] = json.dumps({
        "ajit": {"name": "Ajit Gosavi", "role": "Owner",
                 "password_hash": auth.hash_password("s3cret-pass")},
        "guest": "guest-pass",
    })
    users = auth.load_users()
    check("APP_USERS is read", sorted(users) == ["ajit", "guest"], str(sorted(users)))
    check("record metadata survives", users["ajit"]["name"] == "Ajit Gosavi")
    check("a bare string record becomes a password",
          auth.verify_password("guest-pass", users["guest"]["secret"]))
    check("configured accounts turn the demo warning off", not auth.using_demo_account())

    os.environ["APP_USERS"] = "{not json"
    check("malformed APP_USERS degrades to the demo account",
          list(auth.load_users()) == [auth.DEMO_USER])
    os.environ.pop("APP_USERS", None)


def test_tokens() -> None:
    os.environ["APP_USERS"] = json.dumps({"ajit": {"password": "s3cret-pass"}})
    os.environ["APP_SESSION_SECRET"] = "test-signing-key"

    token = auth.issue_token("ajit")
    check("a fresh token resolves to its user", auth.read_token(token) == "ajit")
    check("a tampered signature is rejected", auth.read_token(token[:-3] + "AAA") is None)
    check("a tampered payload is rejected",
          auth.read_token("Zm9vfDk5OTk5OTk5OTk." + token.split(".", 1)[1]) is None)
    check("a malformed token is rejected", auth.read_token("nonsense") is None)
    check("an expired token is rejected",
          auth.read_token(auth.issue_token("ajit", hours=-1)) is None)
    check("the token lifetime is hours, not days", auth.REMEMBER_HOURS <= 24,
          f"{auth.REMEMBER_HOURS}h")

    os.environ["APP_USERS"] = json.dumps({"someone-else": {"password": "x"}})
    check("a token for a deleted account is rejected", auth.read_token(token) is None)

    os.environ.pop("APP_SESSION_SECRET", None)
    os.environ["APP_USERS"] = json.dumps({"ajit": {"password": "s3cret-pass"}})
    derived = auth.issue_token("ajit")
    check("the derived key round-trips", auth.read_token(derived) == "ajit")
    os.environ["APP_USERS"] = json.dumps({"ajit": {"password": "different-pass"}})
    check("changing a password invalidates outstanding tokens",
          auth.read_token(derived) is None)
    os.environ.pop("APP_USERS", None)


# --------------------------------------------------------------------------
GATE_SCRIPT = """
import os, streamlit as st
from core import auth, login_ui
if not auth.is_signed_in():
    login_ui.render()
    st.stop()
st.write("SIGNED IN AS " + auth.current_user()["username"])
"""


def test_rendered_gate() -> int:
    """Drive the real cover through Streamlit's own test harness."""
    import pathlib
    from streamlit.testing.v1 import AppTest

    os.environ["APP_USERS"] = json.dumps(
        {"ajit": {"name": "Ajit Gosavi", "password": "s3cret-pass"}})
    script = pathlib.Path("_authgate_probe.py")
    script.write_text(GATE_SCRIPT, encoding="utf-8")
    try:
        at = AppTest.from_file(str(script), default_timeout=60)
        at.run()
        check("the cover renders without error", not at.exception,
              str(at.exception[0].value) if at.exception else "")
        body = " ".join(m.value for m in at.markdown)
        check("the cover carries the product name", "Ascend" in body)
        check("the cover carries the readout", "$0.0460" in body)
        check("the sign-in form is present", len(at.text_input) == 2,
              f"{len(at.text_input)} inputs")

        at.text_input[0].set_value("ajit")
        at.text_input[1].set_value("wrong-pass")
        at.button[0].click().run()
        body = " ".join(m.value for m in at.markdown)
        check("a wrong password is refused", "do not match" in body)
        check("still signed out after a refusal", "SIGNED IN" not in body)

        at.text_input[0].set_value("ajit")
        at.text_input[1].set_value("s3cret-pass")
        at.button[0].click().run()
        body = " ".join(str(m.value) for m in at.markdown)
        check("correct credentials sign in", "SIGNED IN AS ajit" in body)
        return 0
    finally:
        script.unlink(missing_ok=True)
        os.environ.pop("APP_USERS", None)


# --------------------------------------------------------------------------
def main() -> int:
    t0 = time.time()
    test_hashing()
    test_user_store()
    test_tokens()
    test_rendered_gate()

    failed = 0
    for name, ok, detail in RESULTS:
        if ok:
            print(f"ok    {name}")
        else:
            failed += 1
            print(f"FAIL  {name}" + (f"  --  {detail}" if detail else ""))
    print()
    if failed:
        print(f"{failed} of {len(RESULTS)} checks failed.")
        return 1
    print(f"All {len(RESULTS)} checks passed in {time.time() - t0:.1f}s.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
