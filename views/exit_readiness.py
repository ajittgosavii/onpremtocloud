"""Exit readiness: the phased roadmap, and the ways these programmes actually fail.

The wave plan elsewhere in this application answers how long the migration takes.
It does not answer whether the programme around it is set up to survive, and the
failure modes are consistent enough across VMware exits to be worth checking
mechanically rather than remembering.

Every anti-pattern that can be tested is tested against the current model, so
this page changes when the scenario changes. The ones that cannot be observed
from a model are still listed, because they are the most common of all.
"""

import pandas as pd
import streamlit as st

from core import broadcom, scenario, ui

sc = scenario.get_scenario()
res = scenario.current()
cur = sc.commercial.currency
sized = res.sized

ui.page_header(
    "Exit readiness",
    "The programme shape this needs, and a mechanical check against the failure "
    "modes that recur in VMware exit programmes. A plan that is fast on paper is "
    "usually a plan with the remediation left out.")

st.markdown(ui.estate_badge(sc.estate_source, sc.estate_label,
                            res.estate_summary["vm_count"]),
            unsafe_allow_html=True)

# --------------------------------------------------------------------------
ui.section("Where this estate sits against the benchmark",
           "Indicative shares for a typical enterprise estate. Being outside a "
           "band is a prompt to explain, not a fault -- but it is better to be "
           "asked here than at a steering committee.")

counts = sized["strategy"].value_counts().to_dict()
rows = broadcom.segmentation_scorecard(counts, len(sized))
board = pd.DataFrame([{
    "Segment": r["segment"], "VMs": r["vms"], "Share": f"{r['pct']:.1f}%",
    "Typical band": r["band"], "Position": r["verdict"].title(),
    "Natural destination": r["destination"]} for r in rows])
st.dataframe(board, hide_index=True, width="stretch")

retire = next((r for r in rows if r["segment"] == "Retire"), None)
if retire and retire["verdict"] == "below":
    ui.note(
        f"<b>Only {retire['pct']:.0f}% of the estate is being retired.</b> A "
        "typical estate carries between a tenth and a quarter with no active "
        "users. Every one of those migrated is paid for twice -- once to move it "
        "and again to run it. Retiring is the highest-return activity in the "
        "programme and the cheapest migration is the one not performed.", "warn")

# --------------------------------------------------------------------------
ui.section("Failure modes, checked against this scenario",
           "Ten patterns that recur often enough to name. Seven can be tested "
           "against the model on screen; three cannot be seen from any model.")

facts = {
    "total_vms": len(sized),
    "retire_pct": float((sized["strategy"] == "Retire").mean() * 100),
    "avs_vms": int((sized["target_service"] == "Azure VMware Solution").sum()),
    "paas_vms": int((~sized["target_service"].isin(
        ["Azure VM (IaaS)", "Decommission", "Azure VMware Solution"])).sum()),
    "dual_run_months": float(getattr(sc.effort, "dual_run_months", 0.0)),
    "elapsed_months": float(res.schedule_summary.get("elapsed_months", 0.0)),
    "appliance_blockers": int(len(res.blockers)) if res.blockers is not None else 0,
    "dr_rebuild_costed": False,
}

checks = broadcom.check_antipatterns(facts)
triggered = [c for c in checks if c[1] is True]
clear = [c for c in checks if c[1] is False]
advisory = [c for c in checks if c[1] is None]

ui.metric_row([
    ("Patterns present", f"{len(triggered)}", "worth answering before the review"),
    ("Patterns avoided", f"{len(clear)}", None),
    ("Not observable here", f"{len(advisory)}", "read them anyway"),
], tones=["neg" if triggered else "pos", "pos", ""])

for name, hit, verdict, why in triggered:
    ui.note(f"<b>{name}.</b> {verdict}. {why}", "bad")

for name, hit, verdict, why in clear:
    with st.expander(f"Avoided -- {name}", expanded=False):
        st.markdown(f"**{verdict}**")
        st.caption(why)

st.markdown("**Cannot be seen from a model, and are the most common of all**")
for name, hit, verdict, why in advisory:
    st.markdown(f"- **{name}.** {why}")

# --------------------------------------------------------------------------
ui.section("The programme shape",
           f"A realistic enterprise exit runs {broadcom.TOTAL_ELAPSED[0]} from "
           "mobilisation to full decommission.")

for key, name, duration, outcome, actions in broadcom.PHASES:
    with st.container(border=True):
        c1, c2 = st.columns([1, 3.4])
        c1.markdown(f"**{key}**")
        c1.caption(duration)
        c2.markdown(f"**{name}**")
        c2.caption(outcome)
        with c2.expander("What has to happen", expanded=False):
            for a in actions:
                st.markdown(f"- {a}")

ui.note(broadcom.TOTAL_ELAPSED[1], "warn")

modelled = res.schedule_summary.get("elapsed_months", 0.0)
ui.takeaway(
    f"This model puts wave execution at <b>{modelled:.1f} months</b>. That is "
    "Phase 3 only. It excludes the six weeks of Phase 0 that establish the "
    "contract position, the discovery and dependency observation window of Phase "
    "1, the landing zone build in Phase 2, and the decommission in Phase 4 that "
    "actually ends the double-run cost. Quote the wave number as the wave number, "
    "not as the programme.")
