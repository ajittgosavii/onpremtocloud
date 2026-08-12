"""AI advisor: OpenAI turns the computed model into deliverables and answers questions."""

import json

import streamlit as st

from core import llm, scenario, ui

sc = scenario.get_scenario()
res = scenario.current()

ui.page_header(
    "AI advisor",
    "The numbers on every other page are computed locally and deterministically. The model's "
    "job here is narrow and honest: turn those numbers into the narrative, risk register and "
    "recommendation a client can act on - and answer questions about this estate, grounded in "
    "the facts passed to it. It is never asked to invent a price or a product limit.",
)

cfg = llm.LlmConfig(api_key=st.session_state.get("openai_key", ""),
                    model=st.session_state.get("openai_model", llm.DEFAULT_MODEL))
enabled = bool(llm.resolve_key(cfg.api_key))

if not enabled:
    ui.note(
        "No OpenAI API key is configured, so the advisor is disabled. Add one in the sidebar, "
        "or set <code>OPENAI_API_KEY</code> in the environment or a <code>.env</code> file. "
        "Everything else in this application works without it - the key buys narrative, not "
        "numbers.", "warn")

state = scenario.llm_state(res, sc)
context = llm.build_context(state)

ui.takeaway(
    "Generate the <b>Executive summary</b> and <b>Risk register</b> at the end of a workshop, "
    "while the client's own parameters are still loaded, and send them the same day. It "
    "converts a two-hour session into a document nobody had to write. If anyone asks what was "
    "shared with OpenAI, the <b>What the model can see</b> tab is the whole answer: aggregate "
    "figures only, no VM names, no hostnames, no uploaded file.")

tab_gen, tab_chat, tab_ctx = st.tabs(["Generate a deliverable", "Ask about this estate",
                                      "What the model can see"])

# --------------------------------------------------------------------------
with tab_gen:
    c1, c2 = st.columns([2, 1])
    task = c1.selectbox("Deliverable", list(llm.PROMPTS))
    temp = c2.slider("Temperature", 0.0, 1.0, 0.2, 0.05,
                     help="Low keeps it factual and close to the numbers. Raise it only if "
                          "the output feels mechanical.")
    extra = st.text_area(
        "Additional instructions (optional)", height=90,
        placeholder="e.g. The client's board meets in three weeks and the CFO is sceptical "
                    "about cloud costs. Emphasise the do-nothing case and the Broadcom "
                    "renewal exposure.")

    st.caption(llm.PROMPTS[task])

    if st.button("Generate", type="primary", disabled=not enabled, width="stretch"):
        prompt = llm.render_prompt(task, context, extra)
        cfg.temperature = temp
        box = st.container(border=True)
        try:
            with box:
                out = st.write_stream(llm.stream(prompt, cfg))
            st.session_state.setdefault("advisor_outputs", {})[task] = out
        except llm.LlmUnavailable as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(f"The model call failed: {exc}")

    saved = st.session_state.get("advisor_outputs", {})
    if saved:
        st.markdown("### Previously generated")
        for name, text in saved.items():
            with st.expander(name):
                st.markdown(text)
                st.download_button(f"Download '{name}'", text.encode("utf-8"),
                                   file_name=f"{name.lower().replace(' ', '_')}.md",
                                   mime="text/markdown", key=f"dl_{name}")
        if st.button("Clear generated outputs"):
            st.session_state["advisor_outputs"] = {}
            st.rerun()

# --------------------------------------------------------------------------
with tab_chat:
    st.caption("Every answer is grounded in the scenario snapshot on the third tab. Ask about "
               "trade-offs, sequencing, risk, or anything the pages left implicit.")

    if "chat" not in st.session_state:
        st.session_state["chat"] = []

    for msg in st.session_state["chat"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    suggestions = [
        "Which twenty VMs should go in the pilot wave, and why those?",
        "What is the single biggest risk to hitting the deadline, and how do I retire it?",
        "How would you defend this cost estimate to a sceptical CFO?",
        "What would change your recommendation from Azure IaaS to Azure Local?",
        "What does Azure Migrate not cover in this estate, and what does that cost?",
    ]
    cols = st.columns(len(suggestions))
    picked = None
    for col, s in zip(cols, suggestions):
        if col.button(s, width="stretch", disabled=not enabled,
                      key=f"sug_{hash(s)}"):
            picked = s

    typed = st.chat_input("Ask about this migration...", disabled=not enabled)
    question = picked or typed

    if question:
        st.session_state["chat"].append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)
        prompt = (f"CONTEXT (computed from the client's inventory and live Azure retail "
                  f"pricing):\n```json\n{context}\n```\n\nQUESTION:\n{question}")
        with st.chat_message("assistant"):
            try:
                history = [{"role": m["role"], "content": m["content"]}
                           for m in st.session_state["chat"][-8:-1]]
                out = st.write_stream(llm.stream(prompt, cfg, history=history))
                st.session_state["chat"].append({"role": "assistant", "content": out})
            except llm.LlmUnavailable as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(f"The model call failed: {exc}")

    if st.session_state["chat"] and st.button("Clear conversation"):
        st.session_state["chat"] = []
        st.rerun()

# --------------------------------------------------------------------------
with tab_ctx:
    st.markdown("### The exact facts passed to the model")
    st.caption(
        "This is the entire context. Nothing else about the estate reaches OpenAI - no VM "
        "names, no application names, no hostnames, no uploaded file. If the client's data is "
        "sensitive, this is the page to show their security team.")
    st.code(context, language="json")
    st.download_button("Download the context", context.encode("utf-8"),
                       file_name="advisor_context.json", mime="application/json")

    st.markdown("### System prompt")
    st.code(llm.SYSTEM, language="text")
