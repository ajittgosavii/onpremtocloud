"""Wave planning and schedule simulation."""

from dataclasses import replace

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core import scenario, ui, waves

sc = scenario.get_scenario()

ui.page_header(
    "Wave plan & timeline",
    "Waves are built application-first, then sequenced up a risk ladder from development to "
    "Tier 0 production. Each wave's duration is the greater of two independent constraints - "
    "the bytes the link can carry, and the hours the team has. Naming which one binds is the "
    "difference between a plan and a wish.",
)

# --------------------------------------------------------------------------
with st.expander("Wave and capacity assumptions", expanded=True):
    w = sc.wave_plan
    c1, c2, c3, c4 = st.columns(4)
    n_waves = c1.number_input("Target number of waves", 2, 40, int(w.target_waves))
    max_vms = c2.number_input("Max VMs per wave", 5, 500, int(w.max_vms_per_wave))
    pilot = c3.toggle("Run a pilot wave first", w.pilot_wave)
    pilot_size = c4.number_input("Pilot size (VMs)", 3, 80, int(w.pilot_size),
                                 disabled=not pilot)

    c5, c6, c7, c8 = st.columns(4)
    bw = c5.number_input("Link bandwidth (Mbps)", 10.0, 100000.0,
                         float(w.bandwidth_mbps), 50.0)
    share = c6.slider("Share available for migration (%)", 5, 100,
                      int(w.bandwidth_available_pct),
                      help="You cannot have the whole link. Production traffic, backups and "
                           "replication all compete for it.")
    eff = c7.slider("Realised WAN efficiency (%)", 20, 100, int(w.wan_efficiency_pct),
                    help="Latency, TCP window behaviour, encryption and protocol overhead. "
                         "75% is generous over a long-haul link.")
    window = c8.slider("Replication hours per day", 4, 24,
                       int(w.replication_window_hours_per_day),
                       help="24 means replication runs continuously. Lower it if replication "
                            "must yield to the backup window.")

    c9, c10, c11, c12 = st.columns(4)
    streams = c9.number_input("Parallel cutover streams", 1, 20, int(w.parallel_streams))
    team_hours = c10.number_input("Team hours available per day", 8.0, 500.0,
                                  float(w.team_hours_per_day), 4.0,
                                  help="Squads x engineers x productive hours.")
    gap = c11.number_input("Stabilisation days between waves", 0.0, 30.0,
                           float(w.days_between_waves), 1.0)
    freeze = c12.number_input("Change-freeze weeks", 0, 12, int(w.freeze_periods),
                              help="Year-end, quarter-end or peak-trading freezes.")

    concurrent = st.slider(
        "Max concurrent replications (tool limit)", 50, 1000,
        int(w.max_concurrent_replications), 50,
        help="Azure Migrate agentless allows 300 per appliance, or 500 with a scale-out "
             "appliance. The real ceiling is 56 disks in flight per appliance.")

    start = st.date_input("Programme start date", pd.Timestamp(sc.start_date))

    new = replace(w, target_waves=int(n_waves), max_vms_per_wave=int(max_vms),
                  pilot_wave=pilot, pilot_size=int(pilot_size), bandwidth_mbps=float(bw),
                  bandwidth_available_pct=float(share), wan_efficiency_pct=float(eff),
                  replication_window_hours_per_day=float(window),
                  parallel_streams=int(streams), team_hours_per_day=float(team_hours),
                  days_between_waves=float(gap), freeze_periods=int(freeze),
                  max_concurrent_replications=int(concurrent))
    if new != w or str(start) != sc.start_date:
        scenario.update(wave_plan=new, start_date=str(start))
        st.rerun()

res = scenario.current()
sched = res.schedule
ss = res.schedule_summary
cur = sc.commercial.currency

if sched.empty:
    st.warning("No VMs are scheduled to migrate under the current disposition.")
    st.stop()

usable = (sc.wave_plan.bandwidth_mbps * sc.wave_plan.bandwidth_available_pct / 100
          * sc.wave_plan.wan_efficiency_pct / 100)

ui.metric_row([
    ("Waves", f"{ss['waves']}", f"{ss['vms_migrating']:,} VMs"),
    ("Elapsed duration", f"{ss['elapsed_months']:.1f} months", f"{ss['elapsed_days']} days"),
    ("Go-live", ss["go_live"].strftime("%d %b %Y"), None),
    ("Data to move", f"{ss['data_tib']:,.1f} TiB",
     f"{usable:,.0f} Mbps usable"),
    ("Bandwidth-bound waves", f"{ss['bandwidth_bound_waves']} of {ss['waves']}",
     f"{ss['capacity_bound_waves']} capacity-bound"),
])

if ss["bandwidth_bound_waves"] > 0:
    ui.note(
        f"<b>{ss['bandwidth_bound_waves']} of {ss['waves']} waves are limited by replication "
        "bandwidth, not by people.</b> Adding engineers to those waves changes nothing. What "
        "moves them is more bandwidth, a longer replication window, or taking bulk data off "
        "the wire entirely.", "warn")
else:
    ui.note(
        "Every wave is limited by engineering capacity rather than bandwidth. Adding parallel "
        "streams or team hours will compress the schedule; more bandwidth will not.")

st.markdown(f"**Seeding assessment.** {waves.offline_seed_advice(ss['data_tib'], sc.wave_plan)}")

ui.takeaway(
    "The column to point at is <b>Bound by</b>. A wave limited by replication bandwidth will "
    "not go faster if you add engineers, and a wave limited by engineering capacity will not "
    "go faster if you buy a bigger circuit. Most plans fail because they spend money on the "
    "wrong one of those two. The <b>Bandwidth sensitivity</b> tab shows the point past which "
    "more link speed buys nothing at all.")

tab_gantt, tab_waves, tab_bw, tab_content = st.tabs(
    ["Timeline", "Wave detail", "Bandwidth sensitivity", "Wave contents"])

# --------------------------------------------------------------------------
with tab_gantt:
    g = sched.copy()
    g["Wave"] = g["wave_name"]
    fig = px.timeline(g, x_start="start", x_end="end", y="Wave",
                      color="binding_constraint",
                      color_discrete_map={"Replication bandwidth": ui.PALETTE[1],
                                          "Engineering capacity": ui.PALETTE[0]},
                      hover_data=["vms", "data_tib", "duration_days"],
                      title="Migration wave timeline")
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(height=90 + 42 * len(g), xaxis_title="", yaxis_title="")
    st.plotly_chart(fig, width="stretch")

    c1, c2 = st.columns(2)
    with c1:
        cum = sched.copy()
        cum["cum_vms"] = cum["vms"].cumsum()
        cum["cum_tib"] = cum["data_tib"].cumsum()
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=cum["end"], y=cum["cum_vms"], mode="lines+markers",
                                 name="VMs migrated", line=dict(width=3, color=ui.PALETTE[0])))
        fig.update_layout(height=330, title="Migration burn-up",
                          xaxis_title="", yaxis_title="Cumulative VMs migrated")
        st.plotly_chart(fig, width="stretch")
    with c2:
        stack = sched.melt(id_vars=["wave_name"],
                           value_vars=["replication_days", "engineering_days", "cutover_days"],
                           var_name="component", value_name="days")
        stack["component"] = stack["component"].map({
            "replication_days": "Replication", "engineering_days": "Engineering",
            "cutover_days": "Cutover windows"})
        fig = px.bar(stack, x="wave_name", y="days", color="component", barmode="group",
                     color_discrete_sequence=ui.PALETTE,
                     title="What sets each wave's duration")
        fig.update_layout(height=330, xaxis_title="", yaxis_title="Days")
        st.plotly_chart(fig, width="stretch")

# --------------------------------------------------------------------------
with tab_waves:
    disp = sched.copy()
    disp["start"] = disp["start"].dt.strftime("%d %b %Y")
    disp["end"] = disp["end"].dt.strftime("%d %b %Y")
    disp["migration_cost"] = disp["migration_cost"].map(lambda v: ui.compact_money(v, cur))
    disp["azure_monthly_cost"] = disp["azure_monthly_cost"].map(
        lambda v: ui.compact_money(v, cur))
    for c in ["data_tib", "mean_complexity", "duration_days", "seed_days", "delta_days",
              "replication_days", "engineering_days", "expected_rollbacks"]:
        disp[c] = disp[c].round(1)
    st.dataframe(disp[[
        "wave_name", "vms", "applications", "prod_vms", "data_tib", "mean_complexity",
        "seed_days", "delta_days", "replication_days", "engineering_days", "cutover_days",
        "duration_days", "binding_constraint", "start", "end", "migration_cost",
        "azure_monthly_cost", "expected_rollbacks"]].rename(columns={
            "wave_name": "Wave", "vms": "VMs", "applications": "Apps",
            "prod_vms": "Prod VMs", "data_tib": "TiB", "mean_complexity": "Complexity",
            "seed_days": "Seed d", "delta_days": "Delta d", "replication_days": "Repl d",
            "engineering_days": "Eng d", "cutover_days": "Cutover d",
            "duration_days": "Duration d", "binding_constraint": "Bound by",
            "start": "Start", "end": "End", "migration_cost": "Migration cost",
            "azure_monthly_cost": "Azure/mo", "expected_rollbacks": "Exp. rollbacks"}),
        hide_index=True, width="stretch")
    ui.df_download(sched, "wave_plan.csv")

    c1, c2 = st.columns(2)
    with c1:
        fig = px.bar(sched, x="wave_name", y="data_tib", color="binding_constraint",
                     color_discrete_map={"Replication bandwidth": ui.PALETTE[1],
                                         "Engineering capacity": ui.PALETTE[0]},
                     title="Data volume per wave")
        fig.update_layout(height=330, xaxis_title="", yaxis_title="TiB")
        st.plotly_chart(fig, width="stretch")
    with c2:
        fig = px.bar(sched, x="wave_name", y="expected_rollbacks",
                     color="mean_complexity", color_continuous_scale=ui.SEQUENTIAL,
                     title="Expected failed cutovers per wave")
        fig.update_layout(height=330, xaxis_title="", yaxis_title="Expected rollbacks",
                          coloraxis_showscale=False)
        st.plotly_chart(fig, width="stretch")

# --------------------------------------------------------------------------
with tab_bw:
    st.markdown("### How the schedule responds to link speed")
    st.caption("The most-asked question in every migration planning workshop, answered "
               "against this estate rather than in the abstract.")
    curve = waves.bandwidth_curve(res.sized, sc.wave_plan)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=curve["bandwidth_mbps"], y=curve["elapsed_months"],
                             mode="lines+markers", line=dict(width=3, color=ui.PALETTE[0]),
                             name="Elapsed months"))
    fig.add_vline(x=sc.wave_plan.bandwidth_mbps, line_dash="dash",
                  line_color="rgba(180,73,95,.7)", annotation_text="Current link")
    fig.update_layout(height=380, title="Programme duration vs available bandwidth",
                      xaxis_title="Link bandwidth (Mbps, log scale)",
                      yaxis_title="Elapsed months", xaxis_type="log")
    st.plotly_chart(fig, width="stretch")

    st.dataframe(curve.round(2).rename(columns={
        "bandwidth_mbps": "Link (Mbps)", "elapsed_months": "Elapsed months",
        "bandwidth_bound_waves": "Bandwidth-bound waves"}),
        hide_index=True, width="stretch")

    knee = curve[curve["bandwidth_bound_waves"] == 0]
    if len(knee):
        k = knee.iloc[0]["bandwidth_mbps"]
        ui.note(
            f"The curve flattens at about <b>{k:,.0f} Mbps</b>. Beyond that, every wave is "
            "limited by engineering capacity, so more bandwidth buys nothing. That is the "
            "number to take to the network team - and the point at which further budget "
            "belongs on people rather than circuits.")

# --------------------------------------------------------------------------
with tab_content:
    pick = st.selectbox("Wave", sorted(sched["wave_name"].unique()))
    wdf = res.sized[res.sized["wave_name"] == pick]
    st.caption(f"{len(wdf):,} VMs across {wdf['app_name'].nunique()} applications, "
               f"{wdf['used_gib'].sum() / 1024:,.1f} TiB")

    c1, c2, c3 = st.columns(3)
    with c1:
        e = wdf["environment"].value_counts().reset_index()
        e.columns = ["environment", "vms"]
        st.plotly_chart(ui.bar(e, "environment", "vms", "Environment", height=280),
                        width="stretch")
    with c2:
        s = wdf["strategy"].value_counts().reset_index()
        s.columns = ["strategy", "vms"]
        st.plotly_chart(ui.bar(s, "strategy", "vms", "Strategy",
                               colour_map=ui.STRATEGY_COLOURS, height=280),
                        width="stretch")
    with c3:
        b = wdf["complexity_band"].value_counts().reset_index()
        b.columns = ["band", "vms"]
        st.plotly_chart(ui.bar(b, "band", "vms", "Complexity",
                               colour_map=ui.BAND_COLOURS, height=280),
                        width="stretch")

    st.dataframe(wdf[["vm_name", "app_name", "environment", "criticality", "strategy",
                      "azure_sku", "used_gib", "daily_churn_pct", "complexity",
                      "cutover_failure_risk"]].round(2),
                 hide_index=True, width="stretch", height=400)
