"""Write a sample RVTools export, for testing the upload path.

  py -3.12 tools_make_sample.py

Produces data/sample_rvtools_300vm.xlsx: a 300-VM vInfo sheet using RVTools' own
column names and value conventions. Deliberately faithful to a real export, which
means it carries no environment, criticality, application name or performance
counters -- vInfo has none of those. Uploading it should therefore raise the
"classification quality will be limited" and "no performance counters" warnings,
because that is what a real vInfo-only upload does.

Different seed and shape from the reference estate, so a successful import is
visibly a different estate rather than the one already on screen.
"""

import pathlib
import sys

import numpy as np
import pandas as pd

from core import inventory

SEED = 731144
N_VMS = 300
OUT = pathlib.Path("data") / "sample_rvtools_300vm.xlsx"


def main() -> int:
    est = inventory.generate_estate(N_VMS, windows_pct=0.68, seed=SEED, n_clusters=6)
    rng = np.random.default_rng(SEED)

    dc = np.where(est["cluster"].str.contains("1|2|3"), "DC-LONDON", "DC-SLOUGH")
    folders = rng.choice(["Production", "Non-Production", "Infrastructure", "Archive"],
                         size=len(est), p=[0.55, 0.28, 0.12, 0.05])

    vinfo = pd.DataFrame({
        "VM": est["vm_name"],
        "Powerstate": np.where(est["powered_on"], "poweredOn", "poweredOff"),
        "Template": False,
        "DNS Name": est["vm_name"].str.lower() + ".corp.local",
        "CPUs": est["vcpu"].astype(int),
        "Memory": (est["ram_gib"] * 1024).astype(int),          # RVTools reports MiB
        "NICs": est["nic_count"].astype(int),
        "Disks": est["total_disks"].astype(int),
        "Provisioned MiB": (est["provisioned_gib"] * 1024).round().astype(int),
        "In Use MiB": (est["used_gib"] * 1024).round().astype(int),
        "Datacenter": dc,
        "Cluster": est["cluster"],
        "Host": est["esxi_host"],
        "Folder": folders,
        "OS according to the configuration file": est["guest_os"],
        "OS according to the VMware Tools": est["guest_os"],
        "Firmware": est["firmware"],
        "Tools": est["vmware_tools"],
        "Annotation": "",
        "VM UUID": [f"5{rng.integers(10**7, 10**8 - 1)}-{rng.integers(1000, 9999)}"
                    for _ in range(len(est))],
    })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(OUT, engine="openpyxl") as xl:
        vinfo.to_excel(xl, sheet_name="vInfo", index=False)

    # Prove it survives the round trip rather than trusting that it will.
    back = pd.read_excel(OUT, sheet_name="vInfo")
    parsed, warns = inventory.import_inventory(back)
    summary = inventory.estate_summary(parsed)

    print(f"Wrote {OUT}  ({OUT.stat().st_size / 1024:.0f} KB)")
    print(f"  {summary['vm_count']:,} VMs, {summary['windows_pct']:.0f}% Windows, "
          f"{summary['total_vcpu']:,} vCPU, {summary['total_ram_tib']:.1f} TiB RAM, "
          f"{summary['provisioned_tib']:,.0f} TiB provisioned")
    print(f"  {summary['eol_os_count']} end-of-life guest OSes, "
          f"{summary['powered_on']} powered on")
    print("  import warnings (expected, vInfo carries none of this):")
    for w in warns:
        print(f"    - {w}")

    # An upload has to produce a working model, not just import cleanly. vInfo
    # has no performance counters, and a NaN in one complexity factor used to
    # make the entire programme cost NaN, which summed to a silent zero.
    from core import scenario
    res = scenario.run_pipeline(scenario.Scenario(use_uploaded=True),
                                estate_override=parsed)
    checks = {
        "complexity scored for every VM": int(res.sized["complexity"].isna().sum()) == 0,
        "programme cost is non-zero": res.effort_summary["migration_cost"] > 0,
        "effort hours are non-zero": res.effort_summary["total_effort_hours"] > 0,
        "schedule has at least one wave": res.schedule_summary.get("waves", 0) >= 1,
        "Azure run rate is non-zero": res.cost_summary["monthly_total"] > 0,
    }
    print("  pipeline on the imported estate:")
    for name, ok in checks.items():
        print(f"    {'ok  ' if ok else 'FAIL'} {name}")
    if not all(checks.values()):
        print("\nThe sample imports but does not model. Not writing this off as fine.")
        return 1

    print(f"    programme cost {res.effort_summary['migration_cost']:,.0f}, "
          f"{res.effort_summary['total_effort_hours']:,.0f} effort hours, "
          f"{res.schedule_summary.get('waves', 0)} waves")
    return 0


if __name__ == "__main__":
    sys.exit(main())
