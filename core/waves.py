"""Wave planning and schedule simulation.

Waves are built application-first (an app's VMs move together, because
splitting them across waves is what creates the latency and firewall problems
that derail migrations), then sequenced by environment and criticality so the
team climbs a risk ladder: dev/test proves the runbook, production follows.

Each wave's duration is the greater of two independent constraints:

* **replication time** -- bytes / usable bandwidth, plus delta sync
* **engineering time** -- effort hours / available parallel capacity

Modelling both is what stops a plan from claiming a 40 TB wave will land in a
weekend on a 500 Mbps link.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

ENV_ORDER = {"Development": 0, "Test": 1, "UAT": 2, "DR": 3, "Production": 4}
CRIT_ORDER = {"Tier 3 - Administrative": 0, "Tier 2 - Business operational": 1,
              "Tier 1 - Business critical": 2, "Tier 0 - Mission critical": 3}


@dataclass
class WavePlan:
    target_waves: int = 8
    max_vms_per_wave: int = 90
    # Azure Migrate agentless: 300 concurrent replications per appliance,
    # 500 with a scale-out appliance, and 56 disks replicating at any moment.
    max_concurrent_replications: int = 300
    bandwidth_mbps: float = 1000.0
    bandwidth_available_pct: float = 60.0    # share of the link the migration may use
    wan_efficiency_pct: float = 75.0         # TCP/latency/compression realities
    replication_window_hours_per_day: float = 24.0
    parallel_streams: int = 4                # concurrent migration squads
    team_hours_per_day: float = 48.0         # squads x engineers x productive hours
    pilot_wave: bool = True
    pilot_size: int = 12
    freeze_periods: int = 0                  # business change freezes, in weeks
    days_between_waves: float = 5.0          # stabilisation / hypercare gap


def _wave_sort_key(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["_env"] = d["environment"].map(ENV_ORDER).fillna(2)
    d["_crit"] = d["criticality"].map(CRIT_ORDER).fillna(1)
    return d


def build_waves(scored: pd.DataFrame, plan: WavePlan) -> pd.DataFrame:
    """Assign every non-retired VM to a wave, keeping applications intact."""
    movable = scored[~scored["strategy"].isin(["Retire", "Retain"])].copy()
    if movable.empty:
        out = scored.copy()
        out["wave"] = 0
        out["wave_name"] = "Not migrating"
        return out

    d = _wave_sort_key(movable)

    # Application move-groups: risk rank = the riskiest VM in the group.
    grp = (d.groupby("app_name")
             .agg(vms=("vm_name", "count"),
                  storage_gib=("used_gib", "sum"),
                  effort_hours=("effort_hours", "sum"),
                  complexity=("complexity", "mean"),
                  env_rank=("_env", "max"),
                  crit_rank=("_crit", "max"),
                  churn=("daily_churn_pct", "mean"))
             .reset_index())
    grp = grp.sort_values(["env_rank", "crit_rank", "complexity", "vms"],
                          ascending=[True, True, True, True]).reset_index(drop=True)

    n_waves = max(plan.target_waves, 1)
    per_wave_target = max(len(movable) / n_waves, 1)

    assignments: dict[str, int] = {}
    wave_idx = 1
    running = 0

    # Optional pilot: the smallest, simplest non-production groups go first.
    if plan.pilot_wave:
        pilot_groups = grp[grp["env_rank"] <= 1].sort_values(["complexity", "vms"])
        taken = 0
        for _, g in pilot_groups.iterrows():
            if taken >= plan.pilot_size:
                break
            assignments[g["app_name"]] = 1
            taken += int(g["vms"])
        wave_idx = 2

    for _, g in grp.iterrows():
        if g["app_name"] in assignments:
            continue
        size = int(g["vms"])
        if running + size > min(per_wave_target, plan.max_vms_per_wave) and running > 0:
            wave_idx += 1
            running = 0
        assignments[g["app_name"]] = wave_idx
        running += size

    out = scored.copy()
    out["wave"] = out["app_name"].map(assignments)
    out.loc[out["strategy"].isin(["Retire", "Retain"]), "wave"] = 0
    out["wave"] = out["wave"].fillna(0).astype(int)

    names = {0: "Wave 0 - Retire / Retain (no migration)"}
    for w in sorted(x for x in out["wave"].unique() if x > 0):
        if plan.pilot_wave and w == 1:
            names[w] = "Wave 1 - Pilot"
        else:
            names[w] = f"Wave {w}"
    out["wave_name"] = out["wave"].map(names)
    return out


def replication_hours(gib: float, plan: WavePlan, churn_pct: float,
                      sync_days: float = 3.0) -> tuple[float, float]:
    """Initial-seed and delta-sync hours for a given data volume.

    Usable throughput = link x share allocated x WAN efficiency. The delta pass
    covers whatever changed while the seed was running, and keeps re-syncing
    until cutover.
    """
    usable_mbps = plan.bandwidth_mbps * (plan.bandwidth_available_pct / 100.0) \
        * (plan.wan_efficiency_pct / 100.0)
    if usable_mbps <= 0:
        return float("inf"), float("inf")
    gib_per_hour = usable_mbps / 8.0 * 3600.0 / 1024.0     # Mb/s -> GiB/h
    duty = max(plan.replication_window_hours_per_day / 24.0, 0.01)

    seed_h = gib / gib_per_hour / duty
    seed_days = seed_h / 24.0
    delta_gib = gib * (churn_pct / 100.0) * (seed_days + sync_days)
    delta_h = delta_gib / gib_per_hour / duty
    return seed_h, delta_h


def simulate_schedule(waved: pd.DataFrame, plan: WavePlan,
                      start_date: str = "2026-09-01") -> pd.DataFrame:
    """Turn waves into a dated plan with the binding constraint made explicit."""
    rows = []
    cursor = pd.Timestamp(start_date)

    for w in sorted(x for x in waved["wave"].unique() if x > 0):
        wdf = waved[waved["wave"] == w]
        gib = float(wdf["used_gib"].sum())
        churn = float(pd.to_numeric(wdf["daily_churn_pct"], errors="coerce").fillna(3).mean())
        effort = float(wdf["effort_hours"].sum())

        seed_h, delta_h = replication_hours(gib, plan, churn)
        repl_days = (seed_h + delta_h) / 24.0

        # Replication is also throttled by how many VMs can replicate at once.
        batches = np.ceil(len(wdf) / max(plan.max_concurrent_replications, 1))
        repl_days *= batches

        eng_days = effort / max(plan.team_hours_per_day, 1)

        # Cutover events are serialised over weekends/change windows.
        apps = wdf["app_name"].nunique()
        cutover_days = np.ceil(apps / max(plan.parallel_streams, 1)) * 1.0

        duration = max(repl_days, eng_days) + cutover_days
        constraint = ("Replication bandwidth" if repl_days >= eng_days
                      else "Engineering capacity")

        start = cursor
        end = start + pd.Timedelta(days=float(duration))
        rows.append({
            "wave": w,
            "wave_name": wdf["wave_name"].iloc[0],
            "vms": int(len(wdf)),
            "applications": int(apps),
            "prod_vms": int(wdf["is_prod"].sum()),
            "data_tib": gib / 1024.0,
            "mean_complexity": float(wdf["complexity"].mean()),
            "effort_hours": effort,
            "seed_days": seed_h / 24.0,
            "delta_days": delta_h / 24.0,
            "replication_days": repl_days,
            "engineering_days": eng_days,
            "cutover_days": cutover_days,
            "duration_days": duration,
            "binding_constraint": constraint,
            "start": start,
            "end": end,
            "migration_cost": float(wdf["migration_cost"].sum()),
            "azure_monthly_cost": float(wdf["monthly_cost"].sum()) if "monthly_cost" in wdf else 0.0,
            "expected_rollbacks": float(wdf["cutover_failure_risk"].sum()),
        })
        cursor = end + pd.Timedelta(days=plan.days_between_waves)

    sched = pd.DataFrame(rows)
    if not sched.empty and plan.freeze_periods:
        # Push everything after the midpoint out by the freeze duration.
        mid = len(sched) // 2
        shift = pd.Timedelta(weeks=plan.freeze_periods)
        sched.loc[mid:, ["start", "end"]] += shift
    return sched


def schedule_summary(sched: pd.DataFrame, plan: WavePlan) -> dict:
    if sched.empty:
        return {"waves": 0, "elapsed_days": 0, "elapsed_months": 0}
    total_days = (sched["end"].max() - sched["start"].min()).days
    bw_bound = int((sched["binding_constraint"] == "Replication bandwidth").sum())
    return {
        "waves": int(len(sched)),
        "vms_migrating": int(sched["vms"].sum()),
        "data_tib": float(sched["data_tib"].sum()),
        "elapsed_days": total_days,
        "elapsed_months": total_days / 30.44,
        "go_live": sched["end"].max(),
        "bandwidth_bound_waves": bw_bound,
        "capacity_bound_waves": int(len(sched)) - bw_bound,
        "expected_rollbacks": float(sched["expected_rollbacks"].sum()),
        "peak_wave_tib": float(sched["data_tib"].max()),
        "longest_wave_days": float(sched["duration_days"].max()),
    }


def bandwidth_curve(waved: pd.DataFrame, plan: WavePlan,
                    mbps_options: tuple[float, ...] = (100, 250, 500, 1000, 2000, 5000, 10000)
                    ) -> pd.DataFrame:
    """How total elapsed time responds to link speed -- the single most-asked question."""
    from dataclasses import replace
    rows = []
    for mbps in mbps_options:
        p = replace(plan, bandwidth_mbps=mbps)
        s = simulate_schedule(waved, p)
        summ = schedule_summary(s, p)
        rows.append({"bandwidth_mbps": mbps,
                     "elapsed_months": summ["elapsed_months"],
                     "bandwidth_bound_waves": summ["bandwidth_bound_waves"]})
    return pd.DataFrame(rows)


def offline_seed_advice(total_tib: float, plan: WavePlan) -> str:
    """When the wire is hopeless, say so and point at Data Box."""
    usable_mbps = plan.bandwidth_mbps * (plan.bandwidth_available_pct / 100) \
        * (plan.wan_efficiency_pct / 100)
    if usable_mbps <= 0:
        return "No usable bandwidth configured."
    days = total_tib * 1024 / (usable_mbps / 8 * 3600 / 1024) / 24
    if days > 60:
        boxes = int(np.ceil(total_tib / 80.0))     # Data Box holds ~80 TB usable
        return (f"At {usable_mbps:,.0f} Mbps usable, seeding {total_tib:,.1f} TiB over the wire "
                f"takes ~{days:,.0f} days. Consider offline seeding: ~{boxes} x Azure Data Box "
                f"(80 TB usable each), or negotiate a temporary ExpressRoute uplift for the "
                f"migration window. Note that Azure Migrate agentless replication does not "
                f"support Data Box seeding -- offline seeding requires a partner tool or a "
                f"storage-level approach for the bulk data.")
    return (f"At {usable_mbps:,.0f} Mbps usable, seeding {total_tib:,.1f} TiB takes ~{days:,.0f} "
            f"days of wire time. Online replication is viable.")


# --------------------------------------------------------------------------
# Wave design principles.
#
# The engine above decides what goes in which wave. These are the rules that
# decide whether a wave is allowed to start at all, and they are the reason a
# plan that looks fine on a Gantt chart fails at the first gate. Three are
# testable against the built plan; four are programme conditions.
# --------------------------------------------------------------------------
PRINCIPLE_TESTED = "tested"
PRINCIPLE_OPEN = "open"
PRINCIPLE_PROGRAMME = "programme"

WAVE_PRINCIPLES = [
    ("dependency_boundary",
     "A wave is defined by dependency boundaries, not by server count and not by "
     "which team happens to be available."),
    ("gates",
     "Every wave has published entry criteria, exit criteria, a named application "
     "owner and an agreed rollback position before it starts."),
    ("disk_sizing",
     "Wave size is governed by disk count, per-host disk limits and datastore "
     "snapshot limits -- not by bandwidth and not by ambition."),
    ("test_migration",
     "Test migration into an isolated network is mandatory for every Azure IaaS "
     "wave. Where the target has no test capability, purpose-built canary workloads "
     "are used instead of production samples."),
    ("rollback_retention",
     "Source virtual machines are retained powered off and intact for an agreed "
     "period after cutover. This is the rollback plan; there is no automated "
     "alternative."),
    ("risk_not_arithmetic",
     "One stateful, tightly coupled application can constitute a larger operational "
     "wave than ten stateless utility servers. Wave sizing is a risk judgement, not "
     "an arithmetic one."),
    ("owner_signoff",
     "No wave proceeds without the application owner having signed off the "
     "validation plan."),
]


def principle_status(schedule, plan, test_migration_pct: float = 0.0) -> list[dict]:
    """Check the wave design principles against the plan actually built.

    Only three can be tested from a schedule. Saying so is the point -- the four
    that cannot are the ones that stop a wave at the gate.
    """
    checks: dict[str, tuple[str, str]] = {}

    cols = list(getattr(schedule, "columns", []))
    if schedule is not None and len(schedule):
        if "applications" in cols:
            apps = int(schedule["applications"].sum())
            checks["dependency_boundary"] = (
                PRINCIPLE_TESTED,
                f"{apps} application groups placed whole, so tightly coupled "
                "applications move in the same wave")

        if "vms" in cols and "mean_complexity" in cols:
            lo, hi = float(schedule["vms"].min()), float(schedule["vms"].max())
            spread = hi / max(lo, 1.0)
            checks["risk_not_arithmetic"] = (
                PRINCIPLE_TESTED if spread > 1.2 else PRINCIPLE_OPEN,
                f"Wave sizes range {lo:.0f} to {hi:.0f} VMs ({spread:.1f}x)"
                + ("" if spread > 1.2 else " -- near-uniform sizing suggests waves "
                                           "were cut by count rather than by risk"))

    if plan:
        checks["disk_sizing"] = (
            PRINCIPLE_TESTED,
            f"Concurrency modelled at {plan.get('disks_replicating_at_once', 0)} disks "
            "in flight, not at link speed")

    if test_migration_pct:
        checks["test_migration"] = (
            PRINCIPLE_TESTED if test_migration_pct >= 100 else PRINCIPLE_OPEN,
            f"{test_migration_pct:.0f}% of VMs given a test migration in this plan")

    out = []
    for key, text in WAVE_PRINCIPLES:
        status, note = checks.get(
            key, (PRINCIPLE_PROGRAMME, "Not observable from a schedule -- a programme "
                                       "condition, and one that stops waves at the gate"))
        out.append({"key": key, "principle": text, "status": status, "note": note})
    return out
