"""Programme risk register for a VMware exit, checked against the live model.

Fifteen risks, taken from the source assessment's register. A register that is
only ever read is a document; this one is scored, because most of these risks are
observable in the scenario the rest of the application has already computed. If
the plan retires nothing, replicates agentlessly onto a constrained SAN, or
leaves workloads on a bridge platform with no decommission date, the register
should say so on screen rather than waiting for a steering committee to notice.

Twelve of the fifteen are testable from the model. The remaining three are
programme conditions no model can see -- landing-zone enforcement, preview-feature
dependency and entitlement audit exposure -- and they are returned as advisory so
they still get read out, which is the same discipline
``broadcom.check_antipatterns`` uses.

No Streamlit and no other core module is imported here: this is the data and the
arithmetic, and the views do the presenting.
"""

from dataclasses import dataclass

TRIGGERED = "triggered"      # the model currently exhibits this risk
CLEAR = "clear"              # testable, and currently not exhibited
ADVISORY = "advisory"        # not observable from any model

HIGH = "High"
MEDIUM = "Medium"

# Who carries it. The register is worth little without a named owner type,
# because an unowned risk is a risk nobody reviews.
PROGRAMME = "Programme director"
COMMERCIAL = "Procurement / commercial lead"
TECHNICAL = "Infrastructure lead"
APPLICATION = "Application owners"


@dataclass
class Risk:
    id: str
    risk: str
    impact: str
    mitigation: str
    owner: str
    testable: bool = False


REGISTER: list[Risk] = [
    Risk("R01",
         "Renewal deadline passes without a decision, forcing an unplanned Broadcom "
         "commitment.",
         HIGH,
         "Establish the contract position in the first two weeks; schedule the decision "
         "gate ahead of the renewal date with a named decision owner.",
         COMMERCIAL, testable=True),
    Risk("R02",
         "An Azure VMware Solution pay-as-you-go estate misses the portable licence "
         "requirement deadline.",
         HIGH,
         "Confirm the AVS licensing position this month. If exposed, initiate the "
         "Broadcom purchase or migrate off immediately.",
         COMMERCIAL, testable=True),
    Risk("R03",
         "Double-run cost exceeds the business case, eroding the exit rationale.",
         HIGH,
         "Model it explicitly in Scenario C, track it monthly, and accelerate cluster "
         "decommission so cores are released early.",
         PROGRAMME, testable=True),
    Risk("R04",
         "Discovery misses dependencies, causing an application outage at cutover.",
         HIGH,
         "Minimum 30-day observation window; agent-based mapping for complex groups; "
         "mandatory application-owner validation per wave.",
         TECHNICAL, testable=True),
    Risk("R05",
         "Agentless replication degrades production SAN performance.",
         HIGH,
         "Baseline IOPS headroom before wave one, schedule replication outside peak, and "
         "use agent-based replication for IOPS-sensitive workloads.",
         TECHNICAL, testable=True),
    Risk("R06",
         "Azure run cost exceeds the assessment estimate after migration.",
         HIGH,
         "Build the surrounding cost lines separately from the tool's output; right-size "
         "within 30 days of each wave; set reservation coverage targets.",
         PROGRAMME, testable=True),
    Risk("R07",
         "Disaster recovery capability is degraded during or after the transition.",
         HIGH,
         "Treat DR re-engineering as a funded workstream from Phase 1 rather than a "
         "post-migration task; failover test per wave group.",
         TECHNICAL, testable=True),
    Risk("R08",
         "Third-party virtual appliances are supported on ESXi only.",
         MEDIUM,
         "Identify in Phase 1, open vendor conversations early, and hold a defined "
         "exception path for appliances with no answer.",
         APPLICATION, testable=True),
    Risk("R09",
         "Backup capability on the target is not at feature parity.",
         MEDIUM,
         "Verify changed-block tracking, application-aware processing, instant recovery "
         "and immutability per target; restore-test before volume waves.",
         TECHNICAL, testable=True),
    Risk("R10",
         "Key skills are lost during the dual-operations period.",
         MEDIUM,
         "Retention planning at mobilisation, funded training, and a realistic on-call "
         "design across both platforms.",
         PROGRAMME, testable=True),
    Risk("R11",
         "Landing zone controls are retrofitted after volume waves have begun.",
         MEDIUM,
         "Hard gate at the end of Phase 2. No production wave without demonstrated policy "
         "enforcement.",
         TECHNICAL),
    Risk("R12",
         "The Azure Local test-migration gap causes an unintended production cutover.",
         MEDIUM,
         "Use purpose-built canaries only, never a sample of production servers, and treat "
         "replication completion as transport rather than acceptance.",
         TECHNICAL, testable=True),
    Risk("R13",
         "Preview migration-tooling capabilities change or are withdrawn mid-programme.",
         MEDIUM,
         "No critical dependency on a preview feature without a documented fallback.",
         TECHNICAL),
    Risk("R14",
         "Vendor audit activity surfaces unquantified entitlement exposure.",
         MEDIUM,
         "Document the entitlement position in Phase 0 and remediate any perpetual-key or "
         "version exposure before the negotiation opens.",
         COMMERCIAL),
    Risk("R15",
         "The bridge platform becomes permanent, leaving the incumbent licence in place.",
         MEDIUM,
         "A board-visible decommission date per bridged workload, with the onward "
         "destination named at the point of entry.",
         PROGRAMME, testable=True),
]

BY_ID = {r.id: r for r in REGISTER}


def check_register(facts: dict) -> list[dict]:
    """Score the register against the current scenario.

    ``facts`` is a plain dict so this module stays independent of the pipeline.
    Returns one row per risk with a status and the observation behind it.
    """
    def f(key, default=0.0):
        return facts.get(key, default)

    obs: dict[str, tuple[bool, str]] = {}

    days = f("renewal_days_remaining", 0)
    obs["R01"] = (
        days <= 90,
        f"{days:,.0f} days to the modelled renewal date" if days
        else "Renewal date not established")

    avs = int(f("avs_vms"))
    obs["R02"] = (
        avs > 0,
        f"{avs:,} VMs routed to AVS, which now needs a portable subscription bought "
        "from the incumbent" if avs else "No AVS workloads in this plan")

    dual = f("dual_run_months")
    obs["R03"] = (
        dual < 1.0,
        f"{dual:.1f} months of platform overlap assumed per wave"
        + ("" if dual >= 1.0 else " -- below the point where the line is material"))

    window = f("observation_days")
    obs["R04"] = (
        window < 30,
        f"{window:.0f}-day performance observation window"
        + (" -- under the 30-day minimum" if window < 30 else ""))

    obs["R05"] = (
        bool(facts.get("agentless_replication", True)),
        "Agentless replication selected -- it borrows IOPS from the production SAN"
        if facts.get("agentless_replication", True)
        else "Agent-based replication selected for this plan")

    overhead = f("platform_overhead_pct")
    obs["R06"] = (
        overhead <= 0,
        f"{overhead:.0f}% landing-zone overhead modelled on top of compute and storage"
        + (" -- the surrounding services are not costed" if overhead <= 0 else ""))

    obs["R07"] = (
        not facts.get("dr_enabled", False),
        "Disaster recovery is modelled in the run cost" if facts.get("dr_enabled")
        else "No DR capability costed on the target")

    blockers = int(f("appliance_blockers"))
    obs["R08"] = (
        blockers == 0,
        f"{blockers:,} appliance or platform blockers identified in the estate"
        if blockers else "No blockers identified -- which usually means none looked for")

    obs["R09"] = (
        not facts.get("backup_enabled", False),
        "Backup is costed on the target" if facts.get("backup_enabled")
        else "No backup costed on the target")

    months = f("elapsed_months")
    obs["R10"] = (
        months > 18,
        f"{months:.1f}-month programme, so dual operations run for at least that long")

    local = int(f("azure_local_vms"))
    obs["R12"] = (
        local > 0,
        f"{local:,} VMs targeted at Azure Local, which has no test-migration action"
        if local else "No Azure Local workloads in this plan")

    obs["R15"] = (
        avs > 0,
        "Applies to every workload sitting on a bridge platform"
        if avs else "No bridge platform in this plan")

    out = []
    for r in REGISTER:
        if r.id in obs:
            triggered, note = obs[r.id]
            status = TRIGGERED if triggered else CLEAR
        else:
            status, note = ADVISORY, "Not observable from the model -- confirm with the programme"
        out.append({"id": r.id, "risk": r.risk, "impact": r.impact,
                    "mitigation": r.mitigation, "owner": r.owner,
                    "status": status, "observation": note})
    return out


def summary(rows: list[dict]) -> dict:
    n_trig = sum(1 for r in rows if r["status"] == TRIGGERED)
    return {
        "total": len(rows),
        "triggered": n_trig,
        "clear": sum(1 for r in rows if r["status"] == CLEAR),
        "advisory": sum(1 for r in rows if r["status"] == ADVISORY),
        "high_triggered": sum(1 for r in rows
                              if r["status"] == TRIGGERED and r["impact"] == HIGH),
    }
