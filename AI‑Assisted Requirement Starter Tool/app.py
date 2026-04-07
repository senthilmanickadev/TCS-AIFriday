from flask import Flask, render_template, request, redirect, url_for, session

app = Flask(__name__)
app.secret_key = "secret123"  # Needed for sessions

# Dummy users
users = {
    "analyst": {"password": "123", "role": "Business Analyst"},
    "reviewer": {"password": "456", "role": "Reviewer"}
}

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        if username in users and users[username]["password"] == password:
            session["role"] = users[username]["role"]
            return redirect(url_for("dashboard"))
        else:
            return "Invalid login"
    return '''
        <form method="post">
            Username: <input type="text" name="username"><br>
            Password: <input type="password" name="password"><br>
            <input type="submit" value="Login">
        </form>
    '''

@app.route("/dashboard")
def dashboard():
    if "role" in session:
        return f"Welcome, {session['role']}!"
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(debug=True)
