"""Complexity, effort and migration cost model."""

from dataclasses import replace

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core import complexity, scenario, ui

sc = scenario.get_scenario()

ui.page_header(
    "Complexity & effort",
    "Migration cost is labour, and labour follows complexity. Every VM is scored on thirteen "
    "weighted factors, and the weights are on this page so a client can argue with them - "
    "which is the point. A model nobody can challenge is a model nobody believes.",
)

# --------------------------------------------------------------------------
with st.expander("Effort model", expanded=True):
    m = sc.effort
    c1, c2, c3, c4 = st.columns(4)
    rate = c1.number_input("Blended rate per hour", 20.0, 400.0,
                           float(m.blended_rate_per_hour), 1.0)
    hours = c2.slider("Productive hours per person-day", 3.0, 8.0,
                      float(m.productive_hours_per_day), 0.5,
                      help="Eight is a fantasy. Six is realistic for engineering work with "
                           "meetings, handovers and change approvals in the mix.")
    team = c3.number_input("Migration team size (FTE)", 1.0, 120.0, float(m.team_size_fte), 0.5)
    cont = c4.slider("Contingency (%)", 0, 60, int(m.contingency_pct))

    c5, c6, c7, c8 = st.columns(4)
    tests = c5.slider("Test cycles per workload", 1, 5, int(m.test_cycles),
                      help="Each cycle beyond the first adds roughly 18% to build effort.")
    tooling = c6.number_input("Third-party tooling cost per VM", 0.0, 2000.0,
                             float(m.tooling_cost_per_vm), 10.0,
                             help="Zero if the plan uses Azure Migrate only. See the "
                                  "Migration tooling page for licensed alternatives.")
    streams = c7.number_input("Parallel migration streams", 1, 30,
                              int(m.parallel_migration_streams))
    prog = c8.number_input("Programme overhead (FTE)", 0.0, 30.0,
                           float(m.programme_overhead_fte), 0.5,
                           help="Programme manager, architects, comms, service management - "
                                "roles that run for the whole engagement.")

    new = replace(m, blended_rate_per_hour=rate, productive_hours_per_day=hours,
                  team_size_fte=team, contingency_pct=float(cont), test_cycles=int(tests),
                  tooling_cost_per_vm=tooling, parallel_migration_streams=int(streams),
                  programme_overhead_fte=prog)
    if new != m:
        scenario.update(effort=new)
        st.rerun()

    st.markdown("#### Factor weights")
    st.caption("Relative importance of each factor in the complexity index. Set one to zero "
               "to remove it entirely.")
    keys = list(complexity.FACTOR_LABELS)
    weights = dict(sc.effort.weights)
    changed = False
    for chunk in [keys[i:i + 5] for i in range(0, len(keys), 5)]:
        cols = st.columns(len(chunk))
        for col, k in zip(cols, chunk):
            v = col.slider(complexity.FACTOR_LABELS[k], 0.0, 3.0,
                           float(weights.get(k, 1.0)), 0.1, key=f"w_{k}")
            if abs(v - weights.get(k, 1.0)) > 1e-9:
                weights[k] = v
                changed = True
    if changed:
        scenario.update(effort=replace(sc.effort, weights=weights))
        st.rerun()

res = scenario.current()
scored = res.sized
es = res.effort_summary
cur = sc.commercial.currency

ui.metric_row([
    ("Total effort", f"{es['total_effort_hours']:,.0f} h",
     f"{es['total_effort_person_days']:,.0f} person-days"),
    ("Migration cost", ui.compact_money(es["migration_cost"], cur),
     f"{ui.money(es['cost_per_vm'], cur)} per VM"),
    ("Mean complexity", f"{es['mean_complexity']:.1f}/100", None),
    ("At current team capacity", f"{es['elapsed_months_at_capacity']:.1f} months",
     f"{sc.effort.team_size_fte:g} FTE"),
    ("Expected failed cutovers", f"{es['expected_failed_cutovers']:.0f}",
     f"{es['expected_failed_cutovers'] / max(len(scored), 1) * 100:.1f}% of migrations"),
])

ui.takeaway(
    "Use the <b>Per-VM</b> tab when a client challenges a number. Pick any server they name "
    "and the model shows exactly which factors scored it and what each contributed. An "
    "estimate that can be interrogated down to a single VM is defensible; a blended "
    "cost-per-VM from a benchmark deck is not.")

tab_dist, tab_drivers, tab_hot, tab_detail = st.tabs(
    ["Distribution", "What drives complexity", "Hot spots", "Per-VM"])

# --------------------------------------------------------------------------
with tab_dist:
    c1, c2 = st.columns([1, 1.3])
    with c1:
        b = res.complexity_bands
        st.plotly_chart(ui.bar(b, "complexity_band", "vms", "VMs by complexity band",
                               colour_map=ui.BAND_COLOURS, height=340, text_fmt=",.0f"),
                        width="stretch")
    with c2:
        fig = go.Figure(go.Histogram(x=scored["complexity"], nbinsx=45,
                                     marker_color=ui.PALETTE[0]))
        for edge, name in zip(list(sc.effort.band_edges)[1:-1], complexity.BAND_NAMES[1:]):
            fig.add_vline(x=edge, line_dash="dash", line_color="rgba(128,128,128,.6)",
                          annotation_text=name, annotation_position="top")
        fig.update_layout(height=340, title="Complexity index distribution",
                          xaxis_title="Complexity (0-100)", yaxis_title="VMs")
        st.plotly_chart(fig, width="stretch")

    bd = res.complexity_bands.copy()
    bd["migration_cost"] = bd["migration_cost"].map(lambda v: ui.money(v, cur))
    bd["effort_hours"] = bd["effort_hours"].map(lambda v: f"{v:,.0f}")
    bd["share_pct"] = bd["share_pct"].map(lambda v: f"{v:.1f}%")
    bd["mean_complexity"] = bd["mean_complexity"].map(lambda v: f"{v:.1f}")
    st.dataframe(bd.rename(columns={"complexity_band": "Band", "vms": "VMs",
                                    "effort_hours": "Effort (h)",
                                    "migration_cost": "Migration cost",
                                    "mean_complexity": "Mean complexity",
                                    "share_pct": "Share"}),
                 hide_index=True, width="stretch")

    st.markdown("### Effort by strategy")
    g = (scored.groupby("strategy").agg(
        vms=("vm_name", "count"), hours=("effort_hours", "sum"),
        cost=("migration_cost", "sum"), mean_cx=("complexity", "mean")).reset_index())
    g["hours_per_vm"] = g["hours"] / g["vms"]
    fig = px.bar(g, x="strategy", y="hours", color="strategy",
                 color_discrete_map=ui.STRATEGY_COLOURS, title="Total effort hours by strategy")
    fig.update_layout(height=340, showlegend=False, xaxis_title="", yaxis_title="Hours")
    st.plotly_chart(fig, width="stretch")
    st.dataframe(g.round(1).rename(columns={
        "strategy": "Strategy", "vms": "VMs", "hours": "Effort (h)", "cost": "Cost",
        "mean_cx": "Mean complexity", "hours_per_vm": "Hours per VM"}),
        hide_index=True, width="stretch")

# --------------------------------------------------------------------------
with tab_drivers:
    fc = res.factor_contribution
    fig = go.Figure(go.Bar(
        x=fc["contribution_pct"], y=fc["factor"], orientation="h",
        marker_color=ui.PALETTE[0],
        text=[f"{v:.1f}%" for v in fc["contribution_pct"]], textposition="auto"))
    fig.update_layout(height=430, title="Share of portfolio complexity by factor",
                      xaxis_title="% of total complexity", yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig, width="stretch")

    st.dataframe(fc.round(2).rename(columns={
        "factor": "Factor", "mean_score": "Mean score (0-10)", "weight": "Weight",
        "contribution": "Weighted contribution", "contribution_pct": "% of total"}),
        hide_index=True, width="stretch")

    top = fc.iloc[0]
    ui.note(
        f"<b>{top['factor']}</b> is the single largest contributor at "
        f"{top['contribution_pct']:.0f}% of portfolio complexity. If you want to reduce "
        "programme cost, that is where to attack it - reducing complexity is far cheaper than "
        "adding engineers to absorb it.")

    st.markdown("### Complexity by grouping")
    dim = st.selectbox("Group by", ["environment", "criticality", "tier", "strategy",
                                    "os_family", "app_name", "cluster"], key="cx_dim")
    g = (scored.groupby(dim).agg(vms=("vm_name", "count"),
                                 mean_cx=("complexity", "mean"),
                                 hours=("effort_hours", "sum"))
         .reset_index().sort_values("mean_cx", ascending=False))
    fig = px.bar(g.head(20), x=dim, y="mean_cx", color="mean_cx",
                 color_continuous_scale=ui.SEQUENTIAL, title=f"Mean complexity by {dim}")
    fig.update_layout(height=340, xaxis_title="", yaxis_title="Mean complexity",
                      coloraxis_showscale=False)
    st.plotly_chart(fig, width="stretch")

# --------------------------------------------------------------------------
with tab_hot:
    st.markdown("### The workloads that will consume the programme")
    hot = scored.nlargest(30, "complexity")[
        ["vm_name", "app_name", "environment", "criticality", "strategy", "db_engine",
         "complexity", "complexity_band", "effort_hours", "migration_cost",
         "cutover_failure_risk"]].copy()
    hot["cutover_failure_risk"] = (hot["cutover_failure_risk"] * 100).round(1)
    st.dataframe(hot.round(1).rename(columns={
        "cutover_failure_risk": "Cutover risk %"}),
        hide_index=True, width="stretch", height=420)

    st.markdown("### Applications by total effort")
    ag = (scored.groupby("app_name").agg(
        vms=("vm_name", "count"), hours=("effort_hours", "sum"),
        cost=("migration_cost", "sum"), mean_cx=("complexity", "mean"),
        risk=("cutover_failure_risk", "sum")).reset_index()
        .sort_values("hours", ascending=False).head(25))
    fig = px.scatter(ag, x="vms", y="mean_cx", size="hours", color="cost",
                     hover_name="app_name", color_continuous_scale=ui.SEQUENTIAL,
                     title="Applications: size vs complexity (bubble = effort hours)")
    fig.update_layout(height=430, xaxis_title="VMs in the application",
                      yaxis_title="Mean complexity")
    st.plotly_chart(fig, width="stretch")
    ui.note(
        "Top-right is where programmes fail: large applications that are also complex. Those "
        "need their own move group, their own rehearsal and their own rollback plan - not a "
        "slot in a standard wave.")

# --------------------------------------------------------------------------
with tab_detail:
    pick = st.selectbox("VM", sorted(scored["vm_name"].unique()), key="cx_vm")
    row = scored[scored["vm_name"] == pick].iloc[0]

    c1, c2 = st.columns([1, 1.4])
    with c1:
        st.metric("Complexity", f"{row['complexity']:.1f}/100", row["complexity_band"])
        st.metric("Effort", f"{row['effort_hours']:.1f} h",
                  f"{row['effort_days']:.1f} person-days")
        st.metric("Migration cost", ui.money(row["migration_cost"], cur))
        st.metric("Cutover failure risk", f"{row['cutover_failure_risk'] * 100:.1f}%")
    with c2:
        vals = [(complexity.FACTOR_LABELS[k], float(row[f"cx_{k}"]),
                 sc.effort.weights.get(k, 0))
                for k in complexity.FACTOR_LABELS if f"cx_{k}" in row]
        fdf = pd.DataFrame(vals, columns=["factor", "score", "weight"])
        fdf["weighted"] = fdf["score"] * fdf["weight"]
        fdf = fdf.sort_values("weighted", ascending=False)
        fig = go.Figure(go.Bar(x=fdf["weighted"], y=fdf["factor"], orientation="h",
                               marker_color=ui.PALETTE[0],
                               text=[f"{s:.1f} x {w:.1f}"
                                     for s, w in zip(fdf["score"], fdf["weight"])],
                               textposition="auto"))
        fig.update_layout(height=430, title=f"Complexity contributions for {pick}",
                          xaxis_title="Weighted score", yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, width="stretch")
