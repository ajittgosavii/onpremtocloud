"""Broadcom exposure: the clock, the bill, and the three ways this can end.

Placed first in the narrative because it is the question that is actually being
asked. Every other page in this application answers "what does the destination
cost". This one answers "what does the incumbent cost, what happens if we do
nothing, and what leverage do we hold" -- and unlike the rest of the model, it
has dates attached that move whether or not anybody opens the page.
"""

import datetime as dt

import pandas as pd
import streamlit as st

from core import broadcom, scenario, tco, ui

sc = scenario.get_scenario()
res = scenario.current()
cur = sc.commercial.currency

ui.page_header(
    "Broadcom exposure",
    "What the incumbent costs, what the calendar is doing to your options, and "
    "the three ways this ends. Doing nothing while a decision is made is itself "
    "a decision to buy from Broadcom.")

st.markdown(ui.estate_badge(sc.estate_source, sc.estate_label,
                            res.estate_summary["vm_count"]),
            unsafe_allow_html=True)

# --------------------------------------------------------------------------
ui.section("The clock",
           "Two dates decide how much room the negotiation has. Both are counted "
           "from today, not from when this was written.")

cols = st.columns(len(broadcom.MILESTONES), gap="medium")
for col, m in zip(cols, broadcom.MILESTONES):
    stat = broadcom.milestone_status(m)
    tone = {"passed": "bad", "critical": "bad", "warning": "warn",
            "watch": "note"}[stat["band"]]
    with col:
        with st.container(border=True):
            st.markdown(
                f"<div class='kpi-label'>{stat['date']}</div>"
                f"<div class='kpi-value'>{stat['label']}</div>",
                unsafe_allow_html=True)
            st.markdown(f"**{m.title}**")
            st.caption(m.detail)
            ui.note(f"<b>Consequence.</b> {m.consequence}", tone)
            st.caption(f"Applies when: {m.applies_when}")

ui.note(
    "<b>&ldquo;Do nothing while we decide&rdquo; is not a neutral option.</b> It "
    "commits you to a Broadcom purchase, because the incumbent platform and the "
    "Azure VMware Solution landing zone both now require a Broadcom-sourced "
    "subscription. The only question left is whether that purchase happens at a "
    "negotiation or under a deadline.", "bad")

# --------------------------------------------------------------------------
ui.section("What the incumbent costs you",
           "Derived from the estate on this model. Licensing is per physical core "
           "with a sixteen-core minimum charged per socket, so a host with fewer "
           "cores than that is billed for cores it does not have.")

p = res.onprem
total_sockets = p.hosts * p.sockets_per_host
physical_cores = total_sockets * p.cores_per_socket
billable_cores = total_sockets * max(p.cores_per_socket, p.vmware_min_cores_per_socket)
phantom = billable_cores - physical_cores

breakdown = tco.onprem_annual_breakdown(p)
vmware_line = float(
    breakdown.loc[breakdown["component"].str.contains("VMware"), "annual_cost"].sum())
onprem_annual = float(breakdown["annual_cost"].sum())

ui.metric_row([
    ("Hosts in the cost model", f"{p.hosts:,}", f"{total_sockets:,} sockets"),
    ("Physical cores", f"{physical_cores:,}", f"{p.cores_per_socket} per socket"),
    ("Billable cores", f"{billable_cores:,}",
     f"+{phantom:,} phantom cores" if phantom else "no minimum applied"),
    ("VMware subscription", f"{ui.compact_money(vmware_line, cur)}/yr",
     f"{vmware_line / max(onprem_annual, 1) * 100:.0f}% of platform cost"),
    ("Whole platform", f"{ui.compact_money(onprem_annual, cur)}/yr",
     "licensing, hardware, facilities, staff"),
], tones=["", "", "warn" if phantom else "", "", ""])

if phantom:
    ui.note(
        f"<b>{phantom:,} phantom cores.</b> Sockets with fewer than "
        f"{p.vmware_min_cores_per_socket} cores are billed at the minimum, so you "
        f"pay for {phantom / max(billable_cores, 1) * 100:.0f}% more core "
        "entitlement than the hardware has. This is the line that makes a "
        "hardware refresh a licensing decision rather than a capacity one.", "warn")

# --------------------------------------------------------------------------
ui.section("Three scenarios, not two",
           "Presenting fewer than three invites the challenge that the analysis "
           "was written to justify a decision already taken. The middle one is "
           "the reason to run this exercise even if nothing moves.")

with st.expander("Adjust the commercial assumptions", expanded=False):
    c1, c2, c3 = st.columns(3)
    multiple = c1.slider(
        "Renewal multiple on the VMware line", 1.0, 10.0, 3.0, 0.5,
        help="Renewal quotes commonly land at three to ten times prior "
             "perpetual-plus-support cost. The multiple depends almost entirely on "
             "the discount previously held, so anchor it on your own quote.")
    discount = c2.slider(
        "Discount achievable with documented alternatives (%)", 0, 60, 25, 5,
        help="A credible, evidenced alternatives evaluation is the strongest "
             "commercial lever available at renewal.")
    horizon = c3.slider("Horizon (years)", 3, 7, 5, 1)

quoted = vmware_line * multiple
negotiated = quoted * (1 - discount / 100.0)
prog_cost = res.effort_summary["migration_cost"]
azure_annual = res.cost_summary["monthly_total"] * 12
elapsed_m = res.schedule_summary.get("elapsed_months", 0) or 12

# Scenario C: residual Broadcom through the transition, then gone.
transition_years = min(elapsed_m / 12.0, horizon)
scen = []
for key, name, desc, sens in broadcom.SCENARIOS:
    if key == "A":
        total = quoted * horizon + (onprem_annual - vmware_line) * horizon
    elif key == "B":
        total = negotiated * horizon + (onprem_annual - vmware_line) * horizon
    else:
        residual = negotiated * transition_years
        rest_of_platform = (onprem_annual - vmware_line) * transition_years
        total = residual + rest_of_platform + prog_cost + azure_annual * horizon
    scen.append({"Scenario": f"{key} -- {name}", "What it is": desc,
                 f"{horizon}-year total": total, "Dominant sensitivity": sens})

frame = pd.DataFrame(scen)
best = frame[f"{horizon}-year total"].min()
frame["vs best"] = frame[f"{horizon}-year total"] - best
st.dataframe(
    frame.style.format({f"{horizon}-year total": lambda v: ui.money(v, cur),
                        "vs best": lambda v: "--" if v == 0 else "+" + ui.money(v, cur)}),
    hide_index=True, width="stretch")

saving_b = (quoted - negotiated) * horizon
ui.note(
    f"<b>Scenario B pays for the evaluation on its own.</b> A {discount}% "
    f"negotiated reduction on a {multiple:.1f}x renewal is worth "
    f"{ui.compact_money(saving_b, cur)} over {horizon} years, and it requires a "
    "documented alternatives evaluation to be credible. That is worth having "
    "whether or not a single virtual machine ever moves.", "good")

ui.note(
    "Scenario C is <b>not</b> complete in this model. The lines it is missing are "
    "listed below, and several of them are large.", "warn")

# --------------------------------------------------------------------------
ui.section("What Scenario C must contain",
           "The cost lines routinely absent from an exit business case, and "
           "whether this application currently models them.")

lines = pd.DataFrame(
    [{"Cost line": name,
      "Modelled here": "Yes" if modelled else "Add by hand",
      "Note": note}
     for name, modelled, note in broadcom.SCENARIO_C_LINES])
st.dataframe(lines, hide_index=True, width="stretch")

missing = sum(1 for _, m, _ in broadcom.SCENARIO_C_LINES if not m)
ui.takeaway(
    f"For a public-cloud rehost, licence savings typically account for less than "
    f"half of the total programme economics. {missing} of the "
    f"{len(broadcom.SCENARIO_C_LINES)} cost lines above are not modelled here -- "
    "disaster recovery re-engineering and backup re-platforming in particular are "
    "often larger than the migration itself. A business case resting on the delta "
    "between the Broadcom quote and Azure compute is incomplete and will be "
    "challenged.")

# --------------------------------------------------------------------------
ui.section("What to table at renewal",
           "Whether or not the exit proceeds. A documented alternatives evaluation "
           "is the instrument that makes each of these credible.")

for i, (lever, why) in enumerate(broadcom.NEGOTIATION_LEVERS, 1):
    st.markdown(f"**{i}. {lever}**")
    st.caption(why)

# --------------------------------------------------------------------------
with st.expander("What already changed, and is not coming back", expanded=False):
    for title, detail in broadcom.IN_FORCE:
        st.markdown(f"**{title}**")
        st.caption(detail)
    st.caption(
        "The exit case rests on commercial exposure, concentration risk and loss "
        "of negotiating leverage -- not on technical inadequacy. A case built on "
        "the claim that the alternatives are technically superior will not survive "
        "contact with an experienced infrastructure team.")
