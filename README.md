# ☁️ Cloud Cost Calculator

An interactive Streamlit application for estimating and comparing **AWS**, **Azure** and **GCP**
costs across compute, storage and network egress — with currency conversion, rule-based cost
optimization advice, historical tracking, a mock REST API, and PDF export.

> Pricing figures in `pricing.py` are illustrative public on-demand list prices (USD), intended
> for **estimation**, not billing-accurate quotes. Edit `pricing.py` and re-run the app to refresh
> the seeded SQLite catalog with your own numbers.

## Features

- **Compute pricing** — AWS EC2, Azure VM, GCP Compute Engine, with On-Demand / Reserved (1 & 3
  year) / Spot-Preemptible pricing models.
- **Storage pricing** — S3, Azure Blob, GCS across Standard/Hot, IA/Cool, and Archive/Cold tiers.
- **Network egress** — per-GB pricing with a free-tier allowance per provider.
- **Currency converter** — live rates via exchangerate.host, cached in SQLite (1 hour TTL) with
  an offline static fallback.
- **Cost optimization advisor** — rule-based suggestions: Reserved Instances for steady workloads,
  Spot/Preemptible for fault-tolerant workloads, rightsizing for oversized dev/test instances,
  storage tiering for cold/rarely-accessed data, and CDN recommendations for high egress.
- **Visualizations** — Plotly cost-breakdown donut charts, monthly-vs-yearly bars, and a stacked
  provider comparison chart.
- **Persistence** — SQLite stores saved estimates (history), the base pricing catalog, and the
  exchange-rate cache.
- **Mock REST API** — a Flask API (`mock_api.py`) exposing `/api/estimate` and pricing lookups,
  runnable standalone or as a background thread from the app's "Mock API" page.
- **PDF export** — download a clean, branded PDF summary of any estimate.

## Project Structure

```
cloud-cost-calculator/
├── app.py                 # Streamlit UI, navigation, charts (entry point)
├── pricing.py              # AWS/Azure/GCP pricing catalogs + cost math
├── currency.py             # Live + cached currency conversion
├── database.py             # SQLite schema, seeding, CRUD
├── optimization.py          # Rule-based cost optimization engine
├── pdf_report.py            # PDF report generation (fpdf2)
├── mock_api.py              # Standalone/background Flask REST API
├── assets/style.css          # Custom branding/CSS
├── .streamlit/config.toml     # Streamlit theme + server config
├── data/                     # SQLite database file (created at runtime)
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## Running Locally

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

The app opens at `http://localhost:8501`.

## Running with Docker

```bash
docker compose up --build
```

This builds the image from the included `Dockerfile`, mounts a named volume for the SQLite
database (`/app/data`), and serves the app at `http://localhost:8501`. A container healthcheck
hits Streamlit's `/_stcore/health` endpoint.

To run the image directly without compose:

```bash
docker build -t cloud-cost-calculator .
docker run -p 8501:8501 -v cost-calculator-data:/app/data cloud-cost-calculator
```

## Mock REST API

From the app's **Mock API** page you can start a Flask API on port 8502 in a background thread.
It can also run completely standalone (e.g. in its own container or CI job):

```bash
python mock_api.py
# Serves on http://localhost:8502
```

Example:

```bash
curl -X POST http://localhost:8502/api/estimate \
  -H "Content-Type: application/json" \
  -d '{
        "provider": "AWS",
        "instance_key": "m5.large",
        "hours_per_month": 730,
        "pricing_model": "On-Demand",
        "storage_tier": "standard",
        "storage_gb": 100,
        "egress_gb": 50
      }'
```

## Deploying to Azure App Service

These steps deploy the Streamlit container to **Azure App Service for Containers** (Linux).

### 1. Build and push the image to a registry

```bash
az acr create --resource-group <rg-name> --name <acrName> --sku Basic
az acr login --name <acrName>

docker build -t <acrName>.azurecr.io/cloud-cost-calculator:latest .
docker push <acrName>.azurecr.io/cloud-cost-calculator:latest
```

### 2. Create the App Service plan and web app

```bash
az appservice plan create \
  --name cost-calculator-plan \
  --resource-group <rg-name> \
  --is-linux \
  --sku B1

az webapp create \
  --resource-group <rg-name> \
  --plan cost-calculator-plan \
  --name <app-name> \
  --deployment-container-image-name <acrName>.azurecr.io/cloud-cost-calculator:latest
```

### 3. Point the Web App at your registry

```bash
az webapp config container set \
  --name <app-name> \
  --resource-group <rg-name> \
  --container-image-name <acrName>.azurecr.io/cloud-cost-calculator:latest \
  --container-registry-url https://<acrName>.azurecr.io
```

### 4. Configure the port and startup command

Streamlit must bind to the port App Service expects (`WEBSITES_PORT`) and to `0.0.0.0`:

```bash
az webapp config appsettings set \
  --resource-group <rg-name> \
  --name <app-name> \
  --settings WEBSITES_PORT=8000

az webapp config set \
  --resource-group <rg-name> \
  --name <app-name> \
  --startup-file "streamlit run app.py --server.port 8000 --server.address 0.0.0.0 --server.headless true"
```

### 5. (Optional) Persist SQLite data across restarts

App Service container filesystems are ephemeral. To persist `data/cost_calculator.db`, mount
Azure Storage as the app's persistent path:

```bash
az webapp config storage-account add \
  --resource-group <rg-name> \
  --name <app-name> \
  --custom-id costdata \
  --storage-type AzureFiles \
  --share-name cost-calculator-data \
  --account-name <storageAccountName> \
  --access-key <storageAccountKey> \
  --mount-path /app/data
```

### 6. Browse the app

```bash
az webapp browse --resource-group <rg-name> --name <app-name>
```

Subsequent code changes: rebuild, push the image with a new tag, update the web app's container
image setting, and Azure will restart the container automatically.

## Editing Pricing Data

All catalogs live in `pricing.py` as plain dataclasses (`InstanceType`, `StorageTier`) and dicts
(`PRICING_MODELS`, `EGRESS_PRICING`). On first run, `database.seed_pricing_catalog()` copies them
into the `pricing_catalog` SQLite table so historical estimates remain traceable even if the
in-code catalog later changes.

## Tech Stack

Streamlit · Plotly · pandas · SQLite · Flask (mock API) · fpdf2 (PDF export) · requests
(exchange rates)
