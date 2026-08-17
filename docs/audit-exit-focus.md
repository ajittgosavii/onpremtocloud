# Audit: refocusing Ascend purely on VMware exit strategy

**Status:** executed 2026-08-17 in commits fb53778, f7dff23, d9a1ebf. Audit
written the same day.

> **Correction to the original headline.** This audit was written as "18 pages
> -> 11". The arithmetic was wrong: 13 pages are kept, 3 merged away and 2 cut,
> so 18 - 5 = **13**. The resulting-shape diagram below was always right; only
> the count in the summary was not. Which pages to keep did not change.
**Objective:** the application should answer one question — *how does an
organisation leave Broadcom-era VMware, and which destination should each part
of the estate go to?* Everything that does not serve that question should be
cut or merged.

The application had **18 pages**. This audit proposed, and the application now
has, **13**.

---

## Evidence used

Two measures per page: size, and how often it touches the exit subject
(`broadcom|vmware|exit|vcf|vsphere|esxi`). Neither is decisive alone — the Azure
Migrate page barely says "VMware" but is central, because the source paper
devotes an entire section to Azure Migrate as the migration control plane.

| Page | Lines | Exit mentions | Verdict |
|---|---:|---:|---|
| `broadcom.py` | 195 | 31 | **Keep** — the spine of the product |
| `platform_options.py` | 344 | 34 | **Keep** — the options. This *is* the question |
| `effort.py` | 235 | 38 | **Keep** — highest relevance of any page |
| `business_case.py` | 368 | 25 | **Keep** — absorb cost + risk into it |
| `exit_readiness.py` | 121 | 12 | **Keep** |
| `assess.py` | 290 | 7 | **Keep** — 7R segmentation drives destination |
| `inventory.py` | 275 | 8 | **Keep** |
| `plan.py` | 263 | 7 | **Keep** |
| `future_state.py` | 202 | 7 | **Keep** |
| `azure_migrate.py` | 484 | 2 | **Keep** — mentions are low, importance is not |
| `overview.py` | 271 | 2 | **Keep** |
| `start.py` | 223 | 4 | **Keep** |
| `assumptions.py` | 165 | 2 | **Keep** — the credibility page |
| `tooling.py` | 177 | 3 | **Merge** into Azure Migrate |
| `cost.py` | 281 | 0 | **Merge** into Business case |
| `simulate.py` | 247 | 0 | **Merge** into Business case |
| `provider.py` | 353 | 3 | **Cut** |
| `advisor.py` | 147 | 1 | **Cut** |

---

## Cut

### 1. Cloud provider (`views/provider.py`, 353 lines)

Ranks Azure vs AWS vs Google vs OCI. It is good work and it answers the wrong
question. The source paper is explicit: Azure is already the chosen strategic
destination and *"this paper does not re-litigate that decision"*. A client
deciding how to leave Broadcom is not simultaneously re-running a hyperscaler
selection; putting one in front of them reopens a settled decision and dilutes
the exit narrative.

**Salvage before deleting.** Two findings from `core/providers.py` are genuinely
valuable to the exit case and should be relocated, not lost:

- Azure and AWS charge **identically** for licence-included Windows compute. The
  Azure case is Hybrid Benefit and free ESU, not cheaper cores.
- Without Software Assurance the Azure advantage narrows sharply.

Move both onto **Business case** as a short "why Azure, in one panel" note.
Keep `core/providers.py` — the licensing comparison feeds that note.

### 2. AI advisor (`views/advisor.py`, 147 lines)

Requires an OpenAI key, is optional by design, and writes narrative rather than
deciding anything. It is a demo feature, not an exit-strategy feature, and it is
the only page that sends anything to a third party. Cutting it also removes the
`openai` dependency and the API-key control from the sidebar, which simplifies
the security conversation with a client's InfoSec team to "nothing leaves the
application except public price-list lookups".

---

## Merge

### 3. Migration tooling → Azure Migrate

The source paper treats these as one topic: Azure Migrate is the control plane,
and §5.10 is *"where to supplement Azure Migrate"* — which is exactly what the
tooling market page contains. Two pages currently make the reader assemble that
argument themselves. Merge as tabs on one page renamed **"Migration tooling"**,
with the Azure Migrate assessment first and the supplementary market second.

### 4. Azure cost simulator → Business case

`cost.py` has **zero** exit-subject mentions. It is a pricing-lever workbench —
reservations, savings plans, non-production scheduling, storage tiering. Those
levers matter, but they are inputs to the business case, not a destination in
the narrative. Move as a "Cost levers" tab inside Business case.

### 5. Risk simulation → Business case

Also zero exit mentions. Monte Carlo over the programme is a confidence
statement about the business case, so it belongs beside it as a "Confidence"
tab. This also fixes a narrative oddity: the Plan act currently ends on a
statistical page rather than on the wave plan.

---

## Resulting shape — 13 pages

```
0  Start        Start here
1  Situation    Broadcom exposure  ·  Executive briefing  ·  Model & assumptions
2  Discover     Estate discovery
3  Assess       Readiness & 7R  ·  Complexity & effort
4  Destination  Target platforms  ·  Current & future state  ·  Business case
5  Plan         Wave plan & timeline
6  Execute      Azure Migrate & tooling  ·  Exit readiness
```

The Communicate act disappeared with the AI advisor. Act 4 was renamed, but to
**Destination** rather than the paper's full phrase "choose the destination":
`ui.ACTS` renders as chips in the stepper, and one long label beside six short
ones unbalances the row.

---

## Execution order

Do these in sequence; each leaves the application working.

1. **Merge first, cut second.** Salvage the provider licensing findings onto
   Business case *before* deleting `provider.py`, or the insight is lost.
2. For every removed page, update **all six** registration points or the app
   breaks. Verified by grep, 2026-08-17:

   | # | Location | What it holds |
   |---|---|---|
   | 1 | `core/ui.py` `NARRATIVE` | act, page title, eyebrow purpose |
   | 2 | `core/ui.py` `_PAGE_PATHS` | title to path, for the next-step footer |
   | 3 | `app.py` `PAGES` | the `st.Page` registration |
   | 4 | `tools_smoketest.py` `PAGES` | the render test |
   | 5 | `core/assumptions.py` (~line 35) | **easy to miss** — maps every assumption to the page that controls it |
   | 6 | `ui.page_link` calls in other views | `views/overview.py:252` links to `views/cost.py` |

   Re-verify before starting:
   `grep -rn "views/provider.py\|views/advisor.py\|views/cost.py\|views/simulate.py\|views/tooling.py" views/ core/ app.py tools_smoketest.py`
3. `NARRATIVE` titles must match `st.Page` titles exactly or the stepper and
   eyebrow silently vanish.
4. Removing the advisor lets `openai` come out of `requirements.txt` — but check
   `core/llm.py` is no longer imported anywhere first.
5. Bump `ui.API_VERSION` **and** `app.py` `REQUIRED_UI_API` together if any
   `core/ui.py` function is added or removed; `tools_deploycheck.py` fails if
   they drift.
6. Run after every step: `py -3.12 tools_deploycheck.py && py -3.12 tools_smoketest.py`.

---

## Open question for the client, not for the code

Cutting Cloud provider assumes Azure is settled. That is true for the source
paper's client. If Ascend is meant to be reusable across clients where the
destination is *not* settled, keep the page but move it behind Start here as an
optional "the destination is not yet decided" branch, rather than leaving it in
the main narrative.

---

## What was actually done

Executed in the order above; each commit left the application rendering.

| Commit | Change |
|---|---|
| `fb53778` | `cost.py` and `simulate.py` merged into Business case; the "why Azure" salvage panel added |
| `f7dff23` | `tooling.py` merged into `azure_migrate.py`, renamed **Azure Migrate & tooling** |
| `d9a1ebf` | `provider.py` and `advisor.py` cut; `openai` removed; act 4 renamed |

Where the merged content landed:

* **Cost simulator** -> Business case, across two tabs rather than one. The
  commercial levers, lever sensitivity, commitment comparison and the live price
  feed became the *Cost levers* tab; the monthly run rate, cost-by-dimension and
  cost concentration went onto *Azure cost base*, beside the annual view they
  explain.
* **Risk simulation** -> Business case, *Confidence* tab, flattened from four
  tabs into sections. Nested tabs were avoided deliberately.
* **Tooling market** -> Azure Migrate, as *Where to supplement it* (ranking and
  recommended stack) and *The tooling market* (cost, heat map, full detail).

Two things fell out that the audit did not anticipate:

1. **The Monte Carlo had to be memoised.** Streamlit executes every tab body on
   every rerun, so once the simulation lived in a tab, 10,000 iterations ran
   again each time an unrelated slider moved. `scenario.monte_carlo` now caches
   on `sc.key()`, the same way `scenario.current()` does.
2. **Cutting the advisor removed more than one page.** `core/llm.py`,
   `scenario.llm_state`, the sidebar API-key panel, `import os` in `app.py`, and
   entries in `tools_env_check.py` and `tools_deploycheck.py` went with it.

The sixth registration point the audit flagged as easy to miss -- the page map in
`core/assumptions.py` -- was the one that needed the most care: ten assumptions
pointed at the cost simulator and two at the risk simulation, and all of them had
to be repointed at Business case rather than simply deleted.

Verified after each step with `tools_deploycheck.py` and `tools_smoketest.py`,
and at the end with `tools_selftest.py engines` and `tools_authtest.py`.

**Still open:** Business case shows stay-vs-migrate, not the paper's Scenario
A/B/C. Those three scenarios live on the Broadcom page, so the two pages can
still disagree. That reconciliation is the next piece of work.
