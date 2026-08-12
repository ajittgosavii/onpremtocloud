"""Executive overview: the whole decision on one page."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import assessment, scenario, ui

sc = scenario.get_scenario()
res = scenario.current()
cur = sc.commercial.currency

ui.page_header(
    "Executive briefing",
    f"A decision model for a {res.estate_summary['vm_count']:,}-VM vSphere estate "
    f"({res.estate_summary['windows_pct']:.0f}% Windows, {res.estate_summary['linux_pct']:.0f}% "
    "Linux). Every Azure figure below is priced against live Microsoft retail rates; every "
    "assumption is exposed on the page that produces it. Change an input anywhere and the "
    "whole model moves.",
)

for w in res.warnings:
    ui.note(w, "warn")

st.markdown(ui.estate_badge(sc.estate_source, sc.estate_label,
                            res.estate_summary["vm_count"])
            + ui.pricing_badge(res.price_book.source)
            + f"<span class='pill'>{sc.commercial.region}</span>"
            + f"<span class='pill'>{cur}</span>"
            + f"<span class='pill'>{res.cost_summary['priced_from_api_pct']:.0f}% of VMs "
              "priced from the live API</span>", unsafe_allow_html=True)

if sc.estate_source == "reference":
    ui.note(
        "These figures are computed from the <b>547-VM reference estate</b>, which is "
        "synthetic. The arithmetic and the Azure prices are real; the estate is not. "
        "Replace it on <b>Start here</b> before presenting any of this as a client's "
        "numbers.", "warn")

# --------------------------------------------------------------------------
cs, es, ts, ss = res.cost_summary, res.effort_summary, res.tco_summary, res.schedule_summary
delta_monthly = res.onprem_monthly - cs["monthly_total"]

ui.section("The headline",
           "Five numbers. If a client remembers nothing else from the session, it should be "
           "these.")

ui.metric_row([
    ("Azure run rate", f"{ui.compact_money(cs['monthly_total'], cur)}/mo",
     f"{delta_monthly / res.onprem_monthly * 100:+.0f}% vs on-premises"),
    ("Current on-premises cost", f"{ui.compact_money(res.onprem_monthly, cur)}/mo",
     f"{res.onprem.hosts} hosts"),
    ("One-off migration cost", ui.compact_money(es["migration_cost"], cur),
     f"{ui.money(es['cost_per_vm'], cur)} per VM"),
    ("Elapsed duration", f"{ss.get('elapsed_months', 0):.1f} months",
     f"{ss.get('waves', 0)} waves"),
    (f"{ts['horizon_years']}-year NPV saving", ui.compact_money(ts["npv_saving"], cur),
     f"payback {ts['payback_years']:.1f} yr" if ts["payback_years"] else "no payback in horizon"),
], tones=["", "", "", "", "pos" if ts["npv_saving"] > 0 else "neg"])

ui.takeaway(
    f"Running this estate on Azure costs "
    f"<b>{ui.compact_money(cs['monthly_total'], cur)} a month</b> against "
    f"<b>{ui.compact_money(res.onprem_monthly, cur)}</b> today - a "
    f"{abs(delta_monthly) / res.onprem_monthly * 100:.0f}% "
    f"{'reduction' if delta_monthly > 0 else 'increase'}. Getting there costs "
    f"{ui.compact_money(es['migration_cost'], cur)} and takes "
    f"{ss.get('elapsed_months', 0):.0f} months. "
    + (f"Over {ts['horizon_years']} years that is "
       f"{ui.compact_money(ts['npv_saving'], cur)} of net present value, paying back in "
       f"year {ts['payback_years']:.1f}."
       if ts["payback_years"] else
       "It does not pay back within the modelled horizon - which is the conversation to "
       "have before anything else."))

# --------------------------------------------------------------------------
ui.section("Where the estate is going",
           "The 7R disposition and the Azure readiness verdict. Everything downstream - "
           "effort, duration, cost and risk - follows from these two charts.")

left, right = st.columns([1.15, 1])

with left:
    st.markdown("### Disposition")
    d = res.disposition.copy()
    fig = ui.bar(d, "strategy", "vms", colour_map=ui.STRATEGY_COLOURS,
                 orientation="h", height=300, text_fmt=",.0f")
    fig.update_layout(xaxis_title="VMs", yaxis_title="")
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "The 7R disposition drives everything downstream: effort, duration, cost and risk. "
        "Adjust the modernisation appetite on the Assessment page."
    )

with right:
    st.markdown("### Azure readiness")
    r = res.readiness
    st.plotly_chart(
        ui.donut(r["readiness"], r["vms"], colour_map=ui.READINESS_COLOURS, height=300),
        width="stretch")
    nr = int(r.loc[r["readiness"] == assessment.NOT_READY, "vms"].sum()) if len(r) else 0
    st.caption(
        f"{nr} VM(s) cannot move to native Azure IaaS as they stand. Each one needs "
        "remediation, a different target, or an exception decision."
    )

rehost_share = float(res.disposition.loc[res.disposition["strategy"] == "Rehost",
                                         "share_pct"].sum()) if len(res.disposition) else 0
ui.takeaway(
    f"{rehost_share:.0f}% of the estate is a straight rehost - low risk, well understood, "
    f"and the fastest route out of the data centre. The interesting {100 - rehost_share:.0f}% "
    f"is where the programme's cost and risk actually sit: the {nr} VMs that cannot move as "
    "they stand, the databases that need a different tool, and the workloads worth "
    "modernising rather than moving.")

# --------------------------------------------------------------------------
ui.section("Cost: today versus Azure",
           "Where the Azure bill comes from, and how much of the saving is optimisation "
           "rather than the move itself.")

c1, c2 = st.columns([1.3, 1])
with c1:
    comp = res.cost_breakdown
    fig = go.Figure(go.Bar(
        x=comp["monthly_cost"], y=comp["component"], orientation="h",
        marker_color=ui.PALETTE[0],
        text=[ui.compact_money(v, cur) for v in comp["monthly_cost"]], textposition="auto"))
    fig.update_layout(height=330, title="Azure monthly run rate by component",
                      xaxis_title=f"{cur} per month", yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig, width="stretch")

with c2:
    st.markdown("### What optimisation is worth")
    st.metric("Baseline: on-demand, no levers",
              f"{ui.compact_money(cs['baseline_monthly'], cur)}/mo")
    st.metric("With the levers applied", f"{ui.compact_money(cs['monthly_total'], cur)}/mo",
              f"-{cs['monthly_saving'] / cs['baseline_monthly'] * 100:.0f}%")
    st.metric("Azure Hybrid Benefit alone",
              f"{ui.compact_money(cs['ahb_saving'], cur)}/mo saved")
    st.metric("Retiring idle VMs",
              f"{ui.compact_money(cs['retire_saving_monthly'], cur)}/mo avoided",
              f"{cs['vms_retired']} VMs never migrated")

ui.takeaway(
    f"Lifting and shifting this estate without touching the commercial levers would cost "
    f"{ui.compact_money(cs['baseline_monthly'], cur)} a month. The levers - Hybrid Benefit, "
    "reservations, non-production scheduling and retiring what nobody uses - take "
    f"{cs['monthly_saving'] / cs['baseline_monthly'] * 100:.0f}% off that. "
    "Most of the saving in this business case is discipline, not the cloud. If the client "
    "will not commit to the levers, the case changes.")

# --------------------------------------------------------------------------
ui.section("Five-year cash position",
           "The do-nothing case against the migrate case, discounted to present value.")

t = res.tco_table
fig = go.Figure()
fig.add_trace(go.Scatter(x=t["year"], y=t["cum_stay"], name="Stay on VMware",
                         mode="lines+markers", line=dict(width=3, color=ui.PALETTE[3])))
fig.add_trace(go.Scatter(x=t["year"], y=t["cum_migrate"], name="Migrate to Azure",
                         mode="lines+markers", line=dict(width=3, color=ui.PALETTE[0])))
fig.update_layout(height=340, xaxis_title="Year", yaxis_title=f"Cumulative cost ({cur})",
                  xaxis=dict(dtick=1))
st.plotly_chart(fig, width="stretch")

if ts["payback_years"]:
    ui.note(
        f"Cumulative cost crosses over at <b>year {ts['payback_years']:.1f}</b>. Year 1 is "
        f"{ui.compact_money(abs(ts['year1_delta']), cur)} worse than doing nothing because the "
        "programme cost and the dual-run overlap land before the on-premises estate switches "
        f"off. Steady state runs {ui.compact_money(ts['steady_state_delta'], cur)} per year "
        "better.")
else:
    ui.note(
        "The migration does not pay back within the modelled horizon. Either the on-premises "
        "baseline is understated, the Azure run rate is not optimised, or the horizon is too "
        "short for the one-off cost. Check the Business case page before presenting this.",
        "warn")

# --------------------------------------------------------------------------
ui.section("What should worry you",
           "The findings and signals that most threaten the numbers above. Raise these "
           "yourself before the client's architects do.")

col1, col2 = st.columns(2)
with col1:
    st.markdown("### Top findings across the estate")
    b = res.blockers.head(8).copy()
    if len(b):
        b = b.rename(columns={"severity": "Type", "finding": "Finding", "vms": "VMs"})
        st.dataframe(b, hide_index=True, width="stretch",
                     column_config={"Finding": st.column_config.TextColumn(width="large")})
    else:
        st.success("No readiness findings across the estate.")

with col2:
    st.markdown("### Programme risk signals")
    signals = []
    if ss.get("bandwidth_bound_waves", 0):
        signals.append(
            f"**{ss['bandwidth_bound_waves']} of {ss['waves']} waves are bandwidth-bound.** "
            "More engineers will not make them faster. Bandwidth or offline seeding will.")
    if ss.get("expected_rollbacks", 0) > 5:
        signals.append(
            f"**{ss['expected_rollbacks']:.0f} cutovers are expected to fail and roll back** "
            f"({ss['expected_rollbacks'] / max(ss.get('vms_migrating', 1), 1) * 100:.1f}% of "
            "migrations). Each one costs a change window and erodes confidence.")
    eol = res.estate_summary["eol_os_count"]
    if eol:
        signals.append(
            f"**{eol} VMs run an end-of-life guest OS** "
            f"({eol / res.estate_summary['vm_count'] * 100:.0f}% of the estate). Azure Migrate "
            "will not upgrade them - the risk moves to Azure unchanged.")
    db = res.estate_summary["db_vms"]
    if db:
        signals.append(
            f"**{db} VMs carry a database engine.** Azure Migrate assesses SQL Server and "
            "migrates nothing. That is a separate workstream with separate tooling - see the "
            "Azure Migrate simulator for the size of the gap.")
    if res.sizing_summary["upsized_count"]:
        signals.append(
            f"**{res.sizing_summary['upsized_count']} VMs get *more* vCPU in Azure than they "
            "have today**, because Azure SKU sizes are discrete and the comfort factor rounds "
            "up. Right-sizing is not free money.")
    for s in signals[:5]:
        st.markdown(f"- {s}")

ui.takeaway(
    "Nothing on this list is a reason not to proceed. Every one of them is a reason to fund "
    "discovery and remediation properly before wave one, rather than discovering them at "
    "2 a.m. during a cutover. Programmes fail on the items in this panel, not on the "
    "arithmetic in the panel above it.",
    label="How to frame the risks")

# --------------------------------------------------------------------------
ui.section("How to read this model",
           "Worth saying out loud at the start of any session, so the numbers are trusted "
           "for the right reasons.")

from core import assumptions as _A                                        # noqa: E402
_reg = _A.build(sc, res)
_s = _A.summary(_reg)

c1, c2, c3 = st.columns(3)
with c1:
    with st.container(border=True):
        st.markdown(
            f"**What is real** &nbsp;&middot;&nbsp; {_s['vendor_facts']} inputs\n\n"
            "Azure prices, SKU specifications, managed-disk tiers, reserved instance and "
            "savings plan rates, and every published Azure Migrate product limit. These come "
            "from Microsoft's own API and documentation, fetched live.")
        ui.page_link("views/cost.py", "See the live rate feed", ":material/payments:")
with c2:
    with st.container(border=True):
        st.markdown(
            f"**What is modelled** &nbsp;&middot;&nbsp; "
            f"{_s['calibrate'] + _s['judgement']} assumptions, "
            f"{_s['priority_1']} that matter\n\n"
            "The estate, utilisation, churn, effort per VM, cutover risk and the on-premises "
            "cost base. Every one is a control on a specific page - the register lists them "
            "all and links straight to it.")
        ui.page_link("views/assumptions.py", "Open the assumptions register",
                     ":material/rule_settings:")
with c3:
    with st.container(border=True):
        st.markdown(
            f"**What to do next** &nbsp;&middot;&nbsp; {_s['estate']} inputs come from the inventory\n\n"
            "Load a real RVTools export. It replaces roughly a dozen assumptions at once and "
            "is worth more than tuning every other parameter combined. The synthetic estate "
            "exists to explore the model before real data arrives, not to substitute for it.")
        ui.page_link("views/inventory.py", "Upload an inventory", ":material/upload_file:")
