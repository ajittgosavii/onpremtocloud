"""Broadcom exposure: the clock, the bill, and the three ways this can end.

Placed first in the narrative because it is the question that is actually being
asked. Every other page in this application answers "what does the destination
cost". This one answers "what does the incumbent cost, what happens if we do
nothing, and what leverage do we hold" -- and unlike the rest of the model, it
has dates attached that move whether or not anybody opens the page.
"""

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

# These figures are not computed here. They come from the same discounted model
# that drives Business case, because a client who finds this page and that page
# disagreeing about the cost of the same three options stops trusting both.
ss = res.scenario_summary
npv = ss["npv"]
horizon = ss["horizon_years"]

frame = pd.DataFrame([
    {"Scenario": f"{k} -- {name}", "What it is": desc,
     f"{horizon}-year NPV": npv[k.lower()],
     "vs cheapest": npv[k.lower()] - min(npv.values()),
     "Dominant sensitivity": sens}
    for k, name, desc, sens in broadcom.SCENARIOS])
st.dataframe(
    frame.style.format({f"{horizon}-year NPV": lambda v: ui.money(v, cur),
                        "vs cheapest": lambda v: "--" if v == 0 else "+" + ui.money(v, cur)}),
    hide_index=True, width="stretch")

ui.metric_row([
    ("Cheapest scenario", f"{ss['cheapest'].upper()} -- {ss['cheapest_label']}",
     f"over {horizon} years, discounted"),
    ("What negotiating alone is worth", ui.compact_money(ss["b_vs_a"], cur),
     "B against A, net of the evaluation"),
    ("What exiting adds beyond that", ui.compact_money(ss["c_vs_b"], cur),
     "C against B -- the honest comparison"),
    ("Exit crossover vs a negotiated renewal",
     f"year {ss['payback_vs_b']:.1f}" if ss["payback_vs_b"] else "beyond horizon",
     f"year {ss['payback_vs_a']:.1f} against the quote" if ss["payback_vs_a"] else None),
], tones=["pos" if ss["cheapest"] == "c" else "warn", "", "", ""])

if ss["b_vs_a"] > 0:
    ui.note(
        f"<b>The negotiation pays for itself.</b> The modelled discount and renewal cap are "
        f"worth {ui.compact_money(ss['b_vs_a'], cur)} in present value over {horizon} years "
        "*after* charging Scenario B with the cost of running the alternatives evaluation. "
        "That is worth having whether or not a single virtual machine ever moves.", "good")
else:
    ui.note(
        "<b>On the current assumptions the negotiation does not pay for itself</b> - the "
        "modelled discount and cap are worth less than the evaluation costs to run. Either "
        "the achievable discount is set too low, or the renewal exposure is small enough "
        "that the exit case has to rest on concentration risk rather than price.", "warn")

ui.note(
    "The three commercial assumptions behind Scenario B - achievable discount, renewal cap "
    "and the cost of the evaluation - are set on Business case and shared with this page. "
    "Change them in one place and both move together.")
ui.page_link("views/business_case.py", "Open the full three-scenario comparison",
             ":material/account_balance:")

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
