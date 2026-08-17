# Audit: does the application say what the source paper says?

**Status:** audit complete and **fully executed** on 2026-08-17, in commits
`d3b0400`, `7f05754`, `316c3b9`, `bd05358`, `7ddb9c7`, `1b9d4ba`, `a4c9a90` and
`b5468bb`. Every gap below is closed. Three of the "aligned" rows in the first
pass turned out to be wrong on closer reading and are corrected in place --
§5.9, §6.1 and §6.3. See *What was executed* at the end.
**Question asked:** is the application aligned with the source paper, and does it
present *all* the alternatives the paper assesses?

**Short answer.** Alignment on framework and discipline is strong — in several
places exact. Alignment on **alternatives is not complete**: the paper assesses
fourteen destinations and the application models fourteen, but they are not the
same fourteen. Ten of the paper's thirteen numbered options have a modelled
equivalent; three do not, and the catch-all section is largely absent. Separately,
**six whole sections of the paper have no representation in the application at
all** — none of them about alternatives, all of them about programme governance.

> Source discipline: this document uses the paper's facts and structure. It does
> not name the paper, its author or the client, because this repository is
> public. Keep it that way if this file is edited.

---

## 1. The alternatives — the direct answer

The paper assesses fourteen destinations (§4.1–4.14) and states that they resolve
into five archetypes (§3.4). The application carries fourteen platform entries in
`core/platforms.py`. The counts match by coincidence, not by coverage.

| Paper | Option | In the app? | As |
|---|---|---|---|
| 4.1 | Stay and renegotiate — VCF 9.1 | **Yes** | Stay on VMware (VCF 9, renegotiated) |
| 4.2 | Azure VMware Solution with VCF BYOL | **Yes** | Azure VMware Solution (AVS) |
| 4.3 | Azure IaaS — native rehost | **Yes** | Azure native IaaS (rehost) |
| 4.4 | Azure PaaS and containers — refactor | **Yes** | Azure PaaS (replatform / refactor) |
| 4.5 | Azure Local (Arc-enabled on-premises) | **Yes** | Azure Local |
| 4.6 | Hyper-V on Windows Server 2025 with SCVMM | **Yes** | Microsoft Hyper-V / Windows Server + SCVMM |
| 4.7 | Nutanix AHV on-premises | **Yes** | Nutanix AHV on-premises |
| 4.8 | Nutanix Cloud Clusters (NC2) on Azure | **Yes** | Nutanix Cloud Clusters (NC2) on Azure |
| 4.9 | Red Hat OpenShift Virtualization (KubeVirt) | **Yes** | Red Hat OpenShift Virtualization |
| 4.10 | **SUSE Virtualization (Harvester) with Rancher** | **No** | — |
| 4.11 | Proxmox VE | **Yes** | Proxmox VE |
| 4.12 | **XCP-ng / Vates Virtualization Management Stack** | **No** | — |
| 4.13 | **OpenStack — managed or self-managed** | **No** | — |
| 4.14 | Other credible platforms (six named) | **Partly** | GCVE and OCVS only |

**10 of 13 numbered options modelled. 3 missing outright.**

Section 4.14 names six: Scale Computing HyperCore, Verge.io, Oracle
OLVM / OCVS, Bigstack CubeCOS, oVirt, and GCVE / AWS Elastic VMware Service. The
application carries Google Cloud VMware Engine and Oracle Cloud VMware Solution
as full platform entries — but as *options*, not as the paper frames them, which
is "evaluated and not shortlisted". Scale Computing, Verge.io, Bigstack, oVirt
and AWS EVS do not appear.

The application also carries two entries the paper does not assess at all:
**Azure Stack Hub** and **Azure Arc only (stay put, manage from Azure)**. Neither
is wrong — Arc-only is a genuinely useful interim position — but both should be
recognised as additions to the paper rather than reflections of it.

### Why the three missing options matter more than their ranking suggests

The paper is explicit that none of 4.10, 4.12 or 4.13 is recommended for this
client. It would be easy to conclude they are safe to omit. That reading inverts
the paper's own argument:

> "an option that scores poorly here may still be worth evaluating formally,
> because a documented, credible alternatives evaluation is itself the lever that
> moves the incumbent's renewal quote" (§4)

and, on the catch-all section, that the platforms are "recorded here so the
evaluation can be shown to be comprehensive" (§4.14).

The application's own Scenario B — the negotiated renewal — is priced on exactly
that lever. So the omissions weaken the artefact that Scenario B's value depends
on. A client asked "did you look at OpenStack?" and answering "no" costs more
than the modelling effort of adding it.

### Archetype coverage is uneven

| Archetype | Paper's options | Modelled |
|---|---|---|
| A — Stay and optimise | 4.1 | 1 of 1 |
| B — Managed VMware in cloud | 4.2 | 1 of 1 |
| C — Cloud-native | 4.3, 4.4 | 2 of 2 |
| D — Alternative on-premises | 4.5, 4.6, 4.7, 4.11, 4.12, 4.13, 4.14 | **4 of 7** |
| E — Kubernetes-unified | 4.9, 4.10 | **1 of 2** |

Archetype E is the one that reads as thin. The paper gives it two options and
contrasts them directly — Harvester as the lighter-footprint, open-source-licensed
counterpart to OpenShift. With only OpenShift present, the app implies the
Kubernetes-unified route is an OpenShift decision, which is not what the paper says.

---

## 2. Where alignment is strong

These are not "close enough" — several are exact.

| Paper | The app | Verdict |
|---|---|---|
| §3.2 Estate segmentation (6 segments, share bands, destinations) | `broadcom.SEGMENTS` | **Exact.** Same six, same bands, same natural destinations |
| §3.4 Five archetypes | `broadcom.ARCHETYPES` | **Exact.** Same five, same dependency verdict and ops-change |
| §4.16 Anti-patterns (10) | `broadcom.check_antipatterns` | **All ten**, and seven are tested mechanically against the live scenario rather than listed |
| §6.2 Phased roadmap (Phase 0–4) | `broadcom.PHASES` | **All five**, with durations |
| §7.1 Three scenarios A/B/C | `tco.three_scenarios` | **Aligned** as of commit `eec6fd9` |
| §7.2 Scenario C cost lines (11) | `broadcom.SCENARIO_C_LINES` (13) | **Superset**, and each is flagged modelled-or-add-by-hand |
| §7.3 Negotiation levers (7) | `broadcom.NEGOTIATION_LEVERS` (7) | **All seven** |
| §5.9 Azure Migrate limitations (14 + considerations) | `azure_migrate_sim.LIMITATIONS` | **Was wrong in the first pass of this audit — see the correction below** |
| §5.10 Where to supplement (7 gaps) | `tools_market` (17 tools, stack recommendation) | **Superset**, and the stack is derived from the live estate |
| §2.3 Hyperscaler licensing change | `broadcom.MILESTONES`, AVS = *relocated* not eliminated | **Aligned**, and counted against the real clock |
| §1.2 Timing pressure | `broadcom.milestone_status` | **Aligned** |
| §6.3 Wave design principles | `waves`, wave plan page | **Mostly** — dependency-boundary sequencing and disk-count sizing are modelled |

### Correction: the Azure Migrate limitations were not a superset

The first pass of this audit recorded §5.9 as covered, on the evidence that the
application carried twenty-one limitation entries against the paper's fourteen.
That was a count, not a check — the same mistake the fourteen-versus-fourteen
platform count invites. Read properly, the two sets overlap rather than nest.

The application was deeper than the paper on databases (five entries; the paper
does not enumerate database gaps at that level) and on unsupported source
configurations. It was **missing nine of the paper's items outright**:

| Paper §5.9 | Was it there? |
|---|---|
| 7. Agentless replication borrows production SAN IOPS | Missing |
| 8. CBT fragility, and pre-existing snapshots blocking it | Partial — VMware Tools and CBT health only |
| 10. vMotion / Storage vMotion during active replication | **Missing** |
| 11. No test migration for the Azure Local target | **Missing** |
| 12. Static IP preservation on Azure Local | **Missing** |
| 13. No live migration to Azure Local or Windows Server | **Missing** |
| 4. Dependency mapping false positives and negatives | **Missing** |
| 5. Richer dependency analysis is neither free nor agentless | Partial |
| 6. Undocumented application-layer dependencies | Partial — in phase prose, not the register |
| Preview feature churn | **Missing** |
| Project and region scoping, sovereign-cloud gaps | **Missing** |
| Appliance as a single point of failure | **Missing** |
| vCenter permission precision | Present, in phase prose |

The Azure Local trio (11, 12, 13) was the most consequential cluster, because the
application models Azure Local as a destination and now scores it as a
recommendable one — while saying nothing about the fact that migrating to it has
no rehearsal step. That is the same gap the newly added register records as R12.

**Closed in commit `316c3b9`:** twelve entries added, taking the register from 21
to 33, including a new `Target-specific` area for the Azure Local gaps. The
application is now a genuine superset of §5.9 rather than an assumed one.

---

## 3. Gaps that are not about alternatives

Six sections of the paper have **no representation anywhere in the application**.
None of them is analytical — all six are the governance apparatus that turns the
analysis into a programme.

| Paper | What it is | In the app |
|---|---|---|
| §8 | **Risk register, R01–R15** — fifteen risks with impact and mitigation | Nothing. "Risk" in the app means the Monte Carlo, which is a different sense of the word |
| §9.4 | **Decision checkpoints DC1–DC6** — the question each answers and the evidence required | Nothing |
| §9.1–9.3 | **30 / 60 / 90-day action plan** | Nothing |
| §5.11 | **Azure Migrate adoption checklist** — 15 items to complete before relying on it for a production wave | Nothing. The limitations are modelled; the pre-flight gate is not |
| Appendix A | **Discovery data checklist** — 15 items, 10 of them explicitly *programme-sourced* rather than tool-produced | Nothing |
| Appendix B | **Questions to table at renewal** — 13 questions written to be asked directly | Partly: §7.3's seven levers are present, the thirteen procurement questions are not |

The Appendix A gap is the one with a modelling consequence rather than a
presentational one. The paper's point is that ten of the fifteen discovery items
— RTO/RPO per application, change windows, third-party appliance support
statements, hardware-bound licensing, SRM runbook logic, backup immutability
evidence, NSX rule sets, hard-coded address inventory, entitlement position — are
**not produced by Azure Migrate** and require deliberate effort. The application
already argues that Azure Migrate covers only part of the estate; Appendix A is
the list that proves it, and it is missing.

---

## 4. Evaluation criteria: 11 modelled against 13 in the paper

`platforms.CRITERIA` scores each platform on eleven dimensions. The paper
specifies thirteen (§3.1) with recommended weights of Critical / High / Medium.

| # | Paper criterion | App dimension |
|---|---|---|
| 1 | Broadcom dependency removed | Handled separately as a verdict, not scored |
| 2 | Migration effort and risk | `migration_effort` |
| 3 | Operational model change | `ops_burden` — measures ongoing burden, not the size of the change |
| 4 | **Feature parity for the workload** | **absent** |
| 5 | Backup and DR ecosystem maturity | `resilience` — partial |
| 6 | Compliance and audit evidence | `compliance` |
| 7 | Commercial shape and predictability | `run_cost` — measures efficiency, not exposure to repricing |
| 8 | Skills availability in market | `skills_fit` — scoped to Microsoft-skill fit, not hire/retrain in geography |
| 9 | **Vendor and roadmap risk** | **absent** |
| 10 | Modernisation trajectory | `modernisation` |
| 11 | **Exit cost from the new platform** | **absent** |
| 12 | **Hardware implications** | **absent** |
| 13 | Time to first production wave | `exit_speed` — partial |

Four criteria absent, three partial. Two of the four absent ones are pointed:

* **#11, exit cost from the new platform.** The paper calls this "the question
  rarely asked at selection". An application built to answer *how do we leave the
  platform we are on* that does not score *how would we leave the next one* has a
  visible blind spot, and a client will find it.
* **#12, hardware implications.** Refresh triggered, HCL constraints, SAN reuse or
  stranding. This is the difference between Proxmox (runs on existing kit) and
  Azure Local (validated hardware list), and it is currently invisible.

The application also scores three dimensions the paper does not list —
`data_residency`, `latency_control`, `lock_in` — which is reasonable, but the
weights the paper recommends (Critical / High / Medium) are not represented, so
every criterion currently carries equal weight unless the user reweights by hand.

### §4.15 matrices

The paper splits the comparison into **three** matrices — strategic fit,
enterprise readiness, commercial and risk shape — and says explicitly that this is
deliberate, because "a single wide matrix compresses the nuance that matters".
The application presents one combined scorecard. Not a factual gap, but the paper
made a presentational decision the app reverses.

---

## 5. What to do, in priority order

Ranked by what a client would notice.

1. **Add the three missing options and the catch-all** (§4.10, 4.12, 4.13, 4.14).
   `core/platforms.py` is a data table — this is data entry plus scoring, not
   engineering. Mark 4.14's entries as evaluated-and-not-shortlisted so the
   comparison page can show them without implying they are candidates. Restores
   the "comprehensive evaluation" claim that Scenario B is priced on.
2. **Add the risk register (§8)** as `core/risks.py` with R01–R15, and check the
   testable ones against the live scenario the way the anti-patterns already are —
   R03 double-run, R06 Azure run cost, R12 Azure Local test gap and R15 bridge
   permanence are all observable from the model.
3. **Add the four missing evaluation criteria** (§3.1 #4, #9, #11, #12) and the
   paper's weights. Criterion #11 in particular.
4. **Add the discovery data checklist (Appendix A)** to Estate discovery, marking
   the ten programme-sourced items. It reinforces an argument the app already makes.
5. **Add decision checkpoints DC1–DC6 (§9.4) and the 30/60/90-day plan (§9.1–9.3)**
   to Exit readiness, which is where the programme-shape material already lives.
6. **Add the Azure Migrate adoption checklist (§5.11)** as a pre-flight tab on
   Azure Migrate & tooling.
7. **Add Appendix B's 13 renewal questions** beside the negotiation levers on
   Broadcom exposure.
8. **Consider splitting the platform scorecard into the paper's three matrices.**

Items 1–3 change what the application concludes. Items 4–8 change what it can
hand over. Nothing in this list requires touching the engines.

---

## 6. What this audit did not check

Stated so the coverage claim is honest.

* **Numeric fidelity.** Whether the app's rates, host counts and percentages match
  the paper's worked figures was not verified line by line — only whether the
  subject is modelled at all.
* **§4.1–4.9 verdict wording.** The per-option strengths, constraints and verdicts
  in the app were not compared sentence by sentence against the paper's; only
  presence was confirmed.
* **§10 references.** Not examined.
* **Appendix C glossary.** Not examined.

---

## What was executed

All eight items, in priority order, one commit each.

| Commit | Item | What changed |
|---|---|---|
| `d3b0400` | 1 + 3 | Three missing options added (SUSE Harvester, XCP-ng/Vates, OpenStack) plus a six-entry evaluated-and-not-shortlisted register. Five scoring dimensions added, including `broadcom_exit` — the paper's only Critical criterion, previously unscored — and `exit_cost`. The paper's Critical/High/Medium bands exposed as `CRITERION_WEIGHT` and as a selectable weighting. |
| `7f05754` | 2 | `core/risks.py`: R01–R15 with impact, mitigation and owner. Twelve scored against the live model, three advisory. Exit readiness moved to tabs to carry it. |
| `316c3b9` | — | **Correction.** Twelve Azure Migrate limitations added (21 → 33), including a new Target-specific area for the three Azure Local gaps. See the §5.9 correction above. |
| `bd05358` | 4 | Discovery data checklist, scored against the columns the loaded inventory actually carries. |
| `7ddb9c7` | 5 | Decision checkpoints DC1–DC6 and the 30/60/90-day plan, as a fourth Exit readiness tab. |
| `1b9d4ba` | 6 | Azure Migrate adoption checklist as a pre-flight gate; six of fifteen items checked against the live configuration. |
| `a4c9a90` | 7 + 8 | Appendix B's thirteen renewal questions, downloadable as CSV. Platform scorecard split into the paper's three matrices. |
| `b5468bb` | — | **Corrections.** §6.1 target state and §6.3 wave design principles (below), plus §7.2's missing egress line. |

### Three rows this audit got wrong on the first pass

Each was recorded as covered on the strength of a count or an engine behaviour,
rather than a reading. The pattern is worth naming: **a count is not a check**,
and "the engine does this" is not the same as "the application says this".

1. **§5.9, Azure Migrate limitations.** Recorded as a superset because 21 > 14.
   Nine of the paper's items were absent, including the entire Azure Local trio —
   no test migration, static IP preservation, no live migration path — while the
   application was simultaneously scoring Azure Local as a recommendable
   destination. Corrected in `316c3b9`.
2. **§6.1, target state.** Recorded as exact via §3.2's segmentation. It was not:
   the application sent the Relocate segment to "AVS or **Azure Local**" where the
   paper sends it to "AVS or **NC2 on Azure**", with the explicit rationale that
   NC2 carries no Broadcom requirement and AVS does. The application was
   contradicting its own central thesis. Corrected in `b5468bb`.
3. **§6.3, wave design principles.** Recorded as "mostly" because the wave engine
   already sequences by dependency cluster and sizes on disk count. True of the
   engine, false of the application: none of the seven rules that decide whether a
   wave may start appeared anywhere on screen — including that there is no
   automated rollback, only source VMs held powered off for a period somebody has
   to agree per wave. Corrected in `b5468bb`.

### Coverage now

| Paper section | Status |
|---|---|
| §3.1 Evaluation criteria (13) | All thirteen scored, with the paper's weight bands |
| §3.2 Segmentation (6) | Exact |
| §3.3 Underestimated costs (8) | Covered across the Scenario C lines and anti-patterns |
| §3.4 Archetypes (5) | Exact |
| §4.1–4.14 Alternatives (14) | All thirteen numbered options modelled; §4.14's six recorded |
| §4.15 Matrices (3) | Split into the paper's three views |
| §4.16 Anti-patterns (10) | All ten, seven mechanically tested |
| §5.9 Limitations | 33 entries, a genuine superset |
| §5.10 Supplementary tooling | Superset |
| §5.11 Adoption checklist (15) | All fifteen, six auto-checked |
| §6.1 Target state | Corrected to match, with rationale per segment |
| §6.2 Phased roadmap (5) | All five |
| §6.3 Wave principles (7) | All seven, four checked against the plan |
| §7.1 Scenarios A/B/C | Built on one shared model |
| §7.2 Scenario C cost lines (11) | Fourteen, including the egress line that was missing |
| §7.3 Negotiation levers (7) | All seven |
| §8 Risk register (15) | All fifteen, twelve scored live |
| §9.1–9.3 Next 30/60/90 days | All three horizons |
| §9.4 Decision checkpoints (6) | All six, with evidence and owner |
| Appendix A Discovery checklist (15) | All fifteen, scored against the inventory |
| Appendix B Renewal questions (13) | All thirteen, downloadable |

Page count is unchanged at 13. Every addition landed as a tab or section on the
page that already owned the subject.
