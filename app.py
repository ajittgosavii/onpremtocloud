"""CISCLD Ascend -- on-prem to cloud decision simulator.

Entry point. Signed-out visitors get the sign-in cover and nothing else; signed-in
ones get the sidebar of controls that affect every page, and navigation grouped
into the seven acts of the client narrative defined in core.ui.NARRATIVE.

Run with:  streamlit run app.py
"""

import os
from dataclasses import replace

import streamlit as st

from core import auth, brand      # imports only -- no output before set_page_config

st.set_page_config(
    page_title=brand.PAGE_TITLE,
    page_icon=brand.PAGE_ICON,
    layout="wide",
    initial_sidebar_state="expanded" if auth.is_signed_in() else "collapsed",
)

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from core import azure_catalog as cat                    # noqa: E402
from core import llm, login_ui, pricing, scenario, ui    # noqa: E402

# --------------------------------------------------------------------------
# Gate. Nothing below this runs for a signed-out visitor.
# --------------------------------------------------------------------------
auth.enforce_idle_timeout()
if not auth.is_signed_in():
    if auth.restore_session():
        st.rerun()               # re-enter with the sidebar expanded
    login_ui.render()
    st.stop()

# --------------------------------------------------------------------------
# Stale-module guard.
#
# .streamlit/config.toml disables the file watcher, which is load-bearing: it is
# what stopped the deploy crashes. The cost is that a hosted redeploy pulls new
# source and re-executes the *pages* from disk on every run, while core/ stays in
# sys.modules from process start. So a page can call a core.ui function that the
# running interpreter has never seen, and Streamlit Cloud reports it as a
# redacted AttributeError with no hint about what to do. Say what to do.
# --------------------------------------------------------------------------
REQUIRED_UI_API = 4

if getattr(ui, "API_VERSION", 0) < REQUIRED_UI_API:
    st.error(
        f"**This server is running an older copy of `core/ui.py` than the pages "
        f"expect** (has API {getattr(ui, 'API_VERSION', 0)}, needs "
        f"{REQUIRED_UI_API}).\n\n"
        "The source on disk is current; the process still holds the modules it "
        "imported at start-up. **Reboot the app** -- on Streamlit Community Cloud, "
        "*Manage app* in the lower right, then *Reboot*. A redeploy on its own does "
        "not reload an already-imported module while the file watcher is off.")
    st.stop()

ui.install_theme()
ui.inject_css()


# --------------------------------------------------------------------------
def sidebar() -> None:
    sc = scenario.get_scenario()

    with st.sidebar:
        st.markdown(
            "<div style='font-size:.68rem;font-weight:750;letter-spacing:.14em;"
            f"text-transform:uppercase;color:#3B6FD4;margin-bottom:.15rem'>"
            f"{brand.SUITE}</div>"
            "<div style='font-size:1.14rem;font-weight:700;letter-spacing:-.025em;"
            f"margin-bottom:.1rem'>{brand.PRODUCT}</div>"
            "<div style='font-size:.74rem;opacity:.62;line-height:1.4;"
            f"margin-bottom:.9rem'>{brand.DESCRIPTOR}</div>",
            unsafe_allow_html=True)

        present = st.toggle(
            "Presentation mode", value=st.session_state.get("present_mode", False),
            help="Hides every configuration panel and enlarges type, so the screen is "
                 "clean when you are walking a client through it.")
        if present != st.session_state.get("present_mode", False):
            st.session_state["present_mode"] = present
            st.rerun()

        st.divider()
        st.markdown("**Scenario**")

        region_labels = {k: v["label"] for k, v in cat.REGIONS.items()}
        region = st.selectbox(
            "Target Azure region", list(cat.REGIONS),
            index=list(cat.REGIONS).index(sc.commercial.region),
            format_func=lambda r: region_labels[r],
            help="Prices are fetched live from the Azure Retail Prices API for this region.")
        currency = st.selectbox("Currency", cat.CURRENCIES,
                                index=cat.CURRENCIES.index(sc.commercial.currency),
                                help="Microsoft prices all services in USD. Other currencies "
                                     "are Microsoft's own conversions and are indicative.")
        live = st.toggle("Live vendor pricing", value=sc.live_pricing,
                         help="Off uses the local cache only, so the app works without a "
                              "network connection.")

        if (region != sc.commercial.region or currency != sc.commercial.currency
                or live != sc.live_pricing):
            scenario.update(commercial=replace(sc.commercial, region=region,
                                               currency=currency),
                            live_pricing=live)
            st.rerun()

        # ---- live scenario readout ---------------------------------------
        # Suppressed until an estate has been chosen: a running total computed
        # from an estate nobody picked is the thing Start here exists to prevent.
        if not sc.estate_source:
            st.markdown("<div style='margin:.9rem 0 .35rem 0'></div>",
                        unsafe_allow_html=True)
            st.markdown(ui.estate_badge(""), unsafe_allow_html=True)
            st.caption("Choose an estate on **Start here** and the model fills in.")
        else:
            try:
                res = scenario.current()
                cs, es, ss, ts = (res.cost_summary, res.effort_summary,
                                  res.schedule_summary, res.tco_summary)
                st.markdown("<div style='margin:.9rem 0 .35rem 0;font-size:.70rem;"
                            "font-weight:700;letter-spacing:.1em;text-transform:uppercase;"
                            "opacity:.62'>Scenario at a glance</div>",
                            unsafe_allow_html=True)
                ui.sidebar_kpis([
                    ("VMs in scope", f"{res.estate_summary['vm_count']:,}"),
                    ("Azure run rate",
                     f"{ui.compact_money(cs['monthly_total'], currency)}/mo"),
                    ("On-premises today",
                     f"{ui.compact_money(res.onprem_monthly, currency)}/mo"),
                    ("Programme cost", ui.compact_money(es["migration_cost"], currency)),
                    ("Duration", f"{ss.get('elapsed_months', 0):.1f} mo"),
                    ("Payback",
                     f"{ts['payback_years']:.1f} yr" if ts["payback_years"]
                     else "beyond horizon"),
                ])
                st.markdown(
                    ui.estate_badge(sc.estate_source, sc.estate_label)
                    + ui.pricing_badge(res.price_book.source), unsafe_allow_html=True)
            except Exception:
                st.caption("Scenario summary unavailable until the first page loads.")

        if not present:
            with st.expander("Pricing feed", expanded=False):
                if st.button("Test the Azure pricing API", width="stretch"):
                    st.session_state["_probe"] = pricing.probe()
                probe = st.session_state.get("_probe")
                if probe:
                    if probe["ok"]:
                        st.success(f"Reachable - {probe['latency_ms']} ms, "
                                   f"{probe['sample_items']} sample meters returned.")
                    else:
                        st.error(f"Unreachable: {probe['error']}")
                st.caption(
                    "Source: Azure Retail Prices API "
                    "(`prices.azure.com/api/retail/prices`, api-version "
                    "2023-01-01-preview). Unauthenticated, Microsoft's published retail "
                    "rates, including reserved instance and savings plan terms. Cached "
                    "locally for 24 hours.")

            st.divider()
            st.markdown("**AI advisor**")
            env_key = os.environ.get("OPENAI_API_KEY", "")
            key = st.text_input(
                "OpenAI API key", value=st.session_state.get("openai_key", ""),
                type="password",
                placeholder="sk-..." if not env_key else "Loaded from environment",
                help="Optional. Every calculation works without it - the model only writes "
                     "the narrative, and only from figures computed here.")
            if key:
                st.session_state["openai_key"] = key
            model = st.selectbox(
                "Model", llm.MODELS,
                index=llm.MODELS.index(st.session_state.get("openai_model",
                                                            llm.DEFAULT_MODEL)))
            st.session_state["openai_model"] = model
            st.caption("Advisor enabled." if llm.resolve_key(
                st.session_state.get("openai_key", "")) else
                "Advisor disabled - no key. Everything else still works.")

            st.divider()
            st.caption(
                "Figures are simulated from the estate profile you configure and priced "
                "against live Azure retail rates. A decision aid, not a quotation.")

        # Always available, presentation mode included -- you have to be able to
        # sign out of a machine you were projecting from.
        st.divider()
        auth.account_panel()


sidebar()

# --------------------------------------------------------------------------
# Navigation, grouped into the seven acts of the client narrative
# --------------------------------------------------------------------------
# Until somebody has said where the estate comes from, Start here is the landing
# page: an executive briefing computed from an estate nobody chose is the most
# misleading screen this application can show.
_chosen = bool(scenario.get_scenario().estate_source)

PAGES = {
    "0 - Start": [
        st.Page("views/start.py", title="Start here",
                icon=":material/play_circle:", default=not _chosen),
    ],
    "1 - Situation": [
        st.Page("views/overview.py", title="Executive briefing",
                icon=":material/insights:", default=_chosen),
        st.Page("views/assumptions.py", title="Model & assumptions",
                icon=":material/rule_settings:"),
    ],
    "2 - Discover": [
        st.Page("views/inventory.py", title="Estate discovery",
                icon=":material/inventory_2:"),
    ],
    "3 - Assess": [
        st.Page("views/assess.py", title="Readiness & 7R", icon=":material/fact_check:"),
        st.Page("views/effort.py", title="Complexity & effort", icon=":material/tune:"),
    ],
    "4 - Decide": [
        st.Page("views/provider.py", title="Cloud provider", icon=":material/cloud:"),
        st.Page("views/platform_options.py", title="Target platforms",
                icon=":material/hub:"),
        st.Page("views/future_state.py", title="Current & future state",
                icon=":material/compare_arrows:"),
        st.Page("views/cost.py", title="Azure cost simulator", icon=":material/payments:"),
        st.Page("views/business_case.py", title="Business case",
                icon=":material/account_balance:"),
    ],
    "5 - Plan": [
        st.Page("views/plan.py", title="Wave plan & timeline",
                icon=":material/calendar_month:"),
        st.Page("views/simulate.py", title="Risk simulation", icon=":material/casino:"),
    ],
    "6 - Execute": [
        st.Page("views/azure_migrate.py", title="Azure Migrate simulator",
                icon=":material/cloud_sync:"),
        st.Page("views/tooling.py", title="Migration tooling", icon=":material/build:"),
    ],
    "7 - Communicate": [
        st.Page("views/advisor.py", title="AI advisor", icon=":material/smart_toy:"),
    ],
}

nav = st.navigation(PAGES, expanded=True)
nav.run()

# Wayfinding for every page from one place: the order lives in ui.NARRATIVE, so
# the footer and the stepper cannot drift apart, and no view needs editing.
ui.next_step(nav.title)
