"""Azure Migrate: how the tool actually behaves against this estate, what it
cannot do at all, and what to supplement it with.

The tooling market used to be a page of its own. The source paper treats the two
as one topic -- Azure Migrate is the control plane, and the question that follows
immediately is where to supplement it -- so making the reader assemble that
argument across two pages was the wrong shape.
"""

from dataclasses import replace

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core import azure_migrate_sim as ams
from core import tools_market as tm
from core import assessment, scenario, ui

sc = scenario.get_scenario()
res = scenario.current()
cur = sc.commercial.currency

ui.page_header(
    "Azure Migrate & tooling",
    "Azure Migrate is the default tool for this migration and it is free, well-supported and "
    "genuinely good at what it does. It is also narrower than most plans assume. This page "
    "runs its full lifecycle against your estate with the real product limits applied, sets "
    "out workload by workload everything it will not do for you - and then ranks what to "
    "supplement it with, priced at this estate's scale.",
)

# --------------------------------------------------------------------------
if "migrate_cfg" not in st.session_state:
    st.session_state["migrate_cfg"] = ams.MigrateConfig(
        replication_bandwidth_mbps=sc.wave_plan.bandwidth_mbps,
        bandwidth_share_pct=sc.wave_plan.bandwidth_available_pct,
        wan_efficiency_pct=sc.wave_plan.wan_efficiency_pct)
cfg: ams.MigrateConfig = st.session_state["migrate_cfg"]

with st.expander("Azure Migrate configuration", expanded=True):
    c1, c2, c3, c4 = st.columns(4)
    vcenters = c1.number_input("vCenter servers", 1, 20, cfg.vcenter_count,
                               help="One appliance is required per vCenter.")
    scope = c2.selectbox(
        "Discovery scope",
        ["Metadata only", "Metadata + software inventory",
         "Full (metadata + software inventory + SQL + web apps)"],
        index=2 if "Full" in cfg.discovery_scope else 0)
    dep = c3.selectbox("Dependency analysis", ["Agentless", "Agent-based", "None"],
                       index=["Agentless", "Agent-based", "None"].index(cfg.dependency_mode))
    scaleout = c4.toggle("Deploy scale-out appliance", cfg.use_scaleout_appliance,
                         help="Raises the concurrent replication ceiling from 300 to 500 "
                              "per vCenter.")

    c5, c6, c7, c8 = st.columns(4)
    hist = c5.selectbox("Performance history", [1, 7, 30],
                        index=[1, 7, 30].index(cfg.performance_history_days),
                        format_func=lambda d: {1: "1 day", 7: "1 week", 30: "1 month"}[d])
    elapsed = c6.slider("Days the appliance has actually run", 0, 60,
                        cfg.profiling_days_elapsed)
    sizing = c7.selectbox("Sizing criterion", ["Performance-based", "As on-premises"],
                          index=0 if cfg.sizing_criterion == "Performance-based" else 1)
    comfort = c8.slider("Comfort factor", 1.0, 2.0, cfg.comfort_factor, 0.1)

    c9, c10, c11, c12 = st.columns(4)
    bw = c9.number_input("Replication bandwidth (Mbps)", 10.0, 100000.0,
                         float(cfg.replication_bandwidth_mbps), 50.0)
    share = c10.slider("Share for migration (%)", 5, 100, int(cfg.bandwidth_share_pct))
    batch = c11.number_input("VMs per cutover window", 1, 200, cfg.cutover_batch_size)
    windows = c12.number_input("Cutover windows per week", 1, 7, cfg.cutover_windows_per_week)

    new = replace(cfg, vcenter_count=int(vcenters), discovery_scope=scope,
                  dependency_mode=dep, use_scaleout_appliance=scaleout,
                  performance_history_days=int(hist), profiling_days_elapsed=int(elapsed),
                  sizing_criterion=sizing, comfort_factor=float(comfort),
                  replication_bandwidth_mbps=float(bw), bandwidth_share_pct=float(share),
                  cutover_batch_size=int(batch), cutover_windows_per_week=int(windows))
    if new != cfg:
        st.session_state["migrate_cfg"] = new
        st.rerun()

phases, msum = ams.simulate(res.estate, cfg, sized=res.sized)
plan = msum["appliance_plan"]
st.session_state["migrate_summary"] = {k: v for k, v in msum.items() if k != "appliance_plan"}
# Published separately so the wave plan page can check its design principles
# against what this simulator actually modelled.
st.session_state["migrate_appliance_plan"] = plan
st.session_state["migrate_test_pct"] = float(cfg.test_migration_pct)

coverage = ams.coverage_assessment(res.estate)
fully = float(coverage.iloc[0]["share_pct"]) if len(coverage) else 0.0

ui.metric_row([
    ("Appliances required", f"{plan['total_appliances']}",
     f"{plan['discovery_appliances']} discovery + {plan['scaleout_appliances']} scale-out"),
    ("Concurrent replication ceiling", f"{plan['max_concurrent_replications']}",
     f"{plan['disks_replicating_at_once']} disks in flight"),
    ("Performance coverage", f"{msum['coverage_pct']:.0f}%",
     f"{msum['confidence_stars']}/5 star confidence"),
    ("End-to-end duration", f"{msum['critical_path_days']:,.0f} days",
     f"{msum['critical_path_days'] / 30.44:.1f} months"),
    ("Fully covered by the tool", f"{fully:.0f}% of VMs",
     "the rest needs something else"),
])

if msum["confidence_stars"] < 4:
    ui.note(
        f"<b>Performance coverage is {msum['coverage_pct']:.0f}%, giving a "
        f"{msum['confidence_stars']}-star confidence rating.</b> Microsoft's own guidance is "
        "that below 80% coverage you should switch to as-on-premises sizing rather than trust "
        "performance-based recommendations. Let the appliance profile for longer before "
        "anyone builds a business case on these numbers.", "warn")

ui.takeaway(
    f"Azure Migrate takes only <b>{fully:.0f}% of this estate end to end</b>. That is not a "
    "criticism of the tool - it is free, supported, and the right backbone for a rehost. It "
    "is a statement about scope. The <b>Limitations</b>, <b>Heterogeneous workloads</b> and "
    "<b>Database migration</b> tabs quantify the other "
    f"{100 - fully:.0f}%, which is work that has to be done by something else and is almost "
    "always missing from a plan built on the assessment alone. Being the person who raises "
    "this first is worth a great deal of credibility - and the last two tabs say what to "
    "supplement it with, and what that costs.")

(tab_life, tab_limits, tab_hetero, tab_db, tab_appl, tab_ready, tab_supp,
 tab_market) = st.tabs(
    ["Lifecycle", "Limitations", "Heterogeneous workloads", "Database migration",
     "Appliance & limits", "Adoption checklist", "Where to supplement it",
     "The tooling market"])

# ==========================================================================
with tab_life:
    st.markdown("### The ten phases, run against your estate")

    pf = ams.phases_frame(phases, sc.start_date)
    fig = px.timeline(pf, x_start="start", x_end="end", y="phase",
                      color="duration_days", color_continuous_scale=ui.SEQUENTIAL,
                      title="Azure Migrate lifecycle")
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(height=90 + 42 * len(pf), xaxis_title="", yaxis_title="",
                      coloraxis_showscale=False)
    st.plotly_chart(fig, width="stretch")
    st.caption("Performance profiling and dependency analysis run concurrently - they are the "
               "two long poles you can overlap. Everything else is sequential.")

    for ph in phases:
        with st.expander(f"{ph.name}  -  {ph.duration_days:,.1f} days", expanded=False):
            st.markdown(ph.detail)
            c1, c2 = st.columns(2)
            if ph.prerequisites:
                with c1:
                    st.markdown("**Prerequisites**")
                    for x in ph.prerequisites:
                        st.markdown(f"- {x}")
            if ph.outputs:
                with (c2 if ph.prerequisites else c1):
                    st.markdown("**Outputs**")
                    for x in ph.outputs:
                        st.markdown(f"- {x}")
            if ph.gotchas:
                st.markdown("**What goes wrong here**")
                for g in ph.gotchas:
                    st.warning(g)
            if ph.metrics:
                st.caption(" | ".join(f"{k}: {v:,.1f}" if isinstance(v, float) else f"{k}: {v}"
                                      for k, v in ph.metrics.items()))

    st.markdown("### Replication feasibility")
    c1, c2 = st.columns([1.3, 1])
    with c1:
        repl = next(p for p in phases if p.key == "replication")
        m = repl.metrics
        fig = go.Figure(go.Bar(
            x=[m["seed_days"], m["delta_days"]],
            y=["Initial seed", "Delta sync to cutover"], orientation="h",
            marker_color=[ui.PALETTE[0], ui.PALETTE[1]],
            text=[f"{m['seed_days']:.1f} d", f"{m['delta_days']:.1f} d"],
            textposition="auto"))
        fig.update_layout(height=250, title="Replication time at the configured bandwidth",
                          xaxis_title="Days", yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, width="stretch")
    with c2:
        st.metric("Usable throughput", f"{msum['usable_gib_per_hour']:,.0f} GiB/hour")
        st.metric("Data to seed", f"{msum['total_tib']:,.1f} TiB")
        st.metric("Mean daily churn", f"{repl.metrics['mean_churn_pct']:.1f}%")

    if repl.metrics["delta_days"] > repl.metrics["seed_days"]:
        ui.note(
            "<b>Delta sync takes longer than the initial seed.</b> That is the warning sign "
            "that churn is close to outrunning the link. If the ratio worsens, the busiest "
            "VMs will never converge and will need a different replication method entirely.",
            "warn")

# ==========================================================================
with tab_limits:
    st.markdown("### What Azure Migrate does not do")
    ui.note(
        "None of this makes Azure Migrate the wrong choice - it is still the right backbone for "
        "this migration. But every item below is work that has to be done by something else, "
        "and a plan built from the Azure Migrate assessment alone will not have budgeted for "
        "any of it.")

    st.markdown("#### Coverage of your estate")
    cov = coverage.copy()
    fig = go.Figure(go.Bar(
        x=cov["vms"], y=cov["category"], orientation="h",
        marker_color=[ui.PALETTE[2] if i == 0 else
                      (ui.PALETTE[1] if i < 4 else ui.PALETTE[3])
                      for i in range(len(cov))],
        text=[f"{v:,} ({p:.0f}%)" for v, p in zip(cov["vms"], cov["share_pct"])],
        textposition="auto"))
    fig.update_layout(height=330, title="How far Azure Migrate takes each VM",
                      xaxis_title="VMs", yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig, width="stretch")

    st.dataframe(cov.rename(columns={
        "category": "Outcome", "vms": "VMs", "share_pct": "Share %",
        "what_it_means": "What it means", "also_needs": "Also needs"}).round(1),
        hide_index=True, width="stretch",
        column_config={"What it means": st.column_config.TextColumn(width="large"),
                       "Also needs": st.column_config.TextColumn(width="medium")})

    ui.note(
        f"<b>Only {fully:.0f}% of this estate is taken end to end by Azure Migrate alone.</b> "
        "The other "
        f"{100 - fully:.0f}% either needs remediation first, needs a second tool, or arrives in "
        "Azure carrying the same problem it had on-premises. That gap is the honest scope of "
        "the programme.", "warn")

    st.markdown("#### Limitations register")
    lim = ams.limitations_frame(res.estate)

    c1, c2 = st.columns([1, 3])
    sev_filter = c1.multiselect("Severity", ams.SEVERITY_ORDER,
                                default=["Blocker", "Major"])
    area_filter = c2.multiselect("Area", sorted(lim["area"].unique()))

    view = lim
    if sev_filter:
        view = view[view["severity"].isin(sev_filter)]
    if area_filter:
        view = view[view["area"].isin(area_filter)]

    sev_icon = {"Blocker": "[!]", "Major": "[*]", "Moderate": "[-]", "Minor": "[.]"}
    for _, r in view.iterrows():
        affected = (f"  |  affects ~{int(r['vms_affected']):,} VMs "
                    f"({r['share_pct']:.0f}%)" if r["vms_affected"] else "")
        with st.expander(f"{sev_icon.get(r['severity'], '')}  [{r['area']}]  "
                         f"{r['limitation']}{affected}"):
            st.markdown(f"**What it means.** {r['detail']}")
            st.markdown(f"**Impact on this programme.** {r['impact']}")
            st.success(f"**Compensating control.** {r['workaround']}")

    st.markdown("#### Limitations by area")
    by_area = (lim.groupby(["area", "severity"]).size().reset_index(name="count"))
    fig = px.bar(by_area, x="area", y="count", color="severity",
                 color_discrete_map={"Blocker": ui.PALETTE[3], "Major": ui.PALETTE[1],
                                     "Moderate": ui.PALETTE[0], "Minor": ui.PALETTE[7]},
                 title="Limitations by area and severity")
    fig.update_layout(height=340, xaxis_title="", yaxis_title="Limitations")
    ui.legend_top(fig)
    st.plotly_chart(fig, width="stretch")
    ui.df_download(lim, "azure_migrate_limitations.csv")

# ==========================================================================
with tab_hetero:
    st.markdown("### Heterogeneous workload migration")
    ui.note(
        "Azure Migrate rehosts a guest OS and its disks. Any migration that changes the "
        "<i>kind</i> of thing being run - the engine, the runtime, the CPU architecture, the "
        "protocol, the platform - is entirely outside its scope. These are the categories that "
        "surface after the assessment has been signed off, and they are where migration "
        "programmes actually overrun.")

    cat = st.selectbox("Category", ["All"] + ams.HETERO_CATEGORIES)
    het = ams.heterogeneous_frame(cat)

    st.caption(f"{len(het)} migration path(s). Every one of them is work Azure Migrate does "
               "not do.")

    for _, r in het.iterrows():
        with st.expander(f"[{r['category']}]  {r['source']}  ->  {r['target']}"):
            c1, c2, c3 = st.columns(3)
            c1.metric("Automatable", f"{r['automation_pct']}%")
            c2.metric("Effort", f"{r['effort_per_unit_days']:g} days per {r['unit']}")
            c3.metric("Unit", r["unit"])
            st.error(f"**Azure Migrate:** {r['azure_migrate']}")
            st.markdown(f"**Tooling.** {r['tool']}")
            st.markdown(f"**What has to be converted.** {r['conversion']}")
            st.markdown("**Risks**")
            for risk in r["risks"]:
                st.markdown(f"- {risk}")

    st.markdown("### Automation coverage across categories")
    fig = px.scatter(
        ams.heterogeneous_frame(), x="automation_pct", y="effort_per_unit_days",
        color="category", hover_name="source", hover_data=["target", "unit"],
        color_discrete_sequence=ui.PALETTE, log_y=True,
        title="Automation versus effort - bottom-right is easy, top-left is a programme")
    fig.update_layout(height=470, xaxis_title="% automatable by tooling",
                      yaxis_title="Days per unit (log)")
    ui.legend_top(fig)
    ui.log_ticks(fig, "y", (0.1, 0.5, 1, 5, 10, 50, 100))
    st.plotly_chart(fig, width="stretch")
    ui.note(
        "The top-left quadrant - low automation, high effort per unit - is where mainframe, "
        "IBM i, non-x86 architectures and ETL platforms live. If any of those exist in the "
        "estate they must be identified in discovery and scoped separately. They will not "
        "appear in a VMware inventory at all, which is exactly why they get missed.")

# ==========================================================================
with tab_db:
    st.markdown("### Database migration: the gap in the plan")
    ui.note(
        "Azure Migrate <b>discovers and assesses</b> SQL Server, and recommends a target. It "
        "then stops. It migrates no database of any kind, and it has no capability at all for "
        "heterogeneous moves such as Oracle to PostgreSQL. If you rehost the VM with Azure "
        "Migrate you get the database engine lifted as-is - which delivers none of the benefit "
        "the assessment just recommended.", "bad")

    impact = ams.db_estate_impact(res.estate)
    if len(impact):
        c1, c2 = st.columns([1, 1.4])
        with c1:
            st.plotly_chart(ui.donut(impact["engine"], impact["vms"],
                                     title="Database engines in the estate", height=340),
                            width="stretch")
        with c2:
            st.dataframe(impact.rename(columns={
                "engine": "Engine", "vms": "VMs",
                "azure_migrate_covers": "What Azure Migrate gives you",
                "needs": "What you still need"}),
                hide_index=True, width="stretch",
                column_config={"What you still need":
                               st.column_config.TextColumn(width="large")})

    st.markdown("### Choose a target for each engine")
    st.caption("The choice drives the effort. Homogeneous moves are days per database; "
               "heterogeneous moves are weeks.")

    engines = [e for e in res.estate["db_engine"].unique() if e != "None"]
    targets = {}
    cols = st.columns(min(len(engines), 3) or 1)
    for i, eng in enumerate(sorted(engines)):
        opts = [p["target"] for p in ams.DB_MIGRATION_PATHS if p["source"] == eng]
        if not opts:
            continue
        targets[eng] = cols[i % len(cols)].selectbox(
            f"{eng} ->", opts, key=f"dbt_{eng}")

    if targets:
        eff = ams.db_effort_estimate(res.estate, targets,
                                     sc.effort.blended_rate_per_hour,
                                     sc.effort.productive_hours_per_day)
        if len(eff):
            total_days = float(eff["total_days"].sum())
            total_cost = float(eff["cost"].sum())
            ui.metric_row([
                ("Database workstream effort", f"{total_days:,.0f} person-days",
                 f"{total_days / 21:,.1f} person-months"),
                ("Database workstream cost", ui.compact_money(total_cost, cur),
                 "none of this is in the Azure Migrate plan"),
                ("Databases in scope", f"{int(eff['vms'].sum()):,}", None),
                ("Share of total migration cost",
                 f"{total_cost / max(res.effort_summary['migration_cost'], 1) * 100:.0f}%",
                 "on top of the VM migration"),
            ])

            fig = go.Figure(go.Bar(
                x=eff["cost"], y=eff["engine"] + " -> " + eff["target"], orientation="h",
                marker_color=[ui.PALETTE[3] if k.startswith("Hetero") else ui.PALETTE[0]
                              for k in eff["kind"]],
                text=[ui.compact_money(v, cur) for v in eff["cost"]], textposition="auto"))
            fig.update_layout(height=320, title="Database migration cost by engine and target "
                                                "(red = heterogeneous)",
                              xaxis_title=cur, yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig, width="stretch")

            disp = eff.copy()
            disp["cost"] = disp["cost"].map(lambda v: ui.money(v, cur))
            st.dataframe(disp.rename(columns={
                "engine": "Source engine", "vms": "Databases", "target": "Target",
                "kind": "Type", "days_per_db": "Days each", "total_days": "Total days",
                "automation_pct": "Automatable %", "cost": "Cost",
                "azure_migrate_covers_it": "Azure Migrate covers it"}),
                hide_index=True, width="stretch")

            hetero = eff[eff["kind"].str.startswith("Hetero")]
            if len(hetero):
                ui.note(
                    f"<b>{int(hetero['vms'].sum())} databases are on a heterogeneous path, "
                    f"consuming {hetero['total_days'].sum():,.0f} person-days - "
                    f"{hetero['total_days'].sum() / max(total_days, 1) * 100:.0f}% of the whole "
                    "database workstream.</b> Heterogeneous conversion is an application "
                    "programme with its own regression testing, not an infrastructure task. "
                    "Strongly consider rehosting these first to hit the data centre exit date, "
                    "then converting them as a separate, properly-funded phase.", "warn")

    st.markdown("### Migration paths in detail")
    c1, c2 = st.columns(2)
    src = c1.selectbox("Source engine", ["All"] + sorted(
        {p["source"] for p in ams.DB_MIGRATION_PATHS}))
    kind = c2.selectbox("Migration type", ["All", "Homogeneous", "Heterogeneous"])
    paths = ams.db_paths_frame(src, kind)

    for _, r in paths.iterrows():
        with st.expander(f"{r['source']}  ->  {r['target']}   ({r['kind']})"):
            c1, c2, c3 = st.columns(3)
            c1.metric("Automatable", f"{r['automation_pct']}%")
            c2.metric("Effort", f"{r['effort_per_db_days']:g} days/db")
            c3.metric("Downtime", r["downtime"])
            st.error(f"**Azure Migrate:** {r['azure_migrate']}")
            st.markdown(f"**Tooling.** {r['tool']}")
            st.markdown(f"**Schema conversion.** {r['schema_conversion']}")
            st.markdown("**Risks**")
            for risk in r["risks"]:
                st.markdown(f"- {risk}")

# ==========================================================================
with tab_appl:
    st.markdown("### Appliance plan")
    st.info(plan["rationale"])
    st.warning(plan["throughput_caveat"])

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Deployment**")
        st.write({
            "Discovery appliances": plan["discovery_appliances"],
            "Scale-out appliances": plan["scaleout_appliances"],
            "Total": plan["total_appliances"],
            "Per-appliance spec": f"{ams.APPLIANCE_SPEC['vcpu']} vCPU, "
                                  f"{ams.APPLIANCE_SPEC['ram_gib']} GB RAM, "
                                  f"{ams.APPLIANCE_SPEC['disk_gib']} GB disk",
            "Total footprint on source cluster":
                f"{plan['vcpu_footprint']} vCPU, {plan['ram_footprint_gib']} GB RAM",
        })
    with c2:
        st.markdown("**Ceilings that apply to this estate**")
        limits = pd.DataFrame([
            {"Limit": "Servers discovered per appliance",
             "Value": f"{ams.DISCOVERY_LIMIT_PER_APPLIANCE:,}",
             "Your estate": f"{len(res.estate):,}"},
            {"Limit": "Concurrent replications, single appliance",
             "Value": f"{ams.CONCURRENT_REPL_PER_APPLIANCE}",
             "Your estate": f"{plan['max_concurrent_replications']} available"},
            {"Limit": "Concurrent replications with scale-out",
             "Value": f"{ams.CONCURRENT_REPL_WITH_SCALEOUT}", "Your estate": ""},
            {"Limit": "Disks replicating at once per appliance",
             "Value": f"{ams.DISKS_REPLICATING_PER_APPLIANCE}",
             "Your estate": f"{plan['disks_replicating_at_once']} total"},
            {"Limit": "Servers with agentless dependency analysis",
             "Value": f"{ams.AGENTLESS_DEPENDENCY_LIMIT:,}",
             "Your estate": f"{len(res.estate):,}"},
            {"Limit": "Servers per assessment",
             "Value": f"{ams.ASSESSMENT_SERVER_LIMIT:,}", "Your estate": f"{len(res.estate):,}"},
            {"Limit": "Free Site Recovery period per instance",
             "Value": f"{ams.ASR_FREE_DAYS} days",
             "Your estate": f"{res.schedule_summary.get('elapsed_months', 0) * 30.44:.0f} day "
                            "programme"},
        ])
        st.dataframe(limits, hide_index=True, width="stretch")

    if res.schedule_summary.get("elapsed_months", 0) * 30.44 > ams.ASR_FREE_DAYS:
        ui.note(
            f"The programme runs longer than the {ams.ASR_FREE_DAYS}-day free Site Recovery "
            "window. That is fine - the clock is per instance and starts when that VM begins "
            "replicating, not when the programme starts. But do not let VMs sit in replication "
            "for months waiting for a cutover slot; that is when the charge appears.", "warn")

    st.markdown("### What Azure Migrate costs")
    st.info(ams.assessment_cost_note(cfg))

    st.markdown("### Sizing criterion comparison")
    st.caption("The same estate, sized both ways. This is the single largest swing factor in "
               "an Azure Migrate assessment.")
    from dataclasses import replace as _r
    from core import costing, rightsizing
    rows = []
    for m, label in [("performance", "Performance-based"), ("as-provisioned", "As on-premises")]:
        pol = _r(sc.sizing, mode=m)
        s2 = rightsizing.rightsize(res.estate, pol)
        s2["strategy"] = "Rehost"
        s2["is_prod"] = res.estate["is_prod"].values
        c2f = costing.compute_costs(s2, res.price_book, sc.commercial)
        rows.append({"Sizing criterion": label,
                     "Total vCPU": int(s2["azure_vcpu"].sum()),
                     "Total RAM TiB": round(float(s2["azure_ram_gib"].sum()) / 1024, 1),
                     "Monthly cost": float(c2f["monthly_cost"].sum())})
    cmp = pd.DataFrame(rows)
    delta = cmp.iloc[1]["Monthly cost"] - cmp.iloc[0]["Monthly cost"]
    cmp["Monthly cost"] = cmp["Monthly cost"].map(lambda v: ui.money(v, cur))
    st.dataframe(cmp, hide_index=True, width="stretch")
    ui.note(
        f"Choosing as-on-premises sizing over performance-based costs a further "
        f"<b>{ui.money(abs(delta), cur)} per month</b>. That is the price of low confidence - "
        "and the reason it is worth waiting for the appliance to finish profiling.")


# ==========================================================================
# Where to supplement it -- the former Migration tooling page.
#
# The paper's own framing: Azure Migrate is the control plane, and the next
# question is what fills the gap the tabs above just quantified. Keeping that
# on a separate page made the reader join the two arguments themselves.
# ==========================================================================
_eol_share = float(res.estate["os_eol"].mean() * 100)
_blocked_share = float((res.sized["readiness"] == assessment.NOT_READY).mean() * 100)
_n_vms = len(res.estate)

with tab_supp:
    ui.section(
        "What fills the gap",
        f"Azure Migrate covers {fully:.0f}% of this estate end to end. Real programmes run a "
        "stack, not a single tool - and the stack below is derived from this client's own "
        "inventory rather than from a generic vendor list.")

    c1, c2 = st.columns([1, 2])
    scen = c1.selectbox("What is the driving requirement?", tm.SCENARIOS)
    custom = c2.toggle("Set my own dimension weights", False)

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

    st.markdown("### The stack this estate actually needs")
    st.caption(
        f"Derived from your inventory: {_n_vms:,} VMs, {_eol_share:.0f}% on an end-of-life "
        f"guest OS, {_blocked_share:.1f}% blocked from agentless replication, "
        f"{res.estate_summary['db_vms']} VMs carrying a database engine.")

    stack = tm.recommended_stack(scen, _n_vms, _eol_share, _blocked_share)
    for i, s in enumerate(stack, 1):
        with st.container(border=True):
            c1, c2 = st.columns([1, 3])
            c1.markdown(f"**{i}. {s['role']}**")
            c1.markdown("`" + s["tool"] + "`")
            c2.markdown(s["why"])

    ui.note(
        "Nobody buys all of these. The point is that a plan naming only Azure Migrate has "
        "left out dependency mapping, database migration and post-migration optimisation - "
        "and those gaps show up as schedule, not as a line item.")

    st.markdown("### Cost of the recommended stack")
    rows = []
    for s in stack:
        est = tm.tooling_cost_estimate(_n_vms, s["tool"])
        rows.append({"Role": s["role"], "Tool": s["tool"],
                     "Low": est["low"], "High": est["high"],
                     "Per VM": f"{est['per_vm_low']:.0f}-{est['per_vm_high']:.0f}"
                     if est["per_vm_high"] else "no incremental cost"})
    stack_df = pd.DataFrame(rows)
    total_lo, total_hi = stack_df["Low"].sum(), stack_df["High"].sum()
    ui.metric_row([
        ("Stack cost, low", ui.compact_money(total_lo, cur), None),
        ("Stack cost, high", ui.compact_money(total_hi, cur), None),
        ("As % of migration cost",
         f"{total_hi / max(res.effort_summary['migration_cost'], 1) * 100:.0f}%",
         "at the high end"),
        ("Per VM", f"{ui.money(total_hi / max(_n_vms, 1), cur)}", "high end"),
    ])
    disp = stack_df.copy()
    disp["Low"] = disp["Low"].map(lambda v: ui.money(v, cur))
    disp["High"] = disp["High"].map(lambda v: ui.money(v, cur))
    st.dataframe(disp, hide_index=True, width="stretch")

    if st.button("Apply the high-end tooling cost to the effort model"):
        scenario.update(effort=replace(sc.effort,
                                       tooling_cost_per_vm=float(total_hi / max(_n_vms, 1))))
        st.success("Applied. The Complexity & effort page and every downstream figure now "
                   "include it.")
        st.rerun()

# ==========================================================================
with tab_market:
    ui.section("Incremental licence cost at this estate's scale",
               "Order-of-magnitude, based on published list pricing and the discounts commonly "
               "available at 500+ VMs. Zero means either free or already owned.")

    cost = pd.DataFrame([tm.tooling_cost_estimate(_n_vms, t)
                         for t in tm.tools_frame()["tool"]]).sort_values("high",
                                                                        ascending=False)

    fig = go.Figure()
    fig.add_trace(go.Bar(x=cost["low"], y=cost["tool"], orientation="h",
                         name="Low estimate", marker_color=ui.PALETTE[2]))
    fig.add_trace(go.Bar(x=cost["high"] - cost["low"], y=cost["tool"], orientation="h",
                         name="Range to high estimate", marker_color=ui.PALETTE[1]))
    fig.update_layout(barmode="stack", height=560,
                      title=f"Tooling cost for {_n_vms:,} VMs",
                      xaxis_title=cur, yaxis=dict(autorange="reversed"))
    ui.legend_top(fig)
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

    st.markdown("### Capability scores across the market")
    heat = tm.rank_tools(tm.SCENARIOS[0]).set_index("tool")[list(tm.DIMENSIONS)]
    heat.columns = [tm.DIMENSIONS[c] for c in heat.columns]
    fig = px.imshow(heat, color_continuous_scale=ui.SEQUENTIAL, aspect="auto",
                    labels=dict(color="Score 1-5"), text_auto=True)
    fig.update_layout(height=600, xaxis_title="", yaxis_title="",
                      xaxis=dict(side="top", tickangle=-40))
    st.plotly_chart(fig, width="stretch")

    st.markdown("### Every tool, in detail")
    tools = tm.tools_frame()
    cats = st.multiselect("Category", sorted(tools["category"].unique()))
    view = tools[tools["category"].isin(cats)] if cats else tools
    for _, r in view.iterrows():
        with st.expander(f"{r['tool']}  |  {r['vendor']}  |  {r['category']}"):
            st.markdown(f"**Licence.** {r['licence']}")
            st.markdown(f"**Best for.** {r['best_for']}")
            st.warning(f"**Limits.** {r['limits']}")
            st.info(f"**Use when:** {r['use_when']}")
            st.dataframe(pd.DataFrame([{tm.DIMENSIONS[k]: r[k] for k in tm.DIMENSIONS}]),
                         hide_index=True, width="stretch")


# ==========================================================================
# Adoption checklist -- the pre-flight gate.
#
# The Limitations tab says what the tool cannot do. This says what has to be
# true before it is relied on for a production wave. Six items are decisions
# this simulator already models, so they are checked rather than listed; the
# rest stay open, because a checklist that ticks itself is worth nothing at a
# wave gate.
# ==========================================================================
with tab_ready:
    ui.section(
        "Before this tool carries a production wave",
        "Fifteen conditions. The ones this simulator can evidence are checked "
        "against the configuration above; the rest are programme actions and "
        "stay open until somebody does them.")

    _adopt = ams.adoption_status(cfg, msum, res.estate,
                                 float(sc.commercial.platform_overhead_pct))
    _n = {k: sum(1 for r in _adopt if r["status"] == k)
          for k in (ams.VERIFIED, ams.OPEN, ams.PROGRAMME)}

    ui.metric_row([
        ("Evidenced by this model", f"{_n[ams.VERIFIED]} of {len(_adopt)}",
         "checked, not assumed"),
        ("Shown as not satisfied", f"{_n[ams.OPEN]}",
         "the model can see these are open"),
        ("Programme actions", f"{_n[ams.PROGRAMME]}",
         "nothing here can evidence them"),
        ("Ready for a production wave", "No" if _n[ams.OPEN] or _n[ams.PROGRAMME] else "Yes",
         "every line has to be closed"),
    ], tones=["pos", "neg" if _n[ams.OPEN] else "pos", "",
              "neg" if _n[ams.OPEN] or _n[ams.PROGRAMME] else "pos"])

    _LABEL = {ams.VERIFIED: "Verified here", ams.OPEN: "Not satisfied",
              ams.PROGRAMME: "Programme action"}
    st.dataframe(
        pd.DataFrame([{"Status": _LABEL[r["status"]], "Condition": r["item"],
                       "What this model shows": r["note"]} for r in _adopt]),
        hide_index=True, width="stretch", height=560,
        column_config={"Condition": st.column_config.TextColumn(width="large"),
                       "What this model shows":
                           st.column_config.TextColumn(width="medium")})

    for r in _adopt:
        if r["status"] == ams.OPEN:
            ui.note(f"<b>{r['item']}</b><br>{r['note']}.", "bad")

    ui.takeaway(
        "Run this list as a gate, not as a report. Every item on it exists because a "
        "programme somewhere skipped it and lost a wave to something avoidable -- a "
        "pre-existing snapshot that blocked changed block tracking, an observation window "
        "too short to catch month-end, a permission applied at one level of vCenter "
        "instead of five. The "
        f"{_n[ams.VERIFIED]} items checked above are the only ones this model can close "
        f"for you. The other {_n[ams.OPEN] + _n[ams.PROGRAMME]} need somebody's name "
        "against them.")
