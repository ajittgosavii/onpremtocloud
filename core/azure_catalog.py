"""Azure target catalog: VM SKUs, managed disk tiers, regions and platform limits.

Sizes/limits reflect the published Azure VM series specs. The catalog is the
right-sizing search space; live unit prices come from core.pricing (Azure Retail
Prices API) and are joined onto these rows by ``arm_name``.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Literal

import pandas as pd

Family = Literal["burstable", "general", "compute", "memory", "storage", "hpc-memory"]


@dataclass(frozen=True)
class VmSku:
    arm_name: str          # e.g. Standard_D4s_v5 -- join key for the pricing API
    series: str            # e.g. Dsv5
    family: Family
    vcpu: int
    ram_gib: float
    max_data_disks: int
    max_nics: int
    temp_disk_gib: int     # 0 = no local temp disk (v5/v6 "s" sizes)
    premium_io: bool
    generation: int        # 5 or 6 -- lets the user bias toward newer silicon
    cpu: str               # marketing name, shown in the UI
    notes: str = ""


def _s(arm, series, fam, vcpu, ram, disks, nics, temp, gen, cpu, notes=""):
    return VmSku(arm, series, fam, vcpu, ram, disks, nics, temp, True, gen, cpu, notes)


# --------------------------------------------------------------------------
# B-series (burstable) -- credit-based CPU. Excellent fit for the long tail of
# idle VMware VMs, which is typically 30-45% of a legacy estate.
# --------------------------------------------------------------------------
_B = [
    _s("Standard_B1s",   "Bsv1", "burstable", 1,   1,  2, 2,  4, 5, "Intel/AMD burstable", "10% baseline"),
    _s("Standard_B1ms",  "Bsv1", "burstable", 1,   2,  2, 2,  4, 5, "Intel/AMD burstable", "20% baseline"),
    _s("Standard_B2s",   "Bsv1", "burstable", 2,   4,  4, 3,  8, 5, "Intel/AMD burstable", "40% baseline"),
    _s("Standard_B2ms",  "Bsv1", "burstable", 2,   8,  4, 3, 16, 5, "Intel/AMD burstable", "60% baseline"),
    _s("Standard_B4ms",  "Bsv1", "burstable", 4,  16,  8, 4, 32, 5, "Intel/AMD burstable", "90% baseline"),
    _s("Standard_B8ms",  "Bsv1", "burstable", 8,  32, 16, 4, 64, 5, "Intel/AMD burstable", "135% baseline"),
    _s("Standard_B12ms", "Bsv1", "burstable", 12, 48, 16, 6, 96, 5, "Intel/AMD burstable", "202% baseline"),
    _s("Standard_B16ms", "Bsv1", "burstable", 16, 64, 32, 8, 128, 5, "Intel/AMD burstable", "270% baseline"),
    _s("Standard_B20ms", "Bsv1", "burstable", 20, 80, 32, 8, 160, 5, "Intel/AMD burstable", "337% baseline"),
]

# --------------------------------------------------------------------------
# General purpose 4 GiB/vCPU -- the default landing zone for most rehosts.
# --------------------------------------------------------------------------
_DSV5 = [
    _s("Standard_D2s_v5",  "Dsv5", "general", 2,    8,  4, 2, 0, 5, "Intel Ice Lake"),
    _s("Standard_D4s_v5",  "Dsv5", "general", 4,   16,  8, 2, 0, 5, "Intel Ice Lake"),
    _s("Standard_D8s_v5",  "Dsv5", "general", 8,   32, 16, 4, 0, 5, "Intel Ice Lake"),
    _s("Standard_D16s_v5", "Dsv5", "general", 16,  64, 32, 8, 0, 5, "Intel Ice Lake"),
    _s("Standard_D32s_v5", "Dsv5", "general", 32, 128, 32, 8, 0, 5, "Intel Ice Lake"),
    _s("Standard_D48s_v5", "Dsv5", "general", 48, 192, 32, 8, 0, 5, "Intel Ice Lake"),
    _s("Standard_D64s_v5", "Dsv5", "general", 64, 256, 32, 8, 0, 5, "Intel Ice Lake"),
    _s("Standard_D96s_v5", "Dsv5", "general", 96, 384, 32, 8, 0, 5, "Intel Ice Lake"),
]
_DASV5 = [
    _s("Standard_D2as_v5",  "Dasv5", "general", 2,    8,  4, 2, 0, 5, "AMD EPYC Milan"),
    _s("Standard_D4as_v5",  "Dasv5", "general", 4,   16,  8, 2, 0, 5, "AMD EPYC Milan"),
    _s("Standard_D8as_v5",  "Dasv5", "general", 8,   32, 16, 4, 0, 5, "AMD EPYC Milan"),
    _s("Standard_D16as_v5", "Dasv5", "general", 16,  64, 32, 8, 0, 5, "AMD EPYC Milan"),
    _s("Standard_D32as_v5", "Dasv5", "general", 32, 128, 32, 8, 0, 5, "AMD EPYC Milan"),
    _s("Standard_D48as_v5", "Dasv5", "general", 48, 192, 32, 8, 0, 5, "AMD EPYC Milan"),
    _s("Standard_D64as_v5", "Dasv5", "general", 64, 256, 32, 8, 0, 5, "AMD EPYC Milan"),
    _s("Standard_D96as_v5", "Dasv5", "general", 96, 384, 32, 8, 0, 5, "AMD EPYC Milan"),
]
_DSV6 = [
    _s("Standard_D2s_v6",  "Dsv6", "general", 2,    8,  4, 2, 0, 6, "Intel Emerald Rapids"),
    _s("Standard_D4s_v6",  "Dsv6", "general", 4,   16,  8, 2, 0, 6, "Intel Emerald Rapids"),
    _s("Standard_D8s_v6",  "Dsv6", "general", 8,   32, 16, 4, 0, 6, "Intel Emerald Rapids"),
    _s("Standard_D16s_v6", "Dsv6", "general", 16,  64, 32, 8, 0, 6, "Intel Emerald Rapids"),
    _s("Standard_D32s_v6", "Dsv6", "general", 32, 128, 32, 8, 0, 6, "Intel Emerald Rapids"),
    _s("Standard_D48s_v6", "Dsv6", "general", 48, 192, 32, 8, 0, 6, "Intel Emerald Rapids"),
    _s("Standard_D64s_v6", "Dsv6", "general", 64, 256, 32, 8, 0, 6, "Intel Emerald Rapids"),
    _s("Standard_D96s_v6", "Dsv6", "general", 96, 384, 32, 8, 0, 6, "Intel Emerald Rapids"),
]
_DASV6 = [
    _s("Standard_D2as_v6",  "Dasv6", "general", 2,    8,  4, 2, 0, 6, "AMD EPYC Genoa"),
    _s("Standard_D4as_v6",  "Dasv6", "general", 4,   16,  8, 2, 0, 6, "AMD EPYC Genoa"),
    _s("Standard_D8as_v6",  "Dasv6", "general", 8,   32, 16, 4, 0, 6, "AMD EPYC Genoa"),
    _s("Standard_D16as_v6", "Dasv6", "general", 16,  64, 32, 8, 0, 6, "AMD EPYC Genoa"),
    _s("Standard_D32as_v6", "Dasv6", "general", 32, 128, 32, 8, 0, 6, "AMD EPYC Genoa"),
    _s("Standard_D48as_v6", "Dasv6", "general", 48, 192, 32, 8, 0, 6, "AMD EPYC Genoa"),
    _s("Standard_D64as_v6", "Dasv6", "general", 64, 256, 32, 8, 0, 6, "AMD EPYC Genoa"),
    _s("Standard_D96as_v6", "Dasv6", "general", 96, 384, 32, 8, 0, 6, "AMD EPYC Genoa"),
]

# --------------------------------------------------------------------------
# Memory optimised 8 GiB/vCPU -- SQL Server, SAP app servers, Java heaps.
# --------------------------------------------------------------------------
_ESV5 = [
    _s("Standard_E2s_v5",   "Esv5", "memory", 2,    16,  4, 2, 0, 5, "Intel Ice Lake"),
    _s("Standard_E4s_v5",   "Esv5", "memory", 4,    32,  8, 2, 0, 5, "Intel Ice Lake"),
    _s("Standard_E8s_v5",   "Esv5", "memory", 8,    64, 16, 4, 0, 5, "Intel Ice Lake"),
    _s("Standard_E16s_v5",  "Esv5", "memory", 16,  128, 32, 8, 0, 5, "Intel Ice Lake"),
    _s("Standard_E20s_v5",  "Esv5", "memory", 20,  160, 32, 8, 0, 5, "Intel Ice Lake"),
    _s("Standard_E32s_v5",  "Esv5", "memory", 32,  256, 32, 8, 0, 5, "Intel Ice Lake"),
    _s("Standard_E48s_v5",  "Esv5", "memory", 48,  384, 32, 8, 0, 5, "Intel Ice Lake"),
    _s("Standard_E64s_v5",  "Esv5", "memory", 64,  512, 32, 8, 0, 5, "Intel Ice Lake"),
    _s("Standard_E96s_v5",  "Esv5", "memory", 96,  672, 32, 8, 0, 5, "Intel Ice Lake"),
    _s("Standard_E104is_v5", "Esv5", "memory", 104, 672, 64, 8, 0, 5, "Intel Ice Lake", "isolated"),
]
_EASV5 = [
    _s("Standard_E2as_v5",  "Easv5", "memory", 2,   16,  4, 2, 0, 5, "AMD EPYC Milan"),
    _s("Standard_E4as_v5",  "Easv5", "memory", 4,   32,  8, 2, 0, 5, "AMD EPYC Milan"),
    _s("Standard_E8as_v5",  "Easv5", "memory", 8,   64, 16, 4, 0, 5, "AMD EPYC Milan"),
    _s("Standard_E16as_v5", "Easv5", "memory", 16, 128, 32, 8, 0, 5, "AMD EPYC Milan"),
    _s("Standard_E20as_v5", "Easv5", "memory", 20, 160, 32, 8, 0, 5, "AMD EPYC Milan"),
    _s("Standard_E32as_v5", "Easv5", "memory", 32, 256, 32, 8, 0, 5, "AMD EPYC Milan"),
    _s("Standard_E48as_v5", "Easv5", "memory", 48, 384, 32, 8, 0, 5, "AMD EPYC Milan"),
    _s("Standard_E64as_v5", "Easv5", "memory", 64, 512, 32, 8, 0, 5, "AMD EPYC Milan"),
    _s("Standard_E96as_v5", "Easv5", "memory", 96, 672, 32, 8, 0, 5, "AMD EPYC Milan"),
]
_ESV6 = [
    _s("Standard_E2s_v6",  "Esv6", "memory", 2,   16,  4, 2, 0, 6, "Intel Emerald Rapids"),
    _s("Standard_E4s_v6",  "Esv6", "memory", 4,   32,  8, 2, 0, 6, "Intel Emerald Rapids"),
    _s("Standard_E8s_v6",  "Esv6", "memory", 8,   64, 16, 4, 0, 6, "Intel Emerald Rapids"),
    _s("Standard_E16s_v6", "Esv6", "memory", 16, 128, 32, 8, 0, 6, "Intel Emerald Rapids"),
    _s("Standard_E32s_v6", "Esv6", "memory", 32, 256, 32, 8, 0, 6, "Intel Emerald Rapids"),
    _s("Standard_E48s_v6", "Esv6", "memory", 48, 384, 32, 8, 0, 6, "Intel Emerald Rapids"),
    _s("Standard_E64s_v6", "Esv6", "memory", 64, 512, 32, 8, 0, 6, "Intel Emerald Rapids"),
    _s("Standard_E96s_v6", "Esv6", "memory", 96, 672, 32, 8, 0, 6, "Intel Emerald Rapids"),
]

# --------------------------------------------------------------------------
# Compute optimised 2 GiB/vCPU -- web front ends, batch, app tiers.
# --------------------------------------------------------------------------
_FSV2 = [
    _s("Standard_F2s_v2",  "Fsv2", "compute", 2,    4,  4, 2,  16, 5, "Intel Cascade Lake"),
    _s("Standard_F4s_v2",  "Fsv2", "compute", 4,    8,  8, 2,  32, 5, "Intel Cascade Lake"),
    _s("Standard_F8s_v2",  "Fsv2", "compute", 8,   16, 16, 4,  64, 5, "Intel Cascade Lake"),
    _s("Standard_F16s_v2", "Fsv2", "compute", 16,  32, 32, 4, 128, 5, "Intel Cascade Lake"),
    _s("Standard_F32s_v2", "Fsv2", "compute", 32,  64, 32, 8, 256, 5, "Intel Cascade Lake"),
    _s("Standard_F48s_v2", "Fsv2", "compute", 48,  96, 32, 8, 384, 5, "Intel Cascade Lake"),
    _s("Standard_F64s_v2", "Fsv2", "compute", 64, 128, 32, 8, 512, 5, "Intel Cascade Lake"),
    _s("Standard_F72s_v2", "Fsv2", "compute", 72, 144, 32, 8, 576, 5, "Intel Cascade Lake"),
]

# --------------------------------------------------------------------------
# Storage optimised (local NVMe) and very-large-memory sizes.
# --------------------------------------------------------------------------
_LSV3 = [
    _s("Standard_L8s_v3",  "Lsv3", "storage", 8,   64, 16, 4, 1920, 5, "Intel Ice Lake", "1x1.92TB NVMe"),
    _s("Standard_L16s_v3", "Lsv3", "storage", 16, 128, 32, 8, 3840, 5, "Intel Ice Lake", "2x1.92TB NVMe"),
    _s("Standard_L32s_v3", "Lsv3", "storage", 32, 256, 32, 8, 7680, 5, "Intel Ice Lake", "4x1.92TB NVMe"),
    _s("Standard_L48s_v3", "Lsv3", "storage", 48, 384, 32, 8, 11520, 5, "Intel Ice Lake", "6x1.92TB NVMe"),
    _s("Standard_L64s_v3", "Lsv3", "storage", 64, 512, 32, 8, 15360, 5, "Intel Ice Lake", "8x1.92TB NVMe"),
    _s("Standard_L80s_v3", "Lsv3", "storage", 80, 640, 32, 8, 19200, 5, "Intel Ice Lake", "10x1.92TB NVMe"),
]
_MSV2 = [
    _s("Standard_M32ms_v2",  "Msv2", "hpc-memory", 32,   875, 64, 8, 0, 5, "Intel Cascade Lake"),
    _s("Standard_M64s_v2",   "Msv2", "hpc-memory", 64,  1024, 64, 8, 0, 5, "Intel Cascade Lake"),
    _s("Standard_M64ms_v2",  "Msv2", "hpc-memory", 64,  1792, 64, 8, 0, 5, "Intel Cascade Lake"),
    _s("Standard_M128s_v2",  "Msv2", "hpc-memory", 128, 2048, 64, 8, 0, 5, "Intel Cascade Lake"),
    _s("Standard_M128ms_v2", "Msv2", "hpc-memory", 128, 3892, 64, 8, 0, 5, "Intel Cascade Lake"),
    _s("Standard_M192is_v2", "Msv2", "hpc-memory", 192, 2048, 64, 8, 0, 5, "Intel Cascade Lake"),
    _s("Standard_M192ims_v2", "Msv2", "hpc-memory", 192, 4096, 64, 8, 0, 5, "Intel Cascade Lake"),
]

ALL_SKUS: list[VmSku] = (
    _B + _DSV5 + _DASV5 + _DSV6 + _DASV6
    + _ESV5 + _EASV5 + _ESV6 + _FSV2 + _LSV3 + _MSV2
)

# Absolute platform ceilings, used by the readiness engine.
MAX_VCPU = 192
MAX_RAM_GIB = 4096
MAX_DISK_GIB = 32767          # single managed disk ceiling (~32 TiB)
MAX_DATA_DISKS = 64
MAX_NICS = 8


def sku_frame(generations: tuple[int, ...] = (5, 6),
              families: tuple[str, ...] | None = None) -> pd.DataFrame:
    """Catalog as a DataFrame, optionally filtered to allowed generations/families."""
    df = pd.DataFrame([asdict(s) for s in ALL_SKUS])
    df = df[df["generation"].isin(generations)]
    if families:
        df = df[df["family"].isin(families)]
    return df.sort_values(["vcpu", "ram_gib", "arm_name"]).reset_index(drop=True)


# --------------------------------------------------------------------------
# Managed disks
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class DiskTier:
    tier: str            # P30 / E30 / S30
    kind: str            # Premium SSD | Standard SSD | Standard HDD
    size_gib: int
    iops: int
    mbps: int


_CAPS = [4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384, 32767]
_CODES = ["1", "2", "3", "4", "6", "10", "15", "20", "30", "40", "50", "60", "70", "80"]
_P_IOPS = [120, 120, 120, 120, 240, 500, 1100, 2300, 5000, 7500, 7500, 16000, 18000, 20000]
_P_MBPS = [25, 25, 25, 25, 50, 100, 125, 150, 200, 250, 250, 500, 750, 900]
_E_IOPS = [120, 120, 120, 500, 500, 500, 500, 500, 500, 500, 500, 2000, 4000, 6000]
_E_MBPS = [25, 25, 25, 60, 60, 60, 60, 60, 60, 60, 60, 400, 600, 750]
_S_IOPS = [500] * 11 + [1300, 2000, 2000]
_S_MBPS = [60] * 11 + [300, 500, 500]

PREMIUM_TIERS = [DiskTier(f"P{c}", "Premium SSD", s, i, m)
                 for c, s, i, m in zip(_CODES, _CAPS, _P_IOPS, _P_MBPS)]
STANDARD_SSD_TIERS = [DiskTier(f"E{c}", "Standard SSD", s, i, m)
                      for c, s, i, m in zip(_CODES, _CAPS, _E_IOPS, _E_MBPS)]
# Standard HDD starts at S4 -- there is no S1/S2/S3.
STANDARD_HDD_TIERS = [DiskTier(f"S{c}", "Standard HDD", s, i, m)
                      for c, s, i, m in zip(_CODES[3:], _CAPS[3:], _S_IOPS[3:], _S_MBPS[3:])]

DISK_KINDS = {
    "Premium SSD": PREMIUM_TIERS,
    "Standard SSD": STANDARD_SSD_TIERS,
    "Standard HDD": STANDARD_HDD_TIERS,
}

# Premium SSD v2 is billed by provisioned GiB + IOPS above 3,000 + MB/s above 125.
PSSD_V2_FREE_IOPS = 3000
PSSD_V2_FREE_MBPS = 125


def pick_disk_tier(size_gib: float, kind: str, iops: float = 0, mbps: float = 0) -> DiskTier:
    """Smallest tier of ``kind`` that satisfies capacity and, where possible, IOPS/throughput."""
    tiers = DISK_KINDS[kind]
    fits = [t for t in tiers if t.size_gib >= size_gib]
    if not fits:
        return tiers[-1]
    perf = [t for t in fits if t.iops >= iops and t.mbps >= mbps]
    return (perf or fits)[0]


# --------------------------------------------------------------------------
# Regions -- the subset an APAC/EMEA/NA enterprise realistically shortlists.
# ``dr_pair`` is the Azure-published regional pair used for the DR estimate.
# --------------------------------------------------------------------------
REGIONS: dict[str, dict] = {
    "eastus":        {"label": "East US (Virginia)",        "geo": "United States", "dr_pair": "westus"},
    "eastus2":       {"label": "East US 2 (Virginia)",      "geo": "United States", "dr_pair": "centralus"},
    "westus2":       {"label": "West US 2 (Washington)",    "geo": "United States", "dr_pair": "westcentralus"},
    "westus3":       {"label": "West US 3 (Arizona)",       "geo": "United States", "dr_pair": "eastus"},
    "centralus":     {"label": "Central US (Iowa)",         "geo": "United States", "dr_pair": "eastus2"},
    "southcentralus": {"label": "South Central US (Texas)", "geo": "United States", "dr_pair": "northcentralus"},
    "canadacentral": {"label": "Canada Central (Toronto)",  "geo": "Canada", "dr_pair": "canadaeast"},
    "northeurope":   {"label": "North Europe (Ireland)",    "geo": "Europe", "dr_pair": "westeurope"},
    "westeurope":    {"label": "West Europe (Netherlands)", "geo": "Europe", "dr_pair": "northeurope"},
    "uksouth":       {"label": "UK South (London)",         "geo": "United Kingdom", "dr_pair": "ukwest"},
    "swedencentral": {"label": "Sweden Central (Gavle)",    "geo": "Europe", "dr_pair": "swedensouth"},
    "germanywestcentral": {"label": "Germany West Central (Frankfurt)", "geo": "Germany", "dr_pair": "germanynorth"},
    "uaenorth":      {"label": "UAE North (Dubai)",         "geo": "UAE", "dr_pair": "uaecentral"},
    "centralindia":  {"label": "Central India (Pune)",      "geo": "India", "dr_pair": "southindia"},
    "southindia":    {"label": "South India (Chennai)",     "geo": "India", "dr_pair": "centralindia"},
    "southeastasia": {"label": "Southeast Asia (Singapore)", "geo": "Asia Pacific", "dr_pair": "eastasia"},
    "eastasia":      {"label": "East Asia (Hong Kong)",     "geo": "Asia Pacific", "dr_pair": "southeastasia"},
    "japaneast":     {"label": "Japan East (Tokyo)",        "geo": "Japan", "dr_pair": "japanwest"},
    "australiaeast": {"label": "Australia East (Sydney)",   "geo": "Australia", "dr_pair": "australiasoutheast"},
    "brazilsouth":   {"label": "Brazil South (Sao Paulo)",  "geo": "Brazil", "dr_pair": "southcentralus"},
}

CURRENCIES = ["USD", "EUR", "GBP", "AUD", "CAD", "INR", "JPY", "CHF", "SEK", "BRL", "DKK", "NOK", "NZD", "KRW", "TWD"]

HOURS_PER_MONTH = 730.0
