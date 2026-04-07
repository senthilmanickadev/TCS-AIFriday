import sqlite3
from flask import Flask, request, redirect, url_for, session
import openai

# --- Flask Setup ---
app = Flask(__name__)
app.secret_key = "supersecretkey"  # Needed for sessions

# --- Dummy Users (Week 1) ---
users = {
    "analyst": {"password": "123", "role": "Business Analyst"},
    "reviewer": {"password": "456", "role": "Reviewer"}
}

# --- Database Setup ---
def init_db():
    conn = sqlite3.connect("requirements.db")
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS requirements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            raw_text TEXT NOT NULL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requirement_id INTEGER NOT NULL,
            reviewer_type TEXT NOT NULL,
            comments TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (requirement_id) REFERENCES requirements(id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- Login Page ---
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if username in users and users[username]["password"] == password:
            session["user"] = username
            session["role"] = users[username]["role"]
            return redirect(url_for("dashboard"))
        else:
            return "Invalid credentials"

    return '''
        <h2>Login</h2>
        <form method="post">
            Username: <input type="text" name="username"><br>
            Password: <input type="password" name="password"><br>
            <input type="submit" value="Login">
        </form>
    '''

@app.route("/dashboard")
def dashboard():
    if "user" in session:
        return f"Welcome, {session['role']}! <br><a href='/input'>Add Requirement</a> | <a href='/list'>View Requirements</a>"
    return redirect(url_for("login"))

# --- Requirement Input ---
@app.route("/input", methods=["GET", "POST"])
def input_requirement():
    if request.method == "POST":
        title = request.form["title"]
        raw_text = request.form["requirement"]

        conn = sqlite3.connect("requirements.db")
        c = conn.cursor()
        c.execute("INSERT INTO requirements (title, raw_text) VALUES (?, ?)", (title, raw_text))
        conn.commit()
        conn.close()

        return redirect(url_for("list_requirements"))

    return '''
        <h2>Add Requirement</h2>
        <form method="post">
            Feature Title: <input type="text" name="title"><br>
            Raw Requirement: <textarea name="requirement"></textarea><br>
            <input type="submit" value="Submit">
        </form>
    '''

@app.route("/list")
def list_requirements():
    conn = sqlite3.connect("requirements.db")
    c = conn.cursor()
    c.execute("SELECT id, title, raw_text FROM requirements")
    rows = c.fetchall()
    conn.close()

    output = "<h2>Saved Requirements</h2><ul>"
    for r in rows:
        output += f"<li><b>{r[1]}</b>: {r[2]} "
        output += f"<a href='/expand/{r[0]}'>[Expand with AI1]</a> "
        output += f"<a href='/expand2/{r[0]}'>[Expand with AI2]</a> "
        output += f"<a href='/review/{r[0]}'>[Review]</a> "
        output += f"<a href='/edit/{r[0]}'>[Edit]</a></li>"
    output += "</ul><a href='/input'>Add New Requirement</a>"
    return output

# --- AI Expansion (AI1 + AI2) ---
openai.api_key = "YOUR_OPENAI_KEY"  # Replace with your actual key

def expand_requirement_ai1(raw_text):
    prompt = f"Expand this requirement into detailed functional and non-functional specifications:\n\n{raw_text}"
    response = openai.Completion.create(
        engine="text-davinci-003",
        prompt=prompt,
        max_tokens=500
    )
    return response.choices[0].text.strip()

def expand_requirement_ai2(raw_text):
    prompt = f"Review this requirement and suggest improvements, risks, and missing details:\n\n{raw_text}"
    response = openai.Completion.create(
        engine="text-davinci-003",
        prompt=prompt,
        max_tokens=500
    )
    return response.choices[0].text.strip()

@app.route("/expand/<int:req_id>")
def expand_ai1(req_id):
    conn = sqlite3.connect("requirements.db")
    c = conn.cursor()
    c.execute("SELECT raw_text FROM requirements WHERE id=?", (req_id,))
    row = c.fetchone()
    conn.close()

    if row:
        raw_text = row[0]
        expanded = expand_requirement_ai1(raw_text)

        conn = sqlite3.connect("requirements.db")
        c = conn.cursor()
        c.execute("INSERT INTO reviews (requirement_id, reviewer_type, comments) VALUES (?, ?, ?)",
                  (req_id, "AI1", expanded))
        conn.commit()
        conn.close()

        return f"<h2>AI1 Expansion</h2><pre>{expanded}</pre><br><a href='/list'>Back to Requirements</a>"
    else:
        return "Requirement not found"

@app.route("/expand2/<int:req_id>")
def expand_ai2(req_id):
    conn = sqlite3.connect("requirements.db")
    c = conn.cursor()
    c.execute("SELECT raw_text FROM requirements WHERE id=?", (req_id,))
    row = c.fetchone()
    conn.close()

    if row:
        raw_text = row[0]
        expanded = expand_requirement_ai2(raw_text)

        conn = sqlite3.connect("requirements.db")
        c = conn.cursor()
        c.execute("INSERT INTO reviews (requirement_id, reviewer_type, comments) VALUES (?, ?, ?)",
                  (req_id, "AI2", expanded))
        conn.commit()
        conn.close()

        return f"<h2>AI2 Review</h2><pre>{expanded}</pre><br><a href='/list'>Back to Requirements</a>"
    else:
        return "Requirement not found"

# --- Reviewer Dashboard (Human Review) ---
@app.route("/review/<int:req_id>", methods=["GET", "POST"])
def review_requirement(req_id):
    conn = sqlite3.connect("requirements.db")
    c = conn.cursor()

    if request.method == "POST":
        comments = request.form["comments"]
        c.execute("INSERT INTO reviews (requirement_id, reviewer_type, comments) VALUES (?, ?, ?)",
                  (req_id, "Human", comments))
        conn.commit()
        conn.close()
        return redirect(url_for("list_requirements"))

    # Fetch requirement
    c.execute("SELECT title, raw_text FROM requirements WHERE id=?", (req_id,))
    req = c.fetchone()

    # Fetch all reviews
    c.execute("SELECT reviewer_type, comments FROM reviews WHERE requirement_id=?", (req_id,))
    reviews = c.fetchall()
    conn.close()

    output = f"<h2>Review Requirement: {req[0]}</h2><p>{req[1]}</p><h3>Reviews:</h3><ul>"
    for r in reviews:
        output += f"<li><b>{r[0]}:</b> {r[1]}</li>"
    output += "</ul>"

    output += '''
        <h3>Add Human Review</h3>
        <form method="post">
            Comments: <textarea name="comments"></textarea><br>
            <input type="submit" value="Submit Review">
        </form>
    '''
    return output

# --- Edit Requirement (Week 5) ---
@app.route("/edit/<int:req_id>", methods=["GET", "POST"])
def edit_requirement(req_id):
    conn = sqlite3.connect("requirements.db")
    c = conn.cursor()

    if request.method == "POST":
        title = request.form["title"]
        raw_text = request.form["requirement"]
        c.execute("UPDATE requirements SET title=?, raw_text=? WHERE id=?", (title, raw_text, req_id))
        conn.commit()
        conn.close()
        return redirect(url_for("list_requirements"))

    c.execute("SELECT title, raw_text FROM requirements WHERE id=?", (req_id,))
    row = c.fetchone()
    conn.close()

    return f'''
        <h2>Edit Requirement</h2>
        <form method="post">
            Feature Title: <input type="text" name="title" value="{row[0]}"><br>
            Raw Requirement: <textarea name="requirement">{row[1]}</textarea><br>
            <input type="submit" value="Update">
        </form>
    '''

# --- Run App ---
if __name__ == "__main__":
    app.run(debug=True)
