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

from core import broadcom, risks, scenario, ui

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

tab_seg, tab_risk, tab_shape, tab_next = st.tabs(
    ["Segmentation & failure modes", "Risk register", "Programme shape",
     "Checkpoints & next steps"])

# ==========================================================================
with tab_seg:
    ui.section("Where this estate sits against the benchmark",
               "Indicative shares for a typical enterprise estate. Being outside a "
               "band is a prompt to explain, not a fault -- but it is better to be "
               "asked here than at a steering committee.")

    counts = sized["strategy"].value_counts().to_dict()
    rows = broadcom.segmentation_scorecard(counts, len(sized))
    _why = {sg.name: sg.rationale for sg in broadcom.SEGMENTS}
    board = pd.DataFrame([{
        "Segment": r["segment"], "VMs": r["vms"], "Share": f"{r['pct']:.1f}%",
        "Typical band": r["band"], "Position": r["verdict"].title(),
        "Natural destination": r["destination"],
        "Why that destination": _why.get(r["segment"], "")} for r in rows])
    st.dataframe(
        board, hide_index=True, width="stretch",
        column_config={"Natural destination": st.column_config.TextColumn(width="medium"),
                       "Why that destination": st.column_config.TextColumn(width="large")})

    ui.note(
        "<b>The Relocate row is the one to read aloud.</b> Its destination is AVS as a "
        "time-boxed bridge <i>or NC2 on Azure</i> -- and NC2 should be evaluated against "
        "AVS specifically, because it carries no Broadcom requirement and AVS does. A "
        "relocate segment that defaults to AVS without that comparison having been made "
        "is the anti-pattern this whole application exists to prevent: spending a "
        "migration budget to move the licence rather than remove it.")

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

# ==========================================================================
with tab_risk:
    ui.section(
        "Fifteen risks, scored against this scenario",
        "A register that is only ever read is a document. Most of these are "
        "observable in the model the rest of this application has already "
        "computed, so they are checked rather than listed -- and the ones no "
        "model can see are still read out, because they are usually the ones "
        "that bite.")

    _ms = broadcom.milestone_status(broadcom.MILESTONES[0])
    risk_facts = {
        "renewal_days_remaining": _ms["days"],
        "avs_vms": facts["avs_vms"],
        "dual_run_months": facts["dual_run_months"],
        "observation_days": float(st.session_state.get("migrate_cfg").profiling_days_elapsed
                                  if st.session_state.get("migrate_cfg") else 0.0),
        "agentless_replication": True,
        "platform_overhead_pct": float(sc.commercial.platform_overhead_pct),
        "dr_enabled": bool(sc.commercial.dr_enabled),
        "backup_enabled": bool(sc.commercial.backup_enabled),
        "appliance_blockers": facts["appliance_blockers"],
        "elapsed_months": facts["elapsed_months"],
        "azure_local_vms": int((sized["target_service"] == "Azure Local").sum()),
    }
    rows = risks.check_register(risk_facts)
    rsum = risks.summary(rows)

    ui.metric_row([
        ("Risks triggered", f"{rsum['triggered']}", "present in this scenario now"),
        ("High-impact triggered", f"{rsum['high_triggered']}",
         "these go to the steering committee"),
        ("Currently clear", f"{rsum['clear']}", "testable and not exhibited"),
        ("Not observable here", f"{rsum['advisory']}", "confirm with the programme"),
        ("Register size", f"{rsum['total']}", "R01 to R15"),
    ], tones=["neg" if rsum["triggered"] else "pos",
              "neg" if rsum["high_triggered"] else "pos", "pos", "", ""])

    if not st.session_state.get("migrate_cfg"):
        ui.note(
            "R04 is being scored against a zero-day observation window because the "
            "Azure Migrate simulator has not been opened in this session. Open "
            "<b>Azure Migrate &amp; tooling</b> and the window it models is used here "
            "instead.")

    _TONE = {risks.TRIGGERED: "bad", risks.CLEAR: "", risks.ADVISORY: "warn"}
    _LABEL = {risks.TRIGGERED: "Present", risks.CLEAR: "Clear",
              risks.ADVISORY: "Advisory"}

    st.dataframe(
        pd.DataFrame([{
            "ID": r["id"], "Risk": r["risk"], "Impact": r["impact"],
            "Status": _LABEL[r["status"]], "What the model shows": r["observation"],
            "Owner": r["owner"]} for r in rows]),
        hide_index=True, width="stretch", height=560,
        column_config={"Risk": st.column_config.TextColumn(width="large"),
                       "What the model shows":
                           st.column_config.TextColumn(width="large")})

    st.markdown("### Triggered now, with the mitigation")
    _live = [r for r in rows if r["status"] == risks.TRIGGERED]
    if _live:
        for r in _live:
            ui.note(
                f"<b>{r['id']} &mdash; {r['risk']}</b><br>"
                f"<i>{r['observation']}.</i><br><br>"
                f"<b>Mitigation.</b> {r['mitigation']}<br>"
                f"<b>Owner.</b> {r['owner']} &nbsp;|&nbsp; <b>Impact.</b> {r['impact']}",
                "bad" if r["impact"] == risks.HIGH else "warn")
    else:
        ui.note("No risk in the register is currently triggered by this scenario. That is "
                "worth checking rather than celebrating -- it usually means an input is "
                "optimistic rather than that the programme is safe.", "warn")

    with st.expander("The three the model cannot see", expanded=False):
        st.caption(
            "Programme conditions rather than model outputs. They are the reason the "
            "register belongs in the client's own risk tooling at mobilisation, "
            "reviewed at every steering committee, rather than living only here.")
        for r in rows:
            if r["status"] != risks.ADVISORY:
                continue
            st.markdown(f"**{r['id']} &mdash; {r['risk']}**")
            st.caption(f"{r['mitigation']}  \n*Owner: {r['owner']} · Impact: {r['impact']}*")

    ui.takeaway(
        "Take the triggered rows to the steering committee with the observation attached, "
        "not the whole register. A risk register presented in full gets skimmed; four rows "
        "that each name a number from this week's model get acted on. Then transfer the "
        "whole register into the client's own risk tooling at mobilisation, because that "
        "is where it has to live to be reviewed.")

# ==========================================================================
with tab_shape:
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


# ==========================================================================
with tab_next:
    ui.section(
        "Decision checkpoints",
        "The phases say what happens. These say who decides what, on what "
        "evidence. A checkpoint without named evidence is a meeting rather than "
        "a gate, and it is the first thing to slip.")

    st.dataframe(
        pd.DataFrame([{
            "ID": cid, "Checkpoint": name, "Question to answer": question,
            "Evidence required": evidence, "Decision owner": owner}
            for cid, name, question, evidence, owner in broadcom.CHECKPOINTS]),
        hide_index=True, width="stretch",
        column_config={"Question to answer": st.column_config.TextColumn(width="medium"),
                       "Evidence required": st.column_config.TextColumn(width="large")})

    ui.note(
        "<b>DC3 is the one this application exists to serve.</b> Its evidence is the "
        "three-scenario business case and the scored matrices re-run against the client's "
        "own weightings -- both of which are on screen elsewhere here. The others need "
        "artefacts this model does not hold: an entitlement inventory, a policy compliance "
        "report, restore-test evidence, core release tracking.")

    ui.section(
        "The first ninety days",
        "Sequenced so the negotiation and the discovery run in parallel. The "
        "observation window is the long pole and it starts before the platform "
        "decision, not after it.")

    cols = st.columns(len(broadcom.NEXT_STEPS))
    for col, (horizon, actions) in zip(cols, broadcom.NEXT_STEPS):
        with col:
            with st.container(border=True):
                st.markdown(f"**{horizon}**")
                for a in actions:
                    st.markdown(f"- {a}")

    _ms = broadcom.milestone_status(broadcom.MILESTONES[0])
    ui.takeaway(
        f"The 30-day column is not a plan, it is a countdown. The nearest modelled "
        f"deadline is <b>{_ms['label']}</b> away, and the 30-day observation window has to "
        "start regardless of where the platform decision lands -- discovery data is the "
        "input to the negotiation and to the migration plan equally. A programme that "
        "waits for the platform decision before starting discovery has spent its "
        "negotiating leverage on a decision it could have made later with better data.")
