"""
Cloud Cost Calculator
======================
An interactive Streamlit application for estimating AWS / Azure / GCP
compute, storage and network egress costs, comparing providers,
getting rule-based cost optimization advice, and exporting a PDF report.

Run:
    streamlit run app.py
"""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import currency
import database
import mock_api
import optimization
import pdf_report
import pricing as p

st.set_page_config(
    page_title="Cloud Cost Calculator",
    page_icon="☁️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

@st.cache_resource
def bootstrap():
    database.init_db()
    database.seed_pricing_catalog()
    return True


def inject_css():
    css_path = Path(__file__).parent / "assets" / "style.css"
    st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)


bootstrap()
inject_css()

PROVIDERS = ["AWS", "Azure", "GCP"]
WORKLOAD_TOLERANCE_OPTIONS = ["Steady / production", "Fault-tolerant / batch", "Light / dev-test"]
ACCESS_PATTERN_OPTIONS = ["Frequently accessed", "Infrequently accessed", "Rarely accessed (archive)"]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def metric_card(label: str, value: str, col):
    col.markdown(
        f"""<div class="cc-metric-card">
                <div class="label">{label}</div>
                <div class="value">{value}</div>
            </div>""",
        unsafe_allow_html=True,
    )


def severity_badge(severity: str) -> str:
    return f'<span class="cc-badge cc-badge-{severity}">{severity.upper()}</span>'


def render_suggestions(suggestions):
    if not suggestions:
        st.success("No major optimization opportunities detected for this configuration. 🎉")
        return
    for s in suggestions:
        saving = f" — potential saving: ${s.estimated_monthly_savings:,.2f}/mo" if s.estimated_monthly_savings > 0 else ""
        st.markdown(
            f"""<div class="cc-suggestion-card">
                    {severity_badge(s.severity)}<b>{s.title}</b>{saving}
                    <div style="color:#6C757D;margin-top:4px;font-size:0.88rem;">{s.detail}</div>
                </div>""",
            unsafe_allow_html=True,
        )


def cost_breakdown_chart(compute, storage, egress):
    fig = go.Figure(data=[go.Pie(
        labels=["Compute", "Storage", "Network Egress"],
        values=[compute, storage, egress],
        hole=0.45,
        marker=dict(colors=["#1062E0", "#34A853", "#F4B400"]),
    )])
    fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=320, showlegend=True)
    return fig


def monthly_vs_yearly_chart(monthly, yearly):
    fig = go.Figure(data=[
        go.Bar(name="Cost (USD)", x=["Monthly", "Yearly"], y=[monthly, yearly],
               marker_color=["#1062E0", "#0B3D91"], text=[f"${monthly:,.0f}", f"${yearly:,.0f}"],
               textposition="outside"),
    ])
    fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=320, showlegend=False)
    return fig


def compute_estimate(provider, instance_key, hours_per_month, pricing_model,
                      storage_tier, storage_gb, egress_gb):
    compute_usd = p.compute_monthly_cost(provider, instance_key, hours_per_month, pricing_model)
    storage_usd = p.storage_monthly_cost(provider, storage_tier, storage_gb)
    egress_usd = p.egress_monthly_cost(provider, egress_gb)
    monthly_total = compute_usd + storage_usd + egress_usd
    return {
        "compute_usd": compute_usd,
        "storage_usd": storage_usd,
        "egress_usd": egress_usd,
        "monthly_total_usd": monthly_total,
        "yearly_total_usd": monthly_total * 12,
    }


# ---------------------------------------------------------------------------
# Page: Calculator
# ---------------------------------------------------------------------------

def page_calculator():
    st.markdown(
        """<div class="cc-hero">
                <h1>☁️ Cloud Cost Calculator</h1>
                <p>Estimate AWS, Azure and GCP spend across compute, storage and network egress —
                   with currency conversion and cost optimization advice.</p>
            </div>""",
        unsafe_allow_html=True,
    )

    left, right = st.columns([1, 1.4], gap="large")

    with left:
        st.subheader("Configuration")
        provider = st.selectbox("Cloud Provider", PROVIDERS)

        instances = p.COMPUTE_CATALOGS[provider]
        instance_labels = {i.label: i.key for i in instances}
        instance_label = st.selectbox("Instance Type", list(instance_labels.keys()))
        instance_key = instance_labels[instance_label]
        instance = p.get_instance(provider, instance_key)
        st.caption(f"{instance.vcpu} vCPU · {instance.ram_gb} GB RAM · ${instance.hourly_usd:.4f}/hr on-demand")

        pricing_model = st.selectbox("Pricing Model", list(p.PRICING_MODELS.keys()))
        st.caption(p.PRICING_MODELS[pricing_model]["note"])

        hours_per_month = st.slider("Compute Hours / Month", 0, 730, 730, step=10)
        workload_tolerance = st.selectbox("Workload Tolerance", WORKLOAD_TOLERANCE_OPTIONS)

        st.divider()
        tiers = p.STORAGE_CATALOGS[provider]
        tier_labels = {t.label: t.key for t in tiers}
        storage_label = st.selectbox("Storage Tier", list(tier_labels.keys()))
        storage_tier = tier_labels[storage_label]
        storage_gb = st.number_input("Storage Size (GB)", min_value=0.0, value=100.0, step=10.0)
        access_pattern = st.selectbox("Storage Access Pattern", ACCESS_PATTERN_OPTIONS)

        st.divider()
        egress_gb = st.number_input("Network Egress (GB / month)", min_value=0.0, value=50.0, step=10.0)
        st.caption(f"First {p.EGRESS_PRICING[provider]['free_gb']} GB/month free on {provider}.")

        st.divider()
        target_currency = st.selectbox("Display Currency", currency.SUPPORTED_CURRENCIES)
        estimate_name = st.text_input("Estimate Name (for saving)", value=f"{provider} {instance_label}")

    breakdown = compute_estimate(provider, instance_key, hours_per_month, pricing_model,
                                  storage_tier, storage_gb, egress_gb)
    monthly_converted, rate_source = currency.convert(breakdown["monthly_total_usd"], target_currency)
    yearly_converted, _ = currency.convert(breakdown["yearly_total_usd"], target_currency)
    breakdown["monthly_total_converted"] = monthly_converted
    breakdown["yearly_total_converted"] = yearly_converted

    with right:
        st.subheader("Estimated Cost")
        c1, c2, c3 = st.columns(3)
        metric_card("Compute / mo", f"${breakdown['compute_usd']:,.2f}", c1)
        metric_card("Storage / mo", f"${breakdown['storage_usd']:,.2f}", c2)
        metric_card("Egress / mo", f"${breakdown['egress_usd']:,.2f}", c3)

        c4, c5 = st.columns(2)
        metric_card("Monthly Total (USD)", f"${breakdown['monthly_total_usd']:,.2f}", c4)
        metric_card("Yearly Total (USD)", f"${breakdown['yearly_total_usd']:,.2f}", c5)

        if target_currency != "USD":
            c6, c7 = st.columns(2)
            metric_card(f"Monthly Total ({target_currency})", f"{monthly_converted:,.2f}", c6)
            metric_card(f"Yearly Total ({target_currency})", f"{yearly_converted:,.2f}", c7)
            st.caption(f"Exchange rate source: **{rate_source}**")

        tab1, tab2 = st.tabs(["Cost Breakdown", "Monthly vs Yearly"])
        with tab1:
            st.plotly_chart(cost_breakdown_chart(breakdown["compute_usd"], breakdown["storage_usd"],
                                                  breakdown["egress_usd"]), use_container_width=True)
        with tab2:
            st.plotly_chart(monthly_vs_yearly_chart(breakdown["monthly_total_usd"],
                                                     breakdown["yearly_total_usd"]), use_container_width=True)

        st.subheader("💡 Cost Optimization Suggestions")
        opt_config = {
            "provider": provider, "instance_key": instance_key, "hours_per_month": hours_per_month,
            "pricing_model": pricing_model, "workload_tolerance": workload_tolerance,
            "monthly_compute_cost": breakdown["compute_usd"], "storage_tier": storage_tier,
            "access_pattern": access_pattern, "monthly_storage_cost": breakdown["storage_usd"],
            "storage_gb": storage_gb, "egress_gb": egress_gb, "monthly_egress_cost": breakdown["egress_usd"],
        }
        suggestions = optimization.all_suggestions(opt_config)
        render_suggestions(suggestions)

        st.divider()
        b1, b2 = st.columns(2)
        with b1:
            if st.button("💾 Save Estimate", use_container_width=True):
                database.save_estimate(
                    estimate_name, provider, opt_config, breakdown["monthly_total_usd"],
                    breakdown["yearly_total_usd"], target_currency, monthly_converted,
                )
                st.success(f"Saved '{estimate_name}' to history.")
        with b2:
            config_for_pdf = {
                "provider": provider, "instance_label": instance_label, "pricing_model": pricing_model,
                "hours_per_month": hours_per_month, "storage_label": storage_label,
                "storage_gb": storage_gb, "egress_gb": egress_gb,
            }
            pdf_bytes = pdf_report.build_report(config_for_pdf, breakdown, suggestions, target_currency)
            st.download_button(
                "📄 Download PDF Report", data=pdf_bytes,
                file_name=f"{provider.lower()}_cost_estimate.pdf", mime="application/pdf",
                use_container_width=True,
            )


# ---------------------------------------------------------------------------
# Page: Compare Providers
# ---------------------------------------------------------------------------

def page_compare():
    st.header("📊 Compare Providers")
    st.caption("Pick a comparable instance on each provider and shared storage/egress assumptions "
                "to see a side-by-side monthly cost comparison.")

    hours_per_month = st.slider("Compute Hours / Month", 0, 730, 730, step=10, key="cmp_hours")
    storage_gb = st.number_input("Storage Size (GB)", min_value=0.0, value=100.0, step=10.0, key="cmp_storage")
    egress_gb = st.number_input("Network Egress (GB / month)", min_value=0.0, value=50.0, step=10.0, key="cmp_egress")

    rows = []
    cols = st.columns(3)
    selections = {}
    for col, provider in zip(cols, PROVIDERS):
        with col:
            st.markdown(f"**{provider}**")
            instances = p.COMPUTE_CATALOGS[provider]
            instance_labels = {i.label: i.key for i in instances}
            instance_label = st.selectbox("Instance", list(instance_labels.keys()), key=f"cmp_inst_{provider}")
            pricing_model = st.selectbox("Pricing Model", list(p.PRICING_MODELS.keys()), key=f"cmp_model_{provider}")
            tiers = p.STORAGE_CATALOGS[provider]
            tier_labels = {t.label: t.key for t in tiers}
            storage_label = st.selectbox("Storage Tier", list(tier_labels.keys()), key=f"cmp_tier_{provider}")
            selections[provider] = (instance_labels[instance_label], pricing_model, tier_labels[storage_label])

    for provider in PROVIDERS:
        instance_key, pricing_model, storage_tier = selections[provider]
        breakdown = compute_estimate(provider, instance_key, hours_per_month, pricing_model,
                                      storage_tier, storage_gb, egress_gb)
        rows.append({"Provider": provider, "Compute": breakdown["compute_usd"],
                     "Storage": breakdown["storage_usd"], "Egress": breakdown["egress_usd"],
                     "Monthly Total": breakdown["monthly_total_usd"],
                     "Yearly Total": breakdown["yearly_total_usd"]})

    df = pd.DataFrame(rows)
    st.divider()
    st.dataframe(df.style.format({c: "${:,.2f}" for c in df.columns if c != "Provider"}),
                 use_container_width=True, hide_index=True)

    fig = go.Figure(data=[
        go.Bar(name="Compute", x=df["Provider"], y=df["Compute"], marker_color="#1062E0"),
        go.Bar(name="Storage", x=df["Provider"], y=df["Storage"], marker_color="#34A853"),
        go.Bar(name="Egress", x=df["Provider"], y=df["Egress"], marker_color="#F4B400"),
    ])
    fig.update_layout(barmode="stack", height=380, margin=dict(t=20, b=10, l=10, r=10),
                       yaxis_title="USD / month")
    st.plotly_chart(fig, use_container_width=True)

    cheapest = df.loc[df["Monthly Total"].idxmin()]
    st.info(f"💰 **{cheapest['Provider']}** is the cheapest option for this configuration at "
            f"**${cheapest['Monthly Total']:,.2f}/month**.")


# ---------------------------------------------------------------------------
# Page: History
# ---------------------------------------------------------------------------

def page_history():
    st.header("🗂 Saved Estimates")
    estimates = database.list_estimates()
    if not estimates:
        st.info("No saved estimates yet. Save one from the Calculator page.")
        return

    df = pd.DataFrame(estimates)[["id", "name", "created_at", "provider", "monthly_usd", "yearly_usd",
                                  "currency", "monthly_converted"]]
    df.columns = ["ID", "Name", "Created (UTC)", "Provider", "Monthly (USD)", "Yearly (USD)",
                  "Currency", "Monthly (Converted)"]
    st.dataframe(df, use_container_width=True, hide_index=True)

    fig = go.Figure(data=[go.Bar(x=df["Name"], y=df["Monthly (USD)"], marker_color="#1062E0")])
    fig.update_layout(height=320, margin=dict(t=10, b=10, l=10, r=10), yaxis_title="Monthly USD")
    st.plotly_chart(fig, use_container_width=True)

    del_id = st.selectbox("Delete an estimate by ID", [None] + df["ID"].tolist())
    if del_id and st.button("🗑 Delete Selected Estimate"):
        database.delete_estimate(del_id)
        st.success(f"Deleted estimate #{del_id}.")
        st.rerun()


# ---------------------------------------------------------------------------
# Page: Mock API
# ---------------------------------------------------------------------------

def page_mock_api():
    st.header("🔌 Mock REST API")
    st.write("Spin up a lightweight Flask API in a background thread, backed by the same "
             "pricing logic as this app, for external integration testing.")

    if "mock_api_running" not in st.session_state:
        st.session_state.mock_api_running = False

    if not st.session_state.mock_api_running:
        if st.button("▶️ Start Mock API on port 8502"):
            mock_api.run_in_background(port=8502)
            st.session_state.mock_api_running = True
            st.rerun()
    else:
        st.success("Mock API running at http://localhost:8502")

    st.subheader("Endpoints")
    st.code(
        "GET  /api/health\n"
        "GET  /api/pricing/compute/<provider>\n"
        "GET  /api/pricing/storage/<provider>\n"
        "POST /api/estimate\n",
        language="text",
    )

    st.subheader("Example request")
    st.code(
        """curl -X POST http://localhost:8502/api/estimate \\
  -H "Content-Type: application/json" \\
  -d '{
        "provider": "AWS",
        "instance_key": "m5.large",
        "hours_per_month": 730,
        "pricing_model": "On-Demand",
        "storage_tier": "standard",
        "storage_gb": 100,
        "egress_gb": 50
      }'""",
        language="bash",
    )
    st.caption("The API can also run standalone (e.g. in its own container) via `python mock_api.py`.")


# ---------------------------------------------------------------------------
# Page: About
# ---------------------------------------------------------------------------

def page_about():
    st.header("ℹ️ About")
    st.markdown(
        """
This Cloud Cost Calculator estimates monthly/yearly spend across **AWS**, **Azure** and **GCP**
for compute, storage and network egress, with:

- Built-in currency conversion (live, with SQLite caching and an offline fallback)
- Rule-based cost optimization advice (reserved/spot, rightsizing, storage tiering, CDN/egress)
- SQLite-backed history of saved estimates and a persisted pricing catalog
- A mock REST API for external integration
- PDF export of any estimate

Pricing figures are illustrative on-demand list prices and are meant for **estimation**, not
billing-accurate quotes. See `pricing.py` to adjust them or re-seed the database.
        """
    )


# ---------------------------------------------------------------------------
# Sidebar navigation
# ---------------------------------------------------------------------------

PAGES = {
    "💰 Calculator": page_calculator,
    "📊 Compare Providers": page_compare,
    "🗂 History": page_history,
    "🔌 Mock API": page_mock_api,
    "ℹ️ About": page_about,
}

st.sidebar.title("☁️ Cost Calculator")
selection = st.sidebar.radio("Navigate", list(PAGES.keys()))
st.sidebar.divider()
st.sidebar.caption("Built with Streamlit · Plotly · SQLite · Flask")

PAGES[selection]()
