"""Total cost of ownership: staying on VMware versus moving to Azure.

The on-premises side is the half most business cases get wrong. Post-Broadcom,
VMware is a per-core subscription (VMware Cloud Foundation / vSphere Foundation)
with a 16-core-per-socket minimum, so the licence line moves with core count,
not VM count -- and it renews. This model makes every on-premises component
visible and adjustable, then discounts both sides to present value.

Stay-versus-migrate is two scenarios, and two is the wrong number. An
organisation facing a Broadcom renewal has three real options -- renew as
quoted, renew having negotiated with documented alternatives in hand, or exit
over the plan period -- and the middle one is the reason to run the exercise
even if nothing moves. ``three_scenarios`` builds all three off the same
year-by-year model, so the business case and the Broadcom exposure page cannot
report different numbers for the same question.
"""

from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd


@dataclass
class OnPremProfile:
    """Current-state VMware estate economics."""
    hosts: int = 34
    sockets_per_host: int = 2
    cores_per_socket: int = 24
    # Broadcom VCF/VVF list is per core per year; minimum 16 cores billed per socket.
    vmware_cost_per_core_year: float = 135.0
    vmware_min_cores_per_socket: int = 16
    vmware_renewal_uplift_pct: float = 22.0     # observed post-acquisition renewal shock
    # Hardware
    host_capex: float = 32000.0
    hardware_refresh_years: int = 5
    years_into_refresh: int = 3
    hardware_support_pct_of_capex: float = 11.0
    # Storage array
    storage_tib_usable: float = 420.0
    storage_cost_per_tib_year: float = 340.0
    storage_refresh_capex: float = 780000.0
    # Facilities
    kw_per_host: float = 0.62
    power_cost_per_kwh: float = 0.155
    pue: float = 1.55
    rack_units_per_host: int = 2
    colo_cost_per_ru_month: float = 42.0
    # Network / other infrastructure
    network_annual: float = 145000.0
    backup_software_annual: float = 96000.0
    dr_site_annual: float = 310000.0
    monitoring_tooling_annual: float = 68000.0
    # People
    infra_fte: float = 7.5
    fte_fully_loaded_cost: float = 138000.0
    fte_pct_on_platform: float = 65.0
    # Guest OS licensing kept on-premises
    windows_datacenter_per_2core_year: float = 0.0    # set if not covered by EA
    sql_licence_annual: float = 240000.0
    # Risk / opportunity
    unplanned_downtime_hours_year: float = 14.0
    downtime_cost_per_hour: float = 22000.0
    # Year-on-year inflation of the current-state estate.
    onprem_cost_escalation_pct: float = 4.5
    # Uniform multiplier on every line of the breakdown. Set by
    # scale_onprem_to_annual() when somebody knows their total current-state
    # spend but not how it splits. 1.0 means the modelled lines stand as they are.
    cost_scale: float = 1.0


@dataclass
class AzureProfile:
    azure_monthly_run: float = 0.0        # from the cost engine
    migration_one_off: float = 0.0        # from the effort model
    # Steady-state Azure operations
    cloud_ops_fte: float = 4.5
    fte_fully_loaded_cost: float = 138000.0
    governance_tooling_annual: float = 55000.0
    training_one_off: float = 120000.0
    landing_zone_one_off: float = 210000.0
    expressroute_monthly: float = 3400.0
    # Optimisation that lands after the migration (rightsizing round 2, tagging,
    # auto-shutdown, RI true-up). Applied from year 2.
    year2plus_optimisation_pct: float = 12.0
    azure_price_escalation_pct: float = 2.0


@dataclass
class TcoInputs:
    horizon_years: int = 5
    discount_rate_pct: float = 8.0
    migration_months: float = 14.0
    residual_onprem_pct_after_migration: float = 6.0   # kit that never leaves
    hardware_resale_recovery_pct: float = 7.0


def onprem_annual_breakdown(p: OnPremProfile) -> pd.DataFrame:
    """Line-by-line current-state annual cost."""
    total_sockets = p.hosts * p.sockets_per_host
    billable_cores = total_sockets * max(p.cores_per_socket, p.vmware_min_cores_per_socket)
    physical_cores = total_sockets * p.cores_per_socket

    vmware = billable_cores * p.vmware_cost_per_core_year
    hw_amort = p.hosts * p.host_capex / max(p.hardware_refresh_years, 1)
    hw_support = p.hosts * p.host_capex * p.hardware_support_pct_of_capex / 100.0
    storage = p.storage_tib_usable * p.storage_cost_per_tib_year
    storage_amort = p.storage_refresh_capex / max(p.hardware_refresh_years, 1)

    kwh_year = p.hosts * p.kw_per_host * p.pue * 24 * 365
    power = kwh_year * p.power_cost_per_kwh
    space = p.hosts * p.rack_units_per_host * p.colo_cost_per_ru_month * 12

    people = p.infra_fte * p.fte_fully_loaded_cost * p.fte_pct_on_platform / 100.0
    windows = physical_cores / 2.0 * p.windows_datacenter_per_2core_year
    downtime = p.unplanned_downtime_hours_year * p.downtime_cost_per_hour

    rows = [
        ("VMware licensing (VCF/VVF subscription)", vmware,
         f"{billable_cores:,} billable cores x {p.vmware_cost_per_core_year:,.0f}/core/yr "
         f"(16-core-per-socket minimum applied)"),
        ("Server hardware amortisation", hw_amort, f"{p.hosts} hosts / {p.hardware_refresh_years} yr"),
        ("Hardware support & maintenance", hw_support, f"{p.hardware_support_pct_of_capex:.0f}% of capex"),
        ("Storage array support", storage, f"{p.storage_tib_usable:,.0f} TiB usable"),
        ("Storage refresh amortisation", storage_amort, ""),
        ("Power & cooling", power, f"{kwh_year / 1000:,.0f} MWh/yr at PUE {p.pue}"),
        ("Data centre space", space, f"{p.hosts * p.rack_units_per_host} RU"),
        ("Network infrastructure", p.network_annual, ""),
        ("Backup software & media", p.backup_software_annual, ""),
        ("DR site", p.dr_site_annual, ""),
        ("Monitoring & management tooling", p.monitoring_tooling_annual, ""),
        ("Infrastructure staff", people, f"{p.infra_fte} FTE at {p.fte_pct_on_platform:.0f}% allocation"),
        ("Windows Server licensing (on-prem)", windows, ""),
        ("SQL Server licensing", p.sql_licence_annual, ""),
        ("Unplanned downtime (business impact)", downtime,
         f"{p.unplanned_downtime_hours_year:.0f} h/yr x {p.downtime_cost_per_hour:,.0f}/h"),
    ]
    df = pd.DataFrame(rows, columns=["component", "annual_cost", "basis"])
    df = df[df["annual_cost"] > 0].copy()
    if p.cost_scale != 1.0:
        df["annual_cost"] = df["annual_cost"] * p.cost_scale
    df["share_pct"] = df["annual_cost"] / df["annual_cost"].sum() * 100
    return df.sort_values("annual_cost", ascending=False)


def scale_onprem_to_annual(p: OnPremProfile, target_annual: float) -> OnPremProfile:
    """Match a known total current-state spend, keeping the modelled mix.

    Somebody who knows they spend 2.4m a year running the VMware platform, but
    not how that divides between licensing, hardware, power and people, gets
    their own total with this model's proportions rather than this model's
    total. The split stays an assumption, and the Model & assumptions page
    continues to say so.
    """
    from dataclasses import replace
    base = replace(p, cost_scale=1.0)
    current = float(onprem_annual_breakdown(base)["annual_cost"].sum())
    if current <= 0 or target_annual <= 0:
        return p
    return replace(p, cost_scale=float(target_annual) / current)


def azure_annual_breakdown(a: AzureProfile) -> pd.DataFrame:
    rows = [
        ("Azure consumption (compute, storage, backup, DR)", a.azure_monthly_run * 12, "from live retail pricing"),
        ("ExpressRoute / connectivity", a.expressroute_monthly * 12, ""),
        ("Cloud operations staff", a.cloud_ops_fte * a.fte_fully_loaded_cost,
         f"{a.cloud_ops_fte} FTE"),
        ("Governance, FinOps & security tooling", a.governance_tooling_annual, ""),
    ]
    df = pd.DataFrame(rows, columns=["component", "annual_cost", "basis"])
    df = df[df["annual_cost"] > 0].copy()
    df["share_pct"] = df["annual_cost"] / df["annual_cost"].sum() * 100
    return df.sort_values("annual_cost", ascending=False)


def build_tco(onprem: OnPremProfile, azure: AzureProfile, inp: TcoInputs) -> pd.DataFrame:
    """Year-by-year cash flow for both options, plus the delta and NPV."""
    op_base = float(onprem_annual_breakdown(onprem)["annual_cost"].sum())
    az_base = float(azure_annual_breakdown(azure)["annual_cost"].sum())

    # VMware renewals reprice at the uplift on the standard 3-year cycle.
    vmware_line = (onprem.hosts * onprem.sockets_per_host
                   * max(onprem.cores_per_socket, onprem.vmware_min_cores_per_socket)
                   * onprem.vmware_cost_per_core_year)

    migration_years = inp.migration_months / 12.0
    rows = []
    for year in range(1, inp.horizon_years + 1):
        esc_op = (1 + onprem.onprem_cost_escalation_pct / 100.0) ** (year - 1)
        esc_az = (1 + azure.azure_price_escalation_pct / 100.0) ** (year - 1)

        # --- Do nothing: stay on VMware -----------------------------------
        stay = op_base * esc_op
        if year >= 4:   # first post-acquisition renewal lands in year 3-4
            stay += vmware_line * (onprem.vmware_renewal_uplift_pct / 100.0) * esc_op
        if year == onprem.hardware_refresh_years - onprem.years_into_refresh + 1:
            stay += onprem.hosts * onprem.host_capex + onprem.storage_refresh_capex

        # --- Migrate to Azure ---------------------------------------------
        # On-prem runs down over the migration period, leaving a residual tail.
        if year <= np.ceil(migration_years):
            done = min(max((year - (migration_years - 1)), 0.0), 1.0) if migration_years > 1 else 1.0
            remaining = 1.0 - 0.5 * done if year < migration_years else \
                inp.residual_onprem_pct_after_migration / 100.0
            remaining = float(np.clip(remaining, inp.residual_onprem_pct_after_migration / 100.0, 1.0))
        else:
            remaining = inp.residual_onprem_pct_after_migration / 100.0

        onprem_tail = op_base * esc_op * remaining
        # The residual Broadcom subscription is paid at the *renewal* price, not
        # today's price, for as long as the transition runs past the renewal.
        # Omitting this is the single most common way an exit case flatters
        # itself: it prices the thing being escaped at the old rate.
        if year >= 4:
            onprem_tail += vmware_line * (onprem.vmware_renewal_uplift_pct / 100.0) \
                * esc_op * remaining
        azure_ramp = min(year / max(migration_years, 0.5), 1.0)
        azure_run = az_base * esc_az * azure_ramp
        if year >= 2:
            azure_run *= (1 - azure.year2plus_optimisation_pct / 100.0)

        one_off = 0.0
        if year == 1:
            one_off += azure.landing_zone_one_off + azure.training_one_off
            one_off += azure.migration_one_off * min(1.0 / max(migration_years, 0.5), 1.0)
        if year <= np.ceil(migration_years):
            share = min(1.0, 1.0 / max(migration_years, 0.5))
            if year > 1:
                one_off += azure.migration_one_off * min(share, 1.0)
        if year == np.ceil(migration_years):
            one_off -= onprem.hosts * onprem.host_capex * inp.hardware_resale_recovery_pct / 100.0

        migrate = onprem_tail + azure_run + one_off

        rows.append({
            "year": year,
            "stay_on_vmware": stay,
            "migrate_onprem_tail": onprem_tail,
            "migrate_azure_run": azure_run,
            "migrate_one_off": one_off,
            "migrate_total": migrate,
            "annual_delta": stay - migrate,
        })

    df = pd.DataFrame(rows)
    r = inp.discount_rate_pct / 100.0
    df["discount_factor"] = 1 / (1 + r) ** (df["year"] - 0.5)
    df["pv_stay"] = df["stay_on_vmware"] * df["discount_factor"]
    df["pv_migrate"] = df["migrate_total"] * df["discount_factor"]
    df["cum_stay"] = df["stay_on_vmware"].cumsum()
    df["cum_migrate"] = df["migrate_total"].cumsum()
    df["cum_delta"] = df["cum_stay"] - df["cum_migrate"]
    return df


def tco_summary(df: pd.DataFrame, inp: TcoInputs) -> dict:
    npv_stay = float(df["pv_stay"].sum())
    npv_mig = float(df["pv_migrate"].sum())
    savings = npv_stay - npv_mig

    # Payback: first year where cumulative migrate cost drops below cumulative stay cost.
    payback = None
    for _, r in df.iterrows():
        if r["cum_delta"] > 0:
            prev = df[df["year"] == r["year"] - 1]
            prev_delta = float(prev["cum_delta"].iloc[0]) if len(prev) else -abs(r["cum_delta"])
            if prev_delta <= 0:
                frac = abs(prev_delta) / max(abs(r["cum_delta"] - prev_delta), 1e-9)
                payback = float(r["year"] - 1 + frac)
            break

    return {
        "horizon_years": inp.horizon_years,
        "npv_stay": npv_stay,
        "npv_migrate": npv_mig,
        "npv_saving": savings,
        "npv_saving_pct": savings / npv_stay * 100 if npv_stay else 0.0,
        "undiscounted_stay": float(df["stay_on_vmware"].sum()),
        "undiscounted_migrate": float(df["migrate_total"].sum()),
        "payback_years": payback,
        "year1_delta": float(df.iloc[0]["annual_delta"]),
        "steady_state_delta": float(df.iloc[-1]["annual_delta"]),
        "peak_cash_out": float(df["migrate_total"].max()),
    }


@dataclass
class NegotiatedRenewal:
    """Scenario B: what a documented alternatives evaluation is worth.

    The discount and the cap are the two things a renewal negotiation can
    actually win. ``evaluation_one_off`` is what running the evaluation costs --
    charged to B rather than hidden, because a scenario that pretends its own
    preparation is free is not a scenario the client can act on.
    """
    licence_discount_pct: float = 25.0
    renewal_cap_pct: float = 8.0
    evaluation_one_off: float = 150000.0


def negotiated_profile(p: OnPremProfile, neg: NegotiatedRenewal) -> OnPremProfile:
    """The on-premises profile as it would stand after a successful negotiation."""
    return replace(
        p,
        vmware_cost_per_core_year=p.vmware_cost_per_core_year
        * (1 - neg.licence_discount_pct / 100.0),
        vmware_renewal_uplift_pct=min(p.vmware_renewal_uplift_pct, neg.renewal_cap_pct),
    )


SCENARIO_LABELS = {
    "A": "Renew as quoted",
    "B": "Renew after negotiation",
    "C": "Exit over the plan period",
}


def three_scenarios(onprem: OnPremProfile, azure: AzureProfile, inp: TcoInputs,
                    neg: NegotiatedRenewal) -> pd.DataFrame:
    """Year-by-year cost of all three options, on one discounting basis.

    A and B are both "stay" lines and differ only in the negotiated position.
    C is the migrate line, and it carries the residual Broadcom subscription at
    the renewal price -- so C is compared against A and B on like terms.
    """
    a = build_tco(onprem, azure, inp)
    b = build_tco(negotiated_profile(onprem, neg), azure, inp)

    df = pd.DataFrame({
        "year": a["year"],
        "scenario_a": a["stay_on_vmware"],
        "scenario_b": b["stay_on_vmware"],
        "scenario_c": a["migrate_total"],
    })
    # The evaluation is a year-one cost of B. C needs the same work done, so it
    # is already inside the programme cost; A is the scenario that skips it.
    df.loc[df["year"] == 1, "scenario_b"] += neg.evaluation_one_off

    r = inp.discount_rate_pct / 100.0
    df["discount_factor"] = 1 / (1 + r) ** (df["year"] - 0.5)
    for k in "abc":
        df[f"pv_{k}"] = df[f"scenario_{k}"] * df["discount_factor"]
        df[f"cum_{k}"] = df[f"scenario_{k}"].cumsum()
    return df


def scenario_summary(df: pd.DataFrame, inp: TcoInputs) -> dict:
    """NPV per scenario, plus the two comparisons worth making out loud."""
    npv = {k: float(df[f"pv_{k}"].sum()) for k in "abc"}
    cheapest = min(npv, key=npv.get)

    def _crossover(against: str) -> float | None:
        """First year cumulative C drops below cumulative `against`."""
        delta = df[f"cum_{against}"] - df["cum_c"]
        prev = 0.0
        for year, d in zip(df["year"], delta):
            if d > 0:
                frac = abs(prev) / max(abs(d - prev), 1e-9)
                return float(year - 1 + frac)
            prev = float(d)
        return None

    return {
        "horizon_years": inp.horizon_years,
        "npv": npv,
        "cheapest": cheapest,
        "cheapest_label": SCENARIO_LABELS[cheapest.upper()],
        # Exit measured against the do-nothing quote -- the flattering comparison.
        "c_vs_a": npv["a"] - npv["c"],
        "c_vs_a_pct": (npv["a"] - npv["c"]) / npv["a"] * 100 if npv["a"] else 0.0,
        # Exit measured against a negotiated renewal -- the honest one, because a
        # client who does nothing else will still negotiate.
        "c_vs_b": npv["b"] - npv["c"],
        "c_vs_b_pct": (npv["b"] - npv["c"]) / npv["b"] * 100 if npv["b"] else 0.0,
        # What the negotiation alone is worth, with no migration at all.
        "b_vs_a": npv["a"] - npv["b"],
        "payback_vs_a": _crossover("a"),
        "payback_vs_b": _crossover("b"),
        "undiscounted": {k: float(df[f"scenario_{k}"].sum()) for k in "abc"},
    }


def onprem_monthly_total(p: OnPremProfile) -> float:
    return float(onprem_annual_breakdown(p)["annual_cost"].sum()) / 12.0


def calibrate_onprem_to_estate(p: OnPremProfile, total_vcpu: int, total_ram_gib: float,
                               provisioned_tib: float,
                               vcpu_per_core: float = 4.0,
                               host_ram_gib: float = 768.0,
                               target_utilisation: float = 0.75) -> OnPremProfile:
    """Derive host count and array size from the discovered estate rather than a guess.

    Sizing is the binding constraint of vCPU consolidation ratio and physical RAM,
    which is how vSphere clusters are actually sized -- memory usually wins.
    """
    from dataclasses import replace
    cores_per_host = p.sockets_per_host * p.cores_per_socket
    hosts_by_cpu = total_vcpu / max(vcpu_per_core * cores_per_host, 1)
    hosts_by_ram = total_ram_gib / max(host_ram_gib * target_utilisation, 1)
    hosts = int(np.ceil(max(hosts_by_cpu, hosts_by_ram)))
    hosts = max(hosts + 1, 3)      # N+1 for maintenance/HA
    return replace(p, hosts=hosts, storage_tib_usable=float(round(provisioned_tib * 1.25, 1)))
