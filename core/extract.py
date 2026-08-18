"""Read client documents into the structured rows no discovery tool produces.

The discovery checklist on Estate discovery lists fifteen items a wave plan
depends on and says plainly that ten of them are programme-sourced. Those ten do
not arrive as data. They arrive as documents: a renewal quote, a vendor support
statement, an SRM runbook export, a CMDB dump with columns nobody standardised.
Turning those into structured rows is the one job in this application that
arithmetic cannot do, which is the only reason a language model is here at all.

Three rules hold this feature in place. They are the difference between a
capability and a liability:

* **It writes inputs, never outputs.** Nothing here touches a score, a ranking,
  a recommendation or a computed cost. Everything it produces is presented for a
  human to confirm before it reaches any figure. The property that makes this
  application defensible to a client is that every number traces to a live
  vendor rate or a stated assumption; a language model in the scoring path would
  destroy that, and no amount of accuracy would give it back.
* **It is off unless somebody turns it on.** With no key configured the
  application is complete and nothing leaves it except public price-list
  lookups. That is the whole of the InfoSec conversation, and it stays true by
  default rather than by policy.
* **Nothing is sent without an explicit action, and the payload is shown
  first.** One document, one click, visible beforehand. There is no background
  call, no batch, and no automatic retry against a different document.

No Streamlit here: this module is the schemas and the client call, and the view
does the presenting and the key handling.
"""

import base64
import json
import mimetypes
from dataclasses import dataclass

# Claude Opus 5. Chosen over a cheaper tier because these documents feed a
# business case a client will be asked to sign off -- a misread core count or
# renewal date is worth far more than the difference in token cost, which runs
# to cents per document either way.
MODEL = "claude-opus-5"

# Published list rates for the model above, USD per million tokens. Used only to
# show the operator what a call cost; nothing in the migration model reads this.
INPUT_PER_MTOK = 5.00
OUTPUT_PER_MTOK = 25.00

# The API caps a whole request at 32MB, and a PDF is sent base64-encoded, which
# inflates it by four thirds. 24MB of PDF is 32MB on the wire before the schema
# and instruction are added -- over the limit with the arithmetic hidden. 20MB
# leaves real headroom.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
TEXT_SUFFIXES = {".csv", ".txt", ".md", ".json", ".log", ".tsv"}
PDF_SUFFIXES = {".pdf"}


class ExtractionError(RuntimeError):
    """Anything that stopped a document being read, in words an operator can use."""


class ExtractionRefused(ExtractionError):
    """The model's safety classifiers declined the document."""


SYSTEM = (
    "You read infrastructure and procurement documents for a VMware exit programme and "
    "return structured facts from them.\n\n"
    "Report only what the document actually states. Where a field is not present, return "
    "null rather than an estimate, an industry norm, or a value inferred from another "
    "field -- a missing value is useful information and a plausible invention is not. Do "
    "not calculate totals the document does not itself give. Quote identifiers, dates and "
    "figures exactly as written.\n\n"
    "Your output is a starting point for a human who will confirm every value against the "
    "source before it is used, so flag ambiguity in the notes rather than resolving it "
    "silently."
)

_CONFIDENCE = {
    "type": "string",
    "enum": ["high", "medium", "low"],
    "description": "How clearly the document states these facts. Low if you had to "
                   "interpret layout, handwriting, or ambiguous labelling.",
}
_NOTES = {
    "type": "string",
    "description": "Anything the reader should check against the source: ambiguity, "
                   "conflicting figures, values that appear on a page you could not read "
                   "cleanly, or an empty string if there is nothing to flag.",
}


def _obj(properties: dict) -> dict:
    """A schema object with every field required -- structured outputs needs both."""
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


@dataclass
class Target:
    key: str
    name: str
    checklist_item: str          # the Appendix A item this closes
    accepts: str                 # human-readable list of what to upload
    instruction: str
    schema: dict


TARGETS: list[Target] = [
    Target(
        key="entitlement",
        name="Licence entitlement and renewal position",
        checklist_item="Entitlement position: core counts, editions, renewal dates, "
                       "perpetual-key exposure",
        accepts="A renewal quote, an order form, a licence entitlement report or a "
                "reseller proposal.",
        instruction=(
            "Read this licensing document and report the client's entitlement and renewal "
            "position. The renewal date and the entitled core count are the two figures "
            "the whole programme is timed against, so be exact about both and say so in "
            "the notes if either is stated ambiguously. Report the commercial terms only "
            "where the document actually offers them -- an absent price cap is a finding."),
        schema=_obj({
            "renewal_date": {"anyOf": [{"type": "string"}, {"type": "null"}],
                             "description": "As written in the document, ISO format if "
                                            "unambiguous."},
            "entitled_cores": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
            "editions": {"type": "array", "items": {"type": "string"},
                         "description": "Product editions or bundles named, e.g. VCF, VVF."},
            "term_years": {"anyOf": [{"type": "number"}, {"type": "null"}]},
            "quoted_cost_per_year": {"anyOf": [{"type": "number"}, {"type": "null"}]},
            "currency": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "cost_per_core_per_year": {"anyOf": [{"type": "number"}, {"type": "null"}],
                                       "description": "Only if the document states it; do "
                                                      "not divide to obtain it."},
            "perpetual_key_exposure": {"anyOf": [{"type": "boolean"}, {"type": "null"}],
                                       "description": "Whether any perpetual licences or "
                                                      "unsupported versions are named."},
            "price_cap_offered": {"anyOf": [{"type": "boolean"}, {"type": "null"}]},
            "ramp_down_offered": {"anyOf": [{"type": "boolean"}, {"type": "null"}]},
            "portability_language": {"anyOf": [{"type": "boolean"}, {"type": "null"}],
                                     "description": "Whether entitlement may move to a "
                                                    "hyperscaler platform, stated in the "
                                                    "contract rather than in guidance."},
            "notes": _NOTES,
            "confidence": _CONFIDENCE,
        }),
    ),
    Target(
        key="appliances",
        name="Third-party virtual appliances",
        checklist_item="Third-party virtual appliance inventory with vendor support "
                       "statements",
        accepts="A vendor support statement, a compatibility matrix, an appliance "
                "inventory or an email thread with a vendor.",
        instruction=(
            "Read this document and list every third-party virtual appliance it names, "
            "with what the vendor says about supported platforms. The question that "
            "matters is whether each appliance is supported anywhere other than ESXi -- "
            "if the document does not say, record that rather than assuming either way."),
        schema=_obj({
            "appliances": {"type": "array", "items": _obj({
                "vendor": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "product": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "esxi_only": {"anyOf": [{"type": "boolean"}, {"type": "null"}],
                              "description": "True only where the document says so. Null "
                                             "where it is silent."},
                "supported_targets": {"type": "array", "items": {"type": "string"},
                                      "description": "Platforms the vendor states support "
                                                     "for."},
                "vendor_statement": {"anyOf": [{"type": "string"}, {"type": "null"}],
                                     "description": "The relevant sentence, quoted."},
                "action_required": {"anyOf": [{"type": "string"}, {"type": "null"}],
                                    "description": "What the programme has to do about it, "
                                                   "if the document indicates."},
            })},
            "notes": _NOTES,
            "confidence": _CONFIDENCE,
        }),
    ),
    Target(
        key="service_levels",
        name="Recovery objectives and change windows",
        checklist_item="RTO and RPO per application; change window availability and "
                       "blackout periods",
        accepts="A service catalogue, an SLA schedule, a BIA output or a change calendar.",
        instruction=(
            "Read this document and report the recovery objectives and change constraints "
            "per application or service. These govern which workloads can be cut over "
            "when, so record the blackout periods as precisely as the document states "
            "them."),
        schema=_obj({
            "applications": {"type": "array", "items": _obj({
                "app_name": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "criticality": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "rto_hours": {"anyOf": [{"type": "number"}, {"type": "null"}]},
                "rpo_hours": {"anyOf": [{"type": "number"}, {"type": "null"}]},
                "change_window": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "blackout_periods": {"type": "array", "items": {"type": "string"}},
            })},
            "notes": _NOTES,
            "confidence": _CONFIDENCE,
        }),
    ),
    Target(
        key="backup_dr",
        name="Backup and disaster recovery position",
        checklist_item="Existing DR topology and SRM runbook logic; backup policy, "
                       "retention, immutability and restore-test evidence",
        accepts="A DR design document, an SRM runbook export, a backup policy or a "
                "restore-test report.",
        instruction=(
            "Read this document and report the current backup and disaster recovery "
            "position. Site Recovery Manager runbook logic does not transfer to any other "
            "platform, so record how much orchestration exists and how it is structured. "
            "For backup, the feature-depth questions are what matter: changed-block "
            "tracking, application-aware processing, instant recovery and immutability."),
        schema=_obj({
            "dr": _obj({
                "replication_product": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "replication_pairs": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
                "orchestration_product": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "runbook_count": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
                "failover_tested": {"anyOf": [{"type": "boolean"}, {"type": "null"}]},
                "topology_notes": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            }),
            "backup": _obj({
                "product": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "retention_days": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
                "immutability": {"anyOf": [{"type": "boolean"}, {"type": "null"}]},
                "changed_block_tracking": {"anyOf": [{"type": "boolean"}, {"type": "null"}]},
                "application_aware": {"anyOf": [{"type": "boolean"}, {"type": "null"}]},
                "restore_test_evidence": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            }),
            "notes": _NOTES,
            "confidence": _CONFIDENCE,
        }),
    ),
    Target(
        key="hardware_licensing",
        name="Hardware-bound licensing",
        checklist_item="Hardware-bound licensing: dongles, MAC-bound licences, licence "
                       "servers",
        accepts="A software asset register, a licence server report or an application "
                "owner questionnaire.",
        instruction=(
            "Read this document and list every licence bound to a piece of hardware or to "
            "a machine identity -- dongles, MAC-bound keys, licence servers pinned to a "
            "host. These fail at cutover rather than before it, so record what each is "
            "bound to and what it would take to move it."),
        schema=_obj({
            "bindings": {"type": "array", "items": _obj({
                "system": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "vendor": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "binding_type": {"anyOf": [{"type": "string"}, {"type": "null"}],
                                 "description": "Dongle, MAC address, host ID, licence "
                                                "server, or as the document describes it."},
                "detail": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "migration_action": {"anyOf": [{"type": "string"}, {"type": "null"}],
                                     "description": "Rehost the licence server, request a "
                                                    "rehost key, and so on -- only where "
                                                    "the document indicates."},
            })},
            "notes": _NOTES,
            "confidence": _CONFIDENCE,
        }),
    ),
]

TARGET_BY_KEY = {t.key: t for t in TARGETS}


# --------------------------------------------------------------------------
# Where the key may live.
#
# Deliberately generous: an operator who has put a working key somewhere sensible
# should not have to discover which exact spelling this file expects, and a
# feature that silently reports itself "off" because of a section name is worse
# than one that is off on purpose. Checked in order; the first non-empty wins.
# --------------------------------------------------------------------------
KEY_LOCATIONS = (
    ("anthropic", "api_key"),
    ("anthropic", "key"),
    ("anthropic", "anthropic_api_key"),
    ("auth", "anthropic_key"),          # sits alongside the sign-in accounts
    ("auth", "anthropic_api_key"),
    ("auth", "api_key"),
)
TOP_LEVEL_KEYS = ("ANTHROPIC_API_KEY", "anthropic_api_key", "anthropic_key", "api_key")


def key_from(secrets=None, environ=None) -> str:
    """Resolve the API key from a secrets mapping, then the environment.

    ``secrets`` is whatever ``st.secrets`` gives back; reading it raises rather
    than returning empty when no secrets file exists, so the caller passes it in
    and this stays free of Streamlit.
    """
    def _get(mapping, name):
        try:
            value = mapping[name]
        except Exception:
            return None
        return value

    if secrets is not None:
        for section, name in KEY_LOCATIONS:
            block = _get(secrets, section)
            if block is None:
                continue
            value = _get(block, name)
            if isinstance(value, str) and value.strip():
                return value.strip()
        for name in TOP_LEVEL_KEYS:
            value = _get(secrets, name)
            if isinstance(value, str) and value.strip():
                return value.strip()

    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_KEY"):
        value = (environ or {}).get(name, "")
        if value.strip():
            return value.strip()
    return ""


def key_source(secrets=None, environ=None) -> str:
    """Which spelling actually supplied the key, for display."""
    if secrets is not None:
        for section, name in KEY_LOCATIONS:
            try:
                value = secrets[section][name]
            except Exception:
                continue
            if isinstance(value, str) and value.strip():
                return f"[{section}] {name}"
        for name in TOP_LEVEL_KEYS:
            try:
                value = secrets[name]
            except Exception:
                continue
            if isinstance(value, str) and value.strip():
                return f"secrets: {name}"
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_KEY"):
        if (environ or {}).get(name, "").strip():
            return f"environment: {name}"
    return ""


# --------------------------------------------------------------------------
def accepted(filename: str) -> bool:
    return _suffix(filename) in (TEXT_SUFFIXES | PDF_SUFFIXES)


def _suffix(filename: str) -> str:
    return ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""


def payload_summary(target: Target, filename: str, data: bytes) -> dict:
    """Exactly what leaving the application would mean, for display before it does.

    The operator sees this and clicks, or does not. There is no path that sends a
    document without this having been rendered first.
    """
    suffix = _suffix(filename)
    return {
        "destination": "Anthropic Claude API (api.anthropic.com)",
        "model": MODEL,
        "document": filename,
        "size": f"{len(data) / 1024:,.0f} KB",
        "sent_as": "PDF, in full" if suffix in PDF_SUFFIXES else "Text, in full",
        "also_sent": "The instruction and schema for "
                     f"'{target.name}', and nothing else.",
        "not_sent": "No estate inventory, no scenario, no other document, no "
                    "previously extracted result.",
        "retention": "Anthropic's standard API retention applies. Confirm it against "
                     "the client's data-handling position before uploading anything "
                     "carrying their identity.",
    }


def _document_block(filename: str, data: bytes) -> dict:
    suffix = _suffix(filename)
    if suffix in PDF_SUFFIXES:
        return {"type": "document",
                "source": {"type": "base64", "media_type": "application/pdf",
                           "data": base64.standard_b64encode(data).decode("ascii")}}
    if suffix in TEXT_SUFFIXES:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("latin-1", errors="replace")
        return {"type": "text",
                "text": f"<document filename=\"{filename}\">\n{text}\n</document>"}
    kind = mimetypes.guess_type(filename)[0] or "unknown"
    raise ExtractionError(
        f"{filename} is a {kind} file. This reads PDFs and text formats "
        f"({', '.join(sorted(TEXT_SUFFIXES))}); export or print to PDF first.")


def estimated_cost(usage) -> float:
    """USD at the model's published list rates, for the operator's own record."""
    return (getattr(usage, "input_tokens", 0) / 1e6 * INPUT_PER_MTOK
            + getattr(usage, "output_tokens", 0) / 1e6 * OUTPUT_PER_MTOK)


def extract(target: Target, filename: str, data: bytes, api_key: str,
            model: str = MODEL) -> dict:
    """Read one document into one schema. Raises ExtractionError with a usable message.

    Imported lazily so the application runs, and every other page works, on a
    deployment where the SDK is not installed at all.
    """
    if not api_key:
        raise ExtractionError("No API key configured.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ExtractionError(
            f"{filename} is {len(data) / 1024 / 1024:.1f} MB. The limit is "
            f"{MAX_UPLOAD_BYTES // 1024 // 1024} MB, because a PDF is sent base64-encoded "
            "and that adds a third again against a 32MB request cap. Split it, or export "
            "just the pages carrying the figures.")

    block = _document_block(filename, data)

    try:
        import anthropic
    except ImportError as exc:                                   # pragma: no cover
        raise ExtractionError(
            "The 'anthropic' package is not installed on this deployment. Add it to "
            "requirements.txt and reboot the app.") from exc

    client = anthropic.Anthropic(api_key=api_key)
    call = dict(
        model=model,
        max_tokens=16000,
        system=SYSTEM,
        output_config={"effort": "medium",
                       "format": {"type": "json_schema", "schema": target.schema}},
        messages=[{"role": "user", "content": [block,
                                               {"type": "text",
                                                "text": target.instruction}]}],
    )
    try:
        try:
            # Server-side fallbacks on by default: this model's safety classifiers
            # can decline a document, and an infrastructure or security export is
            # exactly the shape that occasionally trips them on a false positive.
            # Without this such a document simply fails to read.
            resp = client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **call)
        except TypeError:
            # An SDK older than the fallbacks parameter. Read the document anyway
            # rather than failing -- a declined document then surfaces as a refusal
            # below, which is handled, instead of as an unexpected-keyword crash.
            resp = client.beta.messages.create(**call)
    except Exception as exc:                                     # SDK raises typed errors
        raise ExtractionError(f"{type(exc).__name__}: {exc}") from exc

    if getattr(resp, "stop_reason", None) == "refusal":
        detail = getattr(getattr(resp, "stop_details", None), "category", None)
        raise ExtractionRefused(
            "The model declined to read this document"
            + (f" (category: {detail})" if detail else "")
            + ". That is a content decision, not a failure of the file -- read the "
              "relevant figures across by hand.")

    text = next((b.text for b in resp.content if b.type == "text"), "")
    if not text:
        raise ExtractionError("The model returned no content for this document.")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:                          # pragma: no cover
        raise ExtractionError(f"Could not parse the response as JSON: {exc}") from exc

    return {
        "target": target.key,
        "filename": filename,
        "data": parsed,
        "model": getattr(resp, "model", model),
        "input_tokens": getattr(resp.usage, "input_tokens", 0),
        "output_tokens": getattr(resp.usage, "output_tokens", 0),
        "cost_usd": estimated_cost(resp.usage),
    }
