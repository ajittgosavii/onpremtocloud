"""Start here: choose whose estate the model is about, before it shows an answer.

This page exists because every figure downstream is derived from the estate, and
a reader cannot tell a synthetic estate from a real one by looking at the output.
Landing on a business case built from 547 VMs that do not exist is the single
most misleading thing this application could do, so nothing is presented as an
answer until somebody has said where the estate came from.

Three routes, in descending order of how much they can be trusted: a real
inventory, the client's own headline numbers, or the reference estate clearly
labelled as synthetic.
"""

import pathlib

import pandas as pd
import streamlit as st

from core import inventory, scenario, tco, ui

sc = scenario.get_scenario()

ui.page_header(
    "Start here",
    "Every number in this application is computed from an estate. Say which estate, "
    "and the rest of the model follows. Azure unit prices are always live; nothing "
    "else is, until you provide it.")

# --------------------------------------------------------------------------
# Where we stand
# --------------------------------------------------------------------------
if sc.estate_source:
    res = scenario.current()
    s = res.estate_summary
    st.markdown(
        ui.estate_badge(sc.estate_source, sc.estate_label, s["vm_count"])
        + f"<span class='pill'>{s['total_vcpu']:,} vCPU</span>"
        + f"<span class='pill'>{s['total_ram_tib']:.1f} TiB RAM</span>"
        + f"<span class='pill'>{s['provisioned_tib']:,.0f} TiB provisioned</span>",
        unsafe_allow_html=True)
    if sc.estate_source == "reference":
        ui.note(
            "You are on the <b>reference estate</b>: 547 synthetic VMs with the statistical "
            "shape of an aged vSphere farm. Every figure in the application is real "
            "arithmetic on a fictional estate. Excellent for a demonstration or for "
            "learning the model; not something to put in front of a client as their "
            "numbers.", "warn")
else:
    ui.note(
        "No estate chosen yet. Pick one of the three routes below and the whole model "
        "&mdash; cost, effort, waves, business case &mdash; is computed from it.")

# --------------------------------------------------------------------------
ui.section("Choose an estate",
           "The first option is the only one that produces a defensible client number. "
           "The other two exist so you are never blocked.")

r1, r2, r3 = st.columns(3, gap="medium")

# ---- 1. upload ------------------------------------------------------------
with r1:
    with st.container(border=True):
        st.markdown(
            "<div class='route-num'>1</div>"
            "<div class='route-title'>Upload an inventory</div>"
            "<div class='route-body'>An RVTools export or a CSV. The real path, and the "
            "only one where the estate is measured rather than modelled.</div>",
            unsafe_allow_html=True)
        up = st.file_uploader("RVTools .xlsx (vInfo sheet) or CSV",
                              type=["xlsx", "xls", "csv"], key="start_upload")
        st.caption("Needs at minimum a VM name, CPU count, memory and guest OS. RVTools "
                   "column names are recognised automatically; performance counters, "
                   "environment and application name sharply improve the output.")
        if up is not None:
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
                scenario.update(use_uploaded=True, estate_source="upload",
                                estate_label=up.name)
                st.success(f"Imported {len(df):,} VMs from {up.name}.")
                for w in warns:
                    ui.note(w, "warn")
                st.rerun()
            except Exception as exc:
                st.error(f"Could not read that file: {exc}")

        sample = pathlib.Path("data/sample_rvtools_300vm.xlsx")
        if sample.exists():
            st.download_button(
                "Download a 300-VM sample export",
                sample.read_bytes(), file_name=sample.name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch",
                help="A synthetic vInfo sheet in RVTools' own format, for checking the "
                     "importer against a file of the right shape before you handle a "
                     "client's.")

# ---- 2. headline numbers --------------------------------------------------
with r2:
    with st.container(border=True):
        st.markdown(
            "<div class='route-num'>2</div>"
            "<div class='route-title'>Enter the headline numbers</div>"
            "<div class='route-body'>No export to hand? Six figures are enough to shape a "
            "matching estate. The distribution is modelled; the totals are yours.</div>",
            unsafe_allow_html=True)
        with st.form("headline_numbers"):
            n_vms = st.number_input("VMs in scope", 10, 20000, 400, step=10)
            win = st.slider("Windows share (%)", 0, 100, 60, step=5)
            vcpu = st.number_input("Total vCPU allocated", 0, 400000, 3000, step=100,
                                   help="Leave at 0 to let the model size it from the VM "
                                        "count.")
            ram = st.number_input("Total RAM allocated (GiB)", 0, 4000000, 12000, step=500,
                                  help="Leave at 0 to let the model size it.")
            stor = st.number_input("Provisioned storage (TiB)", 0, 100000, 300, step=10,
                                   help="Leave at 0 to let the model size it.")
            spend = st.number_input(
                "Current platform spend (per year)", 0, 1_000_000_000, 0, step=100000,
                help="Everything you spend running the VMware platform today: licensing, "
                     "hardware, storage, facilities, backup, DR and the staff time. Leave "
                     "at 0 to use the modelled cost base instead.")
            go = st.form_submit_button("Build the model from these", width="stretch")

        if go:
            estate = inventory.generate_estate(int(n_vms), win / 100.0, seed=sc.seed)
            estate = inventory.scale_estate_to_totals(
                estate, total_vcpu=vcpu or None, total_ram_gib=ram or None,
                provisioned_tib=stor or None)
            st.session_state["uploaded_estate"] = estate

            onprem = sc.onprem
            if spend:
                onprem = tco.scale_onprem_to_annual(onprem, float(spend))
            scenario.update(use_uploaded=True, estate_source="manual",
                            estate_label=f"{int(n_vms):,} VMs", onprem=onprem,
                            autocalibrate_onprem=not spend)
            st.rerun()

# ---- 3. reference ---------------------------------------------------------
with r3:
    with st.container(border=True):
        st.markdown(
            "<div class='route-num'>3</div>"
            "<div class='route-title'>Demo data &mdash; reference estate</div>"
            "<div class='route-body'>547 synthetic VMs that behave like an aged vSphere "
            "farm. Fiction with a real price attached: the arithmetic and the Azure rates "
            "are genuine, the estate is invented. For demonstrations and training.</div>",
            unsafe_allow_html=True)
        st.caption("Every page will carry a label saying the estate is synthetic. You can "
                   "swap it for a real inventory at any point without losing your settings.")
        if st.button("Use the reference estate", width="stretch", key="use_reference"):
            st.session_state["uploaded_estate"] = None
            scenario.update(use_uploaded=False, estate_source="reference",
                            estate_label="547-VM reference estate")
            st.rerun()

# --------------------------------------------------------------------------
# What is measured, and what is still assumed
# --------------------------------------------------------------------------
if sc.estate_source:
    ui.section("What is measured, and what is still assumed",
               "Worth reading before quoting any of it. Each row links to the page that "
               "controls it.")

    estate_real = sc.estate_source == "upload"
    onprem_set = sc.onprem.cost_scale != 1.0

    rows = [
        ("Azure unit prices", "Live",
         "Azure Retail Prices API, this region and currency", None),
        ("The estate",
         "Measured" if estate_real else
         ("Your totals, modelled shape" if sc.estate_source == "manual" else "Synthetic"),
         "VM count, vCPU, RAM, storage, OS mix, utilisation",
         None if estate_real else "Estate discovery"),
        ("Current on-premises cost",
         "Your total" if onprem_set else "Assumed",
         "Licensing, hardware, storage, facilities, staff",
         None if onprem_set else "Model & assumptions"),
        ("Migration effort and labour rates", "Assumed",
         "Complexity model, blended day rate, team size", "Complexity & effort"),
        ("Replication bandwidth and wave shape", "Assumed",
         "Link speed, concurrency, cutover windows", "Wave plan & timeline"),
        ("Discount rate and horizon", "Assumed",
         "NPV discounting and the years modelled", "Business case"),
    ]

    table = pd.DataFrame(
        [{"Input": r[0], "Status": r[1], "Covers": r[2],
          "Set it on": r[3] or "--"} for r in rows])
    st.dataframe(table, hide_index=True, width="stretch")

    still_assumed = sum(1 for r in rows if r[1] == "Assumed")
    if estate_real and onprem_set:
        ui.note("Both figures that drive every ratio &mdash; the estate and the current "
                "cost base &mdash; are now yours. The remaining assumptions shape the "
                "programme, not the business case.", "good")
    else:
        ui.note(
            f"{still_assumed} of the six inputs are still model defaults. The two that "
            "matter most are the estate itself and the current on-premises cost, because "
            "every percentage on the executive briefing is a ratio between them.", "warn")
