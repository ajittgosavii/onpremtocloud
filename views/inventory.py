"""Discovery and inventory: generate a synthetic estate or import a real one."""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core import inventory, scenario, ui

sc = scenario.get_scenario()

ui.page_header(
    "Estate discovery",
    "The source of truth for everything else. Either shape a synthetic estate that matches "
    "what the client has described, or import their actual RVTools export. Every downstream "
    "number is only as good as this page.",
)

tab_src, tab_profile, tab_browse, tab_quality = st.tabs(
    ["Estate source", "Portfolio profile", "Browse inventory", "Data quality"])

# --------------------------------------------------------------------------
with tab_src:
    mode = st.radio(
        "Where does the inventory come from?",
        ["Synthetic estate (modelled)", "Upload RVTools / CSV"],
        index=1 if sc.use_uploaded else 0, horizontal=True)

    if mode == "Synthetic estate (modelled)":
        if sc.use_uploaded:
            scenario.update(use_uploaded=False)
            st.rerun()

        c1, c2, c3 = st.columns(3)
        n_vms = c1.number_input("Number of VMs", 10, 20000, sc.n_vms, step=1)
        win = c2.slider("Windows share (%)", 0, 100, int(sc.windows_pct))
        clusters = c3.number_input("vSphere clusters", 1, 40, sc.n_clusters)

        c4, c5 = st.columns(2)
        bias = c4.slider(
            "Utilisation profile", 0.5, 2.5, sc.overprovision_bias, 0.1,
            help="1.0 models a typical aged enterprise farm at roughly 15% mean CPU. Raise it "
                 "for a well-managed estate with less right-sizing headroom to harvest.")
        seed = c5.number_input("Random seed", 1, 10**9, sc.seed,
                               help="Same seed, same estate. Change it to test whether a "
                                    "conclusion is robust or an artefact of one sample.")

        if (n_vms != sc.n_vms or win != sc.windows_pct or clusters != sc.n_clusters
                or bias != sc.overprovision_bias or seed != sc.seed):
            scenario.update(n_vms=int(n_vms), windows_pct=float(win), n_clusters=int(clusters),
                            overprovision_bias=float(bias), seed=int(seed), use_uploaded=False)
            st.rerun()

        ui.note(
            "The generator produces the statistical shape of a real aged vSphere farm: heavy "
            "over-provisioning, a long tail of idle VMs, end-of-life guest operating systems, "
            "and a realistic scattering of the conditions that actually block migration - RDMs, "
            "shared disks, stale VMware Tools, open snapshots, vGPU and MAC-bound licences.")

    else:
        st.markdown("#### Upload an RVTools export or a CSV")
        up = st.file_uploader("RVTools .xlsx (vInfo sheet) or a CSV", type=["xlsx", "xls", "csv"])
        st.caption(
            "Minimum required columns: a VM name, CPU count, memory and guest OS. RVTools "
            "column names are recognised automatically. Performance counters, environment, "
            "criticality and application name are all optional but sharply improve the output.")

        if up is not None:
            try:
                if up.name.lower().endswith(".csv"):
                    raw = pd.read_csv(up)
                else:
                    sheets = pd.read_excel(up, sheet_name=None)
                    pick = next((s for s in sheets if s.lower() in ("vinfo", "tabvinfo")),
                                list(sheets)[0])
                    raw = sheets[pick]
                    st.caption(f"Read sheet: **{pick}** ({len(raw):,} rows).")
                df, warns = inventory.import_inventory(raw)
                st.session_state["uploaded_estate"] = df
                scenario.update(use_uploaded=True)
                st.success(f"Imported {len(df):,} VMs.")
                for w in warns:
                    ui.note(w, "warn")
                st.rerun()
            except Exception as exc:
                st.error(f"Could not import that file: {exc}")

        if st.session_state.get("uploaded_estate") is not None:
            cur = st.session_state["uploaded_estate"]
            st.info(f"Currently using an uploaded inventory of {len(cur):,} VMs.")
            if st.button("Discard the upload and go back to the synthetic estate"):
                st.session_state["uploaded_estate"] = None
                scenario.update(use_uploaded=False)
                st.rerun()

res = scenario.current()
est = res.estate
s = res.estate_summary

# --------------------------------------------------------------------------
with tab_profile:
    ui.metric_row([
        ("VMs", f"{s['vm_count']:,}", f"{s['powered_on']:,} powered on"),
        ("Total vCPU", f"{s['total_vcpu']:,}", None),
        ("Total RAM", f"{s['total_ram_tib']:,.1f} TiB", None),
        ("Provisioned storage", f"{s['provisioned_tib']:,.1f} TiB",
         f"{s['used_tib']:,.1f} TiB consumed"),
        ("Applications", f"{s['app_count']:,}", None),
    ])
    ui.metric_row([
        ("Mean CPU utilisation", f"{s['mean_cpu_pct']:.1f}%", "the right-sizing opportunity"),
        ("Mean memory utilisation", f"{s['mean_mem_pct']:.1f}%", None),
        ("End-of-life guest OS", f"{s['eol_os_count']:,}",
         f"{s['eol_os_count'] / s['vm_count'] * 100:.0f}% of the estate"),
        ("Idle / zombie candidates", f"{s['zombie_count']:,}", "retire before you migrate"),
        ("VMs with a database", f"{s['db_vms']:,}", None),
    ])

    ui.takeaway(
        f"The two numbers to dwell on are <b>{s['mean_cpu_pct']:.0f}% mean CPU</b> and "
        f"<b>{s['zombie_count']} idle VMs</b>. Together they are the entire right-sizing "
        "business case - and they are also the uncomfortable part, because they say the "
        "current estate is paying for capacity nobody uses. "
        f"The other number worth naming early is <b>{s['eol_os_count']} end-of-life guest "
        "operating systems</b>: that is a remediation programme the migration will inherit "
        "whether or not anyone has budgeted for it.")

    c1, c2 = st.columns(2)
    with c1:
        os_mix = (est.groupby(["os_family", "guest_os"]).size()
                  .reset_index(name="vms").sort_values("vms", ascending=False).head(14))
        fig = px.bar(os_mix, x="vms", y="guest_os", color="os_family", orientation="h",
                     color_discrete_map={"Windows": ui.PALETTE[0], "Linux": ui.PALETTE[2]},
                     title="Guest operating systems")
        fig.update_layout(height=430, yaxis=dict(autorange="reversed", title=""),
                          xaxis_title="VMs")
        st.plotly_chart(fig, width="stretch")

    with c2:
        fig = go.Figure()
        fig.add_trace(go.Histogram(x=est["cpu_avg_pct"], name="Mean CPU",
                                   marker_color=ui.PALETTE[0], opacity=0.75, nbinsx=40))
        fig.add_trace(go.Histogram(x=est["mem_avg_pct"], name="Mean memory",
                                   marker_color=ui.PALETTE[1], opacity=0.75, nbinsx=40))
        fig.update_layout(barmode="overlay", height=430, title="Utilisation distribution",
                          xaxis_title="% utilised", yaxis_title="VMs")
        st.plotly_chart(fig, width="stretch")
        st.caption(
            "The mass on the left is the business case. The tail on the right is the part "
            "that will not shrink and must not be under-sized.")

    c3, c4 = st.columns(2)
    with c3:
        envc = est["environment"].value_counts().reset_index()
        envc.columns = ["environment", "vms"]
        st.plotly_chart(ui.bar(envc, "environment", "vms", "Environment", height=320,
                               text_fmt=",.0f"), width="stretch")
    with c4:
        crit = est["criticality"].value_counts().reset_index()
        crit.columns = ["criticality", "vms"]
        st.plotly_chart(ui.bar(crit, "criticality", "vms", "Business criticality",
                               orientation="h", height=320, text_fmt=",.0f"),
                        width="stretch")

    st.markdown("### Size distribution")
    fig = px.scatter(
        est, x="vcpu", y="ram_gib", size="provisioned_gib", color="tier",
        hover_data=["vm_name", "app_name", "environment", "cpu_avg_pct"],
        color_discrete_sequence=ui.PALETTE, log_x=True, log_y=True,
        title="vCPU vs RAM, sized by provisioned storage")
    fig.update_layout(height=440, xaxis_title="vCPU (log)", yaxis_title="RAM GiB (log)")
    st.plotly_chart(fig, width="stretch")

# --------------------------------------------------------------------------
with tab_browse:
    c1, c2, c3, c4 = st.columns(4)
    f_env = c1.multiselect("Environment", sorted(est["environment"].unique()))
    f_tier = c2.multiselect("Tier", sorted(est["tier"].unique()))
    f_os = c3.multiselect("OS family", sorted(est["os_family"].unique()))
    f_app = c4.multiselect("Application", sorted(est["app_name"].unique()))

    view = est
    if f_env:
        view = view[view["environment"].isin(f_env)]
    if f_tier:
        view = view[view["tier"].isin(f_tier)]
    if f_os:
        view = view[view["os_family"].isin(f_os)]
    if f_app:
        view = view[view["app_name"].isin(f_app)]

    st.caption(f"{len(view):,} of {len(est):,} VMs")
    cols = ["vm_name", "app_name", "environment", "criticality", "tier", "guest_os",
            "vcpu", "ram_gib", "provisioned_gib", "used_gib", "cpu_avg_pct", "cpu_p95_pct",
            "mem_avg_pct", "iops_avg", "daily_churn_pct", "cluster", "db_engine",
            "vmware_tools", "powered_on", "zombie_candidate"]
    st.dataframe(view[[c for c in cols if c in view.columns]],
                 hide_index=True, width="stretch", height=480)
    ui.df_download(view, "estate_inventory.csv", "Download this view as CSV")

# --------------------------------------------------------------------------
with tab_quality:
    st.markdown("### Migration friction present in the estate")
    flags = [
        ("has_rdm", "Raw Device Mapping",
         "Physical-mode RDMs are not replicated by agentless migration."),
        ("has_shared_disk", "Shared / clustered disk",
         "Blocks agentless replication outright. The cluster must be rebuilt in Azure."),
        ("has_independent_disk", "Independent disk",
         "Excluded from snapshots, so it silently will not replicate."),
        ("vm_encrypted", "vSphere VM Encryption",
         "Agentless replication cannot read the disks. Decrypt or use agent-based."),
        ("fault_tolerance", "vSphere Fault Tolerance",
         "No Azure equivalent. Redesign onto zones or an availability set."),
        ("has_vgpu", "vGPU attached",
         "Needs an NV/NC-series size. Confirm quota and regional availability early."),
        ("has_usb_or_serial", "USB or serial passthrough",
         "No Azure equivalent. The device must be re-homed to the network."),
        ("licence_mac_bound", "MAC-bound software licence",
         "The NIC MAC changes on migration and the licence fails at cutover."),
        ("has_snapshot", "Open snapshot",
         "Long chains slow replication and risk filling the datastore."),
        ("zombie_candidate", "Idle / zombie VM",
         "Running but doing nothing measurable. Retire rather than migrate."),
    ]
    rows = []
    for col, label, why in flags:
        if col in est.columns:
            n = int(est[col].sum())
            rows.append({"Condition": label, "VMs": n,
                         "Share": f"{n / len(est) * 100:.1f}%", "Why it matters": why})
    fr = pd.DataFrame(rows).sort_values("VMs", ascending=False)
    st.dataframe(fr, hide_index=True, width="stretch",
                 column_config={"Why it matters": st.column_config.TextColumn(width="large")})

    tools = est["vmware_tools"].value_counts().reset_index()
    tools.columns = ["status", "vms"]
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(ui.bar(tools, "status", "vms", "VMware Tools status", height=300,
                               text_fmt=",.0f"), width="stretch")
    with c2:
        snaps = est[est["has_snapshot"]]
        if len(snaps):
            fig = go.Figure(go.Histogram(x=snaps["snapshot_age_days"], nbinsx=30,
                                         marker_color=ui.PALETTE[1]))
            fig.update_layout(height=300, title="Age of open snapshots",
                              xaxis_title="Days", yaxis_title="VMs")
            st.plotly_chart(fig, width="stretch")

    ui.note(
        "Everything on this page is remediation backlog. It is cheaper to clear before the "
        "first wave than to discover during one - and most of it can be cleared by the "
        "platform team without touching an application.")
