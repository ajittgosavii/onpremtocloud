"""Migration tooling market: what else exists besides Azure Migrate, and when
each one is actually the right answer.

Scores are 1-5 on each dimension and are deliberately opinionated. They are
starting points for a client conversation, not vendor-supplied marketing
numbers -- every one is defensible from the capability notes on the same row.
"""

import numpy as np
import pandas as pd

# Dimensions the scores are given against.
DIMENSIONS = {
    "discovery": "Discovery & inventory depth",
    "dependency": "Application dependency mapping",
    "assessment": "Assessment & right-sizing",
    "replication": "Replication & cutover capability",
    "downtime": "Minimal-downtime capability",
    "os_modernisation": "OS/app modernisation in-flight",
    "scale": "Scale & automation for 500+ VMs",
    "multi_target": "Multi-cloud / multi-target",
    "db_migration": "Database migration capability",
    "cost": "Cost efficiency (5 = cheapest)",
    "maturity": "Product maturity & support",
}

_T = [
    dict(
        tool="Azure Migrate (agentless)", vendor="Microsoft", category="Native platform",
        licence="Free (pay only for ASR beyond 180 days, staging storage and Azure resources)",
        scores=dict(discovery=5, dependency=3, assessment=5, replication=4, downtime=3,
                    os_modernisation=1, scale=4, multi_target=1, db_migration=3, cost=5, maturity=5),
        best_for="The default for a VMware-to-Azure rehost. No agents, no licence cost, and the "
                 "assessment output is the one Microsoft support and funding programmes recognise.",
        limits="300 concurrent replications per appliance (500 with scale-out) and 56 disks in "
               "flight; no Data Box seeding; no OS upgrade in flight; shared disks, VM-encrypted "
               "and some UEFI/legacy configurations are unsupported.",
        use_when="Estate is mostly standard Windows/Linux VMs, target is Azure only, and a "
                 "few hours of cutover downtime per app is acceptable.",
    ),
    dict(
        tool="Azure Migrate (agent-based / ASR Mobility Service)", vendor="Microsoft",
        category="Native platform",
        licence="Free for 180 days per instance, then Azure Site Recovery rates",
        scores=dict(discovery=4, dependency=3, assessment=5, replication=5, downtime=4,
                    os_modernisation=1, scale=4, multi_target=1, db_migration=3, cost=5, maturity=5),
        best_for="Physical servers, other hypervisors, and the VMware VMs that agentless cannot "
                 "handle -- encrypted VMs, awkward disk layouts, VMs without usable VMware Tools.",
        limits="Requires installing the Mobility Service in every guest, which means change "
               "windows and a reboot on some OS versions.",
        use_when="Agentless has excluded a subset of the estate, or the source is not vSphere.",
    ),
    dict(
        tool="VMware HCX", vendor="Broadcom", category="Hypervisor-native",
        licence="Included with Azure VMware Solution; VCF subscription otherwise",
        scores=dict(discovery=2, dependency=1, assessment=1, replication=5, downtime=5,
                    os_modernisation=1, scale=4, multi_target=2, db_migration=1, cost=3, maturity=5),
        best_for="Moving VMs into Azure VMware Solution with layer-2 network extension and "
                 "vMotion-class live migration -- effectively zero downtime, no IP change.",
        limits="Target must be a vSphere environment (AVS, GCVE, OCVS). It does not convert "
               "anything to native cloud IaaS, so it defers modernisation rather than delivering it.",
        use_when="You need out of the data centre fast, cannot re-IP, and have accepted AVS as "
                 "a staging platform with a dated exit plan.",
    ),
    dict(
        tool="Zerto", vendor="Hewlett Packard Enterprise", category="Continuous replication",
        licence="Per-VM subscription, typically USD 15-30 per VM per month",
        scores=dict(discovery=2, dependency=1, assessment=2, replication=5, downtime=5,
                    os_modernisation=1, scale=4, multi_target=4, db_migration=2, cost=2, maturity=5),
        best_for="Continuous data protection with seconds-level RPO and journal-based rollback. "
                 "The strongest option when a failed cutover must be reversible in minutes.",
        limits="Priced per VM, so a 547-VM estate is a material line item. It is a replication "
               "engine, not an assessment or planning tool.",
        use_when="Tier 0 workloads where the business will not accept more than a few seconds of "
                 "data loss, or where you want DR and migration on one platform.",
    ),
    dict(
        tool="Carbonite Migrate", vendor="OpenText", category="Continuous replication",
        licence="Per-workload licence, typically USD 200-400 per migrated workload",
        scores=dict(discovery=2, dependency=1, assessment=1, replication=5, downtime=5,
                    os_modernisation=2, scale=3, multi_target=4, db_migration=2, cost=3, maturity=4),
        best_for="Real-time byte-level replication across physical, virtual and cloud with "
                 "cutover measured in minutes. Handles source platforms Azure Migrate will not.",
        limits="Agent-based, so it needs a guest install everywhere. Thin on assessment and "
               "portfolio planning.",
        use_when="Mixed physical/virtual estate, or very tight cutover windows on a subset of apps.",
    ),
    dict(
        tool="RiverMeadow", vendor="RiverMeadow Software", category="SaaS migration platform",
        licence="Per-VM subscription; OS modernisation priced separately",
        scores=dict(discovery=3, dependency=2, assessment=3, replication=4, downtime=3,
                    os_modernisation=5, scale=4, multi_target=5, db_migration=2, cost=3, maturity=4),
        best_for="Migrating and upgrading the guest OS in the same motion -- CentOS 7 to RHEL, "
                 "Windows Server 2012 R2 to 2022 -- which removes the EOL remediation project "
                 "that normally runs before migration.",
        limits="Commercial platform with per-VM cost; OS conversion needs application regression "
               "testing that the tool cannot do for you.",
        use_when="A meaningful share of the estate is on end-of-life OS and you would otherwise "
                 "run a separate upgrade programme first.",
    ),
    dict(
        tool="Cirrus Migrate Cloud", vendor="Cirrus Data Solutions", category="Block-level replication",
        licence="Per-TB or per-host subscription",
        scores=dict(discovery=2, dependency=1, assessment=2, replication=5, downtime=5,
                    os_modernisation=1, scale=4, multi_target=4, db_migration=3, cost=3, maturity=4),
        best_for="Very large, high-churn block storage -- the multi-terabyte database and file "
                 "servers where snapshot-based replication struggles to converge.",
        limits="Storage-centric; contributes little to assessment, dependency mapping or planning.",
        use_when="You have a handful of VMs whose churn rate means agentless replication will "
                 "never catch up.",
    ),
    dict(
        tool="PlateSpin Migrate", vendor="OpenText", category="Workload portability",
        licence="Per-workload perpetual or subscription",
        scores=dict(discovery=3, dependency=1, assessment=2, replication=4, downtime=3,
                    os_modernisation=3, scale=3, multi_target=4, db_migration=1, cost=3, maturity=4),
        best_for="Anywhere-to-anywhere workload portability including physical-to-cloud, with "
                 "strong testing and rollback workflow.",
        limits="Older product line; smaller ecosystem than it once had.",
        use_when="A significant physical server population sits alongside the VMware estate.",
    ),
    dict(
        tool="Veeam Backup & Replication", vendor="Veeam", category="Backup-based migration",
        licence="Already owned by most enterprises (per-VM/VUL licensing)",
        scores=dict(discovery=2, dependency=1, assessment=1, replication=3, downtime=2,
                    os_modernisation=1, scale=3, multi_target=4, db_migration=1, cost=4, maturity=5),
        best_for="Migrating via a backup you already take: restore the VM directly into Azure. "
                 "Zero incremental licence cost when Veeam is already deployed.",
        limits="Restore-based cutover means hours of downtime, not minutes, and there is no "
               "continuous delta sync. Poor fit for large or busy VMs.",
        use_when="Non-production and Tier 3 workloads where downtime is cheap and you want to "
                 "avoid buying anything.",
    ),
    dict(
        tool="Device42", vendor="Freshworks", category="Discovery & dependency",
        licence="Per-device annual subscription",
        scores=dict(discovery=5, dependency=5, assessment=4, replication=1, downtime=1,
                    os_modernisation=1, scale=5, multi_target=5, db_migration=1, cost=2, maturity=4),
        best_for="Agentless discovery and dependency mapping far deeper than Azure Migrate, "
                 "with CMDB reconciliation and application-affinity grouping.",
        limits="Does not migrate anything. It is the planning layer, used alongside a mover.",
        use_when="The CMDB is not trusted and move groups have to be built from evidence -- "
                 "which is the usual situation in a 547-VM estate.",
    ),
    dict(
        tool="Faddom", vendor="Faddom", category="Discovery & dependency",
        licence="Per-server subscription; rapid deployment",
        scores=dict(discovery=4, dependency=5, assessment=3, replication=1, downtime=1,
                    os_modernisation=1, scale=4, multi_target=4, db_migration=1, cost=3, maturity=3),
        best_for="Agentless application dependency mapping that stands up in hours rather than "
                 "weeks -- useful when the dependency question is blocking wave planning.",
        limits="Mapping only; no assessment costing or migration execution.",
        use_when="You need a dependency map quickly and cannot wait out a two-week agentless "
                 "Azure Migrate collection.",
    ),
    dict(
        tool="Corent SurPaaS", vendor="Corent Technology", category="Modernisation platform",
        licence="Per-workload subscription; Azure Migrate certified partner",
        scores=dict(discovery=3, dependency=3, assessment=4, replication=3, downtime=2,
                    os_modernisation=4, scale=3, multi_target=3, db_migration=3, cost=3, maturity=3),
        best_for="Analysing applications for SaaS-ification and containerisation rather than "
                 "just rehosting them.",
        limits="Aimed at ISVs and application transformation; overkill for a straight data "
               "centre exit.",
        use_when="The client has its own software products it wants to re-deliver as SaaS.",
    ),
    dict(
        tool="Turbonomic", vendor="IBM", category="Optimisation",
        licence="Per-workload subscription",
        scores=dict(discovery=3, dependency=3, assessment=5, replication=1, downtime=1,
                    os_modernisation=1, scale=5, multi_target=5, db_migration=1, cost=2, maturity=5),
        best_for="Continuous right-sizing before and after migration, with actions it can execute "
                 "automatically. Typically finds another 10-25% after the initial migration.",
        limits="No migration capability. Value lands post-migration, so it is often deferred -- "
               "and then never bought.",
        use_when="The business case depends on sustained optimisation rather than a one-off "
                 "right-sizing at cutover.",
    ),
    dict(
        tool="Azure Database Migration Service + DMA", vendor="Microsoft", category="Database",
        licence="Free (standard tier); premium tier billed",
        scores=dict(discovery=3, dependency=1, assessment=4, replication=4, downtime=4,
                    os_modernisation=1, scale=3, multi_target=1, db_migration=5, cost=5, maturity=5),
        best_for="Moving SQL Server to Azure SQL Managed Instance or Azure SQL Database with "
                 "online replication, and PostgreSQL/MySQL to their Flexible Server equivalents.",
        limits="Database only. Data Migration Assistant must clear compatibility blockers first.",
        use_when="Any replatform of a database tier -- this is the tool, not Azure Migrate.",
    ),
    dict(
        tool="Azure Migrate: application containerisation", vendor="Microsoft",
        category="Modernisation",
        licence="Free",
        scores=dict(discovery=2, dependency=2, assessment=3, replication=2, downtime=2,
                    os_modernisation=5, scale=2, multi_target=1, db_migration=1, cost=5, maturity=3),
        best_for="Containerising ASP.NET and Java web apps straight onto AKS or App Service "
                 "without touching source code.",
        limits="Narrow applicability -- web tiers only, and it will not handle stateful or "
               "heavily-integrated applications.",
        use_when="A meaningful web tier exists and the client wants a modernisation proof point "
                 "inside the migration programme.",
    ),
    dict(
        tool="ReadyWorks", vendor="ReadyWorks", category="Orchestration",
        licence="Platform subscription",
        scores=dict(discovery=3, dependency=3, assessment=3, replication=1, downtime=1,
                    os_modernisation=1, scale=5, multi_target=5, db_migration=1, cost=2, maturity=3),
        best_for="Orchestrating the human side at scale -- owner outreach, scheduling, approvals "
                 "and comms across hundreds of application owners.",
        limits="No technical migration capability whatsoever.",
        use_when="The bottleneck is coordination and stakeholder sign-off rather than technology, "
                 "which is common past ~300 VMs.",
    ),
    dict(
        tool="Rubrik / Commvault Cloud", vendor="Rubrik / Commvault", category="Backup-based",
        licence="Existing data-protection licence",
        scores=dict(discovery=2, dependency=1, assessment=2, replication=3, downtime=2,
                    os_modernisation=1, scale=3, multi_target=4, db_migration=2, cost=4, maturity=5),
        best_for="Recovering workloads directly into Azure from an existing backup estate, and "
                 "covering the migration's own rollback position.",
        limits="Downtime-heavy cutover; not a primary migration engine at this scale.",
        use_when="You want a proven rollback path and already pay for the platform.",
    ),
]

_SCENARIO_WEIGHTS = {
    "Fast, low-cost data centre exit": dict(
        discovery=1.0, dependency=1.0, assessment=1.2, replication=1.6, downtime=1.0,
        os_modernisation=0.4, scale=1.5, multi_target=0.3, db_migration=0.6, cost=1.8, maturity=1.4),
    "Minimum downtime for critical apps": dict(
        discovery=0.6, dependency=0.9, assessment=0.7, replication=1.6, downtime=2.2,
        os_modernisation=0.4, scale=1.2, multi_target=0.5, db_migration=1.0, cost=0.7, maturity=1.4),
    "Modernise while migrating": dict(
        discovery=1.0, dependency=1.2, assessment=1.2, replication=0.9, downtime=0.7,
        os_modernisation=2.2, scale=1.0, multi_target=0.8, db_migration=1.6, cost=0.8, maturity=1.0),
    "End-of-life OS estate": dict(
        discovery=1.1, dependency=0.8, assessment=1.0, replication=1.1, downtime=0.7,
        os_modernisation=2.4, scale=1.2, multi_target=0.6, db_migration=0.7, cost=1.0, maturity=1.1),
    "Dependency mapping is the blocker": dict(
        discovery=1.8, dependency=2.4, assessment=1.2, replication=0.6, downtime=0.4,
        os_modernisation=0.4, scale=1.3, multi_target=0.7, db_migration=0.4, cost=1.0, maturity=1.0),
    "Keep multi-cloud options open": dict(
        discovery=1.1, dependency=1.0, assessment=1.0, replication=1.3, downtime=1.0,
        os_modernisation=0.8, scale=1.2, multi_target=2.4, db_migration=0.8, cost=1.0, maturity=1.2),
}

SCENARIOS = list(_SCENARIO_WEIGHTS)


def tools_frame() -> pd.DataFrame:
    rows = []
    for t in _T:
        row = {k: v for k, v in t.items() if k != "scores"}
        row.update(t["scores"])
        rows.append(row)
    return pd.DataFrame(rows)


def rank_tools(scenario: str, custom_weights: dict | None = None) -> pd.DataFrame:
    """Weighted ranking of every tool for a given client scenario."""
    weights = custom_weights or _SCENARIO_WEIGHTS[scenario]
    df = tools_frame()
    total_w = sum(weights.get(d, 0) for d in DIMENSIONS)
    df["fit_score"] = sum(df[d] * weights.get(d, 0) for d in DIMENSIONS) / (5.0 * total_w) * 100
    df["fit_score"] = df["fit_score"].round(1)
    return df.sort_values("fit_score", ascending=False).reset_index(drop=True)


def tooling_cost_estimate(n_vms: int, tool: str) -> dict:
    """Rough tooling spend for the estate. Ranges reflect published list pricing and
    the discounts commonly available at this volume -- treat as order-of-magnitude."""
    per_vm = {
        "Azure Migrate (agentless)": (0, 0),
        "Azure Migrate (agent-based / ASR Mobility Service)": (0, 25),
        "VMware HCX": (0, 0),
        "Zerto": (15 * 6, 30 * 9),          # 6-9 months of per-VM subscription
        "Carbonite Migrate": (200, 400),
        "RiverMeadow": (150, 450),
        "Cirrus Migrate Cloud": (120, 380),
        "PlateSpin Migrate": (180, 350),
        "Veeam Backup & Replication": (0, 0),
        "Device42": (25, 70),
        "Faddom": (20, 55),
        "Corent SurPaaS": (200, 500),
        "Turbonomic": (60, 160),
        "Azure Database Migration Service + DMA": (0, 0),
        "Azure Migrate: application containerisation": (0, 0),
        "ReadyWorks": (40, 110),
        "Rubrik / Commvault Cloud": (0, 0),
    }
    lo, hi = per_vm.get(tool, (0, 0))
    return {"tool": tool, "vms": n_vms, "low": lo * n_vms, "high": hi * n_vms,
            "per_vm_low": lo, "per_vm_high": hi,
            "note": "Zero means no incremental licence cost -- either free, or already owned."}


def recommended_stack(scenario: str, n_vms: int, eol_share_pct: float,
                      blocked_share_pct: float) -> list[dict]:
    """A tool *stack*, not a single winner -- which is how these programmes actually run."""
    stack = [
        {"role": "Assessment & bulk replication",
         "tool": "Azure Migrate (agentless)",
         "why": "Free, Microsoft-supported, and the assessment output is what funding programmes "
                "and Microsoft support will reference. It should carry the bulk of the estate."},
    ]
    if blocked_share_pct > 3:
        stack.append({
            "role": "Exception handling",
            "tool": "Azure Migrate (agent-based / ASR Mobility Service)",
            "why": f"About {blocked_share_pct:.0f}% of the estate is blocked from agentless "
                   "replication by shared disks, encryption or missing VMware Tools. The "
                   "agent-based path covers those without buying a second product."})
    if eol_share_pct > 12:
        stack.append({
            "role": "OS modernisation in flight",
            "tool": "RiverMeadow",
            "why": f"{eol_share_pct:.0f}% of the estate is on an end-of-life guest OS. Upgrading "
                   "during migration avoids running a separate remediation programme first, "
                   "which is usually the longest pole in the schedule."})
    stack.append({
        "role": "Dependency mapping",
        "tool": "Device42" if n_vms > 300 else "Azure Migrate (agentless)",
        "why": ("Above ~300 VMs, Azure Migrate's five-minute agentless poll is not enough to "
                "build trustworthy move groups, and its 1,000-server ceiling starts to bite. "
                "A dedicated discovery product pays for itself in avoided failed waves."
                if n_vms > 300 else
                "At this scale the built-in agentless dependency analysis is sufficient.")})
    stack.append({
        "role": "Database migration",
        "tool": "Azure Database Migration Service + DMA",
        "why": "Any database that is replatformed rather than rehosted needs DMS. Data Migration "
               "Assistant clears compatibility blockers before you commit to a target."})
    stack.append({
        "role": "Post-migration optimisation",
        "tool": "Turbonomic",
        "why": "The migration right-sizes once, from vCenter data. Sustained savings come from "
               "continuous optimisation against real Azure Monitor telemetry. Optional, but the "
               "business case usually assumes it."})
    return stack
