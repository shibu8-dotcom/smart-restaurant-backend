from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Database
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///restaurant.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# -----------------------------
# MODELS
# -----------------------------
class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    password = db.Column(db.String(50))

class Orders(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    table_no = db.Column(db.String(20))
    items = db.Column(db.String(500))
    total = db.Column(db.Integer)

# -----------------------------
# ROUTES
# -----------------------------

@app.route("/")
def home():
    return "Backend working!"

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        admin = Admin.query.filter_by(username=username, password=password).first()
        if admin:
            return render_template("admin_dashboard.html")

        return render_template("admin_login.html", error="Invalid credentials")

    return render_template("admin_login.html")

@app.route("/place-order", methods=["POST"])
def place_order():
    data = request.json
    new_order = Orders(
        table_no=data["table_no"],
        items=data["items"],
        total=data["total"],
    )
    db.session.add(new_order)
    db.session.commit()

    return jsonify({"message": "Order saved successfully!"})

@app.route("/orders")
def view_orders():
    all_orders = Orders.query.all()
    data = []
    for o in all_orders:
        data.append({
            "id": o.id,
            "table_no": o.table_no,
            "items": o.items,
            "total": o.total,
        })
    return jsonify(data)

# -----------------------------
# INITIALIZE DB
# -----------------------------
with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run()
