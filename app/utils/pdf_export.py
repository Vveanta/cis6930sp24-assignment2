"""Lightweight PDF summary for presentations (text + embedded matplotlib charts)."""
from __future__ import annotations

import io
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from reportlab.lib.pagesizes import letter  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402


def build_summary_pdf_bytes(stats: dict[str, Any], rows: list[dict[str, Any]]) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    width, height = letter
    y = height - 50
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, y, "Norman PD Incident Summary")
    y -= 28
    c.setFont("Helvetica", 11)
    for line in [
        f"Total incidents: {stats.get('total', 0)}",
        f"Date range: {stats.get('date_min', '—')} – {stats.get('date_max', '—')}",
        f"Most common nature: {stats.get('top_nature', '—')}",
    ]:
        c.drawString(50, y, line)
        y -= 16
    y -= 10
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(
        50,
        y,
        "Charts below are quick matplotlib views; use the web app for full Plotly charts.",
    )
    y -= 24

    # Simple bar: day of week
    if rows:
        from collections import Counter

        dow = Counter()
        for r in rows:
            k = r.get("Day of the Week")
            if k is not None and str(k).strip() != "":
                dow[str(k)] += 1
        if dow:
            labels = ["1", "2", "3", "4", "5", "6", "7"]
            vals = [dow.get(l, 0) for l in labels]
            fig, ax = plt.subplots(figsize=(6.5, 3))
            ax.bar(labels, vals, color="#1a5f7a")
            ax.set_title("Incidents by day-of-week code (1=Sun … 7=Sat)")
            ax.set_xlabel("Day code")
            fig.tight_layout()
            img_buf = io.BytesIO()
            fig.savefig(img_buf, format="png", dpi=120)
            plt.close(fig)
            img_buf.seek(0)
            from reportlab.lib.utils import ImageReader  # noqa: E402

            ir = ImageReader(img_buf)
            img_w, img_h = 400, 185
            c.drawImage(ir, 50, y - img_h, width=img_w, height=img_h, preserveAspectRatio=True)
            y -= img_h + 30

    c.save()
    buf.seek(0)
    return buf.read()
