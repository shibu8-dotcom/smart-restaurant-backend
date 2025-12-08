# app.py
import os, json, hmac, hashlib
from datetime import datetime
from flask import Flask, request, jsonify, render_template, send_file, flash, redirect, url_for, session
from flask_cors import CORS
from dotenv import load_dotenv
import razorpay

from models import db, MenuItem, Order, Bill
from bill_utils import generate_pdf_bill

load_dotenv()

app = Flask(__name__, static_folder='static')
CORS(app, resources={r"/*": {"origins": "*"}})
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.getenv('SECRET_KEY', 'replace_secret')

db.init_app(app)

GST_PERCENT = float(os.getenv('GST_PERCENT', '12.0'))
# Hardcoded admin for now (works without .env)
ADMIN_USER = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASS = os.getenv('ADMIN_PASSWORD', 'admin')

RAZORPAY_KEY_ID = os.getenv('RAZORPAY_KEY_ID')
RAZORPAY_KEY_SECRET = os.getenv('RAZORPAY_KEY_SECRET')
if RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET:
    razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
else:
    razorpay_client = None

@app.before_first_request
def create_tables():
    db.create_all()
@app.route( "/")
def initi():
    return render_template("index.html")
# seed route for creating menu items (idempotent)
@app.route('/admin/seed')
def seed():
    if MenuItem.query.first():
        return "Already seeded"
    items = [
      ('Puran Poli','Maharashtrian',60,'static/images/gujarati/dhokla.jpg'), ('Misal Pav','Maharashtrian',50,'static/images/gujarati/dhokla.jpg'), ('Vada Pav','Maharashtrian',30,'static/images/gujarati/dhokla.jpg'), ('Poha','Maharashtrian',40,'static/images/gujarati/dhokla.jpg'),
      ('Dosa','South Indian',70,'static/images/gujarati/dhokla.jpg'), ('Idli Sambar','South Indian',50,'static/images/gujarati/dhokla.jpg'), ('Uttapam','South Indian',60,'static/images/gujarati/dhokla.jpg'), ('Medu Vada','South Indian',45,'static/images/gujarati/dhokla.jpg'),
      ('Gulab Jamun','Desserts',40,'static/images/gujarati/dhokla.jpg'), ('Rasgulla','Desserts',45,'static/images/gujarati/dhokla.jpg'), ('Kheer','Desserts',50,'static/images/gujarati/dhokla.jpg'), ('Jalebi','Desserts',40,'static/images/gujarati/dhokla.jpg'),
      ('Dal Baati Churma','Rajasthani',100,'static/images/gujarati/dhokla.jpg'), ('Gatte ki Sabzi','Rajasthani',80,'static/images/gujarati/dhokla.jpg'), ('Ker Sangri','Rajasthani',90,'static/images/gujarati/dhokla.jpg'), ('Laal Maas','Rajasthani',150,'static/images/gujarati/dhokla.jpg'),
      ('Shorshe Ilish','Bengali',160,'static/images/gujarati/dhokla.jpg'), ('Chingri Malai Curry','Bengali',150,'static/images/gujarati/dhokla.jpg'), ('Aloo Posto','Bengali',70,'static/images/gujarati/dhokla.jpg'), ('Luchi & Cholar Dal','Bengali',80,'static/images/gujarati/dhokla.jpg'),
      ('Dhokla','Gujarati',40,'static/images/gujarati/dhokla.jpg'), ('Undhiyu','Gujarati',90,'static/images/gujarati/dhokla.jpg'), ('Khandvi','Gujarati',45,'static/images/gujarati/dhokla.jpg'), ('Thepla','Gujarati',50,'static/images/gujarati/dhokla.jpg'),
      ('Butter Chicken','Non-Vegetarian',260,'static/images/gujarati/dhokla.jpg'), ('Chicken Biryani','Non-Vegetarian',340,'static/images/gujarati/dhokla.jpg'), ('Mutton Rogan Josh','Non-Vegetarian',480,'static/images/gujarati/dhokla.jpg'), ('Fish Fry','Non-Vegetarian',420,'static/images/gujarati/dhokla.jpg'),
      ('Paneer Butter Masala','Vegetarian',120,'static/images/gujarati/dhokla.jpg'), ('Chole Bhature','Vegetarian',90,'static/images/gujarati/dhokla.jpg'), ('Rajma Chawal','Vegetarian',80,'static/images/gujarati/dhokla.jpg'), ('Veg Biryani','Vegetarian',100,'static/images/gujarati/dhokla.jpg'),
      ('Amritsari Kulcha','Punjabi',80,'static/images/gujarati/dhokla.jpg'), ('Sarson Da Saag','Punjabi',90,'static/images/gujarati/dhokla.jpg'), ('Makki Di Roti','Punjabi',40,'static/images/gujarati/dhokla.jpg'), ('Lassi','Punjabi',35,'static/images/gujarati/dhokla.jpg')
    ]
    for n,c,p,img in items:
        db.session.add(MenuItem(name=n, category=c, price=p, available=True, image_path=img))
    db.session.commit()
    return "Seeded"

# Public API: list menu
@app.route('/api/menu', methods=['GET'])
def api_menu():
    items = MenuItem.query.filter_by(available=True).all()
    return jsonify([it.to_dict() for it in items]), 200

# Public API: place order (create DB order)
@app.route('/api/order', methods=['POST'])
def api_place_order():
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

# Create Razorpay order
@app.route('/api/create_razorpay_order', methods=['POST'])
def api_create_razorpay_order():
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

# Verify Razorpay payment (mark paid)
@app.route('/api/razorpay_success', methods=['POST'])
def api_razorpay_success():
    data = request.get_json() or {}
    pid = data.get('razorpay_payment_id'); oid = data.get('razorpay_order_id'); sig = data.get('razorpay_signature'); local = data.get('local_order_id')
    if not (pid and oid and sig):
        return jsonify({"status":"error","message":"Missing fields"}), 400
    msg = f"{oid}|{pid}"
    expected = hmac.new(bytes(RAZORPAY_KEY_SECRET,'utf-8'), bytes(msg,'utf-8'), hashlib.sha256).hexdigest()
    if hmac.compare_digest(expected, sig):
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

# Admin UI
@app.route('/admin/login', methods=['GET','POST'])
def admin_login():
    if request.method == 'POST':
        u = request.form.get('username'); p = request.form.get('password')
        if u == ADMIN_USER and p == ADMIN_PASS:
            session['admin'] = u
            return redirect(url_for('admin_dashboard'))
        flash("Invalid username or password", "danger")
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

# Admin generate bill (download)
@app.route('/admin/order/bill/<int:order_id>')
@admin_required
def admin_generate_bill(order_id):
    order = Order.query.get_or_404(order_id)
    subtotal = order.total
    gst_amount = round((GST_PERCENT/100.0) * subtotal, 2)
    discount = 0.0
    final_total = round(subtotal + gst_amount - discount, 2)
    bill = Bill(order_id=order.id, gst=gst_amount, discount=discount, final_total=final_total)
    db.session.add(bill); db.session.commit()
    pdf_path = generate_pdf_bill(order, bill)
    bill.pdf_path = pdf_path; db.session.commit()
    return send_file(pdf_path, as_attachment=True, download_name=os.path.basename(pdf_path))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT',5000)), debug=True)
