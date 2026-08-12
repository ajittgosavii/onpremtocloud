"""Migration tooling market: alternatives to Azure Migrate and when each wins."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core import assessment, scenario, tools_market as tm, ui

sc = scenario.get_scenario()
res = scenario.current()
cur = sc.commercial.currency

eol_share = float(res.estate["os_eol"].mean() * 100)
blocked_share = float((res.sized["readiness"] == assessment.NOT_READY).mean() * 100)
n_vms = len(res.estate)

ui.page_header(
    "Migration tooling",
    "Azure Migrate is free and should carry the bulk of this estate. It is not, however, the "
    "whole answer - and real programmes run a stack, not a single tool. This page ranks the "
    "market against what this client actually needs, and prices the incremental licence cost "
    "of each option at this estate's scale.",
)

c1, c2 = st.columns([1, 2])
scen = c1.selectbox("What is the driving requirement?", tm.SCENARIOS)
custom = c2.toggle("Set my own dimension weights", False)

ui.takeaway(
    "Real programmes run a stack, not a single tool. The <b>Recommended stack</b> tab is "
    "derived from this client's own inventory - the share on an end-of-life OS, the share "
    "blocked from agentless replication, the database count - so it is a recommendation about "
    "them, not a generic vendor list. And note the totals: tooling is almost never the "
    "deciding cost next to labour and a slipped exit date.")

tab_rank, tab_stack, tab_cost, tab_all = st.tabs(
    ["Ranked for your scenario", "Recommended stack", "Tooling cost", "Full market"])

# --------------------------------------------------------------------------
with tab_rank:

    weights = None
    if custom:
        weights = {}
        keys = list(tm.DIMENSIONS)
        for chunk in [keys[i:i + 4] for i in range(0, len(keys), 4)]:
            cols = st.columns(len(chunk))
            for col, k in zip(cols, chunk):
                weights[k] = col.slider(tm.DIMENSIONS[k], 0.0, 3.0, 1.0, 0.1, key=f"tw_{k}")

    ranked = tm.rank_tools(scen, weights)

    fig = go.Figure(go.Bar(
        x=ranked["fit_score"], y=ranked["tool"], orientation="h",
        marker_color=[ui.PALETTE[2] if i == 0 else
                      (ui.PALETTE[0] if i < 4 else ui.PALETTE[7])
                      for i in range(len(ranked))],
        text=[f"{v:.0f}" for v in ranked["fit_score"]], textposition="auto"))
    fig.update_layout(height=560, title=f"Tool fit for: {scen}",
                      xaxis_title="Weighted fit score (0-100)",
                      yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig, width="stretch")

    top = ranked.iloc[0]
    ui.note(f"<b>Best fit: {top['tool']}</b> ({top['vendor']}) -- {top['best_for']}<br><br>"
            f"<i>Limits:</i> {top['limits']}")

    st.markdown("### Capability scores across the market")
    heat = ranked.set_index("tool")[list(tm.DIMENSIONS)]
    heat.columns = [tm.DIMENSIONS[c] for c in heat.columns]
    fig = px.imshow(heat, color_continuous_scale=ui.SEQUENTIAL, aspect="auto",
                    labels=dict(color="Score 1-5"), text_auto=True)
    fig.update_layout(height=600, xaxis_title="", yaxis_title="",
                      xaxis=dict(side="top", tickangle=-40))
    st.plotly_chart(fig, width="stretch")

# --------------------------------------------------------------------------
with tab_stack:
    st.markdown("### The stack this estate actually needs")
    st.caption(
        f"Derived from your inventory: {n_vms:,} VMs, {eol_share:.0f}% on an end-of-life guest "
        f"OS, {blocked_share:.1f}% blocked from agentless replication, "
        f"{res.estate_summary['db_vms']} VMs carrying a database engine.")

    stack = tm.recommended_stack(scen, n_vms, eol_share, blocked_share)
    for i, s in enumerate(stack, 1):
        with st.container(border=True):
            c1, c2 = st.columns([1, 3])
            c1.markdown(f"**{i}. {s['role']}**")
            c1.markdown(f"`{s['tool']}`")
            c2.markdown(s["why"])

    ui.note(
        "Nobody buys all of these. The point is that a plan naming only Azure Migrate has "
        "left out dependency mapping, database migration and post-migration optimisation - "
        "and those gaps show up as schedule, not as a line item.")

    st.markdown("### Cost of the recommended stack")
    rows = []
    for s in stack:
        est = tm.tooling_cost_estimate(n_vms, s["tool"])
        rows.append({"Role": s["role"], "Tool": s["tool"],
                     "Low": est["low"], "High": est["high"],
                     "Per VM": f"{est['per_vm_low']:.0f}-{est['per_vm_high']:.0f}"
                     if est["per_vm_high"] else "no incremental cost"})
    df = pd.DataFrame(rows)
    total_lo, total_hi = df["Low"].sum(), df["High"].sum()
    ui.metric_row([
        ("Stack cost, low", ui.compact_money(total_lo, cur), None),
        ("Stack cost, high", ui.compact_money(total_hi, cur), None),
        ("As % of migration cost",
         f"{total_hi / max(res.effort_summary['migration_cost'], 1) * 100:.0f}%",
         "at the high end"),
        ("Per VM", f"{ui.money(total_hi / max(n_vms, 1), cur)}", "high end"),
    ])
    disp = df.copy()
    disp["Low"] = disp["Low"].map(lambda v: ui.money(v, cur))
    disp["High"] = disp["High"].map(lambda v: ui.money(v, cur))
    st.dataframe(disp, hide_index=True, width="stretch")

    if st.button("Apply the high-end tooling cost to the effort model"):
        from dataclasses import replace
        scenario.update(effort=replace(sc.effort,
                                       tooling_cost_per_vm=float(total_hi / max(n_vms, 1))))
        st.success("Applied. The Complexity & effort page and every downstream figure now "
                   "include it.")
        st.rerun()

# --------------------------------------------------------------------------
with tab_cost:
    st.markdown("### Incremental licence cost at this estate's scale")
    st.caption("Order-of-magnitude, based on published list pricing and the discounts commonly "
               "available at 500+ VMs. Zero means either free or already owned.")

    rows = [tm.tooling_cost_estimate(n_vms, t) for t in tm.tools_frame()["tool"]]
    cost = pd.DataFrame(rows).sort_values("high", ascending=False)

    fig = go.Figure()
    fig.add_trace(go.Bar(x=cost["low"], y=cost["tool"], orientation="h",
                         name="Low estimate", marker_color=ui.PALETTE[2]))
    fig.add_trace(go.Bar(x=cost["high"] - cost["low"], y=cost["tool"], orientation="h",
                         name="Range to high estimate", marker_color=ui.PALETTE[1]))
    fig.update_layout(barmode="stack", height=560,
                      title=f"Tooling cost for {n_vms:,} VMs",
                      xaxis_title=cur, yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig, width="stretch")

    disp = cost.copy()
    disp["low"] = disp["low"].map(lambda v: ui.money(v, cur))
    disp["high"] = disp["high"].map(lambda v: ui.money(v, cur))
    st.dataframe(disp[["tool", "per_vm_low", "per_vm_high", "low", "high"]].rename(columns={
        "tool": "Tool", "per_vm_low": "Per VM (low)", "per_vm_high": "Per VM (high)",
        "low": "Estate total (low)", "high": "Estate total (high)"}),
        hide_index=True, width="stretch")

    ui.note(
        "Tooling is rarely the deciding cost. A commercial replication product at "
        f"{ui.compact_money(cost['high'].max(), cur)} looks expensive next to free - but it is "
        "small against the labour bill, and smaller still against a slipped data centre exit. "
        "Choose on capability and risk, then negotiate.")

# --------------------------------------------------------------------------
with tab_all:
    tools = tm.tools_frame()
    cats = st.multiselect("Category", sorted(tools["category"].unique()))
    view = tools[tools["category"].isin(cats)] if cats else tools

    for _, r in view.iterrows():
        with st.expander(f"{r['tool']}  |  {r['vendor']}  |  {r['category']}"):
            st.markdown(f"**Licence.** {r['licence']}")
            st.markdown(f"**Best for.** {r['best_for']}")
            st.warning(f"**Limits.** {r['limits']}")
            st.info(f"**Use when:** {r['use_when']}")
            scores = pd.DataFrame([{tm.DIMENSIONS[k]: r[k] for k in tm.DIMENSIONS}])
            st.dataframe(scores, hide_index=True, width="stretch")
