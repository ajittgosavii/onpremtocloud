"""Offline checks for the document reader. Runs without an API key or a network.

Everything here is the part that can be wrong without anybody noticing: a schema
structured outputs would reject, a document type routed to the wrong block shape,
or a payload summary that under-states what leaves the application.

    py -3.12 tools_extracttest.py
"""

import sys

from core import broadcom, extract

ok, fail = 0, 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global ok, fail
    if condition:
        ok += 1
        print(f"ok    {label}")
    else:
        fail += 1
        print(f"FAIL  {label}" + (f"  -- {detail}" if detail else ""))


def walk(node, path: str) -> list[str]:
    """Structured outputs requires additionalProperties:false and full `required`."""
    bad = []
    if isinstance(node, dict):
        if node.get("type") == "object":
            props = node.get("properties", {})
            if node.get("additionalProperties") is not False:
                bad.append(f"{path}: additionalProperties is not False")
            if set(node.get("required", [])) != set(props):
                bad.append(f"{path}: `required` does not list every property")
            for k, v in props.items():
                bad += walk(v, f"{path}.{k}")
        if node.get("type") == "array":
            bad += walk(node.get("items", {}), f"{path}[]")
        for branch in node.get("anyOf", []):
            bad += walk(branch, f"{path}|")
    return bad


print(f"Python {sys.version.split()[0]}\n")

for t in extract.TARGETS:
    problems = walk(t.schema, t.key)
    check(f"schema is valid for structured outputs: {t.key}", not problems,
          "; ".join(problems))

check("every target has a unique key",
      len({t.key for t in extract.TARGETS}) == len(extract.TARGETS))
check("every target names the checklist item it closes",
      all(t.checklist_item and t.accepts and t.instruction for t in extract.TARGETS))

# ---- routing -------------------------------------------------------------
check("PDF routes to a document block",
      extract._document_block("q.pdf", b"%PDF-1.4")["type"] == "document")
check("CSV routes to a text block",
      extract._document_block("x.csv", b"a,b\n1,2")["type"] == "text")
# latin-1 maps every byte, so the fallback decode never raises -- the property
# worth asserting is that a non-UTF-8 export still produces a usable text block.
_odd = extract._document_block("x.txt", b"\xff\xfe legacy \x93export\x94")
check("a non-UTF-8 file still produces a text block",
      _odd["type"] == "text" and "legacy" in _odd["text"])
try:
    extract._document_block("photo.jpg", b"\xff\xd8")
    check("an unsupported type is refused", False, "no error raised")
except extract.ExtractionError:
    check("an unsupported type is refused with a usable message", True)

check("accepted() agrees with the block router",
      extract.accepted("a.pdf") and extract.accepted("b.csv")
      and not extract.accepted("c.jpg"))

# ---- the disclosure the operator sees before sending ---------------------
summary = extract.payload_summary(extract.TARGETS[0], "quote.pdf", b"x" * 2048)
check("payload summary names the destination",
      "api.anthropic.com" in summary["destination"])
check("payload summary names the model", summary["model"] == extract.MODEL)
check("payload summary states what is NOT sent",
      "No estate inventory" in summary["not_sent"])
check("payload summary raises data handling", "retention" in summary)

# ---- the checklist wiring -----------------------------------------------
targets_used = {t for *_, t in broadcom.DISCOVERY_CHECKLIST if t}
check("every checklist target exists in the reader",
      targets_used <= set(extract.TARGET_BY_KEY),
      f"unknown: {sorted(targets_used - set(extract.TARGET_BY_KEY))}")
check("every reader target closes at least one checklist item",
      set(extract.TARGET_BY_KEY) <= targets_used,
      f"orphaned: {sorted(set(extract.TARGET_BY_KEY) - targets_used)}")

rows = broadcom.discovery_coverage([], from_documents=targets_used)
check("reading every document closes 7 of the 15 checklist items",
      sum(r["held"] for r in rows) == 7, f"closed {sum(r['held'] for r in rows)}")
check("nothing is held when no document has been read and no estate is loaded",
      not any(r["held"] for r in broadcom.discovery_coverage([])))

# ---- key resolution ------------------------------------------------------
# The failure this guards against is silent: a key present under a spelling the
# resolver does not know reports the feature as "off", which on screen looks
# identical to nobody having configured it at all.
check("[auth] anthropic_key is found",
      extract.key_from({"auth": {"anthropic_key": "sk-ant-x"}}, {}) == "sk-ant-x")
check("[anthropic] api_key is found",
      extract.key_from({"anthropic": {"api_key": "sk-ant-x"}}, {}) == "sk-ant-x")
check("ANTHROPIC_API_KEY in the environment is found",
      extract.key_from({}, {"ANTHROPIC_API_KEY": "sk-ant-x"}) == "sk-ant-x")
check("an auth block holding only sign-in accounts is not mistaken for a key",
      extract.key_from({"auth": {"users": {"demo": "pbkdf2..."}}}, {}) == "")
check("a whitespace-only value does not count as configured",
      extract.key_from({"anthropic": {"api_key": "   "}}, {}) == "")
check("absent secrets resolve to off rather than raising",
      extract.key_from(None, {}) == "")
check("the source is reported for display",
      extract.key_source({"auth": {"anthropic_key": "k"}}, {}) == "[auth] anthropic_key")

print(f"\n{ok} passed, {fail} failed.")
sys.exit(1 if fail else 0)
