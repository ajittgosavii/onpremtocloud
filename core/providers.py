"""Cloud provider selection: which hyperscaler suits *this* estate.

Provider choice is usually argued on brand preference. For a Windows-heavy
VMware estate it is mostly arithmetic, because the licensing rules differ
sharply between providers and they dominate the run rate:

* **Azure Hybrid Benefit** lets you apply existing Windows Server and SQL Server
  licences with Software Assurance to Azure VMs on ordinary shared tenancy, and
  removes the licence component of the rate entirely.
* **AWS** withdrew general BYOL for Windows on shared tenancy for licences
  acquired after 1 October 2019. BYOL now requires Dedicated Hosts or dedicated
  instances -- you buy a whole physical host, losing elasticity and paying a
  capacity premium. Otherwise you take License Included pricing.
* **Google Cloud** is the same shape: BYOL for Windows requires sole-tenant
  nodes, which carry a sole-tenancy premium; otherwise you pay the per-vCPU
  licence charge.
* **Oracle Cloud** is decisive only where Oracle Database licensing dominates.

On top of that, **free Extended Security Updates for end-of-life Windows Server
and SQL Server are available only when the workload runs on Azure** (including
Azure Local and Azure VMware Solution). Everywhere else they are bought.

Live AWS rates come from the public pricing feed that backs the AWS Pricing
Calculator. Azure rates come from the Azure Retail Prices API (core.pricing).
Google and Oracle publish no equivalent unauthenticated feed, so their licence
rates are taken from published list pricing and are labelled as such.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import requests

from core import pricing

# --------------------------------------------------------------------------
# AWS public pricing feed (the one behind calculator.aws)
# --------------------------------------------------------------------------
AWS_FEED = ("https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/ec2/USD/current/"
            "ec2-ondemand-without-sec-sel/{region}/{os}/index.json")

AWS_REGIONS = {
    "eastus": "US East (N. Virginia)",
    "eastus2": "US East (Ohio)",
    "westus2": "US West (Oregon)",
    "westus3": "US West (N. California)",
    "centralus": "US East (N. Virginia)",
    "southcentralus": "US East (N. Virginia)",
    "canadacentral": "Canada (Central)",
    "northeurope": "EU (Ireland)",
    "westeurope": "EU (Frankfurt)",
    "uksouth": "EU (London)",
    "swedencentral": "EU (Stockholm)",
    "germanywestcentral": "EU (Frankfurt)",
    "uaenorth": "Middle East (UAE)",
    "centralindia": "Asia Pacific (Mumbai)",
    "southindia": "Asia Pacific (Mumbai)",
    "southeastasia": "Asia Pacific (Singapore)",
    "eastasia": "Asia Pacific (Hong Kong)",
    "japaneast": "Asia Pacific (Tokyo)",
    "australiaeast": "Asia Pacific (Sydney)",
    "brazilsouth": "South America (Sao Paulo)",
}


def _aws_fetch(region_label: str, os_name: str, live: bool = True) -> dict:
    """One OS/region slice of the AWS feed, as {instance_type: {price, vcpu, mem_gib}}."""
    key = f"AWS|{region_label}|{os_name}"
    cached = pricing._read_cache(key)
    if cached and (not live or time.time() - cached[1] < pricing.CACHE_TTL_SECONDS):
        return {r["t"]: r for r in cached[0]}
    if not live:
        raise pricing.PricingError("AWS pricing not cached and live pricing is disabled.")

    url = AWS_FEED.format(region=requests.utils.quote(region_label), os=os_name)
    try:
        r = requests.get(url, timeout=30,
                         headers={"User-Agent": pricing.USER_AGENT,
                                  "Accept-Encoding": "gzip, deflate"})
        r.raise_for_status()
        payload = r.json()
    except Exception as exc:
        if cached:
            return {row["t"]: row for row in cached[0]}
        raise pricing.PricingError(f"AWS pricing feed unreachable: {exc}") from exc

    rows = []
    for reg in payload.get("regions", {}).values():
        for _, v in reg.items():
            it = v.get("Instance Type")
            if not it or v.get("Pre Installed S/W", "NA") != "NA":
                continue
            try:
                price = float(v["price"])
                vcpu = int(v["vCPU"])
            except (KeyError, ValueError, TypeError):
                continue
            if price <= 0 or vcpu <= 0:
                continue
            mem = str(v.get("Memory", "0")).replace(" GiB", "").strip()
            try:
                mem_gib = float(mem)
            except ValueError:
                mem_gib = 0.0
            rows.append({"t": it, "price": price, "vcpu": vcpu, "mem_gib": mem_gib,
                         "family": v.get("Instance Family", "")})
    pricing._write_cache(key, rows)
    return {r["t"]: r for r in rows}


def aws_windows_premium(region: str = "eastus", live: bool = True) -> dict:
    """Windows licence premium per vCPU per hour, derived from the live AWS feed.

    Computed as the median of (Windows rate - Linux rate) / vCPU across every
    instance type published in both feeds, which is how AWS actually prices it:
    a flat per-vCPU licence charge on top of the Linux rate.
    """
    label = AWS_REGIONS.get(region, "US East (N. Virginia)")
    lin = _aws_fetch(label, "Linux", live)
    win = _aws_fetch(label, "Windows", live)
    deltas, pairs = [], []
    for t, l in lin.items():
        w = win.get(t)
        if not w:
            continue
        d = (w["price"] - l["price"]) / l["vcpu"]
        if 0 < d < 0.5:                       # discard obvious outliers
            deltas.append(d)
            pairs.append({"instance_type": t, "vcpu": l["vcpu"],
                          "linux_hr": l["price"], "windows_hr": w["price"],
                          "premium_per_vcpu_hr": d})
    if not deltas:
        raise pricing.PricingError("Could not derive an AWS Windows premium.")
    return {
        "region_label": label,
        "per_vcpu_hr": float(np.median(deltas)),
        "instance_count": len(deltas),
        "detail": pd.DataFrame(pairs).sort_values("vcpu"),
        "linux_catalog": lin,
    }


def aws_linux_rate_per_vcpu(region: str = "eastus", live: bool = True) -> float:
    """Median Linux on-demand rate per vCPU/hour for current general-purpose sizes.

    Used only as a sanity check that the providers' compute rates are broadly
    comparable -- the decision does not turn on raw compute price.
    """
    label = AWS_REGIONS.get(region, "US East (N. Virginia)")
    lin = _aws_fetch(label, "Linux", live)
    vals = [v["price"] / v["vcpu"] for t, v in lin.items()
            if t.startswith(("m5.", "m6i.", "m7i.")) and "metal" not in t]
    return float(np.median(vals)) if vals else 0.048


# --------------------------------------------------------------------------
# Published licence rates where no public API exists
# --------------------------------------------------------------------------
# Google Cloud charges a per-vCPU hourly rate for Windows Server on machine types
# with 1+ vCPU. Oracle charges per OCPU. Both are list prices, stated here so the
# assumption is visible rather than buried.
GCP_WINDOWS_PER_VCPU_HR = 0.04
GCP_SOLE_TENANCY_PREMIUM_PCT = 25.0     # required for Windows BYOL on GCP
OCI_WINDOWS_PER_OCPU_HR = 0.092
AWS_DEDICATED_HOST_PREMIUM_PCT = 30.0   # required for Windows BYOL on AWS
IBM_WINDOWS_PER_VCPU_HR = 0.046


@dataclass
class ProviderProfile:
    key: str
    name: str
    short: str
    vmware_service: str
    onprem_service: str
    windows_byol: str            # how BYOL works, in one clause
    byol_shared_tenancy: bool    # can you BYOL Windows without dedicated hardware?
    free_esu: bool               # free Extended Security Updates for EOL Windows/SQL
    sql_paas: str
    notes: str


PROVIDERS: list[ProviderProfile] = [
    ProviderProfile(
        key="azure", name="Microsoft Azure", short="Azure",
        vmware_service="Azure VMware Solution (AVS)",
        onprem_service="Azure Local, Azure Stack Hub, Azure Arc",
        windows_byol="Azure Hybrid Benefit on ordinary shared tenancy",
        byol_shared_tenancy=True, free_esu=True,
        sql_paas="Azure SQL Managed Instance -- near-full SQL Server surface compatibility",
        notes="The only provider where existing Windows Server and SQL Server licences with "
              "Software Assurance remove the licence charge on shared tenancy, and the only "
              "one that grants free Extended Security Updates for end-of-life Windows and "
              "SQL Server."),
    ProviderProfile(
        key="aws", name="Amazon Web Services", short="AWS",
        vmware_service="VMware Cloud on AWS (now sold by Broadcom)",
        onprem_service="AWS Outposts",
        windows_byol="Dedicated Hosts or dedicated instances required for licences "
                     "acquired after 1 October 2019",
        byol_shared_tenancy=False, free_esu=False,
        sql_paas="Amazon RDS for SQL Server -- narrower feature surface than Azure SQL MI",
        notes="The broadest service catalogue and the deepest partner ecosystem, but the "
              "Windows licensing position is structurally worse for a Windows-heavy estate: "
              "BYOL forces dedicated tenancy, and Extended Security Updates are bought."),
    ProviderProfile(
        key="gcp", name="Google Cloud", short="Google Cloud",
        vmware_service="Google Cloud VMware Engine (GCVE)",
        onprem_service="Google Distributed Cloud",
        windows_byol="Sole-tenant nodes required for BYOL",
        byol_shared_tenancy=False, free_esu=False,
        sql_paas="Cloud SQL for SQL Server -- the narrowest of the three",
        notes="Strongest for data, analytics and Kubernetes-native workloads. For a "
              "lift-and-shift Windows estate it carries the same BYOL constraint as AWS, "
              "with a smaller Windows-oriented ecosystem."),
    ProviderProfile(
        key="oci", name="Oracle Cloud Infrastructure", short="OCI",
        vmware_service="Oracle Cloud VMware Solution (OCVS)",
        onprem_service="OCI Dedicated Region, Compute Cloud@Customer",
        windows_byol="BYOL supported; Windows also available licence-included per OCPU",
        byol_shared_tenancy=True, free_esu=False,
        sql_paas="No SQL Server PaaS -- SQL Server runs on IaaS",
        notes="Decisive only when Oracle Database licensing dominates the estate. OCVS gives "
              "full vSphere administrative control, and Oracle licensing terms are materially "
              "better on OCI than on any other cloud. Smallest ecosystem of the four."),
]

PROVIDER_BY_KEY = {p.key: p for p in PROVIDERS}


# --------------------------------------------------------------------------
# The quantitative core: Windows and SQL licensing across providers
# --------------------------------------------------------------------------
HOURS = 730.0


@dataclass
class LicensingInputs:
    windows_vcpu: int            # total Azure-target vCPU on Windows VMs
    windows_vms: int
    sql_vms: int
    eol_windows_vms: int
    oracle_vms: int
    linux_vcpu: int
    total_vcpu: int
    owns_software_assurance: bool = True
    azure_windows_premium_per_vcpu_hr: float = 0.046
    aws_windows_premium_per_vcpu_hr: float = 0.046
    esu_cost_per_vm_year: float = 0.0   # filled from the ESU model below


# Extended Security Updates list at roughly 75% of the full licence price per
# year and escalate. This is the per-server-per-year order of magnitude for
# Windows Server Standard; it is an assumption, and it is shown in the UI.
ESU_PER_VM_YEAR = 1200.0


def licensing_comparison(inp: LicensingInputs) -> pd.DataFrame:
    """Annual Windows/SQL licensing cost by provider for this estate.

    Compute capacity is held constant across providers -- the point is the
    licensing delta, not a compute price war, because compute rates across the
    three large providers are within a few percent of each other for equivalent
    capacity.
    """
    rows = []
    for p in PROVIDERS:
        detail: list[str] = []

        if p.key == "azure":
            if inp.owns_software_assurance:
                win = 0.0
                detail.append("Azure Hybrid Benefit removes the Windows Server licence "
                              "charge on shared tenancy.")
            else:
                win = inp.windows_vcpu * inp.azure_windows_premium_per_vcpu_hr * HOURS * 12
                detail.append("No Software Assurance, so licence-included pricing applies.")
            dedicated = 0.0
            esu = 0.0
            detail.append("Extended Security Updates for end-of-life Windows and SQL Server "
                          "are free while the workload runs on Azure.")

        elif p.key == "aws":
            if inp.owns_software_assurance:
                # BYOL is possible but only on dedicated tenancy.
                win = 0.0
                dedicated = (inp.windows_vcpu * 0.048 * HOURS * 12
                             * AWS_DEDICATED_HOST_PREMIUM_PCT / 100.0)
                detail.append("BYOL requires Dedicated Hosts for licences acquired after "
                              "1 October 2019, modelled as a "
                              f"{AWS_DEDICATED_HOST_PREMIUM_PCT:.0f}% dedicated-capacity "
                              "premium on the Windows footprint.")
            else:
                win = inp.windows_vcpu * inp.aws_windows_premium_per_vcpu_hr * HOURS * 12
                dedicated = 0.0
                detail.append("License Included pricing, derived live from the AWS pricing "
                              "feed.")
            esu = inp.eol_windows_vms * ESU_PER_VM_YEAR
            detail.append("Extended Security Updates must be purchased.")

        elif p.key == "gcp":
            if inp.owns_software_assurance:
                win = 0.0
                dedicated = (inp.windows_vcpu * 0.048 * HOURS * 12
                             * GCP_SOLE_TENANCY_PREMIUM_PCT / 100.0)
                detail.append("BYOL requires sole-tenant nodes, modelled as a "
                              f"{GCP_SOLE_TENANCY_PREMIUM_PCT:.0f}% sole-tenancy premium on "
                              "the Windows footprint.")
            else:
                win = inp.windows_vcpu * GCP_WINDOWS_PER_VCPU_HR * HOURS * 12
                dedicated = 0.0
                detail.append(f"Licence-included at a published "
                              f"${GCP_WINDOWS_PER_VCPU_HR:.3f} per vCPU per hour.")
            esu = inp.eol_windows_vms * ESU_PER_VM_YEAR
            detail.append("Extended Security Updates must be purchased.")

        else:  # oci
            win = (0.0 if inp.owns_software_assurance
                   else inp.windows_vcpu / 2 * OCI_WINDOWS_PER_OCPU_HR * HOURS * 12)
            dedicated = 0.0
            esu = inp.eol_windows_vms * ESU_PER_VM_YEAR
            detail.append("BYOL is permitted on shared tenancy." if inp.owns_software_assurance
                          else f"Licence-included at ${OCI_WINDOWS_PER_OCPU_HR:.3f} per OCPU "
                               "per hour (two vCPU per OCPU).")
            detail.append("Extended Security Updates must be purchased.")

        rows.append({
            "provider": p.short,
            "key": p.key,
            "windows_licence": win,
            "dedicated_tenancy_premium": dedicated,
            "esu": esu,
            "total_annual": win + dedicated + esu,
            "byol_on_shared_tenancy": p.byol_shared_tenancy,
            "free_esu": p.free_esu,
            "detail": " ".join(detail),
        })

    df = pd.DataFrame(rows).sort_values("total_annual").reset_index(drop=True)
    best = df["total_annual"].min()
    df["delta_vs_best"] = df["total_annual"] - best
    return df


# --------------------------------------------------------------------------
# Fit scoring against the estate's actual characteristics
# --------------------------------------------------------------------------
CRITERIA = {
    "windows_licensing": "Windows Server licensing economics",
    "sql_estate": "SQL Server path and compatibility",
    "eol_remediation": "End-of-life OS remediation cost",
    "oracle_estate": "Oracle Database licensing",
    "vmware_path": "VMware-native landing option",
    "linux_opensource": "Linux and open-source workloads",
    "skills_fit": "Fit with the client's existing skills",
    "ecosystem": "Partner ecosystem and service breadth",
    "hybrid_onprem": "Hybrid and on-premises extension",
    "data_ai": "Data and AI roadmap",
}

# Base capability scores, 1-5. These describe the provider; the estate decides
# how much each criterion is weighted, which is where the fit actually comes from.
_BASE_SCORES: dict[str, dict[str, int]] = {
    "azure": dict(windows_licensing=5, sql_estate=5, eol_remediation=5, oracle_estate=3,
                  vmware_path=5, linux_opensource=4, skills_fit=5, ecosystem=5,
                  hybrid_onprem=5, data_ai=4),
    "aws":   dict(windows_licensing=2, sql_estate=3, eol_remediation=2, oracle_estate=3,
                  vmware_path=3, linux_opensource=5, skills_fit=3, ecosystem=5,
                  hybrid_onprem=4, data_ai=4),
    "gcp":   dict(windows_licensing=2, sql_estate=2, eol_remediation=2, oracle_estate=2,
                  vmware_path=4, linux_opensource=5, skills_fit=2, ecosystem=3,
                  hybrid_onprem=3, data_ai=5),
    "oci":   dict(windows_licensing=3, sql_estate=2, eol_remediation=2, oracle_estate=5,
                  vmware_path=5, linux_opensource=4, skills_fit=2, ecosystem=2,
                  hybrid_onprem=4, data_ai=3),
}


def estate_weights(windows_pct: float, sql_vms: int, oracle_vms: int, eol_vms: int,
                   blocked_vms: int, total_vms: int,
                   microsoft_shop: bool = True) -> dict[str, float]:
    """Weights derived from what the estate actually contains, not from taste."""
    n = max(total_vms, 1)
    return {
        "windows_licensing": 0.6 + 2.6 * (windows_pct / 100.0),
        "sql_estate": 0.4 + 2.2 * min(sql_vms / n * 4, 1.0),
        "eol_remediation": 0.3 + 2.0 * min(eol_vms / n * 3, 1.0),
        "oracle_estate": 0.2 + 2.4 * min(oracle_vms / n * 8, 1.0),
        "vmware_path": 0.6 + 1.6 * min(blocked_vms / n * 6, 1.0),
        "linux_opensource": 0.5 + 1.8 * (1 - windows_pct / 100.0),
        "skills_fit": 1.6 if microsoft_shop else 0.9,
        "ecosystem": 1.0,
        "hybrid_onprem": 1.0,
        "data_ai": 0.9,
    }


def rank_providers(weights: dict[str, float]) -> pd.DataFrame:
    rows = []
    total_w = sum(weights.get(c, 0) for c in CRITERIA)
    for p in PROVIDERS:
        sc = _BASE_SCORES[p.key]
        score = sum(sc.get(c, 3) * weights.get(c, 0) for c in CRITERIA)
        rec = {"provider": p.short, "key": p.key,
               "fit_score": round(score / (5.0 * total_w) * 100, 1)}
        rec.update({c: sc.get(c, 3) for c in CRITERIA})
        rows.append(rec)
    return pd.DataFrame(rows).sort_values("fit_score", ascending=False).reset_index(drop=True)


def recommendation(rank: pd.DataFrame, lic: pd.DataFrame, windows_pct: float,
                   sql_vms: int, eol_windows_vms: int, oracle_vms: int,
                   total_vms: int, currency: str = "USD") -> dict:
    """``eol_windows_vms`` is Windows-only on purpose: Extended Security Updates
    apply to Windows Server and SQL Server, not to end-of-life Linux."""
    """A single, defensible answer with the reasons that produced it."""
    winner = rank.iloc[0]
    runner = rank.iloc[1]
    p = PROVIDER_BY_KEY[winner["key"]]

    lic_row = lic[lic["key"] == winner["key"]].iloc[0]
    worst = lic.iloc[-1]
    lic_gap = float(worst["total_annual"] - lic_row["total_annual"])

    reasons = []
    if windows_pct >= 45:
        reasons.append(
            f"**{windows_pct:.0f}% of the estate is Windows.** Azure is the only provider "
            "where existing Windows Server licences with Software Assurance remove the "
            "licence charge on ordinary shared tenancy. On AWS and Google Cloud, bringing "
            "your own licence forces dedicated or sole-tenant hardware, which costs more and "
            "gives up the elasticity that justified the move.")
    if eol_windows_vms:
        reasons.append(
            f"**{eol_windows_vms} Windows VMs are past end of support.** Free Extended "
            "Security Updates are available only while the workload runs on Azure. Everywhere "
            f"else they are a purchase -- roughly {currency} "
            f"{eol_windows_vms * ESU_PER_VM_YEAR:,.0f} a year on this estate, recurring until "
            "the operating systems are upgraded.")
    if sql_vms:
        reasons.append(
            f"**{sql_vms} SQL Server workloads.** Azure SQL Managed Instance has the closest "
            "engine-surface compatibility of any managed SQL Server service, so most of these "
            "move without application change. Amazon RDS for SQL Server and Cloud SQL both "
            "have narrower feature surfaces and force more workloads to stay on IaaS.")
    if oracle_vms >= max(total_vms * 0.06, 12):
        reasons.append(
            f"**{oracle_vms} Oracle Database VMs is a material sub-estate.** Oracle licensing "
            "terms are materially better on OCI than on any other cloud. This does not change "
            "the primary recommendation, but the Oracle workloads deserve to be priced "
            "separately -- Oracle Database@Azure or a dual-provider split are both legitimate.")

    counter = (
        f"**The case against.** {runner['provider']} scores {runner['fit_score']:.0f} against "
        f"{winner['fit_score']:.0f}, and the gap is mostly licensing rather than capability. "
        "If the client does not hold Software Assurance, or intends to move the Windows estate "
        "to Linux, most of the advantage disappears and the decision reopens on ecosystem and "
        "skills. It is also worth pricing a second provider properly rather than assuming -- "
        "a credible alternative is the only real leverage in an enterprise agreement "
        "negotiation.")

    return {
        "winner": p, "winner_row": winner, "runner_up": runner,
        "reasons": reasons, "counter": counter,
        "licensing_advantage_annual": lic_gap,
        "licensing_advantage_vs": str(worst["provider"]),
        "confidence": ("High" if winner["fit_score"] - runner["fit_score"] >= 8
                       else "Moderate" if winner["fit_score"] - runner["fit_score"] >= 3
                       else "Marginal"),
    }
