"""Scenario state and the single pipeline that recomputes everything.

Streamlit reruns the whole script on every widget change, so the expensive work
lives here behind ``@st.cache_data`` and is keyed on the scenario parameters.
Pages read the result; they never recompute it themselves.
"""

from dataclasses import dataclass, field, asdict, replace

import pandas as pd
import streamlit as st

from core import (assessment, complexity, costing, inventory, montecarlo,
                  platforms, rightsizing, tco, waves)


@dataclass
class Scenario:
    """Everything the user can change, in one hashable-ish place."""
    # Estate
    n_vms: int = 547
    windows_pct: float = 60.0
    seed: int = inventory.DEFAULT_SEED
    n_clusters: int = 9
    overprovision_bias: float = 1.0
    use_uploaded: bool = False
    # Where the estate came from, so no page can show a synthetic figure without
    # saying it is one. "" means nobody has chosen yet and Start here is the
    # landing page. Otherwise: reference | upload | manual.
    estate_source: str = ""
    estate_label: str = ""

    # Sizing
    sizing: rightsizing.SizingPolicy = field(default_factory=rightsizing.SizingPolicy)
    # Disposition
    modernisation_appetite: str = "balanced"
    retire_zombies: bool = True
    allow_repurchase: bool = True
    avs_for_blockers: bool = True
    # Commercial
    commercial: costing.CommercialPolicy = field(default_factory=costing.CommercialPolicy)
    # Effort
    effort: complexity.EffortModel = field(default_factory=complexity.EffortModel)
    regulated_apps: tuple = ()
    # Waves
    wave_plan: waves.WavePlan = field(default_factory=waves.WavePlan)
    start_date: str = "2026-09-01"
    # TCO
    onprem: tco.OnPremProfile = field(default_factory=tco.OnPremProfile)
    azure_profile: tco.AzureProfile = field(default_factory=tco.AzureProfile)
    tco_inputs: tco.TcoInputs = field(default_factory=tco.TcoInputs)
    autocalibrate_onprem: bool = True
    # Scenario B: the negotiated-renewal position. Lives here rather than on a
    # page so the business case and the Broadcom page cannot disagree about it.
    negotiation: tco.NegotiatedRenewal = field(default_factory=tco.NegotiatedRenewal)
    # Simulation
    mc: montecarlo.SimulationInputs = field(default_factory=montecarlo.SimulationInputs)
    budget_target: float = 4_000_000.0
    deadline_months: float = 12.0
    # Runtime
    live_pricing: bool = True

    def key(self) -> str:
        """Stable cache key. Excludes nothing -- every field affects the result."""
        return repr(asdict(self))


# --------------------------------------------------------------------------
# Session helpers
# --------------------------------------------------------------------------
def get_scenario() -> Scenario:
    if "scenario" not in st.session_state:
        st.session_state.scenario = Scenario()
    return st.session_state.scenario


def set_scenario(sc: Scenario) -> None:
    st.session_state.scenario = sc


def update(**kwargs) -> Scenario:
    sc = replace(get_scenario(), **kwargs)
    set_scenario(sc)
    return sc


def uploaded_estate() -> pd.DataFrame | None:
    return st.session_state.get("uploaded_estate")


# --------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def _build_estate(n_vms: int, windows_pct: float, seed: int, n_clusters: int,
                  bias: float) -> pd.DataFrame:
    return inventory.generate_estate(n_vms, windows_pct / 100.0, seed=seed,
                                     n_clusters=n_clusters, overprovision_bias=bias)


@st.cache_data(show_spinner="Fetching live Azure retail prices...", ttl=3600)
def _price_book(region: str, currency: str, live: bool) -> costing.PriceBook:
    return costing.load_price_book(region, currency, live=live)


@dataclass
class Result:
    estate: pd.DataFrame
    estate_summary: dict
    sized: pd.DataFrame               # + readiness + strategy + cost + complexity + wave
    sizing_summary: dict
    readiness: pd.DataFrame
    disposition: pd.DataFrame
    blockers: pd.DataFrame
    price_book: costing.PriceBook
    cost_summary: dict
    cost_breakdown: pd.DataFrame
    effort_summary: dict
    complexity_bands: pd.DataFrame
    factor_contribution: pd.DataFrame
    schedule: pd.DataFrame
    schedule_summary: dict
    onprem: tco.OnPremProfile
    tco_table: pd.DataFrame
    tco_summary: dict
    scenario_table: pd.DataFrame        # the A/B/C comparison
    scenario_summary: dict
    onprem_monthly: float
    warnings: list


def run_pipeline(sc: Scenario, estate_override: pd.DataFrame | None = None) -> Result:
    """The whole deterministic chain. Cheap enough to run per page load once cached."""
    warnings: list[str] = []

    if estate_override is not None:
        estate = estate_override.copy()
    else:
        estate = _build_estate(sc.n_vms, sc.windows_pct, sc.seed, sc.n_clusters,
                               sc.overprovision_bias)

    est_summary = inventory.estate_summary(estate)

    sized = rightsizing.rightsize(estate, sc.sizing)
    sizing_summary = rightsizing.sizing_delta_summary(sized)

    sized = assessment.assess_readiness(sized)
    sized = assessment.dispose(sized, sc.modernisation_appetite, sc.retire_zombies,
                               sc.allow_repurchase, sc.avs_for_blockers)
    readiness = assessment.readiness_summary(sized)
    disposition = assessment.disposition_summary(sized)
    blockers = assessment.top_blockers(sized, 14)

    try:
        pb = _price_book(sc.commercial.region, sc.commercial.currency, sc.live_pricing)
    except Exception as exc:
        warnings.append(f"Live pricing unavailable: {exc}. Costs below are unreliable.")
        pb = costing.PriceBook(
            vm=pd.DataFrame(columns=["arm_sku_name", "linux_hr", "windows_hr", "win_licence_hr"]),
            disk=pd.DataFrame(columns=["kind", "tier", "price_month", "price_per_10k_ops"]),
            ri=pd.DataFrame(columns=["arm_sku_name", "ri_1y_hr", "ri_3y_hr"]),
            sp=pd.DataFrame(columns=["arm_sku_name", "sp_1y_hr", "sp_3y_hr"]),
            egress_gb=0.087, backup={"instance_month": 10.0, "sql_instance_month": 25.0,
                                     "grs_gb_month": 0.0448, "lrs_gb_month": 0.0224,
                                     "archive_lrs_gb_month": 0.0013},
            asr_instance=25.0, source="unavailable")
    warnings.extend(pb.notes)

    costed = costing.compute_costs(sized, pb, sc.commercial)
    cost_summary = costing.cost_summary(costed, sc.commercial)
    cost_breakdown = costing.cost_breakdown_frame(costed)

    scored = complexity.score_estate(costed, sc.effort, set(sc.regulated_apps))
    effort_summary = complexity.effort_summary(scored, sc.effort)
    bands = complexity.complexity_distribution(scored)
    factors = complexity.factor_contribution(scored, sc.effort)

    waved = waves.build_waves(scored, sc.wave_plan)
    schedule = waves.simulate_schedule(waved, sc.wave_plan, sc.start_date)
    sched_summary = waves.schedule_summary(schedule, sc.wave_plan)

    onprem = sc.onprem
    if sc.autocalibrate_onprem:
        onprem = tco.calibrate_onprem_to_estate(
            onprem, est_summary["total_vcpu"], est_summary["total_ram_tib"] * 1024,
            est_summary["provisioned_tib"])
    onprem_monthly = tco.onprem_monthly_total(onprem)

    az_profile = replace(sc.azure_profile,
                         azure_monthly_run=cost_summary["monthly_total"],
                         migration_one_off=effort_summary["migration_cost"])
    tco_table = tco.build_tco(onprem, az_profile, sc.tco_inputs)
    tco_sum = tco.tco_summary(tco_table, sc.tco_inputs)
    scen_table = tco.three_scenarios(onprem, az_profile, sc.tco_inputs, sc.negotiation)
    scen_sum = tco.scenario_summary(scen_table, sc.tco_inputs)

    return Result(
        estate=estate, estate_summary=est_summary,
        sized=waved, sizing_summary=sizing_summary,
        readiness=readiness, disposition=disposition, blockers=blockers,
        price_book=pb, cost_summary=cost_summary, cost_breakdown=cost_breakdown,
        effort_summary=effort_summary, complexity_bands=bands, factor_contribution=factors,
        schedule=schedule, schedule_summary=sched_summary,
        onprem=onprem, tco_table=tco_table, tco_summary=tco_sum,
        scenario_table=scen_table, scenario_summary=scen_sum,
        onprem_monthly=onprem_monthly, warnings=warnings,
    )


def current() -> Result:
    """Pipeline result for the active scenario, computed once per rerun."""
    sc = get_scenario()
    override = uploaded_estate() if sc.use_uploaded else None
    cache_token = (sc.key(), id(override) if override is not None else None)
    if st.session_state.get("_pipeline_token") == cache_token and "_pipeline" in st.session_state:
        return st.session_state["_pipeline"]
    res = run_pipeline(sc, override)
    st.session_state["_pipeline"] = res
    st.session_state["_pipeline_token"] = cache_token
    return res


def monte_carlo(res: Result, sc: Scenario) -> pd.DataFrame:
    """Simulation for the active scenario, computed once per scenario.

    Memoised on the same principle as ``current()``. This matters since the
    simulation moved onto Business case as a tab: Streamlit executes every tab
    body on every rerun, so without this the default 10,000 iterations would run
    again each time somebody nudged an unrelated slider on another tab.
    """
    token = sc.key()
    if st.session_state.get("_mc_token") == token and "_mc" in st.session_state:
        return st.session_state["_mc"]

    det = montecarlo.Deterministic(
        migration_cost=res.effort_summary["migration_cost"],
        effort_hours=res.effort_summary["total_effort_hours"],
        team_hours_per_day=sc.wave_plan.team_hours_per_day,
        elapsed_days=res.schedule_summary.get("elapsed_days", 0) or 1,
        replication_days=float(res.schedule["replication_days"].sum()) if len(res.schedule) else 1,
        engineering_days=float(res.schedule["engineering_days"].sum()) if len(res.schedule) else 1,
        azure_monthly_cost=res.cost_summary["monthly_total"],
        onprem_monthly_cost=res.onprem_monthly,
        expected_rollbacks=res.schedule_summary.get("expected_rollbacks", 0.0),
        vm_count=int(res.estate_summary["vm_count"]),
        cost_per_vm=res.effort_summary["cost_per_vm"],
    )
    sim = montecarlo.run(det, sc.mc)
    st.session_state["_mc"] = sim
    st.session_state["_mc_token"] = token
    return sim
