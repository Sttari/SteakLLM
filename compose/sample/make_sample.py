# /// script
# requires-python = ">=3.12"
# dependencies = ["fpdf2>=2.8"]
# ///
"""Generate the sample document for `make demo`: a short, fictional quarterly report.

Run once (the PDF is committed): uv run compose/sample/make_sample.py
Fictional company, fictional numbers — nothing here is real.
"""

from pathlib import Path

from fpdf import FPDF

TEXT = """Ferrous Foods plc - Quarterly Report, Q3 2026

Summary of results
Revenue for the third quarter was 148.2 million, up 12 percent year over year. Growth was driven by the
EMEA segment, where the new cold-chain contracts signed in the spring began shipping in July. Operating
margin held at 18 percent despite higher energy costs, helped by the closure of the Leeds depot and the
consolidation of logistics into the Rotterdam hub.

Segment performance
EMEA revenue grew 21 percent to 81.4 million. North America grew 4 percent to 52.1 million, with softness
in food-service offset by retail. Asia-Pacific declined 3 percent to 14.7 million as the Osaka distribution
partner wound down; a replacement partner is expected to be announced in the fourth quarter.

Costs and cash
Cost of sales rose 9 percent, below revenue growth, reflecting the logistics consolidation. Free cash flow
was 19.6 million. Net debt fell to 62 million, or 1.1 times trailing EBITDA. Capital expenditure of 7.2
million was concentrated on refrigeration upgrades at the Rotterdam hub.

Outlook
Guidance for the full year is unchanged: revenue growth of 10 to 12 percent and an operating margin of
17 to 19 percent. The board notes two risks: energy prices in the winter quarter, and the timing of the
Asia-Pacific partner transition. A final dividend of 4.5 pence per share is proposed.

People
Headcount was 2,140 at quarter end, down 60 following the Leeds closure. The apprenticeship programme
enrolled its third cohort of 24. Employee turnover remained at 9 percent on a rolling twelve-month basis.
"""

pdf = FPDF()
pdf.set_auto_page_break(auto=True, margin=15)
pdf.add_page()
pdf.set_font("Helvetica", size=11)
for para in TEXT.strip().split("\n\n"):
    first, *rest = para.split("\n", 1)
    if not rest:
        pdf.set_font("Helvetica", "B", 14)
        pdf.multi_cell(0, 8, first, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", size=11)
        pdf.ln(2)
        continue
    pdf.set_font("Helvetica", "B", 12)
    pdf.multi_cell(0, 7, first, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=11)
    pdf.multi_cell(0, 6, rest[0].replace("\n", " "), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
out = Path(__file__).with_name("quarterly-report.pdf")
pdf.output(out)
print(f"wrote {out} ({out.stat().st_size} bytes)")
