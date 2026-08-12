"""Right-sizing engine: map each source VM onto an Azure VM SKU and disk set.

Mirrors the two sizing modes Azure Migrate offers:

* **As on-premises** -- allocate whatever the VM was configured with. Safe,
  and what you get when performance data is missing, but it carries the
  full on-premises over-provisioning into the cloud bill.
* **Performance-based** -- size from measured utilisation at a chosen
  percentile, inflated by a comfort factor. This is where the savings are.

The comfort factor and percentile are the same knobs Azure Migrate exposes,
so a number produced here can be reconciled against a real assessment.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from core import azure_catalog as cat


@dataclass
class SizingPolicy:
    mode: str = "performance"          # "performance" | "as-provisioned"
    percentile: str = "p95"            # p50 | p90 | p95 | p99  (Azure Migrate default: p95)
    comfort_factor: float = 1.3        # Azure Migrate default: 1.3x
    generations: tuple[int, ...] = (5,)
    allow_burstable: bool = True
    burstable_max_cpu_pct: float = 15.0     # only burst-size genuinely idle VMs
    burstable_max_vcpu: int = 8
    prefer_amd: bool = False           # AMD sizes are typically ~10% cheaper
    min_vcpu: int = 2
    storage_policy: str = "performance-matched"   # or "all-premium" | "cost-optimised"
    size_disks_to_used: bool = False   # shrink to consumed rather than provisioned
    include_families: tuple[str, ...] = ("burstable", "general", "compute", "memory", "hpc-memory")


PERCENTILE_COLS = {
    "p50": ("cpu_avg_pct", "mem_avg_pct"),
    "p90": ("cpu_p95_pct", "mem_p95_pct"),
    "p95": ("cpu_p95_pct", "mem_p95_pct"),
    "p99": ("cpu_p95_pct", "mem_p95_pct"),
}
# Scale factor applied to the p95 column to approximate other percentiles when
# only avg/p95 counters are available (the common RVTools + vCenter case).
PERCENTILE_SCALE = {"p50": 1.0, "p90": 0.92, "p95": 1.0, "p99": 1.12}


def required_capacity(df: pd.DataFrame, policy: SizingPolicy) -> pd.DataFrame:
    """Compute the vCPU / RAM each VM actually needs under the policy."""
    out = pd.DataFrame(index=df.index)
    if policy.mode == "as-provisioned":
        out["req_vcpu"] = df["vcpu"].astype(float)
        out["req_ram_gib"] = df["ram_gib"].astype(float)
        out["sizing_basis"] = "as-provisioned"
        return out

    cpu_col, mem_col = PERCENTILE_COLS[policy.percentile]
    scale = PERCENTILE_SCALE[policy.percentile]
    cpu_pct = pd.to_numeric(df[cpu_col], errors="coerce") * scale
    mem_pct = pd.to_numeric(df[mem_col], errors="coerce") * scale

    # Missing counters -> fall back to as-provisioned for that VM only.
    missing = cpu_pct.isna() | mem_pct.isna()

    req_vcpu = df["vcpu"] * (cpu_pct / 100.0) * policy.comfort_factor
    req_ram = df["ram_gib"] * (mem_pct / 100.0) * policy.comfort_factor

    out["req_vcpu"] = np.where(missing, df["vcpu"], np.maximum(req_vcpu, policy.min_vcpu))
    # Never size RAM below 1 GiB or below 25% of allocated -- guests page badly
    # when memory is cut aggressively, and Azure Migrate applies a similar floor.
    out["req_ram_gib"] = np.where(
        missing, df["ram_gib"], np.maximum(req_ram, np.maximum(1.0, df["ram_gib"] * 0.25)))
    out["sizing_basis"] = np.where(missing, "as-provisioned (no perf data)",
                                   f"performance {policy.percentile} x{policy.comfort_factor:g}")
    return out


def _candidate_skus(policy: SizingPolicy) -> pd.DataFrame:
    df = cat.sku_frame(generations=policy.generations, families=policy.include_families)
    if not policy.allow_burstable:
        df = df[df["family"] != "burstable"]
    if policy.prefer_amd:
        # Sort key that puts AMD ("as") sizes ahead of Intel at equal capacity.
        df = df.assign(_amd=df["arm_name"].str.contains("as_v"))
    else:
        df = df.assign(_amd=~df["arm_name"].str.contains("as_v"))
    return df.sort_values(["vcpu", "ram_gib", "_amd"], ascending=[True, True, False])


def select_sku(req_vcpu: float, req_ram: float, data_disks: int, nics: int,
               cpu_avg: float, candidates: pd.DataFrame,
               policy: SizingPolicy) -> tuple[str, str, int, float, str]:
    """Cheapest-by-capacity SKU that satisfies vCPU, RAM, disk-count and NIC limits.

    Returns ``(arm_name, series, vcpu, ram_gib, rationale)``.
    """
    pool = candidates
    burstable_ok = (policy.allow_burstable
                    and not np.isnan(cpu_avg)
                    and cpu_avg <= policy.burstable_max_cpu_pct
                    and req_vcpu <= policy.burstable_max_vcpu)
    if not burstable_ok:
        pool = pool[pool["family"] != "burstable"]

    fits = pool[(pool["vcpu"] >= np.ceil(req_vcpu))
                & (pool["ram_gib"] >= req_ram)
                & (pool["max_data_disks"] >= data_disks)
                & (pool["max_nics"] >= nics)]
    if fits.empty:
        # Nothing in the preferred pool: widen to the whole catalog.
        allsku = cat.sku_frame(generations=(5, 6))
        fits = allsku[(allsku["vcpu"] >= np.ceil(req_vcpu))
                      & (allsku["ram_gib"] >= req_ram)
                      & (allsku["max_data_disks"] >= data_disks)]
        if fits.empty:
            biggest = allsku.sort_values(["ram_gib", "vcpu"]).iloc[-1]
            return (biggest["arm_name"], biggest["series"], int(biggest["vcpu"]),
                    float(biggest["ram_gib"]),
                    "Exceeds the largest available Azure VM size -- must be split or re-architected")

    # Among sizes that fit, prefer the one with the least wasted capacity.
    fits = fits.assign(
        waste=(fits["vcpu"] - req_vcpu) / fits["vcpu"] + (fits["ram_gib"] - req_ram) / fits["ram_gib"]
    ).sort_values(["vcpu", "ram_gib", "waste"])
    best = fits.iloc[0]
    reason = f"{best['family']} ({best['series']}) fits {req_vcpu:.1f} vCPU / {req_ram:.1f} GiB"
    if best["family"] == "burstable":
        reason += " -- burstable: sustained CPU is low enough for credit-based sizing"
    return (best["arm_name"], best["series"], int(best["vcpu"]), float(best["ram_gib"]), reason)


def size_disks(row: pd.Series, policy: SizingPolicy) -> dict:
    """Choose managed-disk tiers for the OS disk and the data disks."""
    if policy.storage_policy == "all-premium":
        kind_os = kind_data = "Premium SSD"
    elif policy.storage_policy == "cost-optimised":
        kind_os = "Standard SSD"
        kind_data = "Standard SSD"
    else:  # performance-matched
        iops = float(row.get("iops_avg") or 0)
        peak = float(row.get("iops_peak") or 0)
        is_prod = bool(row.get("is_prod", True))
        kind_os = "Premium SSD" if is_prod else "Standard SSD"
        if peak > 500 or iops > 200 or row.get("tier") == "Database":
            kind_data = "Premium SSD"
        elif is_prod:
            kind_data = "Standard SSD"
        else:
            kind_data = "Standard HDD"

    os_size = float(row["os_disk_gib"])
    os_tier = cat.pick_disk_tier(os_size, kind_os)

    n_data = int(row["data_disk_count"])
    total_data = float(row["data_disk_gib"])
    if policy.size_disks_to_used and pd.notna(row.get("used_gib")):
        consumed_ratio = float(row["used_gib"]) / max(float(row["provisioned_gib"]), 1.0)
        total_data = total_data * min(max(consumed_ratio, 0.4), 1.0)

    data_tiers: list[str] = []
    data_gib_alloc = 0.0
    if n_data > 0 and total_data > 0:
        per_disk = total_data / n_data
        # Spread required IOPS across the data disks.
        per_disk_iops = float(row.get("iops_peak") or 0) / max(n_data, 1)
        for _ in range(n_data):
            t = cat.pick_disk_tier(per_disk, kind_data, iops=per_disk_iops)
            data_tiers.append(t.tier)
            data_gib_alloc += t.size_gib
    return {
        "os_disk_tier": os_tier.tier,
        "os_disk_kind": kind_os,
        "os_disk_alloc_gib": float(os_tier.size_gib),
        "data_disk_tiers": ",".join(data_tiers),
        "data_disk_kind": kind_data if data_tiers else "",
        "data_disk_alloc_gib": data_gib_alloc,
        "total_alloc_gib": float(os_tier.size_gib) + data_gib_alloc,
    }


def rightsize(df: pd.DataFrame, policy: SizingPolicy) -> pd.DataFrame:
    """Full right-sizing pass. Returns the inventory with Azure target columns added."""
    req = required_capacity(df, policy)
    candidates = _candidate_skus(policy)

    picks = []
    for idx, row in df.iterrows():
        cpu_avg = pd.to_numeric(pd.Series([row.get("cpu_avg_pct")]), errors="coerce").iloc[0]
        arm, series, vcpu, ram, reason = select_sku(
            float(req.at[idx, "req_vcpu"]), float(req.at[idx, "req_ram_gib"]),
            int(row["data_disk_count"]), int(row.get("nic_count", 1)),
            float(cpu_avg) if pd.notna(cpu_avg) else float("nan"),
            candidates, policy,
        )
        disks = size_disks(row, policy)
        picks.append({
            "azure_sku": arm, "azure_series": series,
            "azure_vcpu": vcpu, "azure_ram_gib": ram, "sku_rationale": reason, **disks,
        })

    out = pd.concat([df.reset_index(drop=True),
                     req.reset_index(drop=True),
                     pd.DataFrame(picks)], axis=1)

    out["vcpu_reduction_pct"] = (1 - out["azure_vcpu"] / out["vcpu"].clip(lower=1)) * 100
    out["ram_reduction_pct"] = (1 - out["azure_ram_gib"] / out["ram_gib"].clip(lower=1)) * 100
    return out


def sizing_delta_summary(sized: pd.DataFrame) -> dict:
    """Portfolio-level view of what right-sizing harvested."""
    return {
        "source_vcpu": int(sized["vcpu"].sum()),
        "target_vcpu": int(sized["azure_vcpu"].sum()),
        "vcpu_saved_pct": float((1 - sized["azure_vcpu"].sum() / max(sized["vcpu"].sum(), 1)) * 100),
        "source_ram_tib": float(sized["ram_gib"].sum() / 1024),
        "target_ram_tib": float(sized["azure_ram_gib"].sum() / 1024),
        "ram_saved_pct": float((1 - sized["azure_ram_gib"].sum() / max(sized["ram_gib"].sum(), 1)) * 100),
        "source_storage_tib": float(sized["provisioned_gib"].sum() / 1024),
        "target_storage_tib": float(sized["total_alloc_gib"].sum() / 1024),
        "burstable_count": int(sized["azure_series"].str.startswith("Bsv").sum()),
        "distinct_skus": int(sized["azure_sku"].nunique()),
        "upsized_count": int((sized["azure_vcpu"] > sized["vcpu"]).sum()),
    }
