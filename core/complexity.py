"""Complexity, effort and duration model.

Every VM gets a complexity score built from weighted, individually-visible
factors. That score drives:

* migration **effort** in person-hours (discovery, remediation, build, test, cutover)
* migration **cost** (labour + tooling + dual-run)
* migration **duration** contribution and the risk of a failed cutover

The weights are exposed in the UI so a client can argue with them -- which is
the point of a simulator, as opposed to a spreadsheet nobody trusts.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict

import numpy as np
import pandas as pd

# Each factor scores 0-10 before weighting.
DEFAULT_WEIGHTS: dict[str, float] = {
    "size": 0.8,               # vCPU / RAM / storage footprint
    "storage_volume": 1.0,     # TB to move -- drives replication time
    "data_churn": 1.1,         # delta-sync burden and cutover window risk
    "os_currency": 1.3,        # EOL guest OS -> remediation project
    "database": 1.6,           # DB engine migration and consistency proof
    "dependencies": 1.7,       # number of coupled VMs in the move group
    "criticality": 1.5,        # blast radius and change-approval overhead
    "technical_blockers": 2.0, # RDM, shared disk, encryption, FT, vGPU
    "network": 1.2,            # NIC count, hard-coded IPs, firewall rules
    "licensing": 0.9,          # MAC-bound or per-socket licences
    "downtime_tolerance": 1.4, # how small the permitted cutover window is
    "strategy": 1.5,           # rehost is cheap; refactor is not
    "compliance": 1.0,         # data residency, regulated workload
}

# Band edges are calibrated to the score the model actually produces, not to a
# naive quartering of 0-100. Many factors score zero for most VMs (no database,
# no blockers, no MAC-bound licence), so the weighted index for a typical
# enterprise estate lands in the high teens to mid forties. The edges are on
# EffortModel so they can be re-tuned against a client's own data.
BAND_EDGES = [0, 20, 32, 45, 100]
BAND_NAMES = ["Simple", "Moderate", "Complex", "Highly complex"]

# Base effort per VM in person-hours at complexity 0, and the slope per point.
STRATEGY_EFFORT = {
    "Retire":     {"base": 1.5,  "slope": 0.02},
    "Retain":     {"base": 1.0,  "slope": 0.01},
    "Relocate":   {"base": 3.0,  "slope": 0.06},
    "Rehost":     {"base": 6.0,  "slope": 0.22},
    "Replatform": {"base": 26.0, "slope": 0.70},
    "Repurchase": {"base": 20.0, "slope": 0.45},
    "Refactor":   {"base": 90.0, "slope": 2.10},
}


@dataclass
class EffortModel:
    weights: dict = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    blended_rate_per_hour: float = 78.0     # blended migration-engineer day rate / 8
    productive_hours_per_day: float = 6.0
    team_size_fte: float = 12.0
    parallel_migration_streams: int = 4
    tooling_cost_per_vm: float = 0.0        # non-zero for licensed third-party tools
    contingency_pct: float = 18.0
    dual_run_months: float = 1.5            # months paying for both estates per wave
    test_cycles: int = 2
    # Programme-level roles that run for the whole engagement, in FTE.
    programme_overhead_fte: float = 4.0
    band_edges: tuple = tuple(BAND_EDGES)


# --------------------------------------------------------------------------
# Factor scoring (0-10 each)
# --------------------------------------------------------------------------
def _score_size(r: pd.Series) -> float:
    pts = (min(float(r["vcpu"]) / 16.0, 1.0) * 4
           + min(float(r["ram_gib"]) / 128.0, 1.0) * 3
           + min(float(r["provisioned_gib"]) / 2000.0, 1.0) * 3)
    return float(np.clip(pts, 0, 10))


def _score_storage(r: pd.Series) -> float:
    tb = float(r["provisioned_gib"]) / 1024.0
    return float(np.clip(np.log1p(tb) / np.log1p(20) * 10, 0, 10))


def _score_churn(r: pd.Series) -> float:
    churn = float(r.get("daily_churn_pct") or 3.0)
    return float(np.clip(churn / 15.0 * 10, 0, 10))


def _score_os(r: pd.Series) -> float:
    support = str(r.get("azure_os_support", "supported"))
    return {"supported": 0.0, "endorsed-eol": 6.0, "esu-required": 7.0, "unsupported": 10.0}.get(support, 3.0)


def _score_db(r: pd.Series) -> float:
    return {"None": 0.0, "MySQL": 5.0, "PostgreSQL": 5.0, "MongoDB": 6.0,
            "Microsoft SQL Server": 7.0, "Oracle Database": 10.0}.get(str(r.get("db_engine")), 0.0)


def _score_deps(r: pd.Series, group_sizes: dict) -> float:
    n = group_sizes.get(r.get("app_name"), 1)
    return float(np.clip(np.log1p(n - 1) / np.log1p(24) * 10, 0, 10))


def _score_crit(r: pd.Series) -> float:
    c = str(r.get("criticality", ""))
    if c.startswith("Tier 0"):
        return 10.0
    if c.startswith("Tier 1"):
        return 7.0
    if c.startswith("Tier 2"):
        return 4.0
    return 1.5


def _score_blockers(r: pd.Series) -> float:
    pts = 0.0
    if r.get("has_shared_disk"):
        pts += 4.0
    if r.get("vm_encrypted"):
        pts += 3.0
    if r.get("has_rdm"):
        pts += 2.5
    if r.get("has_independent_disk"):
        pts += 1.5
    if r.get("fault_tolerance"):
        pts += 2.0
    if r.get("has_vgpu"):
        pts += 2.5
    if r.get("has_usb_or_serial"):
        pts += 2.0
    if str(r.get("vmware_tools")) in ("toolsNotInstalled", "toolsNotRunning"):
        pts += 1.5
    if r.get("has_snapshot") and int(r.get("snapshot_age_days") or 0) > 30:
        pts += 1.0
    return float(np.clip(pts, 0, 10))


def _score_network(r: pd.Series) -> float:
    nics = int(r.get("nic_count", 1))
    pts = (nics - 1) * 2.2
    if str(r.get("tier")) in ("Web", "Infrastructure"):
        pts += 1.5     # more inbound firewall/load-balancer rules to reproduce
    if float(r.get("net_mbps") or 0) > 100:
        pts += 2.0
    return float(np.clip(pts, 0, 10))


def _score_licensing(r: pd.Series) -> float:
    pts = 0.0
    if r.get("licence_mac_bound"):
        pts += 6.0
    if str(r.get("db_engine")) == "Oracle Database":
        pts += 4.0
    if str(r.get("db_engine")) == "Microsoft SQL Server":
        pts += 2.0
    return float(np.clip(pts, 0, 10))


def _score_downtime(r: pd.Series) -> float:
    c = str(r.get("criticality", ""))
    env = str(r.get("environment", ""))
    if env in ("Development", "Test"):
        return 1.0
    if c.startswith("Tier 0"):
        return 10.0
    if c.startswith("Tier 1"):
        return 7.5
    return 4.0


def _score_strategy(r: pd.Series) -> float:
    return {"Retire": 0.0, "Retain": 0.5, "Relocate": 2.0, "Rehost": 3.0,
            "Repurchase": 6.0, "Replatform": 7.5, "Refactor": 10.0}.get(str(r.get("strategy")), 3.0)


def _score_compliance(r: pd.Series, regulated_apps: set[str]) -> float:
    pts = 0.0
    if r.get("app_name") in regulated_apps:
        pts += 6.0
    if str(r.get("tier")) == "Database":
        pts += 2.0
    if str(r.get("criticality", "")).startswith("Tier 0"):
        pts += 2.0
    return float(np.clip(pts, 0, 10))


FACTOR_LABELS = {
    "size": "Compute footprint",
    "storage_volume": "Storage volume to move",
    "data_churn": "Daily data change rate",
    "os_currency": "Guest OS currency",
    "database": "Database engine",
    "dependencies": "Application coupling",
    "criticality": "Business criticality",
    "technical_blockers": "Technical blockers",
    "network": "Network complexity",
    "licensing": "Licence portability",
    "downtime_tolerance": "Downtime tolerance",
    "strategy": "Migration strategy",
    "compliance": "Compliance / data residency",
}


def score_estate(df: pd.DataFrame, model: EffortModel,
                 regulated_apps: set[str] | None = None) -> pd.DataFrame:
    """Compute per-VM factor scores, a 0-100 complexity index, effort and cost."""
    regulated_apps = regulated_apps or set()
    group_sizes = df["app_name"].value_counts().to_dict()

    scorers = {
        "size": _score_size,
        "storage_volume": _score_storage,
        "data_churn": _score_churn,
        "os_currency": _score_os,
        "database": _score_db,
        "dependencies": lambda r: _score_deps(r, group_sizes),
        "criticality": _score_crit,
        "technical_blockers": _score_blockers,
        "network": _score_network,
        "licensing": _score_licensing,
        "downtime_tolerance": _score_downtime,
        "strategy": _score_strategy,
        "compliance": lambda r: _score_compliance(r, regulated_apps),
    }

    out = df.copy()
    weight_total = sum(model.weights.get(k, 0) for k in scorers)
    weighted = np.zeros(len(df))
    for key, fn in scorers.items():
        col = df.apply(fn, axis=1).astype(float)
        out[f"cx_{key}"] = col
        weighted += col.values * model.weights.get(key, 0.0)

    # Normalise to 0-100 (max raw score is 10 x total weight).
    out["complexity"] = np.round(weighted / (10.0 * weight_total) * 100, 1)
    out["complexity_band"] = pd.cut(out["complexity"], bins=list(model.band_edges),
                                    labels=BAND_NAMES, include_lowest=True).astype(str)

    # ---- effort ---------------------------------------------------------
    base = out["strategy"].map(lambda s: STRATEGY_EFFORT.get(s, STRATEGY_EFFORT["Rehost"])["base"])
    slope = out["strategy"].map(lambda s: STRATEGY_EFFORT.get(s, STRATEGY_EFFORT["Rehost"])["slope"])
    hours = base + slope * out["complexity"]
    # Extra test cycles cost roughly 18% of build effort each beyond the first.
    hours = hours * (1 + 0.18 * max(model.test_cycles - 1, 0))
    out["effort_hours"] = np.round(hours, 1)
    out["effort_days"] = np.round(out["effort_hours"] / model.productive_hours_per_day, 2)
    out["labour_cost"] = np.round(out["effort_hours"] * model.blended_rate_per_hour, 0)
    out["tooling_cost"] = model.tooling_cost_per_vm
    out["migration_cost"] = np.round(
        (out["labour_cost"] + out["tooling_cost"]) * (1 + model.contingency_pct / 100.0), 0)

    # ---- cutover risk ----------------------------------------------------
    # Probability a first cutover attempt fails and has to be rolled back.
    # Calibrated so a typical rehost estate lands at a 3-5% rollback rate, which
    # is what well-run programmes actually report; complex and blocked VMs then
    # rise well above that.
    risk = (0.008
            + out["complexity"] / 100.0 * 0.060
            + out["cx_technical_blockers"] / 10.0 * 0.060
            + out["cx_data_churn"] / 10.0 * 0.030
            + (out["cx_downtime_tolerance"] / 10.0) * 0.025)
    out["cutover_failure_risk"] = np.round(np.clip(risk, 0.004, 0.55), 3)
    return out


def effort_summary(scored: pd.DataFrame, model: EffortModel) -> dict:
    total_hours = float(scored["effort_hours"].sum())
    capacity_hours_per_month = (model.team_size_fte * model.productive_hours_per_day * 21.0)
    return {
        "total_effort_hours": total_hours,
        "total_effort_person_days": total_hours / model.productive_hours_per_day,
        "total_effort_fte_months": total_hours / max(capacity_hours_per_month / model.team_size_fte, 1),
        "labour_cost": float(scored["labour_cost"].sum()),
        "migration_cost": float(scored["migration_cost"].sum()),
        "mean_complexity": float(scored["complexity"].mean()),
        "elapsed_months_at_capacity": total_hours / max(capacity_hours_per_month, 1),
        "expected_failed_cutovers": float(scored["cutover_failure_risk"].sum()),
        "cost_per_vm": float(scored["migration_cost"].mean()),
    }


def complexity_distribution(scored: pd.DataFrame) -> pd.DataFrame:
    g = (scored.groupby("complexity_band")
         .agg(vms=("vm_name", "count"),
              effort_hours=("effort_hours", "sum"),
              migration_cost=("migration_cost", "sum"),
              mean_complexity=("complexity", "mean"))
         .reindex(BAND_NAMES).dropna(how="all").reset_index())
    g["share_pct"] = g["vms"] / g["vms"].sum() * 100
    return g


def factor_contribution(scored: pd.DataFrame, model: EffortModel) -> pd.DataFrame:
    """Which factors are actually driving portfolio complexity."""
    rows = []
    total = 0.0
    for key, label in FACTOR_LABELS.items():
        col = f"cx_{key}"
        if col not in scored.columns:
            continue
        contrib = float(scored[col].mean()) * model.weights.get(key, 0.0)
        total += contrib
        rows.append({"factor": label, "mean_score": float(scored[col].mean()),
                     "weight": model.weights.get(key, 0.0), "contribution": contrib})
    df = pd.DataFrame(rows)
    df["contribution_pct"] = df["contribution"] / total * 100 if total else 0
    return df.sort_values("contribution", ascending=False)
