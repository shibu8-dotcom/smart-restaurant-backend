# bill_utils.py
import os, json
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

def generate_pdf_bill(order, bill_obj, output_dir='static/bills'):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    filename = f"bill_order_{order.id}.pdf"
    filepath = os.path.join(output_dir, filename)

    c = canvas.Canvas(filepath, pagesize=A4)
    width, height = A4
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, height-50, "Smart Restaurant")
    c.setFont("Helvetica", 10)
    c.drawString(40, height-70, f"Order ID: {order.id}")
    c.drawString(40, height-90, f"Table: {order.table_no or '-'}")
    c.drawString(40, height-110, f"Date: {order.created_at.strftime('%Y-%m-%d %H:%M:%S')}")

    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, height-140, "Items")
    c.drawString(350, height-140, "Qty")
    c.drawString(420, height-140, "Price")

    c.setFont("Helvetica", 10)
    items = json.loads(order.items)
    y = height - 160
    for it in items:
        name = it.get('name'); qty = it.get('qty',1); price = it.get('price',0)
        c.drawString(40, y, f"{name}")
        c.drawString(350, y, str(qty))
        c.drawString(420, y, f"{price:.2f}")
        y -= 18
        if y < 120:
            c.showPage()
            y = height - 50

    y -= 10
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, f"Subtotal: ₹{order.total:.2f}")
    y -= 18
    c.drawString(40, y, f"GST: ₹{bill_obj.gst:.2f}")
    y -= 18
    c.drawString(40, y, f"Discount: ₹{bill_obj.discount:.2f}")
    y -= 18
    c.drawString(40, y, f"Total Payable: ₹{bill_obj.final_total:.2f}")

    c.setFont("Helvetica", 9)
    c.drawString(40, 40, "Thank you for dining with us!")
    c.save()
    return filepath