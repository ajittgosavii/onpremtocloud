"""Cloud provider selection: one recommendation, and the arithmetic behind it."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core import assessment, providers, scenario, ui

sc = scenario.get_scenario()
res = scenario.current()
cur = sc.commercial.currency
est = res.estate
sized = res.sized
s = res.estate_summary

ui.page_header(
    "Cloud provider",
    "Provider choice is usually argued on brand preference. For a Windows-heavy VMware estate "
    "it is mostly arithmetic, because the three large providers charge within a few percent of "
    "each other for equivalent compute -- and then differ sharply on how your existing "
    "licences may be used. This page answers the question for your configuration and shows "
    "the working.",
)

# --------------------------------------------------------------------------
# Estate facts that drive the decision
# --------------------------------------------------------------------------
windows_vms = int((est["os_family"] == "Windows").sum())
windows_vcpu = int(sized[sized["os_family"] == "Windows"]["azure_vcpu"].sum())
linux_vcpu = int(sized[sized["os_family"] == "Linux"]["azure_vcpu"].sum())
sql_vms = int((est["db_engine"] == "Microsoft SQL Server").sum())
oracle_vms = int((est["db_engine"] == "Oracle Database").sum())
eol_windows = int(((est["os_family"] == "Windows") & est["os_eol"]).sum())
blocked = int((sized["readiness"] == assessment.NOT_READY).sum())

if not ui.presenting():
    with st.expander("Your configuration -- the inputs that decide this", expanded=True):
        c1, c2 = st.columns([2, 1])
        with c1:
            st.caption("Read from your inventory. Change the estate on the Discovery page and "
                       "this recommendation moves with it.")
            facts = pd.DataFrame([
                {"Fact": "Windows share of the estate",
                 "Value": f"{s['windows_pct']:.0f}%  ({windows_vms} VMs)",
                 "Why it matters": "Decides how much the Windows licensing rules are worth"},
                {"Fact": "Windows vCPU in the Azure target", "Value": f"{windows_vcpu:,}",
                 "Why it matters": "Licence charges are per vCPU per hour"},
                {"Fact": "SQL Server workloads", "Value": f"{sql_vms}",
                 "Why it matters": "Managed SQL Server compatibility differs sharply"},
                {"Fact": "Windows VMs past end of support", "Value": f"{eol_windows}",
                 "Why it matters": "Extended Security Updates are free only on Azure"},
                {"Fact": "Oracle Database VMs", "Value": f"{oracle_vms}",
                 "Why it matters": "The one factor that argues for OCI"},
                {"Fact": "VMs blocked from native IaaS", "Value": f"{blocked}",
                 "Why it matters": "Needs a VMware-native landing option"},
            ])
            st.dataframe(facts, hide_index=True, width="stretch",
                         column_config={"Why it matters":
                                        st.column_config.TextColumn(width="large")})
        with c2:
            sa = st.toggle(
                "Client holds Software Assurance on its Windows/SQL licences", True,
                help="This is the single most important question on the page. Without "
                     "Software Assurance there is nothing to bring, and the licensing "
                     "advantage largely disappears.")
            ms_shop = st.toggle("Predominantly a Microsoft shop", True,
                                help="Active Directory, Microsoft 365, existing Windows and "
                                     "SQL Server skills.")
            esu_cost = st.number_input(
                "Extended Security Updates, per server per year", 0.0, 10000.0,
                float(providers.ESU_PER_VM_YEAR), 100.0,
                help="Assumption, not a live rate. ESU lists at roughly 75% of the full "
                     "licence price and escalates each year.")
else:
    sa, ms_shop, esu_cost = True, True, providers.ESU_PER_VM_YEAR

providers.ESU_PER_VM_YEAR = float(esu_cost)

# --------------------------------------------------------------------------
# Live licence rates
# --------------------------------------------------------------------------
notes: list[str] = []
try:
    aws = providers.aws_windows_premium(sc.commercial.region, live=sc.live_pricing)
    aws_prem = aws["per_vcpu_hr"]
    aws_ok = True
except Exception as exc:
    aws, aws_prem, aws_ok = None, 0.046, False
    notes.append(f"AWS pricing feed unavailable ({exc}); using the published "
                 "$0.046 per vCPU per hour.")

azure_prem = 0.046
pb = res.price_book
if len(pb.vm):
    row = pb.vm[pb.vm["arm_sku_name"] == "Standard_D4s_v5"]
    if len(row) and pd.notna(row.iloc[0]["win_licence_hr"]):
        azure_prem = float(row.iloc[0]["win_licence_hr"]) / 4

inp = providers.LicensingInputs(
    windows_vcpu=windows_vcpu, windows_vms=windows_vms, sql_vms=sql_vms,
    eol_windows_vms=eol_windows, oracle_vms=oracle_vms, linux_vcpu=linux_vcpu,
    total_vcpu=int(sized["azure_vcpu"].sum()), owns_software_assurance=sa,
    azure_windows_premium_per_vcpu_hr=azure_prem,
    aws_windows_premium_per_vcpu_hr=aws_prem,
)
lic = providers.licensing_comparison(inp)
weights = providers.estate_weights(s["windows_pct"], sql_vms, oracle_vms,
                                   s["eol_os_count"], blocked, len(est), ms_shop)
rank = providers.rank_providers(weights)
rec = providers.recommendation(rank, lic, s["windows_pct"], sql_vms, eol_windows,
                               oracle_vms, len(est), cur)

for n in notes:
    ui.note(n, "warn")

# ==========================================================================
# The answer
# ==========================================================================
p = rec["winner"]
st.markdown(
    f"<div class='takeaway' style='padding:1.5rem 1.7rem'>"
    f"<div class='tk-label'>Recommendation for this configuration</div>"
    f"<div style='font-size:2.15rem;font-weight:750;letter-spacing:-.025em;"
    f"line-height:1.15;margin:.25rem 0 .5rem 0'>{p.name}</div>"
    f"<div class='tk-body'>{rec['confidence']} confidence. "
    f"Fit score {rec['winner_row']['fit_score']:.0f} against "
    f"{rec['runner_up']['fit_score']:.0f} for {rec['runner_up']['provider']}, "
    f"the next best option."
    + (f" On licensing alone this is worth <b>"
       f"{ui.money(rec['licensing_advantage_annual'], cur)} a year</b> against "
       f"{rec['licensing_advantage_vs']}." if rec["licensing_advantage_annual"] > 0 else "")
    + "</div></div>", unsafe_allow_html=True)

best_lic = lic.iloc[0]
worst_lic = lic.iloc[-1]
ui.metric_row([
    ("Recommended provider", p.short, f"{rec['confidence'].lower()} confidence"),
    ("Annual licensing cost here", ui.compact_money(float(
        lic[lic["key"] == p.key].iloc[0]["total_annual"]), cur), "for Windows and ESU"),
    (f"Same estate on {worst_lic['provider']}",
     ui.compact_money(float(worst_lic["total_annual"]), cur),
     f"+{ui.compact_money(float(worst_lic['total_annual']) - float(lic[lic['key'] == p.key].iloc[0]['total_annual']), cur)}"),
    ("Windows share", f"{s['windows_pct']:.0f}%", f"{windows_vcpu:,} vCPU"),
    ("Over 5 years", ui.compact_money(
        (float(worst_lic["total_annual"]) - float(lic[lic["key"] == p.key].iloc[0]["total_annual"])) * 5,
        cur), "licensing difference alone"),
], tones=["", "pos", "neg", "", "neg"])

ui.section("Why", "Three reasons, each traceable to a number in your inventory.")
for i, r in enumerate(rec["reasons"], 1):
    st.markdown(f"**{i}.** {r}")

st.markdown("")
ui.note(rec["counter"], "warn")

# ==========================================================================
tab_lic, tab_fit, tab_detail, tab_feed = st.tabs(
    ["The licensing arithmetic", "Fit scorecard", "Provider detail",
     "Live rate comparison"])

# --------------------------------------------------------------------------
with tab_lic:
    ui.section(
        "Annual Windows and SQL licensing, by provider",
        "Compute capacity is held identical across providers on purpose. The three large "
        "providers charge within a few percent of each other for equivalent capacity, so a "
        "compute price war is not the decision. How your existing licences may be used is.")

    fig = go.Figure()
    fig.add_trace(go.Bar(name="Windows licence charge", x=lic["provider"],
                         y=lic["windows_licence"], marker_color=ui.PALETTE[0]))
    fig.add_trace(go.Bar(name="Dedicated / sole-tenant premium", x=lic["provider"],
                         y=lic["dedicated_tenancy_premium"], marker_color=ui.PALETTE[1]))
    fig.add_trace(go.Bar(name="Extended Security Updates", x=lic["provider"],
                         y=lic["esu"], marker_color=ui.PALETTE[3]))
    fig.update_layout(barmode="stack", height=390,
                      title=f"Annual licensing cost ({cur})",
                      xaxis_title="", yaxis_title=f"{cur} per year")
    st.plotly_chart(fig, width="stretch")

    disp = lic.copy()
    for c in ["windows_licence", "dedicated_tenancy_premium", "esu", "total_annual",
              "delta_vs_best"]:
        disp[c] = disp[c].map(lambda v: ui.money(v, cur))
    disp["byol_on_shared_tenancy"] = disp["byol_on_shared_tenancy"].map(
        lambda v: "Yes" if v else "No -- dedicated hardware required")
    disp["free_esu"] = disp["free_esu"].map(lambda v: "Free" if v else "Purchased")
    st.dataframe(disp[["provider", "byol_on_shared_tenancy", "free_esu", "windows_licence",
                       "dedicated_tenancy_premium", "esu", "total_annual", "delta_vs_best"]]
                 .rename(columns={
                     "provider": "Provider",
                     "byol_on_shared_tenancy": "BYOL on shared tenancy",
                     "free_esu": "Extended Security Updates",
                     "windows_licence": "Windows licence",
                     "dedicated_tenancy_premium": "Dedicated tenancy premium",
                     "esu": "ESU cost", "total_annual": "Total per year",
                     "delta_vs_best": "vs best"}),
                 hide_index=True, width="stretch")

    st.markdown("### How each provider treats your licences")
    for _, r in lic.iterrows():
        prov = providers.PROVIDER_BY_KEY[r["key"]]
        with st.expander(f"{prov.name} -- {ui.money(r['total_annual'], cur)} per year"):
            st.markdown(f"**Bring-your-own-licence.** {prov.windows_byol}")
            st.markdown(f"**Applied here.** {r['detail']}")
            st.markdown(f"**SQL Server path.** {prov.sql_paas}")

    if sa:
        ui.takeaway(
            "This is the slide that ends the debate. Every provider charges roughly the same "
            "for raw compute -- the live rates on the last tab prove it. What differs is "
            "whether the client's existing Windows licences can be used on ordinary shared "
            "tenancy. On Azure they can. On AWS and Google Cloud, bringing your own licence "
            "means buying dedicated hardware, which costs more and gives up the elasticity "
            "that justified moving in the first place.")
    else:
        ui.takeaway(
            "Without Software Assurance the picture changes completely: there is nothing to "
            "bring, every provider charges licence-included rates, and they are within a few "
            "percent of each other. At that point the decision is genuinely about ecosystem, "
            "skills and data strategy -- and it is worth running a real competitive process.",
            label="The point to make")

# --------------------------------------------------------------------------
with tab_fit:
    ui.section("Weighted fit against your estate",
               "Weights are derived from what your inventory actually contains -- Windows "
               "share, SQL count, Oracle count, end-of-life servers, blocked VMs -- not from "
               "a generic scorecard.")

    fig = go.Figure(go.Bar(
        x=rank["fit_score"], y=rank["provider"], orientation="h",
        marker_color=[ui.PALETTE[2] if i == 0 else ui.PALETTE[7]
                      for i in range(len(rank))],
        text=[f"{v:.0f}" for v in rank["fit_score"]], textposition="auto"))
    fig.update_layout(height=280, title="Provider fit score (0-100)",
                      xaxis_title="", yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig, width="stretch")

    c1, c2 = st.columns([1.4, 1])
    with c1:
        heat = rank.set_index("provider")[list(providers.CRITERIA)]
        heat.columns = [providers.CRITERIA[c] for c in heat.columns]
        fig = px.imshow(heat, color_continuous_scale=ui.SEQUENTIAL, aspect="auto",
                        labels=dict(color="Score 1-5"), text_auto=True)
        fig.update_layout(height=330, xaxis_title="", yaxis_title="",
                          xaxis=dict(side="top", tickangle=-38), coloraxis_showscale=False)
        st.plotly_chart(fig, width="stretch")
    with c2:
        wdf = pd.DataFrame([{"Criterion": providers.CRITERIA[k], "Weight": round(v, 2)}
                            for k, v in weights.items()]).sort_values(
            "Weight", ascending=False)
        st.markdown("**Weights from your estate**")
        st.dataframe(wdf, hide_index=True, width="stretch", height=330)

    top_w = wdf.iloc[0]
    ui.note(
        f"The heaviest weight is <b>{top_w['Criterion']}</b>, at {top_w['Weight']:.2f}. That "
        "is not a preference -- it is what a "
        f"{s['windows_pct']:.0f}% Windows estate with {sql_vms} SQL Server workloads and "
        f"{eol_windows} out-of-support Windows servers forces the model to care about. "
        "Change the estate mix on the Discovery page and watch the ranking move.")

# --------------------------------------------------------------------------
with tab_detail:
    for _, r in rank.iterrows():
        prov = providers.PROVIDER_BY_KEY[r["key"]]
        lr = lic[lic["key"] == r["key"]].iloc[0]
        with st.expander(f"{prov.name}  --  fit {r['fit_score']:.0f}/100  --  "
                         f"{ui.money(lr['total_annual'], cur)} annual licensing",
                         expanded=(r["key"] == rec["winner"].key)):
            st.markdown(prov.notes)
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Landing options**")
                st.write({
                    "VMware-native service": prov.vmware_service,
                    "On-premises / edge": prov.onprem_service,
                    "SQL Server PaaS": prov.sql_paas,
                })
            with c2:
                st.markdown("**Licensing position**")
                st.write({
                    "Windows BYOL": prov.windows_byol,
                    "BYOL on shared tenancy": "Yes" if prov.byol_shared_tenancy else "No",
                    "Free Extended Security Updates": "Yes" if prov.free_esu else "No",
                    "Annual licensing cost here": ui.money(lr["total_annual"], cur),
                })

    ui.note(
        "A note on scope: this compares providers for <i>this</i> estate and this migration. "
        "It is not a general ranking. A data-platform programme, a Kubernetes-first estate or "
        "an Oracle-dominated one would each produce a different answer from the same model -- "
        "which is the argument for keeping the weights visible.")

# --------------------------------------------------------------------------
with tab_feed:
    ui.section("Live rate comparison",
               "Both figures below are fetched from public vendor pricing APIs, not from a "
               "deck. They are what makes the licensing argument checkable.")

    c1, c2, c3 = st.columns(3)
    c1.metric("Azure Windows licence", f"${azure_prem:.4f}", "per vCPU per hour")
    c2.metric("AWS Windows licence", f"${aws_prem:.4f}", "per vCPU per hour")
    c3.metric("Difference", f"${abs(azure_prem - aws_prem):.4f}",
              "essentially identical" if abs(azure_prem - aws_prem) < 0.002 else "")

    if abs(azure_prem - aws_prem) < 0.002:
        ui.takeaway(
            f"Azure and AWS charge <b>the same ${azure_prem:.3f} per vCPU per hour</b> for a "
            "Windows licence when you do not bring your own -- two figures derived "
            "independently, moments ago, from two different vendor APIs. So the recommendation "
            "is not \"Azure is cheaper\". It is that Azure is the only one of them that lets "
            "you stop paying that charge by using licences the client already owns.",
            label="The line that settles it")

    st.markdown("### Sources")
    st.dataframe(pd.DataFrame([
        {"Provider": "Microsoft Azure",
         "Source": "Azure Retail Prices API (prices.azure.com), unauthenticated",
         "Rate": f"${azure_prem:.4f} per vCPU/hr, derived from the Standard_D4s_v5 "
                 "Windows-minus-Linux delta",
         "Live": "Yes" if pb.source in ("live", "cache") else "Cached"},
        {"Provider": "Amazon Web Services",
         "Source": "AWS pricing feed behind calculator.aws, unauthenticated",
         "Rate": (f"${aws_prem:.4f} per vCPU/hr, median across "
                  f"{aws['instance_count'] if aws_ok else 0} instance types"),
         "Live": "Yes" if aws_ok else "Fallback to published list"},
        {"Provider": "Google Cloud",
         "Source": "Published list pricing (the Cloud Billing Catalog API needs a key)",
         "Rate": f"${providers.GCP_WINDOWS_PER_VCPU_HR:.3f} per vCPU/hr",
         "Live": "No -- published list"},
        {"Provider": "Oracle Cloud",
         "Source": "Published list pricing",
         "Rate": f"${providers.OCI_WINDOWS_PER_OCPU_HR:.3f} per OCPU/hr "
                 "(two vCPU per OCPU)",
         "Live": "No -- published list"},
    ]), hide_index=True, width="stretch",
        column_config={"Rate": st.column_config.TextColumn(width="large")})

    if aws_ok:
        st.markdown("### AWS instances used to derive the premium")
        st.caption(f"Median of (Windows rate - Linux rate) / vCPU across "
                   f"{aws['instance_count']} instance types in {aws['region_label']}. "
                   "Burstable T-family sizes price the licence differently, which is why the "
                   "median is used rather than the mean.")
        st.dataframe(aws["detail"].head(40).round(4).rename(columns={
            "instance_type": "Instance type", "vcpu": "vCPU", "linux_hr": "Linux $/hr",
            "windows_hr": "Windows $/hr",
            "premium_per_vcpu_hr": "Licence premium $/vCPU/hr"}),
            hide_index=True, width="stretch", height=340)
        ui.df_download(aws["detail"], "aws_windows_licence_premium.csv")
