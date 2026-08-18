"""Broadcom exit strategy: exposure, archetypes, scenarios and delivery discipline.

The rest of this application answers "what does Azure cost and how long does it
take". That is the second question. The first one, for an organisation on
Broadcom-era VMware, is "what is my exposure, what are my options, and what does
waiting cost me" -- and it has a deadline attached, which nothing else here
models.

Two facts drive everything in this module:

* **"Do nothing while we decide" is not neutral.** It is a decision to buy from
  Broadcom, because both the incumbent platform and the Azure VMware Solution
  landing zone now require a Broadcom-sourced subscription.
* **Azure VMware Solution does not remove the Broadcom relationship, it
  relocates it.** Since the hyperscaler licensing change, AVS requires a
  portable VCF subscription the customer buys from Broadcom directly. An
  organisation whose objective is to leave Broadcom cannot reach that objective
  via AVS, and this module is what stops the rest of the application implying
  otherwise.

Dates are evaluated against the real clock, never hard-coded as "ten weeks", so
the urgency shown is the urgency on the day somebody opens the page.

No Streamlit and no other core module is imported here: this is the data and the
arithmetic, and the views do the presenting.
"""

import datetime as _dt
from dataclasses import dataclass

# --------------------------------------------------------------------------
# Licensing milestones
# --------------------------------------------------------------------------
@dataclass
class Milestone:
    date: str                 # ISO
    title: str
    detail: str
    consequence: str
    applies_when: str         # who this actually bites


MILESTONES = [
    Milestone(
        "2026-11-01",
        "AVS pay-as-you-go must supply a portable VCF key",
        "Azure VMware Solution deployments still running on a Microsoft-included "
        "VCF licence must supply a portable VCF subscription purchased directly "
        "from Broadcom.",
        "An AVS estate that misses this is out of compliance, and the remedy is a "
        "Broadcom purchase made under time pressure rather than at a negotiation.",
        "You run any AVS on pay-as-you-go with an included licence.",
    ),
    Milestone(
        "2027-10-01",
        "vSphere 8 reaches end of general support",
        "The vSphere 8 line, including Standard and Enterprise Plus, is frozen at "
        "Update 3 and has no version 9 successor.",
        "Any estate on those editions is running a platform with no forward "
        "roadmap, which is a support and audit position as much as a technical one.",
        "You are on vSphere 8 Standard or Enterprise Plus.",
    ),
]

# Licensing changes already in force. Not deadlines -- the ground the plan stands on.
IN_FORCE = [
    ("Perpetual licensing withdrawn",
     "All new entitlement is subscription and renews in perpetuity. Organisations "
     "that capitalised licences and budgeted only for support renewal lost the "
     "economic model they planned around."),
    ("Per-core licensing with a 16-core minimum per CPU",
     "Hosts with fewer than sixteen cores per socket are billed for cores they do "
     "not have, which changes the economics of the hardware refresh decision."),
    ("The catalogue collapsed into bundles",
     "Principally VMware Cloud Foundation and vSphere Foundation, so networking "
     "and storage capability is bought whether or not it is used."),
    ("vSAN moved to capacity-based licensing",
     "Storage growth became a licensing event rather than a hardware event, which "
     "penalises storage-dense clusters."),
    ("AVS licensing moved to bring-your-own",
     "New AVS nodes require a portable VCF subscription held by the customer. The "
     "node price fell; the Broadcom line item did not disappear, it moved onto "
     "your paper."),
    ("Renewal mechanics became punitive",
     "Late renewal attracts an uplift on the first-year price with no meaningful "
     "grace period, so the renewal date is a financial control, not an "
     "administrative one."),
]


def days_until(iso_date: str, today: _dt.date | None = None) -> int:
    today = today or _dt.date.today()
    return (_dt.date.fromisoformat(iso_date) - today).days


def milestone_status(m: Milestone, today: _dt.date | None = None) -> dict:
    """Days remaining and an urgency band, computed against the real clock."""
    d = days_until(m.date, today)
    if d < 0:
        band, label = "passed", "Passed"
    elif d <= 90:
        band, label = "critical", f"{d} days"
    elif d <= 365:
        band, label = "warning", f"{d // 30} months"
    else:
        band, label = "watch", f"{d // 30} months"
    return {"days": d, "band": band, "label": label,
            "date": _dt.date.fromisoformat(m.date).strftime("%d %B %Y")}


# --------------------------------------------------------------------------
# Archetypes: five ways to answer the question, not fourteen products
# --------------------------------------------------------------------------
@dataclass
class Archetype:
    key: str
    name: str
    dependency: str          # what happens to the Broadcom line
    ops_change: str
    best_for: str


ARCHETYPES = [
    Archetype("A", "Stay and optimise", "Retained, renegotiated", "None",
              "Estates where operational maturity, not licence cost, is the "
              "binding constraint."),
    Archetype("B", "Managed VMware in cloud", "Relocated to you (BYOL)", "Minimal",
              "Time-boxed bridging of workloads that cannot re-platform inside "
              "the window."),
    Archetype("C", "Cloud-native rehost and refactor", "Eliminated", "Substantial",
              "The majority of a typical enterprise estate. The strategic "
              "destination."),
    Archetype("D", "Alternative on-premises hypervisor", "Eliminated",
              "Moderate to substantial",
              "Workloads that must stay on-premises for residency, latency or "
              "regulatory reasons."),
    Archetype("E", "Kubernetes-unified platform", "Eliminated", "Substantial",
              "Organisations already committed to a container operating model "
              "with a platform team to sustain it."),
]
ARCHETYPE_BY_KEY = {a.key: a for a in ARCHETYPES}

# Broadcom dependency verdict per platform. Keys match core.platforms.
ELIMINATED, RELOCATED, RETAINED = "Eliminated", "Relocated", "Retained"

DEPENDENCY = {
    "Stay on VMware (VCF 9, renegotiated)": (RETAINED, "A", "Control case only"),
    "Azure VMware Solution (AVS)": (RELOCATED, "B", "Bridge only"),
    "Azure native IaaS (rehost)": (ELIMINATED, "C", "Primary"),
    "Azure PaaS (replatform / refactor)": (ELIMINATED, "C", "Parallel track"),
    "Azure Local (formerly Azure Stack HCI)": (ELIMINATED, "D", "On-prem residual"),
    "Azure Stack Hub": (ELIMINATED, "D", "On-prem residual"),
    "Azure Arc only (stay put, manage from Azure)": (RETAINED, "A", "Control case only"),
    "Microsoft Hyper-V / Windows Server + SCVMM": (ELIMINATED, "D", "On-prem residual"),
    "Nutanix AHV on-premises": (ELIMINATED, "D", "On-prem residual"),
    "Nutanix Cloud Clusters (NC2) on Azure": (ELIMINATED, "B", "Shortlist -- AVS alternative"),
    "Red Hat OpenShift Virtualization": (ELIMINATED, "E", "Only if already adopted"),
    "Proxmox VE": (ELIMINATED, "D", "Non-production only"),
    "Google Cloud VMware Engine (GCVE)": (RELOCATED, "B", "Bridge only"),
    "Oracle Cloud VMware Solution / OCI": (RELOCATED, "B", "Bridge only"),
}

DEPENDENCY_NOTE = {
    RELOCATED: "Still requires a VCF subscription you buy from Broadcom. The line "
               "item moves onto your paper; it does not go away.",
    RETAINED: "The Broadcom subscription continues as-is.",
    ELIMINATED: "No Broadcom subscription remains for workloads that land here.",
}


def dependency_for(platform: str) -> tuple:
    """(verdict, archetype key, strategic fit) for a platform name."""
    return DEPENDENCY.get(platform, (ELIMINATED, "D", "Not assessed"))


# --------------------------------------------------------------------------
# Estate segmentation benchmark
# --------------------------------------------------------------------------
@dataclass
class Segment:
    name: str
    low: float               # per cent of VM count
    high: float
    strategies: tuple        # 7R strategies in this application that map here
    destination: str
    rationale: str = ""      # why that destination, for the target-state table


SEGMENTS = [
    Segment("Retire", 10, 25, ("Retire",),
            "Decommission -- the cheapest migration is the one not performed.",
            "Between a tenth and a quarter of a typical estate has no active users. "
            "Removing it is the highest-return activity in the programme."),
    Segment("Replace", 5, 15, ("Repurchase",),
            "SaaS or an Azure managed service.",
            "Commodity function with a viable managed equivalent. Avoids migrating "
            "something that should not exist as a VM."),
    Segment("Refactor / replatform", 10, 25, ("Replatform", "Refactor"),
            "Azure PaaS, AKS, Azure SQL, Azure Database for PostgreSQL / MySQL.",
            "Best long-run economics where the application team has capacity. Run it "
            "as a parallel track, never on the critical path of the exit."),
    Segment("Rehost", 35, 55, ("Rehost",),
            "Azure IaaS.",
            "Removes the Broadcom relationship entirely, provides elastic consumption "
            "and creates the on-ramp to later modernisation."),
    Segment("Relocate", 5, 15, ("Relocate",),
            "AVS as a time-boxed bridge, or NC2 on Azure.",
            "For workloads that cannot re-platform inside the window. NC2 should be "
            "evaluated against AVS specifically, because it carries no Broadcom "
            "requirement and AVS does."),
    Segment("Retain on-premises", 5, 20, ("Retain",),
            "Azure Local or Hyper-V.",
            "Residency, latency, regulatory or OT-integration constraints. Evaluate "
            "Nutanix AHV as the alternative if the residual is large."),
]


def segmentation_scorecard(strategy_counts: dict, total_vms: int) -> list:
    """Compare this estate's disposition against the benchmark bands.

    Bands are indicative for a typical enterprise estate, so a figure outside one
    is a prompt to explain, not a fault. The value is in being asked the question
    before a steering committee asks it.
    """
    rows = []
    for seg in SEGMENTS:
        n = sum(int(strategy_counts.get(s, 0)) for s in seg.strategies)
        pct = (n / total_vms * 100) if total_vms else 0.0
        if pct < seg.low:
            verdict = "below"
        elif pct > seg.high:
            verdict = "above"
        else:
            verdict = "in band"
        rows.append({"segment": seg.name, "vms": n, "pct": pct,
                     "band": f"{seg.low:.0f}-{seg.high:.0f}%", "verdict": verdict,
                     "destination": seg.destination})
    return rows


# --------------------------------------------------------------------------
# Commercial scenarios
# --------------------------------------------------------------------------
SCENARIOS = [
    ("A", "Renew as quoted",
     "Accept the Broadcom renewal at the quoted position and stay on VMware.",
     "Renewal multiple at each subsequent cycle, core-count growth, vSAN capacity "
     "growth, hardware refresh timing."),
    ("B", "Renew after negotiation",
     "Renew with documented alternatives, negotiated term bands, renewal caps and "
     "portability language.",
     "Achievable discount, term length committed, whether ramp-down is secured, "
     "and the cost of running the evaluation itself."),
    ("C", "Exit over the plan period",
     "Phased migration with residual Broadcom spend through the transition, then "
     "surrender of the subscription.",
     "Double-run duration is the dominant variable, then migration effort, Azure "
     "run cost after right-sizing, and the DR rebuild."),
]

# Cost lines that must appear in Scenario C. The flag says whether this
# application models the line or whether it has to be added by hand.
SCENARIO_C_LINES = [
    ("Residual Broadcom subscription for the whole transition", True,
     "At the renewal price, not today's price."),
    ("Azure compute, storage, backup, monitoring and networking", True,
     "After right-sizing, with reservation and savings plan coverage modelled."),
    ("Azure Hybrid Benefit and Extended Security Updates", True,
     "Quantified rather than assumed."),
    ("Egress and inter-region data transfer", False,
     "Steady-state egress is modelled in the run cost, but the expensive part is not: "
     "the transitional period when applications straddle both environments and every "
     "call between them crosses a charged boundary. Size it from the dependency map, "
     "for the length of the double-run."),
    ("Double-run cost across the transition", True,
     "Both platforms paid for simultaneously. Frequently the largest single line "
     "and the one most often omitted."),
    ("Migration tooling beyond the free window", True,
     "Azure Migrate replication charges plus any third-party tooling."),
    ("Professional services and internal effort", True,
     "Including application-owner time the programme consumes but does not pay for."),
    ("Disaster recovery re-engineering", False,
     "Replication topologies, runbooks, orchestration and failover testing. Site "
     "Recovery Manager logic does not transfer. Can consume half the timeline."),
    ("Backup re-platforming", False,
     "Changed-block tracking, application-aware processing, instant recovery and "
     "immutability each need verifying on the target rather than assuming."),
    ("Networking and security reconstruction", False,
     "Distributed switch config, port groups and any NSX micro-segmentation policy "
     "must be recreated by hand on a non-VMware target."),
    ("Third-party virtual appliance remediation", False,
     "Vendor OVAs supported on ESXi only. Each is a vendor conversation and some "
     "have no answer inside the window."),
    ("Training and the transitional dual-operations burden", False,
     "Two operating models run by one team. A real cost and a real attrition risk."),
    ("Data centre exit or contraction benefit", False,
     "Facility, power, cooling, hardware refresh avoided and support contracts "
     "released. This one is in your favour."),
    ("Contingency of 15-20%", False,
     "And the sponsor should be told why."),
]

NEGOTIATION_LEVERS = [
    ("Term length matched to the migration plan",
     "Rather than a default multi-year commitment that outlives the estate."),
    ("A ramp-down structure",
     "Entitlement reduces as clusters are decommissioned, instead of a flat "
     "commitment across the term."),
    ("Renewal price caps for subsequent cycles",
     "The protection that matters most, because the exposure is the next quote, "
     "not this one."),
    ("Price holds on growth cores",
     "So capacity added during the transition does not reprice the whole "
     "agreement."),
    ("Portability language",
     "Entitlement can move between on-premises hosts and Azure VMware Solution as "
     "the estate shifts, turning residual spend into a transition instrument."),
    ("SKU availability and upgrade rights in writing",
     "Confirmed for your geography and agreement type specifically."),
    ("Renewal date mechanics and late-renewal uplift, stated",
     "So the date becomes a managed financial control."),
]


# --------------------------------------------------------------------------
# Phased roadmap
# --------------------------------------------------------------------------
PHASES = [
    ("Phase 0", "Mobilise and negotiate", "0-6 weeks",
     "Contract position established, renewal options quantified, exit governance "
     "stood up, no technical lock-in accepted.",
     ["Establish exact renewal dates, entitled core counts, edition mix and any "
      "perpetual-key exposure.",
      "Confirm whether any AVS estate is pay-as-you-go with a Microsoft-included "
      "licence.",
      "Open the renewal negotiation with documented alternatives in hand.",
      "Deploy discovery immediately -- its output feeds the plan and the "
      "negotiation equally."]),
    ("Phase 1", "Discover and assess", "6-12 weeks",
     "Full estate discovery with a minimum 30-day dependency observation window, "
     "and a segmented disposition per application.",
     ["Observe performance for at least 30 days before acting on any sizing.",
      "Run dependency analysis and validate every inferred dependency with the "
      "application owner.",
      "Apply the segmentation model and name an owner for each disposition."]),
    ("Phase 2", "Landing zone and pilot", "8-12 weeks",
     "Azure landing zone hardened, tooling proven, two or three low-criticality "
     "waves cut over end to end.",
     ["Build governance, tagging, policy and network segmentation before the first "
      "wave, not after several hundred VMs have landed.",
      "Prove the rollback path, not just the migration path."]),
    ("Phase 3", "Wave execution", "9-18 months",
     "The bulk of the estate migrated on a repeatable cadence with published entry "
     "and exit criteria.",
     ["Hold the change gates. A wave that starts without its exit criteria met "
      "moves the problem downstream.",
      "Right-size within 30 days of each wave rather than at the end."]),
    ("Phase 4", "Decommission and optimise", "3-6 months",
     "VMware footprint retired, subscription surrendered, FinOps discipline "
     "embedded.",
     ["Release cores as clusters empty -- this is what ends the double-run cost.",
      "Surrender the subscription deliberately, on a date somebody owns."]),
]

TOTAL_ELAPSED = ("18 to 30 months",
                 "Mobilisation to full decommission, for an enterprise estate of a "
                 "few hundred VMs. Programmes promising materially less usually "
                 "exclude application remediation, DR re-engineering and "
                 "operational readiness -- which together often exceed the "
                 "migration itself.")


# --------------------------------------------------------------------------
# Anti-patterns, checked against the live scenario
# --------------------------------------------------------------------------
def check_antipatterns(facts: dict) -> list:
    """Score the ten recurring failure modes against the current model.

    ``facts`` is a plain dict so this module stays independent of the pipeline.
    Each result is (name, triggered, verdict, why it matters). "Triggered" means
    this scenario currently exhibits the pattern; the ones that cannot be tested
    from the model are returned as advisory so they still get read out.
    """
    total = max(int(facts.get("total_vms", 0)), 1)
    retire_pct = facts.get("retire_pct", 0.0)
    avs_vms = int(facts.get("avs_vms", 0))
    dual_run_months = facts.get("dual_run_months", 0.0)
    elapsed_months = facts.get("elapsed_months", 0.0)
    paas_vms = int(facts.get("paas_vms", 0))
    blockers = int(facts.get("appliance_blockers", 0))
    out = []

    out.append((
        "Treating AVS as an exit",
        avs_vms > 0,
        f"{avs_vms:,} VMs routed to Azure VMware Solution" if avs_vms
        else "Nothing routed to AVS",
        "AVS keeps a Broadcom subscription, now held by you rather than bundled. "
        "It is a bridge with a decommission date, or it is a lateral move that "
        "spent a migration budget."))

    out.append((
        "Migrating without retiring first",
        retire_pct < 10.0,
        f"{retire_pct:.0f}% of the estate retired",
        "Between a tenth and a quarter of a typical estate has no active users. "
        "Paying to migrate it is the most avoidable cost in the programme."))

    out.append((
        "Building the case on licence delta alone",
        not facts.get("dr_rebuild_costed", False),
        "DR re-engineering and backup re-platforming are not costed here",
        "Double-run, DR rebuild and application remediation are routinely omitted, "
        "and the case fails scrutiny six months in when the real numbers surface."))

    out.append((
        "Under-scoping the double run",
        dual_run_months < 1.0,
        f"{dual_run_months:.1f} months of overlap assumed per wave",
        "Both platforms are paid for through the whole transition. On an 18-month "
        "programme this is frequently the single largest line."))

    out.append((
        "Letting the pilot define the plan",
        elapsed_months > 0 and elapsed_months < 6,
        f"{elapsed_months:.1f} months modelled end to end",
        "A realistic enterprise exit runs 18 to 30 months from mobilisation to "
        "decommission. A materially shorter plan is usually excluding remediation, "
        "DR and operational readiness."))

    out.append((
        "Ignoring third-party virtual appliances",
        blockers == 0,
        f"{blockers:,} appliance or platform blockers identified",
        "Vendor OVAs supported on ESXi only surface late. Each is a vendor "
        "conversation and some have no answer inside the window."))

    out.append((
        "No named exit date for the bridge",
        avs_vms > 0,
        "Applies while any workload sits on a bridge platform",
        "Any transitional platform without a board-visible decommission date "
        "becomes permanent."))

    # Advisory: real failure modes this model cannot observe.
    for name, why in [
        ("Choosing the destination before segmenting the estate",
         "A single destination is picked on cost grounds, then discovery finds a "
         "fifth of the estate cannot go there and the programme acquires an "
         "unplanned second platform mid-flight."),
        ("Starting waves before the landing zone is finished",
         "Governance, tagging, policy and segmentation get retrofitted across "
         "hundreds of migrated VMs, at several times the cost of building first."),
        ("Assuming backup vendor support is equivalent",
         "The vendor supports the target, but changed-block tracking or "
         "application-aware processing behave differently. Discovered during the "
         "first restore test, which is the worst possible moment."),
    ]:
        out.append((name, None, "Not observable from the model", why))

    return out


# --------------------------------------------------------------------------
# Discovery data checklist.
#
# The point of this list is the "source" column, not the items. Ten of the
# fifteen are not produced by any discovery tool -- they come from the CMDB,
# the service owners, the network team and procurement. The rest of this
# application argues that the migration tooling covers only part of the estate;
# this is the list that proves it, and it is the one a programme skips.
# --------------------------------------------------------------------------
TOOL_SOURCED = "Discovery tooling"
PROGRAMME_SOURCED = "Programme-sourced"

# (item, source, who supplies it, the column in an uploaded estate that
#  evidences it -- or None where nothing in an inventory export can, and the
#  core.extract target that can read it out of a client document, or None where
#  no document closes it)
DISCOVERY_CHECKLIST = [
    ("VM inventory: name, vCPU, memory, disk count and size, NICs, OS version, "
     "power state", TOOL_SOURCED, "Azure Migrate discovery", "vm_name", None),
    ("Performance profile: CPU, memory, disk IOPS and throughput, network, over a "
     "30-day window", TOOL_SOURCED, "Azure Migrate discovery", "cpu_p95_pct", None),
    ("Installed software, roles and features per guest", TOOL_SOURCED,
     "Azure Migrate guest inventory", None, None),
    ("SQL Server instance and database inventory with compatibility findings",
     TOOL_SOURCED, "Azure Migrate + Data Migration Assistant", "db_engine", None),
    ("Network dependency map", TOOL_SOURCED,
     "Azure Migrate dependency analysis", None, None),
    ("Application-to-server mapping and business criticality", PROGRAMME_SOURCED,
     "CMDB and application owners", "app_name", None),
    ("Recovery time and recovery point objectives per application",
     PROGRAMME_SOURCED, "Service owners", None, 'service_levels'),
    ("Change window availability and blackout periods per application",
     PROGRAMME_SOURCED, "Service owners", None, 'service_levels'),
    ("Third-party virtual appliance inventory with vendor support statements",
     PROGRAMME_SOURCED, "Vendor engagement", None, 'appliances'),
    ("Hardware-bound licensing: dongles, MAC-bound licences, licence servers",
     PROGRAMME_SOURCED, "Application owners", "licence_mac_bound", 'hardware_licensing'),
    ("Existing DR topology, replication pairs and Site Recovery Manager runbook "
     "logic", PROGRAMME_SOURCED, "Infrastructure team", None, 'backup_dr'),
    ("Backup policy, retention, immutability and restore-test evidence",
     PROGRAMME_SOURCED, "Backup team", None, 'backup_dr'),
    ("NSX micro-segmentation rule set and distributed switch configuration",
     PROGRAMME_SOURCED, "Network team", None, None),
    ("IP addressing plan, DNS dependencies and hard-coded address inventory",
     PROGRAMME_SOURCED, "Network and application teams", None, None),
    ("VMware entitlement position: core counts, editions, renewal dates, "
     "perpetual-key exposure", PROGRAMME_SOURCED, "Procurement", None, 'entitlement'),
]


def discovery_coverage(columns, from_documents=()) -> list[dict]:
    """Score the discovery checklist against what is actually held.

    ``columns`` is whatever the loaded inventory carries; ``from_documents`` is
    the set of ``core.extract`` target keys read from client documents this
    session. An item is "held" only where one of those two evidences it --
    everything else is outstanding, including every item no inventory export
    could ever satisfy. That asymmetry is the point: a full-looking estate file
    still leaves two thirds of this list open, and closing the rest means going
    and asking people for documents.
    """
    cols, docs = set(columns), set(from_documents)
    out = []
    for item, source, who, evidence, target in DISCOVERY_CHECKLIST:
        in_estate = bool(evidence) and evidence in cols
        in_doc = bool(target) and target in docs
        # Kept short deliberately: this renders in a table column, and an
        # explanation truncated mid-sentence tells the reader less than a
        # three-word one that fits.
        if in_estate:
            note = f"Present as `{evidence}`"
        elif in_doc:
            note = "Read from a document"
        elif evidence:
            note = "Not in this inventory"
        elif target:
            note = "Needs a document"
        else:
            note = "No inventory has it"
        out.append({
            "item": item, "source": source, "who": who,
            "held": in_estate or in_doc, "from_document": in_doc,
            "target": target, "evidence": note,
        })
    return out


# --------------------------------------------------------------------------
# Decision checkpoints and the first ninety days.
#
# The phases above say what happens. These say who has to decide what, on what
# evidence -- which is the part that slips, because a checkpoint without named
# evidence is a meeting rather than a gate.
# --------------------------------------------------------------------------
CHECKPOINTS = [
    ("DC1", "Contract position",
     "What are we actually committed to, and when?",
     "Entitlement inventory, renewal dates, SKU availability confirmed in writing.",
     "Procurement / commercial lead"),
    ("DC2", "Estate disposition",
     "What fraction of the estate can actually go to Azure IaaS?",
     "Completed discovery, 30-day performance data, validated dependency map, "
     "exception log.",
     "Infrastructure lead"),
    ("DC3", "Platform selection",
     "Which destinations for which segments?",
     "Three-scenario business case, scored matrices re-run against the client's own "
     "weightings, shortlist head-to-heads.",
     "Architecture authority"),
    ("DC4", "Landing zone gate",
     "Are the controls real and enforced?",
     "Policy compliance report, pilot wave evidence, demonstrated rollback.",
     "Infrastructure lead"),
    ("DC5", "Volume authorisation",
     "Are we ready to run waves at cadence?",
     "Published runbook, agreed change windows, resourced DR workstream, "
     "restore-test evidence.",
     "Programme director"),
    ("DC6", "Surrender",
     "Can the incumbent subscription be reduced or surrendered?",
     "Core release tracking, cluster decommission evidence, contractual boundary "
     "confirmed.",
     "Procurement / commercial lead"),
]

NEXT_STEPS = [
    ("Next 30 days", [
        "Confirm the AVS licensing position against the portable-subscription "
        "deadline. This is the only genuinely time-critical item.",
        "Establish the contract baseline: renewal dates, entitled core counts, "
        "edition mix and any perpetual-key exposure.",
        "Create the migration project and deploy the discovery appliance. The "
        "30-day observation window should start now, regardless of where the "
        "platform decision lands.",
        "Stand up programme governance and appoint a named decision owner for the "
        "platform selection.",
        "Open the parallel renewal conversation, framed around the documented "
        "alternatives evaluation.",
    ]),
    ("Next 60 days", [
        "Complete estate discovery and produce the initial segmentation with a "
        "disposition per application.",
        "Confirm the shortlist: Azure IaaS as primary, with a formal head-to-head of "
        "AVS against NC2 for the relocate segment, and Azure Local against Hyper-V "
        "against Nutanix AHV for the on-premises residual.",
        "Baseline source SAN IOPS headroom and decide agentless against agent-based "
        "replication per workload class.",
        "Identify and log every exception -- ESXi-only appliances, hardware-bound "
        "licensing, unsupported guests, low-latency paths and OT dependencies.",
        "Produce the three-scenario business case with the surrounding cost lines "
        "modelled separately from the tool's output.",
    ]),
    ("Next 90 days", [
        "Platform decision taken and ratified by the steering committee.",
        "Azure landing zone built and hardened, with controls demonstrably enforced.",
        "Pilot waves executed end to end, including test migration, cutover, "
        "validation and rollback rehearsal.",
        "Wave runbook, entry and exit criteria and rollback position published, based "
        "on what the pilot actually demonstrated.",
        "Negotiation concluded, with the ramp-down and portability positions either "
        "secured or formally recorded as declined.",
    ]),
]


# --------------------------------------------------------------------------
# Questions to table at renewal.
#
# The levers above are what to ask for. These are the questions that establish
# whether the ask is even available, and they are written to be put directly to
# the vendor or reseller by procurement rather than paraphrased by an architect.
# --------------------------------------------------------------------------
RENEWAL_QUESTIONS = [
    ("Price", "What is the confirmed list price and available discount structure per "
     "core, per year, for the specific bundle and term proposed?"),
    ("Availability", "Which bundles are actually available for purchase in our "
     "geography and under our agreement type, and can that be confirmed in writing?"),
    ("Core count", "What is the licensed core count under the sixteen-core-per-CPU "
     "minimum for our exact host configuration, and how many of those cores are "
     "phantom?"),
    ("Capacity", "How is vSAN capacity licensed against our current and projected "
     "capacity, and what happens commercially when capacity grows?"),
    ("Term", "What term bands are available, and what is the discount differential "
     "between them?"),
    ("Cap", "Will you commit to a renewal price cap for the subsequent cycle, and at "
     "what level?"),
    ("Growth", "Will you commit to a price hold on growth cores added during the "
     "term?"),
    ("Ramp-down", "Can the subscription be structured as a ramp-down matched to our "
     "published decommission plan?"),
    ("Portability", "Does the subscription include portability between on-premises "
     "hosts and hyperscaler platforms, and is that stated in the contract rather than "
     "in guidance?"),
    ("Renewal date", "What is the exact renewal date mechanic, and what uplift applies "
     "to a late renewal?"),
    ("Compliance", "What is our current compliance position against entitlement, and "
     "are there any open audit findings?"),
    ("Upgrade path", "What is the supported upgrade path and end-of-support date for "
     "every edition we currently hold?"),
    ("Support", "What happens to our support entitlement and escalation path given the "
     "changes to the partner programme?"),
]
