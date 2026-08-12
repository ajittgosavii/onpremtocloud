"""Readiness assessment and 7R disposition.

Two independent judgements are produced per VM:

1. **Azure readiness** -- can this VM actually run on Azure IaaS, and under what
   conditions? The rules mirror Azure Migrate's own readiness checks
   (Ready / Ready with conditions / Not ready) and the agentless-replication
   support matrix.
2. **7R disposition** -- what *should* happen to it: Retire, Retain, Rehost,
   Replatform, Refactor, Repurchase or Relocate.

Both are deterministic and explainable: every verdict carries the list of
findings that produced it, so a client can challenge any single VM.
"""

import numpy as np
import pandas as pd

from core import azure_catalog as cat

READY = "Ready for Azure"
CONDITIONAL = "Ready with conditions"
NOT_READY = "Not ready for Azure"
UNKNOWN = "Readiness unknown"

# 7R strategies, ordered from cheapest/fastest to most transformational.
STRATEGIES = ["Retire", "Retain", "Relocate", "Rehost", "Replatform", "Repurchase", "Refactor"]


# --------------------------------------------------------------------------
# Readiness
# --------------------------------------------------------------------------
def _readiness_findings(row: pd.Series) -> tuple[str, list[str], list[str]]:
    """Return (verdict, blockers, conditions) for one VM."""
    blockers: list[str] = []
    conditions: list[str] = []

    support = str(row.get("azure_os_support", "supported"))
    guest = str(row.get("guest_os", ""))
    if support == "unsupported":
        blockers.append(f"Guest OS '{guest}' is not supported on Azure -- the VM will not boot "
                        "or start with Azure support. In-place upgrade or rebuild is required.")
    elif support == "esu-required":
        conditions.append(f"'{guest}' is out of mainstream support. Azure grants free Extended "
                          "Security Updates for eligible Windows Server/SQL versions when the VM "
                          "runs on Azure, but plan an OS upgrade path.")
    elif support == "endorsed-eol":
        conditions.append(f"'{guest}' is past its vendor end-of-life. Azure will run it but it is "
                          "not an endorsed distribution -- support will be best-effort.")

    # --- platform ceilings ------------------------------------------------
    if int(row.get("vcpu", 0)) > cat.MAX_VCPU:
        blockers.append(f"{int(row['vcpu'])} vCPU exceeds the largest Azure VM ({cat.MAX_VCPU} vCPU).")
    if float(row.get("ram_gib", 0)) > cat.MAX_RAM_GIB:
        blockers.append(f"{row['ram_gib']:.0f} GiB RAM exceeds the largest Azure VM "
                        f"({cat.MAX_RAM_GIB} GiB).")
    if int(row.get("total_disks", 1)) > cat.MAX_DATA_DISKS + 1:
        blockers.append(f"{int(row['total_disks'])} disks exceeds the Azure limit of "
                        f"{cat.MAX_DATA_DISKS} data disks + 1 OS disk.")
    if int(row.get("nic_count", 1)) > cat.MAX_NICS:
        blockers.append(f"{int(row['nic_count'])} NICs exceeds the Azure maximum of {cat.MAX_NICS}.")

    # Largest single disk. Data volume is spread across data_disk_count disks.
    n_data = max(int(row.get("data_disk_count", 0)), 1)
    largest_disk = max(float(row.get("os_disk_gib", 0)),
                       float(row.get("data_disk_gib", 0)) / n_data)
    if largest_disk > cat.MAX_DISK_GIB:
        blockers.append(f"A single disk of ~{largest_disk:,.0f} GiB exceeds the "
                        f"{cat.MAX_DISK_GIB:,} GiB managed-disk limit. Split the volume or use "
                        "Azure NetApp Files / Elastic SAN.")

    # --- migration-path conditions ---------------------------------------
    if bool(row.get("has_shared_disk", False)):
        blockers.append("Shared/clustered disk (MSCS, Oracle RAC or similar). Agentless "
                        "replication cannot capture it consistently -- rebuild the cluster in "
                        "Azure with shared managed disks, or use an application-level method.")
    if bool(row.get("has_rdm", False)):
        conditions.append("Raw Device Mapping present. Physical-mode RDMs are not replicated; "
                          "convert to VMDK first or migrate the data separately.")
    if bool(row.get("has_independent_disk", False)):
        conditions.append("Independent/non-persistent disk present -- excluded from snapshots, so "
                          "it will not replicate. Convert to a dependent disk before migration.")
    if bool(row.get("vm_encrypted", False)):
        blockers.append("VM is encrypted with vSphere VM Encryption. Agentless replication is "
                        "unsupported -- decrypt first, or use agent-based replication.")
    if bool(row.get("fault_tolerance", False)):
        conditions.append("vSphere Fault Tolerance is enabled and has no Azure equivalent. "
                          "Redesign for availability zones or an availability set.")
    if bool(row.get("has_vgpu", False)):
        conditions.append("vGPU attached. Requires an Azure NV/NC-series size -- confirm quota, "
                          "regional availability and the substantially higher run rate.")
    if bool(row.get("has_usb_or_serial", False)):
        conditions.append("USB or serial passthrough device attached. Azure has no equivalent; "
                          "re-home the device to a network appliance or IP-based service.")
    if bool(row.get("licence_mac_bound", False)):
        conditions.append("Software licence is bound to the NIC MAC address, which changes on "
                          "migration. Arrange re-hosting keys with the vendor before cutover.")

    tools = str(row.get("vmware_tools", "toolsOk"))
    if tools in ("toolsNotInstalled", "toolsNotRunning"):
        conditions.append(f"VMware Tools status is '{tools}'. Agentless discovery cannot read the "
                          "guest, and application-consistent snapshots are unavailable -- "
                          "expect crash-consistent replication only.")
    elif tools == "toolsOld":
        conditions.append("VMware Tools is out of date -- update before replication to get "
                          "application-consistent snapshots.")

    if bool(row.get("has_snapshot", False)) and int(row.get("snapshot_age_days", 0)) > 30:
        conditions.append(f"Open snapshot {int(row['snapshot_age_days'])} days old. Consolidate "
                          "before replication -- long snapshot chains slow replication and risk "
                          "datastore exhaustion.")

    if str(row.get("firmware", "bios")).lower() == "efi":
        conditions.append("UEFI firmware -- migrate as an Azure Generation 2 VM. Secure Boot and "
                          "vTPM settings need to be re-applied in Azure.")

    if float(row.get("iops_peak") or 0) > 20000:
        conditions.append(f"Peak {float(row['iops_peak']):,.0f} IOPS exceeds what a single Premium "
                          "SSD v1 disk delivers. Use Premium SSD v2, Ultra Disk, or stripe across "
                          "disks -- and confirm the VM size's uncached IOPS ceiling.")

    if not bool(row.get("powered_on", True)):
        conditions.append("VM is powered off. No performance data exists, so sizing falls back to "
                          "as-provisioned -- and it is a strong retire candidate.")

    if blockers:
        return NOT_READY, blockers, conditions
    if conditions:
        return CONDITIONAL, blockers, conditions
    return READY, [], []


def assess_readiness(df: pd.DataFrame) -> pd.DataFrame:
    verdicts, blocks, conds = [], [], []
    for _, row in df.iterrows():
        v, b, c = _readiness_findings(row)
        verdicts.append(v)
        blocks.append(b)
        conds.append(c)
    out = df.copy()
    out["readiness"] = verdicts
    out["blockers"] = blocks
    out["conditions"] = conds
    out["blocker_count"] = [len(b) for b in blocks]
    out["condition_count"] = [len(c) for c in conds]
    out["readiness_detail"] = [
        " | ".join(b + c) if (b or c) else "No issues found."
        for b, c in zip(blocks, conds)
    ]
    return out


# --------------------------------------------------------------------------
# Performance coverage / confidence rating (Azure Migrate's 1-5 stars)
# --------------------------------------------------------------------------
def confidence_rating(coverage_pct: float) -> int:
    """Azure Migrate maps the share of available performance data points to stars."""
    if coverage_pct >= 80:
        return 5
    if coverage_pct >= 60:
        return 4
    if coverage_pct >= 40:
        return 3
    if coverage_pct >= 20:
        return 2
    return 1


def estimate_coverage(df: pd.DataFrame, profiling_days: int, requested_days: int,
                      powered_on_share: float | None = None) -> float:
    """Share of the requested performance history the appliance has actually collected."""
    if requested_days <= 0:
        return 100.0
    duration_share = min(profiling_days / requested_days, 1.0)
    on_share = powered_on_share if powered_on_share is not None else float(df["powered_on"].mean())
    return float(np.clip(duration_share * on_share * 100, 0, 100))


# --------------------------------------------------------------------------
# 7R disposition
# --------------------------------------------------------------------------
def dispose(df: pd.DataFrame,
            modernisation_appetite: str = "balanced",
            retire_zombies: bool = True,
            allow_repurchase: bool = True,
            avs_for_blockers: bool = True) -> pd.DataFrame:
    """Assign a 7R strategy to every VM with a written rationale.

    ``modernisation_appetite`` shifts the rehost/replatform boundary:
    ``lift-and-shift`` keeps almost everything on IaaS, ``aggressive`` pushes
    databases and stateless web tiers into PaaS.
    """
    appetite = {"lift-and-shift": 0.0, "balanced": 1.0, "aggressive": 2.0}[modernisation_appetite]

    strategies, rationales, targets = [], [], []
    for _, r in df.iterrows():
        strategy, why, target = _dispose_one(r, appetite, retire_zombies,
                                             allow_repurchase, avs_for_blockers)
        strategies.append(strategy)
        rationales.append(why)
        targets.append(target)

    out = df.copy()
    out["strategy"] = strategies
    out["strategy_rationale"] = rationales
    out["target_service"] = targets
    return out


_COTS_HINTS = ("Print", "FileShare", "Backup", "Monitoring", "Identity", "Marketing", "CustomerCare")


def _dispose_one(r: pd.Series, appetite: float, retire_zombies: bool,
                 allow_repurchase: bool, avs_for_blockers: bool) -> tuple[str, str, str]:
    env = str(r.get("environment", ""))
    tier = str(r.get("tier", ""))
    db = str(r.get("db_engine", "None"))
    crit = str(r.get("criticality", ""))
    readiness = str(r.get("readiness", CONDITIONAL))

    # 1. Retire -- no consumers.
    if retire_zombies and bool(r.get("zombie_candidate", False)):
        return ("Retire",
                f"Powered on but effectively idle ({float(r.get('cpu_avg_pct') or 0):.1f}% mean CPU, "
                f"{float(r.get('net_mbps') or 0):.2f} Mbps network). Validate with the application "
                "owner, then decommission -- this is the cheapest migration there is.",
                "Decommission")
    if not bool(r.get("powered_on", True)) and int(r.get("days_since_boot", 0)) == 0:
        return ("Retire",
                "Powered off in vCenter. Confirm the last known use and retire rather than pay to "
                "migrate a dormant workload.",
                "Decommission")

    # 2. Retain / Relocate -- something makes IaaS the wrong destination.
    if readiness == NOT_READY:
        blockers = r.get("blockers") or []
        blocker_text = blockers[0] if blockers else "an unresolved technical blocker"
        if avs_for_blockers:
            return ("Relocate",
                    f"Blocked from native Azure IaaS: {blocker_text} Relocating the VM as-is into "
                    "Azure VMware Solution preserves the vSphere construct (shared disks, "
                    "encryption, FT) and exits the data centre without an application change. "
                    "Treat AVS as a staging platform with a dated exit plan, not an endpoint.",
                    "Azure VMware Solution")
        return ("Retain",
                f"Blocked from Azure IaaS: {blocker_text} Keep on-premises until the blocker is "
                "remediated, then re-assess.",
                "On-premises (remediate first)")

    if bool(r.get("has_vgpu", False)):
        return ("Rehost",
                "GPU-attached workload. Rehost onto an Azure NV/NC-series size -- confirm quota and "
                "regional availability early, as GPU capacity is the most common wave blocker.",
                "Azure VM (NV/NC-series)")

    # 3. Repurchase -- commodity function better bought than run.
    app = str(r.get("app_name", ""))
    if allow_repurchase and appetite >= 1.0 and any(h in app for h in _COTS_HINTS) and tier != "Database":
        svc = {"FileShare": "Azure Files / SharePoint Online",
               "Print": "Universal Print",
               "Backup": "Azure Backup",
               "Monitoring": "Azure Monitor",
               "Identity": "Microsoft Entra ID"}
        pick = next((v for k, v in svc.items() if k in app), "SaaS equivalent")
        return ("Repurchase",
                f"'{app}' delivers a commodity capability that Microsoft already sells as a "
                f"service. Moving to {pick} removes the VM, its OS licence, its patching and its "
                "backup line item altogether.",
                pick)

    # 4. Replatform -- managed service with little or no code change.
    if db == "Microsoft SQL Server" and appetite >= 1.0:
        return ("Replatform",
                "SQL Server workload. Azure SQL Managed Instance gives near-100% engine surface "
                "compatibility, so this usually moves with no application code change while "
                "removing OS patching, backup and HA configuration. Validate with Data Migration "
                "Assistant; fall back to SQL Server on an Azure VM if it flags blockers.",
                "Azure SQL Managed Instance")
    if db in ("PostgreSQL", "MySQL") and appetite >= 1.0:
        engine = "Azure Database for PostgreSQL Flexible Server" if db == "PostgreSQL" \
            else "Azure Database for MySQL Flexible Server"
        return ("Replatform",
                f"{db} is a direct fit for {engine}. Migrate with the Azure Database Migration "
                "Service using online replication to keep cutover downtime to minutes.",
                engine)
    if db == "Oracle Database":
        return ("Rehost",
                "Oracle Database. Licensing terms make Oracle on an Azure VM (or Oracle Database@Azure "
                "for larger estates) the pragmatic move. A refactor to PostgreSQL is feasible but is "
                "a separate, application-led programme -- do not couple it to the data centre exit.",
                "Oracle on Azure VM / Oracle Database@Azure")

    if tier == "Web" and appetite >= 2.0 and not r.get("is_prod", True):
        return ("Replatform",
                "Stateless web tier in a non-production environment -- the low-risk place to prove "
                "Azure App Service. Containerise or publish directly and retire the guest OS.",
                "Azure App Service")
    if tier == "Web" and appetite >= 2.0:
        return ("Replatform",
                "Stateless web tier. Azure App Service removes OS management and gives elastic "
                "scale-out; migrate after the non-production instances have proven the pattern.",
                "Azure App Service")
    if tier == "Middleware" and appetite >= 2.0:
        return ("Refactor",
                "Middleware component with a clean service boundary. Containerising onto AKS is "
                "where the durable operating-cost reduction is, but it needs application-team "
                "capacity -- schedule it after the data centre exit, not during it.",
                "Azure Kubernetes Service")

    # 5. Rehost -- the default for a time-boxed data centre exit.
    detail = []
    if str(r.get("azure_os_support")) != "supported":
        detail.append("the guest OS needs an upgrade path scheduled post-migration")
    if crit.startswith("Tier 0"):
        detail.append("Tier 0 criticality means a rehearsed cutover with a tested rollback")
    if r.get("condition_count", 0):
        detail.append(f"{int(r['condition_count'])} readiness condition(s) to clear first")
    suffix = (" Note: " + "; ".join(detail) + ".") if detail else ""
    return ("Rehost",
            "Standard lift-and-shift to Azure IaaS. Lowest risk and fastest route out of the data "
            f"centre; right-sizing captures the cost benefit without touching the application.{suffix}",
            "Azure VM (IaaS)")


def disposition_summary(df: pd.DataFrame) -> pd.DataFrame:
    g = (df.groupby("strategy")
           .agg(vms=("vm_name", "count"),
                vcpu=("vcpu", "sum"),
                ram_gib=("ram_gib", "sum"),
                storage_tib=("provisioned_gib", lambda s: s.sum() / 1024))
           .reindex(STRATEGIES).dropna(how="all").reset_index())
    g["share_pct"] = g["vms"] / g["vms"].sum() * 100
    return g


def readiness_summary(df: pd.DataFrame) -> pd.DataFrame:
    order = [READY, CONDITIONAL, NOT_READY, UNKNOWN]
    g = (df["readiness"].value_counts().reindex(order).dropna()
         .rename_axis("readiness").reset_index(name="vms"))
    g["share_pct"] = g["vms"] / g["vms"].sum() * 100
    return g


def top_blockers(df: pd.DataFrame, n: int = 12) -> pd.DataFrame:
    """Most frequent blockers and conditions across the estate, for the remediation backlog."""
    rows: list[tuple[str, str]] = []
    for _, r in df.iterrows():
        for b in (r.get("blockers") or []):
            rows.append(("Blocker", b))
        for c in (r.get("conditions") or []):
            rows.append(("Condition", c))
    if not rows:
        return pd.DataFrame(columns=["severity", "finding", "vms"])
    d = pd.DataFrame(rows, columns=["severity", "finding"])
    # Collapse to the leading sentence so per-VM numbers do not fragment the count.
    # regex=False matters: pandas treats a multi-character pattern as a regex by
    # default, and ". " as a regex matches any character followed by a space.
    d["finding"] = d["finding"].str.split(". ", regex=False).str[0] + "."
    out = (d.groupby(["severity", "finding"]).size().reset_index(name="vms")
             .sort_values(["severity", "vms"], ascending=[True, False]))
    return out.head(n)
