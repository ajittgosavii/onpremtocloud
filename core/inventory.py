"""Source estate model: synthetic VMware inventory generator and RVTools import.

The generator produces an estate with the statistical shape of a real, aged
vSphere farm -- heavy over-provisioning, a long tail of idle VMs, a handful of
end-of-life guest OSes, and a realistic scattering of the technical conditions
that actually block or slow a migration (RDMs, shared disks, snapshots, stale
VMware Tools, vGPU, MSCS clusters).
"""

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# Guest OS mix. ``eol`` drives the readiness engine and the remediation cost.
# --------------------------------------------------------------------------
WINDOWS_OS = [
    # (name, weight, eol, azure_support)
    ("Microsoft Windows Server 2022 (64-bit)", 0.14, False, "supported"),
    ("Microsoft Windows Server 2019 (64-bit)", 0.34, False, "supported"),
    ("Microsoft Windows Server 2016 (64-bit)", 0.28, False, "supported"),
    ("Microsoft Windows Server 2012 R2 (64-bit)", 0.13, True, "esu-required"),
    ("Microsoft Windows Server 2012 (64-bit)", 0.05, True, "esu-required"),
    ("Microsoft Windows Server 2008 R2 (64-bit)", 0.045, True, "esu-required"),
    ("Microsoft Windows Server 2003 (32-bit)", 0.005, True, "unsupported"),
]
LINUX_OS = [
    ("Red Hat Enterprise Linux 9 (64-bit)", 0.16, False, "supported"),
    ("Red Hat Enterprise Linux 8 (64-bit)", 0.24, False, "supported"),
    ("Red Hat Enterprise Linux 7 (64-bit)", 0.10, True, "endorsed-eol"),
    ("Ubuntu Linux 22.04 LTS (64-bit)", 0.14, False, "supported"),
    ("Ubuntu Linux 20.04 LTS (64-bit)", 0.10, False, "supported"),
    ("Ubuntu Linux 18.04 LTS (64-bit)", 0.04, True, "endorsed-eol"),
    ("CentOS 7 (64-bit)", 0.12, True, "endorsed-eol"),
    ("SUSE Linux Enterprise Server 15 (64-bit)", 0.05, False, "supported"),
    ("Oracle Linux 8 (64-bit)", 0.04, False, "supported"),
    ("Debian GNU/Linux 11 (64-bit)", 0.01, False, "supported"),
]

TIERS = ["Web", "App", "Middleware", "Database", "Infrastructure", "Batch"]
TIER_W = [0.18, 0.30, 0.12, 0.17, 0.15, 0.08]

ENVIRONMENTS = ["Production", "UAT", "Test", "Development", "DR"]
ENV_W = [0.42, 0.13, 0.16, 0.22, 0.07]

CRITICALITY = ["Tier 0 - Mission critical", "Tier 1 - Business critical",
               "Tier 2 - Business operational", "Tier 3 - Administrative"]
CRIT_W = [0.06, 0.22, 0.42, 0.30]

APP_PREFIXES = [
    "Finance", "HR", "CRM", "ERP", "Billing", "Claims", "Payments", "Logistics",
    "Inventory", "Portal", "Analytics", "DataWarehouse", "Identity", "Print",
    "FileShare", "Monitoring", "Backup", "Middleware", "Integration", "Reporting",
    "eCommerce", "Trading", "Risk", "Compliance", "CustomerCare", "Marketing",
    "Procurement", "Manufacturing", "Quality", "Scheduling",
]

DEFAULT_SEED = 20260811


def _weighted(rng: np.random.Generator, options, n: int):
    names = [o[0] for o in options]
    weights = np.array([o[1] for o in options], dtype=float)
    weights = weights / weights.sum()
    return rng.choice(names, size=n, p=weights)


def _os_lookup() -> dict[str, dict]:
    out = {}
    for name, _, eol, support in WINDOWS_OS:
        out[name] = {"os_family": "Windows", "os_eol": eol, "azure_os_support": support}
    for name, _, eol, support in LINUX_OS:
        out[name] = {"os_family": "Linux", "os_eol": eol, "azure_os_support": support}
    return out


OS_LOOKUP = _os_lookup()


def generate_estate(n_vms: int = 547,
                    windows_pct: float = 0.60,
                    seed: int = DEFAULT_SEED,
                    n_clusters: int = 9,
                    n_apps: int | None = None,
                    overprovision_bias: float = 1.0) -> pd.DataFrame:
    """Generate a reproducible synthetic VMware estate.

    ``overprovision_bias`` scales measured utilisation: 1.0 is the typical aged
    enterprise farm (~14% mean CPU), values >1 model a better-managed estate
    with less right-sizing headroom to harvest.
    """
    rng = np.random.default_rng(seed)
    n_apps = n_apps or max(20, n_vms // 7)

    n_win = int(round(n_vms * windows_pct))
    os_names = np.concatenate([
        _weighted(rng, WINDOWS_OS, n_win),
        _weighted(rng, LINUX_OS, n_vms - n_win),
    ])
    rng.shuffle(os_names)

    # ---- shape -----------------------------------------------------------
    vcpu_choices = np.array([1, 2, 4, 6, 8, 12, 16, 24, 32, 48, 64])
    vcpu_w = np.array([0.04, 0.30, 0.28, 0.05, 0.16, 0.03, 0.08, 0.02, 0.025, 0.01, 0.005])
    vcpu = rng.choice(vcpu_choices, size=n_vms, p=vcpu_w / vcpu_w.sum())

    # RAM per vCPU varies by workload; DB tiers get more.
    tier = np.array(_weighted(rng, list(zip(TIERS, TIER_W)), n_vms))
    ratio = rng.choice([1, 2, 4, 8], size=n_vms, p=[0.08, 0.34, 0.44, 0.14]).astype(float)
    ratio = np.where(tier == "Database", np.maximum(ratio, 4.0), ratio)
    ratio = np.where(tier == "Web", np.minimum(ratio, 2.0), ratio)
    ram_gib = np.clip(np.round(vcpu * ratio), 1, 4096)

    env = np.array(_weighted(rng, list(zip(ENVIRONMENTS, ENV_W)), n_vms))
    crit = np.array(_weighted(rng, list(zip(CRITICALITY, CRIT_W)), n_vms))
    # Non-production is rarely Tier 0/1.
    nonprod = np.isin(env, ["Development", "Test"])
    crit = np.where(nonprod & np.isin(crit, CRITICALITY[:2]), CRITICALITY[2], crit)

    # ---- storage ---------------------------------------------------------
    os_disk = np.where(
        pd.Series(os_names).map(lambda o: OS_LOOKUP[o]["os_family"]).values == "Windows",
        rng.choice([80, 100, 127, 150], size=n_vms, p=[0.25, 0.40, 0.25, 0.10]),
        rng.choice([40, 60, 80, 100], size=n_vms, p=[0.25, 0.35, 0.30, 0.10]),
    )
    n_data_disks = rng.choice([0, 1, 2, 3, 4, 6, 8], size=n_vms,
                              p=[0.30, 0.28, 0.18, 0.10, 0.07, 0.05, 0.02])
    # Database servers always carry data and log volumes. Force this before
    # sizing the data, so a DB VM never ends up with disks of zero capacity.
    n_data_disks = np.where(tier == "Database", np.maximum(n_data_disks, 2), n_data_disks)
    # Log-normal data volume -- a few very large file/DB servers dominate TB.
    data_gib = np.where(
        n_data_disks > 0,
        np.round(rng.lognormal(mean=5.3, sigma=1.15, size=n_vms)) * np.maximum(n_data_disks, 1) / 2,
        0,
    )
    data_gib = np.clip(data_gib, 0, 60000)
    provisioned_gib = os_disk + data_gib
    # VMware thin provisioning: consumed is typically 45-80% of provisioned.
    used_ratio = rng.uniform(0.42, 0.86, size=n_vms)
    used_gib = np.round(provisioned_gib * used_ratio, 1)

    # ---- utilisation (the over-provisioning story) -----------------------
    cpu_avg = np.clip(rng.gamma(shape=1.5, scale=9.0, size=n_vms) * overprovision_bias, 0.2, 99)
    cpu_p95 = np.clip(cpu_avg * rng.uniform(1.8, 3.6, size=n_vms), 1, 100)
    mem_avg = np.clip(rng.gamma(shape=3.0, scale=11.0, size=n_vms) * overprovision_bias, 2, 99)
    mem_p95 = np.clip(mem_avg * rng.uniform(1.1, 1.6, size=n_vms), 3, 100)
    # DB and batch tiers genuinely run hotter.
    hot = np.isin(tier, ["Database", "Batch"])
    cpu_avg = np.where(hot, np.clip(cpu_avg * 1.9, 0.2, 99), cpu_avg)
    cpu_p95 = np.where(hot, np.clip(cpu_p95 * 1.5, 1, 100), cpu_p95)

    iops_avg = np.round(np.clip(rng.lognormal(4.2, 1.3, size=n_vms) * (1 + 3 * hot), 1, 80000))
    iops_peak = np.round(iops_avg * rng.uniform(2.0, 6.0, size=n_vms))
    tput_mbps = np.round(iops_avg * rng.uniform(0.02, 0.12, size=n_vms), 1)
    net_mbps = np.round(np.clip(rng.lognormal(1.0, 1.4, size=n_vms), 0.05, 2000), 2)

    # Daily block churn drives replication delta-sync volume and cutover risk.
    churn_pct = np.clip(rng.gamma(2.0, 1.6, size=n_vms) + hot * 4, 0.1, 40)

    # ---- lifecycle / power state ----------------------------------------
    powered_on = rng.random(n_vms) > 0.085          # ~8.5% parked VMs
    days_since_boot = np.where(powered_on, rng.integers(1, 900, n_vms), 0)

    # Zombie VMs: powered on but doing nothing measurable. Real assessments of an
    # aged estate consistently find 10-20% of running VMs in this state, so they
    # are constructed explicitly rather than left to emerge from the tails.
    zombie_share = 0.14
    zombie = np.zeros(n_vms, dtype=bool)
    on_idx = np.flatnonzero(powered_on)
    # Pick from the least-utilised running VMs, with some randomness so the
    # selection is not a clean cut-off.
    rank = (cpu_avg[on_idx] / cpu_avg[on_idx].max()
            + net_mbps[on_idx] / net_mbps[on_idx].max()
            + rng.uniform(0, 0.6, on_idx.size))
    chosen = on_idx[np.argsort(rank)[:int(round(on_idx.size * zombie_share))]]
    zombie[chosen] = True
    # Make the telemetry consistent with the label.
    cpu_avg[chosen] = np.clip(cpu_avg[chosen] * 0.12, 0.1, 2.5)
    cpu_p95[chosen] = np.clip(cpu_avg[chosen] * rng.uniform(1.5, 3.0, chosen.size), 0.2, 8)
    net_mbps[chosen] = np.clip(net_mbps[chosen] * 0.05, 0.01, 0.4)

    # ---- migration friction flags ---------------------------------------
    has_rdm = rng.random(n_vms) < 0.045
    has_shared_disk = rng.random(n_vms) < 0.030      # MSCS / Oracle RAC style
    has_independent_disk = rng.random(n_vms) < 0.025
    has_snapshot = rng.random(n_vms) < 0.11
    snapshot_age_days = np.where(has_snapshot, rng.integers(1, 700, n_vms), 0)
    tools_status = rng.choice(["toolsOk", "toolsOld", "toolsNotInstalled", "toolsNotRunning"],
                              size=n_vms, p=[0.72, 0.18, 0.05, 0.05])
    has_vgpu = rng.random(n_vms) < 0.012
    has_usb_or_serial = rng.random(n_vms) < 0.018
    licence_mac_bound = rng.random(n_vms) < 0.035
    firmware = rng.choice(["bios", "efi"], size=n_vms, p=[0.62, 0.38])
    n_nics = rng.choice([1, 2, 3, 4, 6, 9], size=n_vms, p=[0.68, 0.21, 0.06, 0.03, 0.015, 0.005])
    encrypted = rng.random(n_vms) < 0.015
    fault_tolerant = rng.random(n_vms) < 0.006

    # ---- database / middleware estate ------------------------------------
    is_db_tier = tier == "Database"
    db_engine = np.where(
        is_db_tier,
        rng.choice(["Microsoft SQL Server", "Oracle Database", "PostgreSQL", "MySQL", "MongoDB"],
                   size=n_vms, p=[0.50, 0.20, 0.14, 0.11, 0.05]),
        np.where(rng.random(n_vms) < 0.09,
                 rng.choice(["Microsoft SQL Server", "PostgreSQL", "MySQL"],
                            size=n_vms, p=[0.6, 0.2, 0.2]),
                 "None"),
    )
    # Oracle/SQL on Linux vs Windows must stay coherent.
    os_family = pd.Series(os_names).map(lambda o: OS_LOOKUP[o]["os_family"]).values
    db_engine = np.where((db_engine == "Microsoft SQL Server") & (os_family == "Linux"),
                         "PostgreSQL", db_engine)

    # ---- placement and application grouping ------------------------------
    clusters = [f"CL-{chr(65 + i)}-{['LON','FRA','NYC','SIN','SYD','TOR','DUB','MUM','TOK'][i % 9]}"
                for i in range(n_clusters)]
    cluster = rng.choice(clusters, size=n_vms)
    host = np.array([f"esxi{rng.integers(1, 17):02d}.{c.lower()}.corp.local" for c in cluster])
    datastore = np.array([f"DS-{c.split('-')[1]}-{rng.integers(1, 9):02d}" for c in cluster])

    app_names = [f"{rng.choice(APP_PREFIXES)}-{i:03d}" for i in range(1, n_apps + 1)]
    # Zipf-ish: a few large apps hold many VMs, most apps hold 1-3.
    app_w = 1.0 / np.arange(1, n_apps + 1) ** 0.55
    app = rng.choice(app_names, size=n_vms, p=app_w / app_w.sum())

    vm_names = []
    for i in range(n_vms):
        role = {"Web": "web", "App": "app", "Middleware": "mw", "Database": "db",
                "Infrastructure": "inf", "Batch": "bat"}[tier[i]]
        envc = {"Production": "p", "UAT": "u", "Test": "t", "Development": "d", "DR": "r"}[env[i]]
        vm_names.append(f"{envc}{role}{i + 1:04d}")

    df = pd.DataFrame({
        "vm_name": vm_names,
        "app_name": app,
        "guest_os": os_names,
        "os_family": os_family,
        "environment": env,
        "criticality": crit,
        "tier": tier,
        "cluster": cluster,
        "esxi_host": host,
        "datastore": datastore,
        "vcpu": vcpu,
        "ram_gib": ram_gib.astype(float),
        "os_disk_gib": os_disk.astype(float),
        "data_disk_count": n_data_disks.astype(int),
        "data_disk_gib": np.round(data_gib, 1),
        "provisioned_gib": np.round(provisioned_gib, 1),
        "used_gib": used_gib,
        "cpu_avg_pct": np.round(cpu_avg, 1),
        "cpu_p95_pct": np.round(cpu_p95, 1),
        "mem_avg_pct": np.round(mem_avg, 1),
        "mem_p95_pct": np.round(mem_p95, 1),
        "iops_avg": iops_avg,
        "iops_peak": iops_peak,
        "disk_mbps": tput_mbps,
        "net_mbps": net_mbps,
        "daily_churn_pct": np.round(churn_pct, 2),
        "powered_on": powered_on,
        "days_since_boot": days_since_boot,
        "zombie_candidate": zombie,
        "nic_count": n_nics,
        "firmware": firmware,
        "vmware_tools": tools_status,
        "has_rdm": has_rdm,
        "has_shared_disk": has_shared_disk,
        "has_independent_disk": has_independent_disk,
        "has_snapshot": has_snapshot,
        "snapshot_age_days": snapshot_age_days,
        "has_vgpu": has_vgpu,
        "has_usb_or_serial": has_usb_or_serial,
        "licence_mac_bound": licence_mac_bound,
        "vm_encrypted": encrypted,
        "fault_tolerance": fault_tolerant,
        "db_engine": db_engine,
        "os_eol": pd.Series(os_names).map(lambda o: OS_LOOKUP[o]["os_eol"]).values,
        "azure_os_support": pd.Series(os_names).map(lambda o: OS_LOOKUP[o]["azure_os_support"]).values,
    })

    # Derived helpers used all over the app.
    df["total_disks"] = 1 + df["data_disk_count"]
    df["allocated_vcpu_hours_month"] = df["vcpu"] * 730
    df["is_prod"] = df["environment"].isin(["Production", "DR"])
    return df


# --------------------------------------------------------------------------
# RVTools / CSV import
# --------------------------------------------------------------------------
RVTOOLS_MAP = {
    "vm": "vm_name", "VM": "vm_name", "Name": "vm_name",
    "CPUs": "vcpu", "cpu": "vcpu", "NumCPU": "vcpu",
    "Memory": "ram_mib", "memory": "ram_mib", "MemoryMB": "ram_mib",
    "Provisioned MiB": "provisioned_mib", "Provisioned MB": "provisioned_mib",
    "In Use MiB": "used_mib", "In Use MB": "used_mib",
    "OS according to the configuration file": "guest_os",
    "OS according to the VMware Tools": "guest_os_tools",
    "Guest OS": "guest_os", "Powerstate": "power_state",
    "Cluster": "cluster", "Host": "esxi_host", "Datacenter": "datacenter",
    "Disks": "total_disks", "NICs": "nic_count",
    "Firmware": "firmware", "Tools": "vmware_tools",
    "Annotation": "notes", "Folder": "folder",
}

REQUIRED = ["vm_name", "vcpu", "ram_gib", "guest_os"]


def import_inventory(df_raw: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Normalise an uploaded RVTools ``vInfo`` sheet (or a generic CSV) to the
    internal schema. Returns the frame plus a list of human-readable warnings."""
    warnings: list[str] = []
    df = df_raw.copy()
    df.columns = [str(c).strip() for c in df.columns]
    df = df.rename(columns={k: v for k, v in RVTOOLS_MAP.items() if k in df.columns})

    if "ram_gib" not in df.columns and "ram_mib" in df.columns:
        df["ram_gib"] = pd.to_numeric(df["ram_mib"], errors="coerce") / 1024.0
    if "provisioned_gib" not in df.columns and "provisioned_mib" in df.columns:
        df["provisioned_gib"] = pd.to_numeric(df["provisioned_mib"], errors="coerce") / 1024.0
    if "used_gib" not in df.columns and "used_mib" in df.columns:
        df["used_gib"] = pd.to_numeric(df["used_mib"], errors="coerce") / 1024.0

    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(
            f"Could not find required columns {missing}. "
            "Expected an RVTools vInfo export or a CSV with vm_name/vcpu/ram_gib/guest_os."
        )

    for col, default in [
        ("provisioned_gib", 100.0), ("used_gib", np.nan), ("os_disk_gib", 80.0),
        ("data_disk_count", 1), ("nic_count", 1), ("firmware", "bios"),
        ("environment", "Production"), ("criticality", CRITICALITY[2]),
        ("tier", "App"), ("cluster", "Unknown"), ("esxi_host", "unknown"),
        ("datastore", "Unknown"), ("app_name", "Unassigned"), ("db_engine", "None"),
        ("vmware_tools", "toolsOk"), ("powered_on", True),
    ]:
        if col not in df.columns:
            df[col] = default
            if col in ("environment", "criticality", "tier", "app_name"):
                warnings.append(f"'{col}' not in the upload -- defaulted to '{default}'. "
                                "Classification quality will be limited until you supply it.")

    if "power_state" in df.columns:
        df["powered_on"] = df["power_state"].astype(str).str.lower().str.contains("on")

    df["used_gib"] = pd.to_numeric(df["used_gib"], errors="coerce").fillna(
        pd.to_numeric(df["provisioned_gib"], errors="coerce") * 0.65)

    # Utilisation is usually absent from vInfo; flag it so the UI can warn that
    # right-sizing will fall back to as-provisioned sizing.
    perf_cols = ["cpu_avg_pct", "cpu_p95_pct", "mem_avg_pct", "mem_p95_pct"]
    if not any(c in df.columns for c in perf_cols):
        warnings.append(
            "No performance counters found. Right-sizing will use as-provisioned sizing "
            "(equivalent to an Azure Migrate assessment with 1-star performance coverage)."
        )
        for c in perf_cols:
            df[c] = np.nan

    for c in ["iops_avg", "iops_peak", "disk_mbps", "net_mbps", "daily_churn_pct"]:
        if c not in df.columns:
            df[c] = np.nan
    for flag in ["has_rdm", "has_shared_disk", "has_independent_disk", "has_snapshot",
                 "has_vgpu", "has_usb_or_serial", "licence_mac_bound", "vm_encrypted",
                 "fault_tolerance", "zombie_candidate"]:
        if flag not in df.columns:
            df[flag] = False
    if "snapshot_age_days" not in df.columns:
        df["snapshot_age_days"] = 0
    if "days_since_boot" not in df.columns:
        df["days_since_boot"] = 0

    df["guest_os"] = df["guest_os"].astype(str)
    df["os_family"] = np.where(
        df["guest_os"].str.contains("windows", case=False, na=False), "Windows", "Linux")
    meta = df["guest_os"].map(lambda o: OS_LOOKUP.get(o))
    df["os_eol"] = [m["os_eol"] if isinstance(m, dict) else _guess_eol(o)
                    for m, o in zip(meta, df["guest_os"])]
    df["azure_os_support"] = [m["azure_os_support"] if isinstance(m, dict) else
                              ("esu-required" if _guess_eol(o) else "supported")
                              for m, o in zip(meta, df["guest_os"])]

    df["data_disk_gib"] = (pd.to_numeric(df["provisioned_gib"], errors="coerce")
                           - pd.to_numeric(df["os_disk_gib"], errors="coerce")).clip(lower=0)
    if "total_disks" not in df.columns:
        df["total_disks"] = 1 + pd.to_numeric(df["data_disk_count"], errors="coerce").fillna(1)
    df["is_prod"] = df["environment"].astype(str).isin(["Production", "DR"])
    df["ram_gib"] = pd.to_numeric(df["ram_gib"], errors="coerce").fillna(4.0)
    df["vcpu"] = pd.to_numeric(df["vcpu"], errors="coerce").fillna(2).astype(int)
    return df, warnings


_EOL_TOKENS = ["2003", "2008", "2012", " 6 ", "centos 6", "centos 7",
               "rhel 6", "rhel 7", "red hat enterprise linux 6",
               "red hat enterprise linux 7", "ubuntu linux 14", "ubuntu linux 16",
               "ubuntu linux 18", "sles 11", "windows 7", "windows xp"]


def _guess_eol(os_name: str) -> bool:
    o = (os_name or "").lower()
    return any(tok.strip() in o for tok in _EOL_TOKENS)


def estate_summary(df: pd.DataFrame) -> dict:
    """Headline numbers for the executive dashboard."""
    return {
        "vm_count": int(len(df)),
        "powered_on": int(df["powered_on"].sum()),
        "windows_pct": float((df["os_family"] == "Windows").mean() * 100),
        "linux_pct": float((df["os_family"] == "Linux").mean() * 100),
        "total_vcpu": int(df["vcpu"].sum()),
        "total_ram_tib": float(df["ram_gib"].sum() / 1024),
        "provisioned_tib": float(df["provisioned_gib"].sum() / 1024),
        "used_tib": float(df["used_gib"].sum() / 1024),
        "mean_cpu_pct": float(pd.to_numeric(df["cpu_avg_pct"], errors="coerce").mean()),
        "mean_mem_pct": float(pd.to_numeric(df["mem_avg_pct"], errors="coerce").mean()),
        "eol_os_count": int(df["os_eol"].sum()),
        "app_count": int(df["app_name"].nunique()),
        "prod_pct": float(df["is_prod"].mean() * 100),
        "db_vms": int((df["db_engine"] != "None").sum()),
        "zombie_count": int(df["zombie_candidate"].sum()),
    }
