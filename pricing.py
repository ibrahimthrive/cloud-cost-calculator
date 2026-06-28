"""
Base pricing catalog for AWS, Azure and GCP.

Figures are illustrative, public on-demand list prices (USD, approximate,
modeled on us-east-1 / East US / us-central1) meant for cost ESTIMATION,
not billing-accurate quotes. They are seeded into SQLite on first run via
database.py so they can be edited/persisted without touching code.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class InstanceType:
    key: str
    label: str
    vcpu: int
    ram_gb: float
    hourly_usd: float


@dataclass(frozen=True)
class StorageTier:
    key: str
    label: str
    usd_per_gb_month: float


# ---------------------------------------------------------------------------
# Compute catalogs
# ---------------------------------------------------------------------------

AWS_EC2: list[InstanceType] = [
    InstanceType("t3.micro", "t3.micro (burstable)", 2, 1, 0.0104),
    InstanceType("t3.medium", "t3.medium (burstable)", 2, 4, 0.0416),
    InstanceType("m5.large", "m5.large (general purpose)", 2, 8, 0.0960),
    InstanceType("m5.xlarge", "m5.xlarge (general purpose)", 4, 16, 0.1920),
    InstanceType("c5.large", "c5.large (compute optimized)", 2, 4, 0.0850),
    InstanceType("c5.xlarge", "c5.xlarge (compute optimized)", 4, 8, 0.1700),
    InstanceType("r5.large", "r5.large (memory optimized)", 2, 16, 0.1260),
    InstanceType("r5.xlarge", "r5.xlarge (memory optimized)", 4, 32, 0.2520),
]

AZURE_VM: list[InstanceType] = [
    InstanceType("B1s", "B1s (burstable)", 1, 1, 0.0104),
    InstanceType("B2s", "B2s (burstable)", 2, 4, 0.0416),
    InstanceType("D2s_v5", "D2s v5 (general purpose)", 2, 8, 0.0960),
    InstanceType("D4s_v5", "D4s v5 (general purpose)", 4, 16, 0.1920),
    InstanceType("F2s_v2", "F2s v2 (compute optimized)", 2, 4, 0.0850),
    InstanceType("F4s_v2", "F4s v2 (compute optimized)", 4, 8, 0.1690),
    InstanceType("E2s_v5", "E2s v5 (memory optimized)", 2, 16, 0.1260),
    InstanceType("E4s_v5", "E4s v5 (memory optimized)", 4, 32, 0.2520),
]

GCP_COMPUTE: list[InstanceType] = [
    InstanceType("e2-micro", "e2-micro (shared core)", 2, 1, 0.0084),
    InstanceType("e2-medium", "e2-medium (shared core)", 2, 4, 0.0335),
    InstanceType("n2-standard-2", "n2-standard-2 (general purpose)", 2, 8, 0.0971),
    InstanceType("n2-standard-4", "n2-standard-4 (general purpose)", 4, 16, 0.1942),
    InstanceType("c2-standard-4", "c2-standard-4 (compute optimized)", 4, 16, 0.2088),
    InstanceType("n2-highmem-2", "n2-highmem-2 (memory optimized)", 2, 16, 0.1310),
    InstanceType("n2-highmem-4", "n2-highmem-4 (memory optimized)", 4, 32, 0.2620),
]

COMPUTE_CATALOGS: dict[str, list[InstanceType]] = {
    "AWS": AWS_EC2,
    "Azure": AZURE_VM,
    "GCP": GCP_COMPUTE,
}

# Discount multipliers applied to the on-demand hourly rate.
PRICING_MODELS: dict[str, dict] = {
    "On-Demand": {"discount": 0.00, "note": "Pay as you go, no commitment."},
    "Reserved 1-Year": {"discount": 0.40, "note": "~40% off for a 1-year commitment."},
    "Reserved 3-Year": {"discount": 0.60, "note": "~60% off for a 3-year commitment."},
    "Spot / Preemptible": {"discount": 0.70, "note": "~70% off, can be interrupted."},
}

# ---------------------------------------------------------------------------
# Storage catalogs (per GB / month)
# ---------------------------------------------------------------------------

AWS_S3: list[StorageTier] = [
    StorageTier("standard", "S3 Standard", 0.0230),
    StorageTier("standard_ia", "S3 Standard-IA", 0.0125),
    StorageTier("one_zone_ia", "S3 One Zone-IA", 0.0100),
    StorageTier("glacier_ir", "S3 Glacier Instant Retrieval", 0.0040),
    StorageTier("glacier_flexible", "S3 Glacier Flexible Retrieval", 0.0036),
    StorageTier("glacier_deep", "S3 Glacier Deep Archive", 0.00099),
]

AZURE_BLOB: list[StorageTier] = [
    StorageTier("hot", "Blob Hot", 0.0184),
    StorageTier("cool", "Blob Cool", 0.0100),
    StorageTier("cold", "Blob Cold", 0.0036),
    StorageTier("archive", "Blob Archive", 0.00099),
]

GCS: list[StorageTier] = [
    StorageTier("standard", "GCS Standard", 0.0200),
    StorageTier("nearline", "GCS Nearline", 0.0100),
    StorageTier("coldline", "GCS Coldline", 0.0040),
    StorageTier("archive", "GCS Archive", 0.0012),
]

STORAGE_CATALOGS: dict[str, list[StorageTier]] = {
    "AWS": AWS_S3,
    "Azure": AZURE_BLOB,
    "GCP": GCS,
}

# ---------------------------------------------------------------------------
# Network egress (per GB, after the monthly free tier)
# ---------------------------------------------------------------------------

EGRESS_PRICING: dict[str, dict] = {
    "AWS": {"free_gb": 100, "usd_per_gb": 0.0900},
    "Azure": {"free_gb": 100, "usd_per_gb": 0.0870},
    "GCP": {"free_gb": 100, "usd_per_gb": 0.1200},
}


def get_instance(provider: str, key: str) -> InstanceType:
    for inst in COMPUTE_CATALOGS[provider]:
        if inst.key == key:
            return inst
    raise KeyError(f"Unknown instance '{key}' for provider '{provider}'")


def get_storage_tier(provider: str, key: str) -> StorageTier:
    for tier in STORAGE_CATALOGS[provider]:
        if tier.key == key:
            return tier
    raise KeyError(f"Unknown storage tier '{key}' for provider '{provider}'")


def compute_monthly_cost(provider: str, instance_key: str, hours_per_month: float, pricing_model: str) -> float:
    instance = get_instance(provider, instance_key)
    discount = PRICING_MODELS[pricing_model]["discount"]
    effective_rate = instance.hourly_usd * (1 - discount)
    return effective_rate * hours_per_month


def storage_monthly_cost(provider: str, tier_key: str, size_gb: float) -> float:
    tier = get_storage_tier(provider, tier_key)
    return tier.usd_per_gb_month * size_gb


def egress_monthly_cost(provider: str, egress_gb: float) -> float:
    cfg = EGRESS_PRICING[provider]
    billable_gb = max(0.0, egress_gb - cfg["free_gb"])
    return billable_gb * cfg["usd_per_gb"]
