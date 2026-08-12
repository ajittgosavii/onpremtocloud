"""The sign-in cover.

This is the first screen a client sees on a projector, so it does a second job
besides taking a password: it states what the product is for. The signature
element is a discovery scan reading down a manifest of the reference estate,
because discovery is literally the product's first act, and the figures it reads
out are model outputs -- including the two that argue against the migration.

Everything is CSS. Streamlit strips <script> from markdown, and an iframe would
not be able to paint the page background, so motion here is keyframes only.
"""

import streamlit as st

from core import auth, brand

_PERIOD = 19.2          # one full pass of the manifest, in seconds
_ROW_H = 46             # row height in px; the scan step is the same figure


def _css() -> str:
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

:root {{
  --void: {brand.VOID};
  --plate: {brand.PLATE};
  --rule: {brand.RULE};
  --accent: {brand.ACCENT};
  --accent-2: {brand.ACCENT_2};
  --live: {brand.LIVE};
  --paper: {brand.PAPER};
  --dim: {brand.PAPER_DIM};
}}

/* ---- strip the application chrome; this page is a cover, not a screen ---- */
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"],
[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"], #MainMenu, footer {{ display: none !important; }}

.stApp {{
  background: var(--void);
  color: var(--paper);
  font-family: {brand.FONT_SANS};
}}
/* Two soft lights, breathing slowly. The only ambient motion on the page. */
.stApp::before {{
  content: ""; position: fixed; inset: 0; pointer-events: none; z-index: 0;
  background:
    radial-gradient(900px 620px at 14% 6%, rgba(59,111,212,.20), transparent 66%),
    radial-gradient(760px 560px at 92% 96%, rgba(122,91,196,.16), transparent 64%);
  animation: breathe 34s ease-in-out infinite alternate;
}}
@keyframes breathe {{ from {{ opacity: .72; }} to {{ opacity: 1; }} }}

.block-container {{
  position: relative; z-index: 1;
  max-width: 1180px;
  /* Optical centring. A fixed clamp rather than flex centring, because a flex
     scroll container clips the top of the page on a short viewport. */
  padding-top: clamp(1.5rem, 14vh, 8rem);
  padding-bottom: 3rem;
}}

@keyframes rise {{
  from {{ opacity: 0; transform: translateY(14px); }}
  to   {{ opacity: 1; transform: none; }}
}}
.rise {{ animation: rise .62s cubic-bezier(.22,.61,.36,1) both; }}
.rise-2 {{ animation-delay: .09s; }}
.rise-3 {{ animation-delay: .18s; }}

/* ---- cover ---- */
.suite {{
  display: flex; align-items: center; gap: .6rem;
  font-family: {brand.FONT_MONO};
  font-size: .70rem; font-weight: 500; letter-spacing: .30em;
  text-transform: uppercase; color: var(--dim); margin-bottom: 1.5rem;
}}
.suite .bar {{
  width: 26px; height: 2px; border-radius: 2px;
  background: linear-gradient(90deg, var(--accent), var(--accent-2));
}}
.mark {{
  font-size: clamp(3.2rem, 7vw, 4.9rem); font-weight: 700;
  letter-spacing: -.045em; line-height: .94; margin: 0;
  background: linear-gradient(96deg, var(--paper) 30%, #A9C2F2 78%);
  -webkit-background-clip: text; background-clip: text;
  -webkit-text-fill-color: transparent; color: var(--paper);
}}
.mark-sub {{
  font-family: {brand.FONT_MONO};
  font-size: .74rem; font-weight: 500; letter-spacing: .16em;
  text-transform: uppercase; color: var(--accent);
  margin: .7rem 0 1.35rem 0;
}}
.thesis {{
  font-size: 1.06rem; line-height: 1.66; color: var(--dim);
  max-width: 44ch; margin: 0 0 2.3rem 0;
}}

/* ---- signature: the discovery scan ---- */
.mf-head {{
  display: flex; align-items: center; justify-content: space-between;
  font-family: {brand.FONT_MONO};
  font-size: .655rem; letter-spacing: .20em; text-transform: uppercase;
  color: var(--dim); padding-bottom: .55rem; border-bottom: 1px solid var(--rule);
}}
.mf-live {{ color: var(--live); display: flex; align-items: center; gap: .42rem; }}
.mf-live .dot {{
  width: 6px; height: 6px; border-radius: 50%; background: var(--live);
  box-shadow: 0 0 0 3px rgba(63,191,131,.16);
}}

.mf-rows {{ position: relative; }}
.mf-scan {{
  position: absolute; left: -.7rem; right: -.7rem; top: 0; height: {_ROW_H}px;
  border-left: 2px solid var(--accent);
  background: linear-gradient(90deg, rgba(59,111,212,.19), rgba(122,91,196,.05) 62%,
                              transparent);
  animation: scan {_PERIOD}s steps(4) infinite;
  pointer-events: none;
}}
@keyframes scan {{
  from {{ transform: translateY(0); }}
  to   {{ transform: translateY({_ROW_H * 4}px); }}
}}

.mf-row {{
  position: relative; height: {_ROW_H}px;
  display: grid; grid-template-columns: 84px 108px 1fr;
  align-items: center; gap: .9rem;
  border-bottom: 1px solid var(--rule);
  opacity: .38; animation: rowOn {_PERIOD}s linear infinite;
}}
@keyframes rowOn {{
  0%   {{ opacity: .38; }}
  1%   {{ opacity: 1; }}
  24%  {{ opacity: 1; }}
  25%  {{ opacity: .38; }}
  100% {{ opacity: .38; }}
}}
.mf-row:nth-child(1) {{ animation-delay: 0s; }}
.mf-row:nth-child(2) {{ animation-delay: {_PERIOD / 4:.2f}s; }}
.mf-row:nth-child(3) {{ animation-delay: {_PERIOD / 2:.2f}s; }}
.mf-row:nth-child(4) {{ animation-delay: {_PERIOD * 3 / 4:.2f}s; }}

.mf-act {{
  font-family: {brand.FONT_MONO};
  font-size: .60rem; letter-spacing: .17em; text-transform: uppercase;
  color: var(--accent);
}}
.mf-fig {{
  font-family: {brand.FONT_MONO};
  font-size: 1.34rem; font-weight: 600; letter-spacing: -.03em;
  text-align: right; font-variant-numeric: tabular-nums;
}}
.mf-unit {{ font-size: .855rem; line-height: 1.35; color: var(--dim); }}

.mf-note {{ position: relative; min-height: 5.3rem; margin-top: 1.1rem; }}
.mf-note p {{
  position: absolute; inset: 0; margin: 0;
  font-size: .90rem; line-height: 1.62; color: var(--paper); opacity: 0;
  max-width: 52ch;
  animation: noteOn {_PERIOD}s linear infinite;
}}
@keyframes noteOn {{
  0%   {{ opacity: 0; transform: translateY(6px); }}
  3%   {{ opacity: .92; transform: none; }}
  23%  {{ opacity: .92; transform: none; }}
  26%  {{ opacity: 0; transform: translateY(-6px); }}
  100% {{ opacity: 0; transform: translateY(-6px); }}
}}
.mf-note p:nth-child(1) {{ animation-delay: 0s; }}
.mf-note p:nth-child(2) {{ animation-delay: {_PERIOD / 4:.2f}s; }}
.mf-note p:nth-child(3) {{ animation-delay: {_PERIOD / 2:.2f}s; }}
.mf-note p:nth-child(4) {{ animation-delay: {_PERIOD * 3 / 4:.2f}s; }}

.foot {{
  font-family: {brand.FONT_MONO};
  font-size: .655rem; letter-spacing: .10em; line-height: 1.9;
  color: rgba(232,237,247,.36); margin-top: 2.2rem;
  border-top: 1px solid var(--rule); padding-top: .9rem;
}}

/* ---- the sign-in plate: the form element itself is the card ---- */
[data-testid="stForm"] {{
  position: relative; overflow: hidden;
  background: linear-gradient(180deg, rgba(20,28,50,.92), rgba(14,20,38,.92));
  border: 1px solid var(--rule) !important;
  border-radius: 16px !important;
  padding: 1.85rem 1.7rem 1.5rem 1.7rem !important;
  box-shadow: 0 26px 60px rgba(3,6,16,.55);
  animation: rise .62s cubic-bezier(.22,.61,.36,1) .18s both;
}}
[data-testid="stForm"]::before {{
  content: ""; position: absolute; inset: 0 0 auto 0; height: 2px;
  background: linear-gradient(90deg, var(--accent), var(--accent-2), transparent);
}}
.plate-title {{
  font-size: 1.28rem; font-weight: 600; letter-spacing: -.02em; margin: 0 0 .3rem 0;
}}
.plate-sub {{ font-size: .845rem; line-height: 1.55; color: var(--dim);
             margin: 0 0 1.35rem 0; }}

/* Streamlit widget chrome sits on a light theme by default; restate it here. */
[data-testid="stForm"] label, [data-testid="stForm"] label p {{
  color: var(--dim) !important;
  font-family: {brand.FONT_MONO};
  font-size: .645rem !important; font-weight: 500 !important;
  letter-spacing: .17em !important; text-transform: uppercase;
}}
[data-testid="stForm"] div[data-baseweb="input"],
[data-testid="stForm"] div[data-baseweb="base-input"] {{
  background: rgba(8,12,23,.72) !important;
  border: 1px solid var(--rule) !important;
  border-radius: 10px !important;
  transition: border-color .16s ease, box-shadow .16s ease;
}}
[data-testid="stForm"] div[data-baseweb="input"]:focus-within {{
  border-color: rgba(59,111,212,.85) !important;
  box-shadow: 0 0 0 3px rgba(59,111,212,.20);
}}
[data-testid="stForm"] input {{
  background: transparent !important; color: var(--paper) !important;
  font-family: {brand.FONT_SANS}; font-size: .95rem !important;
  caret-color: var(--accent); border-radius: 9px;
}}
[data-testid="stForm"] input::placeholder {{ color: rgba(232,237,247,.30) !important; }}
/* Streamlit overlays "Press Enter to submit form" inside the focused field. The
   submit button is directly below and full width, so the hint only adds clutter. */
[data-testid="stForm"] [data-testid="InputInstructions"] {{ display: none !important; }}

/* A password manager filling these fields makes the text invisible otherwise.
   Chrome paints an autofilled input with its own light background and forces the
   text colour through -webkit-text-fill-color, which outranks `color`. The only
   way to repaint the background is a large inset shadow, and the only way to set
   the text is the -webkit property. The absurd transition delay stops Chrome
   animating its background back in on focus. */
[data-testid="stForm"] input:-webkit-autofill,
[data-testid="stForm"] input:-webkit-autofill:hover,
[data-testid="stForm"] input:-webkit-autofill:focus,
[data-testid="stForm"] input:-webkit-autofill:active {{
  -webkit-text-fill-color: {brand.PAPER} !important;
  -webkit-box-shadow: 0 0 0 1000px #0D1424 inset !important;
  box-shadow: 0 0 0 1000px #0D1424 inset !important;
  caret-color: var(--accent) !important;
  transition: background-color 600000s 0s, color 600000s 0s;
}}
[data-testid="stForm"] button[title="Show password text"],
[data-testid="stForm"] div[data-baseweb="input"] button {{
  color: var(--dim) !important; background: transparent !important; border: none !important;
}}
[data-testid="stForm"] [data-testid="stCheckbox"] label p {{
  text-transform: none !important; letter-spacing: .01em !important;
  font-family: {brand.FONT_SANS} !important; font-size: .82rem !important;
  color: var(--dim) !important;
}}
/* The box is label[data-baseweb=checkbox] > span; it defaults to the light theme. */
[data-testid="stForm"] label[data-baseweb="checkbox"] > span:first-child {{
  background-color: rgba(8,12,23,.75) !important;
  border-color: rgba(150,170,215,.38) !important;
}}
[data-testid="stForm"] label[data-baseweb="checkbox"]:hover > span:first-child {{
  border-color: rgba(59,111,212,.75) !important;
}}
[data-testid="stForm"] label[data-baseweb="checkbox"] input:checked ~ span:first-child,
[data-testid="stForm"] label[data-baseweb="checkbox"][aria-checked="true"] > span:first-child {{
  background-color: var(--accent) !important; border-color: var(--accent) !important;
}}

/* The button stretches via width="stretch" on the widget itself; Streamlit wraps
   it in a shrink-to-fit flex row that CSS alone cannot reliably widen. */
[data-testid="stFormSubmitButton"] button {{
  border: none !important; border-radius: 10px !important;
  padding: .70rem 1rem !important;
  background: linear-gradient(96deg, var(--accent), var(--accent-2)) !important;
  color: #fff !important; font-weight: 600 !important; font-size: .95rem !important;
  letter-spacing: .01em;
  box-shadow: 0 10px 26px rgba(59,111,212,.30);
  transition: transform .16s ease, box-shadow .16s ease, filter .16s ease;
}}
[data-testid="stFormSubmitButton"] button:hover {{
  transform: translateY(-1px); filter: brightness(1.07);
  box-shadow: 0 14px 32px rgba(59,111,212,.40);
}}
[data-testid="stFormSubmitButton"] button:active {{ transform: translateY(0); }}
[data-testid="stFormSubmitButton"] button:focus-visible {{
  outline: 2px solid #fff; outline-offset: 2px;
}}
/* The input already shows focus through its wrapper, so suppress the second
   ring rather than drawing a box inside a box. */
[data-testid="stForm"] input:focus-visible {{ outline: none; }}
[data-testid="stForm"] div[data-baseweb="input"] button:focus-visible {{
  outline: 2px solid var(--accent); outline-offset: 1px; border-radius: 6px;
}}
[data-testid="stForm"] label[data-baseweb="checkbox"]:focus-within > span:first-child {{
  box-shadow: 0 0 0 3px rgba(59,111,212,.35);
}}

.lg-alert {{
  border-left: 2px solid #E06B7E; border-radius: 0 8px 8px 0;
  background: rgba(224,107,126,.13); color: #FFD5DC;
  padding: .6rem .85rem; font-size: .845rem; line-height: 1.5;
  margin: 0 0 1.1rem 0;
}}
.lg-alert.info {{ border-left-color: var(--accent); background: rgba(59,111,212,.14);
                 color: #CFE0FF; }}
.lg-alert code {{
  font-family: {brand.FONT_MONO}; font-size: .78rem; color: inherit !important;
  background: rgba(255,255,255,.10); padding: .05rem .3rem; border-radius: 4px;
}}
.plate-foot {{
  margin-top: 1.15rem; padding-top: .95rem; border-top: 1px solid var(--rule);
  font-size: .755rem; line-height: 1.55; color: rgba(232,237,247,.42);
}}

/* Narrow screens: the rows wrap to two lines, so a scan stepping by a fixed row
   height would drift out of alignment. Drop the scan, light every row, and let
   the readout be a plain list. */
@media (max-width: 900px) {{
  .block-container {{ padding-top: 2rem; }}
  .mark {{ font-size: 3rem; }}
  .thesis {{ margin-bottom: 1.6rem; }}
  .foot {{ display: none; }}
  .mf-scan {{ display: none; }}
  .mf-row {{
    height: auto; min-height: {_ROW_H}px; padding: .5rem 0;
    grid-template-columns: 76px 92px 1fr; opacity: 1; animation: none;
  }}
  .mf-note {{ display: none; }}
}}

@media (prefers-reduced-motion: reduce) {{
  .stApp::before, .rise, .mf-scan, .mf-row, .mf-note p,
  [data-testid="stForm"] {{ animation: none !important; }}
  .rise, [data-testid="stForm"] {{ opacity: 1; transform: none; }}
  .mf-row {{ opacity: 1; }}
  .mf-note p {{ position: relative; opacity: .92; }}
  .mf-note p + p {{ display: none; }}
  .mf-scan {{ display: none; }}
}}
</style>
"""


def _cover() -> str:
    rows, notes = [], []
    for act, figure, unit, note in brand.READOUT:
        rows.append(f"<div class='mf-row'><div class='mf-act'>{act}</div>"
                    f"<div class='mf-fig'>{figure}</div>"
                    f"<div class='mf-unit'>{unit}</div></div>")
        notes.append(f"<p>{note}</p>")
    return (
        f"<div class='rise'>"
        f"<div class='suite'><span class='bar'></span>{brand.SUITE}</div>"
        f"<h1 class='mark'>{brand.PRODUCT}</h1>"
        f"<div class='mark-sub'>{brand.DESCRIPTOR}</div>"
        f"<p class='thesis'>{brand.THESIS}</p></div>"
        f"<div class='rise rise-2'>"
        f"<div class='mf-head'><span>Reference estate readout</span>"
        f"<span class='mf-live'><span class='dot'></span>live rates</span></div>"
        f"<div class='mf-rows'>{''.join(rows)}<div class='mf-scan'></div></div>"
        f"<div class='mf-note'>{''.join(notes)}</div></div>"
        f"<div class='rise rise-3'><div class='foot'>"
        f"Azure Retail Prices API &middot; AWS public rate feed &middot; "
        f"Microsoft product limits</div></div>")


def render() -> None:
    """Draw the sign-in cover. Call this instead of the application when signed out."""
    st.markdown(_css(), unsafe_allow_html=True)

    left, right = st.columns([1.18, 0.82], gap="large")
    with left:
        st.markdown(_cover(), unsafe_allow_html=True)

    with right:
        with st.form("sign_in", clear_on_submit=False, border=True):
            st.markdown("<div class='plate-title'>Sign in</div>"
                        "<div class='plate-sub'>Accounts are issued by the "
                        "engagement lead.</div>", unsafe_allow_html=True)
            message_slot = st.container()

            # No widget keys: the password must not outlive the run that read it.
            username = st.text_input("Username", placeholder="your.name")
            password = st.text_input("Password", type="password",
                                     placeholder="Password")
            remember = st.checkbox(
                f"Stay signed in on this browser for {auth.REMEMBER_HOURS} hours",
                value=False,
                help="Puts a signed token in the address bar so a reload does not "
                     "sign you out. Leave it off on a shared or projected machine.")
            submitted = st.form_submit_button(f"Sign in to {brand.PRODUCT}",
                                              width="stretch")

            st.markdown(f"<div class='plate-foot'>{brand.FOOTNOTE}</div>",
                        unsafe_allow_html=True)

        notice = auth.notice()
        error = ""
        if submitted:
            ok, error = auth.attempt(username, password, remember)
            if ok:
                st.rerun()

        if error:
            message_slot.markdown(f"<div class='lg-alert'>{error}</div>",
                                  unsafe_allow_html=True)
        elif notice:
            message_slot.markdown(f"<div class='lg-alert info'>{notice}</div>",
                                  unsafe_allow_html=True)
        elif auth.using_demo_account():
            message_slot.markdown(
                "<div class='lg-alert info'>No accounts are configured, so the demo "
                f"login is active: <code>{auth.DEMO_USER}</code> / "
                f"<code>{auth.DEMO_PASSWORD}</code>. Add an <code>[auth.users]</code> "
                "block to <code>.streamlit/secrets.toml</code> before this leaves your "
                "machine.</div>", unsafe_allow_html=True)
