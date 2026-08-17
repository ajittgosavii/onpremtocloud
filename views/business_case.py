"""Business case: staying on VMware versus migrating to Azure.

This page absorbed three former pages, because none of them was a destination in
the exit narrative on its own:

* **Azure cost simulator** -- the commercial levers (reservations, savings plans,
  Hybrid Benefit, non-production scheduling) are inputs to the case, not an
  answer, so they live on the *Cost levers* tab.
* **Risk simulation** -- a Monte Carlo over the programme is a confidence
  statement about this case, so it lives on the *Confidence* tab.
* **Cloud provider** -- cut, because the destination is settled. The two findings
  worth keeping are the "why Azure" panel below.
"""

from dataclasses import replace

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core import azure_catalog as cat
from core import costing, montecarlo, providers, scenario, tco, ui

sc = scenario.get_scenario()
res = scenario.current()
cur = sc.commercial.currency

ui.page_header(
    "Business case",
    "The on-premises side is the half most business cases get wrong. Post-Broadcom, VMware is "
    "a per-core subscription with a sixteen-core-per-socket minimum that renews - so the "
    "licence line moves with core count, not VM count. Every component below is visible and "
    "adjustable, because the credibility of the comparison rests entirely on the baseline.",
)

# --------------------------------------------------------------------------
with st.expander("Current-state (on-premises) assumptions", expanded=True):
    op = res.onprem
    auto = st.toggle(
        "Size the cluster automatically from the discovered estate", sc.autocalibrate_onprem,
        help="Derives host count from vCPU consolidation ratio and physical memory, with N+1 "
             "for maintenance. Turn it off to enter the real host count.")
    if auto != sc.autocalibrate_onprem:
        scenario.update(autocalibrate_onprem=auto)
        st.rerun()

    c1, c2, c3, c4 = st.columns(4)
    hosts = c1.number_input("ESXi hosts", 1, 2000, int(op.hosts), disabled=auto)
    sockets = c2.number_input("Sockets per host", 1, 8, int(op.sockets_per_host))
    cores = c3.number_input("Cores per socket", 4, 128, int(op.cores_per_socket))
    vcf = c4.number_input("VCF/VVF per core per year", 0.0, 800.0,
                          float(op.vmware_cost_per_core_year), 5.0,
                          help="Broadcom lists per core per year with a sixteen-core-per-socket "
                               "minimum. Post-acquisition renewals have repriced sharply.")

    c5, c6, c7, c8 = st.columns(4)
    renewal = c5.slider("Renewal uplift at next term (%)", 0, 300,
                        int(op.vmware_renewal_uplift_pct),
                        help="Applied from year 4, when the first post-acquisition renewal "
                             "typically lands.")
    capex = c6.number_input("Host capex", 5000.0, 300000.0, float(op.host_capex), 1000.0)
    refresh = c7.number_input("Hardware refresh cycle (years)", 3, 10,
                              int(op.hardware_refresh_years))
    into = c8.number_input("Years into the current cycle", 0, 10, int(op.years_into_refresh))

    c9, c10, c11, c12 = st.columns(4)
    kwh = c9.number_input("Power cost per kWh", 0.01, 1.5, float(op.power_cost_per_kwh), 0.005,
                          format="%.3f")
    pue = c10.number_input("Data centre PUE", 1.0, 3.0, float(op.pue), 0.05)
    fte = c11.number_input("Infrastructure FTE", 0.0, 200.0, float(op.infra_fte), 0.5)
    fte_cost = c12.number_input("Fully loaded FTE cost", 30000.0, 400000.0,
                                float(op.fte_fully_loaded_cost), 1000.0)

    c13, c14, c15, c16 = st.columns(4)
    dr_site = c13.number_input("DR site annual", 0.0, 5e6, float(op.dr_site_annual), 10000.0)
    backup_sw = c14.number_input("Backup software annual", 0.0, 2e6,
                                 float(op.backup_software_annual), 5000.0)
    sql_lic = c15.number_input("SQL Server licensing annual", 0.0, 5e6,
                               float(op.sql_licence_annual), 10000.0)
    downtime = c16.number_input("Downtime cost per hour", 0.0, 500000.0,
                                float(op.downtime_cost_per_hour), 1000.0)

    esc = st.slider("On-premises cost escalation per year (%)", 0.0, 15.0,
                    float(op.onprem_cost_escalation_pct), 0.5)

    new_op = replace(sc.onprem, hosts=int(hosts), sockets_per_host=int(sockets),
                     cores_per_socket=int(cores), vmware_cost_per_core_year=float(vcf),
                     vmware_renewal_uplift_pct=float(renewal), host_capex=float(capex),
                     hardware_refresh_years=int(refresh), years_into_refresh=int(into),
                     power_cost_per_kwh=float(kwh), pue=float(pue), infra_fte=float(fte),
                     fte_fully_loaded_cost=float(fte_cost), dr_site_annual=float(dr_site),
                     backup_software_annual=float(backup_sw), sql_licence_annual=float(sql_lic),
                     downtime_cost_per_hour=float(downtime),
                     onprem_cost_escalation_pct=float(esc))
    if new_op != sc.onprem:
        scenario.update(onprem=new_op)
        st.rerun()

with st.expander("Azure-side and financial assumptions", expanded=False):
    az, ti = sc.azure_profile, sc.tco_inputs
    c1, c2, c3, c4 = st.columns(4)
    ops_fte = c1.number_input("Cloud operations FTE", 0.0, 100.0, float(az.cloud_ops_fte), 0.5)
    lz = c2.number_input("Landing zone build (one-off)", 0.0, 5e6,
                         float(az.landing_zone_one_off), 10000.0)
    train = c3.number_input("Training & enablement (one-off)", 0.0, 2e6,
                            float(az.training_one_off), 10000.0)
    er = c4.number_input("ExpressRoute monthly", 0.0, 100000.0,
                         float(az.expressroute_monthly), 100.0)

    c5, c6, c7, c8 = st.columns(4)
    horizon = c5.slider("Horizon (years)", 3, 10, int(ti.horizon_years))
    disc = c6.slider("Discount rate (%)", 0.0, 20.0, float(ti.discount_rate_pct), 0.5)
    mig_months = c7.number_input("Migration duration (months)", 1.0, 60.0,
                                 float(res.schedule_summary.get("elapsed_months",
                                                                ti.migration_months)), 0.5)
    residual = c8.slider("Residual on-premises after migration (%)", 0, 40,
                         int(ti.residual_onprem_pct_after_migration),
                         help="The kit that never leaves - out-of-scope systems, network "
                              "edge, physical appliances.")

    c9, c10, c11 = st.columns(3)
    opt2 = c9.slider("Year 2+ optimisation (%)", 0, 40, int(az.year2plus_optimisation_pct),
                     help="Post-migration right-sizing against real Azure Monitor data, "
                          "reservation true-up and auto-shutdown.")
    az_esc = c10.slider("Azure price escalation (%/yr)", 0.0, 10.0,
                        float(az.azure_price_escalation_pct), 0.5)
    resale = c11.slider("Hardware resale recovery (%)", 0, 40,
                        int(ti.hardware_resale_recovery_pct))

    new_az = replace(az, cloud_ops_fte=float(ops_fte), landing_zone_one_off=float(lz),
                     training_one_off=float(train), expressroute_monthly=float(er),
                     year2plus_optimisation_pct=float(opt2),
                     azure_price_escalation_pct=float(az_esc))
    new_ti = replace(ti, horizon_years=int(horizon), discount_rate_pct=float(disc),
                     migration_months=float(mig_months),
                     residual_onprem_pct_after_migration=float(residual),
                     hardware_resale_recovery_pct=float(resale))
    if new_az != az or new_ti != ti:
        scenario.update(azure_profile=new_az, tco_inputs=new_ti)
        st.rerun()

res = scenario.current()
ts = res.tco_summary

# --------------------------------------------------------------------------
ui.metric_row([
    (f"{ts['horizon_years']}-year NPV, stay", ui.compact_money(ts["npv_stay"], cur), None),
    (f"{ts['horizon_years']}-year NPV, migrate", ui.compact_money(ts["npv_migrate"], cur),
     f"{-ts['npv_saving_pct']:.0f}%"),
    ("NPV saving", ui.compact_money(ts["npv_saving"], cur),
     f"{ts['npv_saving_pct']:.1f}% of the do-nothing case"),
    ("Payback", f"{ts['payback_years']:.1f} years" if ts["payback_years"] else "beyond horizon",
     None),
    ("Steady-state annual saving", ui.compact_money(ts["steady_state_delta"], cur), None),
])

ui.takeaway(
    "The argument this page has to win is not \"Azure is cheaper\" - it is \"doing nothing is "
    "not free\". The do-nothing line rises: the VMware subscription renews at a higher rate, "
    "the hardware refresh lands on schedule, and neither is optional. Show the "
    "<b>Sensitivity</b> tab unprompted; a case that survives having its assumptions attacked "
    "in front of the client is worth far more than one that is merely presented.")


# ==========================================================================
# Why Azure, in one panel.
#
# Salvaged from the former Cloud provider page, which was cut because the
# destination is already settled and a hyperscaler bake-off reopens it. These
# two findings survive because they pre-empt the question a CFO does ask -
# "did you check the others?" - without re-running the selection.
# ==========================================================================
ui.section(
    "Why Azure",
    "Not a provider selection - that decision is made. This is the answer to "
    "\"did anyone check?\", in two numbers.")

est, sized = res.estate, res.sized
_s = res.estate_summary

azure_prem = 0.046
if len(res.price_book.vm):
    _row = res.price_book.vm[res.price_book.vm["arm_sku_name"] == "Standard_D4s_v5"]
    if len(_row) and pd.notna(_row.iloc[0]["win_licence_hr"]):
        azure_prem = float(_row.iloc[0]["win_licence_hr"]) / 4

aws_prem, aws_live = 0.046, False
try:
    aws_prem = providers.aws_windows_premium(sc.commercial.region,
                                             live=sc.live_pricing)["per_vcpu_hr"]
    aws_live = True
except Exception:
    pass

_lic_inputs = dict(
    windows_vcpu=int(sized[sized["os_family"] == "Windows"]["azure_vcpu"].sum()),
    windows_vms=int((est["os_family"] == "Windows").sum()),
    sql_vms=int((est["db_engine"] == "Microsoft SQL Server").sum()),
    eol_windows_vms=int(((est["os_family"] == "Windows") & est["os_eol"]).sum()),
    oracle_vms=int((est["db_engine"] == "Oracle Database").sum()),
    linux_vcpu=int(sized[sized["os_family"] == "Linux"]["azure_vcpu"].sum()),
    total_vcpu=int(sized["azure_vcpu"].sum()),
    azure_windows_premium_per_vcpu_hr=azure_prem,
    aws_windows_premium_per_vcpu_hr=aws_prem,
    esu_per_vm_year=providers.ESU_PER_VM_YEAR,
)
lic_sa = providers.licensing_comparison(
    providers.LicensingInputs(owns_software_assurance=True, **_lic_inputs))
lic_no_sa = providers.licensing_comparison(
    providers.LicensingInputs(owns_software_assurance=False, **_lic_inputs))


def _annual(frame: pd.DataFrame, key: str) -> float:
    row = frame[frame["key"] == key]
    return float(row.iloc[0]["total_annual"]) if len(row) else 0.0


_gap_sa = _annual(lic_sa, "aws") - _annual(lic_sa, "azure")
_best_no_sa = lic_no_sa.iloc[0]

ui.metric_row([
    ("Windows licence, Azure", f"{ui.money(azure_prem, cur, 4)}/vCPU/hr",
     "live retail rate"),
    ("Windows licence, AWS", f"{ui.money(aws_prem, cur, 4)}/vCPU/hr",
     "live feed" if aws_live else "published list price"),
    ("Difference on compute", f"{abs(aws_prem - azure_prem) / max(azure_prem, 1e-9) * 100:.1f}%",
     "the case is not cheaper cores"),
    ("Azure advantage, with SA", f"{ui.compact_money(_gap_sa, cur)}/yr",
     "Hybrid Benefit + free ESU"),
    ("Cheapest without SA", str(_best_no_sa["provider"]),
     f"{ui.compact_money(float(_best_no_sa['total_annual']), cur)}/yr"),
], tones=["", "", "", "pos", "warn" if _best_no_sa["key"] != "azure" else ""])

_no_sa_note = (
    f"<b>Without Software Assurance the advantage narrows sharply</b> - on this estate "
    f"{_best_no_sa['provider']} comes out cheapest on licensing alone "
    f"({ui.compact_money(float(_best_no_sa['total_annual']), cur)} against "
    f"{ui.compact_money(_annual(lic_no_sa, 'azure'), cur)} for Azure). Confirm the client "
    "actually holds SA before any Hybrid Benefit saving enters this case."
    if _best_no_sa["key"] != "azure" else
    "Azure stays cheapest on licensing even without Software Assurance on this estate, but "
    "the margin is thin - confirm the SA position rather than assuming it.")

ui.note(
    f"<b>Azure and AWS charge within {abs(aws_prem - azure_prem) / max(azure_prem, 1e-9) * 100:.1f}% "
    "of each other for licence-included Windows compute.</b> So the Azure case is not cheaper "
    "cores - it is that Azure is the only provider allowing bring-your-own-licence on ordinary "
    "shared tenancy, and the only one giving free Extended Security Updates for end-of-life "
    "Windows. Both of those depend on Software Assurance.")
ui.note(_no_sa_note, "warn")

# ==========================================================================
tab_cash, tab_onprem, tab_azure, tab_levers, tab_conf, tab_sens = st.tabs(
    ["Cash flow", "Current-state cost base", "Azure cost base", "Cost levers",
     "Confidence", "Sensitivity"])

# --------------------------------------------------------------------------
with tab_cash:
    t = res.tco_table
    fig = go.Figure()
    fig.add_trace(go.Bar(x=t["year"], y=t["stay_on_vmware"], name="Stay on VMware",
                         marker_color=ui.PALETTE[3], opacity=0.85))
    fig.add_trace(go.Bar(x=t["year"], y=t["migrate_total"], name="Migrate to Azure",
                         marker_color=ui.PALETTE[0], opacity=0.85))
    fig.update_layout(height=380, barmode="group", title="Annual cost by option",
                      xaxis_title="Year", yaxis_title=f"{cur} per year",
                      xaxis=dict(dtick=1))
    ui.legend_top(fig)
    st.plotly_chart(fig, width="stretch")

    c1, c2 = st.columns(2)
    with c1:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=t["year"], y=t["cum_stay"], name="Stay",
                                 mode="lines+markers", line=dict(width=3, color=ui.PALETTE[3])))
        fig.add_trace(go.Scatter(x=t["year"], y=t["cum_migrate"], name="Migrate",
                                 mode="lines+markers", line=dict(width=3, color=ui.PALETTE[0])))
        fig.update_layout(height=340, title="Cumulative cost",
                          xaxis_title="Year", yaxis_title=cur, xaxis=dict(dtick=1))
        ui.legend_top(fig)
        st.plotly_chart(fig, width="stretch")
    with c2:
        fig = go.Figure(go.Bar(
            x=t["year"], y=t["cum_delta"],
            marker_color=[ui.PALETTE[2] if v > 0 else ui.PALETTE[3] for v in t["cum_delta"]],
            text=[ui.compact_money(v, cur) for v in t["cum_delta"]], textposition="auto"))
        fig.update_layout(height=340, title="Cumulative saving from migrating",
                          xaxis_title="Year", yaxis_title=cur, xaxis=dict(dtick=1))
        st.plotly_chart(fig, width="stretch")

    disp = t.copy()
    for c in ["stay_on_vmware", "migrate_onprem_tail", "migrate_azure_run",
              "migrate_one_off", "migrate_total", "annual_delta", "cum_delta"]:
        disp[c] = disp[c].map(lambda v: ui.money(v, cur))
    st.dataframe(disp[["year", "stay_on_vmware", "migrate_onprem_tail", "migrate_azure_run",
                       "migrate_one_off", "migrate_total", "annual_delta", "cum_delta"]]
                 .rename(columns={
                     "year": "Year", "stay_on_vmware": "Stay on VMware",
                     "migrate_onprem_tail": "On-prem tail", "migrate_azure_run": "Azure run",
                     "migrate_one_off": "One-off", "migrate_total": "Migrate total",
                     "annual_delta": "Annual delta", "cum_delta": "Cumulative delta"}),
                 hide_index=True, width="stretch")

    if ts["year1_delta"] < 0:
        ui.note(
            f"<b>Year 1 costs {ui.compact_money(abs(ts['year1_delta']), cur)} more than doing "
            "nothing.</b> That is not a flaw in the case - it is the shape of every migration. "
            "The programme cost, the landing zone build and the dual-run overlap all land "
            "before the on-premises estate switches off. Fund it as an investment year and "
            f"hold the programme to the year {int(ts['payback_years'] or 3)} crossover.",
            "warn")

# --------------------------------------------------------------------------
with tab_onprem:
    bd = tco.onprem_annual_breakdown(res.onprem)
    fig = go.Figure(go.Bar(
        x=bd["annual_cost"], y=bd["component"], orientation="h",
        marker_color=ui.PALETTE[3],
        text=[f"{ui.compact_money(v, cur)}  ({p:.0f}%)"
              for v, p in zip(bd["annual_cost"], bd["share_pct"])], textposition="auto"))
    fig.update_layout(height=520, title="Current-state annual cost",
                      xaxis_title=f"{cur}/year", yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig, width="stretch")

    disp = bd.copy()
    disp["annual_cost"] = disp["annual_cost"].map(lambda v: ui.money(v, cur))
    disp["share_pct"] = disp["share_pct"].map(lambda v: f"{v:.1f}%")
    st.dataframe(disp.rename(columns={"component": "Component", "annual_cost": "Annual",
                                      "share_pct": "Share", "basis": "Basis"}),
                 hide_index=True, width="stretch",
                 column_config={"Basis": st.column_config.TextColumn(width="large")})

    vmw = bd[bd["component"].str.startswith("VMware")]
    if len(vmw):
        v = float(vmw["annual_cost"].iloc[0])
        ui.note(
            f"<b>VMware licensing alone is {ui.compact_money(v, cur)} per year, "
            f"{float(vmw['share_pct'].iloc[0]):.0f}% of the current-state cost.</b> It is "
            "billed per physical core with a sixteen-core-per-socket minimum, so it does not "
            "fall when VMs are consolidated - only when hosts are removed. And it renews. "
            f"At the modelled {res.onprem.vmware_renewal_uplift_pct:.0f}% uplift, the next "
            f"renewal adds {ui.compact_money(v * res.onprem.vmware_renewal_uplift_pct / 100, cur)} "
            "per year on its own.")

    st.metric("Total current-state annual cost",
              ui.money(float(bd["annual_cost"].sum()), cur),
              f"{ui.money(res.onprem_monthly, cur)} per month")

# --------------------------------------------------------------------------
with tab_azure:
    az_profile = replace(sc.azure_profile,
                         azure_monthly_run=res.cost_summary["monthly_total"],
                         migration_one_off=res.effort_summary["migration_cost"])
    bd = tco.azure_annual_breakdown(az_profile)
    c1, c2 = st.columns([1.3, 1])
    with c1:
        fig = go.Figure(go.Bar(
            x=bd["annual_cost"], y=bd["component"], orientation="h",
            marker_color=ui.PALETTE[0],
            text=[f"{ui.compact_money(v, cur)}  ({p:.0f}%)"
                  for v, p in zip(bd["annual_cost"], bd["share_pct"])], textposition="auto"))
        fig.update_layout(height=320, title="Azure steady-state annual cost",
                          xaxis_title=f"{cur}/year", yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, width="stretch")
    with c2:
        st.markdown("**One-off programme costs**")
        one_off = pd.DataFrame([
            {"Item": "Migration execution", "Cost": res.effort_summary["migration_cost"]},
            {"Item": "Landing zone build", "Cost": sc.azure_profile.landing_zone_one_off},
            {"Item": "Training & enablement", "Cost": sc.azure_profile.training_one_off},
        ])
        one_off["Cost"] = one_off["Cost"].map(lambda v: ui.money(v, cur))
        st.dataframe(one_off, hide_index=True, width="stretch")
        st.metric("Total one-off",
                  ui.money(res.effort_summary["migration_cost"]
                           + sc.azure_profile.landing_zone_one_off
                           + sc.azure_profile.training_one_off, cur))

    disp = bd.copy()
    disp["annual_cost"] = disp["annual_cost"].map(lambda v: ui.money(v, cur))
    disp["share_pct"] = disp["share_pct"].map(lambda v: f"{v:.1f}%")
    st.dataframe(disp.rename(columns={"component": "Component", "annual_cost": "Annual",
                                      "share_pct": "Share", "basis": "Basis"}),
                 hide_index=True, width="stretch")

    # ---- monthly run rate, from the former cost simulator -----------------
    ui.section("The monthly run rate underneath it",
               "The annual figure above is this, times twelve, plus the platform lines. "
               "Priced against live Azure retail rates for "
               f"{cat.REGIONS[sc.commercial.region]['label']}.")
    st.markdown(ui.pricing_badge(res.price_book.source)
                + f"<span class='pill'>{res.cost_summary['priced_from_api_pct']:.0f}% of VMs "
                  "matched to a live meter</span>"
                + f"<span class='pill'>{len(res.price_book.vm):,} VM meters</span>"
                + f"<span class='pill'>{len(res.price_book.disk):,} disk meters</span>",
                unsafe_allow_html=True)

    cs = res.cost_summary
    ui.metric_row([
        ("Monthly Azure run rate", ui.money(cs["monthly_total"], cur),
         f"{ui.compact_money(cs['annual_total'], cur)} per year"),
        ("Unoptimised baseline", ui.money(cs["baseline_monthly"], cur),
         f"-{cs['monthly_saving'] / cs['baseline_monthly'] * 100:.0f}% with levers"),
        ("Average per VM", ui.money(cs["avg_cost_per_vm"], cur, 2),
         f"{cs['vms_costed']:,} VMs costed"),
        ("Avoided by retiring", f"{ui.compact_money(cs['retire_saving_monthly'], cur)}/mo",
         f"{cs['vms_retired']} VMs"),
        ("On-premises today", ui.money(res.onprem_monthly, cur),
         f"{(cs['monthly_total'] - res.onprem_monthly) / res.onprem_monthly * 100:+.0f}%"),
    ])

    c1, c2 = st.columns([1.4, 1])
    with c1:
        comp = res.cost_breakdown
        fig = go.Figure(go.Bar(
            x=comp["monthly_cost"], y=comp["component"], orientation="h",
            marker_color=ui.PALETTE[0],
            text=[f"{ui.compact_money(v, cur)}  ({p:.0f}%)"
                  for v, p in zip(comp["monthly_cost"], comp["share_pct"])],
            textposition="auto"))
        fig.update_layout(height=380, title="Monthly cost by component",
                          xaxis_title=f"{cur}/month", yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, width="stretch")
    with c2:
        st.plotly_chart(ui.donut(comp["component"], comp["monthly_cost"], height=380),
                        width="stretch")

    st.markdown("### Cost by dimension")
    dim = st.selectbox("Group by", ["environment", "criticality", "tier", "strategy",
                                    "os_family", "azure_series", "app_name", "cluster"])
    live = res.sized[res.sized["strategy"] != "Retire"]
    g = (live.groupby(dim).agg(vms=("vm_name", "count"),
                               monthly=("monthly_cost", "sum"),
                               compute=("compute_cost", "sum"),
                               storage=("storage_cost", "sum"))
         .reset_index().sort_values("monthly", ascending=False))
    g["per_vm"] = g["monthly"] / g["vms"]
    fig = px.bar(g.head(20), x=dim, y="monthly", color=dim,
                 color_discrete_sequence=ui.PALETTE, title=f"Monthly cost by {dim}")
    fig.update_layout(height=360, showlegend=False, yaxis_title=f"{cur}/month", xaxis_title="")
    st.plotly_chart(fig, width="stretch")
    st.dataframe(g.head(30).round(2), hide_index=True, width="stretch")

    st.markdown("### Where the spend concentrates")
    live = live.sort_values("monthly_cost", ascending=False).copy()
    live["cum_pct"] = live["monthly_cost"].cumsum() / live["monthly_cost"].sum() * 100
    n80 = int((live["cum_pct"] <= 80).sum()) + 1
    ui.note(
        f"<b>{n80} VMs ({n80 / len(live) * 100:.0f}% of the estate) account for 80% of the "
        "Azure bill.</b> Optimisation effort belongs there. The long tail is where automation "
        "and standard patterns belong.")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=list(range(1, len(live) + 1)), y=live["cum_pct"],
                             mode="lines", line=dict(width=3, color=ui.PALETTE[0]),
                             name="Cumulative cost"))
    fig.add_hline(y=80, line_dash="dash", line_color="rgba(180,73,95,.7)",
                  annotation_text="80% of spend")
    fig.update_layout(height=340, title="Cost concentration",
                      xaxis_title="VMs ranked by cost", yaxis_title="Cumulative % of spend")
    st.plotly_chart(fig, width="stretch")

    st.markdown("**Most expensive VMs**")
    st.dataframe(live.head(30)[["vm_name", "app_name", "environment", "azure_sku", "azure_vcpu",
                                "azure_ram_gib", "total_alloc_gib", "compute_cost",
                                "storage_cost", "monthly_cost"]].round(2),
                 hide_index=True, width="stretch", height=420)
    ui.df_download(live, "azure_costs_per_vm.csv", "Download full per-VM costing")

    st.markdown("### Headcount change")
    hc = pd.DataFrame([
        {"Role": "Infrastructure staff on the VMware platform",
         "FTE": res.onprem.infra_fte * res.onprem.fte_pct_on_platform / 100,
         "Annual cost": res.onprem.infra_fte * res.onprem.fte_fully_loaded_cost
                        * res.onprem.fte_pct_on_platform / 100},
        {"Role": "Cloud operations staff after migration",
         "FTE": sc.azure_profile.cloud_ops_fte,
         "Annual cost": sc.azure_profile.cloud_ops_fte * sc.azure_profile.fte_fully_loaded_cost},
    ])
    hc["Annual cost"] = hc["Annual cost"].map(lambda v: ui.money(v, cur))
    st.dataframe(hc.round(2), hide_index=True, width="stretch")
    ui.note(
        "Treat the headcount line carefully. Migration rarely removes people - it changes what "
        "they do. If the business case depends on a reduction that nobody intends to make, it "
        "will not survive contact with the CFO.")

# --------------------------------------------------------------------------
# Cost levers -- the former Azure cost simulator. These are inputs to the case
# above, which is why they sit inside it rather than beside it in the narrative.
# --------------------------------------------------------------------------
with tab_levers:
    st.caption("Every lever here reprices the whole estate against live Azure retail rates, so "
               "the NPV at the top of this page moves as you change them.")

    with st.expander("Commercial levers", expanded=True):
        p = sc.commercial
        c1, c2, c3, c4 = st.columns(4)
        commitment = c1.selectbox(
            "Compute commitment", ["none", "ri-1y", "ri-3y", "sp-1y", "sp-3y"],
            index=["none", "ri-1y", "ri-3y", "sp-1y", "sp-3y"].index(p.commitment),
            format_func=lambda v: {"none": "Pay-as-you-go", "ri-1y": "Reserved Instance, 1 year",
                                   "ri-3y": "Reserved Instance, 3 year",
                                   "sp-1y": "Savings plan, 1 year",
                                   "sp-3y": "Savings plan, 3 year"}[v],
            help="Reservations are cheaper but lock to a VM family and region. Savings plans "
                 "are slightly dearer and far more flexible.")
        coverage = c2.slider("Commitment coverage of production (%)", 0, 100,
                             int(p.commitment_coverage_pct),
                             help="Committing 100% of a portfolio you are still migrating is "
                                  "how organisations end up paying for unused reservations.")
        ahb = c3.toggle("Azure Hybrid Benefit", p.apply_ahb_windows,
                        help="Removes the Windows Server licence component for VMs covered by "
                             "Software Assurance.")
        ahb_cov = c4.slider("Windows VMs with eligible SA (%)", 0, 100, int(p.ahb_coverage_pct),
                            disabled=not ahb)

        c5, c6, c7, c8 = st.columns(4)
        sched = c5.toggle("Schedule non-production off-hours", p.nonprod_schedule)
        hours = c6.slider("Non-production hours per week", 20, 168,
                          int(p.nonprod_hours_per_week), disabled=not sched,
                          help="168 is 24x7. 55 is roughly 11 hours a day, five days a week.")
        backup = c7.toggle("Azure Backup enabled", p.backup_enabled)
        redundancy = c8.selectbox("Vault redundancy", ["GRS", "LRS"],
                                  index=0 if p.backup_redundancy == "GRS" else 1,
                                  disabled=not backup)

        c9, c10, c11, c12 = st.columns(4)
        dr = c9.toggle("Disaster recovery (Site Recovery)", p.dr_enabled)
        dr_cov = c10.selectbox("DR coverage",
                               ["Tier 0 only", "Tier 0 + Tier 1", "All production"],
                               index=["Tier 0 only", "Tier 0 + Tier 1",
                                      "All production"].index(p.dr_coverage),
                               disabled=not dr)
        overhead = c11.slider("Landing zone overhead (%)", 0, 30, int(p.platform_overhead_pct),
                              help="Hub network, firewall, bastion, private endpoints, Log "
                                   "Analytics, Defender for Cloud and management VMs. Azure "
                                   "Migrate's own estimate excludes all of this.")
        discount = c12.slider("Negotiated EA / CSP discount (%)", 0.0, 25.0,
                              float(p.negotiated_discount_pct), 0.5)

        egress = st.slider("Monthly internet egress (GB)", 0, 100000,
                           int(p.monthly_egress_gb), step=500,
                           help=f"Charged at {ui.money(res.price_book.egress_gb, cur, 3)}/GB "
                                "above the free 100 GB, from the live API.")

        new = replace(p, commitment=commitment, commitment_coverage_pct=float(coverage),
                      apply_ahb_windows=ahb, ahb_coverage_pct=float(ahb_cov),
                      nonprod_schedule=sched, nonprod_hours_per_week=float(hours),
                      backup_enabled=backup, backup_redundancy=redundancy,
                      dr_enabled=dr, dr_coverage=dr_cov,
                      platform_overhead_pct=float(overhead),
                      negotiated_discount_pct=float(discount),
                      monthly_egress_gb=float(egress))
        if new != p:
            scenario.update(commercial=new)
            st.rerun()

    st.markdown("### What each lever is actually worth")
    st.caption("Each row turns one lever off and reprices the whole estate. The delta is what "
               "that lever contributes to the plan.")
    lev = costing.lever_sensitivity(res.sized, res.price_book, sc.commercial)
    lev_disp = lev.copy()
    lev_disp["monthly_cost"] = lev_disp["monthly_cost"].map(lambda v: ui.money(v, cur))
    lev_disp["delta_vs_plan"] = lev.apply(
        lambda r: f"{'+' if r['delta_vs_plan'] >= 0 else '-'}"
                  f"{ui.money(abs(r['delta_vs_plan']), cur)} ({r['delta_pct']:+.1f}%)", axis=1)
    st.dataframe(lev_disp[["lever", "monthly_cost", "delta_vs_plan"]].rename(
        columns={"lever": "If this lever were removed", "monthly_cost": "Monthly cost",
                 "delta_vs_plan": "Change vs the current plan"}),
        hide_index=True, width="stretch")

    fig = go.Figure(go.Bar(
        x=lev["delta_vs_plan"], y=lev["lever"], orientation="h",
        marker_color=[ui.PALETTE[3] if v > 0 else ui.PALETTE[2] for v in lev["delta_vs_plan"]],
        text=[ui.compact_money(v, cur) for v in lev["delta_vs_plan"]], textposition="auto"))
    fig.update_layout(height=300, title="Monthly cost impact of removing each lever",
                      xaxis_title=f"{cur}/month", yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig, width="stretch")

    ui.note(
        "Two of these are decisions, not switches. Reservations and savings plans are "
        "contractual commitments that are painful to unwind, so the coverage percentage "
        "should follow the migration curve rather than being set at 100% on day one. Azure "
        "Hybrid Benefit depends on Software Assurance the client may or may not hold - "
        "confirm it before the saving appears in a business case.")

    st.markdown("### Commitment term comparison")
    rows = []
    for c in ["none", "ri-1y", "ri-3y", "sp-1y", "sp-3y"]:
        pol = replace(sc.commercial, commitment=c,
                      commitment_coverage_pct=(0 if c == "none"
                                               else sc.commercial.commitment_coverage_pct))
        tbl = costing.compute_costs(res.sized, res.price_book, pol)
        rows.append({"Commitment": {"none": "Pay-as-you-go", "ri-1y": "RI 1 year",
                                    "ri-3y": "RI 3 year", "sp-1y": "Savings plan 1 year",
                                    "sp-3y": "Savings plan 3 year"}[c],
                     "Monthly cost": tbl[tbl["strategy"] != "Retire"]["monthly_cost"].sum()})
    cdf = pd.DataFrame(rows)
    base_payg = cdf.loc[cdf["Commitment"] == "Pay-as-you-go", "Monthly cost"].iloc[0]
    cdf["Saving vs PAYG"] = (base_payg - cdf["Monthly cost"]) / base_payg * 100
    st.dataframe(
        cdf.assign(**{"Monthly cost": cdf["Monthly cost"].map(lambda v: ui.money(v, cur)),
                      "Saving vs PAYG": cdf["Saving vs PAYG"].map(lambda v: f"{v:.1f}%")}),
        hide_index=True, width="stretch")

    # ---- the live feed itself ---------------------------------------------
    ui.section("Where these rates come from",
               "Worth opening when someone asks. Every rate is Microsoft's own published "
               "retail price, fetched from a public API a few seconds ago - not a "
               "spreadsheet someone maintained last quarter.")
    st.caption(
        "`https://prices.azure.com/api/retail/prices` (api-version 2023-01-01-preview). "
        "Unauthenticated. Cached locally for 24 hours so the app keeps working offline.")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Virtual machine rates** (per hour)")
        vm = res.price_book.vm.copy()
        used = set(res.sized["azure_sku"].unique())
        vm["in_plan"] = vm["arm_sku_name"].isin(used)
        vm = vm.sort_values(["in_plan", "linux_hr"], ascending=[False, True])
        st.dataframe(
            vm[["arm_sku_name", "linux_hr", "windows_hr", "win_licence_hr", "in_plan"]]
            .rename(columns={"arm_sku_name": "SKU", "linux_hr": "Linux",
                             "windows_hr": "Windows", "win_licence_hr": "Windows licence",
                             "in_plan": "Used in this plan"}).round(4),
            hide_index=True, width="stretch", height=340)
    with c2:
        st.markdown("**Managed disk rates** (per month)")
        st.dataframe(res.price_book.disk.rename(
            columns={"kind": "Disk type", "tier": "Tier", "price_month": "Monthly",
                     "price_per_10k_ops": "Per 10k operations"}).round(4),
            hide_index=True, width="stretch", height=340)

    st.markdown("**Other live rates**")
    st.dataframe(pd.DataFrame([
        {"Meter": "Internet egress (above the free 100 GB)",
         "Rate": f"{ui.money(res.price_book.egress_gb, cur, 4)} per GB"},
        {"Meter": "Azure Backup protected instance (per 500 GB block)",
         "Rate": f"{ui.money(res.price_book.backup['instance_month'], cur, 2)} per month"},
        {"Meter": "Azure Backup, SQL Server in an Azure VM",
         "Rate": f"{ui.money(res.price_book.backup['sql_instance_month'], cur, 2)} per month"},
        {"Meter": "Backup vault storage, LRS",
         "Rate": f"{ui.money(res.price_book.backup['lrs_gb_month'], cur, 4)} per GB/month"},
        {"Meter": "Backup vault storage, GRS",
         "Rate": f"{ui.money(res.price_book.backup['grs_gb_month'], cur, 4)} per GB/month"},
        {"Meter": "Azure Site Recovery, VM replicated to Azure",
         "Rate": f"{ui.money(res.price_book.asr_instance, cur, 2)} per instance/month "
                 "(free for the first 180 days when used for migration)"},
    ]), hide_index=True, width="stretch")

    if st.button("Force a refresh from the vendor API"):
        st.cache_data.clear()
        st.session_state.pop("_pipeline_token", None)
        st.session_state.pop("_mc_token", None)
        st.rerun()

# --------------------------------------------------------------------------
# Confidence -- the former Risk simulation page. A Monte Carlo over the
# programme is a statement about how much to trust the case above, not a
# destination of its own, so it ends up here rather than closing the Plan act.
# --------------------------------------------------------------------------
with tab_conf:
    st.caption("A single-point estimate is the least useful thing you can hand a steering "
               "committee. This runs the plan thousands of times with every uncertain input "
               "sampled from a three-point estimate, and reports the confidence bands - plus "
               "which uncertainty is actually driving the spread.")

    with st.expander("Uncertainty ranges", expanded=False):
        st.caption("Each driver is a PERT three-point estimate: optimistic, most likely, "
                   "pessimistic. The most likely value is the deterministic plan's assumption.")
        inp = sc.mc
        new_fields = {}
        fields = [f for f in montecarlo.DRIVER_LABELS if hasattr(inp, f)]
        for chunk in [fields[i:i + 2] for i in range(0, len(fields), 2)]:
            cols = st.columns(len(chunk) * 3)
            for i, f in enumerate(chunk):
                u = getattr(inp, f)
                label = montecarlo.DRIVER_LABELS[f]
                step = 0.05 if u.high <= 5 else (0.5 if u.high <= 100 else 500.0)
                lo = cols[i * 3].number_input(f"{label} - low", value=float(u.low),
                                              step=step, key=f"mc_{f}_lo")
                mo = cols[i * 3 + 1].number_input("most likely", value=float(u.mode),
                                                  step=step, key=f"mc_{f}_mo")
                hi = cols[i * 3 + 2].number_input("high", value=float(u.high),
                                                  step=step, key=f"mc_{f}_hi")
                if (lo, mo, hi) != (u.low, u.mode, u.high):
                    new_fields[f] = montecarlo.Uncertainty(lo, mo, hi)

        c1, c2, c3, c4 = st.columns(4)
        iters = c1.select_slider("Iterations", [1000, 2500, 5000, 10000, 25000, 50000],
                                 value=inp.iterations)
        seed = c2.number_input("Seed", 1, 10**6, inp.seed)
        budget = c3.number_input("Budget target", 0.0, 1e9, float(sc.budget_target), 100000.0)
        deadline = c4.number_input("Deadline (months)", 1.0, 120.0,
                                   float(sc.deadline_months), 1.0)

        if new_fields or iters != inp.iterations or seed != inp.seed:
            scenario.update(mc=replace(inp, iterations=int(iters), seed=int(seed), **new_fields))
            st.rerun()
        if budget != sc.budget_target or deadline != sc.deadline_months:
            scenario.update(budget_target=float(budget), deadline_months=float(deadline))
            st.rerun()

    with st.spinner(f"Running {sc.mc.iterations:,} iterations..."):
        sim = scenario.monte_carlo(res, sc)
    pct = montecarlo.percentiles(sim)
    st.session_state["mc_percentiles"] = pct.to_dict("records")

    # Named _q rather than p: this page already binds `p` to the commercial
    # policy in the Cost levers tab above.
    def _q(metric: str, q: int) -> float:
        row = pct[pct["metric"] == metric]
        return float(row[f"P{q}"].iloc[0]) if len(row) else 0.0

    ui.metric_row([
        ("Programme cost P50", ui.compact_money(_q("total_programme_cost", 50), cur), "median"),
        ("Programme cost P80", ui.compact_money(_q("total_programme_cost", 80), cur),
         f"+{(_q('total_programme_cost', 80) / max(_q('total_programme_cost', 50), 1) - 1) * 100:.0f}% "
         "contingency"),
        ("Duration P50", f"{_q('elapsed_months', 50):.1f} mo", "median"),
        ("Duration P80", f"{_q('elapsed_months', 80):.1f} mo", None),
        ("Azure run rate P80", f"{ui.compact_money(_q('azure_monthly_cost', 80), cur)}/mo", None),
    ])

    for line in montecarlo.confidence_statement(sim, sc.budget_target, sc.deadline_months):
        prob_ok = "Below 80% confidence" not in line and "not credible" not in line
        ui.note(line, "note" if prob_ok else "warn")

    ui.note(
        "<b>Never present the P50.</b> It is a coin flip, and a steering committee funded to "
        "the median spends the second half of the programme asking for more money. Quote the "
        "P80 and say plainly that it includes contingency - then show the tornado below, which "
        "names the one uncertainty worth spending money to narrow.", "warn")

    st.markdown("### Distributions")
    c1, c2 = st.columns(2)
    for col, (metric, title) in zip(
            [c1, c2],
            [("total_programme_cost", "Total programme cost"),
             ("elapsed_months", "Elapsed duration (months)")]):
        with col:
            vals = sim[metric]
            fig = go.Figure()
            fig.add_trace(go.Histogram(x=vals, nbinsx=60, marker_color=ui.PALETTE[0],
                                       opacity=0.85, name=title))
            for q, colour in [(50, ui.PALETTE[2]), (80, ui.PALETTE[1]), (95, ui.PALETTE[3])]:
                fig.add_vline(x=np.percentile(vals, q), line_dash="dash", line_color=colour,
                              annotation_text=f"P{q}", annotation_position="top")
            fig.update_layout(height=380, title=title, showlegend=False,
                              xaxis_title="", yaxis_title="Iterations")
            st.plotly_chart(fig, width="stretch")

    st.markdown("### Cost versus duration")
    samp = sim.sample(min(4000, len(sim)), random_state=1)
    fig = go.Figure(go.Scattergl(
        x=samp["elapsed_months"], y=samp["total_programme_cost"], mode="markers",
        marker=dict(size=4, color=samp["effort_multiplier"], colorscale="Blues",
                    showscale=True, colorbar=dict(title="Effort<br>multiplier")),
        name="Iterations"))
    fig.add_vline(x=sc.deadline_months, line_dash="dash", line_color=ui.PALETTE[3],
                  annotation_text="Deadline")
    fig.add_hline(y=sc.budget_target, line_dash="dash", line_color=ui.PALETTE[3],
                  annotation_text="Budget")
    fig.update_layout(height=430, xaxis_title="Elapsed months",
                      yaxis_title=f"Total programme cost ({cur})")
    st.plotly_chart(fig, width="stretch")
    inside = float(((sim["elapsed_months"] <= sc.deadline_months)
                    & (sim["total_programme_cost"] <= sc.budget_target)).mean() * 100)
    ui.note(f"<b>{inside:.0f}% of iterations land inside both the budget and the deadline.</b> "
            "The bottom-left quadrant is the only one that counts.",
            "note" if inside >= 60 else "warn")

    st.markdown("### What drives the spread")
    target = st.selectbox(
        "Outcome to analyse",
        ["total_programme_cost", "elapsed_months", "migration_cost", "year1_total"],
        format_func=lambda v: {"total_programme_cost": "Total programme cost",
                               "elapsed_months": "Elapsed duration",
                               "migration_cost": "One-off migration cost",
                               "year1_total": "Year 1 total cost"}[v])
    tor = montecarlo.tornado(sim, target)
    fig = go.Figure(go.Bar(
        x=tor["swing"], y=tor["driver"], orientation="h",
        marker_color=[ui.PALETTE[3] if v > 0 else ui.PALETTE[2] for v in tor["swing"]],
        text=[ui.compact_money(v, cur) if "cost" in target or "total" in target
              else f"{v:+.1f}" for v in tor["swing"]],
        textposition="auto"))
    fig.update_layout(height=440, title="Swing in the outcome between the driver's "
                                        "bottom and top quintile",
                      xaxis_title="Impact", yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig, width="stretch")

    st.dataframe(tor.round(3).rename(columns={
        "driver": "Driver", "correlation": "Rank correlation", "swing": "Swing",
        "abs_swing": "Absolute swing"}), hide_index=True, width="stretch")

    ui.note(
        f"<b>{tor.iloc[0]['driver']}</b> dominates the uncertainty. Narrowing that one range is "
        "worth more than reducing every other assumption combined - and unlike contingency, it "
        "is something the programme can actually act on. Tighten it with a pilot wave, a "
        "bandwidth test, or a proper bottom-up estimate on a representative sample.")

    st.markdown("### Funding recommendation")
    c1, c2 = st.columns(2)
    with c1:
        v = np.sort(sim["total_programme_cost"])
        fig = go.Figure(go.Scatter(x=v, y=np.arange(1, len(v) + 1) / len(v) * 100,
                                   mode="lines", line=dict(width=3, color=ui.PALETTE[0])))
        fig.add_vline(x=sc.budget_target, line_dash="dash", line_color=ui.PALETTE[3],
                      annotation_text="Budget")
        fig.add_hline(y=80, line_dash="dot", line_color="rgba(128,128,128,.6)",
                      annotation_text="80% confidence")
        fig.update_layout(height=400, title="Probability of landing at or below a cost",
                          xaxis_title=f"Total programme cost ({cur})",
                          yaxis_title="Confidence (%)")
        st.plotly_chart(fig, width="stretch")
    with c2:
        v = np.sort(sim["elapsed_months"])
        fig = go.Figure(go.Scatter(x=v, y=np.arange(1, len(v) + 1) / len(v) * 100,
                                   mode="lines", line=dict(width=3, color=ui.PALETTE[2])))
        fig.add_vline(x=sc.deadline_months, line_dash="dash", line_color=ui.PALETTE[3],
                      annotation_text="Deadline")
        fig.add_hline(y=80, line_dash="dot", line_color="rgba(128,128,128,.6)")
        fig.update_layout(height=400, title="Probability of finishing within a duration",
                          xaxis_title="Elapsed months", yaxis_title="Confidence (%)")
        st.plotly_chart(fig, width="stretch")

    st.dataframe(pd.DataFrame([
        {"Confidence": f"P{q}",
         "Programme cost": ui.money(np.percentile(sim["total_programme_cost"], q), cur),
         "Duration (months)": f"{np.percentile(sim['elapsed_months'], q):.1f}",
         "Contingency over P50":
             f"{(np.percentile(sim['total_programme_cost'], q) / np.percentile(sim['total_programme_cost'], 50) - 1) * 100:.0f}%"}
        for q in [50, 70, 80, 90, 95]]), hide_index=True, width="stretch")
    ui.note(
        "Fund to P80. P50 is a coin flip that the programme lands on budget, and every "
        "steering committee that funds the median spends the second half of the programme "
        "asking for more money.")

    with st.expander("Full percentile table and raw iterations", expanded=False):
        disp = pct.copy()
        label = {"elapsed_months": "Elapsed months", "migration_cost": "One-off migration cost",
                 "total_programme_cost": "Total programme cost",
                 "azure_monthly_cost": "Azure monthly run rate",
                 "year1_total": "Year 1 total", "rollbacks": "Failed cutovers"}
        disp["metric"] = disp["metric"].map(lambda m: label.get(m, m))
        st.dataframe(disp.round(1), hide_index=True, width="stretch")

        p80 = sim[sim["total_programme_cost"]
                  >= np.percentile(sim["total_programme_cost"], 79)].head(400).mean(
                      numeric_only=True)
        st.plotly_chart(ui.bar(pd.DataFrame([
            {"Component": "Labour", "Cost": p80["labour_cost"]},
            {"Component": "Rework from failed cutovers", "Cost": p80["rework_cost"]},
            {"Component": "Dual-run overlap", "Cost": p80["dual_run_cost"]},
            {"Component": "On-premises tail during migration", "Cost": p80["onprem_tail_cost"]},
        ]), "Component", "Cost", "P80 programme cost composition",
            orientation="h", height=300, text_fmt=",.0f"), width="stretch")
        ui.df_download(sim, "monte_carlo_iterations.csv", "Download all iterations")

# --------------------------------------------------------------------------
with tab_sens:
    st.markdown("### What would change the answer")
    st.caption("Each row varies one assumption and reports the NPV saving. If the sign flips, "
               "that assumption is load-bearing and needs evidence rather than a default.")

    base = ts["npv_saving"]
    rows = []
    variants = [
        ("VMware licence 40% lower", replace(res.onprem,
                                             vmware_cost_per_core_year=res.onprem.vmware_cost_per_core_year * 0.6), None),
        ("VMware renewal uplift of 0%", replace(res.onprem, vmware_renewal_uplift_pct=0.0), None),
        ("VMware renewal uplift of 100%", replace(res.onprem,
                                                  vmware_renewal_uplift_pct=100.0), None),
        ("No downtime cost attributed", replace(res.onprem, downtime_cost_per_hour=0.0), None),
        ("Azure run rate 25% higher", None,
         replace(sc.azure_profile,
                 azure_monthly_run=res.cost_summary["monthly_total"] * 1.25,
                 migration_one_off=res.effort_summary["migration_cost"])),
        ("Migration cost 50% higher", None,
         replace(sc.azure_profile,
                 azure_monthly_run=res.cost_summary["monthly_total"],
                 migration_one_off=res.effort_summary["migration_cost"] * 1.5)),
        ("No year 2+ optimisation", None,
         replace(sc.azure_profile,
                 azure_monthly_run=res.cost_summary["monthly_total"],
                 migration_one_off=res.effort_summary["migration_cost"],
                 year2plus_optimisation_pct=0.0)),
        ("No hardware refresh in the horizon",
         replace(res.onprem, years_into_refresh=0, hardware_refresh_years=10), None),
    ]
    base_az = replace(sc.azure_profile,
                      azure_monthly_run=res.cost_summary["monthly_total"],
                      migration_one_off=res.effort_summary["migration_cost"])
    for label, op_v, az_v in variants:
        t = tco.build_tco(op_v or res.onprem, az_v or base_az, sc.tco_inputs)
        s = tco.tco_summary(t, sc.tco_inputs)
        rows.append({"Assumption changed": label, "NPV saving": s["npv_saving"],
                     "Change vs base": s["npv_saving"] - base,
                     "Payback": f"{s['payback_years']:.1f} yr" if s["payback_years"]
                                else "beyond horizon"})
    sens = pd.DataFrame(rows).sort_values("Change vs base")

    fig = go.Figure(go.Bar(
        x=sens["Change vs base"], y=sens["Assumption changed"], orientation="h",
        marker_color=[ui.PALETTE[3] if v < 0 else ui.PALETTE[2]
                      for v in sens["Change vs base"]],
        text=[ui.compact_money(v, cur) for v in sens["Change vs base"]], textposition="auto"))
    fig.update_layout(height=400, title="Impact on NPV saving",
                      xaxis_title=f"Change in NPV saving ({cur})",
                      yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig, width="stretch")

    disp = sens.copy()
    disp["NPV saving"] = disp["NPV saving"].map(lambda v: ui.money(v, cur))
    disp["Change vs base"] = disp["Change vs base"].map(lambda v: ui.money(v, cur))
    st.dataframe(disp, hide_index=True, width="stretch")

    flips = sens[sens["NPV saving"] < 0] if sens["NPV saving"].dtype != object else pd.DataFrame()
    if len(flips):
        ui.note(
            "<b>At least one single assumption change turns the saving negative.</b> The case "
            "is not robust. Get evidence for those assumptions before presenting it - "
            "particularly the VMware renewal position, which is the one the client can "
            "actually influence by negotiating.", "warn")
    else:
        ui.note(
            "No single assumption change reverses the conclusion, which is the test a business "
            "case has to pass. Present the range, not the point estimate.")
