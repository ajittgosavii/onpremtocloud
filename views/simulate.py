"""Monte Carlo simulation of programme cost, duration and risk."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import montecarlo, scenario, ui

sc = scenario.get_scenario()
res = scenario.current()
cur = sc.commercial.currency

ui.page_header(
    "Risk simulation",
    "A single-point estimate is the least useful thing you can hand a steering committee. "
    "This runs the plan thousands of times with every uncertain input sampled from a "
    "three-point estimate, and reports the confidence bands - plus which uncertainty is "
    "actually driving the spread.",
)

# --------------------------------------------------------------------------
with st.expander("Uncertainty ranges", expanded=True):
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

# --------------------------------------------------------------------------
with st.spinner(f"Running {sc.mc.iterations:,} iterations..."):
    sim = scenario.monte_carlo(res, sc)
pct = montecarlo.percentiles(sim)
st.session_state["mc_percentiles"] = pct.to_dict("records")

def p(metric: str, q: int) -> float:
    row = pct[pct["metric"] == metric]
    return float(row[f"P{q}"].iloc[0]) if len(row) else 0.0

ui.metric_row([
    ("Programme cost P50", ui.compact_money(p("total_programme_cost", 50), cur), "median"),
    ("Programme cost P80", ui.compact_money(p("total_programme_cost", 80), cur),
     f"+{(p('total_programme_cost', 80) / max(p('total_programme_cost', 50), 1) - 1) * 100:.0f}% "
     "contingency"),
    ("Duration P50", f"{p('elapsed_months', 50):.1f} mo", "median"),
    ("Duration P80", f"{p('elapsed_months', 80):.1f} mo", None),
    ("Azure run rate P80", f"{ui.compact_money(p('azure_monthly_cost', 80), cur)}/mo", None),
])

for line in montecarlo.confidence_statement(sim, sc.budget_target, sc.deadline_months):
    prob_ok = "Below 80% confidence" not in line and "not credible" not in line
    ui.note(line, "note" if prob_ok else "warn")

ui.takeaway(
    "Never present the P50. It is a coin flip, and a steering committee funded to the median "
    "spends the second half of the programme asking for more money. Quote the <b>P80</b> and "
    "say plainly that it includes contingency. Then show the <b>tornado</b>: it names the one "
    "uncertainty worth spending money to narrow, which is a far better use of budget than "
    "adding blanket contingency to everything.")

tab_dist, tab_tornado, tab_conf, tab_table = st.tabs(
    ["Distributions", "What drives the spread", "Confidence curves", "Percentile table"])

# --------------------------------------------------------------------------
with tab_dist:
    c1, c2 = st.columns(2)
    for col, (metric, title, fmt) in zip(
            [c1, c2],
            [("total_programme_cost", "Total programme cost", "money"),
             ("elapsed_months", "Elapsed duration (months)", "num")]):
        with col:
            vals = sim[metric]
            fig = go.Figure()
            fig.add_trace(go.Histogram(x=vals, nbinsx=60, marker_color=ui.PALETTE[0],
                                       opacity=0.85, name=title))
            for q, colour in [(50, ui.PALETTE[2]), (80, ui.PALETTE[1]), (95, ui.PALETTE[3])]:
                v = np.percentile(vals, q)
                fig.add_vline(x=v, line_dash="dash", line_color=colour,
                              annotation_text=f"P{q}", annotation_position="top")
            fig.update_layout(height=380, title=title, showlegend=False,
                              xaxis_title="", yaxis_title="Iterations")
            st.plotly_chart(fig, width="stretch")

    c3, c4 = st.columns(2)
    with c3:
        fig = go.Figure(go.Histogram(x=sim["azure_monthly_cost"], nbinsx=60,
                                     marker_color=ui.PALETTE[2]))
        fig.update_layout(height=340, title="Azure monthly run rate", xaxis_title=cur,
                          yaxis_title="Iterations")
        st.plotly_chart(fig, width="stretch")
    with c4:
        fig = go.Figure(go.Histogram(x=sim["rollbacks"], nbinsx=50,
                                     marker_color=ui.PALETTE[3]))
        fig.update_layout(height=340, title="Failed cutovers requiring rollback",
                          xaxis_title="Count", yaxis_title="Iterations")
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

# --------------------------------------------------------------------------
with tab_tornado:
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

    top = tor.iloc[0]
    ui.note(
        f"<b>{top['driver']}</b> dominates the uncertainty. Narrowing that one range is worth "
        "more than reducing every other assumption combined - and unlike contingency, it is "
        "something the programme can actually act on. Tighten it with a pilot wave, a "
        "bandwidth test, or a proper bottom-up estimate on a representative sample.")

# --------------------------------------------------------------------------
with tab_conf:
    c1, c2 = st.columns(2)
    with c1:
        v = np.sort(sim["total_programme_cost"])
        cdf = np.arange(1, len(v) + 1) / len(v) * 100
        fig = go.Figure(go.Scatter(x=v, y=cdf, mode="lines",
                                   line=dict(width=3, color=ui.PALETTE[0])))
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
        cdf = np.arange(1, len(v) + 1) / len(v) * 100
        fig = go.Figure(go.Scatter(x=v, y=cdf, mode="lines",
                                   line=dict(width=3, color=ui.PALETTE[2])))
        fig.add_vline(x=sc.deadline_months, line_dash="dash", line_color=ui.PALETTE[3],
                      annotation_text="Deadline")
        fig.add_hline(y=80, line_dash="dot", line_color="rgba(128,128,128,.6)")
        fig.update_layout(height=400, title="Probability of finishing within a duration",
                          xaxis_title="Elapsed months", yaxis_title="Confidence (%)")
        st.plotly_chart(fig, width="stretch")

    st.markdown("### Funding recommendation")
    rows = []
    for q in [50, 70, 80, 90, 95]:
        rows.append({
            "Confidence": f"P{q}",
            "Programme cost": ui.money(np.percentile(sim["total_programme_cost"], q), cur),
            "Duration (months)": f"{np.percentile(sim['elapsed_months'], q):.1f}",
            "Contingency over P50":
                f"{(np.percentile(sim['total_programme_cost'], q) / np.percentile(sim['total_programme_cost'], 50) - 1) * 100:.0f}%",
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    ui.note(
        "Fund to P80. P50 is a coin flip that the programme lands on budget, and every "
        "steering committee that funds the median spends the second half of the programme "
        "asking for more money.")

# --------------------------------------------------------------------------
with tab_table:
    disp = pct.copy()
    label = {"elapsed_months": "Elapsed months", "migration_cost": "One-off migration cost",
             "total_programme_cost": "Total programme cost",
             "azure_monthly_cost": "Azure monthly run rate",
             "year1_total": "Year 1 total", "rollbacks": "Failed cutovers"}
    disp["metric"] = disp["metric"].map(lambda m: label.get(m, m))
    st.dataframe(disp.round(1), hide_index=True, width="stretch")
    ui.df_download(sim, "monte_carlo_iterations.csv", "Download all iterations")

    st.markdown("### Cost composition at P80")
    p80 = sim[sim["total_programme_cost"]
              >= np.percentile(sim["total_programme_cost"], 79)].head(400).mean(numeric_only=True)
    comp = pd.DataFrame([
        {"Component": "Labour", "Cost": p80["labour_cost"]},
        {"Component": "Rework from failed cutovers", "Cost": p80["rework_cost"]},
        {"Component": "Dual-run overlap", "Cost": p80["dual_run_cost"]},
        {"Component": "On-premises tail during migration", "Cost": p80["onprem_tail_cost"]},
    ])
    st.plotly_chart(ui.bar(comp, "Component", "Cost", "P80 programme cost composition",
                           orientation="h", height=300, text_fmt=",.0f"),
                    width="stretch")
