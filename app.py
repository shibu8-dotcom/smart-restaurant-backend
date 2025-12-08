from flask import Flask, render_template, request, redirect, flash
import os

app = Flask(__name__)
app.secret_key = "12345"

# ---------------- Admin Login Page ----------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        # Hardcoded login (you can change)
        if username == "admin" and password == "admin123":
            return redirect("/admin/dashboard")
        else:
            flash("Invalid username or password!", "error")
            return redirect("/admin/login")

    return render_template("admin_login.html")


# ---------------- Admin Dashboard Page ----------------
@app.route("/admin/dashboard")
def admin_dashboard():
    return render_template("admin_dashboard.html")


# ---------------- Home Route ----------------
@app.route("/")
def home():
    return "Backend Running Successfully!"


# ---------------- Render Deploy Fix ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
