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
| **1 · Situation** | Executive briefing | What is the answer? |
| **2 · Discover** | Estate discovery | What do you actually have? |
| **3 · Assess** | Readiness & 7R · Complexity & effort | What should happen to it, and how hard is it? |
| **4 · Decide** | Target platforms · Azure cost simulator · Business case | Where should it land, what does it cost, is it worth doing? |
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
| **Estate discovery** | Synthetic estate generator, or import a real RVTools `vInfo` export. Portfolio profile, size distribution, data-quality and migration-friction analysis |
| **Readiness & 7R** | Right-sizing (performance-based or as-provisioned), Azure readiness (Ready / Ready with conditions / Not ready), and 7R disposition -- each explainable to the individual VM |
| **Complexity & effort** | Thirteen weighted complexity factors driving effort, cost and cutover risk. Weights are user-adjustable |
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
python tools_selftest.py pricing    # live API + meter validation
python tools_selftest.py engines    # full deterministic chain
python tools_smoketest.py           # renders all 12 pages, non-zero exit on failure
```

---

## What is real and what is modelled

**Real** -- Azure prices, VM SKU specifications, managed disk tiers and IOPS, reserved instance
and savings plan rates, Azure Migrate product limits (300/500 concurrent replications, 56 disks
in flight, 10,000 servers per appliance, 1,000-server agentless dependency cap, confidence
rating thresholds), Azure Local and AVS pricing models, VMware per-core licensing structure.

**Modelled** -- the estate and its utilisation, data churn, effort per VM, cutover failure
probability, and the on-premises cost base. All are parameters. None should be shown to a
client without being calibrated against their data.

The distinction is deliberate and stated on every page. This is a decision aid for structuring
an argument and testing its sensitivity -- not a quotation.

---

## Licence

MIT.
