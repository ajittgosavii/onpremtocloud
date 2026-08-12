"""Check the provider comparison against the reference estate."""
from core import assessment, inventory, providers, rightsizing


def main() -> None:
    est = inventory.generate_estate(547, 0.60)
    sized = rightsizing.rightsize(est, rightsizing.SizingPolicy())
    sized = assessment.assess_readiness(sized)

    win = sized[sized["os_family"] == "Windows"]
    s = inventory.estate_summary(est)
    blocked = int((sized["readiness"] == assessment.NOT_READY).sum())
    sql = int((est["db_engine"] == "Microsoft SQL Server").sum())
    ora = int((est["db_engine"] == "Oracle Database").sum())
    eol_win = int(((est["os_family"] == "Windows") & est["os_eol"]).sum())

    print("--- live AWS Windows premium ---")
    aws = providers.aws_windows_premium("eastus")
    print(f"region       : {aws['region_label']}")
    print(f"instances    : {aws['instance_count']}")
    print(f"per vCPU/hr  : ${aws['per_vcpu_hr']:.4f}")
    print(aws["detail"].head(6).to_string(index=False))
    print(f"AWS Linux $/vCPU/hr (m-family median): "
          f"{providers.aws_linux_rate_per_vcpu('eastus'):.4f}")

    from core import pricing
    az = pricing.vm_prices("eastus")
    az_prem = (az["win_licence_hr"] / az["arm_sku_name"].map(
        lambda n: 1)).dropna()
    # Derive Azure's per-vCPU Windows premium from a known SKU.
    row = az[az["arm_sku_name"] == "Standard_D4s_v5"].iloc[0]
    azure_per_vcpu = float(row["win_licence_hr"]) / 4
    print(f"\nAzure Windows premium per vCPU/hr: ${azure_per_vcpu:.4f} "
          f"(from Standard_D4s_v5, live)")

    inp = providers.LicensingInputs(
        windows_vcpu=int(sized[sized["os_family"] == "Windows"]["azure_vcpu"].sum()),
        windows_vms=len(win), sql_vms=sql, eol_windows_vms=eol_win, oracle_vms=ora,
        linux_vcpu=int(sized[sized["os_family"] == "Linux"]["azure_vcpu"].sum()),
        total_vcpu=int(sized["azure_vcpu"].sum()),
        owns_software_assurance=True,
        azure_windows_premium_per_vcpu_hr=azure_per_vcpu,
        aws_windows_premium_per_vcpu_hr=aws["per_vcpu_hr"],
    )
    print(f"\nWindows vCPU in Azure target: {inp.windows_vcpu:,}  "
          f"(Windows VMs {inp.windows_vms}, SQL {sql}, Oracle {ora}, EOL Windows {eol_win})")

    print("\n--- licensing comparison, WITH Software Assurance ---")
    lic = providers.licensing_comparison(inp)
    print(lic[["provider", "windows_licence", "dedicated_tenancy_premium", "esu",
               "total_annual", "delta_vs_best"]].round(0).to_string(index=False))

    print("\n--- licensing comparison, NO Software Assurance ---")
    import dataclasses
    lic2 = providers.licensing_comparison(
        dataclasses.replace(inp, owns_software_assurance=False))
    print(lic2[["provider", "windows_licence", "dedicated_tenancy_premium", "esu",
                "total_annual", "delta_vs_best"]].round(0).to_string(index=False))

    w = providers.estate_weights(s["windows_pct"], sql, ora, s["eol_os_count"],
                                 blocked, len(est))
    rank = providers.rank_providers(w)
    print("\n--- provider fit ---")
    print(rank[["provider", "fit_score"]].to_string(index=False))

    rec = providers.recommendation(rank, lic, s["windows_pct"], sql,
                                   eol_win, ora, len(est))
    print(f"\nRECOMMENDATION: {rec['winner'].name}   confidence={rec['confidence']}")
    print(f"Licensing advantage vs {rec['licensing_advantage_vs']}: "
          f"${rec['licensing_advantage_annual']:,.0f}/yr")
    for r in rec["reasons"]:
        print("  * " + r.replace("**", "")[:150])
    print("\n" + rec["counter"].replace("**", "")[:260])
    print("\nPROVIDER TEST OK")


if __name__ == "__main__":
    main()
