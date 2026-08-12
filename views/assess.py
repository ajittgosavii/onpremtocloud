"""Assessment: right-sizing, Azure readiness and 7R disposition."""

from dataclasses import replace

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core import assessment, rightsizing, scenario, ui

sc = scenario.get_scenario()

ui.page_header(
    "Readiness & 7R",
    "Three judgements, made independently and shown separately: what size the workload really "
    "needs, whether Azure can run it at all, and what should actually happen to it. Each one "
    "is explainable down to the individual VM.",
)

# --------------------------------------------------------------------------
with st.expander("Sizing and disposition policy", expanded=True):
    c1, c2, c3, c4 = st.columns(4)
    mode = c1.selectbox(
        "Sizing basis", ["performance", "as-provisioned"],
        index=0 if sc.sizing.mode == "performance" else 1,
        format_func=lambda m: {"performance": "Performance-based",
                               "as-provisioned": "As on-premises"}[m],
        help="Azure Migrate offers exactly these two. Performance-based is where the saving "
             "is; as-provisioned is what you fall back to when the data is thin.")
    pct = c2.selectbox("Percentile", ["p50", "p90", "p95", "p99"],
                       index=["p50", "p90", "p95", "p99"].index(sc.sizing.percentile),
                       help="Azure Migrate defaults to p95.")
    comfort = c3.slider("Comfort factor", 1.0, 2.0, sc.sizing.comfort_factor, 0.05,
                        help="Azure Migrate defaults to 1.3. It multiplies measured "
                             "utilisation, not headroom.")
    gen = c4.selectbox("VM generation", ["v5 only", "v5 and v6", "v6 only"],
                       index={(5,): 0, (5, 6): 1, (6,): 2}.get(sc.sizing.generations, 0))

    c5, c6, c7, c8 = st.columns(4)
    burst = c5.toggle("Allow burstable (B-series)", sc.sizing.allow_burstable,
                      help="B-series is the right answer for genuinely idle VMs and the wrong "
                           "answer for anything with sustained load.")
    amd = c6.toggle("Prefer AMD sizes", sc.sizing.prefer_amd,
                    help="AMD sizes are typically around 10% cheaper at equal capacity.")
    storage = c7.selectbox(
        "Storage policy", ["performance-matched", "all-premium", "cost-optimised"],
        index=["performance-matched", "all-premium", "cost-optimised"].index(
            sc.sizing.storage_policy))
    to_used = c8.toggle("Size disks to consumed, not provisioned", sc.sizing.size_disks_to_used,
                        help="VMware thin provisioning means provisioned is far above consumed. "
                             "Azure Migrate sizes to provisioned.")

    c9, c10, c11, c12 = st.columns(4)
    appetite = c9.selectbox(
        "Modernisation appetite", ["lift-and-shift", "balanced", "aggressive"],
        index=["lift-and-shift", "balanced", "aggressive"].index(sc.modernisation_appetite),
        help="Shifts the boundary between rehost and replatform.")
    retire = c10.toggle("Retire idle VMs", sc.retire_zombies)
    repurchase = c11.toggle("Allow repurchase to SaaS", sc.allow_repurchase)
    avs = c12.toggle("Use AVS for blocked VMs", sc.avs_for_blockers,
                     help="Off means blocked VMs are retained on-premises instead.")

    gen_map = {"v5 only": (5,), "v5 and v6": (5, 6), "v6 only": (6,)}
    new_sizing = replace(sc.sizing, mode=mode, percentile=pct, comfort_factor=comfort,
                         generations=gen_map[gen], allow_burstable=burst, prefer_amd=amd,
                         storage_policy=storage, size_disks_to_used=to_used)
    if (new_sizing != sc.sizing or appetite != sc.modernisation_appetite
            or retire != sc.retire_zombies or repurchase != sc.allow_repurchase
            or avs != sc.avs_for_blockers):
        scenario.update(sizing=new_sizing, modernisation_appetite=appetite,
                        retire_zombies=retire, allow_repurchase=repurchase,
                        avs_for_blockers=avs)
        st.rerun()

res = scenario.current()
sized = res.sized
ss = res.sizing_summary
cur = sc.commercial.currency

ui.takeaway(
    "Three separate judgements, deliberately kept apart. <b>Right-sizing</b> is what the "
    "workload needs, <b>readiness</b> is whether Azure can run it at all, and <b>disposition</b> "
    "is what should actually happen to it. Conflating them is how estates end up rehosted "
    "onto oversized VMs that still cannot start. Every verdict on this page traces to the "
    "individual VM on the last tab.")

tab_size, tab_ready, tab_7r, tab_vm = st.tabs(
    ["Right-sizing", "Azure readiness", "7R disposition", "Per-VM detail"])

# --------------------------------------------------------------------------
with tab_size:
    ui.metric_row([
        ("Source vCPU", f"{ss['source_vcpu']:,}", None),
        ("Azure vCPU", f"{ss['target_vcpu']:,}", f"-{ss['vcpu_saved_pct']:.1f}%"),
        ("Source RAM", f"{ss['source_ram_tib']:.1f} TiB", None),
        ("Azure RAM", f"{ss['target_ram_tib']:.1f} TiB", f"-{ss['ram_saved_pct']:.1f}%"),
        ("Distinct SKUs", f"{ss['distinct_skus']}", f"{ss['burstable_count']} burstable"),
    ])

    if ss["vcpu_saved_pct"] < 25 and sc.sizing.mode == "performance":
        ui.note(
            f"Only {ss['vcpu_saved_pct']:.0f}% of vCPU is harvested despite a mean utilisation "
            f"of {res.estate_summary['mean_cpu_pct']:.0f}%. This is the comfort factor at work: "
            f"at {sc.sizing.comfort_factor:g}x, a VM at 70% CPU is sized for "
            f"{70 * sc.sizing.comfort_factor:.0f}% and does not shrink. Azure sizes are also "
            "discrete, so a 6-vCPU VM lands on an 8-vCPU SKU. Business cases that assume a "
            "blanket 30-40% right-sizing saving are usually wrong for this reason.", "warn")

    if ss["upsized_count"]:
        ui.note(
            f"<b>{ss['upsized_count']} VMs are allocated more vCPU in Azure than they have "
            "today.</b> That is SKU granularity plus the 2-vCPU floor, not a modelling error - "
            "but it is worth knowing before someone spots it in the output.", "warn")

    storage_ratio = ss["target_storage_tib"] / max(ss["source_storage_tib"], 1)
    if storage_ratio > 1.3:
        ui.note(
            f"<b>{ss['source_storage_tib']:,.0f} TiB provisioned becomes "
            f"{ss['target_storage_tib']:,.0f} TiB of billed managed disk "
            f"({storage_ratio:.2f}x).</b> Azure managed disks are sold in fixed tiers - a "
            "130 GiB disk is billed as a 256 GiB P15 - and on Premium SSD v1 you buy capacity "
            "to get IOPS. Two things fix this: consolidate volumes before migrating, and use "
            "Premium SSD v2, which decouples IOPS and throughput from capacity.", "warn")

    c1, c2 = st.columns(2)
    with c1:
        skus = (sized.groupby(["azure_series", "azure_sku"]).size()
                .reset_index(name="vms").sort_values("vms", ascending=False).head(18))
        fig = px.bar(skus, x="vms", y="azure_sku", color="azure_series", orientation="h",
                     color_discrete_sequence=ui.PALETTE, title="Recommended Azure VM sizes")
        fig.update_layout(height=470, yaxis=dict(autorange="reversed", title=""),
                          xaxis_title="VMs")
        ui.legend_top(fig)
        st.plotly_chart(fig, width="stretch")

    with c2:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=sized["vcpu"], y=sized["azure_vcpu"], mode="markers",
            marker=dict(size=7, color=sized["cpu_avg_pct"], colorscale="Blues",
                        showscale=True, colorbar=dict(title="Mean<br>CPU %")),
            text=sized["vm_name"], name="VMs"))
        mx = max(sized["vcpu"].max(), sized["azure_vcpu"].max())
        fig.add_trace(go.Scatter(x=[0, mx], y=[0, mx], mode="lines", name="No change",
                                 line=dict(dash="dash", color="rgba(128,128,128,.6)")))
        fig.update_layout(height=470, title="Source vCPU vs Azure vCPU",
                          xaxis_title="On-premises vCPU", yaxis_title="Azure vCPU")
        ui.legend_top(fig)
        st.plotly_chart(fig, width="stretch")
        st.caption("Points below the line shrank. Points above were rounded up by SKU "
                   "granularity or the minimum size floor.")

    st.markdown("### Storage tiering")
    tiers = (sized.groupby(["os_disk_kind"]).agg(
        vms=("vm_name", "count"),
        allocated_tib=("total_alloc_gib", lambda x: x.sum() / 1024)).reset_index())
    tiers.columns = ["Disk type (OS disk)", "VMs", "Total allocated TiB"]
    st.dataframe(tiers, hide_index=True, width="stretch")

# --------------------------------------------------------------------------
with tab_ready:
    r = res.readiness
    cols = st.columns(len(r) if len(r) else 1)
    for col, (_, row) in zip(cols, r.iterrows()):
        col.metric(row["readiness"], f"{int(row['vms']):,}", f"{row['share_pct']:.1f}%")

    c1, c2 = st.columns([1, 1.5])
    with c1:
        st.plotly_chart(ui.donut(r["readiness"], r["vms"],
                                 colour_map=ui.READINESS_COLOURS, height=340),
                        width="stretch")
    with c2:
        by_env = (sized.groupby(["environment", "readiness"]).size()
                  .reset_index(name="vms"))
        fig = px.bar(by_env, x="environment", y="vms", color="readiness",
                     color_discrete_map=ui.READINESS_COLOURS, title="Readiness by environment")
        fig.update_layout(height=340, xaxis_title="", yaxis_title="VMs")
        ui.legend_top(fig)
        st.plotly_chart(fig, width="stretch")

    st.markdown("### Findings across the estate")
    b = res.blockers.copy()
    if len(b):
        b = b.rename(columns={"severity": "Severity", "finding": "Finding", "vms": "VMs"})
        st.dataframe(b, hide_index=True, width="stretch", height=380,
                     column_config={"Finding": st.column_config.TextColumn(width="large")})
        ui.df_download(res.blockers, "readiness_findings.csv")
    else:
        st.success("No readiness findings.")

    nr = sized[sized["readiness"] == assessment.NOT_READY]
    if len(nr):
        st.markdown("### VMs that cannot move to native Azure IaaS")
        st.caption("Each needs remediation, a different target platform, or an exception. "
                   "These are the ones to look at first - they set the critical path.")
        show = nr[["vm_name", "app_name", "environment", "criticality", "guest_os",
                   "strategy", "target_service", "readiness_detail"]]
        st.dataframe(show, hide_index=True, width="stretch", height=320,
                     column_config={"readiness_detail":
                                    st.column_config.TextColumn("Why", width="large")})

# --------------------------------------------------------------------------
with tab_7r:
    d = res.disposition
    cols = st.columns(len(d) if len(d) else 1)
    for col, (_, row) in zip(cols, d.iterrows()):
        col.metric(row["strategy"], f"{int(row['vms']):,}", f"{row['share_pct']:.0f}%")

    c1, c2 = st.columns([1.3, 1])
    with c1:
        by_env = sized.groupby(["environment", "strategy"]).size().reset_index(name="vms")
        fig = px.bar(by_env, x="environment", y="vms", color="strategy",
                     color_discrete_map=ui.STRATEGY_COLOURS,
                     title="Disposition by environment")
        fig.update_layout(height=380, xaxis_title="", yaxis_title="VMs")
        ui.legend_top(fig)
        st.plotly_chart(fig, width="stretch")
    with c2:
        st.plotly_chart(ui.donut(d["strategy"], d["vms"],
                                 colour_map=ui.STRATEGY_COLOURS, height=380),
                        width="stretch")

    st.markdown("### Target services")
    tg = (sized.groupby(["strategy", "target_service"]).size().reset_index(name="vms")
          .sort_values("vms", ascending=False))
    st.dataframe(tg.rename(columns={"strategy": "Strategy",
                                    "target_service": "Azure target", "vms": "VMs"}),
                 hide_index=True, width="stretch")

    st.markdown("### Why each strategy was chosen")
    for strat in [s for s in assessment.STRATEGIES if s in sized["strategy"].unique()]:
        sub = sized[sized["strategy"] == strat]
        with st.expander(f"{strat} - {len(sub):,} VMs"):
            st.markdown(f"**Representative rationale:** {sub['strategy_rationale'].iloc[0]}")
            st.dataframe(
                sub[["vm_name", "app_name", "environment", "criticality", "tier",
                     "db_engine", "target_service"]].head(60),
                hide_index=True, width="stretch", height=260)

# --------------------------------------------------------------------------
with tab_vm:
    st.markdown("### Inspect a single VM")
    pick = st.selectbox("VM", sorted(sized["vm_name"].unique()))
    row = sized[sized["vm_name"] == pick].iloc[0]

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**Source**")
        st.write({
            "Application": row["app_name"], "Environment": row["environment"],
            "Criticality": row["criticality"], "Tier": row["tier"],
            "Guest OS": row["guest_os"], "vCPU": int(row["vcpu"]),
            "RAM GiB": float(row["ram_gib"]),
            "Provisioned GiB": float(row["provisioned_gib"]),
            "Mean CPU %": float(row["cpu_avg_pct"]) if pd.notna(row["cpu_avg_pct"]) else None,
            "p95 CPU %": float(row["cpu_p95_pct"]) if pd.notna(row["cpu_p95_pct"]) else None,
        })
    with c2:
        st.markdown("**Azure target**")
        st.write({
            "VM size": row["azure_sku"], "Series": row["azure_series"],
            "vCPU": int(row["azure_vcpu"]), "RAM GiB": float(row["azure_ram_gib"]),
            "OS disk": f"{row['os_disk_tier']} ({row['os_disk_kind']})",
            "Data disks": row["data_disk_tiers"] or "none",
            "Allocated GiB": float(row["total_alloc_gib"]),
            "Monthly cost": ui.money(float(row.get("monthly_cost", 0)), cur, 2),
        })
    with c3:
        st.markdown("**Verdict**")
        st.write({
            "Readiness": row["readiness"], "Strategy": row["strategy"],
            "Target service": row["target_service"],
            "Complexity": float(row.get("complexity", 0)),
            "Complexity band": row.get("complexity_band", ""),
            "Effort (hours)": float(row.get("effort_hours", 0)),
            "Cutover failure risk": f"{float(row.get('cutover_failure_risk', 0)) * 100:.1f}%",
            "Wave": row.get("wave_name", ""),
        })

    st.markdown("**Sizing rationale**")
    st.info(f"{row['sizing_basis']} - {row['sku_rationale']}")
    st.markdown("**Disposition rationale**")
    st.info(row["strategy_rationale"])
    if row["readiness_detail"] != "No issues found.":
        st.markdown("**Readiness findings**")
        for f in (row["blockers"] or []):
            st.error(f)
        for f in (row["conditions"] or []):
            st.warning(f)
