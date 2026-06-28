"""Rule-based cost optimization advisor.

Looks at the shape of the user's workload (uptime, workload tolerance,
instance size vs. declared need, storage access pattern, egress volume)
and returns actionable suggestions with an estimated USD/month saving.
"""

from dataclasses import dataclass

import pricing as p


@dataclass
class Suggestion:
    title: str
    detail: str
    estimated_monthly_savings: float
    severity: str  # "high", "medium", "low"


def _uptime_ratio(hours_per_month: float) -> float:
    return hours_per_month / 730.0


def suggest_compute(provider: str, instance_key: str, hours_per_month: float, pricing_model: str,
                     workload_tolerance: str, monthly_compute_cost: float) -> list[Suggestion]:
    suggestions: list[Suggestion] = []
    uptime = _uptime_ratio(hours_per_month)
    instance = p.get_instance(provider, instance_key)
    on_demand_cost = instance.hourly_usd * hours_per_month

    if pricing_model == "On-Demand" and uptime >= 0.70:
        reserved_cost = on_demand_cost * (1 - p.PRICING_MODELS["Reserved 1-Year"]["discount"])
        suggestions.append(Suggestion(
            title="Switch to a 1-Year Reserved Instance",
            detail=(f"This workload runs ~{hours_per_month:.0f} h/month ({uptime:.0%} uptime). "
                    "Steady, always-on workloads are cheaper with a 1-year reservation than On-Demand."),
            estimated_monthly_savings=max(0.0, monthly_compute_cost - reserved_cost),
            severity="high",
        ))

    if pricing_model in ("On-Demand", "Reserved 1-Year") and workload_tolerance == "Fault-tolerant / batch":
        spot_cost = on_demand_cost * (1 - p.PRICING_MODELS["Spot / Preemptible"]["discount"])
        suggestions.append(Suggestion(
            title="Use Spot / Preemptible capacity",
            detail=("The workload was marked fault-tolerant, so interruptions are acceptable. "
                    "Spot/preemptible instances offer the deepest discount for this profile."),
            estimated_monthly_savings=max(0.0, monthly_compute_cost - spot_cost),
            severity="high",
        ))

    if workload_tolerance == "Light / dev-test" and instance.vcpu >= 4:
        smaller_candidates = [i for i in p.COMPUTE_CATALOGS[provider] if i.vcpu < instance.vcpu]
        if smaller_candidates:
            cheapest = min(smaller_candidates, key=lambda i: i.hourly_usd)
            rightsized_cost = cheapest.hourly_usd * hours_per_month * (1 - p.PRICING_MODELS[pricing_model]["discount"])
            suggestions.append(Suggestion(
                title=f"Rightsize down to {cheapest.label}",
                detail=("A light/dev-test workload is unlikely to need "
                        f"{instance.vcpu} vCPUs / {instance.ram_gb} GB RAM around the clock."),
                estimated_monthly_savings=max(0.0, monthly_compute_cost - rightsized_cost),
                severity="medium",
            ))

    if uptime < 0.35 and pricing_model != "On-Demand":
        suggestions.append(Suggestion(
            title="Reconsider the reservation/commitment",
            detail=("This instance is used less than 35% of the month. Commitment-based discounts "
                    "(Reserved) only pay off for steady, high-utilization workloads — On-Demand or "
                    "scheduling auto-stop/start may be cheaper here."),
            estimated_monthly_savings=0.0,
            severity="medium",
        ))

    return suggestions


def suggest_storage(provider: str, tier_key: str, access_pattern: str, monthly_storage_cost: float,
                     size_gb: float) -> list[Suggestion]:
    suggestions: list[Suggestion] = []
    tiers = p.STORAGE_CATALOGS[provider]
    current_tier = p.get_storage_tier(provider, tier_key)

    cold_keys = {"glacier_deep", "glacier_flexible", "glacier_ir", "archive", "coldline"}
    cool_keys = {"standard_ia", "one_zone_ia", "cool", "cold", "nearline"}

    target_keys: set[str] = set()
    if access_pattern == "Rarely accessed (archive)":
        target_keys = cold_keys
    elif access_pattern == "Infrequently accessed":
        target_keys = cool_keys

    if target_keys and current_tier.key not in target_keys:
        candidates = [t for t in tiers if t.key in target_keys]
        if candidates:
            cheapest = min(candidates, key=lambda t: t.usd_per_gb_month)
            new_cost = cheapest.usd_per_gb_month * size_gb
            if new_cost < monthly_storage_cost:
                suggestions.append(Suggestion(
                    title=f"Move data to {cheapest.label}",
                    detail=(f"Storage marked '{access_pattern.lower()}' is currently on "
                            f"{current_tier.label}, a tier priced for frequent access."),
                    estimated_monthly_savings=monthly_storage_cost - new_cost,
                    severity="high" if access_pattern == "Rarely accessed (archive)" else "medium",
                ))

    return suggestions


def suggest_egress(provider: str, egress_gb: float, monthly_egress_cost: float) -> list[Suggestion]:
    suggestions = []
    if monthly_egress_cost > 50:
        suggestions.append(Suggestion(
            title="Front high-egress traffic with a CDN",
            detail=(f"Estimated egress of {egress_gb:.0f} GB/month is generating "
                    f"${monthly_egress_cost:,.2f} in transfer costs. Caching static/streamable "
                    "content at the edge (CloudFront, Azure CDN, Cloud CDN) typically cuts "
                    "origin egress by 60-90%."),
            estimated_monthly_savings=monthly_egress_cost * 0.6,
            severity="high" if monthly_egress_cost > 200 else "medium",
        ))
    return suggestions


def all_suggestions(config: dict) -> list[Suggestion]:
    suggestions: list[Suggestion] = []
    suggestions += suggest_compute(
        config["provider"], config["instance_key"], config["hours_per_month"],
        config["pricing_model"], config["workload_tolerance"], config["monthly_compute_cost"],
    )
    suggestions += suggest_storage(
        config["provider"], config["storage_tier"], config["access_pattern"],
        config["monthly_storage_cost"], config["storage_gb"],
    )
    suggestions += suggest_egress(config["provider"], config["egress_gb"], config["monthly_egress_cost"])
    return sorted(suggestions, key=lambda s: s.estimated_monthly_savings, reverse=True)
