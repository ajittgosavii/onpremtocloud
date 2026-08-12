"""Cost simulator, priced against live Azure retail rates."""

from dataclasses import replace

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core import azure_catalog as cat
from core import costing, pricing, scenario, ui

sc = scenario.get_scenario()
res = scenario.current()
cur = sc.commercial.currency
cs = res.cost_summary

ui.page_header(
    "Azure cost simulator",
    "Every rate on this page is pulled live from Microsoft's Azure Retail Prices API for "
    f"{cat.REGIONS[sc.commercial.region]['label']} - VM hours, reserved instance and savings "
    "plan terms, managed disk tiers, backup, Site Recovery and egress. Nothing here is a "
    "hard-coded estimate.",
)

st.markdown(ui.pricing_badge(res.price_book.source)
            + f"<span class='pill'>{res.cost_summary['priced_from_api_pct']:.0f}% of VMs matched "
              "to a live meter</span>"
            + f"<span class='pill'>{len(res.price_book.vm):,} VM meters</span>"
            + f"<span class='pill'>{len(res.price_book.disk):,} disk meters</span>",
            unsafe_allow_html=True)

# --------------------------------------------------------------------------
with st.expander("Commercial levers", expanded=True):
    p = sc.commercial
    c1, c2, c3, c4 = st.columns(4)
    commitment = c1.selectbox(
        "Compute commitment", ["none", "ri-1y", "ri-3y", "sp-1y", "sp-3y"],
        index=["none", "ri-1y", "ri-3y", "sp-1y", "sp-3y"].index(p.commitment),
        format_func=lambda v: {"none": "Pay-as-you-go", "ri-1y": "Reserved Instance, 1 year",
                               "ri-3y": "Reserved Instance, 3 year",
                               "sp-1y": "Savings plan, 1 year",
                               "sp-3y": "Savings plan, 3 year"}[v],
        help="Reservations are cheaper but lock to a VM family and region. Savings plans are "
             "slightly dearer and far more flexible.")
    coverage = c2.slider("Commitment coverage of production (%)", 0, 100,
                         int(p.commitment_coverage_pct),
                         help="Committing 100% of a portfolio you are still migrating is how "
                              "organisations end up paying for unused reservations.")
    ahb = c3.toggle("Azure Hybrid Benefit", p.apply_ahb_windows,
                    help="Removes the Windows Server licence component for VMs covered by "
                         "Software Assurance.")
    ahb_cov = c4.slider("Windows VMs with eligible SA (%)", 0, 100, int(p.ahb_coverage_pct),
                        disabled=not ahb)

    c5, c6, c7, c8 = st.columns(4)
    sched = c5.toggle("Schedule non-production off-hours", p.nonprod_schedule)
    hours = c6.slider("Non-production hours per week", 20, 168, int(p.nonprod_hours_per_week),
                      disabled=not sched,
                      help="168 is 24x7. 55 is roughly 11 hours a day, five days a week.")
    backup = c7.toggle("Azure Backup enabled", p.backup_enabled)
    redundancy = c8.selectbox("Vault redundancy", ["GRS", "LRS"],
                              index=0 if p.backup_redundancy == "GRS" else 1,
                              disabled=not backup)

    c9, c10, c11, c12 = st.columns(4)
    dr = c9.toggle("Disaster recovery (Site Recovery)", p.dr_enabled)
    dr_cov = c10.selectbox("DR coverage",
                           ["Tier 0 only", "Tier 0 + Tier 1", "All production"],
                           index=["Tier 0 only", "Tier 0 + Tier 1",
                                  "All production"].index(p.dr_coverage),
                           disabled=not dr)
    overhead = c11.slider("Landing zone overhead (%)", 0, 30, int(p.platform_overhead_pct),
                          help="Hub network, firewall, bastion, private endpoints, Log "
                               "Analytics, Defender for Cloud and management VMs. Azure "
                               "Migrate's own estimate excludes all of this.")
    discount = c12.slider("Negotiated EA / CSP discount (%)", 0.0, 25.0,
                          float(p.negotiated_discount_pct), 0.5)

    egress = st.slider("Monthly internet egress (GB)", 0, 100000,
                       int(p.monthly_egress_gb), step=500,
                       help=f"Charged at {ui.money(res.price_book.egress_gb, cur, 3)}/GB above "
                            "the free 100 GB, from the live API.")

    new = replace(p, commitment=commitment, commitment_coverage_pct=float(coverage),
                  apply_ahb_windows=ahb, ahb_coverage_pct=float(ahb_cov),
                  nonprod_schedule=sched, nonprod_hours_per_week=float(hours),
                  backup_enabled=backup, backup_redundancy=redundancy,
                  dr_enabled=dr, dr_coverage=dr_cov,
                  platform_overhead_pct=float(overhead),
                  negotiated_discount_pct=float(discount),
                  monthly_egress_gb=float(egress))
    if new != p:
        scenario.update(commercial=new)
        st.rerun()

# --------------------------------------------------------------------------
ui.metric_row([
    ("Monthly Azure run rate", ui.money(cs["monthly_total"], cur),
     f"{ui.compact_money(cs['annual_total'], cur)} per year"),
    ("Unoptimised baseline", ui.money(cs["baseline_monthly"], cur),
     f"-{cs['monthly_saving'] / cs['baseline_monthly'] * 100:.0f}% with levers"),
    ("Average per VM", ui.money(cs["avg_cost_per_vm"], cur, 2),
     f"{cs['vms_costed']:,} VMs costed"),
    ("Avoided by retiring", f"{ui.compact_money(cs['retire_saving_monthly'], cur)}/mo",
     f"{cs['vms_retired']} VMs"),
    ("On-premises today", ui.money(res.onprem_monthly, cur),
     f"{(cs['monthly_total'] - res.onprem_monthly) / res.onprem_monthly * 100:+.0f}%"),
])

ui.takeaway(
    "Open the <b>Live price feed</b> tab when someone asks where these numbers come from. "
    "Every rate is Microsoft's own published retail price, fetched from a public API a few "
    "seconds ago - not a spreadsheet someone maintained last quarter. That is usually the "
    "moment the room starts trusting the model.")

tab_break, tab_levers, tab_top, tab_meters = st.tabs(
    ["Breakdown", "Lever sensitivity", "Cost concentration", "Live price feed"])

# --------------------------------------------------------------------------
with tab_break:
    c1, c2 = st.columns([1.4, 1])
    with c1:
        comp = res.cost_breakdown
        fig = go.Figure(go.Bar(
            x=comp["monthly_cost"], y=comp["component"], orientation="h",
            marker_color=ui.PALETTE[0],
            text=[f"{ui.compact_money(v, cur)}  ({p:.0f}%)"
                  for v, p in zip(comp["monthly_cost"], comp["share_pct"])],
            textposition="auto"))
        fig.update_layout(height=380, title="Monthly cost by component",
                          xaxis_title=f"{cur}/month", yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, width="stretch")
    with c2:
        st.plotly_chart(ui.donut(comp["component"], comp["monthly_cost"], height=380),
                        width="stretch")

    st.markdown("### Cost by dimension")
    dim = st.selectbox("Group by", ["environment", "criticality", "tier", "strategy",
                                    "os_family", "azure_series", "app_name", "cluster"])
    live = res.sized[res.sized["strategy"] != "Retire"]
    g = (live.groupby(dim).agg(vms=("vm_name", "count"),
                               monthly=("monthly_cost", "sum"),
                               compute=("compute_cost", "sum"),
                               storage=("storage_cost", "sum"))
         .reset_index().sort_values("monthly", ascending=False))
    g["per_vm"] = g["monthly"] / g["vms"]
    fig = px.bar(g.head(20), x=dim, y="monthly", color=dim,
                 color_discrete_sequence=ui.PALETTE, title=f"Monthly cost by {dim}")
    fig.update_layout(height=360, showlegend=False, yaxis_title=f"{cur}/month", xaxis_title="")
    st.plotly_chart(fig, width="stretch")
    st.dataframe(g.head(30).round(2), hide_index=True, width="stretch")

# --------------------------------------------------------------------------
with tab_levers:
    st.markdown("### What each lever is actually worth")
    st.caption("Each row turns one lever off and reprices the whole estate. The delta is what "
               "that lever contributes to the plan.")
    lev = costing.lever_sensitivity(res.sized, res.price_book, sc.commercial)
    lev_disp = lev.copy()
    lev_disp["monthly_cost"] = lev_disp["monthly_cost"].map(lambda v: ui.money(v, cur))
    lev_disp["delta_vs_plan"] = lev.apply(
        lambda r: f"{'+' if r['delta_vs_plan'] >= 0 else '-'}"
                  f"{ui.money(abs(r['delta_vs_plan']), cur)} ({r['delta_pct']:+.1f}%)", axis=1)
    st.dataframe(lev_disp[["lever", "monthly_cost", "delta_vs_plan"]].rename(
        columns={"lever": "If this lever were removed", "monthly_cost": "Monthly cost",
                 "delta_vs_plan": "Change vs the current plan"}),
        hide_index=True, width="stretch")

    fig = go.Figure(go.Bar(
        x=lev["delta_vs_plan"], y=lev["lever"], orientation="h",
        marker_color=[ui.PALETTE[3] if v > 0 else ui.PALETTE[2] for v in lev["delta_vs_plan"]],
        text=[ui.compact_money(v, cur) for v in lev["delta_vs_plan"]], textposition="auto"))
    fig.update_layout(height=300, title="Monthly cost impact of removing each lever",
                      xaxis_title=f"{cur}/month", yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig, width="stretch")

    ui.note(
        "Two of these are decisions, not switches. Reservations and savings plans are "
        "contractual commitments that are painful to unwind, so the coverage percentage "
        "should follow the migration curve rather than being set at 100% on day one. Azure "
        "Hybrid Benefit depends on Software Assurance the client may or may not hold - "
        "confirm it before the saving appears in a business case.")

    st.markdown("### Commitment term comparison")
    rows = []
    for c in ["none", "ri-1y", "ri-3y", "sp-1y", "sp-3y"]:
        pol = replace(sc.commercial, commitment=c,
                      commitment_coverage_pct=0 if c == "none" else sc.commercial.commitment_coverage_pct)
        t = costing.compute_costs(res.sized, res.price_book, pol)
        t = t[t["strategy"] != "Retire"]["monthly_cost"].sum()
        rows.append({"Commitment": {"none": "Pay-as-you-go", "ri-1y": "RI 1 year",
                                    "ri-3y": "RI 3 year", "sp-1y": "Savings plan 1 year",
                                    "sp-3y": "Savings plan 3 year"}[c],
                     "Monthly cost": t})
    cdf = pd.DataFrame(rows)
    base = cdf.loc[cdf["Commitment"] == "Pay-as-you-go", "Monthly cost"].iloc[0]
    cdf["Saving vs PAYG"] = (base - cdf["Monthly cost"]) / base * 100
    st.dataframe(cdf.assign(**{"Monthly cost": cdf["Monthly cost"].map(lambda v: ui.money(v, cur)),
                               "Saving vs PAYG": cdf["Saving vs PAYG"].map(lambda v: f"{v:.1f}%")}),
                 hide_index=True, width="stretch")

# --------------------------------------------------------------------------
with tab_top:
    live = res.sized[res.sized["strategy"] != "Retire"].copy()
    live = live.sort_values("monthly_cost", ascending=False)
    live["cum_pct"] = live["monthly_cost"].cumsum() / live["monthly_cost"].sum() * 100

    n80 = int((live["cum_pct"] <= 80).sum()) + 1
    ui.note(
        f"<b>{n80} VMs ({n80 / len(live) * 100:.0f}% of the estate) account for 80% of the "
        "Azure bill.</b> Optimisation effort belongs there. The long tail is where automation "
        "and standard patterns belong.")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=list(range(1, len(live) + 1)), y=live["cum_pct"],
                             mode="lines", line=dict(width=3, color=ui.PALETTE[0]),
                             name="Cumulative cost"))
    fig.add_hline(y=80, line_dash="dash", line_color="rgba(180,73,95,.7)",
                  annotation_text="80% of spend")
    fig.update_layout(height=340, title="Cost concentration",
                      xaxis_title="VMs ranked by cost", yaxis_title="Cumulative % of spend")
    st.plotly_chart(fig, width="stretch")

    st.markdown("### Most expensive VMs")
    top = live.head(30)[["vm_name", "app_name", "environment", "azure_sku", "azure_vcpu",
                         "azure_ram_gib", "total_alloc_gib", "compute_cost", "storage_cost",
                         "monthly_cost"]].round(2)
    st.dataframe(top, hide_index=True, width="stretch", height=420)
    ui.df_download(live, "azure_costs_per_vm.csv", "Download full per-VM costing")

# --------------------------------------------------------------------------
with tab_meters:
    st.markdown("### Raw vendor price feed")
    st.caption(
        "Fetched from `https://prices.azure.com/api/retail/prices` "
        "(api-version 2023-01-01-preview). Unauthenticated, Microsoft's own published retail "
        "rates. Cached locally for 24 hours so the app keeps working offline.")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Virtual machine rates** (per hour)")
        vm = res.price_book.vm.copy()
        used = set(res.sized["azure_sku"].unique())
        vm["in_plan"] = vm["arm_sku_name"].isin(used)
        vm = vm.sort_values(["in_plan", "linux_hr"], ascending=[False, True])
        st.dataframe(
            vm[["arm_sku_name", "linux_hr", "windows_hr", "win_licence_hr", "in_plan"]]
            .rename(columns={"arm_sku_name": "SKU", "linux_hr": "Linux",
                             "windows_hr": "Windows", "win_licence_hr": "Windows licence",
                             "in_plan": "Used in this plan"}).round(4),
            hide_index=True, width="stretch", height=340)
    with c2:
        st.markdown("**Managed disk rates** (per month)")
        st.dataframe(res.price_book.disk.rename(
            columns={"kind": "Disk type", "tier": "Tier", "price_month": "Monthly",
                     "price_per_10k_ops": "Per 10k operations"}).round(4),
            hide_index=True, width="stretch", height=340)

    st.markdown("**Other live rates**")
    other = pd.DataFrame([
        {"Meter": "Internet egress (above the free 100 GB)",
         "Rate": f"{ui.money(res.price_book.egress_gb, cur, 4)} per GB"},
        {"Meter": "Azure Backup protected instance (per 500 GB block)",
         "Rate": f"{ui.money(res.price_book.backup['instance_month'], cur, 2)} per month"},
        {"Meter": "Azure Backup, SQL Server in an Azure VM",
         "Rate": f"{ui.money(res.price_book.backup['sql_instance_month'], cur, 2)} per month"},
        {"Meter": "Backup vault storage, LRS",
         "Rate": f"{ui.money(res.price_book.backup['lrs_gb_month'], cur, 4)} per GB/month"},
        {"Meter": "Backup vault storage, GRS",
         "Rate": f"{ui.money(res.price_book.backup['grs_gb_month'], cur, 4)} per GB/month"},
        {"Meter": "Azure Site Recovery, VM replicated to Azure",
         "Rate": f"{ui.money(res.price_book.asr_instance, cur, 2)} per instance/month "
                 "(free for the first 180 days when used for migration)"},
    ])
    st.dataframe(other, hide_index=True, width="stretch")

    if st.button("Force a refresh from the vendor API"):
        st.cache_data.clear()
        st.session_state.pop("_pipeline_token", None)
        st.rerun()
