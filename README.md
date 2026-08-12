# VMware to Azure Migration Decision Simulator

A Streamlit decision-support simulator for moving an on-premises VMware vSphere estate to
Microsoft Azure. Built around a 547-VM reference estate (60% Windows, 40% Linux), but the
estate is a parameter -- point it at any inventory.

Every Azure figure is priced against **live Microsoft retail rates** pulled from the public
Azure Retail Prices API. Every product limit modelled for Azure Migrate comes from Microsoft's
published documentation. Everything else -- the estate, effort, risk, on-premises cost base --
is an explicit, adjustable assumption shown on the page that uses it.

---

## What it answers

1. **What will it cost to run in Azure?** Right-sized per VM, priced from live meters,
   with Azure Hybrid Benefit, reservations, savings plans, non-production scheduling,
   storage tiering, backup, DR and landing-zone overhead all as levers.
2. **How long will it take, and what actually constrains it?** Wave planning that computes
   replication time and engineering capacity independently and names which one binds.
3. **How confident should we be?** Monte Carlo over eleven uncertain drivers, with a
   tornado chart showing which uncertainty is worth attacking.
4. **How does Azure Migrate actually behave here?** The full lifecycle simulated with real
   product limits -- and an explicit register of what the tool will not do.
5. **Is Azure even the right destination?** Fifteen target platforms scored and priced,
   including the on-premises Azure options.
6. **What should we buy?** The migration tooling market ranked against this client's
   requirement, with licence cost at this estate's scale.

---

## Built to be presented

The application is organised as a **seven-act client narrative**, not a menu of features.
Navigation is grouped into those acts, and every page opens with its position in the story
("Step 4 of 12 / Decide") plus a stepper showing where the conversation has reached.

| Act | Pages | The question being answered |
|---|---|---|
| **1 · Situation** | Executive briefing · Model & assumptions | What is the answer, and what are we assuming? |
| **2 · Discover** | Estate discovery | What do you actually have? |
| **3 · Assess** | Readiness & 7R · Complexity & effort | What should happen to it, and how hard is it? |
| **4 · Decide** | Cloud provider · Target platforms · Azure cost simulator · Business case | Which provider, where should it land, what does it cost, is it worth doing? |
| **5 · Plan** | Wave plan & timeline · Risk simulation | How long, and how confident are we? |
| **6 · Execute** | Azure Migrate simulator · Migration tooling | How would we actually do it? |
| **7 · Communicate** | AI advisor | Turn it into deliverables |

Two features exist purely for running a client session:

- **Presentation mode** (sidebar toggle) hides every configuration panel and enlarges type, so
  the screen is clean when projected.
- **"The point to make"** callouts on every page give the line to say out loud -- the insight
  the screen is there to deliver, not a description of the chart.

The sidebar also carries a live scenario readout (VMs, run rate, on-premises cost, programme
cost, duration, payback) that updates as any parameter changes, so the headline numbers are
always on screen.

### What each page does

| Page | What it does |
|---|---|
| **Executive briefing** | The whole decision on one screen: run rate, programme cost, duration, NPV, payback, top risks |
| **Model & assumptions** | Every input in the model, classified as vendor fact / estate observation / assumption, each linking to the page that controls it |
| **Estate discovery** | Synthetic estate generator, or import a real RVTools `vInfo` export. Portfolio profile, size distribution, data-quality and migration-friction analysis |
| **Readiness & 7R** | Right-sizing (performance-based or as-provisioned), Azure readiness (Ready / Ready with conditions / Not ready), and 7R disposition -- each explainable to the individual VM |
| **Complexity & effort** | Thirteen weighted complexity factors driving effort, cost and cutover risk. Weights are user-adjustable |
| **Cloud provider** | Azure vs AWS vs Google Cloud vs OCI, scored against *this* estate and decided on live licensing arithmetic rather than preference |
| **Target platforms** | Azure IaaS, Azure PaaS, AVS, **Azure Local**, Azure Stack Hub, Azure Arc, Nutanix, Hyper-V, OpenShift Virtualization, Proxmox, GCVE, OCI, and staying on VMware |
| **Azure cost simulator** | Live Azure retail pricing, commercial levers, lever sensitivity, cost concentration, and the raw vendor price feed |
| **Business case** | Post-Broadcom VMware cost base versus Azure, five-year cash flow, NPV, payback, and single-assumption sensitivity |
| **Wave plan & timeline** | Application-first waves sequenced up a risk ladder, with a Gantt, the binding constraint per wave, and a bandwidth sensitivity curve |
| **Risk simulation** | PERT Monte Carlo over eleven drivers: confidence curves, tornado analysis, funding recommendation |
| **Azure Migrate simulator** | Ten-phase lifecycle, appliance sizing, replication feasibility -- plus the **limitations register**, **heterogeneous workload matrix** and **database migration gap** |
| **Migration tooling** | Seventeen tools scored across eleven dimensions, a recommended stack, and licence cost at scale |
| **AI advisor** | OpenAI turns the computed model into an executive summary, risk register, board paper or runbook -- grounded strictly in the numbers |

---

## The Azure Migrate limitations section

This is the part most plans omit. Azure Migrate is free, well-supported and the right backbone
for a rehost -- but it is narrower than assessments imply. The simulator computes, for your
estate, how far the tool actually takes each VM:

- Fully covered end to end
- Covered but needs VMware Tools remediation first
- Rehosts, but the guest OS is still end-of-life on arrival
- Rehosts, but the database is not migrated
- Special hardware or licence binding
- Blocked from agentless replication entirely

On the reference estate, **only ~46% of VMs are taken end to end by Azure Migrate alone.**

It also carries a full limitations register (20 entries across Databases, Replication, Source
configuration, Assessment, Dependency analysis, Modernisation and Programme operations), each
with what it means, the impact on the programme, and the compensating control.

### Heterogeneous workloads

Azure Migrate rehosts a guest OS and its disks. Any migration that changes the *kind* of thing
being run is out of scope. The simulator ships a matrix of 23 such paths across 19 categories:

Operating system upgrades · CPU architecture (SPARC/POWER/Itanium) · Middleware (WebLogic,
WebSphere, IIS, Tomcat) · Messaging (IBM MQ, TIBCO EMS) · Integration and ETL (Informatica,
DataStage) · Batch scheduling (Control-M, AutoSys) · File services (NetApp, Isilon) · Block
storage · Load balancing (F5, NetScaler) · Identity (Active Directory) · PKI and MAC-bound
licences · DNS/DHCP/IPAM · Backup · Monitoring · Reporting and BI · Container platforms
(OpenShift, Cloud Foundry) · Mainframe (z/OS COBOL, CICS, IMS) · IBM i (AS/400) · Licensed
virtual appliances

Each gives the tooling, what must be converted, the automatable percentage, effort per unit
and the risks.

### Database migration

A dedicated tab with twelve source/target paths covering homogeneous and heterogeneous moves
(SQL Server, Oracle, SAP ASE, Db2, MySQL, PostgreSQL, MongoDB). Pick a target per engine and it
computes the database workstream effort and cost that the Azure Migrate plan does not include.
On the reference estate, 19 Oracle databases moving to PostgreSQL consume more effort than the
entire SQL Server workstream several times over.

---

## Cloud provider selection

Provider choice is usually argued on brand preference. For a Windows-heavy VMware estate it is
mostly arithmetic, and the simulator does that arithmetic from two live vendor APIs.

The finding on the reference estate (60% Windows, 328 Windows VMs, 2,024 Windows vCPU):

| | Azure | AWS | Google Cloud | OCI |
|---|---|---|---|---|
| Windows licence, licence-included | **$0.0460/vCPU/hr** *(live)* | **$0.0460/vCPU/hr** *(live)* | $0.040 *(list)* | $0.092/OCPU *(list)* |
| BYOL on ordinary shared tenancy | **Yes** (Azure Hybrid Benefit) | No -- Dedicated Hosts | No -- sole-tenant nodes | Yes |
| Free ESU for end-of-life Windows | **Yes** | No | No | No |
| **Annual licensing cost, with SA** | **$0** | $340,515 | $297,963 | $85,200 |

Azure and AWS charge **exactly the same** licence-included rate -- two figures derived
independently from two different public APIs. So the recommendation is not "Azure is cheaper".
It is that Azure is the only provider that lets the client *stop paying that charge* by using
licences they already own, and the only one granting free Extended Security Updates for the
71 out-of-support Windows servers in this estate.

Flip the "holds Software Assurance" toggle off and the advantage largely disappears -- which
is the honest counter-case the page states rather than hides.

Live rate sources: **Azure Retail Prices API** and the **public AWS pricing feed behind
calculator.aws** (median Windows-minus-Linux delta across ~905 instance types). Google Cloud's
Billing Catalog API requires a key and Oracle publishes no equivalent feed, so those two are
published list prices and are labelled as such in the UI.

---

## Target platform alternatives, including on-premises Azure

Explicitly covers the AWS Outposts equivalents and the non-AWS options:

- **Azure Local** (formerly Azure Stack HCI) -- Azure's stack on validated hardware in your own
  data centre, Arc-managed, at $10.00 per physical core per month ($20.10 with external SAN),
  plus Windows Server guest rights at $23.30 per core per month unless waived by Azure Hybrid
  Benefit. Removes the Broadcom licence entirely without the workload leaving the site.
  Includes a full node-sizing and cost model.
- **Azure Stack Hub** -- a self-contained Azure region you operate, including air-gapped.
- **Azure Arc only** -- leave the estate where it is and manage it as Azure resources.
- **Azure VMware Solution** -- sized properly from the estate (memory is almost always the
  binding constraint), including the portable VCF subscription that must now be bought
  separately from Broadcom.
- Nutanix (on-premises and NC2 on Azure), Hyper-V, Red Hat OpenShift Virtualization, Proxmox VE
- Google Cloud VMware Engine, Oracle Cloud VMware Solution
- Staying on VMware with a renegotiated VCF subscription -- the honest baseline

---

## Live pricing

Source: `https://prices.azure.com/api/retail/prices` (api-version `2023-01-01-preview`).
Unauthenticated. Microsoft's own published retail rates.

Meters consumed:

| Meter | Used for |
|---|---|
| Virtual Machines, Consumption | Per-hour Linux and Windows rates; the delta is the AHB-eligible licence component |
| Virtual Machines, Reservation | 1-year and 3-year RI, normalised to an effective hourly rate |
| `savingsPlan` block | 1-year and 3-year Azure savings plan for compute |
| Storage, Managed Disks | Premium SSD, Standard SSD and Standard HDD capacity and transaction rates |
| Bandwidth | Internet egress above the free 100 GB |
| Backup | Protected-instance fee and vault storage (LRS/GRS/Archive) |
| Azure Site Recovery | Per-protected-instance monthly fee |

Responses are cached to `.cache/` for 24 hours, so the app keeps working offline. The **Cost
simulator → Live price feed** tab shows every raw rate in use, and the sidebar has a
connectivity probe.

Validated against Azure's published prices for East US: `Standard_D4s_v5` Linux $0.1920/hr,
Windows $0.3760/hr; P30 $135.17/mo; E30 $76.80/mo; S30 $40.96/mo; 3-year RI $0.0758/hr.

---

## Install and run

```bash
git clone https://github.com/ajittgosavii/onpremtocloud.git
cd onpremtocloud
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

Opens on `http://localhost:8501`.

### Deploying to Streamlit Community Cloud

Point it at `app.py`. No secrets are required -- the pricing APIs are unauthenticated and the
OpenAI key is optional and entered at runtime. Python 3.12 or later; set the version under
**Advanced settings**.

**`.streamlit/config.toml` is load-bearing, not decoration.** It sets
`fileWatcherType = "none"`, and without it the app crashes on every deploy.

Streamlit's `LocalSourcesWatcher` reacts to a changed source file by deleting *every* watched
module from `sys.modules`, from a background thread. Its own source comments call this a
workaround: "determining all import paths for a given loaded module is non-trivial, and so as a
workaround we simply unload all watched modules." On Community Cloud a `git pull` rewrites every
file at once, so that mass deletion races the script thread's imports. All of these are the same
bug wearing different hats:

```
KeyError: 'core.pricing'      importlib's _load_unlocked did sys.modules.pop(spec.name)
KeyError: 'core'              ...and the parent package had been removed too
AttributeError: 'NoneType'    dataclasses' _is_type() did
  object has no attribute       sys.modules.get(cls.__module__).__dict__
  '__dict__'                    on a module that had just been unloaded
```

A server never needs hot reload -- a redeploy restarts the process. For local development with
auto-reload, override it: `streamlit run app.py --server.fileWatcherType auto`.

Three further hardenings, all guarded by `tools_deploycheck.py`:

- **No `from __future__ import annotations` anywhere.** With it every annotation is a string, so
  `dataclasses` calls `_is_type()` on each one -- the second failure mode above. Removing it means
  annotations are real objects and that branch is never reached. Not version-specific: it
  reproduces on 3.12 as readily as on 3.14.
- **No SciPy.** `pandas.corr(method="spearman")` requires it. The tornado chart computes the same
  rank correlation as Pearson-on-ranks instead, keeping SciPy out of `requirements.txt`.
- **A read-only application directory degrades, not crashes.** The price cache probes for a
  writable location, falls back to the system temp directory, then to no caching at all.

Run the guard before every deploy:

```bash
python tools_deploycheck.py     # exit 1 on any problem
```

### OpenAI (optional)

The advisor is the only feature that needs a key. Every calculation works without it.

```bash
cp .env.example .env      # then add OPENAI_API_KEY
```

Or paste the key into the sidebar at runtime.

**What reaches OpenAI:** only the aggregate scenario snapshot -- estate summary, cost and
effort totals, readiness counts, top findings. No VM names, no application names, no
hostnames, no uploaded file. The **AI advisor → What the model can see** tab shows the exact
JSON payload, which is the page to show a client's security team.

---

## Using a real inventory

**Discovery & inventory → Estate source → Upload RVTools / CSV.**

Accepts an RVTools `.xlsx` (the `vInfo` sheet is found automatically) or a generic CSV.
Minimum columns: VM name, CPU count, memory, guest OS. RVTools column names are recognised.

Optional but high-value: performance counters (`cpu_avg_pct`, `cpu_p95_pct`, `mem_avg_pct`,
`mem_p95_pct`), `environment`, `criticality`, `app_name`, `db_engine`, and the friction flags
(`has_rdm`, `has_shared_disk`, `vm_encrypted`, ...). Without performance data, right-sizing
falls back to as-provisioned sizing -- the equivalent of a 1-star Azure Migrate assessment, and
the app says so.

---

## Layout

```
app.py                      Entry point: sidebar controls and navigation
core/
  azure_catalog.py          VM SKUs, managed disk tiers, regions, platform ceilings
  pricing.py                Azure Retail Prices API client with disk cache
  inventory.py              Synthetic estate generator + RVTools import
  rightsizing.py            Performance-based and as-provisioned sizing
  assessment.py             Azure readiness rules and 7R disposition
  costing.py                Run-cost engine and commercial levers
  complexity.py             Thirteen-factor complexity, effort and risk model
  waves.py                  Wave planning and schedule simulation
  montecarlo.py             PERT Monte Carlo and tornado analysis
  tco.py                    On-premises VMware vs Azure TCO and NPV
  azure_migrate_sim.py      Lifecycle, limits, limitations, heterogeneous matrix
  tools_market.py           Migration tooling market
  platforms.py              Target platforms incl. Azure Local cost model
  llm.py                    OpenAI advisor and context builder
  scenario.py               Scenario state and the pipeline
  ui.py                     Theme, chart defaults, formatting
views/                      One module per page
tools_selftest.py           Headless engine test (pricing + full chain)
tools_smoketest.py          Renders every page headlessly via streamlit.testing
```

### Tests

```bash
python tools_selftest.py pricing     # live Azure API + meter validation
python tools_selftest.py engines     # full deterministic chain
python tools_provider_test.py        # live AWS + Azure licensing comparison
python tools_smoketest.py            # renders all 14 pages, non-zero exit on failure
python tools_deploycheck.py          # the failures that only appear when hosted
```

---

## What is real and what is modelled

Every number in the application is one of four kinds, and the **Model & assumptions** page
lists all of them with the page that controls each:

| Kind | What it means | Adjustable |
|---|---|---|
| **Vendor fact** | Fetched live from the Azure Retail Prices API or the AWS pricing feed, or taken from published product documentation -- Azure Migrate's replication limits, VM SKU specs, managed disk tiers | No |
| **Estate observation** | Read from the inventory. Upload a real RVTools export and these become evidence | Via the inventory |
| **Calibrate with client** | A defensible default standing in for a figure only the client has -- their rate card, renewal quote, circuit capacity, hurdle rate | Yes |
| **Modelling judgement** | A deliberate choice with no single right answer, such as effort per VM or WAN efficiency -- exposed as a control specifically so it can be argued with | Yes |

Roughly 50 inputs are catalogued, of which about 15 are flagged **calibrate first** because the
conclusion genuinely depends on them. The register exports to CSV, which makes it a better
leave-behind than a number the client cannot question.

The distinction is deliberate and stated on the Executive briefing. This is a decision aid for
structuring an argument and testing its sensitivity -- not a quotation.

---

## Licence

MIT.
