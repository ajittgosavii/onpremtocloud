"""Five-year cost of the Microsoft-only shortlist: Azure IaaS, AVS, Azure Local, Hyper-V.

``core.platforms`` ranks seventeen destinations on fit and ``core.tco`` prices
one of them -- Azure public cloud -- against staying put. Neither answers the
question a Microsoft-centric client actually asks, which is: *of the Microsoft
options alone, which is cheapest over five years, and by how much?*

Four destinations, because they are the four a Microsoft shop will genuinely
consider:

* **Azure native IaaS** -- the data centre closes.
* **Azure VMware Solution** -- the data centre closes, the Broadcom
  subscription does not (see ``core.broadcom``); since November 2025 the VCF
  subscription is bought from Broadcom directly and priced here as its own line.
* **Azure Local** -- Azure's stack on validated hardware in your building.
* **Hyper-V + System Center** -- the licence swap, no data centre exit.

Hyper-V is not Azure, and it is here on purpose: it is the floor. It is the
cheapest way to stop paying Broadcom, so every Azure option on this page has to
beat it on something other than price, and the page is more useful for saying so.

Why this is not just ``run rate x 60``
--------------------------------------
Three things make a five-year total differ from the monthly figure times sixty,
and all three favour a different destination:

1. **Migration takes time, and both platforms are paid during it.** A destination
   that lands workloads quickly pays the overlap for fewer months.
2. **What ramps and what does not.** Azure consumption starts near zero and grows
   with the workload landed. The hosts, power, floor space and staff behind a
   Hyper-V conversion are already there in year one and do not ramp at all --
   which is exactly the double-count that flatters an in-place option if you
   model it as a new stack running alongside the old one. So each destination
   declares which of its costs ramp and which are continuous, and the VMware
   stack it displaces declines against the ramp rather than against the clock.
3. **The renewal lands inside the horizon.** The residual VMware estate is priced
   at the *renewal* rate from year four, not today's rate, matching
   ``tco.build_tco``. Omitting that is the most common way an exit case flatters
   itself: it prices the thing being escaped at the old price.

Everything here is deterministic and Streamlit-free; the view does the presenting.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from core import platforms, tco

# Catalogue keys, so this module, core.platforms and core.broadcom cannot drift.
AZURE_IAAS = "Azure native IaaS (rehost)"
AVS = "Azure VMware Solution (AVS)"
AZURE_LOCAL = "Azure Local (formerly Azure Stack HCI)"
HYPERV = "Microsoft Hyper-V / Windows Server + SCVMM"

DESTINATIONS = [AZURE_IAAS, AVS, AZURE_LOCAL, HYPERV]

# Where each destination physically lands, which is the question behind the cost.
LOCATION = {
    AZURE_IAAS: "Azure region",
    AVS: "Azure region, dedicated hosts",
    AZURE_LOCAL: "Your data centre",
    HYPERV: "Your data centre",
}


# --------------------------------------------------------------------------
# Hyper-V: the licence swap
# --------------------------------------------------------------------------
# List price for System Center Datacenter is roughly USD 3,607 per 16-core pack,
# which is about USD 225 per core perpetual; carried under Software Assurance at
# the usual quarter of licence value that annualises to something near USD 55 per
# core per year. Windows Server Datacenter works out near USD 106 per core per
# year on the same basis, and is defaulted to zero because the platform record
# for Hyper-V says what most enterprises find: it is already owned under an EA.
# Both are list, both are adjustable on the page, and neither is a quotation.
SCVMM_PER_CORE_YEAR = 55.0
WINDOWS_DC_PER_CORE_YEAR = 106.0


@dataclass
class HyperVInputs:
    """What changes when ESXi becomes Hyper-V on the same hardware."""
    scvmm_per_core_year: float = SCVMM_PER_CORE_YEAR
    windows_dc_per_core_year: float = 0.0      # 0 = already covered by the EA
    # vCenter-adjacent tooling that has to be re-bought or replaced: backup
    # integration, monitoring packs, anything that spoke to the vSphere API.
    replacement_tooling_annual: float = 60000.0
    # Hyper-V and SCVMM are further from vCenter than the marketing suggests.
    ops_fte_delta: float = 0.5
    fte_fully_loaded_cost: float = 138000.0


# Lines in the current-state model that describe services, not hypervisors: they
# are still there the morning after any on-premises conversion, and they are the
# reason a destination that prices only its own nodes looks cheaper than it is.
PERSISTENT_ONPREM_SERVICES = (
    "Data centre space",
    "Network infrastructure",
    "Backup software & media",
    "DR site",
    "Monitoring & management tooling",
    "SQL Server licensing",
)

# Business impact rather than platform cost, and no Azure figure on this page
# carries an equivalent -- so it is excluded from all four rather than from some.
_EXCLUDED = ("Unplanned downtime",)


def _lines(p, names):
    """Named current-state lines at their modelled value, cost scaling included."""
    df = tco.onprem_annual_breakdown(p)
    return df[df["component"].isin(names)].copy()


def persistent_services_annual(p):
    """Annual cost of the services any on-premises destination still needs."""
    return float(_lines(p, PERSISTENT_ONPREM_SERVICES)["annual_cost"].sum())


def excluded_annual(p):
    """Current-state lines this page leaves out of every destination.

    Worth surfacing rather than burying: the same lines are still inside the
    stay-on-VMware reference, which comes from the Business case unchanged.
    """
    df = tco.onprem_annual_breakdown(p)
    return float(
        df.loc[df["component"].str.startswith(tuple(_EXCLUDED)), "annual_cost"].sum())


def hyperv_annual_breakdown(p, i):
    """Steady-state annual cost of the same estate on Hyper-V.

    Built as a delta from the current on-premises stack rather than as a fresh
    tower of costs: the hosts, array, floor space and people do not change when
    the hypervisor does, so they are carried across at their current modelled
    value and only the licensing and tooling lines move. The VMware subscription
    is the line that disappears, and it is the whole point of the option.
    """
    carried = hyperv_continuous_annual(p)

    physical_cores = p.hosts * p.sockets_per_host * p.cores_per_socket
    scvmm = physical_cores * i.scvmm_per_core_year
    windows = physical_cores * i.windows_dc_per_core_year
    people = i.ops_fte_delta * i.fte_fully_loaded_cost

    rows = [
        ("Existing on-premises platform (hardware, facilities, staff)", carried,
         "Every current-state line except the VMware subscription, carried across "
         "unchanged -- Hyper-V runs on the hosts you already own"),
        ("System Center (SCVMM) licensing", scvmm,
         f"{physical_cores:,} physical cores x {i.scvmm_per_core_year:,.0f}/core/yr"),
        ("Windows Server Datacenter", windows,
         f"{physical_cores:,} physical cores x {i.windows_dc_per_core_year:,.0f}/core/yr"
         if windows else "Assumed already owned under the enterprise agreement"),
        ("Replacement management & backup tooling", i.replacement_tooling_annual,
         "vSphere-integrated tooling that does not follow you to Hyper-V"),
        ("Additional operations effort", people,
         f"{i.ops_fte_delta} FTE -- SCVMM is materially behind vCenter"),
    ]
    df = pd.DataFrame(rows, columns=["component", "annual_cost", "basis"])
    df = df[df["annual_cost"] > 0].copy()
    df["share_pct"] = df["annual_cost"] / df["annual_cost"].sum() * 100
    return df.sort_values("annual_cost", ascending=False)


def hyperv_continuous_annual(p):
    """The part of the Hyper-V bill that exists in year one whatever has migrated.

    The building, the racks in it and the people who run them are already being
    paid for. Ramping them with migration progress would show a Hyper-V
    conversion getting cheaper the slower it goes, which is the wrong answer.
    """
    onprem = tco.onprem_annual_breakdown(p)
    drop = (onprem["component"].str.startswith("VMware licensing")
            | onprem["component"].str.startswith(tuple(_EXCLUDED)))
    return float(onprem.loc[~drop, "annual_cost"].sum())


# --------------------------------------------------------------------------
# AVS
# --------------------------------------------------------------------------
def avs_annual_breakdown(avs, az, vcf_per_core_year=135.0):
    """Steady-state annual cost of running the estate on AVS.

    ``avs`` is a :func:`core.platforms.size_avs` result, so the host count is the
    one this estate needs rather than the three-host minimum. The VCF line is
    separate and deliberately conspicuous: Microsoft stopped bundling it, so it
    is a Broadcom invoice that survives the move to Azure.
    """
    spec = avs["spec"]
    nodes = avs["hosts"] * spec["hourly"] * 8760
    vcf = avs["hosts"] * spec["cores"] * vcf_per_core_year
    rows = [
        ("AVS dedicated nodes", nodes,
         f"{avs['hosts']} x {avs['node']} at {spec['hourly']:.2f}/hr, sized by "
         f"{avs['binding_constraint'].lower()}"),
        ("VCF subscription (bought from Broadcom)", vcf,
         f"{avs['hosts'] * spec['cores']:,} cores x {vcf_per_core_year:,.0f}/core/yr -- "
         "no longer bundled with the node price"),
        ("ExpressRoute / connectivity", az.expressroute_monthly * 12, ""),
        ("Cloud operations staff", az.cloud_ops_fte * az.fte_fully_loaded_cost,
         f"{az.cloud_ops_fte} FTE"),
        ("Governance, FinOps & security tooling", az.governance_tooling_annual, ""),
    ]
    df = pd.DataFrame(rows, columns=["component", "annual_cost", "basis"])
    df = df[df["annual_cost"] > 0].copy()
    df["share_pct"] = df["annual_cost"] / df["annual_cost"].sum() * 100
    return df.sort_values("annual_cost", ascending=False)


# --------------------------------------------------------------------------
# Programme shape per destination
# --------------------------------------------------------------------------
@dataclass
class Shape:
    """How a destination behaves as a programme, not as a price list.

    ``effort_mult`` scales the estate-wide migration cost the effort model
    produced for a rehost. ``residual_pct`` is what is still running on-premises
    once the programme finishes -- zero for the two destinations that never left
    the building, because their own steady-state cost already includes it.
    """
    effort_mult: float
    landing_zone_mult: float
    training_mult: float
    residual_pct: float          # of the old stack, after cutover
    shed_rate: float             # how fast the old stack sheds against the ramp
    resale: bool                 # is the displaced hardware sold
    # What of the current estate winds down. "full" for a destination that
    # displaces the whole stack; "licence" where the hardware is converted in
    # place and only the Broadcom subscription goes -- the rest of that stack is
    # carried as a continuous cost of the destination itself, and counting it in
    # both places is exactly the double-count this field exists to prevent.
    legacy_scope: str = "full"


SHAPES = {
    # A rehost is what the effort model priced, so the multiplier is 1.0 and the
    # rest of the page is calibrated against it.
    AZURE_IAAS: Shape(1.00, 1.00, 1.00, residual_pct=6.0, shed_rate=0.5, resale=True),
    # Relocation rather than rebuild: HCX moves VMs with no guest change, which is
    # why AVS is the fastest exit on the ranking and the cheapest to execute.
    AVS: Shape(0.35, 0.85, 0.70, residual_pct=6.0, shed_rate=0.5, resale=True),
    # Azure Local is a real conversion to Hyper-V, so per-VM effort matches a
    # rehost, and it needs validated hardware -- the old estate still goes.
    AZURE_LOCAL: Shape(1.00, 0.40, 0.85, residual_pct=0.0, shed_rate=0.6, resale=True),
    # Same conversion effort, no Azure landing zone worth the name, and the hosts
    # are reused in place, so there is nothing to sell and nothing to shed but
    # the subscription.
    HYPERV: Shape(0.95, 0.10, 0.55, residual_pct=0.0, shed_rate=0.9, resale=False,
                  legacy_scope="licence"),
}


def _steady_and_continuous(dest, res, sc, avs_sizing, local, hv_inputs, vcf_rate):
    """Annual steady-state cost for one destination, split into ramped and continuous.

    Returns ``(breakdown, ramped_annual, continuous_annual)``. Continuous costs are
    charged in full from year one; ramped costs follow the workload landed.
    """
    az = sc.azure_profile
    if dest == AZURE_IAAS:
        bd = tco.azure_annual_breakdown(
            _with_run(az, res.cost_summary["monthly_total"]))
        # Connectivity and governance are stood up before the first VM lands.
        cont = az.expressroute_monthly * 12 + az.governance_tooling_annual
        return bd, float(bd["annual_cost"].sum()) - cont, cont
    if dest == AVS:
        bd = avs_annual_breakdown(avs_sizing, az, vcf_rate)
        cont = az.expressroute_monthly * 12 + az.governance_tooling_annual
        return bd, float(bd["annual_cost"].sum()) - cont, cont
    if dest == AZURE_LOCAL:
        # platforms.azure_local_cost prices the cluster: service fee, nodes,
        # power and the staff who run it. It does not price the network the
        # cluster plugs into, the backup product, the DR site, the monitoring
        # estate or the SQL licences -- all of which survive the conversion and
        # all of which the Hyper-V figure carries. Adding them back is what puts
        # the two on-premises destinations on one basis; without it Azure Local
        # wins this page on an accounting artefact.
        extra = _lines(res.onprem, PERSISTENT_ONPREM_SERVICES)
        extra = extra.rename(columns={"basis": "_b"})
        extra["basis"] = "Unchanged by the conversion -- still required on-premises"
        bd = pd.concat([local["breakdown"],
                        extra[["component", "annual_cost", "basis"]]],
                       ignore_index=True)
        bd["share_pct"] = bd["annual_cost"] / bd["annual_cost"].sum() * 100
        bd = bd.sort_values("annual_cost", ascending=False)
        services = persistent_services_annual(res.onprem)
        # The cluster is bought in tranches as workload lands; the services it
        # plugs into are already there.
        return bd, float(local["annual_total"]), services
    bd = hyperv_annual_breakdown(res.onprem, hv_inputs)
    cont = hyperv_continuous_annual(res.onprem)
    return bd, float(bd["annual_cost"].sum()) - cont, cont


def _with_run(az, monthly):
    from dataclasses import replace
    return replace(az, azure_monthly_run=monthly)


def destination_cashflow(dest, ramped, continuous, onprem, inp, one_offs, shape,
                         escalation_pct=2.0):
    """Year-by-year cash flow for one destination over the TCO horizon.

    The legacy VMware stack and the destination are modelled together, because
    during a migration you are paying for both and that overlap is most of what
    separates these four options.
    """
    op_lines = tco.onprem_annual_breakdown(onprem)
    # Business-impact downtime comes out here too, not just out of the Hyper-V
    # figure. Leaving it in the declining stack but out of the destination that
    # replaces it would hand the in-place option a saving the other three pay
    # for, which is a bias in the model rather than a fact about the platforms.
    op_base = float(
        op_lines.loc[~op_lines["component"].str.startswith(tuple(_EXCLUDED)),
                     "annual_cost"].sum())
    vmware_line = (onprem.hosts * onprem.sockets_per_host
                   * max(onprem.cores_per_socket, onprem.vmware_min_cores_per_socket)
                   * onprem.vmware_cost_per_core_year)
    # For an in-place conversion the only legacy cost that winds down is the
    # subscription itself; the rest of the stack is carried in `continuous`.
    legacy_base = vmware_line if shape.legacy_scope == "licence" else op_base

    migration_years = max(inp.migration_months / 12.0, 0.01)
    residual = shape.residual_pct / 100.0
    rows = []
    for year in range(1, inp.horizon_years + 1):
        esc_op = (1 + onprem.onprem_cost_escalation_pct / 100.0) ** (year - 1)
        esc_new = (1 + escalation_pct / 100.0) ** (year - 1)

        ramp = float(np.clip(year / migration_years, 0.0, 1.0))
        if shape.legacy_scope == "licence":
            # A subscription is not refunded VM by VM. You pay it in full until
            # the estate is off it, and then you stop -- so it steps rather than
            # slopes, and the step is what an in-place conversion is racing.
            remaining = residual if ramp >= 1.0 else 1.0
        else:
            # A whole stack does wind down gradually: racks empty, arrays are
            # retired, people move on. Same shape as tco.build_tco, so the two
            # models cannot disagree about the option they share.
            remaining = float(np.clip(1.0 - shape.shed_rate * ramp, residual, 1.0))
            if ramp >= 1.0:
                remaining = residual

        legacy = legacy_base * esc_op * remaining
        # The residual estate renews at the post-acquisition rate, not today's.
        if year >= 4 and shape.legacy_scope == "full":
            legacy += (vmware_line * onprem.vmware_renewal_uplift_pct / 100.0
                       * esc_op * remaining)

        run = (continuous * esc_new) + (ramped * ramp * esc_new)

        one_off = 0.0
        if year == 1:
            one_off += one_offs["landing_zone"] + one_offs["training"]
        if year <= np.ceil(migration_years):
            one_off += one_offs["migration"] / max(np.ceil(migration_years), 1)
        if year == np.ceil(migration_years) and shape.resale:
            one_off -= (onprem.hosts * onprem.host_capex
                        * inp.hardware_resale_recovery_pct / 100.0)

        rows.append({
            "destination": dest, "year": year,
            "legacy_vmware": legacy, "destination_run": run,
            "one_off": one_off, "total": legacy + run + one_off,
        })

    df = pd.DataFrame(rows)
    r = inp.discount_rate_pct / 100.0
    df["discount_factor"] = 1 / (1 + r) ** (df["year"] - 0.5)
    df["pv"] = df["total"] * df["discount_factor"]
    df["cumulative"] = df["total"].cumsum()
    return df


def compare(res, sc, hv_inputs=None, vcf_rate=135.0, avs_node="AV36",
            local_inputs=None):
    """Five-year cost of all four Microsoft destinations, on one basis.

    Returns a dict with the per-year cash flows, a one-row-per-destination
    summary, and the steady-state breakdown behind each, so the page can show
    both the answer and its working.
    """
    hv_inputs = hv_inputs or HyperVInputs()
    inp = sc.tco_inputs
    s = res.estate_summary

    avs_sizing = platforms.size_avs(
        s["total_vcpu"], s["total_ram_tib"] * 1024, s["provisioned_tib"], node=avs_node)
    local = platforms.azure_local_cost(local_inputs or platforms.AzureLocalInputs(
        total_vcpu=s["total_vcpu"], total_ram_gib=s["total_ram_tib"] * 1024,
        provisioned_tib=s["provisioned_tib"]))

    base_effort = res.effort_summary["migration_cost"]
    az = sc.azure_profile

    flows, summary, breakdowns = [], [], {}
    for dest in DESTINATIONS:
        shape = SHAPES[dest]
        bd, ramped, cont = _steady_and_continuous(
            dest, res, sc, avs_sizing, local, hv_inputs, vcf_rate)
        breakdowns[dest] = bd
        one_offs = {
            "migration": base_effort * shape.effort_mult,
            "landing_zone": az.landing_zone_one_off * shape.landing_zone_mult,
            "training": az.training_one_off * shape.training_mult,
        }
        # Azure-metered destinations escalate at the Azure assumption; a stack in
        # your own building escalates at your own cost inflation.
        esc = (res.onprem.onprem_cost_escalation_pct if dest == HYPERV
               else az.azure_price_escalation_pct)
        df = destination_cashflow(dest, ramped, cont, res.onprem, inp, one_offs, shape,
                                  escalation_pct=esc)
        flows.append(df)
        summary.append({
            "destination": dest,
            "location": LOCATION[dest],
            "steady_annual": ramped + cont,
            "five_year_total": float(df["total"].sum()),
            "npv": float(df["pv"].sum()),
            "one_off_total": sum(one_offs.values()),
            "year1": float(df.iloc[0]["total"]),
            "steady_year": float(df.iloc[-1]["total"]),
        })

    flow = pd.concat(flows, ignore_index=True)
    sm = pd.DataFrame(summary).sort_values("npv").reset_index(drop=True)
    cheapest = sm.iloc[0]
    sm["vs_cheapest"] = sm["npv"] - cheapest["npv"]
    sm["vs_cheapest_pct"] = sm["vs_cheapest"] / cheapest["npv"] * 100

    # The control case: staying on VMware over the same horizon, on the same
    # basis, so "cheapest Microsoft option" is not mistaken for "worth doing".
    stay_npv = float(res.tco_summary["npv_stay"])
    sm["vs_stay"] = sm["npv"] - stay_npv
    sm["vs_stay_pct"] = sm["vs_stay"] / stay_npv * 100 if stay_npv else 0.0

    return {
        "flows": flow, "summary": sm, "breakdowns": breakdowns,
        "avs_sizing": avs_sizing, "azure_local": local,
        "stay_npv": stay_npv, "horizon_years": inp.horizon_years,
    }
