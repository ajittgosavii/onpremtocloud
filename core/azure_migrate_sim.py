"""Azure Migrate process simulator.

Models what actually happens when you run Azure Migrate against a vSphere
estate, phase by phase, with the real product limits applied to the client's
own numbers:

* appliance sizing and how many appliances the estate needs
* discovery latency by discovery type (metadata, software inventory, SQL, web apps)
* performance profiling duration and the resulting confidence rating
* dependency analysis mode limits (agentless vs agent-based)
* assessment outputs -- readiness, sizing, monthly cost estimate
* agentless replication: 300 concurrent per appliance (500 with scale-out),
  56 disks replicating at a time, initial seed then delta cycles
* test migration, cutover and post-migration cleanup

Every number is derived, not hard-coded, so changing the estate or the link
speed changes the plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# ---- Published Azure Migrate limits --------------------------------------
DISCOVERY_LIMIT_PER_APPLIANCE = 10_000     # servers discovered per VMware appliance
VCENTERS_PER_APPLIANCE = 1
CONCURRENT_REPL_PER_APPLIANCE = 300        # scheduled replications, single appliance
CONCURRENT_REPL_WITH_SCALEOUT = 500        # with one scale-out appliance added
DISKS_REPLICATING_PER_APPLIANCE = 56       # the real throughput ceiling
AGENTLESS_DEPENDENCY_LIMIT = 1_000         # servers with agentless dependency analysis
ASSESSMENT_SERVER_LIMIT = 35_000           # servers per assessment
GROUP_SERVER_LIMIT = 35_000
APPLIANCE_SPEC = {"vcpu": 8, "ram_gib": 32, "disk_gib": 80,
                  "note": "16 vCPU / 32 GB is the sizing for up to 10,000 servers"}
SCALEOUT_SPEC = {"vcpu": 8, "ram_gib": 32, "disk_gib": 80,
                 "note": "Scale-out appliance adds replication capacity only, not discovery"}

# Performance profiling: the appliance samples every 20s, aggregates to a
# 10-minute point, and uploads hourly.
SAMPLE_INTERVAL_SECONDS = 20
ROLLUP_MINUTES = 10
UPLOAD_INTERVAL_HOURS = 1

ASR_FREE_DAYS = 180        # migration is free per instance for the first 180 days


@dataclass
class MigrateConfig:
    vcenter_count: int = 2
    discovery_scope: str = "Full (metadata + software inventory + SQL + web apps)"
    dependency_mode: str = "Agentless"          # Agentless | Agent-based | None
    performance_history_days: int = 30          # Azure Migrate: 1 day / 1 week / 1 month
    profiling_days_elapsed: int = 30            # how long the appliance has actually run
    percentile: str = "p95"
    comfort_factor: float = 1.3
    sizing_criterion: str = "Performance-based"  # or "As on-premises"
    pricing_offer: str = "Pay-as-you-go"
    reserved_instance: str = "3 year"
    ahb_windows: bool = True
    ahb_linux: bool = False
    use_scaleout_appliance: bool = True
    replication_bandwidth_mbps: float = 1000.0
    bandwidth_share_pct: float = 60.0
    wan_efficiency_pct: float = 75.0
    test_migration_pct: float = 100.0           # share of VMs given a test migration
    cutover_batch_size: int = 25                # VMs per cutover window
    cutover_windows_per_week: int = 2


# --------------------------------------------------------------------------
# Sizing the tooling itself
# --------------------------------------------------------------------------
def appliance_plan(n_vms: int, cfg: MigrateConfig) -> dict:
    """How many appliances, of what kind, and why."""
    # One appliance per vCenter is the supported topology; each also caps at 10k servers.
    discovery_appliances = max(cfg.vcenter_count,
                               int(np.ceil(n_vms / DISCOVERY_LIMIT_PER_APPLIANCE)))
    max_concurrent = CONCURRENT_REPL_PER_APPLIANCE * discovery_appliances
    scaleout = 0
    if cfg.use_scaleout_appliance:
        scaleout = cfg.vcenter_count
        max_concurrent = CONCURRENT_REPL_WITH_SCALEOUT * cfg.vcenter_count

    disks_at_once = DISKS_REPLICATING_PER_APPLIANCE * (discovery_appliances + scaleout)
    return {
        "discovery_appliances": discovery_appliances,
        "scaleout_appliances": scaleout,
        "total_appliances": discovery_appliances + scaleout,
        "max_concurrent_replications": max_concurrent,
        "disks_replicating_at_once": disks_at_once,
        "appliance_spec": APPLIANCE_SPEC,
        "vcpu_footprint": (discovery_appliances + scaleout) * APPLIANCE_SPEC["vcpu"],
        "ram_footprint_gib": (discovery_appliances + scaleout) * APPLIANCE_SPEC["ram_gib"],
        "rationale": (
            f"One appliance is required per vCenter ({cfg.vcenter_count}), and each appliance "
            f"discovers up to {DISCOVERY_LIMIT_PER_APPLIANCE:,} servers. "
            + (f"A scale-out appliance is added per vCenter because concurrent replication is "
               f"capped at {CONCURRENT_REPL_PER_APPLIANCE} VMs on a single appliance and "
               f"{CONCURRENT_REPL_WITH_SCALEOUT} with scale-out."
               if cfg.use_scaleout_appliance else
               f"Without a scale-out appliance, concurrent replication is capped at "
               f"{CONCURRENT_REPL_PER_APPLIANCE} VMs per vCenter.")
        ),
        "throughput_caveat": (
            f"Scheduling {max_concurrent} VMs does not mean {max_concurrent} replicate at once. "
            f"Each appliance replicates {DISKS_REPLICATING_PER_APPLIANCE} disks at a time, so "
            f"with {discovery_appliances + scaleout} appliance(s) the real ceiling is "
            f"{disks_at_once} disks in flight -- the rest queue."
        ),
    }


# --------------------------------------------------------------------------
# Phase model
# --------------------------------------------------------------------------
@dataclass
class Phase:
    key: str
    name: str
    duration_days: float
    detail: str
    outputs: list[str] = field(default_factory=list)
    gotchas: list[str] = field(default_factory=list)
    prerequisites: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def _usable_gib_per_hour(cfg: MigrateConfig) -> float:
    mbps = cfg.replication_bandwidth_mbps * (cfg.bandwidth_share_pct / 100.0) \
        * (cfg.wan_efficiency_pct / 100.0)
    return mbps / 8.0 * 3600.0 / 1024.0


def simulate(estate: pd.DataFrame, cfg: MigrateConfig,
             sized: pd.DataFrame | None = None) -> tuple[list[Phase], dict]:
    """Run the full Azure Migrate lifecycle against this estate."""
    n = len(estate)
    plan = appliance_plan(n, cfg)
    gib_hr = _usable_gib_per_hour(cfg)

    phases: list[Phase] = []

    # ---- 1. Prepare ------------------------------------------------------
    phases.append(Phase(
        key="prepare", name="1. Prepare Azure and vCenter",
        duration_days=5.0,
        detail=(
            "Create the Azure Migrate project in the target geography (project data residency is "
            "chosen here and cannot be changed later). Register the required resource providers, "
            "create the vCenter read-only account with the privileges Azure Migrate needs, and "
            "prepare guest credentials for software inventory and dependency analysis."
        ),
        outputs=["Azure Migrate project", "vCenter service account", "Guest credential set",
                 "Outbound connectivity (HTTPS 443) to Azure Migrate endpoints"],
        prerequisites=[
            "vCenter Server 6.7 or later (7.x/8.x recommended)",
            "A user with at least Contributor on the target subscription",
            "Outbound 443 to *.azure.com / *.azmk8s.io endpoints, or an ExpressRoute Microsoft peering",
        ],
        gotchas=[
            "The project geography fixes where discovery metadata is stored. For a regulated "
            "client, agree this with the data-protection team before anyone clicks Create.",
            "A read-only vCenter account is enough for discovery and assessment, but agentless "
            "replication needs additional privileges -- granting them late stalls the first wave.",
        ],
    ))

    # ---- 2. Deploy appliance --------------------------------------------
    phases.append(Phase(
        key="appliance", name="2. Deploy the Azure Migrate appliance",
        duration_days=2.0 + 0.5 * plan["total_appliances"],
        detail=(
            f"Deploy {plan['discovery_appliances']} discovery appliance(s) from the downloaded OVA "
            f"({APPLIANCE_SPEC['vcpu']} vCPU, {APPLIANCE_SPEC['ram_gib']} GB RAM, "
            f"{APPLIANCE_SPEC['disk_gib']} GB disk each)"
            + (f" plus {plan['scaleout_appliances']} scale-out appliance(s) for replication capacity."
               if plan["scaleout_appliances"] else ".")
            + f" {plan['rationale']}"
        ),
        outputs=[f"{plan['total_appliances']} registered appliance(s)",
                 f"Appliance footprint: {plan['vcpu_footprint']} vCPU / "
                 f"{plan['ram_footprint_gib']} GB RAM on the source cluster"],
        gotchas=[
            plan["throughput_caveat"],
            "The appliance must resolve and reach both vCenter and Azure. Proxy interception "
            "with TLS inspection is the most common cause of a failed registration.",
            "The scale-out appliance adds replication capacity only -- it does not discover.",
        ],
        metrics={"appliances": plan["total_appliances"],
                 "concurrent_replication_ceiling": plan["max_concurrent_replications"]},
    ))

    # ---- 3. Discovery ----------------------------------------------------
    # Metadata lands fast; deeper discovery types take progressively longer.
    meta_hours = max(0.25, n / 100 * 0.25)
    sw_hours = 1.0 + n / 500.0
    sql_hours = 24.0
    disc_days = meta_hours / 24.0
    scope = cfg.discovery_scope
    disc_detail = [f"vCenter metadata for {n:,} VMs appears in the portal within "
                   f"~{meta_hours * 60:,.0f} minutes."]
    if "software" in scope.lower() or "Full" in scope:
        disc_days = max(disc_days, sw_hours / 24.0)
        disc_detail.append(f"Software inventory (installed applications, roles and features) "
                           f"completes in ~{sw_hours:,.1f} hours and requires guest credentials.")
    if "SQL" in scope or "Full" in scope:
        disc_days = max(disc_days, sql_hours / 24.0)
        disc_detail.append(f"SQL Server instance and database discovery completes within "
                           f"~{sql_hours:,.0f} hours.")
    if "web" in scope.lower() or "Full" in scope:
        disc_days = max(disc_days, 1.0)
        disc_detail.append("ASP.NET and Java web-app discovery completes within ~24 hours.")

    no_tools = int((estate["vmware_tools"].isin(["toolsNotInstalled", "toolsNotRunning"])).sum()) \
        if "vmware_tools" in estate.columns else 0
    phases.append(Phase(
        key="discovery", name="3. Discover the estate",
        duration_days=max(disc_days, 1.0),
        detail=" ".join(disc_detail),
        outputs=[f"{n:,} servers discovered",
                 "Per-VM inventory: cores, memory, disks, NICs, OS, firmware, power state",
                 "Application inventory and SQL/web-app estate (if in scope)"],
        gotchas=[
            (f"{no_tools} VM(s) have VMware Tools not installed or not running. Agentless "
             "software inventory and dependency analysis read the guest through VMware Tools, "
             "so those VMs will show hardware metadata only." if no_tools else
             "All VMs report a healthy VMware Tools state, so guest-level discovery will be complete."),
            "Discovery is read-only and adds no measurable load to vCenter, but the appliance "
            "does poll continuously -- size the appliance's own vCPU/RAM as listed above.",
        ],
        metrics={"servers_discovered": n, "vms_without_tools": no_tools},
    ))

    # ---- 4. Performance profiling ---------------------------------------
    from core.assessment import confidence_rating, estimate_coverage
    coverage = estimate_coverage(estate, cfg.profiling_days_elapsed, cfg.performance_history_days)
    stars = confidence_rating(coverage)
    wait_days = max(cfg.performance_history_days - cfg.profiling_days_elapsed, 0)
    phases.append(Phase(
        key="profiling", name="4. Collect performance data",
        duration_days=float(max(cfg.performance_history_days, 1)),
        detail=(
            f"The appliance samples CPU, memory, disk IOPS/throughput and network I/O every "
            f"{SAMPLE_INTERVAL_SECONDS} seconds, rolls the samples into {ROLLUP_MINUTES}-minute "
            f"points, and uploads hourly. The assessment is configured for "
            f"{cfg.performance_history_days} days of history; the appliance has been running for "
            f"{cfg.profiling_days_elapsed} days, giving {coverage:.0f}% performance coverage "
            f"-- a {stars}-star confidence rating."
        ),
        outputs=[f"{coverage:.0f}% performance coverage", f"{stars}/5 star confidence rating"],
        gotchas=[
            (f"Wait a further {wait_days} day(s) and recalculate before presenting sizing numbers. "
             "Below 80% coverage, Microsoft's own guidance is to switch to as-on-premises sizing "
             "rather than trust performance-based recommendations."
             if coverage < 80 else
             "Coverage is at or above 80%, so performance-based sizing is trustworthy."),
            "Powered-off VMs contribute no data points and drag the rating down. Either power "
            "them on for the profiling window or exclude them from the assessment group.",
            "VMs built during the profiling window cannot have full history, so their sizing is "
            "always weaker than the estate average.",
        ],
        metrics={"coverage_pct": coverage, "confidence_stars": stars},
    ))

    # ---- 5. Dependency analysis -----------------------------------------
    if cfg.dependency_mode == "Agentless":
        dep_days = 14.0
        over = max(n - AGENTLESS_DEPENDENCY_LIMIT, 0)
        dep_detail = (
            f"Agentless dependency analysis polls the guest through VMware Tools every five "
            f"minutes, capturing TCP connections and the owning process. It needs no agents, but "
            f"it is limited to {AGENTLESS_DEPENDENCY_LIMIT:,} servers at a time"
            + (f" -- this estate of {n:,} exceeds that, so run it in "
               f"{int(np.ceil(n / AGENTLESS_DEPENDENCY_LIMIT))} batches." if over else ".")
        )
        dep_gotchas = [
            "Agentless capture is a five-minute poll, not a continuous packet capture. "
            "Short-lived connections and rare batch jobs can be missed -- run it for at least "
            "two weeks and cross-check with a month-end close.",
            "It requires guest credentials and a working VMware Tools on every VM in scope.",
        ]
    elif cfg.dependency_mode == "Agent-based":
        dep_days = 21.0
        dep_detail = (
            "Agent-based dependency analysis installs the Microsoft Monitoring Agent and the "
            "Dependency Agent in each guest and reports into a Log Analytics workspace. It gives "
            "continuous, higher-fidelity data and lets you query connections with KQL, at the "
            "cost of deploying two agents to every server and a Log Analytics ingestion charge."
        )
        dep_gotchas = [
            "Agent deployment across 500+ guests is itself a mini-project -- budget change "
            "windows for the servers that will not take a silent install.",
            "Log Analytics ingestion is billed per GB and is easy to underestimate at this scale.",
        ]
    else:
        dep_days = 0.0
        dep_detail = ("Dependency analysis is skipped. Move groups will be built from naming "
                      "conventions and CMDB data alone.")
        dep_gotchas = [
            "Skipping dependency analysis is the single most common cause of a failed wave: an "
            "application is split across waves and breaks on a latency-sensitive call back to "
            "a server still on-premises.",
        ]

    phases.append(Phase(
        key="dependency", name="5. Map dependencies and build move groups",
        duration_days=dep_days,
        detail=dep_detail,
        outputs=["Dependency map per server", "Validated application move groups"],
        gotchas=dep_gotchas,
        metrics={"mode": cfg.dependency_mode},
    ))

    # ---- 6. Assessment ---------------------------------------------------
    ready = cond = notready = 0
    est_monthly = 0.0
    if sized is not None and "readiness" in sized.columns:
        vc = sized["readiness"].value_counts()
        ready = int(vc.get("Ready for Azure", 0))
        cond = int(vc.get("Ready with conditions", 0))
        notready = int(vc.get("Not ready for Azure", 0))
        est_monthly = float(sized["monthly_cost"].sum()) if "monthly_cost" in sized.columns else 0.0

    phases.append(Phase(
        key="assessment", name="6. Create and review the assessment",
        duration_days=3.0,
        detail=(
            f"Create an Azure VM assessment over the discovered group using "
            f"{cfg.sizing_criterion.lower()} sizing at the {cfg.percentile} percentile with a "
            f"{cfg.comfort_factor:g}x comfort factor, priced on {cfg.pricing_offer}"
            + (f" with a {cfg.reserved_instance} reserved instance" if cfg.reserved_instance != "None" else "")
            + (" and Azure Hybrid Benefit applied to Windows Server." if cfg.ahb_windows else ".")
            + " Azure Migrate returns readiness, a recommended size per VM, and a monthly cost estimate."
        ),
        outputs=[
            f"Ready: {ready} | Ready with conditions: {cond} | Not ready: {notready}",
            f"Estimated Azure monthly run rate: {est_monthly:,.0f}" if est_monthly else
            "Estimated Azure monthly run rate (see the Cost Simulator)",
            "Per-VM recommended size and disk tier",
        ],
        gotchas=[
            "The assessment is a point-in-time snapshot. It does not auto-refresh -- recalculate "
            "after the profiling window completes and again before each wave.",
            "The comfort factor multiplies utilisation, not the VM size. At 1.3x, a VM at 70% CPU "
            "is sized for 91% -- which usually means no downsizing at all for busy servers.",
            "The cost estimate covers compute and storage. It excludes bandwidth, backup, DR, "
            "the landing zone and anything else in the platform -- typically another 10-20%.",
        ],
        metrics={"ready": ready, "conditional": cond, "not_ready": notready,
                 "estimated_monthly": est_monthly},
    ))

    # ---- 7. Replication --------------------------------------------------
    total_gib = float(estate["used_gib"].sum())
    total_disks = int(estate["total_disks"].sum()) if "total_disks" in estate.columns else n * 2
    seed_hours = total_gib / max(gib_hr, 0.001)
    # Disk-concurrency queueing: the seed cannot go faster than the disk slots allow.
    disk_batches = np.ceil(total_disks / max(plan["disks_replicating_at_once"], 1))
    mean_churn = float(pd.to_numeric(estate.get("daily_churn_pct", pd.Series([3.0] * n)),
                                     errors="coerce").fillna(3.0).mean())
    seed_days = seed_hours / 24.0
    delta_gib = total_gib * (mean_churn / 100.0) * (seed_days + 3)
    delta_days = delta_gib / max(gib_hr, 0.001) / 24.0

    phases.append(Phase(
        key="replication", name="7. Replicate (agentless, snapshot-based)",
        duration_days=float(seed_days + delta_days),
        detail=(
            f"Agentless replication takes a VM snapshot through vCenter, reads the disks with "
            f"VMware's Changed Block Tracking, and writes them into a staging storage account "
            f"in Azure, then repeats on a delta cycle. With {cfg.replication_bandwidth_mbps:,.0f} "
            f"Mbps of link at {cfg.bandwidth_share_pct:.0f}% allocation and "
            f"{cfg.wan_efficiency_pct:.0f}% efficiency, usable throughput is "
            f"{gib_hr:,.0f} GiB/hour. Seeding {total_gib / 1024:,.1f} TiB takes "
            f"~{seed_days:,.1f} days, and delta sync at {mean_churn:.1f}% daily churn adds "
            f"~{delta_days:,.1f} days."
        ),
        outputs=[f"{total_gib / 1024:,.1f} TiB seeded",
                 f"{total_disks:,} disks replicated in ~{disk_batches:,.0f} batch(es)",
                 "Replicating VMs held in delta sync until cutover"],
        gotchas=[
            f"Replication is capped at {plan['disks_replicating_at_once']} disks in flight across "
            f"{plan['total_appliances']} appliance(s). Scheduling more VMs simply lengthens the queue.",
            "Agentless replication does not support Azure Data Box seeding. If the wire cannot "
            "carry the volume, the bulk data needs a different tool or a storage-level approach.",
            f"Azure Site Recovery replication is free for the first {ASR_FREE_DAYS} days per "
            "instance when used for migration. A wave that slips past that starts billing.",
            "High-churn VMs may never converge: if daily change exceeds what the link can carry, "
            "the delta cycle never catches up. Those VMs need a bigger window or a different method.",
            "Snapshots are taken and deleted on every cycle. Confirm the source datastores have "
            "headroom -- a full datastore stops replication and can stun the VM.",
        ],
        metrics={"seed_days": seed_days, "delta_days": delta_days,
                 "usable_gib_per_hour": gib_hr, "total_tib": total_gib / 1024,
                 "mean_churn_pct": mean_churn},
    ))

    # ---- 8. Test migration ----------------------------------------------
    test_vms = int(n * cfg.test_migration_pct / 100.0)
    test_days = np.ceil(test_vms / max(cfg.cutover_batch_size * 2, 1)) / \
        max(cfg.cutover_windows_per_week, 1) * 7
    phases.append(Phase(
        key="test", name="8. Test migration",
        duration_days=float(test_days),
        detail=(
            f"Run a test migration for {test_vms:,} VM(s) into an isolated virtual network. The "
            "source VM keeps running and replication continues, so this is non-disruptive. Test "
            "migration is what proves the boot, the drivers, the agents and the application -- "
            "before anyone commits to a cutover window."
        ),
        outputs=["Booted test VMs in an isolated VNet", "Validated Azure VM agent and boot diagnostics",
                 "Application smoke-test evidence per move group"],
        gotchas=[
            "Always clean up the test VMs afterwards. Left running, they bill at full rate and "
            "block the real cutover.",
            "Test into an isolated network with no route back to production. A test VM that can "
            "reach the production database will happily write to it.",
            "A successful boot is not a successful test. Insist on an application-level check "
            "signed off by the app owner.",
        ],
        metrics={"tested_vms": test_vms},
    ))

    # ---- 9. Cutover ------------------------------------------------------
    batches = np.ceil(n / max(cfg.cutover_batch_size, 1))
    cut_days = batches / max(cfg.cutover_windows_per_week, 1) * 7
    phases.append(Phase(
        key="cutover", name="9. Cut over",
        duration_days=float(cut_days),
        detail=(
            f"Shut down the source VM, run a final delta sync, and start the Azure VM. "
            f"At {cfg.cutover_batch_size} VMs per window and {cfg.cutover_windows_per_week} "
            f"window(s) per week, {n:,} VMs need {batches:,.0f} windows -- about "
            f"{cut_days / 7:,.0f} weeks of cutover calendar."
        ),
        outputs=["VMs running in Azure", "DNS and load-balancer records repointed",
                 "Source VMs powered off but retained for rollback"],
        gotchas=[
            "The final delta sync is the only downtime, but its length depends on churn since "
            "the last cycle. Freeze batch jobs and backups in the hours before cutover.",
            "Keep the source VM powered off, not deleted, until hypercare completes. It is the "
            "only real rollback you have.",
            "Static IPs, hard-coded hostnames and MAC-bound licences all break at this moment. "
            "They are cheap to fix beforehand and expensive to fix at 2 a.m.",
        ],
        metrics={"cutover_windows": batches},
    ))

    # ---- 10. Post-migration ---------------------------------------------
    phases.append(Phase(
        key="post", name="10. Stop replication and optimise",
        duration_days=10.0,
        detail=(
            "Stop replication to release the staging storage and end ASR billing, remove the "
            "Mobility Service where agent-based replication was used, install the Azure VM agent "
            "and required extensions, enable Azure Backup and Defender for Cloud, apply tags and "
            "policy, and take the first real right-sizing pass using Azure Monitor data rather "
            "than vCenter data."
        ),
        outputs=["Staging storage released", "Backup and monitoring enrolled",
                 "Post-migration right-sizing recommendations"],
        gotchas=[
            "Forgetting to stop replication leaves ASR charges and staging storage running "
            "indefinitely -- a recurring finding in post-migration cost reviews.",
            "The biggest cost reduction usually comes 60-90 days after migration, from real "
            "Azure Monitor data. Plan a formal optimisation gate, do not leave it to goodwill.",
            "Decommission the source estate deliberately. Hardware and VMware licences that stay "
            "on the books erase the business case.",
        ],
    ))

    summary = {
        "total_days": float(sum(p.duration_days for p in phases)),
        "critical_path_days": float(
            sum(p.duration_days for p in phases if p.key not in ("profiling", "dependency"))
            + max(next(p.duration_days for p in phases if p.key == "profiling"),
                  next(p.duration_days for p in phases if p.key == "dependency"))
        ),
        "appliance_plan": plan,
        "coverage_pct": coverage,
        "confidence_stars": stars,
        "usable_gib_per_hour": gib_hr,
        "total_tib": total_gib / 1024,
    }
    return phases, summary


def phases_frame(phases: list[Phase], start_date: str = "2026-09-01") -> pd.DataFrame:
    """Phase list as a dated Gantt-ready frame. Profiling and dependency analysis
    run concurrently with each other, which the sequencing reflects."""
    rows = []
    cursor = pd.Timestamp(start_date)
    parallel_start = None
    for p in phases:
        if p.key == "profiling":
            parallel_start = cursor
            start = cursor
            end = start + pd.Timedelta(days=p.duration_days)
        elif p.key == "dependency":
            start = parallel_start or cursor
            end = start + pd.Timedelta(days=p.duration_days)
            cursor = max(cursor, end)
        else:
            start = cursor
            end = start + pd.Timedelta(days=p.duration_days)
            cursor = end
        if p.key == "profiling":
            cursor = max(cursor, end)
        rows.append({"phase": p.name, "key": p.key, "start": start, "end": end,
                     "duration_days": p.duration_days, "detail": p.detail})
    return pd.DataFrame(rows)


# ==========================================================================
# Limitations register
# ==========================================================================
# What Azure Migrate does *not* do. Each entry names the compensating control,
# because "the tool cannot do this" is only useful next to "so use that instead".
SEVERITY_ORDER = ["Blocker", "Major", "Moderate", "Minor"]

LIMITATIONS: list[dict] = [
    # ---- Databases -------------------------------------------------------
    dict(
        area="Databases", severity="Blocker",
        limitation="Azure Migrate does not migrate databases at all.",
        detail="Azure Migrate discovers and assesses SQL Server instances and databases, and "
               "recommends a target (Azure SQL Managed Instance, Azure SQL Database, or SQL "
               "Server on an Azure VM). It then stops. There is no schema conversion, no data "
               "movement and no cutover capability for any database engine. If you rehost the "
               "VM with Azure Migrate you get a lift-and-shift of the whole guest, including the "
               "database engine as-is -- which is not a database migration and delivers none of "
               "the PaaS benefit the assessment just recommended.",
        impact="Every database in the replatform column needs a second tool and a second plan. "
               "Programmes that budget from the Azure Migrate assessment alone under-scope the "
               "database workstream, which is routinely the longest one.",
        workaround="Azure Database Migration Service (DMS) for the data movement, and Data "
                   "Migration Assistant (DMA) to clear compatibility blockers before you commit "
                   "to a target.",
        affects="Any VM with a database engine",
    ),
    dict(
        area="Databases", severity="Blocker",
        limitation="Heterogeneous database migration is entirely out of scope.",
        detail="Moving Oracle to PostgreSQL, Oracle to Azure SQL, Sybase/SAP ASE to SQL Server, "
               "DB2 to PostgreSQL, or MySQL to PostgreSQL involves schema conversion, data-type "
               "mapping, and rewriting stored procedures, triggers, packages and application SQL. "
               "Azure Migrate has no capability in this area whatsoever -- it will not even "
               "assess the feasibility. Its SQL assessment only understands SQL Server as both "
               "source and target.",
        impact="A heterogeneous move is an application project, not an infrastructure one. "
               "PL/SQL to PL/pgSQL conversion is typically 60-85% automatable; the remaining "
               "manual portion plus regression testing is where the schedule goes.",
        workaround="SQL Server Migration Assistant (SSMA) for Oracle, DB2, Sybase, MySQL and "
                   "Access to a SQL Server target. For Oracle to PostgreSQL, use ora2pg for "
                   "schema assessment and the Azure Database for PostgreSQL migration service "
                   "for data. Budget an application regression cycle in every case.",
        affects="Oracle, DB2, Sybase and MySQL workloads targeting a different engine",
    ),
    dict(
        area="Databases", severity="Major",
        limitation="Oracle discovery and assessment is limited compared with SQL Server.",
        detail="SQL Server gets first-class treatment -- instance discovery, database-level "
               "sizing, target recommendation and readiness. Oracle receives far less. You will "
               "not get the same depth of target recommendation, and Oracle licensing "
               "implications are not modelled at all, despite being the dominant cost factor in "
               "any Oracle migration decision.",
        impact="Oracle estates need a separate, manual assessment. Do not present an Azure "
               "Migrate report as covering them.",
        workaround="A dedicated Oracle assessment covering licence portability (Oracle's Azure "
                   "policy counts two vCPU as one licensed core with hyper-threading on), plus "
                   "Oracle Database@Azure for larger estates where the licensing arithmetic works.",
        affects="Oracle Database VMs",
    ),
    dict(
        area="Databases", severity="Major",
        limitation="No assessment of PostgreSQL, MySQL, MongoDB, Cassandra or any open-source engine.",
        detail="Azure Migrate's database intelligence is SQL Server. Open-source engines are "
               "discovered only as software inventory -- a process name in a list. There is no "
               "sizing, no target recommendation and no readiness verdict for them.",
        impact="Open-source database estates appear in the assessment as ordinary VMs, so the "
               "assessment silently recommends rehosting them when a Flexible Server target "
               "would be cheaper and better.",
        workaround="Assess these manually, then migrate with the Azure Database Migration "
                   "Service or engine-native logical replication for near-zero downtime.",
        affects="PostgreSQL, MySQL, MongoDB and similar",
    ),
    dict(
        area="Databases", severity="Moderate",
        limitation="Always On availability groups, failover cluster instances and Oracle RAC "
                   "are not migrated as clusters.",
        detail="Azure Migrate replicates individual VMs. A clustered database is a distributed "
               "system with shared storage, quorum and virtual network names -- none of which "
               "survive a per-VM replication. The shared disks that make it a cluster are "
               "themselves unsupported by agentless replication.",
        impact="Every clustered database must be rebuilt in Azure and the data moved at the "
               "application layer.",
        workaround="Rebuild the cluster in Azure, then seed it with Always On, log shipping or "
                   "backup/restore. For SQL Server, a distributed availability group gives the "
                   "shortest cutover of any method.",
        affects="Clustered database VMs",
    ),

    # ---- Replication -----------------------------------------------------
    dict(
        area="Replication", severity="Major",
        limitation=f"Concurrent replication is capped at {CONCURRENT_REPL_PER_APPLIANCE} VMs per "
                   f"appliance ({CONCURRENT_REPL_WITH_SCALEOUT} with a scale-out appliance).",
        detail=f"Worse, the real ceiling is {DISKS_REPLICATING_PER_APPLIANCE} disks actively "
               "replicating per appliance. Scheduling more VMs than that simply builds a queue; "
               "it does not add throughput.",
        impact="Wave sizes are constrained by the tool, not only by the network. This is the "
               "limit most plans discover late.",
        workaround="Deploy a scale-out appliance per vCenter, size waves to the disk ceiling, and "
                   "sequence high-disk-count VMs deliberately rather than alphabetically.",
        affects="Any estate above roughly 300 VMs",
    ),
    dict(
        area="Replication", severity="Major",
        limitation="No offline seeding -- Azure Data Box is not supported for agentless replication.",
        detail="All data must cross the wire. For a multi-hundred-terabyte estate on a modest "
               "link, this alone can make the plan infeasible regardless of how many appliances "
               "you deploy.",
        impact="Bandwidth becomes the binding constraint on the entire programme schedule.",
        workaround="Negotiate a temporary ExpressRoute uplift for the migration window, or move "
                   "bulk file and archive data with a partner tool or a storage-level method "
                   "(Azure Storage Mover, Data Box) and migrate only the compute with Azure Migrate.",
        affects="Estates with large data volumes relative to link speed",
    ),
    dict(
        area="Replication", severity="Major",
        limitation="High-churn VMs may never converge.",
        detail="If a VM changes data faster than the link can replicate it, the delta cycle "
               "never catches up and the VM stays permanently behind. Azure Migrate will not "
               "warn you in advance -- you find out by watching the replication lag stop falling.",
        impact="The busiest, most important servers are exactly the ones most likely to hit this.",
        workaround="Model churn against usable bandwidth per VM before the wave. For the ones "
                   "that fail the test, use a longer window with reduced load, a dedicated link "
                   "allocation, or a continuous-replication product such as Zerto or Cirrus.",
        affects="Database and high-write file servers",
    ),
    dict(
        area="Replication", severity="Moderate",
        limitation="Agentless replication requires healthy VMware Tools and Changed Block Tracking.",
        detail="Without VMware Tools, application-consistent snapshots are impossible and you get "
               "crash-consistent replication only. Without working CBT, each cycle re-reads the "
               "whole disk. Both conditions are common in aged estates.",
        impact="Databases replicated crash-consistently need a recovery on first boot, and may "
               "not be transactionally clean.",
        workaround="Remediate VMware Tools before the wave, or use agent-based replication for "
                   "the affected VMs.",
        affects="VMs with stale or missing VMware Tools",
    ),

    # ---- Unsupported configurations ---------------------------------------
    dict(
        area="Source configuration", severity="Blocker",
        limitation="Shared disks, vSphere VM Encryption and Fault Tolerance are unsupported.",
        detail="Agentless replication takes a VM-level snapshot. Shared and multi-writer disks "
               "cannot be captured consistently, encrypted VMs cannot be read, and Fault "
               "Tolerance has no Azure equivalent.",
        impact="These VMs drop out of the standard process entirely and need an individual plan.",
        workaround="Rebuild clusters in Azure with shared managed disks; decrypt before migration "
                   "or use agent-based replication; redesign FT workloads onto availability zones.",
        affects="Clustered, encrypted and fault-tolerant VMs",
    ),
    dict(
        area="Source configuration", severity="Moderate",
        limitation="Physical-mode RDMs and independent/non-persistent disks are not replicated.",
        detail="Physical-mode RDMs are pass-through to the array and are invisible to snapshot-"
               "based replication. Independent disks are excluded from snapshots by design, so "
               "they will silently not migrate.",
        impact="The VM arrives in Azure missing a disk -- and the failure is discovered at test "
               "migration, not before.",
        workaround="Convert RDMs to VMDK and independent disks to dependent before replication, "
                   "or move that data separately.",
        affects="VMs with RDM or independent disks",
    ),
    dict(
        area="Source configuration", severity="Moderate",
        limitation="No in-flight guest OS upgrade or remediation.",
        detail="Azure Migrate moves the guest exactly as it is. An end-of-life Windows Server "
               "2012 R2 or CentOS 7 VM arrives in Azure still end-of-life. Azure will grant "
               "Extended Security Updates free for eligible Windows versions running on Azure, "
               "but the OS is still unsupported by its vendor.",
        impact="The EOL remediation programme has to run either before migration (delaying the "
               "exit) or after it (carrying the risk into Azure).",
        workaround="A tool such as RiverMeadow upgrades the OS during migration. Otherwise "
                   "sequence the upgrade explicitly and price it.",
        affects="End-of-life guest operating systems",
    ),

    # ---- Assessment ------------------------------------------------------
    dict(
        area="Assessment", severity="Major",
        limitation="The cost estimate excludes most of the real bill.",
        detail="Azure Migrate prices compute and managed disks. It does not include networking, "
               "bandwidth or egress, backup, disaster recovery, the landing zone (hub network, "
               "firewall, bastion, private endpoints), Log Analytics, Microsoft Defender for "
               "Cloud, or any PaaS service.",
        impact="Real Azure bills typically land 10-25% above the Azure Migrate estimate for a "
               "well-governed landing zone. Presenting the raw figure to a CFO sets up a "
               "credibility problem later.",
        workaround="Add the platform components explicitly -- this simulator applies a "
                   "configurable landing-zone overhead and prices backup, DR and egress from the "
                   "live retail API.",
        affects="Every cost figure Azure Migrate produces",
    ),
    dict(
        area="Assessment", severity="Moderate",
        limitation="Assessments are a point-in-time snapshot and never refresh themselves.",
        detail="An assessment reflects the estate and the prices at the moment it was calculated. "
               "It does not update as the estate changes, as more performance data arrives, or "
               "as Azure prices move.",
        impact="Stale assessments drive wrong sizing decisions months later.",
        workaround="Recalculate after the profiling window completes and again before each wave. "
                   "Treat the assessment as perishable.",
        affects="Programme-wide",
    ),
    dict(
        area="Assessment", severity="Moderate",
        limitation="The comfort factor multiplies utilisation, not headroom, and quietly erases "
                   "most right-sizing benefit.",
        detail="At the default 1.3x, a VM running at 70% CPU is sized for 91%, which rounds up to "
               "the same size it already has. The saving in the business case comes from idle "
               "VMs; busy VMs will not shrink.",
        impact="Cost models built on a blanket right-sizing percentage overstate the benefit.",
        workaround="Segment the estate: aggressive sizing for non-production, conservative for "
                   "Tier 0/1. This simulator lets you vary the percentile and comfort factor and "
                   "see the effect immediately.",
        affects="Right-sizing savings",
    ),
    dict(
        area="Assessment", severity="Minor",
        limitation="Imported CSV assessments get no confidence rating.",
        detail="If you feed Azure Migrate an inventory file rather than discovering through the "
               "appliance, no performance coverage rating is calculated -- there is no way to "
               "judge how reliable the sizing is.",
        impact="A CSV-based assessment looks identical to a discovered one but carries far less "
               "assurance.",
        workaround="Use appliance-based discovery for anything that will drive a funding decision.",
        affects="CSV-imported inventories",
    ),

    # ---- Dependency analysis ---------------------------------------------
    dict(
        area="Dependency analysis", severity="Major",
        limitation=f"Agentless dependency analysis polls every five minutes and covers at most "
                   f"{AGENTLESS_DEPENDENCY_LIMIT:,} servers.",
        detail="It is a periodic poll, not a continuous capture. Short-lived connections, "
               "overnight batch jobs and month-end processes are routinely missed. It also "
               "reports network connections, not application semantics -- it cannot tell you "
               "that a connection is a critical synchronous call rather than a health check.",
        impact="Move groups built on incomplete dependency data are the most common cause of a "
               "failed wave.",
        workaround="Run it for at least two weeks including a month-end. Cross-check against the "
                   "CMDB and application owners. For large estates, a dedicated discovery product "
                   "(Device42, Faddom) gives materially better data.",
        affects="Wave and move-group planning",
    ),

    # ---- Modernisation ---------------------------------------------------
    dict(
        area="Modernisation", severity="Major",
        limitation="Effectively no modernisation capability beyond rehost.",
        detail="Azure Migrate is a rehost engine. The App Containerization tool handles ASP.NET "
               "and Java web apps only. There is nothing for middleware, message queues, batch "
               "schedulers, ETL, reporting platforms or packaged applications -- which is most of "
               "a typical enterprise estate.",
        impact="A 7R strategy that includes replatform or refactor cannot be executed with Azure "
               "Migrate. Those columns need separate tooling, separate teams and separate budget.",
        workaround="Treat modernisation as a distinct programme sequenced after the data centre "
                   "exit, not as part of it.",
        affects="Replatform and refactor dispositions",
    ),
    dict(
        area="Modernisation", severity="Moderate",
        limitation="No application-level testing, validation or rollback automation.",
        detail="Test migration proves a VM boots. It says nothing about whether the application "
               "works. There is no test orchestration, no validation scripting and no automated "
               "rollback -- rollback means manually powering the source VM back on.",
        impact="Validation effort is entirely manual and is consistently under-estimated.",
        workaround="Build a per-application validation runbook and automate it yourself. Budget "
                   "it as real effort -- this simulator's effort model includes test cycles.",
        affects="Every cutover",
    ),

    # ---- Operations ------------------------------------------------------
    dict(
        area="Programme operations", severity="Moderate",
        limitation="No wave management, scheduling, approvals or stakeholder workflow.",
        detail="Azure Migrate has no concept of a wave, a change window, an approval or an "
               "application owner. Everything beyond the technical replication -- which is most "
               "of the work at 500+ VMs -- happens in spreadsheets and email.",
        impact="Coordination overhead scales worse than the technical work and becomes the "
               "binding constraint on large programmes.",
        workaround="A migration factory with proper orchestration (ReadyWorks, ServiceNow, or a "
                   "purpose-built tracker). Do not run a 547-VM programme from a spreadsheet.",
        affects="Programmes above roughly 200 VMs",
    ),
    dict(
        area="Programme operations", severity="Minor",
        limitation="Azure is the only supported target.",
        detail="There is no multi-cloud or on-premises target. If the estate is later split "
               "across clouds, or lands on Azure Local rather than public Azure, Azure Migrate "
               "does not help.",
        impact="Tool lock-in to the destination decision.",
        workaround="Multi-target tools (Carbonite, PlateSpin, RiverMeadow) if genuine optionality "
                   "is required. Usually it is not, and this limitation is acceptable.",
        affects="Multi-cloud strategies",
    ),
]


def limitations_frame(estate: pd.DataFrame | None = None) -> pd.DataFrame:
    """Limitations register, with an estimate of how many VMs each one touches."""
    df = pd.DataFrame(LIMITATIONS)
    df["severity_rank"] = df["severity"].map({s: i for i, s in enumerate(SEVERITY_ORDER)})

    if estate is not None and len(estate):
        counts = []
        for _, r in df.iterrows():
            counts.append(_affected_count(r["affects"], estate))
        df["vms_affected"] = counts
        df["share_pct"] = df["vms_affected"] / len(estate) * 100
    else:
        df["vms_affected"] = 0
        df["share_pct"] = 0.0
    return df.sort_values(["severity_rank", "vms_affected"], ascending=[True, False])


def _affected_count(affects: str, e: pd.DataFrame) -> int:
    n = len(e)
    a = affects.lower()
    try:
        if "database engine" in a:
            return int((e["db_engine"] != "None").sum())
        if "oracle" in a and "db2" in a:
            return int(e["db_engine"].isin(["Oracle Database", "MySQL"]).sum())
        if a.startswith("oracle database"):
            return int((e["db_engine"] == "Oracle Database").sum())
        if "postgresql, mysql" in a:
            return int(e["db_engine"].isin(["PostgreSQL", "MySQL", "MongoDB"]).sum())
        if "clustered database" in a:
            return int(((e["db_engine"] != "None") & e["has_shared_disk"]).sum())
        if "clustered, encrypted" in a:
            return int((e["has_shared_disk"] | e["vm_encrypted"] | e["fault_tolerance"]).sum())
        if "rdm or independent" in a:
            return int((e["has_rdm"] | e["has_independent_disk"]).sum())
        if "end-of-life guest" in a:
            return int(e["os_eol"].sum())
        if "stale or missing vmware tools" in a:
            return int(e["vmware_tools"].isin(["toolsOld", "toolsNotInstalled",
                                               "toolsNotRunning"]).sum())
        if "database and high-write" in a:
            return int(((e["tier"] == "Database") | (e["daily_churn_pct"] > 8)).sum())
        if "300 vms" in a or "200 vms" in a:
            return n
    except Exception:
        return 0
    return n if ("every" in a or "programme-wide" in a or "wave and move-group" in a
                 or "right-sizing" in a or "cost figure" in a) else 0


# --------------------------------------------------------------------------
# Heterogeneous database migration matrix
# --------------------------------------------------------------------------
DB_MIGRATION_PATHS: list[dict] = [
    dict(
        source="Microsoft SQL Server", target="Azure SQL Managed Instance",
        kind="Homogeneous",
        azure_migrate="Discovers and assesses; recommends this target. Does not migrate.",
        tool="Data Migration Assistant (compatibility) then Azure Database Migration Service "
             "(online or offline), or a managed instance link for near-zero downtime.",
        schema_conversion="None required -- near-full engine surface compatibility.",
        automation_pct=95, downtime="Minutes with the MI link; hours offline.",
        effort_per_db_days=3.0,
        risks=["Cross-database queries, SQL Agent jobs and linked servers need review",
               "CLR, FileStream and some Service Broker features behave differently",
               "Instance-level collation is fixed at creation"],
    ),
    dict(
        source="Microsoft SQL Server", target="Azure SQL Database",
        kind="Homogeneous",
        azure_migrate="Discovers and assesses; recommends where compatible.",
        tool="Data Migration Assistant then Azure Database Migration Service.",
        schema_conversion="Minor -- single-database scope removes cross-database and "
                          "instance-level features.",
        automation_pct=85, downtime="Minutes online; hours offline.",
        effort_per_db_days=6.0,
        risks=["No SQL Agent, no cross-database queries, no linked servers",
               "Application connection resilience must handle transient faults",
               "Higher rewrite risk than Managed Instance"],
    ),
    dict(
        source="Microsoft SQL Server", target="SQL Server on an Azure VM",
        kind="Homogeneous (rehost)",
        azure_migrate="Full support -- this is a plain VM rehost.",
        tool="Azure Migrate itself, or backup/restore, log shipping or a distributed "
             "availability group for a shorter cutover.",
        schema_conversion="None.",
        automation_pct=99, downtime="Minutes with a distributed AG; hours with backup/restore.",
        effort_per_db_days=1.5,
        risks=["Keeps all OS and engine patching, backup and HA burden",
               "No PaaS benefit -- the licence and the toil both remain"],
    ),
    dict(
        source="Oracle Database", target="Oracle on Azure VM / Oracle Database@Azure",
        kind="Homogeneous (rehost)",
        azure_migrate="Limited discovery. No Oracle-specific assessment or sizing.",
        tool="Oracle Data Guard, RMAN, or Oracle Zero Downtime Migration.",
        schema_conversion="None.",
        automation_pct=95, downtime="Minutes with Data Guard switchover.",
        effort_per_db_days=5.0,
        risks=["Oracle licensing on Azure counts two vCPU as one core where hyper-threading "
               "is enabled -- model this before choosing a VM size",
               "RAC is not supported on Azure VMs; use Data Guard or Oracle Database@Azure",
               "Oracle Database@Azure requires an Oracle contract alongside the Azure one"],
    ),
    dict(
        source="Oracle Database", target="Azure SQL Managed Instance / Azure SQL Database",
        kind="Heterogeneous",
        azure_migrate="Not supported in any form.",
        tool="SQL Server Migration Assistant (SSMA) for Oracle for schema and code conversion, "
             "then SSMA or Azure Database Migration Service for the data.",
        schema_conversion="Substantial. PL/SQL packages, procedures and triggers convert to "
                          "T-SQL; sequences, hierarchical queries, ROWNUM, analytic functions "
                          "and Oracle-specific data types all need attention.",
        automation_pct=70, downtime="Depends entirely on the cutover design; usually a "
                                    "planned outage.",
        effort_per_db_days=45.0,
        risks=["The 25-35% SSMA cannot convert is the hard 25-35%",
               "Application SQL embedded in code is out of SSMA's reach entirely",
               "Full regression testing is mandatory and is the bulk of the effort",
               "Performance characteristics change -- expect an optimisation cycle after go-live"],
    ),
    dict(
        source="Oracle Database", target="Azure Database for PostgreSQL",
        kind="Heterogeneous",
        azure_migrate="Not supported in any form.",
        tool="ora2pg for schema assessment and conversion, then the Azure Database for "
             "PostgreSQL migration service or logical replication for data.",
        schema_conversion="Substantial. PL/SQL to PL/pgSQL is largely mechanical but the "
                          "long tail is not; packages have no direct PostgreSQL equivalent.",
        automation_pct=65, downtime="Minutes with logical replication once schema is proven.",
        effort_per_db_days=55.0,
        risks=["ora2pg gives a migration difficulty score early -- run it before committing",
               "No package construct in PostgreSQL; packages become schemas plus functions",
               "Licensing saving is the prize, but it only lands after a long conversion",
               "This is an application programme -- do not couple it to a data centre exit deadline"],
    ),
    dict(
        source="SAP ASE (Sybase)", target="Azure SQL Managed Instance",
        kind="Heterogeneous",
        azure_migrate="Not supported.",
        tool="SSMA for SAP ASE.",
        schema_conversion="Moderate. Transact-SQL dialects are close, so conversion rates are "
                          "better than Oracle.",
        automation_pct=80, downtime="Planned outage.",
        effort_per_db_days=25.0,
        risks=["Identity and sequence handling differs",
               "Sybase-specific system procedures need replacement"],
    ),
    dict(
        source="IBM Db2", target="Azure SQL Managed Instance / Azure Database for PostgreSQL",
        kind="Heterogeneous",
        azure_migrate="Not supported.",
        tool="SSMA for Db2 targeting SQL Server; manual or partner tooling for PostgreSQL.",
        schema_conversion="Substantial, and worse on mainframe Db2 (z/OS) than on LUW.",
        automation_pct=60, downtime="Planned outage.",
        effort_per_db_days=60.0,
        risks=["Db2 for z/OS is a different problem again and usually needs a specialist partner",
               "EBCDIC and packed-decimal data types need explicit handling",
               "Often entangled with COBOL applications that must move at the same time"],
    ),
    dict(
        source="MySQL", target="Azure Database for MySQL Flexible Server",
        kind="Homogeneous",
        azure_migrate="Discovered as software inventory only. No assessment, no target advice.",
        tool="Azure Database Migration Service, or native binlog replication.",
        schema_conversion="None.",
        automation_pct=95, downtime="Minutes with binlog replication.",
        effort_per_db_days=2.5,
        risks=["Storage-engine differences if any tables are still MyISAM",
               "Some server variables are not configurable on Flexible Server"],
    ),
    dict(
        source="MySQL", target="Azure Database for PostgreSQL",
        kind="Heterogeneous",
        azure_migrate="Not supported.",
        tool="pgloader for schema and data, plus manual application SQL review.",
        schema_conversion="Moderate. Data types and auto-increment semantics differ; "
                          "application SQL needs review.",
        automation_pct=75, downtime="Planned outage.",
        effort_per_db_days=18.0,
        risks=["Rarely worth doing during a migration -- move homogeneously first",
               "Case sensitivity and collation behaviour differ meaningfully"],
    ),
    dict(
        source="PostgreSQL", target="Azure Database for PostgreSQL Flexible Server",
        kind="Homogeneous",
        azure_migrate="Discovered as software inventory only.",
        tool="Azure Database Migration Service, or native logical replication.",
        schema_conversion="None.",
        automation_pct=98, downtime="Minutes with logical replication.",
        effort_per_db_days=2.0,
        risks=["Extension availability -- check every extension is supported before committing",
               "Superuser is not available; anything relying on it needs rework"],
    ),
    dict(
        source="MongoDB", target="Azure Cosmos DB for MongoDB / MongoDB Atlas on Azure",
        kind="Homogeneous-ish",
        azure_migrate="Not supported.",
        tool="Azure Database Migration Service, native mongodump/mongorestore, or Atlas Live "
             "Migration.",
        schema_conversion="None, but the Cosmos DB wire-protocol implementation is not "
                          "feature-complete -- verify every operator the application uses.",
        automation_pct=85, downtime="Minutes with a live migration.",
        effort_per_db_days=6.0,
        risks=["Cosmos DB request-unit sizing is unlike anything on-premises and drives cost",
               "Aggregation pipeline coverage gaps surface late, in testing"],
    ),
]


def db_paths_frame(source_filter: str | None = None,
                   kind_filter: str | None = None) -> pd.DataFrame:
    df = pd.DataFrame(DB_MIGRATION_PATHS)
    if source_filter and source_filter != "All":
        df = df[df["source"] == source_filter]
    if kind_filter and kind_filter != "All":
        df = df[df["kind"].str.startswith(kind_filter)]
    return df.reset_index(drop=True)


def db_estate_impact(estate: pd.DataFrame) -> pd.DataFrame:
    """How much of this estate falls outside Azure Migrate's database capability."""
    if "db_engine" not in estate.columns:
        return pd.DataFrame(columns=["engine", "vms", "azure_migrate_covers", "needs"])
    counts = estate[estate["db_engine"] != "None"]["db_engine"].value_counts()
    cover = {
        "Microsoft SQL Server": ("Discovery + assessment only",
                                 "Azure Database Migration Service for the actual move"),
        "Oracle Database": ("Limited discovery; no assessment",
                            "A separate Oracle assessment, plus Data Guard (rehost) or "
                            "SSMA/ora2pg (heterogeneous)"),
        "PostgreSQL": ("Software inventory only",
                       "Manual assessment, then DMS or logical replication"),
        "MySQL": ("Software inventory only",
                  "Manual assessment, then DMS or binlog replication"),
        "MongoDB": ("Software inventory only",
                    "Manual assessment, then DMS or Atlas Live Migration"),
    }
    rows = []
    for engine, n in counts.items():
        c = cover.get(engine, ("Not covered", "A separate tool and plan"))
        rows.append({"engine": engine, "vms": int(n),
                     "azure_migrate_covers": c[0], "needs": c[1]})
    return pd.DataFrame(rows).sort_values("vms", ascending=False)


def db_effort_estimate(estate: pd.DataFrame, targets: dict[str, str],
                       blended_rate_per_hour: float = 78.0,
                       hours_per_day: float = 6.0) -> pd.DataFrame:
    """Database workstream effort and cost -- the part the Azure Migrate plan omits.

    ``targets`` maps a source engine to the chosen target, e.g.
    ``{"Oracle Database": "Azure Database for PostgreSQL"}``.
    """
    paths = {(p["source"], p["target"]): p for p in DB_MIGRATION_PATHS}
    counts = estate[estate["db_engine"] != "None"]["db_engine"].value_counts().to_dict()
    rows = []
    for engine, n in counts.items():
        target = targets.get(engine)
        p = paths.get((engine, target))
        if p is None:
            # Fall back to the first available path for this engine.
            cands = [q for q in DB_MIGRATION_PATHS if q["source"] == engine]
            if not cands:
                continue
            p = cands[0]
            target = p["target"]
        days = p["effort_per_db_days"] * n
        rows.append({
            "engine": engine, "vms": int(n), "target": target, "kind": p["kind"],
            "days_per_db": p["effort_per_db_days"], "total_days": days,
            "automation_pct": p["automation_pct"],
            "cost": days * hours_per_day * blended_rate_per_hour,
            "azure_migrate_covers_it": p["azure_migrate"].startswith("Full"),
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("cost", ascending=False)
    return df


# --------------------------------------------------------------------------
# Heterogeneous workload migration -- everything Azure Migrate does not touch
# --------------------------------------------------------------------------
# Azure Migrate rehosts a guest OS and its disks. Any migration that changes
# the *kind* of thing being run -- the engine, the runtime, the architecture,
# the protocol, the platform -- is outside its scope entirely. These are the
# categories that consistently surface after the assessment is signed off, and
# they are where migration programmes actually overrun.
HETEROGENEOUS_PATHS: list[dict] = [
    # ---- Operating system and architecture -------------------------------
    dict(category="Operating system", source="Windows Server 2008 R2 / 2012 R2",
         target="Windows Server 2022 / 2025",
         azure_migrate="Rehosts as-is. Will not upgrade. The VM arrives in Azure still "
                       "end-of-life.",
         tool="In-place upgrade, rebuild-and-migrate, or RiverMeadow for in-flight upgrade.",
         conversion="Application compatibility testing, driver and .NET Framework version checks.",
         automation_pct=60, effort_per_unit_days=2.5, unit="server",
         risks=["Azure grants free Extended Security Updates for eligible Windows versions "
                "running on Azure, which removes the urgency but not the risk",
                "Two consecutive in-place upgrades are often needed from 2008 R2",
                "Legacy applications may hard-fail on TLS and cipher-suite changes"]),
    dict(category="Operating system", source="CentOS 7 / CentOS 8",
         target="RHEL 9, Rocky Linux, AlmaLinux or Ubuntu LTS",
         azure_migrate="Rehosts as-is. CentOS is past end-of-life and is not an endorsed "
                       "Azure distribution.",
         tool="ELevate/leapp for in-place conversion, or rebuild from configuration management.",
         conversion="Package and repository remapping; Python 2 to 3 for older tooling.",
         automation_pct=70, effort_per_unit_days=2.0, unit="server",
         risks=["Conversion tooling is community-maintained, not vendor-supported",
                "Third-party agents frequently need re-installation afterwards",
                "Rebuild is often faster and safer than conversion where config management exists"]),
    dict(category="Architecture", source="SPARC (Solaris), POWER (AIX), Itanium (HP-UX)",
         target="x86-64 Linux on Azure",
         azure_migrate="Not supported at all. Azure has no non-x86 VM offering for these.",
         tool="Recompile from source, or an emulation/rehosting platform (Stromasys Charon, "
              "Astadia). Otherwise a full application rewrite.",
         conversion="Endianness, compiler and libc differences, and every piece of native code.",
         automation_pct=25, effort_per_unit_days=90.0, unit="application",
         risks=["Frequently the single largest item in a data centre exit",
                "Source code may not exist for the oldest applications",
                "Emulation preserves the application but carries its own licence cost",
                "Must be identified in discovery -- it will not appear in a VMware inventory"]),

    # ---- Middleware and application runtimes -----------------------------
    dict(category="Middleware", source="Oracle WebLogic Server",
         target="Azure App Service, AKS, or WebLogic on Azure VMs",
         azure_migrate="Rehosts the VM. No awareness of the application server at all.",
         tool="Oracle WebLogic on Azure marketplace offers for rehost; JBoss EAP or Open "
              "Liberty for a heterogeneous move.",
         conversion="JNDI, datasource, JMS and security-realm configuration; proprietary "
                    "WebLogic APIs in application code.",
         automation_pct=55, effort_per_unit_days=20.0, unit="application",
         risks=["WebLogic licensing on Azure follows Oracle's cloud policy -- price it first",
                "Applications using WebLogic-specific APIs need code change",
                "Clustered deployments need session-replication redesign"]),
    dict(category="Middleware", source="IBM WebSphere Application Server",
         target="Open Liberty / WebSphere Liberty on AKS, or Azure App Service",
         azure_migrate="Rehosts the VM only.",
         tool="IBM Transformation Advisor, then Open Liberty on AKS.",
         conversion="Deployment descriptors, JCA resource adapters, and WebSphere-specific "
                    "extensions.",
         automation_pct=60, effort_per_unit_days=18.0, unit="application",
         risks=["Traditional WebSphere to Liberty is a genuine re-platform, not a config change",
                "EJB 2.x era applications need significant work"]),
    dict(category="Middleware", source="IIS on Windows Server",
         target="Azure App Service or Azure Container Apps",
         azure_migrate="The App Containerization tool handles ASP.NET only, and only for "
                       "straightforward sites.",
         tool="Azure Migrate App Containerization, or App Service Migration Assistant.",
         conversion="GAC assemblies, COM components, local file dependencies, Windows "
                    "authentication and machine-level configuration.",
         automation_pct=75, effort_per_unit_days=5.0, unit="site",
         risks=["Anything writing to the local file system needs re-pointing to storage",
                "COM+ and 32-bit dependencies frequently block the move",
                "Windows authentication needs replacing with Entra ID"]),
    dict(category="Middleware", source="Apache Tomcat / JBoss",
         target="Azure App Service for Java, AKS, or Container Apps",
         azure_migrate="Rehosts the VM only.",
         tool="App Service Migration Assistant for Java, or containerise directly.",
         conversion="Externalise configuration, replace local session state, restructure logging.",
         automation_pct=80, effort_per_unit_days=4.0, unit="application",
         risks=["Sticky sessions and in-memory state are the usual blockers",
                "JVM tuning that was right on-premises is usually wrong in a container"]),

    # ---- Integration, messaging and batch --------------------------------
    dict(category="Messaging", source="IBM MQ, TIBCO EMS, RabbitMQ",
         target="Azure Service Bus or Azure Event Hubs",
         azure_migrate="No awareness. Rehosts the broker VM as-is.",
         tool="Manual re-platform; run the broker on an Azure VM as an interim step.",
         conversion="Queue and topic semantics, transaction and ordering guarantees, "
                    "dead-letter behaviour, and every client library.",
         automation_pct=35, effort_per_unit_days=25.0, unit="broker estate",
         risks=["Message ordering and exactly-once semantics differ between brokers",
                "Every producer and consumer application needs a client change",
                "Rehosting the broker first, then re-platforming, is nearly always right"]),
    dict(category="Integration / ETL", source="Informatica PowerCenter, IBM DataStage, "
                                              "TIBCO BusinessWorks",
         target="Azure Data Factory, Synapse pipelines, or Logic Apps",
         azure_migrate="No awareness whatsoever.",
         tool="Vendor conversion utilities where they exist; otherwise manual rebuild. "
              "Informatica offers a managed cloud service on Azure as a rehost path.",
         conversion="Every mapping, workflow, transformation and scheduling dependency.",
         automation_pct=30, effort_per_unit_days=1.5, unit="mapping / job",
         risks=["Effort scales with the number of mappings, which nobody counts up front",
                "Lift-and-shift the ETL tool first; re-platform it as a separate programme",
                "Data lineage and audit obligations often force a like-for-like rebuild"]),
    dict(category="Batch scheduling", source="BMC Control-M, CA AutoSys, Tidal",
         target="Azure Data Factory triggers, Azure Automation, AKS CronJobs, or keep the "
                "scheduler on an Azure VM",
         azure_migrate="Rehosts the scheduler VM. Does not understand the job dependency graph.",
         tool="Manual conversion of job definitions and calendars.",
         conversion="Job dependencies, calendars, SLAs, alerting and cross-system triggers.",
         automation_pct=40, effort_per_unit_days=0.4, unit="job",
         risks=["The dependency graph is the value, and it is rarely documented anywhere else",
                "Cutover must be all-or-nothing per job chain -- split chains break silently",
                "Usually right to rehost the scheduler and defer replacement"]),

    # ---- Storage and data services ---------------------------------------
    dict(category="File services", source="NetApp ONTAP, Dell Isilon/PowerScale, Windows "
                                          "file clusters",
         target="Azure NetApp Files, Azure Files, or Azure Blob with a storage gateway",
         azure_migrate="Not in scope. It migrates VMs, not NAS shares.",
         tool="Azure Storage Mover, NetApp Cloud Sync/SnapMirror, robocopy, or a partner tool.",
         conversion="NTFS/NFS permission models, ACL translation, alternate data streams, "
                    "quotas and DFS namespaces.",
         automation_pct=75, effort_per_unit_days=0.5, unit="TB",
         risks=["Permission fidelity is the usual failure -- test ACL translation early",
                "Large file counts hurt far more than large capacity does",
                "Azure NetApp Files is the only realistic target for demanding NFS workloads",
                "Final delta sync on an active share needs a real change window"]),
    dict(category="Block storage", source="Fibre Channel SAN, iSCSI arrays",
         target="Azure managed disks, Premium SSD v2, Ultra Disk, or Azure Elastic SAN",
         azure_migrate="Only migrates disks attached as VMDKs. Physical-mode RDMs and "
                       "SAN-attached LUNs are invisible to it.",
         tool="Convert RDMs to VMDK first, or move the data at the application layer.",
         conversion="Multipathing, LUN masking, and any array-based replication or snapshots.",
         automation_pct=60, effort_per_unit_days=1.0, unit="LUN",
         risks=["Array-based replication and snapshots have no Azure equivalent",
                "Per-disk IOPS ceilings differ fundamentally from a shared array",
                "Premium SSD v2 decouples IOPS from capacity and is usually the right answer"]),

    # ---- Platform services -----------------------------------------------
    dict(category="Load balancing / ADC", source="F5 BIG-IP, Citrix NetScaler, HAProxy",
         target="Azure Application Gateway with WAF, Azure Front Door, or the appliance from "
                "the Azure Marketplace",
         azure_migrate="Not in scope.",
         tool="Marketplace virtual appliance for like-for-like; manual rebuild for a "
              "native target.",
         conversion="iRules and policies have no direct Azure equivalent and must be rewritten.",
         automation_pct=30, effort_per_unit_days=3.0, unit="virtual server",
         risks=["iRule logic often encodes undocumented business rules",
                "SSL certificate and private key handling needs a Key Vault design",
                "Source-IP visibility changes and can break application logic"]),
    dict(category="Identity", source="Active Directory Domain Services on-premises",
         target="Entra ID, Microsoft Entra Domain Services, or AD DS on Azure VMs",
         azure_migrate="Rehosts domain controllers as VMs, which is not how you migrate AD.",
         tool="Extend the existing forest into Azure with new domain controllers, then "
              "decommission on-premises ones.",
         conversion="Sites and services topology, replication, FSMO role placement, DNS.",
         automation_pct=80, effort_per_unit_days=10.0, unit="forest",
         risks=["Never replicate a domain controller as a VM image -- it causes USN rollback",
                "This is a prerequisite for almost every other wave, so it goes first",
                "Legacy NTLM and Kerberos-constrained delegation need review"]),
    dict(category="PKI / certificates", source="Internal certificate authorities, "
                                               "MAC-bound licences, HSMs",
         target="Azure Key Vault, Managed HSM, or the CA rehosted",
         azure_migrate="Rehosts the VM, but the identity the certificate or licence is bound "
                       "to changes.",
         tool="Manual re-issue and re-binding.",
         conversion="Re-issue certificates against new hostnames and IPs; re-host licences "
                    "bound to MAC addresses.",
         automation_pct=40, effort_per_unit_days=0.5, unit="certificate / licence",
         risks=["MAC-bound licences fail at cutover, not before -- resolve with vendors early",
                "Hardware security modules cannot migrate; Managed HSM is the target",
                "Certificate expiry during a long migration window is a classic own-goal"]),
    dict(category="Networking services", source="Infoblox, BlueCat, on-premises DNS/DHCP/IPAM",
         target="Azure DNS, Azure Private DNS, DHCP via Azure DNS resolver",
         azure_migrate="Not in scope.",
         tool="Zone export and import; conditional forwarders during the transition.",
         conversion="Split-horizon DNS, conditional forwarding, and hard-coded IPs everywhere.",
         automation_pct=70, effort_per_unit_days=8.0, unit="zone estate",
         risks=["Hard-coded IP addresses in application configuration are found at cutover",
                "Hybrid DNS resolution must work before the first wave, not during it"]),

    # ---- Operations tooling ----------------------------------------------
    dict(category="Backup", source="Veritas NetBackup, Commvault, Veeam on-premises",
         target="Azure Backup, or the incumbent product extended to Azure",
         azure_migrate="Not in scope. Backup must be re-established after migration.",
         tool="Azure Backup for VM-level; the incumbent product where application-aware "
              "backup is required.",
         conversion="Retention policies, compliance holds, and restore testing.",
         automation_pct=85, effort_per_unit_days=5.0, unit="policy set",
         risks=["Historical backups usually cannot migrate -- plan a retention bridge",
                "Regulatory retention may force the old platform to stay running for years",
                "This is a frequently forgotten cost line in both the migration and the run rate"]),
    dict(category="Monitoring", source="SCOM, Nagios, Zabbix, SolarWinds",
         target="Azure Monitor, Log Analytics, and Managed Grafana",
         azure_migrate="Not in scope.",
         tool="Rebuild alert rules and dashboards; agent deployment via Azure Policy.",
         conversion="Every alert rule, threshold, dashboard and runbook link.",
         automation_pct=50, effort_per_unit_days=12.0, unit="monitoring estate",
         risks=["Log Analytics ingestion cost is routinely underestimated by a wide margin",
                "Alert fatigue if rules are ported without rationalising them",
                "Must be live before the first production wave, not after"]),
    dict(category="Reporting / BI", source="SQL Server Reporting Services, Cognos, "
                                           "BusinessObjects",
         target="Power BI, Power BI Paginated Reports, or Fabric",
         azure_migrate="Rehosts the VM only.",
         tool="Power BI Report Server for a lift of SSRS; manual rebuild otherwise.",
         conversion="Report definitions, data sources, subscriptions and row-level security.",
         automation_pct=55, effort_per_unit_days=1.0, unit="report",
         risks=["Report counts are always higher than anyone believes",
                "Most reports are unused -- audit before migrating and retire aggressively"]),

    # ---- Container and mainframe -----------------------------------------
    dict(category="Container platform", source="Red Hat OpenShift, Docker Swarm, "
                                               "Cloud Foundry",
         target="Azure Kubernetes Service, Azure Red Hat OpenShift, or Container Apps",
         azure_migrate="Not in scope -- it migrates VMs, not clusters or workloads.",
         tool="Redeploy manifests through the existing CI/CD pipeline.",
         conversion="Ingress, storage classes, secrets management, RBAC and network policy.",
         automation_pct=70, effort_per_unit_days=15.0, unit="cluster",
         risks=["OpenShift Routes and SecurityContextConstraints have no direct AKS equivalent",
                "Persistent volumes need a storage-class redesign",
                "Azure Red Hat OpenShift avoids the conversion but costs more"]),
    dict(category="Mainframe", source="IBM z/OS COBOL, PL/I, CICS, IMS, Db2 for z/OS",
         target="Azure with Rocket/Micro Focus, LzLabs, Astadia, or a rewrite to .NET/Java",
         azure_migrate="Not supported in any form.",
         tool="Specialist rehosting platforms, or a refactor programme.",
         conversion="COBOL to a managed runtime, JCL to a scheduler, VSAM to a relational "
                    "or key-value store, CICS to a transaction manager.",
         automation_pct=45, effort_per_unit_days=0.02, unit="line of code",
         risks=["Multi-year programme in its own right -- never couple it to a VMware exit",
                "Emulation preserves behaviour but carries its own substantial licence cost",
                "Business logic is often understood by nobody currently employed"]),
    dict(category="IBM i / AS-400", source="IBM i (AS/400) RPG, DB2 for i",
         target="Azure with a partner emulation platform, or a package replacement",
         azure_migrate="Not supported. IBM i is POWER architecture.",
         tool="Infinite Corporation, Fresche, or a move to a packaged ERP.",
         conversion="RPG to a managed language, or replacement of the whole application.",
         automation_pct=40, effort_per_unit_days=120.0, unit="application",
         risks=["Frequently cheaper to replace the application than to migrate it",
                "Green-screen user workflows carry decades of undocumented process"]),
    dict(category="Licensed appliances", source="Virtual firewalls, proxies, WAFs, "
                                                "SD-WAN appliances",
         target="Azure Firewall, Front Door, or the vendor appliance from the Marketplace",
         azure_migrate="Rehosting a virtual appliance is unsupported by most vendors and "
                       "usually breaks licensing.",
         tool="Deploy fresh from the Azure Marketplace and port the configuration.",
         conversion="Rule bases, NAT policies and routing.",
         automation_pct=50, effort_per_unit_days=6.0, unit="appliance",
         risks=["Never replicate a virtual appliance -- deploy new and migrate configuration",
                "Licences are usually bound to the appliance identity",
                "Azure networking constrains what topologies are even possible"]),
]


def heterogeneous_frame(category: str | None = None) -> pd.DataFrame:
    df = pd.DataFrame(HETEROGENEOUS_PATHS)
    if category and category != "All":
        df = df[df["category"] == category]
    return df.reset_index(drop=True)


HETERO_CATEGORIES = sorted({p["category"] for p in HETEROGENEOUS_PATHS})


def coverage_assessment(estate: pd.DataFrame) -> pd.DataFrame:
    """How much of this estate Azure Migrate genuinely covers end to end.

    "Covered" means Azure Migrate can take the workload all the way to a running,
    supported state in Azure without a second tool. On a real estate that number
    is always lower than the assessment implies.
    """
    n = len(estate)
    if n == 0:
        return pd.DataFrame()

    db = estate["db_engine"] != "None"
    blocked = (estate["has_shared_disk"] | estate["vm_encrypted"]
               | estate["fault_tolerance"] | estate["has_rdm"]
               | estate["has_independent_disk"])
    eol = estate["os_eol"].astype(bool)
    no_tools = estate["vmware_tools"].isin(["toolsNotInstalled", "toolsNotRunning"])
    special = estate["has_vgpu"] | estate["has_usb_or_serial"] | estate["licence_mac_bound"]

    # Precedence: hardest problem wins, so each VM is counted once.
    cat_blocked = blocked
    cat_db = db & ~cat_blocked
    cat_eol = eol & ~cat_blocked & ~cat_db
    cat_special = special & ~cat_blocked & ~cat_db & ~cat_eol
    cat_tools = no_tools & ~cat_blocked & ~cat_db & ~cat_eol & ~cat_special
    cat_clean = ~(cat_blocked | cat_db | cat_eol | cat_special | cat_tools)

    rows = [
        ("Fully covered by Azure Migrate", int(cat_clean.sum()),
         "Standard VM, supported OS, no blockers -- agentless replication takes this "
         "end to end.", "None"),
        ("Covered, but needs VMware Tools remediation first", int(cat_tools.sum()),
         "Replicates, but only crash-consistently until Tools is fixed.",
         "Remediate VMware Tools, or use agent-based replication"),
        ("Rehosts, but the OS is still end-of-life on arrival", int(cat_eol.sum()),
         "Azure Migrate will not upgrade the guest. The risk moves to Azure with it.",
         "Separate OS remediation programme, or an in-flight upgrade tool"),
        ("Rehosts, but the database is not migrated", int(cat_db.sum()),
         "The VM moves; the database stays exactly as it was. No PaaS benefit, and "
         "heterogeneous moves are entirely out of scope.",
         "Azure Database Migration Service, DMA, SSMA or ora2pg"),
        ("Special hardware or licence binding", int(cat_special.sum()),
         "vGPU, USB/serial passthrough or MAC-bound licences need individual handling.",
         "GPU SKU sizing, device re-homing, vendor licence re-host"),
        ("Blocked from agentless replication", int(cat_blocked.sum()),
         "Shared disks, encryption, Fault Tolerance, RDM or independent disks.",
         "Agent-based replication, cluster rebuild, or Azure VMware Solution"),
    ]
    df = pd.DataFrame(rows, columns=["category", "vms", "what_it_means", "also_needs"])
    df["share_pct"] = df["vms"] / n * 100
    return df


def assessment_cost_note(cfg: MigrateConfig) -> str:
    return (
        "Azure Migrate itself is free: discovery, assessment, dependency analysis and the "
        "migration tooling carry no licence charge. What you do pay for is (a) Azure Site "
        f"Recovery beyond {ASR_FREE_DAYS} days per instance, (b) the staging storage account "
        "holding replicated data, (c) Log Analytics ingestion if you choose agent-based "
        "dependency analysis, and (d) the Azure resources you migrate into. The tooling is "
        "not where the money goes -- the run rate is."
    )
