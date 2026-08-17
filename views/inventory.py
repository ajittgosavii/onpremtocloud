"""Discovery and inventory: import a real estate, or shape a synthetic one.

Import leads and the generator sits behind an expander. Both work, but only one
of them produces a number anybody can defend, and a page that opens on a random
seed control reads as a toy however good the arithmetic behind it is.
"""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core import broadcom, inventory, scenario, ui

sc = scenario.get_scenario()

ui.page_header(
    "Estate discovery",
    "The source of truth for everything else. Import the client's RVTools export and every "
    "downstream number is measured; use the demo generator instead and every downstream "
    "number is fiction with a real price attached. This page decides which.",
)

tab_src, tab_profile, tab_browse, tab_quality = st.tabs(
    ["Estate source", "Portfolio profile", "Browse inventory", "Data quality"])

# --------------------------------------------------------------------------
with tab_src:
    st.markdown(ui.estate_badge(sc.estate_source, sc.estate_label), unsafe_allow_html=True)

    st.markdown("#### Upload an RVTools export or a CSV")
    up = st.file_uploader("RVTools .xlsx (vInfo sheet) or a CSV", type=["xlsx", "xls", "csv"])
    st.caption(
        "Minimum required columns: a VM name, CPU count, memory and guest OS. RVTools "
        "column names are recognised automatically. Performance counters, environment, "
        "criticality and application name are all optional but sharply improve the output.")

    # As on Start here: the uploader returns the same file on every rerun, so the
    # import must be guarded by a fingerprint or it re-fires in a loop.
    _token = f"{up.name}:{getattr(up, 'size', 0)}" if up is not None else None

    if up is not None and st.session_state.get("_import_token") != _token:
        st.session_state["_import_token"] = _token
        try:
            if up.name.lower().endswith(".csv"):
                raw = pd.read_csv(up)
            else:
                sheets = pd.read_excel(up, sheet_name=None)
                pick = next((s for s in sheets if s.lower() in ("vinfo", "tabvinfo")),
                            list(sheets)[0])
                raw = sheets[pick]
            df, warns = inventory.import_inventory(raw)
            st.session_state["uploaded_estate"] = df
            st.session_state["_import_warnings"] = warns
            scenario.update(use_uploaded=True, estate_source="upload", estate_label=up.name)
            st.rerun()
        except Exception as exc:
            st.error(f"Could not import that file: {exc}")

    if up is not None and sc.estate_source == "upload":
        st.success(f"Imported {len(st.session_state['uploaded_estate']):,} VMs.")
        for w in st.session_state.get("_import_warnings", []):
            ui.note(w, "warn")

    if sc.estate_source == "upload" and st.session_state.get("uploaded_estate") is not None:
        st.info(f"Using an uploaded inventory of "
                f"{len(st.session_state['uploaded_estate']):,} VMs.")

    # ---- demo data, deliberately behind a door --------------------------
    st.divider()
    with st.expander("Demo data -- synthetic estate generator", expanded=False):
        ui.note(
            "Everything produced from here is <b>fiction with a real price attached</b>. "
            "The arithmetic and the Azure rates are genuine; the estate is invented. Use it "
            "to demonstrate the model or to rehearse a session, never to quote a client.",
            "warn")

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

        # An explicit button, not auto-apply: nudging a slider must never silently
        # replace a client's uploaded inventory with a generated one.
        if st.button("Generate this estate and use it", width="stretch"):
            st.session_state["uploaded_estate"] = None
            scenario.update(n_vms=int(n_vms), windows_pct=float(win), n_clusters=int(clusters),
                            overprovision_bias=float(bias), seed=int(seed),
                            use_uploaded=False, estate_source="reference",
                            estate_label=f"{int(n_vms):,}-VM synthetic estate")
            st.rerun()

        st.caption(
            "The generator produces the statistical shape of a real aged vSphere farm: heavy "
            "over-provisioning, a long tail of idle VMs, end-of-life guest operating systems, "
            "and a realistic scattering of the conditions that actually block migration -- "
            "RDMs, shared disks, stale VMware Tools, open snapshots, vGPU and MAC-bound "
            "licences.")

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
        ui.legend_top(fig)
        st.plotly_chart(fig, width="stretch")

    with c2:
        fig = go.Figure()
        fig.add_trace(go.Histogram(x=est["cpu_avg_pct"], name="Mean CPU",
                                   marker_color=ui.PALETTE[0], opacity=0.75, nbinsx=40))
        fig.add_trace(go.Histogram(x=est["mem_avg_pct"], name="Mean memory",
                                   marker_color=ui.PALETTE[1], opacity=0.75, nbinsx=40))
        fig.update_layout(barmode="overlay", height=430, title="Utilisation distribution",
                          xaxis_title="% utilised", yaxis_title="VMs")
        ui.legend_top(fig)
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
        size_max=34, opacity=0.62,
        title="vCPU vs RAM, sized by provisioned storage")
    fig.update_traces(marker=dict(line=dict(width=0)))
    fig.update_layout(height=440, xaxis_title="vCPU (log)", yaxis_title="RAM GiB (log)")
    ui.legend_top(fig)
    ui.log_ticks(fig, "x", (1, 2, 4, 8, 16, 32, 64))
    ui.log_ticks(fig, "y", (1, 2, 4, 8, 16, 32, 64, 128, 256))
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


# --------------------------------------------------------------------------
# What discovery has not given you.
#
# The rest of this page shows what the inventory contains. This shows what a
# migration needs and no inventory export carries -- which is the argument the
# application makes everywhere else, stated as a list somebody can action.
# --------------------------------------------------------------------------
ui.section(
    "Discovery data checklist",
    "Fifteen items a wave plan depends on. Ten of them are not produced by any "
    "discovery tool -- they come from the CMDB, the service owners, the network "
    "team and procurement, and they are the ones a programme discovers it is "
    "missing at the first wave gate.")

_disc = broadcom.discovery_coverage(res.estate.columns)
_held = sum(r["held"] for r in _disc)
_prog = [r for r in _disc if r["source"] == broadcom.PROGRAMME_SOURCED]
_prog_held = sum(r["held"] for r in _prog)

ui.metric_row([
    ("Evidenced by this inventory", f"{_held} of {len(_disc)}",
     "everything else is outstanding"),
    ("Programme-sourced items", f"{len(_prog)}",
     "no tool produces these"),
    ("Programme-sourced still open", f"{len(_prog) - _prog_held}",
     "each needs a named owner"),
    ("Tool-sourced still open", f"{sum(1 for r in _disc if not r['held'] and r['source'] == broadcom.TOOL_SOURCED)}",
     "discovery will close these"),
], tones=["", "", "neg" if len(_prog) - _prog_held else "pos", ""])

st.dataframe(
    pd.DataFrame([{
        "Held": "Yes" if r["held"] else "No",
        "Data item": r["item"],
        "Source": r["source"],
        "Who supplies it": r["who"],
        "Evidence here": r["evidence"]} for r in _disc]),
    hide_index=True, width="stretch", height=560,
    column_config={"Data item": st.column_config.TextColumn(width="large"),
                   "Evidence here": st.column_config.TextColumn(width="medium")})

ui.note(
    f"<b>{len(_prog) - _prog_held} of the {len(_prog)} programme-sourced items are still "
    "open.</b> None of them will be closed by running discovery for longer. RTO and RPO "
    "per application, change windows, vendor support statements for third-party "
    "appliances, Site Recovery Manager runbook logic, backup immutability evidence, the "
    "micro-segmentation rule set and the entitlement position are all conversations with "
    "people, and each one has a lead time. Start them in parallel with discovery rather "
    "than after it.", "warn")

ui.takeaway(
    "The value of this list is the <b>source</b> column, not the items. A steering "
    "committee that has seen a discovery report generally believes discovery is done. "
    "Two thirds of what a wave plan actually needs is not in that report and never will "
    "be -- and the items are exactly the ones that stop a cutover: an appliance the "
    "vendor will not support, a licence bound to a MAC address, an RTO nobody can meet "
    "on the target.")
