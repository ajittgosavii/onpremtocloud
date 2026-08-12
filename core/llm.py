"""OpenAI advisor layer.

The simulator's numbers are deterministic and computed locally. The LLM's job is
narrow and honest: turn those numbers into the narrative, risk register and
recommendation a client can act on -- and answer questions about *this* estate,
grounded in the facts passed to it.

It is never asked to invent a price or a limit. Every figure in a prompt comes
from the engines or from the live Azure Retail Prices API.
"""

import json
import os
from dataclasses import dataclass

MODELS = ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "o4-mini"]
DEFAULT_MODEL = "gpt-4o"

SYSTEM = """You are a principal cloud migration architect advising an enterprise client on \
moving a VMware vSphere estate to Microsoft Azure. You have deep, current experience of \
Azure Migrate, Azure VMware Solution, Azure Local, Azure landing zones, VMware licensing \
after the Broadcom acquisition, and the competitive tooling market.

Rules you must follow:
- Ground every quantitative claim in the CONTEXT provided. Never invent prices, product \
limits, SKU names or percentages. If the context does not contain a number you need, say \
what is missing and what it would take to find out.
- Be specific to this estate. Generic migration advice is worthless to the reader.
- Lead with the decision or recommendation, then the reasoning. No throat-clearing.
- Name trade-offs honestly, including the ones that count against the recommendation.
- Write in clear British-English prose for a technically literate executive audience. \
Short paragraphs. Use headings and bullets only where they genuinely aid scanning.
- Do not use marketing language, and do not congratulate the reader."""


@dataclass
class LlmConfig:
    api_key: str = ""
    model: str = DEFAULT_MODEL
    temperature: float = 0.2
    max_tokens: int = 2200
    base_url: str = ""


class LlmUnavailable(RuntimeError):
    pass


def resolve_key(explicit: str = "") -> str:
    return explicit or os.environ.get("OPENAI_API_KEY", "")


def _client(cfg: LlmConfig):
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise LlmUnavailable("The 'openai' package is not installed. Run: pip install openai") from exc
    key = resolve_key(cfg.api_key)
    if not key:
        raise LlmUnavailable(
            "No OpenAI API key. Add it in the sidebar, or set OPENAI_API_KEY in the environment "
            "or a .env file. Every other part of the simulator works without it."
        )
    kwargs = {"api_key": key}
    if cfg.base_url:
        kwargs["base_url"] = cfg.base_url
    return OpenAI(**kwargs)


def complete(prompt: str, cfg: LlmConfig, system: str = SYSTEM) -> str:
    client = _client(cfg)
    resp = client.chat.completions.create(
        model=cfg.model,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": prompt}],
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
    )
    return resp.choices[0].message.content or ""


def stream(prompt: str, cfg: LlmConfig, system: str = SYSTEM, history: list | None = None):
    """Yield tokens for st.write_stream."""
    client = _client(cfg)
    messages = [{"role": "system", "content": system}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": prompt})
    resp = client.chat.completions.create(
        model=cfg.model, messages=messages,
        temperature=cfg.temperature, max_tokens=cfg.max_tokens, stream=True,
    )
    for chunk in resp:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


# --------------------------------------------------------------------------
# Context builder -- the single place that decides what the model gets to see
# --------------------------------------------------------------------------
def build_context(state: dict) -> str:
    """Compact, factual snapshot of the current scenario for grounding."""
    ctx: dict = {}

    if "estate_summary" in state:
        ctx["estate"] = state["estate_summary"]
    if "sizing_summary" in state:
        ctx["rightsizing"] = state["sizing_summary"]
    if "readiness_counts" in state:
        ctx["readiness"] = state["readiness_counts"]
    if "disposition_counts" in state:
        ctx["seven_r_disposition"] = state["disposition_counts"]
    if "cost_summary" in state:
        ctx["azure_monthly_cost"] = state["cost_summary"]
    if "effort_summary" in state:
        ctx["migration_effort"] = state["effort_summary"]
    if "schedule_summary" in state:
        s = dict(state["schedule_summary"])
        s.pop("go_live", None)
        ctx["schedule"] = s
    if "tco_summary" in state:
        ctx["tco"] = state["tco_summary"]
    if "migrate_summary" in state:
        m = dict(state["migrate_summary"])
        m.pop("appliance_plan", None)
        ctx["azure_migrate_run"] = m
    if "mc_percentiles" in state:
        ctx["monte_carlo_percentiles"] = state["mc_percentiles"]
    if "top_blockers" in state:
        ctx["top_blockers"] = state["top_blockers"]
    if "commercial_policy" in state:
        ctx["commercial_levers"] = state["commercial_policy"]
    if "pricing_source" in state:
        ctx["pricing_source"] = state["pricing_source"]

    return json.dumps(ctx, indent=2, default=str)


# --------------------------------------------------------------------------
# Prompt templates
# --------------------------------------------------------------------------
PROMPTS: dict[str, str] = {
    "Executive summary": (
        "Write a one-page executive summary of this migration for a CIO and CFO. Cover: what is "
        "being proposed, what it costs to run versus today, what the one-off programme costs, how "
        "long it takes, the three risks that most threaten the outcome, and a clear recommendation "
        "with the decision you are asking them to make. Put the single most important number in "
        "the first two sentences."
    ),
    "Technical migration strategy": (
        "Write the technical migration strategy. Cover the target landing-zone design implied by "
        "this estate, the tooling stack and why, the wave approach and its binding constraint, how "
        "the readiness blockers get cleared, the network and identity prerequisites, and the "
        "cutover and rollback pattern. Be concrete about what is done first and what it unblocks."
    ),
    "Risk register": (
        "Produce a risk register as a markdown table with columns: Risk, Category, Likelihood "
        "(H/M/L), Impact (H/M/L), Leading indicator, Mitigation, Owner role. Derive the risks from "
        "the actual numbers in the context -- blockers, confidence rating, bandwidth constraint, "
        "cost variance, EOL operating systems, cutover failure rate. Ten to fourteen rows. Order "
        "by exposure, highest first."
    ),
    "Cost optimisation plan": (
        "Write a cost optimisation plan for this Azure estate. Quantify what each lever is worth "
        "using the context figures: right-sizing, Azure Hybrid Benefit, reservations versus "
        "savings plans, non-production scheduling, storage tiering, retiring zombie VMs. State the "
        "order to pull them in, who owns each, and which ones must be decided before the first "
        "wave because they are hard to retrofit."
    ),
    "Platform decision rationale": (
        "The client is choosing between Azure native IaaS, Azure VMware Solution, Azure Local "
        "on-premises, and staying on VMware. Write the decision rationale. Use the cost and "
        "readiness figures in the context. Address explicitly when Azure Local is the right answer "
        "rather than public Azure, and be honest about where the recommendation could be wrong."
    ),
    "Azure Migrate runbook": (
        "Write an operational runbook for executing this migration with Azure Migrate. Sequence "
        "the phases with entry and exit criteria, name the product limits that constrain this "
        "specific estate and what they mean in practice, and list the checks that must pass before "
        "each cutover. Write it so a migration engineer could follow it."
    ),
    "Board paper: business case": (
        "Write a board paper making the investment case. Structure: recommendation, the decision "
        "required, financial summary (one-off, run-rate change, NPV, payback), what happens if we "
        "do nothing, key risks and how they are controlled, and the milestones the board should "
        "hold the programme to. Be direct about the confidence level and quote the P80 figures, "
        "not just the median."
    ),
    "Wave plan narrative": (
        "Explain the wave plan: why the waves are grouped as they are, what the binding constraint "
        "is in each phase and how to relieve it, what has to be true before wave 1 starts, and "
        "which waves carry the most risk. Recommend where to add parallelism and where not to."
    ),
    "Client Q&A prep": (
        "Anticipate the fifteen hardest questions this client's architecture review board will ask "
        "about this plan, and give a direct, defensible answer to each, grounded in the context. "
        "Include the questions that expose weaknesses in the plan, not just the easy ones."
    ),
}


def render_prompt(task: str, context: str, extra: str = "") -> str:
    body = PROMPTS.get(task, task)
    return (f"CONTEXT (all figures are computed from the client's own inventory and live Azure "
            f"retail pricing):\n```json\n{context}\n```\n\n"
            f"TASK:\n{body}\n"
            + (f"\nADDITIONAL INSTRUCTIONS FROM THE USER:\n{extra}\n" if extra.strip() else ""))
