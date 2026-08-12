"""Ad-hoc meter explorer used while calibrating the pricing filters."""
import json
import sys

from core import pricing


def dump(flt, needle=None, limit=40, fields=("productName", "skuName", "meterName",
                                             "retailPrice", "unitOfMeasure", "tierMinimumUnits")):
    res = pricing.fetch(flt, live=True, max_pages=60, use_cache=False)
    print(f"--- {flt}  ({len(res.items)} items) ---")
    n = 0
    for it in res.items:
        blob = json.dumps(it)
        if needle and needle.lower() not in blob.lower():
            continue
        print({k: it.get(k) for k in fields})
        n += 1
        if n >= limit:
            break


if __name__ == "__main__":
    what = sys.argv[1]
    if what == "disk":
        dump("serviceName eq 'Storage' and armRegionName eq 'eastus' and priceType eq 'Consumption'",
             needle="P30", limit=20)
        dump("serviceName eq 'Storage' and armRegionName eq 'eastus' and priceType eq 'Consumption'",
             needle="E30", limit=20)
        dump("serviceName eq 'Storage' and armRegionName eq 'eastus' and priceType eq 'Consumption'",
             needle="S30", limit=20)
    elif what == "bandwidth":
        dump("serviceName eq 'Bandwidth' and priceType eq 'Consumption'", needle="Data Transfer Out", limit=40)
    elif what == "backup":
        dump("serviceName eq 'Backup' and armRegionName eq 'eastus' and priceType eq 'Consumption'", limit=60)
    elif what == "asr":
        dump("serviceName eq 'Azure Site Recovery' and priceType eq 'Consumption'", limit=40)
