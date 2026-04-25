"""Generate a tiny AcroForm PDF for tests. Not shipped as an example —
this lives in tests/ because the file is regenerated each run from
known field metadata so the fill assertions can be precise."""
from __future__ import annotations

from pathlib import Path

from reportlab.lib.colors import black, white  # type: ignore
from reportlab.pdfgen import canvas  # type: ignore


def build_acroform(out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out), pagesize=(612, 792))
    c.setFont("Helvetica", 14)
    c.drawString(72, 740, "Test invoice")

    form = c.acroForm
    c.drawString(72, 700, "Customer:")
    form.textfield(name="customer_name", x=160, y=692, width=280, height=22,
                   borderColor=black, fillColor=white,
                   maxlen=80, fontSize=11)

    c.drawString(72, 660, "Invoice date:")
    form.textfield(name="invoice_date", x=160, y=652, width=120, height=22,
                   borderColor=black, fillColor=white,
                   maxlen=20, fontSize=11)

    c.drawString(72, 620, "I agree to terms:")
    form.checkbox(name="agree_terms", x=200, y=614, size=18,
                  borderColor=black, fillColor=white)

    c.save()


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("usage: _acroform_fixture.py OUT.pdf", file=sys.stderr)
        sys.exit(1)
    build_acroform(Path(sys.argv[1]))
