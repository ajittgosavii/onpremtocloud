"""Business case: staying on VMware versus migrating to Azure."""

from __future__ import annotations

from dataclasses import replace

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import scenario, tco, ui

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

tab_cash, tab_onprem, tab_azure, tab_sens = st.tabs(
    ["Cash flow", "Current-state cost base", "Azure cost base", "Sensitivity"])

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
