"""Design system: theming, hero headers, KPI cards, chart defaults, formatting.

The visual language is deliberately restrained but not plain -- a single accent
gradient, generous whitespace, cards that lift on hover, and content that fades
up on load. It is built to be projected in front of a client, so type is large,
contrast is high, and every page opens by saying where it sits in the story.
"""

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# --------------------------------------------------------------------------
# Palette
# --------------------------------------------------------------------------
ACCENT = "#3B6FD4"
ACCENT_2 = "#7A5BC4"
POSITIVE = "#2F9E68"
WARNING = "#E08A2E"
NEGATIVE = "#C4485E"

PALETTE = ["#3B6FD4", "#E08A2E", "#2F9E68", "#C4485E", "#7A5BC4",
           "#2E8FA3", "#C46A9E", "#8A8F98", "#6B8F3B", "#C1553B"]
SEQUENTIAL = ["#EEF3FD", "#CBDAF6", "#9FBCEC", "#6E98DE", "#3B6FD4", "#28518F"]

STRATEGY_COLOURS = {
    "Retire": "#8A8F98", "Retain": "#C4485E", "Relocate": "#7A5BC4",
    "Rehost": "#3B6FD4", "Replatform": "#2F9E68", "Repurchase": "#E08A2E",
    "Refactor": "#2E8FA3",
}
READINESS_COLOURS = {
    "Ready for Azure": "#2F9E68",
    "Ready with conditions": "#E08A2E",
    "Not ready for Azure": "#C4485E",
    "Readiness unknown": "#8A8F98",
}
BAND_COLOURS = {"Simple": "#2F9E68", "Moderate": "#E08A2E",
                "Complex": "#C1553B", "Highly complex": "#C4485E"}


# --------------------------------------------------------------------------
# The client narrative -- drives the stepper on every page
# --------------------------------------------------------------------------
NARRATIVE: list[tuple[str, str, str]] = [
    # (act, page title, one-line purpose used as the eyebrow)
    ("Situation", "Executive briefing", "The answer, up front"),
    ("Situation", "Model & assumptions", "What we are assuming, and where to change it"),
    ("Discover", "Estate discovery", "What you actually have"),
    ("Assess", "Readiness & 7R", "What should happen to each workload"),
    ("Assess", "Complexity & effort", "How hard it is, and why"),
    ("Decide", "Cloud provider", "Which provider suits this estate"),
    ("Decide", "Target platforms", "Where it should land"),
    ("Decide", "Azure cost simulator", "What it costs to run"),
    ("Decide", "Business case", "Whether it is worth doing"),
    ("Plan", "Wave plan & timeline", "How long, and what constrains it"),
    ("Plan", "Risk simulation", "How confident we should be"),
    ("Execute", "Azure Migrate simulator", "How the tooling behaves, and its limits"),
    ("Execute", "Migration tooling", "What else you need to buy"),
    ("Communicate", "AI advisor", "Turning this into deliverables"),
]
_STEP_INDEX = {title: i for i, (_, title, _) in enumerate(NARRATIVE)}
ACTS = ["Situation", "Discover", "Assess", "Decide", "Plan", "Execute", "Communicate"]


def presenting() -> bool:
    """Presentation mode hides configuration and enlarges type for projection."""
    return bool(st.session_state.get("present_mode", False))


# --------------------------------------------------------------------------
# CSS
# --------------------------------------------------------------------------
def _css(present: bool) -> str:
    scale = 1.12 if present else 1.0
    return f"""
<style>
  :root {{
    --accent: {ACCENT};
    --accent-2: {ACCENT_2};
    --pos: {POSITIVE};
    --warn: {WARNING};
    --neg: {NEGATIVE};
    --card-bg: rgba(127,140,170,.055);
    --card-br: rgba(127,140,170,.20);
    --ink-dim: rgba(127,140,170,.95);
  }}

  .block-container {{
    padding-top: 1.6rem;
    padding-bottom: 4rem;
    max-width: 1560px;
  }}

  /* ---- entrance animation ---- */
  @keyframes fadeUp {{
    from {{ opacity: 0; transform: translateY(10px); }}
    to   {{ opacity: 1; transform: none; }}
  }}
  .block-container > div > div > div > [data-testid="stVerticalBlock"] > div {{
    animation: fadeUp .34s cubic-bezier(.22,.61,.36,1) both;
  }}
  @media (prefers-reduced-motion: reduce) {{
    .block-container > div > div > div > [data-testid="stVerticalBlock"] > div {{
      animation: none;
    }}
  }}

  /* ---- hero ---- */
  .hero {{
    position: relative;
    padding: 1.5rem 1.7rem 1.4rem 1.7rem;
    border-radius: 18px;
    background:
      radial-gradient(1100px 260px at 8% -30%, rgba(59,111,212,.20), transparent 62%),
      radial-gradient(760px 220px at 88% -50%, rgba(122,91,196,.17), transparent 60%),
      var(--card-bg);
    border: 1px solid var(--card-br);
    margin-bottom: 1.25rem;
    overflow: hidden;
  }}
  .hero::after {{
    content: "";
    position: absolute; inset: 0 0 auto 0; height: 3px;
    background: linear-gradient(90deg, var(--accent), var(--accent-2), transparent);
  }}
  .hero-eyebrow {{
    display: flex; align-items: center; gap: .55rem;
    font-size: {0.72 * scale}rem; font-weight: 700; letter-spacing: .10em;
    text-transform: uppercase; color: var(--accent); margin-bottom: .45rem;
  }}
  .hero-eyebrow .sep {{ opacity: .40; font-weight: 400; }}
  .hero-eyebrow .purpose {{
    color: var(--ink-dim); font-weight: 600; letter-spacing: .02em;
    text-transform: none; font-size: {0.78 * scale}rem;
  }}
  .hero h1 {{
    font-size: {2.05 * scale}rem !important;
    line-height: 1.12; letter-spacing: -.026em; font-weight: 700;
    margin: 0 0 .5rem 0 !important; padding: 0 !important;
  }}
  .hero .lede {{
    font-size: {1.0 * scale}rem; line-height: 1.62;
    opacity: .84; max-width: 90ch; margin: 0;
  }}

  /* ---- stepper ---- */
  .stepper {{
    display: flex; flex-wrap: wrap; gap: .3rem;
    margin: .1rem 0 1.35rem 0;
  }}
  .step {{
    font-size: .70rem; font-weight: 650; letter-spacing: .04em;
    padding: .26rem .68rem; border-radius: 999px;
    border: 1px solid var(--card-br); color: var(--ink-dim);
    background: transparent; white-space: nowrap;
    transition: all .18s ease;
  }}
  .step.done {{ opacity: .55; }}
  .step.now {{
    color: #fff; border-color: transparent;
    background: linear-gradient(92deg, var(--accent), var(--accent-2));
    box-shadow: 0 3px 12px rgba(59,111,212,.32);
  }}

  /* ---- KPI cards ---- */
  .kpi {{
    padding: .95rem 1.05rem; border-radius: 14px;
    background: var(--card-bg); border: 1px solid var(--card-br);
    height: 100%; transition: transform .18s ease, box-shadow .18s ease,
                              border-color .18s ease;
  }}
  .kpi:hover {{
    transform: translateY(-3px);
    box-shadow: 0 10px 26px rgba(20,30,60,.13);
    border-color: rgba(59,111,212,.42);
  }}
  .kpi-label {{
    font-size: {0.745 * scale}rem; font-weight: 650; letter-spacing: .035em;
    text-transform: uppercase; opacity: .68; margin-bottom: .34rem;
    line-height: 1.3;
  }}
  .kpi-value {{
    font-size: {1.72 * scale}rem; font-weight: 700; line-height: 1.12;
    letter-spacing: -.022em;
    font-variant-numeric: tabular-nums;
  }}
  .kpi-sub {{
    font-size: {0.775 * scale}rem; opacity: .70; margin-top: .3rem;
    line-height: 1.42;
  }}
  .kpi-sub.pos {{ color: var(--pos); opacity: .95; font-weight: 600; }}
  .kpi-sub.neg {{ color: var(--neg); opacity: .95; font-weight: 600; }}
  .kpi-sub.warn {{ color: var(--warn); opacity: .95; font-weight: 600; }}
  .kpi-accent {{ height: 3px; border-radius: 3px; margin-bottom: .8rem;
                 background: linear-gradient(90deg, var(--accent), var(--accent-2)); }}

  /* ---- callouts ---- */
  .note, .warn, .bad, .good {{
    border-left: 3px solid var(--accent);
    padding: .68rem 1rem; border-radius: 0 10px 10px 0;
    background: rgba(59,111,212,.075);
    font-size: {0.90 * scale}rem; line-height: 1.62; margin: .55rem 0 1.15rem 0;
  }}
  .warn {{ border-left-color: var(--warn); background: rgba(224,138,46,.095); }}
  .bad  {{ border-left-color: var(--neg);  background: rgba(196,72,94,.095); }}
  .good {{ border-left-color: var(--pos);  background: rgba(47,158,104,.095); }}

  /* ---- the client talking point ---- */
  .takeaway {{
    position: relative;
    padding: 1.0rem 1.2rem 1.0rem 1.35rem;
    border-radius: 14px; margin: 1.1rem 0 1.5rem 0;
    background: linear-gradient(96deg, rgba(59,111,212,.13), rgba(122,91,196,.085));
    border: 1px solid rgba(59,111,212,.30);
  }}
  .takeaway .tk-label {{
    font-size: .68rem; font-weight: 750; letter-spacing: .12em;
    text-transform: uppercase; color: var(--accent); margin-bottom: .4rem;
  }}
  .takeaway .tk-body {{
    font-size: {1.0 * scale}rem; line-height: 1.62; font-weight: 500;
  }}

  /* ---- pills ---- */
  .pill {{
    display: inline-block; padding: .2rem .68rem; border-radius: 999px;
    font-size: .73rem; font-weight: 650; letter-spacing: .025em;
    background: rgba(127,140,170,.16); margin: 0 .35rem .4rem 0;
    border: 1px solid var(--card-br);
  }}
  .pill-live  {{ background: rgba(47,158,104,.18); color: #2b8659;
                 border-color: rgba(47,158,104,.42); }}
  .pill-cache {{ background: rgba(224,138,46,.18); color: #9d5f18;
                 border-color: rgba(224,138,46,.42); }}
  .pill-off   {{ background: rgba(196,72,94,.18); color: #96354a;
                 border-color: rgba(196,72,94,.42); }}

  /* ---- section rule ---- */
  .sect {{ margin: 2.1rem 0 .3rem 0; }}
  .sect h2 {{
    font-size: {1.24 * scale}rem !important; font-weight: 680;
    letter-spacing: -.014em; margin: 0 0 .2rem 0 !important;
  }}
  .sect .sect-sub {{ font-size: {0.865 * scale}rem; opacity: .70; line-height: 1.55;
                     max-width: 88ch; }}
  .sect .rule {{
    height: 2px; width: 52px; border-radius: 2px; margin: .55rem 0 .1rem 0;
    background: linear-gradient(90deg, var(--accent), var(--accent-2));
  }}

  /* ---- native widget polish ---- */
  h2 {{ font-size: {1.24 * scale}rem !important; }}
  h3 {{ font-size: {1.03 * scale}rem !important; font-weight: 660; }}
  [data-testid="stMetricValue"] {{ font-size: {1.6 * scale}rem; font-weight: 700; }}
  [data-testid="stMetricLabel"] {{ opacity: .70; font-size: {0.79 * scale}rem; }}
  .stTabs [data-baseweb="tab-list"] {{ gap: .15rem; }}
  .stTabs [data-baseweb="tab"] {{
    font-weight: 620; font-size: {0.90 * scale}rem;
    padding: .55rem .95rem; border-radius: 9px 9px 0 0;
  }}
  [data-testid="stExpander"] details {{
    border-radius: 12px; border: 1px solid var(--card-br);
  }}
  [data-testid="stSidebar"] {{ border-right: 1px solid var(--card-br); }}
  .side-kpi {{
    display: flex; justify-content: space-between; align-items: baseline;
    padding: .30rem 0; border-bottom: 1px dashed var(--card-br);
    font-size: .805rem;
  }}
  .side-kpi span:first-child {{ opacity: .70; }}
  .side-kpi span:last-child {{ font-weight: 700; font-variant-numeric: tabular-nums; }}

  /* ---- signed-in account block ---- */
  .acct {{ display: flex; align-items: center; gap: .6rem; margin-bottom: .55rem; }}
  .acct-mark {{
    width: 32px; height: 32px; border-radius: 9px; flex: 0 0 32px;
    display: flex; align-items: center; justify-content: center;
    background: linear-gradient(96deg, var(--accent), var(--accent-2));
    color: #fff; font-size: .74rem; font-weight: 700; letter-spacing: .02em;
  }}
  .acct-name {{ font-size: .855rem; font-weight: 650; line-height: 1.25; }}
  .acct-role {{ font-size: .70rem; opacity: .62; letter-spacing: .04em;
                text-transform: uppercase; }}
  {".stExpander {display:none !important;}" if present else ""}
</style>
"""


CSS = _css(False)


def install_theme() -> None:
    """Plotly template. Called once from app.py before any chart is drawn."""
    tmpl = go.layout.Template()
    tmpl.layout = go.Layout(
        colorway=PALETTE,
        font=dict(family="Inter, 'Segoe UI', system-ui, -apple-system, sans-serif",
                  size=13),
        title=dict(font=dict(size=15.5, weight=600), x=0, xanchor="left", pad=dict(b=12)),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=8, r=14, t=52, b=10),
        xaxis=dict(showgrid=False, zeroline=False, showline=True, linewidth=1,
                   linecolor="rgba(127,140,170,.32)", ticks="outside", ticklen=4,
                   tickfont=dict(size=12)),
        yaxis=dict(gridcolor="rgba(127,140,170,.16)", zeroline=False, showline=False,
                   tickfont=dict(size=12)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title_text="",
                    font=dict(size=12)),
        hoverlabel=dict(font_size=12.5, bordercolor="rgba(127,140,170,.4)"),
        transition=dict(duration=420, easing="cubic-in-out"),
        bargap=0.26,
    )
    pio.templates["migsim"] = tmpl
    pio.templates.default = "migsim"


def inject_css() -> None:
    st.markdown(_css(presenting()), unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Page furniture
# --------------------------------------------------------------------------
def _esc(text: str) -> str:
    return text


def stepper(title: str) -> str:
    """Horizontal act stepper with the current act highlighted."""
    idx = _STEP_INDEX.get(title)
    if idx is None:
        return ""
    current_act = NARRATIVE[idx][0]
    cur_pos = ACTS.index(current_act)
    chips = []
    for i, act in enumerate(ACTS):
        cls = "now" if i == cur_pos else ("done" if i < cur_pos else "")
        chips.append(f"<div class='step {cls}'>{i + 1}. {act}</div>")
    return f"<div class='stepper'>{''.join(chips)}</div>"


def page_header(title: str, lede: str) -> None:
    """Hero header with the narrative position, plus the act stepper beneath."""
    idx = _STEP_INDEX.get(title)
    if idx is not None:
        act, _, purpose = NARRATIVE[idx]
        eyebrow = (f"<div class='hero-eyebrow'>"
                   f"<span>Step {idx + 1} of {len(NARRATIVE)}</span>"
                   f"<span class='sep'>/</span><span>{act}</span>"
                   f"<span class='sep'>&middot;</span>"
                   f"<span class='purpose'>{purpose}</span></div>")
    else:
        eyebrow = ""
    st.markdown(
        f"<div class='hero'>{eyebrow}<h1>{title}</h1>"
        f"<p class='lede'>{lede}</p></div>",
        unsafe_allow_html=True)
    step = stepper(title)
    if step:
        st.markdown(step, unsafe_allow_html=True)


def section(title: str, subtitle: str = "") -> None:
    """Section heading with an accent rule -- replaces bare ## markdown."""
    sub = f"<div class='sect-sub'>{subtitle}</div>" if subtitle else ""
    st.markdown(f"<div class='sect'><h2>{title}</h2><div class='rule'></div>{sub}</div>",
                unsafe_allow_html=True)


def note(text: str, kind: str = "note") -> None:
    st.markdown(f"<div class='{kind}'>{text}</div>", unsafe_allow_html=True)


def page_link(path: str, label: str, icon: str = "", container=None) -> None:
    """``st.page_link`` that degrades to a caption when no page registry exists.

    The registry is only populated by ``st.navigation`` in app.py, so a bare page
    executed on its own -- which is how the headless smoke test runs them --
    would otherwise raise. The link is navigation sugar, not content, so falling
    back keeps every page independently renderable.
    """
    target = container if container is not None else st
    try:
        target.page_link(path, label=label, icon=icon or None)
    except Exception:
        target.caption(f"-> {label}")


def takeaway(text: str, label: str = "The point to make") -> None:
    """The line to say out loud when presenting this screen to a client."""
    st.markdown(
        f"<div class='takeaway'><div class='tk-label'>{label}</div>"
        f"<div class='tk-body'>{text}</div></div>", unsafe_allow_html=True)


# --------------------------------------------------------------------------
# KPI cards
# --------------------------------------------------------------------------
def _tone(sub: str | None) -> str:
    if not sub:
        return ""
    s = sub.strip()
    if s.startswith("-"):
        return "pos"          # a cost reduction reads as good
    if s.startswith("+"):
        return "neg"
    return ""


def metric_row(items: list[tuple[str, str, str | None]], tones: list[str] | None = None) -> None:
    """Row of KPI cards. ``items`` = [(label, value, sub)].

    ``tones`` optionally forces "pos" | "neg" | "warn" | "" per card; otherwise
    the tone is inferred from a leading +/- in the sub-line.
    """
    cols = st.columns(len(items), gap="small")
    for i, (col, (label, value, sub)) in enumerate(zip(cols, items)):
        tone = (tones[i] if tones and i < len(tones) else _tone(sub))
        sub_html = f"<div class='kpi-sub {tone}'>{sub}</div>" if sub else ""
        col.markdown(
            f"<div class='kpi'><div class='kpi-accent'></div>"
            f"<div class='kpi-label'>{label}</div>"
            f"<div class='kpi-value'>{value}</div>{sub_html}</div>",
            unsafe_allow_html=True)


def sidebar_kpis(rows: list[tuple[str, str]]) -> None:
    """Compact live scenario readout for the sidebar."""
    html = "".join(f"<div class='side-kpi'><span>{k}</span><span>{v}</span></div>"
                   for k, v in rows)
    st.markdown(html, unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Formatting
# --------------------------------------------------------------------------
_SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "AUD": "A$", "CAD": "C$",
            "INR": "₹", "JPY": "¥", "CHF": "CHF ", "BRL": "R$", "NZD": "NZ$"}


def money(x: float, currency: str = "USD", decimals: int = 0) -> str:
    sym = _SYMBOLS.get(currency, f"{currency} ")
    return f"{sym}{x:,.{decimals}f}"


def compact_money(x: float, currency: str = "USD") -> str:
    sym = _SYMBOLS.get(currency, "")
    a = abs(x)
    if a >= 1e9:
        return f"{sym}{x / 1e9:.2f}bn"
    if a >= 1e6:
        return f"{sym}{x / 1e6:.2f}m"
    if a >= 1e3:
        return f"{sym}{x / 1e3:.1f}k"
    return f"{sym}{x:,.0f}"


def pricing_badge(source: str) -> str:
    label = {"live": ("Live vendor pricing", "pill-live"),
             "cache": ("Cached vendor pricing", "pill-cache"),
             "cache-stale": ("Stale cache -- API unreachable", "pill-cache"),
             "unavailable": ("Pricing unavailable", "pill-off")}.get(
        source, ("Pricing", "pill"))
    return f"<span class='pill {label[1]}'>{label[0]}</span>"


# --------------------------------------------------------------------------
# Charts
# --------------------------------------------------------------------------
def legend_top(fig, title: str = "", height: int | None = None):
    """Lay a horizontal legend beneath the chart title instead of on top of it.

    The template puts the title and a horizontal legend in the same place, which
    is fine for the legend-less charts ``bar`` and ``donut`` build but collides on
    anything with a colour dimension. Plotly Express compounds it by writing the
    colour column's own name into the legend, so a chart heading ends up sharing a
    line with the word "tier" or "os_family".

    Call this on any figure that shows a legend. ``title`` is normally left empty:
    the swatch labels in this application say what they are.
    """
    fig.update_layout(
        title=dict(y=0.985, yanchor="top", yref="container"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0,
                    title_text=title, font=dict(size=12)),
        margin=dict(t=86),
    )
    if height is not None:
        fig.update_layout(height=height)
    return fig


def log_ticks(fig, axis: str = "x", values=(1, 2, 4, 8, 16, 32, 64, 128, 256)):
    """Label a log axis at the given values only.

    Plotly's default log ticks interleave minor ticks without their exponent, so a
    run of decades reads "2, 100, 5, 2, 10" -- actively misleading rather than
    merely dense. The quantities plotted on log axes here (vCPU, RAM GiB) are
    powers of two, so naming the ticks is both clearer and shorter.
    """
    update = dict(tickmode="array", tickvals=list(values),
                  ticktext=[format(v, ",g") for v in values])
    (fig.update_xaxes if axis == "x" else fig.update_yaxes)(**update)
    return fig


def bar(df, x: str, y: str, title: str = "", colour_map: dict | None = None,
        orientation: str = "v", height: int = 340, text_fmt: str | None = None):
    colours = [colour_map.get(v, PALETTE[0]) for v in df[x]] if colour_map else PALETTE[0]
    text = df[y].map(lambda v: format(v, text_fmt)) if text_fmt else None
    if orientation == "h":
        fig = go.Figure(go.Bar(x=df[y], y=df[x], orientation="h", marker_color=colours,
                               text=text, textposition="auto",
                               marker_line_width=0, hovertemplate="%{y}: %{x}<extra></extra>"))
        fig.update_layout(yaxis=dict(autorange="reversed"))
    else:
        fig = go.Figure(go.Bar(x=df[x], y=df[y], marker_color=colours, text=text,
                               textposition="auto", marker_line_width=0,
                               hovertemplate="%{x}: %{y}<extra></extra>"))
    fig.update_layout(title=title, height=height, showlegend=False)
    fig.update_traces(marker_cornerradius=5)
    return fig


def donut(labels, values, title: str = "", colour_map: dict | None = None, height: int = 340):
    colours = ([colour_map.get(l, PALETTE[i % len(PALETTE)]) for i, l in enumerate(labels)]
               if colour_map else PALETTE)
    fig = go.Figure(go.Pie(labels=list(labels), values=list(values), hole=0.62,
                           marker=dict(colors=colours,
                                       line=dict(color="rgba(0,0,0,0)", width=2)),
                           textinfo="label+percent", textposition="outside",
                           sort=False))
    fig.update_layout(title=title, height=height, showlegend=False)
    return fig


def df_download(df, filename: str, label: str = "Download CSV") -> None:
    st.download_button(label, df.to_csv(index=False).encode("utf-8"),
                       file_name=filename, mime="text/csv")
