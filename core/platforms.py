"""Target platform alternatives -- where the 547 VMs could actually land.

Azure public cloud is one option among many. This module models the realistic
shortlist for a post-Broadcom VMware estate, including the **on-premises Azure**
options that answer "we want cloud economics and cloud tooling but the workload
cannot leave our building" -- the Azure equivalents of AWS Outposts:

* **Azure Local** (formerly Azure Stack HCI) -- Azure-managed infrastructure on
  your own hardware in your own data centre, billed per physical core per month.
* **Azure Stack Hub** -- a self-contained Azure region you operate, including
  fully disconnected/air-gapped deployments.
* **Azure Arc** -- leave the workload where it is and manage it as an Azure
  resource, which is the cheapest way to get Azure governance without moving.

Non-AWS clouds and non-VMware hypervisors are included because "migrate to
Azure" is a decision that should be tested against its alternatives, not assumed.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

# Scoring dimensions. The first five were added to close the gap against the
# source paper's evaluation criteria, which specifies thirteen -- including
# "Broadcom dependency removed" as the single Critical criterion, and "exit cost
# from the new platform", which the paper calls the question rarely asked at
# selection. See CRITERION_WEIGHT below for the paper's recommended weighting.
CRITERIA = {
    "broadcom_exit": "Broadcom dependency removed (5 = eliminated, 1 = retained)",
    "feature_parity": "Feature parity for the workload (HA, live migration, affinity)",
    "vendor_risk": "Freedom from vendor and roadmap risk",
    "exit_cost": "Cheapness of leaving this platform in five years",
    "hardware_impact": "Freedom from hardware refresh, HCL and SAN stranding",
    "exit_speed": "Speed of data centre exit",
    "migration_effort": "Low migration effort (5 = least work)",
    "run_cost": "Run-cost efficiency",
    "modernisation": "Modernisation runway",
    "data_residency": "Data residency / sovereignty control",
    "latency_control": "Low-latency / edge suitability",
    "ops_burden": "Low operational burden (5 = least)",
    "lock_in": "Freedom from lock-in (5 = most portable)",
    "skills_fit": "Fit with existing Microsoft skills",
    "resilience": "Resilience & DR capability",
    "compliance": "Regulated-workload suitability",
}

_P = [
    dict(
        platform="Azure native IaaS (rehost)", family="Azure public cloud",
        location="Public cloud region",
        scores=dict(broadcom_exit=5, feature_parity=4, vendor_risk=4,
                    exit_cost=3, hardware_impact=5,
                    exit_speed=4, migration_effort=4, run_cost=4, modernisation=4,
                    data_residency=3, latency_control=2, ops_burden=4, lock_in=3,
                    skills_fit=5, resilience=5, compliance=4),
        summary="Lift-and-shift onto Azure Virtual Machines. The default destination and the "
                "baseline every other option should be measured against.",
        cost_model="Per-second VM billing, managed disks, plus platform services. Azure Hybrid "
                   "Benefit and 3-year reservations together take 55-65% off list.",
        pros=["No VMware licence at all -- the Broadcom problem disappears",
              "Right-sizing harvests the on-premises over-provisioning immediately",
              "Full Azure service catalogue available for later modernisation",
              "Reserved instances and Hybrid Benefit are large, contractible savings"],
        cons=["Every VM needs re-IP, re-agent and re-test",
              "Workloads with vSphere-specific constructs (shared disks, FT, RDM) need rework",
              "Egress charges and cross-region traffic become a running cost line",
              "Requires the operating model to change, not just the infrastructure"],
        best_when="A time-boxed data centre exit where most workloads are ordinary Windows and "
                  "Linux servers -- which describes the large majority of this estate.",
    ),
    dict(
        platform="Azure PaaS (replatform / refactor)", family="Azure public cloud",
        location="Public cloud region",
        scores=dict(broadcom_exit=5, feature_parity=2, vendor_risk=4,
                    exit_cost=1, hardware_impact=5,
                    exit_speed=2, migration_effort=1, run_cost=5, modernisation=5,
                    data_residency=3, latency_control=2, ops_burden=5, lock_in=1,
                    skills_fit=4, resilience=5, compliance=4),
        summary="Azure SQL Managed Instance, App Service, AKS and the rest -- retiring the guest "
                "OS rather than moving it.",
        cost_model="Consumption or vCore-based; removes OS licensing, patching, backup and HA "
                   "configuration from the run cost entirely.",
        pros=["Lowest long-run cost per workload and the biggest operational saving",
              "Removes OS patching, backup and HA engineering from the estate",
              "Elastic scale that an on-premises VM never had"],
        cons=["Highest migration effort and the only option that needs application-team capacity",
              "Strongest lock-in of any option here",
              "Wrong thing to couple to a hard data-centre-exit deadline"],
        best_when="Databases and stateless web tiers, run as a deliberate second phase after the "
                  "exit -- not as a dependency of it.",
    ),
    dict(
        platform="Azure VMware Solution (AVS)", family="Azure public cloud",
        location="Public cloud region (dedicated hosts)",
        scores=dict(broadcom_exit=2, feature_parity=5, vendor_risk=2,
                    exit_cost=2, hardware_impact=5,
                    exit_speed=5, migration_effort=5, run_cost=2, modernisation=2,
                    data_residency=3, latency_control=2, ops_burden=3, lock_in=2,
                    skills_fit=4, resilience=4, compliance=4),
        summary="Your vSphere environment, running on dedicated Azure hardware. VMs move with "
                "HCX at effectively zero downtime and keep their IP addresses.",
        cost_model="Per-host, per-hour on dedicated nodes with a three-host minimum. Since "
                   "November 2025, new nodes also require a portable VMware Cloud Foundation "
                   "subscription bought separately from Broadcom -- Microsoft no longer includes it.",
        pros=["Fastest possible exit: no re-IP, no re-platform, no application change",
              "Existing vSphere skills and runbooks keep working on day one",
              "Handles the workloads native IaaS rejects -- shared disks, FT, encrypted VMs"],
        cons=["Three-host minimum means you pay for capacity, not consumption",
              "You now pay Broadcom *and* Microsoft -- the VCF subscription is no longer bundled",
              "Run cost frequently exceeds on-premises VMware once egress and networking land",
              "Defers modernisation rather than delivering it, and the exit is a second project"],
        best_when="A hard deadline (lease expiry, divestment) makes exit speed worth the premium "
                  "-- and only with a funded, dated plan to leave AVS afterwards.",
    ),
    dict(
        platform="Azure Local (formerly Azure Stack HCI)", family="On-premises Azure",
        location="Your data centre / edge site",
        scores=dict(broadcom_exit=5, feature_parity=4, vendor_risk=4,
                    exit_cost=3, hardware_impact=1,
                    exit_speed=1, migration_effort=3, run_cost=3, modernisation=3,
                    data_residency=5, latency_control=5, ops_burden=3, lock_in=3,
                    skills_fit=5, resilience=4, compliance=5),
        summary="Azure's own stack running on validated hardware in your data centre, managed "
                "from the Azure portal through Arc. The closest Azure equivalent to AWS Outposts, "
                "and the most direct like-for-like replacement for vSphere on-premises.",
        cost_model="USD 10 per physical core per month for the Azure Local service (USD 20.10 "
                   "with external SAN support), plus your own hardware, plus Windows Server guest "
                   "rights at USD 23.30 per core per month unless covered by Azure Hybrid Benefit. "
                   "First 60 days free. No VMware licence.",
        pros=["Removes the Broadcom licence entirely while keeping workloads on-premises",
              "Data never leaves the building -- the strongest answer to residency objections",
              "Single-node clusters are now supported, so branch and edge sites are viable",
              "Runs AKS and Azure Virtual Desktop session hosts locally, and is Arc-managed "
              "alongside real Azure resources",
              "Existing Hyper-V and Windows skills transfer directly"],
        cons=["No data centre exit -- you still own hardware, power, space and refresh",
              "Requires validated hardware from a partner; you cannot use arbitrary servers",
              "Guest OS conversion from VMware to Hyper-V is a real migration, not a vMotion",
              "Smaller ecosystem and fewer third-party integrations than vSphere"],
        best_when="Workloads that legally or physically cannot leave the site, latency-bound "
                  "systems, and any client whose objection to Azure is residency rather than cost.",
    ),
    dict(
        platform="Azure Stack Hub", family="On-premises Azure",
        location="Your data centre (can be fully disconnected)",
        scores=dict(broadcom_exit=5, feature_parity=3, vendor_risk=3,
                    exit_cost=2, hardware_impact=1,
                    exit_speed=1, migration_effort=2, run_cost=2, modernisation=3,
                    data_residency=5, latency_control=5, ops_burden=2, lock_in=2,
                    skills_fit=4, resilience=3, compliance=5),
        summary="A self-contained Azure region you own and operate, including air-gapped "
                "deployments with no connectivity to Microsoft at all.",
        cost_model="Integrated-system purchase or lease from an OEM, plus either pay-as-you-use "
                   "Azure metering or a fixed-fee capacity licence for disconnected use.",
        pros=["The only option that works with no internet connectivity whatsoever",
              "Consistent Azure Resource Manager APIs, so automation is portable",
              "Meets the strictest classified and sovereign requirements"],
        cons=["Highest operational burden of any option -- you run the region",
              "Lags public Azure by several service generations",
              "Capacity is fixed at purchase; elasticity is limited to what you bought"],
        best_when="Defence, intelligence, or regulated workloads with a genuine air-gap "
                  "requirement. Rare, but decisive where it applies.",
    ),
    dict(
        platform="Azure Arc only (stay put, manage from Azure)", family="On-premises Azure",
        location="Existing VMware estate",
        scores=dict(broadcom_exit=1, feature_parity=5, vendor_risk=5,
                    exit_cost=5, hardware_impact=5,
                    exit_speed=1, migration_effort=5, run_cost=1, modernisation=2,
                    data_residency=5, latency_control=5, ops_burden=2, lock_in=5,
                    skills_fit=5, resilience=3, compliance=5),
        summary="Project the existing vSphere estate into Azure as Arc resources. Azure Policy, "
                "Defender for Cloud, Update Manager and Monitor all apply -- without moving a "
                "single VM.",
        cost_model="Arc control-plane management is free for servers; you pay only for the Azure "
                   "services consumed (Defender, Monitor, Update Manager). VMware licence costs "
                   "continue unchanged.",
        pros=["Near-zero migration effort and no application risk",
              "Delivers Azure governance and security posture in weeks, not quarters",
              "A legitimate interim step that makes the later migration easier",
              "Fully reversible -- no lock-in of any kind"],
        cons=["Does nothing about the Broadcom licence bill, which is usually the trigger",
              "No data centre exit, no hardware saving, no refresh avoidance",
              "Solves governance, not economics"],
        best_when="As a first move alongside the migration programme, or where the migration "
                  "decision has to be deferred but governance cannot wait.",
    ),
    dict(
        platform="Nutanix Cloud Clusters (NC2) on Azure", family="Hybrid alternative",
        location="Public cloud region (bare metal) and/or on-premises",
        scores=dict(broadcom_exit=5, feature_parity=4, vendor_risk=3,
                    exit_cost=3, hardware_impact=5,
                    exit_speed=4, migration_effort=4, run_cost=2, modernisation=2,
                    data_residency=4, latency_control=3, ops_burden=3, lock_in=2,
                    skills_fit=3, resilience=4, compliance=4),
        summary="Nutanix AHV running on Azure bare-metal, with the identical stack available "
                "on-premises -- one hypervisor across both, and a genuine escape from VMware.",
        cost_model="Nutanix subscription plus Azure bare-metal host charges. Comparable order of "
                   "magnitude to AVS.",
        pros=["Same platform on-premises and in Azure, so workloads move both directions",
              "Complete exit from the Broadcom licence model",
              "Built-in migration tooling from ESXi to AHV"],
        cons=["Swaps one proprietary vendor for another",
              "Bare-metal host pricing is capacity-based, like AVS",
              "New skills for a team that only knows vSphere"],
        best_when="The client wants out of VMware specifically and values a consistent hybrid "
                  "platform more than native cloud services.",
    ),
    dict(
        platform="Nutanix AHV on-premises", family="On-premises hypervisor",
        location="Your data centre",
        scores=dict(broadcom_exit=5, feature_parity=4, vendor_risk=3,
                    exit_cost=3, hardware_impact=2,
                    exit_speed=1, migration_effort=3, run_cost=3, modernisation=2,
                    data_residency=5, latency_control=5, ops_burden=3, lock_in=2,
                    skills_fit=2, resilience=4, compliance=5),
        summary="Replace vSphere with Nutanix on the existing or refreshed hardware. The most "
                "common straight VMware replacement in the enterprise mid-market.",
        cost_model="Per-core subscription, typically materially below current VCF pricing, plus "
                   "hardware.",
        pros=["Mature, enterprise-grade, with a well-trodden ESXi-to-AHV conversion path",
              "Hypervisor licence included in the platform subscription",
              "Keeps everything on-premises with no application change"],
        cons=["No data centre exit and no cloud economics",
              "Retraining the platform team",
              "Vendor concentration risk simply moves to Nutanix"],
        best_when="The driver is purely the Broadcom bill and there is no mandate to leave the "
                  "data centre.",
    ),
    dict(
        platform="Microsoft Hyper-V / Windows Server + SCVMM", family="On-premises hypervisor",
        location="Your data centre",
        scores=dict(broadcom_exit=5, feature_parity=3, vendor_risk=4,
                    exit_cost=4, hardware_impact=4,
                    exit_speed=1, migration_effort=3, run_cost=4, modernisation=2,
                    data_residency=5, latency_control=5, ops_burden=3, lock_in=4,
                    skills_fit=5, resilience=3, compliance=5),
        summary="Hyper-V on Windows Server Datacenter, which most enterprises already license. "
                "The cheapest possible VMware replacement on paper.",
        cost_model="Effectively included where Windows Server Datacenter is already owned; "
                   "System Center licensing for management.",
        pros=["Often no incremental licence cost at all",
              "Existing Windows skills apply directly",
              "Clean path to Azure Local later, since it is the same virtualisation stack"],
        cons=["Management tooling is well behind vCenter",
              "Linux guest support is workable but not a strength",
              "No data centre exit"],
        best_when="Cost-driven replacement in a Microsoft-centric shop, especially as a stepping "
                  "stone to Azure Local.",
    ),
    dict(
        platform="Red Hat OpenShift Virtualization", family="On-premises hypervisor",
        location="Your data centre or any cloud",
        scores=dict(broadcom_exit=5, feature_parity=3, vendor_risk=4,
                    exit_cost=4, hardware_impact=3,
                    exit_speed=2, migration_effort=2, run_cost=3, modernisation=5,
                    data_residency=5, latency_control=4, ops_burden=2, lock_in=4,
                    skills_fit=2, resilience=4, compliance=4),
        summary="Run VMs and containers on one KubeVirt-based platform, so the same infrastructure "
                "carries today's VMs and tomorrow's containers.",
        cost_model="OpenShift subscription per core or socket; runs on-premises or on any cloud.",
        pros=["A single platform for VMs and containers -- a real modernisation runway",
              "Open-source foundation, portable across clouds",
              "Includes a migration toolkit for virtualization from vSphere"],
        cons=["Steep learning curve for a traditional virtualisation team",
              "VM feature parity with vSphere is still maturing",
              "Only pays off if the container ambition is genuine"],
        best_when="The client already runs OpenShift and has a real container strategy, not an "
                  "aspirational one.",
    ),
    dict(
        platform="Proxmox VE", family="On-premises hypervisor",
        location="Your data centre",
        scores=dict(broadcom_exit=5, feature_parity=3, vendor_risk=4,
                    exit_cost=5, hardware_impact=5,
                    exit_speed=1, migration_effort=3, run_cost=5, modernisation=2,
                    data_residency=5, latency_control=5, ops_burden=2, lock_in=5,
                    skills_fit=1, resilience=3, compliance=3),
        summary="Open-source KVM-based virtualisation with optional paid support. The cheapest "
                "credible VMware replacement, and increasingly seen in production.",
        cost_model="Free to use; support subscription per socket at a small fraction of VCF.",
        pros=["Dramatically lower licence cost than any commercial option",
              "No lock-in whatsoever",
              "Built-in ESXi import"],
        cons=["Thinner enterprise support ecosystem and fewer certified ISV stacks",
              "Operational tooling and RBAC are less mature than vCenter",
              "Hard to defend to a risk committee for Tier 0 workloads"],
        best_when="Non-production, test/dev and Tier 3 estates where the licence saving is real "
                  "and the risk appetite allows it -- which is over half of this estate.",
    ),
    dict(
        platform="Google Cloud VMware Engine (GCVE)", family="Other public cloud",
        location="Google Cloud region",
        scores=dict(broadcom_exit=2, feature_parity=5, vendor_risk=2,
                    exit_cost=2, hardware_impact=5,
                    exit_speed=5, migration_effort=5, run_cost=2, modernisation=3,
                    data_residency=3, latency_control=2, ops_burden=3, lock_in=2,
                    skills_fit=2, resilience=4, compliance=4),
        summary="The same vSphere-in-cloud pattern as AVS, on Google Cloud. Worth pricing purely "
                "as commercial leverage.",
        cost_model="Per-node hourly on dedicated hardware, with committed-use discounts.",
        pros=["Same zero-downtime HCX migration path as AVS",
              "Genuinely useful as a competitive lever in Azure negotiations",
              "Strong data and analytics services if that is where the roadmap points"],
        cons=["Fragments the Microsoft relationship and the skills base",
              "Same capacity-based economics as AVS",
              "Windows and SQL licensing is less advantageous outside Azure"],
        best_when="Mainly as a pricing benchmark, or where the wider application roadmap already "
                  "points at Google Cloud.",
    ),
    dict(
        platform="Oracle Cloud VMware Solution / OCI", family="Other public cloud",
        location="OCI region",
        scores=dict(broadcom_exit=2, feature_parity=5, vendor_risk=2,
                    exit_cost=2, hardware_impact=5,
                    exit_speed=4, migration_effort=4, run_cost=4, modernisation=2,
                    data_residency=4, latency_control=2, ops_burden=3, lock_in=2,
                    skills_fit=2, resilience=3, compliance=4),
        summary="Customer-managed vSphere on OCI, with the sharpest commercial terms of the "
                "hyperscalers and the only place Oracle licensing works fully in your favour.",
        cost_model="Per-node hourly, typically the lowest of the VMware-in-cloud options; Oracle "
                   "Database licensing is materially cheaper on OCI.",
        pros=["Lowest headline cost among VMware-in-cloud offerings",
              "You retain full vSphere administrative control, unlike AVS",
              "Decisive if the estate carries significant Oracle Database licensing"],
        cons=["Smallest ecosystem of the major clouds",
              "Poor fit for a Microsoft-centric estate that is 60% Windows",
              "Fragments skills and tooling"],
        best_when="Only if Oracle Database licensing is a large part of the bill -- which for the "
                  "Oracle VMs in this estate is worth pricing separately.",
    ),
    dict(
        platform="SUSE Virtualization (Harvester) + Rancher", family="Kubernetes-unified",
        location="Your data centre",
        scores=dict(broadcom_exit=5, feature_parity=3, vendor_risk=3,
                    exit_cost=5, hardware_impact=4,
                    exit_speed=1, migration_effort=2, run_cost=4, modernisation=5,
                    data_residency=5, latency_control=5, ops_burden=2, lock_in=5,
                    skills_fit=1, resilience=3, compliance=3),
        summary="Open-source hyperconverged virtualisation built on Kubernetes, KubeVirt and "
                "Longhorn, managed through Rancher with SUSE commercial support. The lighter "
                "counterpart to OpenShift Virtualization.",
        cost_model="Genuinely open-source licensing; SUSE subscription for support. No per-core "
                   "hypervisor licence at all.",
        pros=["The Kubernetes-unified trajectory without OpenShift's licensing weight",
              "Genuinely open-source licence model, so no acquisition repricing risk",
              "Lighter footprint and a more infrastructure-oriented interface than OpenShift",
              "Natural fit where the estate is already standardised on SUSE Linux Enterprise"],
        cons=["Smaller installed base and a narrower third-party ecosystem than OpenShift",
              "Backup vendor support, monitoring integrations and available expertise are all "
              "thinner, which raises delivery risk on a regulated estate",
              "Kubernetes-shaped operating model -- a substantial change for a vSphere team"],
        best_when="SUSE-aligned estates wanting an open-source-licensed Kubernetes-native "
                  "platform. Worth including in a formal market scan; not a primary "
                  "recommendation where regulated-estate ecosystem depth is required.",
    ),
    dict(
        platform="XCP-ng / Vates (Xen Orchestra)", family="On-premises hypervisor",
        location="Your data centre",
        scores=dict(broadcom_exit=5, feature_parity=3, vendor_risk=3,
                    exit_cost=4, hardware_impact=4,
                    exit_speed=1, migration_effort=3, run_cost=4, modernisation=2,
                    data_residency=5, latency_control=5, ops_burden=3, lock_in=4,
                    skills_fit=1, resilience=3, compliance=3),
        summary="Open-source Xen-based virtualisation with commercial support from Vates, managed "
                "through Xen Orchestra. More structured than Proxmox and less expensive than "
                "Nutanix, which is a real niche.",
        cost_model="Open-source platform with Vates support subscriptions. Commercial pricing is "
                   "opaque, which itself complicates business-case modelling.",
        pros=["Xen's microkernel architecture gives strong isolation between hypervisor and "
              "guests -- a genuine security-architecture argument",
              "Structurally familiar to former Citrix Hypervisor / XenServer teams",
              "European-domiciled vendor, which matters for some public-sector and "
              "sovereignty-sensitive buyers"],
        cons=["Smaller community than Proxmox",
              "Opaque commercial pricing complicates the business case",
              "Noticeably less third-party tool support than VMware, Hyper-V or Nutanix"],
        best_when="Former XenServer estates, and organisations for whom vendor domicile is a "
                  "procurement or sovereignty consideration. Record as evaluated-and-not-selected "
                  "rather than omitted.",
    ),
    dict(
        platform="OpenStack (managed or self-managed)", family="On-premises hypervisor",
        location="Your data centre",
        scores=dict(broadcom_exit=5, feature_parity=4, vendor_risk=4,
                    exit_cost=4, hardware_impact=3,
                    exit_speed=1, migration_effort=1, run_cost=2, modernisation=4,
                    data_residency=5, latency_control=5, ops_burden=1, lock_in=4,
                    skills_fit=1, resilience=3, compliance=4),
        summary="A full private cloud with multi-tenancy, quotas, self-service provisioning and "
                "API-driven consumption. The reference answer for organisations that need to "
                "operate an internal cloud rather than a virtualisation platform.",
        cost_model="Self-managed at no licence cost, or a supported distribution from Canonical, "
                   "Red Hat or Mirantis. The dominant cost is standing engineering headcount.",
        pros=["Genuine self-service, multi-tenancy and chargeback that no hypervisor offers",
              "Vendor-neutral, foundation-governed, available from several distributors",
              "The right answer where internal tenants genuinely require API-driven "
              "infrastructure"],
        cons=["The highest operational burden of any option assessed -- it needs a standing team "
              "with deep expertise",
              "Under-resourced deployments become unsupportable, and self-managed OpenStack has "
              "a documented history of becoming the most expensive line in the budget once "
              "staffing is counted honestly",
              "Time to value is measured in quarters, not weeks",
              "Selecting it substitutes a larger transformation programme for the one being "
              "solved"],
        best_when="Service providers, large research and public-sector estates with a real "
                  "self-service requirement. Not a hypervisor replacement, and not recommended "
                  "where the requirement is migration rather than building a cloud.",
    ),
    dict(
        platform="Stay on VMware (VCF 9, renegotiated)", family="Do nothing",
        location="Your data centre",
        scores=dict(broadcom_exit=1, feature_parity=5, vendor_risk=1,
                    exit_cost=2, hardware_impact=2,
                    exit_speed=1, migration_effort=5, run_cost=1, modernisation=1,
                    data_residency=5, latency_control=5, ops_burden=3, lock_in=1,
                    skills_fit=5, resilience=4, compliance=5),
        summary="Renew with Broadcom and keep the estate as it is. The honest baseline every "
                "business case has to beat.",
        cost_model="Per-core VCF subscription with a 16-core-per-socket minimum, renewing on a "
                   "1-, 3- or 5-year term. Renewals have repriced sharply.",
        pros=["Zero migration risk and zero project cost",
              "No retraining, no application change, no cutover weekends",
              "Preserves every existing operational process"],
        cons=["The licence cost is the problem being solved, and it renews",
              "Hardware refresh capex still lands on schedule",
              "No cloud elasticity and no modernisation path",
              "Negotiating leverage decays the longer you have no alternative"],
        best_when="As a costed baseline, and as leverage. Building a credible alternative is "
                  "itself worth money at the negotiating table, whether or not you execute it.",
    ),
]


# --------------------------------------------------------------------------
# Evaluated and not shortlisted.
#
# These are not scored, because scoring implies candidacy. They are recorded
# because the source paper's own argument is that a documented, comprehensive
# alternatives evaluation is the instrument that moves the incumbent's renewal
# quote -- which is exactly what Scenario B on the business case is priced on.
# An evaluation that cannot answer "did you look at OpenStack?" is worth less at
# the negotiating table than one that can.
# --------------------------------------------------------------------------
EVALUATED_NOT_SHORTLISTED = [
    ("Scale Computing HyperCore",
     "Purpose-built HCI emphasising simplicity and edge deployment. Genuinely strong "
     "at automated self-healing and low-touch operation.",
     "Optimised for edge and small-site deployments rather than a consolidated "
     "enterprise data centre; ecosystem depth is limited at enterprise scale."),
    ("Verge.io",
     "Software-defined data centre with native multi-tenancy and nested virtual data "
     "centres. Interesting architecture and aggressive commercial positioning.",
     "Small installed base and limited independent operational track record at "
     "enterprise scale; carries more platform risk than most enterprise risk "
     "appetites will accept."),
    ("Oracle Linux Virtualization Manager / OCVS",
     "KVM-based, oVirt-derived, with no separate hypervisor licence cost for "
     "Oracle-licensed estates. OCVS provides a VMware-compatible cloud landing zone.",
     "Attractive only where the estate is Oracle-heavy and Oracle licensing terms "
     "dominate the decision. Trades a Broadcom dependency for an Oracle one."),
    ("Bigstack CubeCOS",
     "Integrated OpenStack-derived cloud platform packaged for enterprise consumption.",
     "Niche presence and a limited regional support footprint; inherits OpenStack's "
     "operational complexity."),
    ("oVirt",
     "Open-source upstream of the former Red Hat Virtualization, sharing lineage with "
     "OpenShift Virtualization. Provides HA, live migration and a web console.",
     "Community-supported with no enterprise support contract, and Red Hat's strategic "
     "investment is in OpenShift Virtualization, so the forward roadmap is uncertain."),
    ("AWS Elastic VMware Service",
     "The managed-VMware pattern on AWS, equivalent to AVS and GCVE.",
     "Subject to the same Broadcom bring-your-own-licence requirement as AVS, and "
     "inconsistent with an Azure-first direction."),
]

_PRIORITY_WEIGHTS = {
    "Exit the data centre on a deadline": dict(
        broadcom_exit=1.4, feature_parity=1.0, vendor_risk=0.6,
        exit_cost=0.5, hardware_impact=1.6,
        exit_speed=2.4, migration_effort=1.4, run_cost=1.2, modernisation=0.7,
        data_residency=0.5, latency_control=0.4, ops_burden=1.0, lock_in=0.6,
        skills_fit=1.0, resilience=1.0, compliance=0.8),
    "Cut total cost of ownership": dict(
        broadcom_exit=1.6, feature_parity=0.8, vendor_risk=0.8,
        exit_cost=1.0, hardware_impact=1.4,
        exit_speed=0.8, migration_effort=1.0, run_cost=2.6, modernisation=1.0,
        data_residency=0.6, latency_control=0.4, ops_burden=1.4, lock_in=0.8,
        skills_fit=1.0, resilience=0.9, compliance=0.7),
    "Escape Broadcom licensing": dict(
        broadcom_exit=3.0, feature_parity=1.0, vendor_risk=1.6,
        exit_cost=1.2, hardware_impact=1.0,
        exit_speed=1.0, migration_effort=1.2, run_cost=2.2, modernisation=0.8,
        data_residency=1.0, latency_control=0.8, ops_burden=1.2, lock_in=1.6,
        skills_fit=1.1, resilience=1.0, compliance=0.9),
    "Data must stay on-premises": dict(
        broadcom_exit=1.4, feature_parity=1.4, vendor_risk=1.0,
        exit_cost=0.8, hardware_impact=1.6,
        exit_speed=0.3, migration_effort=1.2, run_cost=1.4, modernisation=0.9,
        data_residency=2.8, latency_control=2.0, ops_burden=1.2, lock_in=1.0,
        skills_fit=1.2, resilience=1.0, compliance=2.2),
    "Modernise the application estate": dict(
        broadcom_exit=1.2, feature_parity=0.8, vendor_risk=1.0,
        exit_cost=1.0, hardware_impact=0.8,
        exit_speed=0.8, migration_effort=0.7, run_cost=1.4, modernisation=2.6,
        data_residency=0.6, latency_control=0.5, ops_burden=1.6, lock_in=0.7,
        skills_fit=1.0, resilience=1.2, compliance=0.8),
    "Minimise risk and disruption": dict(
        broadcom_exit=0.8, feature_parity=2.2, vendor_risk=1.4,
        exit_cost=0.8, hardware_impact=1.0,
        exit_speed=0.9, migration_effort=2.4, run_cost=1.0, modernisation=0.5,
        data_residency=1.0, latency_control=0.9, ops_burden=1.2, lock_in=0.8,
        skills_fit=1.8, resilience=1.6, compliance=1.2),
    "Regulated / sovereign workload": dict(
        broadcom_exit=1.0, feature_parity=1.6, vendor_risk=1.4,
        exit_cost=0.8, hardware_impact=1.0,
        exit_speed=0.5, migration_effort=1.0, run_cost=1.0, modernisation=0.7,
        data_residency=2.6, latency_control=1.4, ops_burden=1.0, lock_in=1.0,
        skills_fit=1.0, resilience=1.4, compliance=2.8),
    # The source paper's own recommended weighting (its section 3.1): one
    # Critical criterion, six High, six Medium. Offered as a priority so the
    # scorecard can be run the way the paper says to run it, rather than only
    # against a client-stated driver.
    "The paper's recommended weighting": dict(
        broadcom_exit=3.0,
        migration_effort=2.0, ops_burden=2.0, feature_parity=2.0, resilience=2.0,
        compliance=2.0, run_cost=2.0,
        skills_fit=1.0, vendor_risk=1.0, modernisation=1.0, exit_cost=1.0,
        hardware_impact=1.0, exit_speed=1.0,
        data_residency=1.0, latency_control=1.0, lock_in=1.0),
}

# What band the source paper puts each criterion in, for display beside the
# scorecard. Criteria the paper does not list are marked "-- (not in the paper)".
CRITERION_WEIGHT = {
    "broadcom_exit": "Critical",
    "migration_effort": "High", "ops_burden": "High", "feature_parity": "High",
    "resilience": "High", "compliance": "High", "run_cost": "High",
    "skills_fit": "Medium", "vendor_risk": "Medium", "modernisation": "Medium",
    "exit_cost": "Medium", "hardware_impact": "Medium", "exit_speed": "Medium",
    "data_residency": "Added here", "latency_control": "Added here",
    "lock_in": "Added here",
}

PRIORITIES = list(_PRIORITY_WEIGHTS)

# Used when no objective has been stated. The paper's own weighting is the only
# defensible default, because it is the one that does not assume a driver.
DEFAULT_PRIORITY = "The paper's recommended weighting"


def platforms_frame() -> pd.DataFrame:
    rows = []
    for p in _P:
        row = {k: v for k, v in p.items() if k != "scores"}
        row.update(p["scores"])
        rows.append(row)
    return pd.DataFrame(rows)


def rank_platforms(priority: str, custom_weights: dict | None = None) -> pd.DataFrame:
    weights = custom_weights or _PRIORITY_WEIGHTS.get(
        priority) or _PRIORITY_WEIGHTS[DEFAULT_PRIORITY]
    df = platforms_frame()
    total_w = sum(weights.get(c, 0) for c in CRITERIA)
    df["fit_score"] = sum(df[c] * weights.get(c, 0) for c in CRITERIA) / (5.0 * total_w) * 100
    df["fit_score"] = df["fit_score"].round(1)
    return df.sort_values("fit_score", ascending=False).reset_index(drop=True)


# --------------------------------------------------------------------------
# Azure Local cost model -- the on-premises Azure option, priced properly
# --------------------------------------------------------------------------
AZURE_LOCAL_CORE_MONTH = 10.00           # standard
AZURE_LOCAL_CORE_MONTH_EXTERNAL_SAN = 20.10
AZURE_LOCAL_WINDOWS_GUEST_CORE_MONTH = 23.30   # waived by Azure Hybrid Benefit
AZURE_LOCAL_FREE_DAYS = 60


@dataclass
class AzureLocalInputs:
    total_vcpu: int = 1800
    total_ram_gib: float = 14000.0
    provisioned_tib: float = 380.0
    vcpu_per_physical_core: float = 4.0
    cores_per_node: int = 48          # dual 24-core, typical validated Azure Local node
    ram_gib_per_node: float = 1024.0
    node_capex: float = 46000.0
    node_life_years: int = 5
    external_san: bool = False
    apply_hybrid_benefit: bool = True
    windows_share_pct: float = 60.0
    power_kw_per_node: float = 0.75
    power_cost_per_kwh: float = 0.155
    pue: float = 1.5
    support_pct_of_capex: float = 10.0
    ops_fte: float = 3.5
    fte_cost: float = 138000.0


def azure_local_cost(i: AzureLocalInputs) -> dict:
    """Annual cost of landing this estate on Azure Local instead of Azure public cloud."""
    nodes_by_cpu = i.total_vcpu / max(i.vcpu_per_physical_core * i.cores_per_node, 1)
    nodes_by_ram = i.total_ram_gib / max(i.ram_gib_per_node * 0.8, 1)
    nodes = int(np.ceil(max(nodes_by_cpu, nodes_by_ram))) + 1      # N+1
    nodes = max(nodes, 2)
    physical_cores = nodes * i.cores_per_node

    core_rate = AZURE_LOCAL_CORE_MONTH_EXTERNAL_SAN if i.external_san else AZURE_LOCAL_CORE_MONTH
    service_fee = physical_cores * core_rate * 12

    if i.apply_hybrid_benefit:
        windows_guest = 0.0
        ahb_note = ("Azure Hybrid Benefit waives the Windows Server guest-rights charge entirely. "
                    "Without it, this line would be "
                    f"{physical_cores * AZURE_LOCAL_WINDOWS_GUEST_CORE_MONTH * 12:,.0f} per year.")
    else:
        windows_guest = physical_cores * AZURE_LOCAL_WINDOWS_GUEST_CORE_MONTH * 12
        ahb_note = ("No Hybrid Benefit applied. Windows Server guest rights are charged per "
                    "physical core for unlimited guest VMs.")

    hw_amort = nodes * i.node_capex / max(i.node_life_years, 1)
    hw_support = nodes * i.node_capex * i.support_pct_of_capex / 100
    kwh = nodes * i.power_kw_per_node * i.pue * 24 * 365
    power = kwh * i.power_cost_per_kwh
    people = i.ops_fte * i.fte_cost

    lines = [
        ("Azure Local service fee", service_fee,
         f"{physical_cores:,} physical cores x {core_rate:.2f}/core/month"),
        ("Windows Server guest rights", windows_guest, ahb_note),
        ("Node hardware amortisation", hw_amort,
         f"{nodes} validated node(s) x {i.node_capex:,.0f} over {i.node_life_years} years"),
        ("Hardware support", hw_support, f"{i.support_pct_of_capex:.0f}% of capex"),
        ("Power & cooling", power, f"{kwh / 1000:,.0f} MWh/yr at PUE {i.pue}"),
        ("Operations staff", people, f"{i.ops_fte} FTE"),
    ]
    df = pd.DataFrame(lines, columns=["component", "annual_cost", "basis"])
    df = df[df["annual_cost"] > 0].copy()
    df["share_pct"] = df["annual_cost"] / df["annual_cost"].sum() * 100

    return {
        "nodes": nodes,
        "physical_cores": physical_cores,
        "breakdown": df.sort_values("annual_cost", ascending=False),
        "annual_total": float(df["annual_cost"].sum()),
        "monthly_total": float(df["annual_cost"].sum()) / 12,
        "vmware_licence_avoided": True,
        "notes": [
            f"The first {AZURE_LOCAL_FREE_DAYS} days of the Azure Local service fee are free.",
            "Azure Local removes the VMware licence entirely while keeping every workload "
            "on-premises -- it is the direct answer to a residency objection.",
            "Single-node clusters are supported, so branch and edge sites do not need a "
            "two-node minimum.",
            "Migration from ESXi is a real conversion to Hyper-V, not a vMotion. Budget the "
            "same per-VM effort as a rehost to Azure IaaS.",
            "Hardware must come from the Azure Local validated catalogue -- existing VMware "
            "hosts generally cannot be reused.",
        ],
    }


# AVS node specifications (AV36 is the common default; AV64 for denser estates).
AVS_NODES = {
    "AV36":  {"cores": 36, "ram_gib": 576,  "nvme_tib": 15.2, "hourly": 8.50},
    "AV36P": {"cores": 36, "ram_gib": 768,  "nvme_tib": 19.2, "hourly": 10.20},
    "AV52":  {"cores": 52, "ram_gib": 1536, "nvme_tib": 38.4, "hourly": 16.40},
    "AV64":  {"cores": 64, "ram_gib": 1024, "nvme_tib": 30.7, "hourly": 14.20},
}
AVS_MIN_HOSTS = 3
AVS_STORAGE_SLACK = 1.25      # vSAN overhead, FTT=1 and free-space headroom


def size_avs(total_vcpu: int, total_ram_gib: float, used_tib: float,
             node: str = "AV36", vcpu_per_core: float = 4.0,
             ram_utilisation: float = 0.80) -> dict:
    """Number of AVS hosts this estate actually needs.

    AVS is dedicated hardware, so it is sized on the binding constraint of CPU,
    memory and vSAN capacity -- not on VM count. Memory almost always wins.
    """
    spec = AVS_NODES[node]
    by_cpu = total_vcpu / max(vcpu_per_core * spec["cores"], 1)
    by_ram = total_ram_gib / max(spec["ram_gib"] * ram_utilisation, 1)
    by_storage = (used_tib * AVS_STORAGE_SLACK) / spec["nvme_tib"]
    hosts = int(np.ceil(max(by_cpu, by_ram, by_storage)))
    hosts = max(hosts, AVS_MIN_HOSTS)
    driver = max([("CPU", by_cpu), ("Memory", by_ram), ("vSAN capacity", by_storage)],
                 key=lambda x: x[1])[0]
    if hosts == AVS_MIN_HOSTS and max(by_cpu, by_ram, by_storage) < AVS_MIN_HOSTS:
        driver = "Three-host minimum"
    return {"node": node, "hosts": hosts, "spec": spec, "binding_constraint": driver,
            "by_cpu": by_cpu, "by_ram": by_ram, "by_storage": by_storage}


def platform_cost_comparison(azure_public_monthly: float, onprem_vmware_monthly: float,
                             azure_local: dict, avs: dict,
                             vcf_per_core_year: float = 135.0) -> pd.DataFrame:
    """Side-by-side monthly run rate for the shortlisted destinations.

    ``avs`` comes from :func:`size_avs` so the AVS line reflects the hosts this
    estate genuinely needs, not the three-host minimum.
    """
    spec = avs["spec"]
    avs_compute = avs["hosts"] * spec["hourly"] * 730
    # Since November 2025, new AVS nodes require a portable VCF subscription
    # bought from Broadcom -- Microsoft no longer bundles it.
    avs_vcf = avs["hosts"] * spec["cores"] * vcf_per_core_year / 12
    rows = [
        {"platform": "Azure native IaaS (rehost)", "monthly_cost": azure_public_monthly,
         "basis": "Live Azure retail pricing with the selected commercial levers applied"},
        {"platform": "Azure Local (on-premises Azure)", "monthly_cost": azure_local["monthly_total"],
         "basis": f"{azure_local['nodes']} node(s), {azure_local['physical_cores']:,} cores, "
                  "including hardware, power and staff"},
        {"platform": "Azure VMware Solution", "monthly_cost": avs_compute + avs_vcf,
         "basis": f"{avs['hosts']} x {avs['node']} at {spec['hourly']:.2f}/hr "
                  f"(sized by {avs['binding_constraint'].lower()}), plus a separately-purchased "
                  f"VCF subscription at {vcf_per_core_year:,.0f}/core/yr"},
        {"platform": "Stay on VMware on-premises", "monthly_cost": onprem_vmware_monthly,
         "basis": "Current-state TCO including licence, hardware, facilities and staff"},
    ]
    df = pd.DataFrame(rows)
    base = df.loc[df["platform"] == "Stay on VMware on-premises", "monthly_cost"].iloc[0]
    df["vs_stay_pct"] = (df["monthly_cost"] - base) / base * 100 if base else 0
    df["annual_cost"] = df["monthly_cost"] * 12
    return df.sort_values("monthly_cost")
