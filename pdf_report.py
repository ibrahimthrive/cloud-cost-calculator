"""Generate a clean PDF summary report of a cost estimate using fpdf2."""

from datetime import datetime

from fpdf import FPDF

BRAND_COLOR = (16, 98, 224)
DARK = (33, 37, 41)
GREY = (108, 117, 125)


class ReportPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 16)
        self.set_text_color(*BRAND_COLOR)
        self.cell(0, 10, "Cloud Cost Estimate Report", ln=True)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*GREY)
        self.cell(0, 6, f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}", ln=True)
        self.set_draw_color(*BRAND_COLOR)
        self.line(10, self.get_y() + 2, 200, self.get_y() + 2)
        self.ln(8)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*GREY)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")

    def section_title(self, text: str):
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(*DARK)
        self.ln(2)
        self.cell(0, 8, text, ln=True)
        self.set_text_color(*GREY)

    def kv_row(self, key: str, value: str):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*DARK)
        self.cell(60, 7, key)
        self.set_font("Helvetica", "B", 10)
        self.cell(0, 7, value, ln=True)


def build_report(config: dict, breakdown: dict, suggestions: list, currency: str) -> bytes:
    """
    config: dict of user inputs (provider, instance, region, hours, storage, egress...)
    breakdown: dict with compute/storage/egress/monthly_total/yearly_total (USD) and converted values
    suggestions: list of optimization.Suggestion
    """
    pdf = ReportPDF()
    pdf.add_page()

    pdf.section_title("Configuration")
    pdf.kv_row("Cloud Provider", config.get("provider", "-"))
    pdf.kv_row("Compute Instance", config.get("instance_label", "-"))
    pdf.kv_row("Pricing Model", config.get("pricing_model", "-"))
    pdf.kv_row("Hours / Month", f"{config.get('hours_per_month', 0):.0f}")
    pdf.kv_row("Storage Tier", config.get("storage_label", "-"))
    pdf.kv_row("Storage Size", f"{config.get('storage_gb', 0):.0f} GB")
    pdf.kv_row("Egress / Month", f"{config.get('egress_gb', 0):.0f} GB")

    pdf.section_title("Cost Breakdown (USD)")
    pdf.kv_row("Compute", f"${breakdown['compute_usd']:,.2f}")
    pdf.kv_row("Storage", f"${breakdown['storage_usd']:,.2f}")
    pdf.kv_row("Network Egress", f"${breakdown['egress_usd']:,.2f}")
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*BRAND_COLOR)
    pdf.cell(60, 9, "Monthly Total")
    pdf.cell(0, 9, f"${breakdown['monthly_total_usd']:,.2f}", ln=True)
    pdf.cell(60, 9, "Yearly Total")
    pdf.cell(0, 9, f"${breakdown['yearly_total_usd']:,.2f}", ln=True)

    if currency != "USD":
        pdf.section_title(f"Converted ({currency})")
        pdf.kv_row("Monthly Total", f"{breakdown['monthly_total_converted']:,.2f} {currency}")
        pdf.kv_row("Yearly Total", f"{breakdown['yearly_total_converted']:,.2f} {currency}")

    if suggestions:
        pdf.section_title("Cost Optimization Suggestions")
        content_width = pdf.w - pdf.l_margin - pdf.r_margin
        for s in suggestions:
            pdf.set_x(pdf.l_margin)
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(*DARK)
            saving = f" (save up to ${s.estimated_monthly_savings:,.2f}/mo)" if s.estimated_monthly_savings > 0 else ""
            pdf.multi_cell(content_width, 6, f"- {s.title}{saving}")
            pdf.set_x(pdf.l_margin)
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(*GREY)
            pdf.multi_cell(content_width, 5, s.detail)
            pdf.ln(1)

    return bytes(pdf.output())
