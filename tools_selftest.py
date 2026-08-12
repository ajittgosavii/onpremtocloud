"""Offline self-test: exercises the pricing client and the engines end to end.

Run with:  py -3.12 tools_selftest.py
"""
import sys


def test_pricing():
    from core import pricing
    print("probe:", pricing.probe())
    vm = pricing.vm_prices("eastus")
    print("vm rows:", len(vm), "source:", vm.attrs.get("source"))
    print(vm[vm.arm_sku_name.isin(["Standard_D4s_v5", "Standard_E8s_v5", "Standard_B2ms"])].to_string())
    d = pricing.disk_prices("eastus")
    print("disk rows:", len(d))
    print(d[d.tier.isin(["P10", "P30", "E30", "S30"])].to_string())
    ri = pricing.vm_reservation_prices("eastus")
    print("ri rows:", len(ri))
    print(ri[ri.arm_sku_name == "Standard_D4s_v5"].to_string())
    sp = pricing.vm_savings_plan_prices("eastus")
    print("sp rows:", len(sp))
    print(sp[sp.arm_sku_name == "Standard_D4s_v5"].to_string())
    print("egress $/GB:", pricing.egress_price("eastus"))
    print("backup:", pricing.backup_price("eastus"))
    print("asr $/instance/mo:", pricing.site_recovery_price())


def test_engines():
    """Full deterministic chain: estate -> sizing -> readiness -> 7R -> cost -> effort
    -> waves -> schedule -> Monte Carlo -> TCO -> Azure Migrate simulation."""
    import pandas as pd
    from core import (inventory, rightsizing, assessment, costing, complexity,
                      waves, montecarlo, tco, azure_migrate_sim, platforms, tools_market)

    est = inventory.generate_estate(547, 0.60)
    summ = inventory.estate_summary(est)
    print("ESTATE:", {k: round(v, 1) if isinstance(v, float) else v for k, v in summ.items()})
    assert len(est) == 547
    assert abs(summ["windows_pct"] - 60) < 0.5, summ["windows_pct"]

    pol = rightsizing.SizingPolicy()
    sized = rightsizing.rightsize(est, pol)
    print("SIZING:", {k: round(v, 1) if isinstance(v, float) else v
                      for k, v in rightsizing.sizing_delta_summary(sized).items()})

    sized = assessment.assess_readiness(sized)
    print("READINESS:\n", assessment.readiness_summary(sized).to_string(index=False))
    sized = assessment.dispose(sized)
    print("7R:\n", assessment.disposition_summary(sized).to_string(index=False))
    print("TOP BLOCKERS:\n", assessment.top_blockers(sized, 5).to_string(index=False))

    pb = costing.load_price_book("eastus", "USD")
    cpol = costing.CommercialPolicy()
    costed = costing.compute_costs(sized, pb, cpol)
    cs = costing.cost_summary(costed, cpol)
    print("COST:", {k: round(v, 1) if isinstance(v, float) else v for k, v in cs.items()})
    assert cs["monthly_total"] > 0
    assert cs["priced_from_api_pct"] > 95, f"only {cs['priced_from_api_pct']:.0f}% priced from API"
    print("BREAKDOWN:\n", costing.cost_breakdown_frame(costed).to_string(index=False))
    print("LEVERS:\n", costing.lever_sensitivity(sized, pb, cpol).to_string(index=False))

    em = complexity.EffortModel()
    scored = complexity.score_estate(costed, em)
    es = complexity.effort_summary(scored, em)
    print("EFFORT:", {k: round(v, 1) for k, v in es.items()})
    print("COMPLEXITY BANDS:\n", complexity.complexity_distribution(scored).to_string(index=False))
    print("FACTORS:\n", complexity.factor_contribution(scored, em).head(5).to_string(index=False))

    wp = waves.WavePlan()
    waved = waves.build_waves(scored, wp)
    sched = waves.simulate_schedule(waved, wp)
    ss = waves.schedule_summary(sched, wp)
    print("SCHEDULE:", {k: (round(v, 1) if isinstance(v, float) else v) for k, v in ss.items()})
    print(sched[["wave_name", "vms", "data_tib", "duration_days", "binding_constraint"]]
          .to_string(index=False))
    print("BANDWIDTH CURVE:\n", waves.bandwidth_curve(waved, wp).to_string(index=False))
    print("SEED ADVICE:", waves.offline_seed_advice(ss["data_tib"], wp))

    op = tco.OnPremProfile()
    op = tco.calibrate_onprem_to_estate(op, summ["total_vcpu"], summ["total_ram_tib"] * 1024,
                                        summ["provisioned_tib"])
    print("ONPREM hosts:", op.hosts, "storage TiB:", op.storage_tib_usable)
    az = tco.AzureProfile(azure_monthly_run=cs["monthly_total"], migration_one_off=es["migration_cost"])
    t = tco.build_tco(op, az, tco.TcoInputs())
    print("TCO:", {k: round(v, 1) if isinstance(v, float) else v
                   for k, v in tco.tco_summary(t, tco.TcoInputs()).items()})
    print(t[["year", "stay_on_vmware", "migrate_total", "annual_delta"]].round(0).to_string(index=False))

    det = montecarlo.Deterministic(
        migration_cost=es["migration_cost"], effort_hours=es["total_effort_hours"],
        team_hours_per_day=wp.team_hours_per_day, elapsed_days=ss["elapsed_days"],
        replication_days=float(sched["replication_days"].sum()),
        engineering_days=float(sched["engineering_days"].sum()),
        azure_monthly_cost=cs["monthly_total"],
        onprem_monthly_cost=tco.onprem_monthly_total(op),
        expected_rollbacks=ss["expected_rollbacks"], vm_count=547,
        cost_per_vm=es["cost_per_vm"])
    sim = montecarlo.run(det, montecarlo.SimulationInputs(iterations=4000))
    print("MONTE CARLO:\n", montecarlo.percentiles(sim).round(1).to_string(index=False))
    print("TORNADO:\n", montecarlo.tornado(sim).head(5).round(3).to_string(index=False))
    for line in montecarlo.confidence_statement(sim, 4_000_000, 14):
        print(" *", line)

    cfg = azure_migrate_sim.MigrateConfig()
    phases, msum = azure_migrate_sim.simulate(est, cfg, sized=costed)
    print("AZURE MIGRATE:", {k: v for k, v in msum.items() if k != "appliance_plan"})
    print("APPLIANCE:", msum["appliance_plan"]["rationale"])
    for p in phases:
        print(f"  {p.name}: {p.duration_days:.1f}d")
    print(azure_migrate_sim.phases_frame(phases).to_string(index=False))

    print("PLATFORM RANK:\n",
          platforms.rank_platforms("Escape Broadcom licensing")[["platform", "fit_score"]]
          .head(5).to_string(index=False))
    al = platforms.azure_local_cost(platforms.AzureLocalInputs(
        total_vcpu=summ["total_vcpu"], total_ram_gib=summ["total_ram_tib"] * 1024,
        provisioned_tib=summ["provisioned_tib"]))
    print("AZURE LOCAL:", al["nodes"], "nodes,", f"{al['annual_total']:,.0f}/yr")
    print(al["breakdown"].to_string(index=False))
    avs = platforms.size_avs(summ["total_vcpu"], summ["total_ram_tib"] * 1024, summ["used_tib"])
    print("AVS SIZING:", avs["hosts"], "x", avs["node"], "-- bound by", avs["binding_constraint"])
    print("PLATFORM COST:\n", platforms.platform_cost_comparison(
        cs["monthly_total"], tco.onprem_monthly_total(op), al, avs).to_string(index=False))

    print("TOOLS RANK:\n", tools_market.rank_tools("Fast, low-cost data centre exit")
          [["tool", "fit_score"]].head(5).to_string(index=False))
    eol = float(est["os_eol"].mean() * 100)
    blocked = float((sized["readiness"] == assessment.NOT_READY).mean() * 100)
    for s in tools_market.recommended_stack("Fast, low-cost data centre exit", 547, eol, blocked):
        print(f"  [{s['role']}] {s['tool']}")

    print("\nALL ENGINES OK")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "pricing"
    globals()[f"test_{which}"]()
