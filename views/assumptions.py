"""Model & assumptions: every input, where to change it, and what it drives."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import assumptions as A
from core import scenario, ui

sc = scenario.get_scenario()
res = scenario.current()
cur = sc.commercial.currency

ui.page_header(
    "Model & assumptions",
    "Every number in this application is one of three things: a vendor fact fetched from a "
    "live API, an observation read from the inventory, or a modelling assumption. This page "
    "lists all of them, tells you which is which, and links to the page that controls each "
    "one. When a client asks \"what are you assuming?\", this is the complete answer.",
)

df = A.build(sc, res)
s = A.summary(df)

ui.metric_row([
    ("Inputs in the model", f"{s['total']}", "all listed below"),
    ("Vendor facts", f"{s['vendor_facts']}", "live API or published docs"),
    ("Read from your inventory", f"{s['estate']}", "changes with the estate"),
    ("Need the client's real figure", f"{s['calibrate']}", "calibrate before presenting"),
    ("Calibrate first", f"{s['priority_1']}", "highest impact on the answer"),
], tones=["", "pos", "", "warn", "warn"])

ui.takeaway(
    f"Of {s['total']} inputs, {s['vendor_facts']} are vendor facts you cannot argue with and "
    f"{s['estate']} come straight from the inventory. That leaves "
    f"{s['calibrate'] + s['judgement']} genuine assumptions -- and only <b>{s['priority_1']}</b> "
    "of them materially move the answer. Work through those first on a real engagement and "
    "the model stops being a shape and starts being a number.")

tab_first, tab_all, tab_kinds = st.tabs(
    ["Calibrate these first", "Full register", "How the model is put together"])

# --------------------------------------------------------------------------
with tab_first:
    ui.section(
        "The inputs that actually move the answer",
        "Ranked by how much the conclusion depends on them. Everything here should be "
        "replaced with the client's own figure before the output is presented as a number "
        "rather than a shape.")

    first = df[df["Priority"] == 1]
    for group in first["Group"].unique():
        sub = first[first["Group"] == group]
        st.markdown(f"#### {group}")
        for _, r in sub.iterrows():
            with st.container(border=True):
                c1, c2, c3 = st.columns([2.1, 1.3, 1.4])
                with c1:
                    st.markdown(f"**{r['Assumption']}**")
                    if r["Note"]:
                        st.caption(r["Note"])
                with c2:
                    st.markdown(f"Currently: **{r['Current value']}**")
                    st.caption(r["Kind"])
                with c3:
                    st.caption(f"Drives: {r['What it drives']}")
                    path = A.PAGES.get(r["Set on page"])
                    if path:
                        ui.page_link(path, f"Change on {r['Set on page']}",
                                     ":material/tune:")

# --------------------------------------------------------------------------
with tab_all:
    c1, c2, c3 = st.columns(3)
    f_group = c1.multiselect("Group", sorted(df["Group"].unique()))
    f_kind = c2.multiselect("Kind", A.KIND_ORDER)
    f_pri = c3.multiselect("Priority", [1, 2, 3],
                           format_func=lambda p: {1: "1 - calibrate first",
                                                  2: "2 - review",
                                                  3: "3 - default is fine"}[p])
    view = df
    if f_group:
        view = view[view["Group"].isin(f_group)]
    if f_kind:
        view = view[view["Kind"].isin(f_kind)]
    if f_pri:
        view = view[view["Priority"].isin(f_pri)]

    st.caption(f"{len(view)} of {len(df)} inputs")
    st.dataframe(
        view[["Group", "Assumption", "Current value", "Kind", "Set on page",
              "What it drives", "Priority"]],
        hide_index=True, width="stretch", height=560,
        column_config={
            "What it drives": st.column_config.TextColumn(width="large"),
            "Priority": st.column_config.NumberColumn(
                help="1 = calibrate first, 3 = the default is fine"),
        })
    ui.df_download(df, "model_assumptions_register.csv",
                   "Download the full register as CSV")
    st.caption("Export this and send it with the deck. An assumptions register the client can "
               "mark up is worth more than a number they cannot question.")

# --------------------------------------------------------------------------
with tab_kinds:
    ui.section("Three kinds of number",
               "The distinction is what makes the model defensible. Say it out loud at the "
               "start of a session.")

    counts = (df["Kind"].value_counts().reindex(A.KIND_ORDER).dropna()
              .rename_axis("kind").reset_index(name="inputs"))
    colours = {A.VENDOR: ui.PALETTE[2], A.ESTATE: ui.PALETTE[0],
               A.CALIBRATE: ui.PALETTE[1], A.JUDGEMENT: ui.PALETTE[4]}
    c1, c2 = st.columns([1, 1.4])
    with c1:
        st.plotly_chart(ui.donut(counts["kind"], counts["inputs"],
                                 colour_map=colours, height=320), width="stretch")
    with c2:
        st.markdown(
            f"**{A.VENDOR} ({s['vendor_facts']}).** Fetched live from the Azure Retail Prices "
            "API and the AWS pricing feed, or taken from published product documentation - "
            "Azure Migrate's replication limits, VM SKU specifications, managed disk tiers. "
            "Not adjustable, because they are not ours to adjust.")
        st.markdown(
            f"**{A.ESTATE} ({s['estate']}).** Read from the inventory. Upload a real RVTools "
            "export and every one of these becomes evidence rather than a model.")
        st.markdown(
            f"**{A.CALIBRATE} ({s['calibrate']}).** Defensible defaults standing in for a "
            "figure only the client has - their rate card, their renewal quote, their circuit "
            "capacity, their hurdle rate.")
        st.markdown(
            f"**{A.JUDGEMENT} ({s['judgement']}).** Deliberate modelling choices with no single "
            "right answer, such as effort per VM or WAN efficiency. Exposed as controls "
            "specifically so they can be argued with.")

    ui.section("How the pieces fit together",
               "Each stage consumes the one above it, which is why calibrating early inputs "
               "matters far more than tuning late ones.")

    chain = [
        ("Inventory", "VM count, sizes, utilisation, OS, databases, friction flags",
         "Estate discovery"),
        ("Right-sizing", "Azure VM SKU and disk tiers per VM", "Readiness & 7R"),
        ("Readiness & disposition", "What can move, and what should happen to it",
         "Readiness & 7R"),
        ("Run cost", "Monthly Azure bill, priced from live vendor rates",
         "Azure cost simulator"),
        ("Complexity & effort", "Person-hours, migration cost, cutover risk",
         "Complexity & effort"),
        ("Wave plan", "Duration, sequencing, binding constraint", "Wave plan & timeline"),
        ("Risk simulation", "Confidence bands on cost and duration", "Risk simulation"),
        ("Business case", "NPV, payback, the recommendation", "Business case"),
    ]
    for i, (stage, what, page) in enumerate(chain, 1):
        c1, c2, c3 = st.columns([1.1, 2.4, 1.2])
        c1.markdown(f"**{i}. {stage}**")
        c2.markdown(what)
        path = A.PAGES.get(page)
        if path:
            ui.page_link(path, page, ":material/arrow_forward:", container=c3)

    ui.note(
        "The chain is why the inventory matters more than anything else on this page. A "
        "wrong rate card changes the cost by a few percent. A wrong inventory changes "
        "everything downstream of it.")
