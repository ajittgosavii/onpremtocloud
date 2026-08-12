"""Azure run-cost engine.

Joins the right-sized estate onto live Azure Retail Prices and produces a
per-VM and portfolio monthly run rate, with the commercial levers that actually
move the number:

* Azure Hybrid Benefit (removes the Windows Server licence component)
* Reserved Instances (1yr / 3yr) and Azure savings plan for compute
* Non-production scheduling (power off outside business hours)
* Storage tier choice
* Backup, DR, egress and platform overhead
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from core import azure_catalog as cat
from core import pricing

HOURS = cat.HOURS_PER_MONTH


@dataclass
class CommercialPolicy:
    region: str = "eastus"
    currency: str = "USD"
    # Commitment: none | ri-1y | ri-3y | sp-1y | sp-3y
    commitment: str = "ri-3y"
    commitment_coverage_pct: float = 75.0   # share of prod hours under commitment
    apply_ahb_windows: bool = True
    ahb_coverage_pct: float = 100.0         # share of Windows VMs with eligible SA
    # Non-production scheduling
    nonprod_schedule: bool = True
    nonprod_hours_per_week: float = 55.0    # 11h x 5d
    # Storage / protection
    backup_enabled: bool = True
    backup_retention_gb_multiplier: float = 1.6   # vault footprint vs source used GB
    backup_redundancy: str = "GRS"
    dr_enabled: bool = False
    dr_coverage: str = "Tier 0 + Tier 1"    # which criticality bands get ASR
    # Network
    monthly_egress_gb: float = 2000.0
    # Platform overhead as a % uplift (hub network, firewall, bastion, Log Analytics,
    # Defender, management VMs). Applied to the compute+storage subtotal.
    platform_overhead_pct: float = 9.0
    # Enterprise Agreement / CSP discount off retail, if the client has one.
    negotiated_discount_pct: float = 0.0


@dataclass
class PriceBook:
    vm: pd.DataFrame
    disk: pd.DataFrame
    ri: pd.DataFrame
    sp: pd.DataFrame
    egress_gb: float
    backup: dict
    asr_instance: float
    source: str = "live"
    fetched_at: float = 0.0
    notes: list[str] = field(default_factory=list)


def load_price_book(region: str, currency: str = "USD", live: bool = True) -> PriceBook:
    """Fetch every meter the cost engine needs. Falls back to cache on failure."""
    notes: list[str] = []
    vm = pricing.vm_prices(region, currency, live=live)
    disk = pricing.disk_prices(region, currency, live=live)
    try:
        ri = pricing.vm_reservation_prices(region, currency, live=live)
    except Exception as exc:
        ri = pd.DataFrame(columns=["arm_sku_name", "ri_1y_hr", "ri_3y_hr"])
        notes.append(f"Reserved Instance rates unavailable ({exc}); commitment modelling disabled.")
    try:
        sp = pricing.vm_savings_plan_prices(region, currency, live=live)
    except Exception:
        sp = pd.DataFrame(columns=["arm_sku_name", "sp_1y_hr", "sp_3y_hr"])
    return PriceBook(
        vm=vm, disk=disk, ri=ri, sp=sp,
        egress_gb=pricing.egress_price(region, currency, live=live),
        backup=pricing.backup_price(region, currency, live=live),
        asr_instance=pricing.site_recovery_price(currency, live=live),
        source=str(vm.attrs.get("source", "live")),
        fetched_at=float(vm.attrs.get("fetched_at", 0.0)),
        notes=notes,
    )


def _disk_price_lookup(disk: pd.DataFrame) -> dict[tuple[str, str], float]:
    return {(r["kind"], r["tier"]): float(r["price_month"]) for _, r in disk.iterrows()}


def _disk_cost(row: pd.Series, lut: dict) -> float:
    total = lut.get((row["os_disk_kind"], row["os_disk_tier"]), 0.0)
    tiers = str(row.get("data_disk_tiers") or "")
    if tiers:
        kind = row["data_disk_kind"]
        for t in tiers.split(","):
            if t:
                total += lut.get((kind, t), 0.0)
    return total


def _backup_cost(row: pd.Series, pol: CommercialPolicy, pb: PriceBook) -> float:
    if not pol.backup_enabled:
        return 0.0
    used = float(row.get("used_gib") or row.get("provisioned_gib") or 0)
    # Azure charges the protected-instance fee once per 500 GB block (min one).
    blocks = max(1, int(np.ceil(used / 500.0)))
    is_sql = str(row.get("db_engine")) == "Microsoft SQL Server"
    unit = pb.backup["sql_instance_month"] if is_sql else pb.backup["instance_month"]
    instance_fee = unit * blocks
    rate = pb.backup["grs_gb_month"] if pol.backup_redundancy == "GRS" else pb.backup["lrs_gb_month"]
    vault_gb = used * pol.backup_retention_gb_multiplier
    return instance_fee + vault_gb * rate


def _dr_applies(row: pd.Series, pol: CommercialPolicy) -> bool:
    if not pol.dr_enabled:
        return False
    crit = str(row.get("criticality", ""))
    if pol.dr_coverage == "All production":
        return bool(row.get("is_prod", False))
    if pol.dr_coverage == "Tier 0 only":
        return crit.startswith("Tier 0")
    if pol.dr_coverage == "Tier 0 + Tier 1":
        return crit.startswith("Tier 0") or crit.startswith("Tier 1")
    return False


def compute_costs(sized: pd.DataFrame, pb: PriceBook, pol: CommercialPolicy) -> pd.DataFrame:
    """Per-VM monthly Azure cost breakdown."""
    df = sized.copy()

    vm_lut = pb.vm.set_index("arm_sku_name")
    ri_lut = pb.ri.set_index("arm_sku_name") if len(pb.ri) else None
    sp_lut = pb.sp.set_index("arm_sku_name") if len(pb.sp) else None
    disk_lut = _disk_price_lookup(pb.disk)

    linux_hr, win_lic_hr, ri1, ri3, sp1, sp3, missing = [], [], [], [], [], [], []
    for sku in df["azure_sku"]:
        if sku in vm_lut.index:
            row = vm_lut.loc[sku]
            lin = float(row["linux_hr"]) if pd.notna(row["linux_hr"]) else np.nan
            lic = float(row["win_licence_hr"]) if pd.notna(row["win_licence_hr"]) else np.nan
            missing.append(False)
        else:
            lin, lic = np.nan, np.nan
            missing.append(True)
        linux_hr.append(lin)
        win_lic_hr.append(lic)
        ri1.append(float(ri_lut.loc[sku, "ri_1y_hr"]) if ri_lut is not None and sku in ri_lut.index
                   and pd.notna(ri_lut.loc[sku, "ri_1y_hr"]) else np.nan)
        ri3.append(float(ri_lut.loc[sku, "ri_3y_hr"]) if ri_lut is not None and sku in ri_lut.index
                   and pd.notna(ri_lut.loc[sku, "ri_3y_hr"]) else np.nan)
        sp1.append(float(sp_lut.loc[sku, "sp_1y_hr"]) if sp_lut is not None and sku in sp_lut.index
                   and pd.notna(sp_lut.loc[sku, "sp_1y_hr"]) else np.nan)
        sp3.append(float(sp_lut.loc[sku, "sp_3y_hr"]) if sp_lut is not None and sku in sp_lut.index
                   and pd.notna(sp_lut.loc[sku, "sp_3y_hr"]) else np.nan)

    df["price_missing"] = missing
    df["ondemand_linux_hr"] = linux_hr
    df["windows_licence_hr"] = np.nan_to_num(win_lic_hr, nan=0.0)
    df["ri_1y_hr"], df["ri_3y_hr"] = ri1, ri3
    df["sp_1y_hr"], df["sp_3y_hr"] = sp1, sp3

    # Fill any gap with a capacity-derived estimate so the total is never silently short.
    est = df["azure_vcpu"] * 0.048 + df["azure_ram_gib"] * 0.006
    df["ondemand_linux_hr"] = df["ondemand_linux_hr"].fillna(est)

    # ---- committed vs on-demand compute rate ----------------------------
    commit_col = {"ri-1y": "ri_1y_hr", "ri-3y": "ri_3y_hr",
                  "sp-1y": "sp_1y_hr", "sp-3y": "sp_3y_hr"}.get(pol.commitment)
    if commit_col:
        committed = df[commit_col].fillna(df["ondemand_linux_hr"])
    else:
        committed = df["ondemand_linux_hr"]
    df["committed_linux_hr"] = committed

    # Commitments only make sense on hours that actually run 24x7. Non-production
    # VMs that are scheduled off are billed on demand for the hours they do run.
    scheduled = pol.nonprod_schedule & (~df["is_prod"])
    weeks_per_month = HOURS / (24 * 7)
    df["billed_hours"] = np.where(
        scheduled, pol.nonprod_hours_per_week * weeks_per_month, HOURS)

    cov = np.where(df["is_prod"], pol.commitment_coverage_pct / 100.0, 0.0)
    df["blended_compute_hr"] = (df["committed_linux_hr"] * cov
                                + df["ondemand_linux_hr"] * (1 - cov))
    df["compute_cost"] = df["blended_compute_hr"] * df["billed_hours"]

    # ---- Windows Server licensing ---------------------------------------
    is_win = df["os_family"] == "Windows"
    ahb_share = (pol.ahb_coverage_pct / 100.0) if pol.apply_ahb_windows else 0.0
    df["windows_licence_cost"] = np.where(
        is_win, df["windows_licence_hr"] * df["billed_hours"] * (1 - ahb_share), 0.0)
    df["ahb_saving"] = np.where(
        is_win, df["windows_licence_hr"] * df["billed_hours"] * ahb_share, 0.0)

    # ---- storage, backup, DR --------------------------------------------
    df["storage_cost"] = df.apply(lambda r: _disk_cost(r, disk_lut), axis=1)
    df["backup_cost"] = df.apply(lambda r: _backup_cost(r, pol, pb), axis=1)
    df["dr_cost"] = df.apply(
        lambda r: (pb.asr_instance + _disk_cost(r, disk_lut) * 0.5) if _dr_applies(r, pol) else 0.0,
        axis=1)

    subtotal = (df["compute_cost"] + df["windows_licence_cost"]
                + df["storage_cost"] + df["backup_cost"] + df["dr_cost"])
    df["platform_overhead_cost"] = subtotal * (pol.platform_overhead_pct / 100.0)

    # Egress is a portfolio-level number; allocate it by relative network throughput.
    net = pd.to_numeric(df["net_mbps"], errors="coerce").fillna(0.1)
    share = net / net.sum() if net.sum() > 0 else 1.0 / len(df)
    df["egress_cost"] = pol.monthly_egress_gb * pb.egress_gb * share

    df["monthly_cost"] = (subtotal + df["platform_overhead_cost"] + df["egress_cost"])
    if pol.negotiated_discount_pct:
        df["monthly_cost"] *= (1 - pol.negotiated_discount_pct / 100.0)
    df["annual_cost"] = df["monthly_cost"] * 12

    # On-demand, no-AHB, no-schedule baseline -- the "do nothing clever" number.
    df["baseline_monthly_cost"] = (
        df["ondemand_linux_hr"] * HOURS
        + np.where(is_win, df["windows_licence_hr"] * HOURS, 0.0)
        + df["storage_cost"] + df["backup_cost"]
    ) * (1 + pol.platform_overhead_pct / 100.0)
    df["optimisation_saving"] = df["baseline_monthly_cost"] - df["monthly_cost"]
    return df


def cost_summary(costed: pd.DataFrame, pol: CommercialPolicy) -> dict:
    live = costed[costed["strategy"] != "Retire"]
    return {
        "vms_costed": int(len(live)),
        "vms_retired": int((costed["strategy"] == "Retire").sum()),
        "monthly_total": float(live["monthly_cost"].sum()),
        "annual_total": float(live["annual_cost"].sum()),
        "baseline_monthly": float(live["baseline_monthly_cost"].sum()),
        "monthly_saving": float(live["optimisation_saving"].sum()),
        "compute": float(live["compute_cost"].sum()),
        "windows_licence": float(live["windows_licence_cost"].sum()),
        "ahb_saving": float(live["ahb_saving"].sum()),
        "storage": float(live["storage_cost"].sum()),
        "backup": float(live["backup_cost"].sum()),
        "dr": float(live["dr_cost"].sum()),
        "overhead": float(live["platform_overhead_cost"].sum()),
        "egress": float(live["egress_cost"].sum()),
        "retire_saving_monthly": float(costed[costed["strategy"] == "Retire"]["baseline_monthly_cost"].sum()),
        "avg_cost_per_vm": float(live["monthly_cost"].mean()) if len(live) else 0.0,
        "priced_from_api_pct": float((~costed["price_missing"]).mean() * 100),
        "currency": pol.currency,
    }


def cost_breakdown_frame(costed: pd.DataFrame) -> pd.DataFrame:
    live = costed[costed["strategy"] != "Retire"]
    rows = [
        ("Compute (VM hours)", live["compute_cost"].sum()),
        ("Windows Server licence", live["windows_licence_cost"].sum()),
        ("Managed disks", live["storage_cost"].sum()),
        ("Backup (vault + instances)", live["backup_cost"].sum()),
        ("DR (Site Recovery)", live["dr_cost"].sum()),
        ("Platform / landing zone overhead", live["platform_overhead_cost"].sum()),
        ("Network egress", live["egress_cost"].sum()),
    ]
    df = pd.DataFrame(rows, columns=["component", "monthly_cost"])
    df = df[df["monthly_cost"] > 0]
    df["share_pct"] = df["monthly_cost"] / df["monthly_cost"].sum() * 100
    return df.sort_values("monthly_cost", ascending=False)


def lever_sensitivity(sized: pd.DataFrame, pb: PriceBook, base: CommercialPolicy) -> pd.DataFrame:
    """Isolate what each commercial lever is worth, by turning it off one at a time."""
    from dataclasses import replace

    base_total = compute_costs(sized, pb, base)
    base_total = base_total[base_total["strategy"] != "Retire"]["monthly_cost"].sum()

    scenarios = {
        "No commitment (pay-as-you-go)": replace(base, commitment="none", commitment_coverage_pct=0),
        "No Azure Hybrid Benefit": replace(base, apply_ahb_windows=False),
        "No non-production scheduling": replace(base, nonprod_schedule=False),
        "All-Premium SSD storage": None,      # handled by the caller via sizing policy
        "No backup": replace(base, backup_enabled=False),
    }
    rows = []
    for name, pol in scenarios.items():
        if pol is None:
            continue
        t = compute_costs(sized, pb, pol)
        t = t[t["strategy"] != "Retire"]["monthly_cost"].sum()
        rows.append({"lever": name, "monthly_cost": t,
                     "delta_vs_plan": t - base_total,
                     "delta_pct": (t - base_total) / base_total * 100 if base_total else 0})
    return pd.DataFrame(rows).sort_values("delta_vs_plan", ascending=False)
