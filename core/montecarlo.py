"""Monte Carlo simulation of programme cost, duration and complexity.

A single-point estimate is the least useful thing you can hand a steering
committee. This module runs the plan thousands of times with the uncertain
inputs sampled from PERT (three-point) distributions, and reports the
percentile bands plus which uncertainty actually drives the spread.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class Uncertainty:
    """Three-point estimate. ``mode`` is the planning assumption."""
    low: float
    mode: float
    high: float

    def sample(self, rng: np.random.Generator, n: int, lam: float = 4.0) -> np.ndarray:
        """PERT (beta-shaped) sample -- concentrates around the mode, unlike triangular."""
        lo, mo, hi = self.low, self.mode, self.high
        if hi <= lo:
            return np.full(n, mo)
        mo = min(max(mo, lo + 1e-9), hi - 1e-9)
        alpha = 1 + lam * (mo - lo) / (hi - lo)
        beta = 1 + lam * (hi - mo) / (hi - lo)
        return lo + rng.beta(alpha, beta, n) * (hi - lo)


@dataclass
class SimulationInputs:
    """Every uncertain driver, expressed as a multiplier on the deterministic plan
    unless stated otherwise."""
    effort_multiplier: Uncertainty = field(default_factory=lambda: Uncertainty(0.85, 1.00, 1.75))
    rate_multiplier: Uncertainty = field(default_factory=lambda: Uncertainty(0.92, 1.00, 1.25))
    discovery_gap_pct: Uncertainty = field(default_factory=lambda: Uncertainty(2.0, 8.0, 22.0))
    bandwidth_realised_pct: Uncertainty = field(default_factory=lambda: Uncertainty(45.0, 75.0, 92.0))
    churn_multiplier: Uncertainty = field(default_factory=lambda: Uncertainty(0.7, 1.0, 2.2))
    azure_run_multiplier: Uncertainty = field(default_factory=lambda: Uncertainty(0.88, 1.00, 1.30))
    rollback_rate_multiplier: Uncertainty = field(default_factory=lambda: Uncertainty(0.5, 1.0, 2.5))
    team_availability_pct: Uncertainty = field(default_factory=lambda: Uncertainty(70.0, 88.0, 100.0))
    freeze_weeks: Uncertainty = field(default_factory=lambda: Uncertainty(0.0, 2.0, 8.0))
    dual_run_months: Uncertainty = field(default_factory=lambda: Uncertainty(1.0, 2.0, 5.0))
    rework_cost_per_rollback: Uncertainty = field(default_factory=lambda: Uncertainty(3000, 9000, 28000))
    iterations: int = 10000
    seed: int = 7


DRIVER_LABELS = {
    "effort_multiplier": "Engineering effort vs estimate",
    "rate_multiplier": "Blended day rate",
    "discovery_gap_pct": "Undiscovered / late-found workloads (%)",
    "bandwidth_realised_pct": "Realised WAN throughput (%)",
    "churn_multiplier": "Data change rate vs assumption",
    "azure_run_multiplier": "Azure run-rate vs estimate",
    "rollback_rate_multiplier": "Cutover failure rate vs estimate",
    "team_availability_pct": "Team availability (%)",
    "freeze_weeks": "Change-freeze weeks",
    "dual_run_months": "Dual-run overlap (months)",
    "rework_cost_per_rollback": "Rework cost per failed cutover",
}


@dataclass
class Deterministic:
    """The single-point plan the simulation perturbs."""
    migration_cost: float
    effort_hours: float
    team_hours_per_day: float
    elapsed_days: float
    replication_days: float
    engineering_days: float
    azure_monthly_cost: float
    onprem_monthly_cost: float
    expected_rollbacks: float
    vm_count: int
    cost_per_vm: float


def run(det: Deterministic, inp: SimulationInputs) -> pd.DataFrame:
    """Run the simulation. Returns one row per iteration."""
    rng = np.random.default_rng(inp.seed)
    n = inp.iterations

    eff_m = inp.effort_multiplier.sample(rng, n)
    rate_m = inp.rate_multiplier.sample(rng, n)
    gap = inp.discovery_gap_pct.sample(rng, n) / 100.0
    bw = inp.bandwidth_realised_pct.sample(rng, n) / 100.0
    churn_m = inp.churn_multiplier.sample(rng, n)
    run_m = inp.azure_run_multiplier.sample(rng, n)
    rb_m = inp.rollback_rate_multiplier.sample(rng, n)
    avail = inp.team_availability_pct.sample(rng, n) / 100.0
    freeze_w = inp.freeze_weeks.sample(rng, n)
    dual = inp.dual_run_months.sample(rng, n)
    rework = inp.rework_cost_per_rollback.sample(rng, n)

    # Late-discovered workloads add both scope and cost at the plan's unit rate.
    extra_vms = det.vm_count * gap
    scope_m = 1.0 + gap

    # ---- duration --------------------------------------------------------
    # Engineering time stretches with effort, scope and (inversely) availability.
    eng_days = det.engineering_days * eff_m * scope_m / np.clip(avail, 0.3, 1.0)
    # Replication stretches when realised throughput or churn disappoint. The
    # baseline plan already assumed a WAN efficiency, so this re-bases it.
    baseline_bw = 0.75
    repl_days = det.replication_days * (baseline_bw / np.clip(bw, 0.15, 1.0)) \
        * (0.75 + 0.25 * churn_m) * scope_m
    # Waves are bandwidth- or capacity-bound, then cutovers add on top.
    cutover_overhead = det.elapsed_days - max(det.replication_days, det.engineering_days)
    cutover_overhead = max(cutover_overhead, 0.0)
    elapsed = np.maximum(eng_days, repl_days) + cutover_overhead + freeze_w * 7.0
    # Failed cutovers add a re-run window each.
    rollbacks = det.expected_rollbacks * rb_m * scope_m
    elapsed = elapsed + rollbacks * 1.5

    # ---- cost ------------------------------------------------------------
    labour = det.migration_cost * eff_m * rate_m * scope_m
    rework_cost = rollbacks * rework
    # Dual-run: paying for both estates while the programme is in flight.
    dual_run_cost = (det.onprem_monthly_cost + det.azure_monthly_cost * run_m) * 0.5 * dual
    one_off = labour + rework_cost + dual_run_cost

    azure_annual = det.azure_monthly_cost * run_m * scope_m * 12.0
    # Programme extends the on-prem tail: you keep paying until the last wave lands.
    onprem_tail = det.onprem_monthly_cost * (elapsed / 30.44) * 0.55

    return pd.DataFrame({
        "elapsed_days": elapsed,
        "elapsed_months": elapsed / 30.44,
        "migration_cost": one_off,
        "labour_cost": labour,
        "rework_cost": rework_cost,
        "dual_run_cost": dual_run_cost,
        "onprem_tail_cost": onprem_tail,
        "azure_annual_cost": azure_annual,
        "azure_monthly_cost": det.azure_monthly_cost * run_m * scope_m,
        "total_programme_cost": one_off + onprem_tail,
        "year1_total": one_off + onprem_tail + azure_annual,
        "extra_vms": extra_vms,
        "rollbacks": rollbacks,
        "effort_multiplier": eff_m,
        "rate_multiplier": rate_m,
        "discovery_gap_pct": gap * 100,
        "bandwidth_realised_pct": bw * 100,
        "churn_multiplier": churn_m,
        "azure_run_multiplier": run_m,
        "rollback_rate_multiplier": rb_m,
        "team_availability_pct": avail * 100,
        "freeze_weeks": freeze_w,
        "dual_run_months": dual,
        "rework_cost_per_rollback": rework,
    })


PCTILES = [10, 50, 80, 90, 95]


def percentiles(sim: pd.DataFrame, cols: tuple[str, ...] = (
        "elapsed_months", "migration_cost", "total_programme_cost",
        "azure_monthly_cost", "year1_total", "rollbacks")) -> pd.DataFrame:
    rows = []
    for c in cols:
        if c not in sim.columns:
            continue
        rec = {"metric": c, "mean": float(sim[c].mean())}
        for p in PCTILES:
            rec[f"P{p}"] = float(np.percentile(sim[c], p))
        rows.append(rec)
    return pd.DataFrame(rows)


def tornado(sim: pd.DataFrame, target: str = "total_programme_cost") -> pd.DataFrame:
    """Rank drivers by their correlation with the outcome -- the sensitivity story."""
    rows = []
    y = sim[target]
    for driver, label in DRIVER_LABELS.items():
        if driver not in sim.columns:
            continue
        x = sim[driver]
        if x.std() == 0:
            continue
        # Spearman: robust to the non-linear way these drivers combine.
        corr = float(pd.Series(x).corr(y, method="spearman"))
        # Swing: outcome at the driver's P10 vs P90.
        lo_mask = x <= np.percentile(x, 20)
        hi_mask = x >= np.percentile(x, 80)
        swing = float(y[hi_mask].mean() - y[lo_mask].mean())
        rows.append({"driver": label, "correlation": corr, "swing": swing,
                     "abs_swing": abs(swing)})
    return pd.DataFrame(rows).sort_values("abs_swing", ascending=False)


def confidence_statement(sim: pd.DataFrame, budget: float | None,
                         deadline_months: float | None) -> list[str]:
    """Plain-English readouts a steering committee can act on."""
    out = []
    p50c = np.percentile(sim["total_programme_cost"], 50)
    p80c = np.percentile(sim["total_programme_cost"], 80)
    p50t = np.percentile(sim["elapsed_months"], 50)
    p80t = np.percentile(sim["elapsed_months"], 80)
    out.append(f"Programme cost: P50 {p50c:,.0f}, P80 {p80c:,.0f}. "
               f"Funding to P80 buys an {(p80c / p50c - 1) * 100:.0f}% contingency over the "
               "median -- that is the number to take to the board, not the P50.")
    out.append(f"Duration: P50 {p50t:.1f} months, P80 {p80t:.1f} months.")
    if budget:
        prob = float((sim["total_programme_cost"] <= budget).mean() * 100)
        out.append(f"Probability of landing within a {budget:,.0f} budget: {prob:.0f}%."
                   + ("" if prob >= 80 else
                      " Below 80% confidence -- either raise the budget, cut scope, or "
                      "attack the top driver in the tornado chart."))
    if deadline_months:
        prob = float((sim["elapsed_months"] <= deadline_months).mean() * 100)
        out.append(f"Probability of finishing within {deadline_months:.0f} months: {prob:.0f}%."
                   + ("" if prob >= 80 else
                      " The schedule is not credible at this confidence level. Adding parallel "
                      "streams or bandwidth moves this more than adding contingency does."))
    return out
