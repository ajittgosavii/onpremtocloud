"""Five-year cost of the Microsoft-only shortlist, on one basis."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import azure_options as ao
from core import broadcom, platforms, scenario, ui

sc = scenario.get_scenario()
res = scenario.current()
cur = sc.commercial.currency

ui.page_header(
    "Azure-only TCO",
    "Target platforms ranks seventeen destinations on fit. This page asks the narrower "
    "question a Microsoft-centric client actually puts: of the Microsoft options alone, "
    "which is cheapest over five years, and by how much? Four destinations, one basis, "
    "including the migration itself - because a five-year total is not the monthly run "
    "rate times sixty, and the gap between those two numbers is where these options "
    "separate.",
)

ui.takeaway(
    "Hyper-V is on this page deliberately: it is the cheapest way to stop paying Broadcom, "
    "so every Azure option here has to beat it on something other than price. Two figures "
    "usually decide the room - <b>Azure Local</b> is the cheapest destination and never "
    "leaves the building, and <b>AVS</b> is both the most expensive over five years "
    "<i>and</i> the only one of the four still buying a Broadcom subscription.")

# --------------------------------------------------------------------------
# Controls. Every default is an assumption, so every default is adjustable.
# --------------------------------------------------------------------------
present = ui.presenting()
hv = ao.HyperVInputs()
vcf_rate, avs_node = 135.0, "AV36"

if not present:
    with st.expander("Assumptions behind these four numbers", expanded=False):
        c1, c2, c3 = st.columns(3)
        vcf_rate = c1.number_input(
            "VCF subscription per core/year", 0.0, 600.0, 135.0, 5.0,
            help="Since November 2025 an AVS node no longer includes the VMware licence. "
                 "You buy a portable VCF subscription from Broadcom and it lands on this "
                 "page as its own line.")
        avs_node = c2.selectbox(
            "AVS node type", list(platforms.AVS_NODES), index=0,
            help="AVS is dedicated hardware, sized on whichever of CPU, memory and vSAN "
                 "capacity binds first. Memory almost always wins.")
        owns_windows = c3.toggle(
            "Windows Server Datacenter already owned", True,
            help="Most enterprises running Hyper-V already hold Datacenter under an "
                 "enterprise agreement, which is the assumption behind Hyper-V being the "
                 "cheap option. Turn this off and it stops being cheap.")

        c4, c5, c6 = st.columns(3)
        scvmm = c4.number_input(
            "System Center per core/year", 0.0, 400.0, ao.SCVMM_PER_CORE_YEAR, 5.0,
            help="List is about 3,607 per 16-core pack, roughly 225 per core perpetual, "
                 "carried under Software Assurance at about a quarter of licence value a "
                 "year. List price, not a quotation.")
        tooling = c5.number_input(
            "Replacement tooling per year", 0.0, 500000.0,
            float(hv.replacement_tooling_annual), 10000.0,
            help="Backup, monitoring and automation that integrated with the vSphere API "
                 "and does not follow you to Hyper-V.")
        fte_delta = c6.number_input(
            "Extra operations FTE on Hyper-V", 0.0, 5.0, float(hv.ops_fte_delta), 0.5,
            help="SCVMM is materially behind vCenter. This is the honesty line in the "
                 "Hyper-V case.")

        hv = ao.HyperVInputs(
            scvmm_per_core_year=scvmm,
            windows_dc_per_core_year=0.0 if owns_windows else ao.WINDOWS_DC_PER_CORE_YEAR,
            replacement_tooling_annual=tooling,
            ops_fte_delta=fte_delta)

out = ao.compare(res, sc, hv_inputs=hv, vcf_rate=vcf_rate, avs_node=avs_node)
sm, flows = out["summary"], out["flows"]
years = out["horizon_years"]
best = sm.iloc[0]
worst = sm.iloc[-1]

# Colour by whether the Broadcom relationship actually ends.
DEP_COLOUR = {broadcom.ELIMINATED: ui.POSITIVE, broadcom.RELOCATED: ui.NEGATIVE,
              broadcom.RETAINED: ui.WARNING}
dep_of = {d: broadcom.dependency_for(d)[0] for d in ao.DESTINATIONS}
colour_map = {d: DEP_COLOUR[dep_of[d]] for d in ao.DESTINATIONS}

ui.metric_row([
    (f"Cheapest over {years} years", best["destination"].split(" (")[0],
     ui.compact_money(best["npv"], cur) + " NPV"),
    ("Against staying on VMware", ui.compact_money(abs(best["vs_stay"]), cur),
     f"{best['vs_stay_pct']:+.0f}% over {years} years"),
    ("Spread across the four", ui.compact_money(worst["npv"] - best["npv"], cur),
     f"{worst['vs_cheapest_pct']:.0f}% between cheapest and dearest"),
    ("Still paying Broadcom",
     ", ".join(d.split(" (")[0] for d, v in dep_of.items() if v != broadcom.ELIMINATED)
     or "None of the four",
     "after the programme completes"),
], tones=["", "pos" if best["vs_stay"] < 0 else "neg", "", "neg"])

tab_cost, tab_year, tab_basis = st.tabs(
    [f"{years}-year comparison", "Year by year", "What is in each number"])

# --------------------------------------------------------------------------
with tab_cost:
    ui.section(f"{years}-year net present cost",
               f"Discounted at {sc.tco_inputs.discount_rate_pct:.0f}%, including the "
               "migration and the VMware estate still running during it. Bars are "
               "coloured by what happens to the Broadcom relationship, not by price.")

    plot = sm.copy()
    # regex=False: " (" is an unterminated subpattern, not a separator.
    plot["short"] = plot["destination"].str.split(" (", regex=False).str[0]
    fig = ui.bar(plot, "short", "npv", orientation="h", height=300)
    fig.update_traces(text=[ui.compact_money(v, cur) for v in plot["npv"]],
                      marker_color=[colour_map[d] for d in plot["destination"]])
    fig.update_layout(xaxis_title=f"{years}-year NPV ({cur})")
    # The control case, so "cheapest of four" is not read as "worth doing".
    fig.add_vline(x=out["stay_npv"], line_dash="dot", line_color=ui.NEGATIVE,
                  annotation_text="Stay on VMware", annotation_position="top")
    st.plotly_chart(fig, width="stretch")

    show = sm.copy()
    show["Destination"] = show["destination"]
    show["Where it lands"] = show["location"]
    show["Broadcom"] = show["destination"].map(dep_of)
    show["Steady-state / yr"] = show["steady_annual"].map(lambda v: ui.money(v, cur))
    show["One-off"] = show["one_off_total"].map(lambda v: ui.money(v, cur))
    show[f"{years}-yr total"] = show["five_year_total"].map(lambda v: ui.money(v, cur))
    show[f"{years}-yr NPV"] = show["npv"].map(lambda v: ui.money(v, cur))
    show["vs staying"] = show["vs_stay_pct"].map(lambda v: f"{v:+.0f}%")
    st.dataframe(
        show[["Destination", "Where it lands", "Broadcom", "Steady-state / yr",
              "One-off", f"{years}-yr total", f"{years}-yr NPV", "vs staying"]],
        hide_index=True, width="stretch")

    relocated = [d for d, v in dep_of.items() if v == broadcom.RELOCATED]
    if relocated:
        ui.note(
            "<b>" + ", ".join(relocated) + " does not remove the Broadcom relationship, "
            "it relocates it.</b> " + broadcom.DEPENDENCY_NOTE[broadcom.RELOCATED]
            + " On a five-year view that subscription is priced above as its own line, "
            "which is why this option can be both the fastest exit and the dearest "
            "destination at the same time.", "bad")

    if best["vs_stay"] > 0:
        ui.note(
            f"<b>None of the four beats staying put over {years} years on cost alone.</b> "
            "That is a legitimate finding and worth saying out loud: the case for moving "
            "then rests on the renewal risk, the hardware refresh, and what happens in "
            "year six - not on this table.", "warn")

    ui.df_download(sm, "microsoft_destinations_tco.csv",
                   f"Download the {years}-year comparison")

# --------------------------------------------------------------------------
with tab_year:
    ui.section("Where the money actually falls",
               "The overlap is the point. Every destination pays for the VMware estate "
               "and its replacement at the same time for as long as the migration runs, "
               "and the options separate on how long that is.")

    fig = go.Figure()
    for dest in ao.DESTINATIONS:
        d = flows[flows["destination"] == dest]
        fig.add_trace(go.Scatter(
            x=d["year"], y=d["cumulative"], name=dest.split(" (")[0],
            mode="lines+markers", line=dict(width=2.5, color=colour_map[dest])))
    fig.update_layout(height=380, xaxis_title="Year",
                      yaxis_title=f"Cumulative cost ({cur})",
                      xaxis=dict(dtick=1))
    st.plotly_chart(ui.legend_top(fig, "Cumulative cost by destination"),
                    width="stretch")

    pick = st.selectbox("Break one destination down by year", ao.DESTINATIONS,
                        format_func=lambda d: d.split(" (")[0])
    d = flows[flows["destination"] == pick].copy()
    tbl = pd.DataFrame({
        "Year": d["year"],
        "VMware estate still running": d["legacy_vmware"].map(lambda v: ui.money(v, cur)),
        "Destination run cost": d["destination_run"].map(lambda v: ui.money(v, cur)),
        "One-off / recovery": d["one_off"].map(lambda v: ui.money(v, cur)),
        "Total": d["total"].map(lambda v: ui.money(v, cur)),
        "Cumulative": d["cumulative"].map(lambda v: ui.money(v, cur)),
    })
    st.dataframe(tbl, hide_index=True, width="stretch")

    shape = ao.SHAPES[pick]
    if shape.legacy_scope == "licence":
        ui.note(
            "Hyper-V converts the hosts you already own, so the hardware, floor space and "
            "staff behind it are charged in full from year one and do not ramp - they are "
            "already being paid for. The only line that winds down is the Broadcom "
            "subscription, and it steps to zero at cutover rather than sloping, because a "
            "subscription is not refunded machine by machine.")
    else:
        ui.note(
            f"The VMware estate winds down as workload lands, to a residual "
            f"{shape.residual_pct:.0f}% of kit that never leaves. From year four the "
            "residual is priced at the <b>renewal</b> rate rather than today's - pricing "
            "the thing you are escaping at the old price is the most common way an exit "
            "case flatters itself.")

# --------------------------------------------------------------------------
with tab_basis:
    ui.section("What is inside each figure",
               "These four are only comparable if they are costed on the same "
               "checklist. They are, and this is it.")

    ui.note(
        "The trap on this page is a destination that prices only its own nodes. "
        f"<b>Azure Local</b> is the clearest case: its own cost model covers the cluster, "
        "its power and the staff who run it, but not the network it plugs into, the backup "
        "product, the DR site, the monitoring estate or the SQL licences - all of which "
        "survive the conversion. Those lines are added back here "
        f"({ui.money(ao.persistent_services_annual(res.onprem), cur)} a year) so that it and "
        "Hyper-V stand on the same footing.")

    _dt = ao.excluded_annual(res.onprem)
    if _dt:
        ui.note(
            "<b>One asymmetry to declare.</b> Business-impact downtime "
            f"({ui.money(_dt, cur)} a year in the current-state model) is excluded from all "
            "four destinations, because none of the Azure cost models carries an equivalent "
            "and inventing one would be worse. It is still inside the <i>stay on VMware</i> "
            "reference line, which is taken unchanged from the Business case so the two "
            "pages cannot disagree. The effect is that the <i>vs staying</i> column flatters "
            "a move by roughly that line; the four destinations are compared with each "
            "other on a clean basis either way.", "warn")

    pick2 = st.selectbox("Steady-state breakdown", ao.DESTINATIONS,
                         format_func=lambda d: d.split(" (")[0], key="basis_pick")
    bd = out["breakdowns"][pick2].copy()
    bd["Annual"] = bd["annual_cost"].map(lambda v: ui.money(v, cur))
    bd["Share"] = bd["share_pct"].map(lambda v: f"{v:.1f}%")
    st.dataframe(
        bd.rename(columns={"component": "Component", "basis": "Basis"})[
            ["Component", "Annual", "Share", "Basis"]],
        hide_index=True, width="stretch")

    a = out["avs_sizing"]
    st.caption(
        f"AVS sized at {a['hosts']} x {a['node']} hosts, bound by "
        f"{a['binding_constraint'].lower()}. Azure Local sized at "
        f"{out['azure_local']['nodes']} nodes / "
        f"{out['azure_local']['physical_cores']:,} physical cores. Azure native IaaS is "
        f"priced from {res.price_book.source} retail rates for "
        f"{sc.commercial.region}. Migration effort for each destination is scaled from "
        "the estate-wide figure on Complexity & effort.")

    ui.page_link("views/platform_options.py",
                 "See all seventeen destinations, ranked on fit rather than cost",
                 icon=":material/hub:")
