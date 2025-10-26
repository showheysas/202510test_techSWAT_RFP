from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from datetime import datetime
import os

def create_minutes_pdf(title: str, summary: str, decision: str, action: str, issue: str, output_path="minutes_output.pdf"):
    c = canvas.Canvas(output_path, pagesize=A4)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(72, 800, f"議事録：{title}")
    c.setFont("Helvetica", 12)
    y = 760
    for label, text in [("Summary", summary), ("Decision", decision), ("Action", action), ("Issue", issue)]:
        c.drawString(72, y, f"{label}:")
        y -= 20
        for line in text.splitlines():
            c.drawString(90, y, line)
            y -= 15
        y -= 10
    c.setFont("Helvetica-Oblique", 10)
    c.drawString(72, 60, f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    c.save()
    return output_path
