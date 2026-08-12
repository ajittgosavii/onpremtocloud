"""Current and future state, side by side, and the flow between them.

The rest of the application answers questions in numbers. This page answers the
one question a room always asks first -- "so what does it actually look like
afterwards?" -- and answers it from the same pipeline, so the picture cannot
drift from the business case.

Nothing here is drawn that the model did not compute. There are no invented
VNets, subnets or landing-zone boxes: every line is a quantity with an engine
behind it, because a diagram is read as fact far more readily than a table is.
"""

import pandas as pd
import streamlit as st

from core import scenario, ui

sc = scenario.get_scenario()
res = scenario.current()
est, sized = res.estate, res.sized
s = res.estate_summary
cur = sc.commercial.currency

ui.page_header(
    "Current & future state",
    "The estate as it stands, the estate as it lands, and every VM's path between "
    "the two. Same pipeline as the business case -- if a number moves there, it "
    "moves here.")

st.markdown(ui.estate_badge(sc.estate_source, sc.estate_label, s["vm_count"])
            + ui.pricing_badge(res.price_book.source)
            + f"<span class='pill'>{sc.commercial.region}</span>",
            unsafe_allow_html=True)

# --------------------------------------------------------------------------
ui.section("The two ends",
           "Left is what discovery found. Right is where the disposition engine "
           "sends it. Both are counts, not concepts.")

decommissioned = int((sized["target_service"] == "Decommission").sum())
landing = (sized.loc[sized["target_service"] != "Decommission", "target_service"]
           .value_counts())
iaas = int(landing.get("Azure VM (IaaS)", 0))
avs = int(landing.get("Azure VMware Solution", 0))
paas = int(landing.sum() - iaas - avs)

ABSENT = "<span style='opacity:.55;font-weight:500'>not in the upload</span>"


def _distinct(column: str, placeholder: str) -> str:
    """Count of distinct values, or a note when the column was defaulted.

    An RVTools vInfo sheet has no datastore column, so the importer fills one
    placeholder value. Reporting that as "1 datastore" would be a fact the
    upload never contained.
    """
    values = est[column].astype(str).unique()
    if len(values) <= 1 and (len(values) == 0 or values[0] == placeholder):
        return ABSENT
    return f"{len(values):,}"


mean_cpu = (f"{s['mean_cpu_pct']:.0f}%" if pd.notna(s["mean_cpu_pct"]) else ABSENT)

left, right = st.columns(2, gap="medium")

with left:
    st.markdown(ui.arch_panel(
        "Current state &mdash; VMware vSphere",
        "As discovered, before any change.",
        [("vSphere clusters", _distinct("cluster", "Unknown")),
         ("ESXi hosts in the inventory", _distinct("esxi_host", "unknown")),
         ("Datastores", _distinct("datastore", "Unknown")),
         ("Virtual machines", f"{s['vm_count']:,}"),
         ("&nbsp;&nbsp;of which powered on", f"{s['powered_on']:,}"),
         ("Windows / Linux", f"{s['windows_pct']:.0f}% / {s['linux_pct']:.0f}%"),
         ("End-of-life guest OS", f"{s['eol_os_count']:,}"),
         ("Allocated vCPU", f"{s['total_vcpu']:,}"),
         ("Allocated RAM", f"{s['total_ram_tib']:.1f} TiB"),
         ("Provisioned storage", f"{s['provisioned_tib']:,.0f} TiB"),
         ("Mean CPU utilisation", mean_cpu)],
        accent=ui.NEGATIVE,
        footer=f"The cost model sizes this as <b>{res.onprem.hosts} hosts</b> at a "
               f"75% memory target, which is the figure behind "
               f"{ui.compact_money(res.onprem_monthly, cur)}/month. Where that "
               "differs from the host count above, the inventory is the fact and "
               "the model is the estimate."), unsafe_allow_html=True)

with right:
    disk_mix = sized.loc[sized["target_service"] != "Decommission", "os_disk_kind"]
    series = (sized.loc[sized["target_service"] == "Azure VM (IaaS)", "azure_series"]
              .value_counts())
    st.markdown(ui.arch_panel(
        f"Future state &mdash; Azure {sc.commercial.region}",
        "As dispositioned by the 7R engine and priced by the cost engine.",
        [("Azure VMs (IaaS)", f"{iaas:,}"),
         ("&nbsp;&nbsp;most common series",
          ", ".join(series.head(3).index) if len(series) else "--"),
         ("Managed-service targets (PaaS/SaaS)", f"{paas:,}"),
         ("Azure VMware Solution", f"{avs:,}"),
         ("Retired, never migrated", f"{decommissioned:,}"),
         ("Right-sized vCPU",
          f"{int(sized.loc[sized['target_service'] != 'Decommission', 'azure_vcpu'].sum()):,}"),
         ("Premium SSD / Standard SSD",
          f"{int((disk_mix == 'Premium SSD').sum()):,} / "
          f"{int((disk_mix == 'Standard SSD').sum()):,}"),
         ("Azure run rate",
          f"{ui.compact_money(res.cost_summary['monthly_total'], cur)}/mo"),
         ("Programme cost",
          ui.compact_money(res.effort_summary["migration_cost"], cur)),
         ("Waves", f"{res.schedule_summary.get('waves', 0):,}"),
         ("Elapsed", f"{res.schedule_summary.get('elapsed_months', 0):.1f} months")],
        accent=ui.POSITIVE,
        footer="Networking, identity and the landing zone itself are priced as an "
               "overhead but not drawn here, because the model does not design "
               "them. That design is a workshop, not an output."),
        unsafe_allow_html=True)

if paas == 0 and sc.estate_source == "upload":
    ui.note(
        "<b>Nothing lands on a managed service</b>, and that is a property of the upload "
        "rather than of the estate. An RVTools vInfo sheet carries no database engine, "
        "application name or workload tier, so the disposition engine has nothing to "
        "identify a PaaS candidate by and rehosts everything. Add those columns to the "
        "upload, or classify the estate on <b>Readiness &amp; 7R</b>, and the replatform "
        "cases appear.", "warn")

# --------------------------------------------------------------------------
ui.section("How every VM gets from one to the other",
           "Width is VM count. Read left to right: what it is today, what happens "
           "to it, and the service it ends up on.")

TOP_SERVICES = 8
flow = sized[["tier", "strategy", "target_service", "vm_name"]].copy()

keep = (flow.loc[flow["target_service"] != "Decommission", "target_service"]
        .value_counts().head(TOP_SERVICES).index)
grouped = ~flow["target_service"].isin(keep) & (flow["target_service"] != "Decommission")
n_grouped = int(grouped.sum())
flow.loc[grouped, "target_service"] = "Other Azure services"

tiers = sorted(flow["tier"].unique())
strategies = [s for s in ui.STRATEGY_COLOURS if s in set(flow["strategy"])]
services = (flow["target_service"].value_counts().index.tolist())

labels = tiers + strategies + services
colours = ([ui.PALETTE[i % len(ui.PALETTE)] for i in range(len(tiers))]
           + [ui.STRATEGY_COLOURS[s] for s in strategies]
           + [(ui.NEGATIVE if svc == "Decommission" else
               ui.ACCENT_2 if svc == "Other Azure services" else
               ui.PALETTE[(i + 2) % len(ui.PALETTE)])
              for i, svc in enumerate(services)])
index = {name: i for i, name in enumerate(labels)}

src, tgt, val = [], [], []
for (tier, strat), n in flow.groupby(["tier", "strategy"]).size().items():
    src.append(index[tier]); tgt.append(index[strat]); val.append(int(n))
for (strat, svc), n in flow.groupby(["strategy", "target_service"]).size().items():
    src.append(index[strat]); tgt.append(index[svc]); val.append(int(n))

st.plotly_chart(
    ui.sankey(labels, colours, src, tgt, val,
              title="Workload tier  ->  7R disposition  ->  target service",
              height=560),
    width="stretch")

if n_grouped:
    st.caption(f"{n_grouped} VMs across the smaller target services are grouped as "
               "*Other Azure services* so the diagram stays readable. The table below "
               "is complete.")

# --------------------------------------------------------------------------
ui.section("Where the estate lands, in full",
           "Every target service the disposition engine selected, with nothing grouped.")

full = (sized.groupby("target_service")
        .agg(vms=("vm_name", "count"),
             vcpu_today=("vcpu", "sum"),
             vcpu_azure=("azure_vcpu", "sum"),
             storage_tib=("provisioned_gib", lambda x: x.sum() / 1024))
        .sort_values("vms", ascending=False).reset_index())
full["share_pct"] = full["vms"] / full["vms"].sum() * 100
full = full.rename(columns={
    "target_service": "Target service", "vms": "VMs", "vcpu_today": "vCPU today",
    "vcpu_azure": "vCPU after right-sizing", "storage_tib": "Storage TiB",
    "share_pct": "Share %"})
st.dataframe(full.style.format({"VMs": "{:,.0f}", "vCPU today": "{:,.0f}",
                                "vCPU after right-sizing": "{:,.0f}",
                                "Storage TiB": "{:,.1f}", "Share %": "{:.1f}%"}),
             hide_index=True, width="stretch")
ui.df_download(full, "current_future_state.csv")

# --------------------------------------------------------------------------
moved = s["vm_count"] - decommissioned
ui.takeaway(
    f"Of {s['vm_count']:,} virtual machines, <b>{decommissioned:,} never move</b> -- they "
    f"are retired or replaced by something you already pay for. Of the {moved:,} that do, "
    f"{iaas:,} land on Azure VMs and {paas:,} land on a managed service, which is the "
    "part of the estate that stops being your problem to patch. "
    + (f"{avs:,} go to Azure VMware Solution because something about them resists "
       "everything else." if avs else
       "Nothing needs Azure VMware Solution, so the estate can leave VMware entirely."))
