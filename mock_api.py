"""
Lightweight mock REST API exposing the same pricing/estimation logic as the
Streamlit app, for external integration (CI pipelines, other dashboards,
quick curl/Postman testing).

Run standalone:
    python mock_api.py            # serves on http://localhost:8502

Or import `create_app()` / `run_in_background()` from app.py to host it
alongside the Streamlit process.
"""

import threading

from flask import Flask, jsonify, request

import pricing as p


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    @app.get("/api/pricing/compute/<provider>")
    def compute_pricing(provider):
        try:
            instances = p.COMPUTE_CATALOGS[provider]
        except KeyError:
            return jsonify({"error": f"unknown provider '{provider}'"}), 404
        return jsonify([
            {"key": i.key, "label": i.label, "vcpu": i.vcpu, "ram_gb": i.ram_gb, "hourly_usd": i.hourly_usd}
            for i in instances
        ])

    @app.get("/api/pricing/storage/<provider>")
    def storage_pricing(provider):
        try:
            tiers = p.STORAGE_CATALOGS[provider]
        except KeyError:
            return jsonify({"error": f"unknown provider '{provider}'"}), 404
        return jsonify([{"key": t.key, "label": t.label, "usd_per_gb_month": t.usd_per_gb_month} for t in tiers])

    @app.post("/api/estimate")
    def estimate():
        """
        Expected JSON body:
        {
          "provider": "AWS",
          "instance_key": "m5.large",
          "hours_per_month": 730,
          "pricing_model": "On-Demand",
          "storage_tier": "standard",
          "storage_gb": 100,
          "egress_gb": 50
        }
        """
        data = request.get_json(force=True, silent=True) or {}
        required = ["provider", "instance_key", "hours_per_month", "pricing_model",
                    "storage_tier", "storage_gb", "egress_gb"]
        missing = [f for f in required if f not in data]
        if missing:
            return jsonify({"error": f"missing fields: {missing}"}), 400

        try:
            compute_usd = p.compute_monthly_cost(
                data["provider"], data["instance_key"], float(data["hours_per_month"]), data["pricing_model"]
            )
            storage_usd = p.storage_monthly_cost(data["provider"], data["storage_tier"], float(data["storage_gb"]))
            egress_usd = p.egress_monthly_cost(data["provider"], float(data["egress_gb"]))
        except KeyError as e:
            return jsonify({"error": str(e)}), 400

        monthly_total = compute_usd + storage_usd + egress_usd
        return jsonify({
            "compute_usd": round(compute_usd, 4),
            "storage_usd": round(storage_usd, 4),
            "egress_usd": round(egress_usd, 4),
            "monthly_total_usd": round(monthly_total, 4),
            "yearly_total_usd": round(monthly_total * 12, 4),
        })

    return app


def run_in_background(port: int = 8502):
    """Start the mock API on a daemon thread; safe to call multiple times."""
    app = create_app()

    def _run():
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

    thread = threading.Thread(target=_run, daemon=True, name="mock-api")
    thread.start()
    return thread


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=8502, debug=False)
