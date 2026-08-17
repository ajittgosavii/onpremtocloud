"""The assumptions register: every modelled input, where to change it, what it drives.

The application distinguishes between three kinds of number, and the distinction
is the reason the model can be trusted:

* **Vendor fact** -- fetched live from a vendor API or taken from published
  product documentation. Not adjustable, because it is not ours to adjust.
* **Estate observation** -- read from the inventory. Change the inventory and it
  changes.
* **Calibrate with the client** -- a modelling assumption with a defensible
  default that should be replaced with the client's real figure before anything
  is presented as a number rather than a shape.

This module renders all three as one register so the question "what are you
assuming?" has a single, complete, exportable answer -- and so every assumption
carries a link to the page that controls it.
"""

from dataclasses import dataclass

import pandas as pd

VENDOR = "Vendor fact"
ESTATE = "Estate observation"
CALIBRATE = "Calibrate with client"
JUDGEMENT = "Modelling judgement"

KIND_ORDER = [CALIBRATE, JUDGEMENT, ESTATE, VENDOR]

# Page paths for st.page_link, keyed by the page title used in the navigation.
PAGES = {
    "Estate discovery": "views/inventory.py",
    "Readiness & 7R": "views/assess.py",
    "Complexity & effort": "views/effort.py",
    "Target platforms": "views/platform_options.py",
    "Business case": "views/business_case.py",
    "Wave plan & timeline": "views/plan.py",
    "Azure Migrate & tooling": "views/azure_migrate.py",
}


@dataclass
class Assumption:
    group: str
    label: str
    value: str
    kind: str
    page: str
    drives: str
    priority: int = 3          # 1 = calibrate first, 3 = leave at default
    note: str = ""


def _money(x: float, cur: str) -> str:
    sym = {"USD": "$", "EUR": "€", "GBP": "£", "AUD": "A$", "CAD": "C$",
           "INR": "₹", "JPY": "¥"}.get(cur, f"{cur} ")
    return f"{sym}{x:,.0f}"


def build(sc, res) -> pd.DataFrame:
    """The full register for the current scenario."""
    cur = sc.commercial.currency
    sz, com, ef, wp, op, az, ti = (sc.sizing, sc.commercial, sc.effort, sc.wave_plan,
                                   res.onprem, sc.azure_profile, sc.tco_inputs)
    s = res.estate_summary
    a: list[Assumption] = []

    # ---- Estate -----------------------------------------------------------
    a += [
        Assumption("Estate", "Source of the inventory",
                   "Uploaded RVTools/CSV" if sc.use_uploaded else "Synthetic (modelled)",
                   ESTATE if sc.use_uploaded else CALIBRATE, "Estate discovery",
                   "Everything. Every downstream number inherits this.",
                   1 if not sc.use_uploaded else 3,
                   "The single highest-value calibration. A real RVTools export replaces "
                   "roughly a dozen assumptions at once."),
        Assumption("Estate", "VM count", f"{s['vm_count']:,}",
                   ESTATE, "Estate discovery", "Effort, duration, cost, wave count", 3),
        Assumption("Estate", "Windows share", f"{s['windows_pct']:.0f}%",
                   ESTATE, "Estate discovery",
                   "Licensing economics and the cloud provider recommendation", 3),
        Assumption("Estate", "Mean CPU utilisation", f"{s['mean_cpu_pct']:.1f}%",
                   ESTATE if sc.use_uploaded else CALIBRATE, "Estate discovery",
                   "Right-sizing savings -- the core of the cost case", 1,
                   "If the inventory has no performance counters, this is modelled and the "
                   "right-sizing saving is not evidence."),
        Assumption("Estate", "Daily data change rate",
                   f"{pd.to_numeric(res.estate['daily_churn_pct'], errors='coerce').mean():.1f}% mean",
                   ESTATE if sc.use_uploaded else CALIBRATE, "Estate discovery",
                   "Replication delta-sync time and cutover risk", 2,
                   "Rarely present in an RVTools export. Get it from vSphere performance "
                   "counters or a replication pilot."),
        Assumption("Estate", "Utilisation profile bias", f"{sc.overprovision_bias:.1f}x",
                   JUDGEMENT, "Estate discovery",
                   "How much right-sizing headroom exists to harvest", 2),
    ]

    # ---- Sizing -----------------------------------------------------------
    a += [
        Assumption("Right-sizing", "Sizing basis",
                   "Performance-based" if sz.mode == "performance" else "As on-premises",
                   JUDGEMENT, "Readiness & 7R", "Azure VM sizes and therefore compute cost", 2),
        Assumption("Right-sizing", "Percentile", sz.percentile,
                   VENDOR, "Readiness & 7R",
                   "Sizing headroom. Azure Migrate defaults to p95.", 3),
        Assumption("Right-sizing", "Comfort factor", f"{sz.comfort_factor:g}x",
                   JUDGEMENT, "Readiness & 7R",
                   "The largest single swing factor in the Azure run rate", 1,
                   "Azure Migrate defaults to 1.3. It multiplies utilisation, not headroom, "
                   "so it quietly erases most right-sizing benefit on busy VMs."),
        Assumption("Right-sizing", "Storage policy", sz.storage_policy,
                   JUDGEMENT, "Readiness & 7R", "Managed disk cost, typically 25-35% of the bill", 2),
        Assumption("Right-sizing", "Disks sized to",
                   "consumed" if sz.size_disks_to_used else "provisioned",
                   JUDGEMENT, "Readiness & 7R", "Storage cost", 2,
                   "Azure Migrate sizes to provisioned. Sizing to consumed is more realistic "
                   "but requires a volume-consolidation exercise."),
        Assumption("Right-sizing", "Burstable (B-series) allowed",
                   "Yes" if sz.allow_burstable else "No",
                   JUDGEMENT, "Readiness & 7R", "Cost of the idle long tail", 3),
    ]

    # ---- Disposition ------------------------------------------------------
    a += [
        Assumption("Disposition", "Modernisation appetite", sc.modernisation_appetite,
                   CALIBRATE, "Readiness & 7R",
                   "The rehost/replatform split, and therefore effort and duration", 1,
                   "A business decision, not a technical one. Ask the client directly."),
        Assumption("Disposition", "Retire idle VMs",
                   "Yes" if sc.retire_zombies else "No", CALIBRATE, "Readiness & 7R",
                   "VM count in scope, and the avoided run cost", 2,
                   "Needs application-owner validation before anyone commits to it."),
        Assumption("Disposition", "Blocked VMs go to AVS",
                   "Yes" if sc.avs_for_blockers else "No -- retained on-premises",
                   CALIBRATE, "Readiness & 7R", "Whether the data centre fully closes", 2),
    ]

    # ---- Commercial -------------------------------------------------------
    a += [
        Assumption("Commercial", "Azure region and currency",
                   f"{com.region} / {com.currency}", CALIBRATE, "Business case",
                   "Every price on every page", 1),
        Assumption("Commercial", "Azure unit prices", "Live from the Retail Prices API",
                   VENDOR, "Business case",
                   "Compute, storage, backup, DR and egress cost", 3,
                   "Not adjustable. Microsoft's own published retail rates."),
        Assumption("Commercial", "Compute commitment",
                   {"none": "Pay-as-you-go", "ri-1y": "Reserved Instance 1yr",
                    "ri-3y": "Reserved Instance 3yr", "sp-1y": "Savings plan 1yr",
                    "sp-3y": "Savings plan 3yr"}.get(com.commitment, com.commitment),
                   CALIBRATE, "Business case", "20-40% of the compute bill", 1,
                   "A contractual commitment. Confirm the client will actually sign it."),
        Assumption("Commercial", "Commitment coverage of production",
                   f"{com.commitment_coverage_pct:.0f}%", CALIBRATE, "Business case",
                   "Compute cost, and the risk of paying for unused reservations", 2),
        Assumption("Commercial", "Azure Hybrid Benefit applied",
                   f"{'Yes' if com.apply_ahb_windows else 'No'}"
                   + (f", {com.ahb_coverage_pct:.0f}% of Windows VMs"
                      if com.apply_ahb_windows else ""),
                   CALIBRATE, "Business case",
                   "The Windows licence line, and the provider recommendation", 1,
                   "Depends entirely on whether the client holds Software Assurance. Verify "
                   "before this saving appears in a business case."),
        Assumption("Commercial", "Non-production scheduling",
                   f"{com.nonprod_hours_per_week:.0f} h/week" if com.nonprod_schedule
                   else "Not scheduled -- 24x7",
                   CALIBRATE, "Business case", "Non-production compute cost", 1,
                   "Requires an operational commitment. Many organisations plan it and never "
                   "implement it."),
        Assumption("Commercial", "Landing zone overhead",
                   f"{com.platform_overhead_pct:.0f}% uplift", JUDGEMENT,
                   "Business case",
                   "Hub network, firewall, bastion, Log Analytics, Defender", 2,
                   "Azure Migrate's own estimate excludes all of this."),
        Assumption("Commercial", "Monthly internet egress",
                   f"{com.monthly_egress_gb:,.0f} GB", CALIBRATE, "Business case",
                   "Egress cost", 2,
                   "Almost never known up front. Measure it at the perimeter before go-live."),
        Assumption("Commercial", "Negotiated EA/CSP discount",
                   f"{com.negotiated_discount_pct:.1f}%", CALIBRATE, "Business case",
                   "Every Azure cost line", 1,
                   "Retail rates are the starting point. Enterprise customers rarely pay them."),
        Assumption("Commercial", "Backup and DR",
                   f"Backup {'on' if com.backup_enabled else 'off'} "
                   f"({com.backup_redundancy}), DR "
                   f"{com.dr_coverage if com.dr_enabled else 'off'}",
                   CALIBRATE, "Business case", "Protection cost", 2),
    ]

    # ---- Effort -----------------------------------------------------------
    a += [
        Assumption("Effort", "Blended rate per hour",
                   _money(ef.blended_rate_per_hour, cur), CALIBRATE, "Complexity & effort",
                   "The entire migration cost", 1,
                   "Use the client's actual blended rate or the partner's rate card."),
        Assumption("Effort", "Productive hours per person-day",
                   f"{ef.productive_hours_per_day:g}", JUDGEMENT, "Complexity & effort",
                   "Duration at a given team size", 2),
        Assumption("Effort", "Migration team size", f"{ef.team_size_fte:g} FTE",
                   CALIBRATE, "Complexity & effort", "Duration", 1),
        Assumption("Effort", "Effort per VM by strategy",
                   "6h rehost to 90h refactor, plus complexity slope",
                   JUDGEMENT, "Complexity & effort", "Migration cost and duration", 1,
                   "The most challengeable assumption in the model. Validate against the "
                   "pilot wave and re-baseline."),
        Assumption("Effort", "Complexity factor weights",
                   f"{len(ef.weights)} factors, adjustable", JUDGEMENT,
                   "Complexity & effort", "Effort distribution across the estate", 2),
        Assumption("Effort", "Contingency", f"{ef.contingency_pct:.0f}%",
                   JUDGEMENT, "Complexity & effort", "Migration cost", 2),
        Assumption("Effort", "Test cycles per workload", f"{ef.test_cycles}",
                   CALIBRATE, "Complexity & effort", "Effort, at ~18% per extra cycle", 2),
        Assumption("Effort", "Third-party tooling per VM",
                   _money(ef.tooling_cost_per_vm, cur), CALIBRATE, "Azure Migrate & tooling",
                   "Migration cost", 3),
        Assumption("Effort", "Cutover failure probability",
                   "0.8% base, rising with complexity and blockers",
                   JUDGEMENT, "Complexity & effort", "Rework cost and schedule risk", 2),
    ]

    # ---- Schedule ---------------------------------------------------------
    a += [
        Assumption("Schedule", "Link bandwidth", f"{wp.bandwidth_mbps:,.0f} Mbps",
                   CALIBRATE, "Wave plan & timeline",
                   "Replication time and, in many plans, total duration", 1,
                   "Get the real circuit capacity, not the contracted one."),
        Assumption("Schedule", "Share available for migration",
                   f"{wp.bandwidth_available_pct:.0f}%", CALIBRATE, "Wave plan & timeline",
                   "Replication time", 1),
        Assumption("Schedule", "Realised WAN efficiency",
                   f"{wp.wan_efficiency_pct:.0f}%", JUDGEMENT, "Wave plan & timeline",
                   "Replication time", 2,
                   "75% is generous over a long-haul link. A replication pilot settles it."),
        Assumption("Schedule", "Team hours available per day",
                   f"{wp.team_hours_per_day:.0f}", CALIBRATE, "Wave plan & timeline",
                   "Duration of capacity-bound waves", 1),
        Assumption("Schedule", "Cutover windows per week",
                   f"{wp.parallel_streams} parallel streams", CALIBRATE,
                   "Wave plan & timeline", "Cutover calendar length", 2),
        Assumption("Schedule", "Change-freeze weeks", f"{wp.freeze_periods}",
                   CALIBRATE, "Wave plan & timeline", "Duration", 2,
                   "Year-end, quarter-end and peak-trading freezes. Ask early."),
        Assumption("Schedule", "Azure Migrate product limits",
                   "300/500 concurrent, 56 disks in flight", VENDOR,
                   "Azure Migrate & tooling", "Wave size ceilings", 3,
                   "Published by Microsoft. Not adjustable."),
    ]

    # ---- Current state ----------------------------------------------------
    a += [
        Assumption("Current state", "ESXi host count",
                   f"{op.hosts}" + (" (auto-sized from the estate)"
                                    if sc.autocalibrate_onprem else ""),
                   CALIBRATE, "Business case", "The entire on-premises baseline", 1,
                   "Get the real host count. The auto-sizing is a stand-in, not a survey."),
        Assumption("Current state", "VMware licence per core per year",
                   _money(op.vmware_cost_per_core_year, cur), CALIBRATE, "Business case",
                   "Usually the largest single current-state line", 1,
                   "Get the client's actual renewal quote. This is the number the whole "
                   "business case turns on."),
        Assumption("Current state", "Renewal uplift at next term",
                   f"{op.vmware_renewal_uplift_pct:.0f}%", CALIBRATE, "Business case",
                   "The do-nothing case from year 4", 1,
                   "Post-Broadcom renewals have repriced sharply and unevenly. Ask what the "
                   "client has actually been quoted."),
        Assumption("Current state", "Host capex and refresh cycle",
                   f"{_money(op.host_capex, cur)} / {op.hardware_refresh_years} yr, "
                   f"{op.years_into_refresh} yr in",
                   CALIBRATE, "Business case", "Whether a refresh lands inside the horizon", 1),
        Assumption("Current state", "Power cost and PUE",
                   f"{op.power_cost_per_kwh:.3f}/kWh at PUE {op.pue}", CALIBRATE,
                   "Business case", "Facilities cost", 3),
        Assumption("Current state", "Infrastructure staff",
                   f"{op.infra_fte:g} FTE at {op.fte_pct_on_platform:.0f}% allocation",
                   CALIBRATE, "Business case", "Current-state cost, and the headcount argument", 2,
                   "Treat carefully. Migration rarely removes people; it changes what they do."),
        Assumption("Current state", "Unplanned downtime cost",
                   f"{op.unplanned_downtime_hours_year:.0f} h/yr x "
                   f"{_money(op.downtime_cost_per_hour, cur)}",
                   CALIBRATE, "Business case", "Current-state cost", 2,
                   "The most-challenged line in any TCO. Either get it from the client's own "
                   "incident data or set it to zero."),
    ]

    # ---- Financial --------------------------------------------------------
    a += [
        Assumption("Financial", "Horizon and discount rate",
                   f"{ti.horizon_years} years at {ti.discount_rate_pct:.1f}%",
                   CALIBRATE, "Business case", "NPV and payback", 1,
                   "Use the client's own hurdle rate. Finance will ask."),
        Assumption("Financial", "Landing zone and training one-off",
                   f"{_money(az.landing_zone_one_off + az.training_one_off, cur)}",
                   CALIBRATE, "Business case", "Year 1 cash out", 2),
        Assumption("Financial", "Cloud operations FTE after migration",
                   f"{az.cloud_ops_fte:g}", CALIBRATE, "Business case",
                   "Steady-state cost", 2),
        Assumption("Financial", "Year 2+ optimisation",
                   f"{az.year2plus_optimisation_pct:.0f}%", JUDGEMENT, "Business case",
                   "Steady-state Azure cost", 2,
                   "Only real if someone is accountable for it. Otherwise set it to zero."),
        Assumption("Financial", "Residual on-premises after migration",
                   f"{ti.residual_onprem_pct_after_migration:.0f}%", CALIBRATE,
                   "Business case", "Whether the saving is ever fully realised", 2),
        Assumption("Financial", "Extended Security Updates per server per year",
                   "Assumption in the why-Azure comparison", CALIBRATE, "Business case",
                   "The non-Azure licensing penalty", 2),
    ]

    # ---- Scenario B: the negotiated renewal -------------------------------
    # These three drive the middle scenario, which is the one that decides
    # whether the exit case is being compared against a straw man.
    neg = sc.negotiation
    a += [
        Assumption("Renewal negotiation", "Discount achievable with documented alternatives",
                   f"{neg.licence_discount_pct:.0f}%", CALIBRATE, "Business case",
                   "Scenario B, and therefore the honest exit comparison", 1,
                   "The single most consequential assumption on the page. Anchor it on the "
                   "client's own prior discount position, not on a market average."),
        Assumption("Renewal negotiation", "Renewal uplift cap secured",
                   f"{neg.renewal_cap_pct:.0f}% against an uncapped "
                   f"{op.vmware_renewal_uplift_pct:.0f}%", CALIBRATE, "Business case",
                   "Scenario B beyond the first renewal", 1,
                   "Applied only if it beats the uncapped uplift. The cap matters more than "
                   "this cycle's discount, because the exposure is the next quote."),
        Assumption("Renewal negotiation", "Cost of running the alternatives evaluation",
                   _money(neg.evaluation_one_off, cur), CALIBRATE, "Business case",
                   "Charged to Scenario B in year one", 2,
                   "Scenario C already carries this work inside the programme cost. "
                   "Scenario A is the one that skips it."),
    ]

    # ---- Risk -------------------------------------------------------------
    a += [
        Assumption("Risk", "Monte Carlo driver ranges",
                   f"{sc.mc.iterations:,} iterations, 11 PERT drivers", JUDGEMENT,
                   "Business case", "The confidence bands and the funding recommendation", 2,
                   "The three-point ranges are where the honesty lives. Widen them if the "
                   "estate is poorly understood."),
        Assumption("Risk", "Budget and deadline targets",
                   f"{_money(sc.budget_target, cur)} / {sc.deadline_months:.0f} months",
                   CALIBRATE, "Business case", "The probability statements", 1),
    ]

    df = pd.DataFrame([{
        "Group": x.group, "Assumption": x.label, "Current value": x.value,
        "Kind": x.kind, "Set on page": x.page, "What it drives": x.drives,
        "Priority": x.priority, "Note": x.note,
    } for x in a])
    df["_k"] = df["Kind"].map({k: i for i, k in enumerate(KIND_ORDER)})
    return df.sort_values(["Priority", "_k", "Group"]).drop(columns="_k").reset_index(drop=True)


def summary(df: pd.DataFrame) -> dict:
    return {
        "total": int(len(df)),
        "vendor_facts": int((df["Kind"] == VENDOR).sum()),
        "estate": int((df["Kind"] == ESTATE).sum()),
        "calibrate": int((df["Kind"] == CALIBRATE).sum()),
        "judgement": int((df["Kind"] == JUDGEMENT).sum()),
        "priority_1": int((df["Priority"] == 1).sum()),
    }
