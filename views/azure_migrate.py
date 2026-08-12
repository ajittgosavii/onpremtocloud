"""Azure Migrate simulator: how the tool actually behaves against this estate,
and - just as important - what it cannot do at all."""

from dataclasses import replace

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core import azure_migrate_sim as ams
from core import scenario, ui

sc = scenario.get_scenario()
res = scenario.current()
cur = sc.commercial.currency

ui.page_header(
    "Azure Migrate simulator",
    "Azure Migrate is the default tool for this migration and it is free, well-supported and "
    "genuinely good at what it does. It is also narrower than most plans assume. This page "
    "runs its full lifecycle against your estate with the real product limits applied - and "
    "then sets out, workload by workload, everything it will not do for you.",
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
    "this first is worth a great deal of credibility.")

tab_life, tab_limits, tab_hetero, tab_db, tab_appl = st.tabs(
    ["Lifecycle", "Limitations", "Heterogeneous workloads", "Database migration",
     "Appliance & limits"])

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
