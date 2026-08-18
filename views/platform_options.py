"""Target platform alternatives, including the on-premises Azure options."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core import broadcom, platforms, scenario, tco, ui

sc = scenario.get_scenario()
res = scenario.current()
cur = sc.commercial.currency
s = res.estate_summary

ui.page_header(
    "Target platforms",
    "Azure public cloud is one destination among several, and a business case that has not "
    "been tested against the alternatives is not a business case. This includes the "
    "on-premises Azure options - Azure Local and Azure Stack Hub - which answer the residency "
    "objection without giving up cloud tooling, and the non-VMware hypervisors that solve the "
    "licensing problem without leaving the data centre.",
)

ui.takeaway(
    "Change the priority selector live, in front of the client, and let them watch the ranking "
    "move. It converts \"why Azure?\" from an assertion into a decision they made themselves. "
    "Two answers usually surprise people: <b>Azure VMware Solution</b> is the fastest exit and "
    "rarely the cheapest destination, and <b>Azure Local</b> removes the Broadcom licence "
    "entirely without the workload ever leaving the building.")

tab_rank, tab_cost, tab_local, tab_detail = st.tabs(
    ["Decision matrix", "Cost comparison", "Azure Local deep dive", "All options"])

# --------------------------------------------------------------------------
with tab_rank:
    # The objective is scenario state, set on Start here. Changing it here changes
    # it everywhere, rather than producing a ranking that disagrees with the one
    # the briefing was written from.
    _obj = sc.objective if sc.objective in platforms.PRIORITIES else platforms.DEFAULT_PRIORITY
    c1, c2 = st.columns([1, 2])
    priority = c1.selectbox(
        "What matters most to this client?", platforms.PRIORITIES,
        index=platforms.PRIORITIES.index(_obj),
        help="Set on Start here and shared with every page. Changing it here "
             "changes the stated objective for the whole model.")
    if priority != sc.objective:
        scenario.update(objective=priority)
        st.rerun()
    custom = c2.toggle("Set my own criteria weights", False)

    if not sc.objective:
        ui.note(
            "No objective has been stated, so this is ranked on the source assessment's "
            "own recommended weighting. Pick one above, or on <b>Start here</b>, and the "
            "ranking becomes an answer to a question rather than a general scorecard.",
            "warn")

    weights = None
    if custom:
        weights = {}
        keys = list(platforms.CRITERIA)
        for chunk in [keys[i:i + 4] for i in range(0, len(keys), 4)]:
            cols = st.columns(len(chunk))
            for col, k in zip(cols, chunk):
                weights[k] = col.slider(
                    platforms.CRITERIA[k], 0.0, 3.0, 1.0, 0.1, key=f"pw_{k}",
                    help=f"The source paper bands this criterion as "
                         f"**{platforms.CRITERION_WEIGHT.get(k, 'not listed')}**.")

    ranked = platforms.rank_platforms(priority, weights)

    fig = go.Figure(go.Bar(
        x=ranked["fit_score"], y=ranked["platform"], orientation="h",
        marker_color=[ui.PALETTE[2] if i == 0 else
                      (ui.PALETTE[0] if i < 3 else ui.PALETTE[7])
                      for i in range(len(ranked))],
        text=[f"{v:.0f}" for v in ranked["fit_score"]], textposition="auto"))
    fig.update_layout(height=520, title=f"Platform fit for: {priority}",
                      xaxis_title="Weighted fit score (0-100)",
                      yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig, width="stretch")

    top = ranked.iloc[0]
    ui.note(f"<b>Best fit: {top['platform']}</b> -- {top['summary']}<br><br>"
            f"<i>Best when:</i> {top['best_when']}")

    # A fit score says how well a platform suits the estate. It does not say
    # whether the platform achieves the stated objective, and for anyone leaving
    # Broadcom that is the only question that decides the shortlist.
    st.markdown("### Does it actually remove the Broadcom dependency?")
    verdicts = []
    for name in ranked["platform"]:
        dep, arch, fit = broadcom.dependency_for(name)
        verdicts.append({
            "Platform": name,
            "Broadcom dependency": dep,
            "Archetype": f"{arch} -- {broadcom.ARCHETYPE_BY_KEY[arch].name}",
            "Strategic fit": fit,
            "Fit score": float(ranked.loc[ranked["platform"] == name,
                                          "fit_score"].iloc[0]),
        })
    vf = pd.DataFrame(verdicts)

    relocated = vf[vf["Broadcom dependency"] == broadcom.RELOCATED]["Platform"].tolist()
    retained = vf[vf["Broadcom dependency"] == broadcom.RETAINED]["Platform"].tolist()
    if relocated:
        ui.note(
            "<b>These do not remove the Broadcom relationship, they relocate it: "
            + ", ".join(relocated) + ".</b> Since the hyperscaler licensing change, "
            "a managed VMware service requires a portable VCF subscription that you "
            "buy from Broadcom directly. The node price falls and the subscription "
            "becomes a line item on your own paper. If the objective is to leave "
            "Broadcom, these are bridges with a decommission date, not destinations.",
            "bad")
    if retained:
        ui.note("<b>These keep the Broadcom subscription as it is: "
                + ", ".join(retained) + ".</b> Legitimate as a control case in the "
                "business case, and as a negotiating position. Not an exit.", "warn")

    st.dataframe(
        vf.style.format({"Fit score": "{:.0f}"}),
        hide_index=True, width="stretch")
    st.caption(
        "There is a genuine upside in the relocated case: the portable subscription "
        "is portable. The same entitlement can cover on-premises hosts, managed "
        "cloud hosts, or a mix, and can shift between them as the estate moves -- "
        "which turns residual Broadcom spend into a transition instrument rather "
        "than a sunk cost. It only works if the migration sequencing and the "
        "renewal term are negotiated together.")

    with st.expander("The five archetypes, and why the choice is really between them",
                     expanded=False):
        st.caption(
            "Fourteen products resolve into five architectural answers. Framing a "
            "steering committee discussion around the archetype keeps it at the "
            "right altitude; the product choice inside an archetype is a later and "
            "much smaller decision.")
        st.dataframe(pd.DataFrame([{
            "Archetype": f"{a.key} -- {a.name}",
            "Broadcom dependency": a.dependency,
            "Operating model change": a.ops_change,
            "Best suited to": a.best_for} for a in broadcom.ARCHETYPES]),
            hide_index=True, width="stretch")

    # ---- three matrices, not one -------------------------------------------
    # A single wide matrix compresses exactly the nuance that decides this, so
    # the comparison is split into the three views the source assessment uses:
    # strategic fit, enterprise readiness, and commercial and risk shape.
    st.markdown("### How they score, in three views")
    st.caption(
        "Split deliberately. One wide matrix across sixteen criteria compresses the "
        "nuance that matters -- a platform can be an excellent strategic fit and an "
        "unacceptable enterprise risk, and a single averaged row hides that.")

    _MATRICES = [
        ("Strategic fit",
         "Does it deliver the objective, and what does getting there cost?",
         ["broadcom_exit", "exit_speed", "migration_effort", "modernisation",
          "run_cost"]),
        ("Enterprise readiness",
         "Can a regulated estate actually run on it?",
         ["feature_parity", "resilience", "compliance", "ops_burden", "skills_fit",
          "data_residency", "latency_control"]),
        ("Commercial and risk shape",
         "What are you exposed to once you are on it?",
         ["vendor_risk", "lock_in", "exit_cost", "hardware_impact"]),
    ]

    for title, subtitle, keys in _MATRICES:
        st.markdown(f"**{title}** &nbsp;&mdash;&nbsp; {subtitle}")
        heat = ranked.set_index("platform")[keys]
        heat.columns = [
            f"{platforms.CRITERIA[c].split('(')[0].strip()}"
            f"{'' if platforms.CRITERION_WEIGHT.get(c) in (None, 'Added here') else chr(10) + '(' + platforms.CRITERION_WEIGHT[c] + ')'}"
            for c in keys]
        fig = px.imshow(heat, color_continuous_scale=ui.SEQUENTIAL, aspect="auto",
                        labels=dict(color="Score 1-5"), text_auto=True,
                        zmin=1, zmax=5)
        fig.update_layout(height=460, xaxis_title="", yaxis_title="",
                          xaxis=dict(side="top", tickangle=-30),
                          margin=dict(t=110))
        st.plotly_chart(fig, width="stretch")

    st.caption(
        "Scores are 1-5 and deliberately opinionated; each is defensible from the "
        "trade-offs listed on the All options tab. The band in brackets is the weight "
        "the source assessment recommends for that criterion -- one Critical, six High, "
        "six Medium. Three criteria carry no band because they are scored here and not "
        "in the source: residency, latency and lock-in.")

# --------------------------------------------------------------------------
with tab_cost:
    st.markdown("### Sizing the alternatives against this estate")

    c1, c2, c3, c4 = st.columns(4)
    avs_node = c1.selectbox("AVS node type", list(platforms.AVS_NODES), index=0)
    vcpu_ratio = c2.slider("vCPU per physical core", 1.0, 12.0, 4.0, 0.5,
                           help="The consolidation ratio the current estate actually achieves.")
    vcf_rate = c3.number_input("VCF subscription per core/year", 0.0, 600.0, 135.0, 5.0,
                               help="Since November 2025 new AVS nodes require a portable VCF "
                                    "subscription bought separately from Broadcom.")
    node_capex = c4.number_input("Azure Local node capex", 10000.0, 200000.0, 46000.0, 1000.0)

    al_inputs = platforms.AzureLocalInputs(
        total_vcpu=s["total_vcpu"], total_ram_gib=s["total_ram_tib"] * 1024,
        provisioned_tib=s["provisioned_tib"], vcpu_per_physical_core=vcpu_ratio,
        node_capex=node_capex,
        apply_hybrid_benefit=sc.commercial.apply_ahb_windows,
        windows_share_pct=s["windows_pct"])
    al = platforms.azure_local_cost(al_inputs)

    avs = platforms.size_avs(s["total_vcpu"], s["total_ram_tib"] * 1024, s["used_tib"],
                             node=avs_node, vcpu_per_core=vcpu_ratio)

    cmp = platforms.platform_cost_comparison(
        res.cost_summary["monthly_total"], res.onprem_monthly, al, avs,
        vcf_per_core_year=vcf_rate)

    fig = go.Figure(go.Bar(
        x=cmp["monthly_cost"], y=cmp["platform"], orientation="h",
        marker_color=[ui.PALETTE[2] if v < res.onprem_monthly else ui.PALETTE[3]
                      for v in cmp["monthly_cost"]],
        text=[f"{ui.compact_money(v, cur)}/mo   ({d:+.0f}%)"
              for v, d in zip(cmp["monthly_cost"], cmp["vs_stay_pct"])],
        textposition="auto"))
    fig.update_layout(height=330, title="Monthly run rate by destination",
                      xaxis_title=f"{cur}/month", yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig, width="stretch")

    disp = cmp.copy()
    disp["monthly_cost"] = disp["monthly_cost"].map(lambda v: ui.money(v, cur))
    disp["annual_cost"] = disp["annual_cost"].map(lambda v: ui.money(v, cur))
    disp["vs_stay_pct"] = disp["vs_stay_pct"].map(lambda v: f"{v:+.1f}%")
    st.dataframe(disp.rename(columns={
        "platform": "Destination", "monthly_cost": "Monthly", "annual_cost": "Annual",
        "vs_stay_pct": "vs staying on VMware", "basis": "How it is sized"}),
        hide_index=True, width="stretch",
        column_config={"How it is sized": st.column_config.TextColumn(width="large")})

    ui.metric_row([
        ("AVS hosts required", f"{avs['hosts']} x {avs['node']}",
         f"bound by {avs['binding_constraint'].lower()}"),
        ("Azure Local nodes", f"{al['nodes']}", f"{al['physical_cores']:,} physical cores"),
        ("Current VMware hosts", f"{res.onprem.hosts}", None),
        ("AVS three-host minimum",
         "not binding" if avs["hosts"] > 3 else "binding", None),
    ])

    if avs["hosts"] > 6:
        avs_cost = cmp.loc[cmp["platform"] == "Azure VMware Solution", "monthly_cost"].iloc[0]
        ui.note(
            f"<b>Azure VMware Solution needs {avs['hosts']} hosts for this estate, bound by "
            f"{avs['binding_constraint'].lower()}.</b> AVS is dedicated hardware sold by "
            "capacity, not consumption, so the whole estate's memory footprint has to be "
            f"bought whether it is used or not. At {ui.compact_money(avs_cost, cur)} per month "
            "plus a separately-purchased VCF subscription, AVS is the fastest exit and rarely "
            "the cheapest destination. Treat it as a staging platform with a dated exit plan, "
            "not an endpoint.", "warn")

    st.markdown("### AVS sizing detail")
    st.dataframe(pd.DataFrame([
        {"Constraint": "CPU", "Hosts needed": f"{avs['by_cpu']:.1f}",
         "Basis": f"{s['total_vcpu']:,} vCPU at {vcpu_ratio:g}:1 on "
                  f"{avs['spec']['cores']} cores/host"},
        {"Constraint": "Memory", "Hosts needed": f"{avs['by_ram']:.1f}",
         "Basis": f"{s['total_ram_tib']:.1f} TiB at 80% utilisation on "
                  f"{avs['spec']['ram_gib']} GiB/host"},
        {"Constraint": "vSAN capacity", "Hosts needed": f"{avs['by_storage']:.1f}",
         "Basis": f"{s['used_tib']:.1f} TiB x {platforms.AVS_STORAGE_SLACK} overhead on "
                  f"{avs['spec']['nvme_tib']} TiB/host"},
    ]), hide_index=True, width="stretch")

# --------------------------------------------------------------------------
with tab_local:
    st.markdown("### Azure Local -- Azure in your own data centre")
    ui.note(
        "Azure Local (formerly Azure Stack HCI) is the closest Azure equivalent to AWS "
        "Outposts, and the most direct like-for-like replacement for vSphere on-premises. "
        "It runs Microsoft's own stack on validated hardware in your building, managed through "
        "the Azure portal via Arc, and it removes the Broadcom licence entirely - without the "
        "workload ever leaving the site.")

    c1, c2, c3, c4, c5 = st.columns(5)
    cores_node = c1.number_input("Physical cores per node", 16, 128, 48, 4,
                                 key="al_cores")
    ram_node = c2.number_input("RAM per node (GiB)", 128.0, 6144.0, 1024.0, 128.0,
                               key="al_ram")
    node_capex_local = c3.number_input("Node capex", 10000.0, 200000.0, 46000.0, 1000.0,
                                       key="al_capex")
    ext_san = c4.toggle("External SAN storage", False,
                        help="External SAN support raises the service fee from $10.00 to "
                             "$20.10 per physical core per month.")
    ahb = c5.toggle("Apply Azure Hybrid Benefit", sc.commercial.apply_ahb_windows,
                    help="Without it, Windows Server guest rights are charged at $23.30 per "
                         "physical core per month for unlimited guest VMs.")

    al2 = platforms.azure_local_cost(platforms.AzureLocalInputs(
        total_vcpu=s["total_vcpu"], total_ram_gib=s["total_ram_tib"] * 1024,
        provisioned_tib=s["provisioned_tib"], cores_per_node=int(cores_node),
        ram_gib_per_node=float(ram_node), external_san=ext_san,
        apply_hybrid_benefit=ahb, windows_share_pct=s["windows_pct"],
        node_capex=float(node_capex_local)))

    ui.metric_row([
        ("Nodes required", f"{al2['nodes']}", f"{al2['physical_cores']:,} physical cores"),
        ("Annual cost", ui.compact_money(al2["annual_total"], cur), None),
        ("Monthly cost", ui.compact_money(al2["monthly_total"], cur), None),
        ("vs staying on VMware",
         f"{(al2['monthly_total'] - res.onprem_monthly) / res.onprem_monthly * 100:+.0f}%",
         None),
        ("vs Azure public cloud",
         f"{(al2['monthly_total'] - res.cost_summary['monthly_total']) / max(res.cost_summary['monthly_total'], 1) * 100:+.0f}%",
         None),
    ])

    c1, c2 = st.columns([1.3, 1])
    with c1:
        bd = al2["breakdown"]
        fig = go.Figure(go.Bar(
            x=bd["annual_cost"], y=bd["component"], orientation="h",
            marker_color=ui.PALETTE[0],
            text=[f"{ui.compact_money(v, cur)} ({p:.0f}%)"
                  for v, p in zip(bd["annual_cost"], bd["share_pct"])],
            textposition="auto"))
        fig.update_layout(height=340, title="Azure Local annual cost breakdown",
                          xaxis_title=f"{cur}/year", yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, width="stretch")
    with c2:
        st.markdown("**Pricing model**")
        st.write({
            "Service fee": f"${platforms.AZURE_LOCAL_CORE_MONTH_EXTERNAL_SAN if ext_san else platforms.AZURE_LOCAL_CORE_MONTH:.2f}"
                           " per physical core per month",
            "Windows guest rights": "Waived by Azure Hybrid Benefit" if ahb else
                                    f"${platforms.AZURE_LOCAL_WINDOWS_GUEST_CORE_MONTH:.2f} "
                                    "per core per month",
            "Free period": f"{platforms.AZURE_LOCAL_FREE_DAYS} days",
            "VMware licence": "None required",
            "Minimum cluster": "1 node",
        })

    st.dataframe(al2["breakdown"].rename(columns={
        "component": "Component", "annual_cost": "Annual", "basis": "Basis",
        "share_pct": "Share %"}).round(1), hide_index=True, width="stretch",
        column_config={"Basis": st.column_config.TextColumn(width="large")})

    st.markdown("### What to know before recommending it")
    for n in al2["notes"]:
        st.markdown(f"- {n}")

    plat = platforms.platforms_frame()
    row = plat[plat["platform"].str.startswith("Azure Local")].iloc[0]
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**In its favour**")
        for x in row["pros"]:
            st.success(x)
    with c2:
        st.markdown("**Against it**")
        for x in row["cons"]:
            st.warning(x)

    st.markdown("### The other on-premises Azure options")
    for name in ["Azure Stack Hub", "Azure Arc only"]:
        r = plat[plat["platform"].str.startswith(name)].iloc[0]
        with st.expander(f"{r['platform']} -- {r['location']}"):
            st.markdown(r["summary"])
            st.markdown(f"**Cost model.** {r['cost_model']}")
            c1, c2 = st.columns(2)
            with c1:
                for x in r["pros"]:
                    st.success(x)
            with c2:
                for x in r["cons"]:
                    st.warning(x)
            st.info(f"**Best when:** {r['best_when']}")

# --------------------------------------------------------------------------
with tab_detail:
    plat = platforms.platforms_frame()
    fam = st.multiselect("Family", sorted(plat["family"].unique()))
    view = plat[plat["family"].isin(fam)] if fam else plat

    for _, r in view.iterrows():
        with st.expander(f"{r['platform']}  |  {r['family']}  |  {r['location']}"):
            st.markdown(r["summary"])
            st.markdown(f"**Cost model.** {r['cost_model']}")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**In its favour**")
                for x in r["pros"]:
                    st.markdown(f"- {x}")
            with c2:
                st.markdown("**Against it**")
                for x in r["cons"]:
                    st.markdown(f"- {x}")
            st.info(f"**Best when:** {r['best_when']}")
            scores = pd.DataFrame([{platforms.CRITERIA[k]: r[k] for k in platforms.CRITERIA}])
            st.dataframe(scores, hide_index=True, width="stretch")

# --------------------------------------------------------------------------
# Evaluated and not shortlisted. Deliberately not scored -- scoring implies
# candidacy -- but recorded, because the evaluation's completeness is itself
# the commercial lever the negotiated-renewal scenario is priced on.
# --------------------------------------------------------------------------
    ui.section(
        "Evaluated and not shortlisted",
        "Recorded so the evaluation can be shown to be comprehensive. None of "
        "these is a candidate destination here, and none is scored above -- but "
        "being able to answer \"did you look at OpenStack?\" is worth more at a "
        "renewal negotiation than the modelling effort it costs.")

    st.dataframe(
        pd.DataFrame([{"Platform": n, "Position": pos, "Why not a candidate here": why}
                      for n, pos, why in platforms.EVALUATED_NOT_SHORTLISTED]),
        hide_index=True, width="stretch",
        column_config={"Position": st.column_config.TextColumn(width="large"),
                       "Why not a candidate here":
                           st.column_config.TextColumn(width="large")})

    ui.note(
        "A documented alternatives evaluation is the strongest commercial lever available "
        "at renewal, and its value comes from being complete rather than from being "
        "favourable. These six are recorded for that reason. Together with the "
        f"{len(platforms.platforms_frame())} scored options above, the evaluation covers "
        "every destination in the source assessment.")
