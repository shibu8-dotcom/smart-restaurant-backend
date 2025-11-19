
import os, json, hmac, hashlib
from datetime import datetime
from flask import Flask, request, jsonify, render_template, send_file, flash, redirect, url_for, session
from flask_cors import CORS
from dotenv import load_dotenv
import razorpay

from models import db, MenuItem, Order, Bill

from bill_utils import generate_pdf_bill

# load .env
load_dotenv()

app = Flask(__name__, static_folder='static')
CORS(app, resources={r"/*": {"origins": "*"}})  # allow cross-origin for public frontend
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.getenv('SECRET_KEY', 'replace_secret')

db.init_app(app)

# Config
GST_PERCENT = 12.0
RAZORPAY_KEY_ID = os.getenv('RAZORPAY_KEY_ID')
RAZORPAY_KEY_SECRET = os.getenv('RAZORPAY_KEY_SECRET')
if RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET:
    razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
else:
    razorpay_client = None

# ADMIN CREDENTIALS (use environment)
ADMIN_USER = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASS = os.getenv('ADMIN_PASSWORD', 'admin')

@app.before_first_request
def create_tables():
    db.create_all()

# -------------------------
# Public API endpoints
# -------------------------

@app.route('/api/menu', methods=['GET'])
def api_menu():
    """Return all available menu items."""
    items = MenuItem.query.filter_by(available=True).all()
    return jsonify([it.to_dict() for it in items]), 200

@app.route('/api/menu/<int:item_id>', methods=['GET'])
def api_get_item(item_id):
    it = MenuItem.query.get_or_404(item_id)
    return jsonify(it.to_dict()), 200

@app.route('/api/order', methods=['POST'])
def api_place_order():
    """
    Expected JSON:
    {
      "table_no": "1",
      "items": [{"id":1,"name":"Dosa","price":70,"qty":2}, ...]
    }
    """
    data = request.get_json() or {}
    items = data.get('items')
    table_no = data.get('table_no')
    if not items:
        return jsonify({"error":"items required"}), 400
    total = sum([it.get('price',0) * it.get('qty',1) for it in items])
    order = Order(table_no=str(table_no), items=json.dumps(items), total=total, status='Pending', paid=False)
    db.session.add(order)
    db.session.commit()
    return jsonify({"message":"order placed", "order_id": order.id, "total": total}), 201

# Create Razorpay order (server side)
@app.route('/api/create_razorpay_order', methods=['POST'])
def api_create_razorpay_order():
    """
    Expects JSON: {"amount": 250.00, "currency":"INR", "receipt":"rcpt_123", "order_id":<local_order_id>}
    amount in rupees (float)
    """
    if not razorpay_client:
        return jsonify({"error":"Razorpay not configured"}), 500
    data = request.get_json() or {}
    amount_rupees = float(data.get('amount', 0))
    amount_paise = int(round(amount_rupees * 100))
    receipt = data.get('receipt', f'rcpt_{int(datetime.utcnow().timestamp())}')
    notes = {"local_order_id": data.get('order_id','')}
    try:
        r_order = razorpay_client.order.create({
            'amount': amount_paise, 'currency': data.get('currency','INR'),
            'receipt': receipt, 'notes': notes, 'payment_capture': 1
        })
        return jsonify({
            "id": r_order.get('id'),
            "amount": r_order.get('amount'),
            "currency": r_order.get('currency'),
            "receipt": r_order.get('receipt')
        })
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500

# Verify payment (server side)
@app.route('/api/razorpay_success', methods=['POST'])
def api_razorpay_success():
    """
    Expects JSON: {razorpay_payment_id, razorpay_order_id, razorpay_signature, local_order_id}
    """
    data = request.get_json() or {}
    pid = data.get('razorpay_payment_id'); oid = data.get('razorpay_order_id'); sig = data.get('razorpay_signature'); local = data.get('local_order_id')
    if not (pid and oid and sig):
        return jsonify({"status":"error","message":"Missing fields"}), 400
    msg = f"{oid}|{pid}"
    expected = hmac.new(bytes(RAZORPAY_KEY_SECRET,'utf-8'), bytes(msg,'utf-8'), hashlib.sha256).hexdigest()
    if hmac.compare_digest(expected, sig):
        # mark order as paid (if local id provided)
        try:
            if local:
                o = Order.query.get(int(local))
                if o:
                    o.paid = True
                    db.session.commit()
        except:
            pass
        return jsonify({"status":"success","message":"Payment verified","payment_id": pid})
    else:
        return jsonify({"status":"error","message":"Invalid signature"}), 400

# Download bill (admin)
@app.route('/api/admin/bill/<int:order_id>', methods=['GET'])
def api_admin_generate_bill(order_id):
    # simple admin check with basic auth (very simple; for production use proper auth)
    auth_user = request.args.get('u'); auth_pass = request.args.get('p')
    if auth_user != ADMIN_USER or auth_pass != ADMIN_PASS:
        return jsonify({"error":"unauthorized"}), 401

    order = Order.query.get_or_404(order_id)
    subtotal = order.total
    gst_amount = round((GST_PERCENT/100.0) * subtotal, 2)
    discount = 0.0
    final_total = round(subtotal + gst_amount - discount, 2)
    bill = Bill(order_id=order.id, gst=gst_amount, discount=discount, final_total=final_total)
    db.session.add(bill)
    db.session.commit()
    pdf_path = generate_pdf_bill(order, bill)
    bill.pdf_path = pdf_path
    db.session.commit()
    return send_file(pdf_path, as_attachment=True, download_name=os.path.basename(pdf_path))

# -------------------------
# Admin UI (optional small pages to manage menu) - for convenience if you want server-side UI
# -------------------------
@app.route('/admin/login', methods=['GET','POST'])
def admin_login():
    if request.method == 'POST':
        u = request.form.get('username'); p = request.form.get('password')
        if u == ADMIN_USER and p == ADMIN_PASS:
            session['admin'] = u
            return redirect(url_for('admin_dashboard'))
        flash("Invalid", "danger")
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('admin_login'))

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'admin' not in session:
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return wrapper

@app.route('/admin')
@admin_required
def admin_dashboard():
    orders = Order.query.order_by(Order.created_at.desc()).all()
    items = MenuItem.query.order_by(MenuItem.category).all()
    return render_template('admin_dashboard.html', orders=orders, items=items)

@app.route('/admin/menu/add', methods=['POST'])
@admin_required
def admin_add_menu():
    name = request.form.get('name'); cat = request.form.get('category'); price = int(request.form.get('price',0))
    mi = MenuItem(name=name, category=cat, price=price, available=True)
    db.session.add(mi); db.session.commit()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/menu/toggle/<int:item_id>')
@admin_required
def admin_toggle(item_id):
    it = MenuItem.query.get_or_404(item_id); it.available = not it.available; db.session.commit(); return redirect(url_for('admin_dashboard'))

@app.route('/admin/menu/delete/<int:item_id>')
@admin_required
def admin_delete(item_id):
    it = MenuItem.query.get_or_404(item_id); db.session.delete(it); db.session.commit(); return redirect(url_for('admin_dashboard'))

# Seed endpoint (for local)
@app.route('/admin/seed')
def admin_seed():
    # simple seeding - idempotent
    if MenuItem.query.first():
        return "Already seeded"
    # you can include the SQL inserts or simple list
    items = [
      ('Puran Poli','Maharashtrian',60), ('Misal Pav','Maharashtrian',50), ('Vada Pav','Maharashtrian',30), ('Poha','Maharashtrian',40),
      ('Dosa','South Indian',70), ('Idli Sambar','South Indian',50), ('Uttapam','South Indian',60), ('Medu Vada','South Indian',45),
      ('Gulab Jamun','Desserts',40), ('Rasgulla','Desserts',45), ('Kheer','Desserts',50), ('Jalebi','Desserts',40),
      ('Dal Baati Churma','Rajasthani',100), ('Gatte ki Sabzi','Rajasthani',80), ('Ker Sangri','Rajasthani',90), ('Laal Maas','Rajasthani',150),
      ('Shorshe Ilish','Bengali',160), ('Chingri Malai Curry','Bengali',150), ('Aloo Posto','Bengali',70), ('Luchi & Cholar Dal','Bengali',80),
      ('Dhokla','Gujarati',40), ('Undhiyu','Gujarati',90), ('Khandvi','Gujarati',45), ('Thepla','Gujarati',50),
      ('Butter Chicken','Non-Vegetarian',260), ('Chicken Biryani','Non-Vegetarian',340), ('Mutton Rogan Josh','Non-Vegetarian',480), ('Fish Fry','Non-Vegetarian',420),
      ('Paneer Butter Masala','Vegetarian',120), ('Chole Bhature','Vegetarian',90), ('Rajma Chawal','Vegetarian',80), ('Veg Biryani','Vegetarian',100),
      ('Amritsari Kulcha','Punjabi',80), ('Sarson Da Saag','Punjabi',90), ('Makki Di Roti','Punjabi',40), ('Lassi','Punjabi',35)
    ]
    for n,c,p in items:
        db.session.add(MenuItem(name=n, category=c, price=p, available=True))
    db.session.commit()
    return "Seeded"

if __name__ == '__main__':

    app.run(host='0.0.0.0', port=int(os.getenv('PORT',5000)), debug=True)
