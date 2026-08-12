"""Live vendor pricing.

Primary source is the **Azure Retail Prices API** (https://prices.azure.com/api/retail/prices),
which is unauthenticated and returns Microsoft's published retail rates for every
meter, region and currency, including Reserved Instance and Savings Plan rates.

Everything is cached to disk under ``.cache/`` so a workshop demo keeps working
when the venue Wi-Fi does not. If the API is unreachable and no cache exists, the
callers fall back to :mod:`core.fallback_prices`.
"""

import hashlib
import json
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import requests

API = "https://prices.azure.com/api/retail/prices"
API_VERSION = "2023-01-01-preview"   # required for savingsPlan rates
CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"
CACHE_TTL_SECONDS = 24 * 3600
USER_AGENT = "vmware-azure-migration-simulator/1.0"


class PricingError(RuntimeError):
    pass


@dataclass
class FetchResult:
    items: list[dict]
    source: str          # "live" | "cache" | "cache-stale"
    fetched_at: float
    pages: int

    @property
    def age_hours(self) -> float:
        return (time.time() - self.fetched_at) / 3600


# --------------------------------------------------------------------------
# Transport
# --------------------------------------------------------------------------
def _cache_dir() -> Path | None:
    """Writable cache directory, or None if there isn't one.

    Hosted environments frequently mount the application directory read-only, so
    the cache has to be optional rather than assumed. Falls back to the system
    temp directory, and finally to no caching at all -- the app still works, it
    just re-fetches from the vendor APIs.
    """
    for candidate in (CACHE_DIR, Path(tempfile.gettempdir()) / "migsim-cache"):
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / ".write-test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return candidate
        except Exception:
            continue
    return None


def _cache_path(key: str) -> Path | None:
    d = _cache_dir()
    if d is None:
        return None
    return d / f"{hashlib.sha256(key.encode()).hexdigest()[:20]}.json"


def _read_cache(key: str) -> tuple[list[dict], float] | None:
    p = _cache_path(key)
    if p is None or not p.exists():
        return None
    try:
        blob = json.loads(p.read_text(encoding="utf-8"))
        return blob["items"], blob["fetched_at"]
    except Exception:
        return None


def _write_cache(key: str, items: list[dict]) -> None:
    """Best effort. A cache miss is a performance problem, not a failure."""
    p = _cache_path(key)
    if p is None:
        return
    try:
        p.write_text(json.dumps({"items": items, "fetched_at": time.time()}),
                     encoding="utf-8")
    except Exception:
        pass


def fetch(odata_filter: str, currency: str = "USD", max_pages: int = 40,
          use_cache: bool = True, live: bool = True, timeout: int = 25) -> FetchResult:
    """Page through the Retail Prices API for one OData filter."""
    key = f"{currency}|{odata_filter}"
    cached = _read_cache(key) if use_cache else None

    if cached and live:
        items, ts = cached
        if time.time() - ts < CACHE_TTL_SECONDS:
            return FetchResult(items, "cache", ts, 0)
    if cached and not live:
        items, ts = cached
        return FetchResult(items, "cache", ts, 0)

    if not live:
        raise PricingError("Live pricing disabled and no cache available.")

    items: list[dict] = []
    url = API
    params = {"api-version": API_VERSION, "$filter": odata_filter, "currencyCode": f"'{currency}'"}
    pages = 0
    try:
        session = requests.Session()
        session.headers["User-Agent"] = USER_AGENT
        while url and pages < max_pages:
            r = session.get(url, params=params if pages == 0 else None, timeout=timeout)
            r.raise_for_status()
            payload = r.json()
            items.extend(payload.get("Items", []))
            url = payload.get("NextPageLink")
            pages += 1
    except Exception as exc:
        if cached:
            its, ts = cached
            return FetchResult(its, "cache-stale", ts, 0)
        raise PricingError(f"Azure Retail Prices API unreachable: {exc}") from exc

    _write_cache(key, items)
    return FetchResult(items, "live", time.time(), pages)


# --------------------------------------------------------------------------
# Virtual machines
# --------------------------------------------------------------------------
def _is_noise(item: dict) -> bool:
    """Drop Spot, Low Priority and dev/test meters -- not valid for production estates."""
    sku = (item.get("skuName") or "")
    meter = (item.get("meterName") or "")
    if "Spot" in sku or "Spot" in meter:
        return True
    if "Low Priority" in sku or "Low Priority" in meter:
        return True
    if item.get("type") == "DevTestConsumption":
        return True
    return False


def vm_prices(region: str, currency: str = "USD", live: bool = True) -> pd.DataFrame:
    """Per-hour on-demand VM rates for a region, split into Linux and Windows.

    The API emits one row per (SKU, OS) pair. Windows rows carry ``Windows`` in
    ``productName``; the Linux/BYOL rate is the row without it. Returns one row
    per ``arm_sku_name`` with both columns plus the Windows licence delta.
    """
    flt = (f"serviceName eq 'Virtual Machines' and armRegionName eq '{region}' "
           f"and priceType eq 'Consumption'")
    res = fetch(flt, currency=currency, live=live, max_pages=60)
    rows = []
    for it in res.items:
        if _is_noise(it) or not it.get("armSkuName"):
            continue
        if (it.get("unitOfMeasure") or "").strip() not in ("1 Hour", "1 Hour "):
            continue
        rows.append({
            "arm_sku_name": it["armSkuName"],
            "is_windows": "Windows" in (it.get("productName") or ""),
            "price_hr": float(it.get("retailPrice") or 0.0),
            "product_name": it.get("productName"),
            "meter_id": it.get("meterId"),
        })
    if not rows:
        return pd.DataFrame(columns=["arm_sku_name", "linux_hr", "windows_hr", "win_licence_hr"])

    df = pd.DataFrame(rows)
    df = df[df["price_hr"] > 0]
    piv = (df.pivot_table(index="arm_sku_name", columns="is_windows",
                          values="price_hr", aggfunc="min")
             .rename(columns={False: "linux_hr", True: "windows_hr"})
             .reset_index())
    for col in ("linux_hr", "windows_hr"):
        if col not in piv.columns:
            piv[col] = pd.NA
    # Windows rows already include the licence; the delta is the AHB-eligible part.
    piv["win_licence_hr"] = (piv["windows_hr"] - piv["linux_hr"]).clip(lower=0)
    piv.attrs["source"] = res.source
    piv.attrs["fetched_at"] = res.fetched_at
    return piv


def vm_reservation_prices(region: str, currency: str = "USD", live: bool = True) -> pd.DataFrame:
    """Reserved Instance rates (1yr/3yr), normalised to an effective hourly rate.

    RI meters are billed upfront for the whole term, so the hourly equivalent is
    ``retailPrice / (8760 * years)``.
    """
    flt = (f"serviceName eq 'Virtual Machines' and armRegionName eq '{region}' "
           f"and priceType eq 'Reservation'")
    try:
        res = fetch(flt, currency=currency, live=live, max_pages=60)
    except PricingError:
        return pd.DataFrame(columns=["arm_sku_name", "ri_1y_hr", "ri_3y_hr"])
    rows = []
    for it in res.items:
        if not it.get("armSkuName"):
            continue
        term = (it.get("reservationTerm") or "").strip()
        years = {"1 Year": 1, "3 Years": 3, "5 Years": 5}.get(term)
        if not years:
            continue
        # Windows RI meters exist but AHB/licence handling is done separately;
        # take the base (Linux) compute reservation.
        if "Windows" in (it.get("productName") or ""):
            continue
        rows.append({
            "arm_sku_name": it["armSkuName"],
            "years": years,
            "hourly": float(it.get("retailPrice") or 0.0) / (8760.0 * years),
        })
    if not rows:
        return pd.DataFrame(columns=["arm_sku_name", "ri_1y_hr", "ri_3y_hr"])
    df = pd.DataFrame(rows)
    piv = (df.pivot_table(index="arm_sku_name", columns="years", values="hourly", aggfunc="min")
             .rename(columns={1: "ri_1y_hr", 3: "ri_3y_hr", 5: "ri_5y_hr"})
             .reset_index())
    for c in ("ri_1y_hr", "ri_3y_hr"):
        if c not in piv.columns:
            piv[c] = pd.NA
    return piv[["arm_sku_name", "ri_1y_hr", "ri_3y_hr"]]


def vm_savings_plan_prices(region: str, currency: str = "USD", live: bool = True) -> pd.DataFrame:
    """Azure savings plan for compute rates, embedded in the preview API response."""
    flt = (f"serviceName eq 'Virtual Machines' and armRegionName eq '{region}' "
           f"and priceType eq 'Consumption'")
    try:
        res = fetch(flt, currency=currency, live=live, max_pages=60)
    except PricingError:
        return pd.DataFrame(columns=["arm_sku_name", "sp_1y_hr", "sp_3y_hr"])
    rows = []
    for it in res.items:
        if _is_noise(it) or not it.get("armSkuName") or not it.get("savingsPlan"):
            continue
        if "Windows" in (it.get("productName") or ""):
            continue
        rec = {"arm_sku_name": it["armSkuName"]}
        for sp in it["savingsPlan"]:
            if sp.get("term") == "1 Year":
                rec["sp_1y_hr"] = float(sp["retailPrice"])
            elif sp.get("term") == "3 Years":
                rec["sp_3y_hr"] = float(sp["retailPrice"])
        rows.append(rec)
    if not rows:
        return pd.DataFrame(columns=["arm_sku_name", "sp_1y_hr", "sp_3y_hr"])
    df = pd.DataFrame(rows).groupby("arm_sku_name", as_index=False).min()
    for c in ("sp_1y_hr", "sp_3y_hr"):
        if c not in df.columns:
            df[c] = pd.NA
    return df[["arm_sku_name", "sp_1y_hr", "sp_3y_hr"]]


# --------------------------------------------------------------------------
# Managed disks
# --------------------------------------------------------------------------
_DISK_PRODUCTS = {
    "Premium SSD": "Premium SSD Managed Disks",
    "Standard SSD": "Standard SSD Managed Disks",
    "Standard HDD": "Standard HDD Managed Disks",
}


def disk_prices(region: str, currency: str = "USD", live: bool = True) -> pd.DataFrame:
    """Monthly price per managed-disk tier (P30, E30, S30 ...) for a region.

    Each tier has three meters -- ``"P30 LRS Disk"`` (the capacity charge we
    want), ``"P30 LRS Disk Mount"`` (shared-disk attach fee) and
    ``"P30 LRS Disk Operations"`` (per-10k transactions on Standard tiers).
    Matching on the exact meter name is what keeps the mount fee from being
    mistaken for the capacity price.
    """
    flt = (f"serviceName eq 'Storage' and armRegionName eq '{region}' "
           f"and priceType eq 'Consumption'")
    res = fetch(flt, currency=currency, live=live, max_pages=60)
    cap, ops = [], []
    for it in res.items:
        product = it.get("productName") or ""
        kind = next((k for k, v in _DISK_PRODUCTS.items() if v == product), None)
        if not kind:
            continue
        sku = (it.get("skuName") or "")
        meter = (it.get("meterName") or "")
        parts = sku.split()
        if len(parts) < 2 or parts[1] != "LRS":
            continue
        tier, price = parts[0], float(it.get("retailPrice") or 0.0)
        if meter == f"{tier} LRS Disk" and "Month" in (it.get("unitOfMeasure") or ""):
            cap.append({"kind": kind, "tier": tier, "price_month": price})
        elif meter == f"{tier} LRS Disk Operations":
            ops.append({"kind": kind, "tier": tier, "price_per_10k_ops": price})

    if not cap:
        return pd.DataFrame(columns=["kind", "tier", "price_month", "price_per_10k_ops"])
    out = pd.DataFrame(cap).groupby(["kind", "tier"], as_index=False)["price_month"].min()
    if ops:
        o = pd.DataFrame(ops).groupby(["kind", "tier"], as_index=False)["price_per_10k_ops"].min()
        out = out.merge(o, on=["kind", "tier"], how="left")
    else:
        out["price_per_10k_ops"] = 0.0
    out["price_per_10k_ops"] = out["price_per_10k_ops"].fillna(0.0)
    out.attrs["source"] = res.source
    return out


def snapshot_price(region: str, currency: str = "USD", live: bool = True) -> float:
    """USD/GiB/month for standard (HDD-backed) incremental snapshots."""
    flt = (f"serviceName eq 'Storage' and armRegionName eq '{region}' "
           f"and priceType eq 'Consumption' and contains(meterName, 'Snapshot')")
    try:
        res = fetch(flt, currency=currency, live=live, max_pages=5)
    except PricingError:
        return 0.05
    vals = [float(i["retailPrice"]) for i in res.items
            if "Standard" in (i.get("productName") or "") and float(i.get("retailPrice") or 0) > 0]
    return min(vals) if vals else 0.05


# --------------------------------------------------------------------------
# Bandwidth / egress, Backup, Site Recovery
# --------------------------------------------------------------------------
def egress_price(region: str, currency: str = "USD", live: bool = True) -> float:
    """Internet data-transfer-out rate for the first paid tier (>100 GB/month).

    The first 100 GB per month is free, so the meaningful rate is the one at
    ``tierMinimumUnits == 100``.
    """
    flt = (f"serviceName eq 'Bandwidth' and armRegionName eq '{region}' "
           f"and priceType eq 'Consumption'")
    try:
        res = fetch(flt, currency=currency, live=live, max_pages=10)
    except PricingError:
        return 0.087
    cands = [float(i["retailPrice"]) for i in res.items
             if (i.get("productName") or "").startswith("Bandwidth - Routing Preference: Internet")
             and (i.get("meterName") or "") == "Standard Data Transfer Out"
             and float(i.get("retailPrice") or 0) > 0
             and float(i.get("tierMinimumUnits") or 0) == 100.0]
    return min(cands) if cands else 0.087


def backup_price(region: str, currency: str = "USD", live: bool = True) -> dict:
    """Azure Backup protected-instance fee and Recovery Services vault storage rates.

    ``instance_month`` is the per-VM block price: Azure charges it once for an
    instance up to 500 GB, then once more per additional 500 GB.
    """
    out = {"instance_month": 10.0, "sql_instance_month": 25.0,
           "grs_gb_month": 0.0448, "lrs_gb_month": 0.0224, "archive_lrs_gb_month": 0.0013}
    flt = (f"serviceName eq 'Backup' and armRegionName eq '{region}' "
           f"and priceType eq 'Consumption'")
    try:
        res = fetch(flt, currency=currency, live=live, max_pages=10)
    except PricingError:
        return out

    def pick(meter: str) -> float | None:
        vals = [float(i["retailPrice"]) for i in res.items
                if (i.get("meterName") or "") == meter and float(i.get("retailPrice") or 0) > 0]
        return min(vals) if vals else None

    for key, meter in (("instance_month", "Azure VM Protected Instance"),
                       ("sql_instance_month", "SQL Server in Azure VM Protected Instance"),
                       ("grs_gb_month", "Standard GRS Data Stored"),
                       ("lrs_gb_month", "Standard LRS Data Stored"),
                       ("archive_lrs_gb_month", "Archive LRS Data Stored")):
        v = pick(meter)
        if v is not None:
            out[key] = v
    return out


def site_recovery_price(currency: str = "USD", live: bool = True) -> float:
    """Azure Site Recovery "VM Replicated to Azure" monthly fee per protected instance.

    This is also the meter behind agent-based Azure Migrate replication -- and it
    is waived for the first 180 days per instance when used for migration.
    """
    flt = "serviceName eq 'Azure Site Recovery' and priceType eq 'Consumption'"
    try:
        res = fetch(flt, currency=currency, live=live, max_pages=5)
    except PricingError:
        return 25.0
    vals = [float(i["retailPrice"]) for i in res.items
            if (i.get("meterName") or "") == "VM Replicated to Azure"
            and float(i.get("retailPrice") or 0) > 0]
    return min(vals) if vals else 25.0


def expressroute_price(currency: str = "USD", live: bool = True) -> pd.DataFrame:
    """ExpressRoute circuit monthly rates by bandwidth (metered/unlimited)."""
    flt = "serviceName eq 'ExpressRoute' and priceType eq 'Consumption'"
    try:
        res = fetch(flt, currency=currency, live=live, max_pages=10)
    except PricingError:
        return pd.DataFrame(columns=["meter", "price_month"])
    rows = [{"meter": i.get("meterName"), "product": i.get("productName"),
             "price_month": float(i.get("retailPrice") or 0)}
            for i in res.items
            if "Month" in (i.get("unitOfMeasure") or "") and float(i.get("retailPrice") or 0) > 0]
    return pd.DataFrame(rows).drop_duplicates()


def sql_mi_prices(region: str, currency: str = "USD", live: bool = True) -> pd.DataFrame:
    """Azure SQL Managed Instance vCore rates -- used by the replatform costing."""
    flt = (f"serviceName eq 'SQL Managed Instance' and armRegionName eq '{region}' "
           f"and priceType eq 'Consumption'")
    try:
        res = fetch(flt, currency=currency, live=live, max_pages=20)
    except PricingError:
        return pd.DataFrame(columns=["product_name", "meter_name", "price", "unit"])
    rows = [{"product_name": i.get("productName"), "meter_name": i.get("meterName"),
             "sku_name": i.get("skuName"), "price": float(i.get("retailPrice") or 0),
             "unit": i.get("unitOfMeasure")}
            for i in res.items if float(i.get("retailPrice") or 0) > 0]
    return pd.DataFrame(rows)


def probe() -> dict:
    """Cheap connectivity check for the UI status badge."""
    try:
        t0 = time.time()
        r = requests.get(API, params={"api-version": API_VERSION,
                                      "$filter": "serviceName eq 'Virtual Machines' and armSkuName eq 'Standard_D2s_v5' and armRegionName eq 'eastus'"},
                         timeout=10, headers={"User-Agent": USER_AGENT})
        r.raise_for_status()
        n = len(r.json().get("Items", []))
        return {"ok": True, "latency_ms": int((time.time() - t0) * 1000), "sample_items": n}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
