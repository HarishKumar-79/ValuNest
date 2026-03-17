import os, sqlite3, pickle
import numpy as np
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = "houseprice_secret_2025"

BASE = os.path.dirname(os.path.abspath(__file__))
DB   = os.path.join(BASE, "users.db")
CSV  = os.path.join(BASE, "merged_files.csv")

model        = pickle.load(open(os.path.join(BASE, "model.pkl"), "rb"))
feature_cols = pickle.load(open(os.path.join(BASE, "feature_cols.pkl"), "rb"))
df           = pd.read_csv(CSV)
CITIES       = sorted(df['City'].dropna().unique().tolist())

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL)""")
        conn.commit()

init_db()

from functools import wraps
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('select_city'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        name     = request.form['name'].strip()
        email    = request.form['email'].strip().lower()
        password = request.form['password']
        confirm  = request.form['confirm']
        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("register.html")
        hashed = generate_password_hash(password)
        try:
            with get_db() as conn:
                conn.execute("INSERT INTO users (name,email,password) VALUES (?,?,?)", (name,email,hashed))
                conn.commit()
            flash("Account created! Please log in.", "success")
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash("Email already registered.", "error")
    return render_template("register.html")

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email    = request.form['email'].strip().lower()
        password = request.form['password']
        with get_db() as conn:
            user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user and check_password_hash(user['password'], password):
            session['user_id']   = user['id']
            session['user_name'] = user['name']
            return redirect(url_for('select_city'))
        flash("Invalid email or password.", "error")
    return render_template("login.html")

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/city', methods=['GET','POST'])
@login_required
def select_city():
    if request.method == 'POST':
        session['city'] = request.form['city']
        return redirect(url_for('select_location'))
    return render_template("city.html", cities=CITIES)

@app.route('/location', methods=['GET','POST'])
@login_required
def select_location():
    city = session.get('city', CITIES[0])
    locations = sorted(df[df['City']==city]['Location'].dropna().unique().tolist())
    if request.method == 'POST':
        session['location'] = request.form['location']
        return redirect(url_for('choose_option'))
    return render_template("location.html", city=city, locations=locations)

@app.route('/options')
@login_required
def choose_option():
    return render_template("options.html",
        city=session.get('city',''), location=session.get('location',''))

@app.route('/predict', methods=['GET','POST'])
@login_required
def predict():
    city     = session.get('city', '')
    location = session.get('location', '')
    if request.method == 'POST':
        try:
            area      = float(request.form['area'])
            bedrooms  = float(request.form['bedrooms'])
            bathrooms = float(request.form['bathrooms'])
            resale    = float(request.form['resale'])
            parking   = float(request.form['parking'])
            lift      = float(request.form['lift'])
            gym       = float(request.form.get('gym', 0))
            pool      = float(request.form.get('pool', 0))
            security  = float(request.form.get('security', 0))
            power     = float(request.form.get('power', 0))
            club      = float(request.form.get('club', 0))
        except ValueError:
            flash("Please enter valid numbers.", "error")
            return render_template("predict.html", city=city, location=location)
        row = {col: 0 for col in feature_cols}
        row['Area'] = area
        row['No. of Bedrooms'] = bedrooms
        row['Resale'] = resale
        row['CarParking'] = parking
        row['LiftAvailable'] = lift
        row['Gymnasium'] = gym
        row['SwimmingPool'] = pool
        row['24X7Security'] = security
        row['PowerBackup'] = power
        row['ClubHouse'] = club
        city_col = f'City_{city}'
        if city_col in row:
            row[city_col] = 1
        input_df = pd.DataFrame([row])[feature_cols]
        pred = model.predict(input_df)[0]

        # If prediction is negative or too low, mark as unavailable
        if pred < 100000:
            return render_template("predict.html", city=city, location=location,
                                   error="Could not estimate a valid price for these inputs. Please try different values.")

        low  = round(pred * 0.92)
        high = round(pred * 1.08)
        session['predicted_price'] = round(pred)
        session['payment_from']    = 'predict'
        return redirect(url_for('result', pred=round(pred), low=low, high=high))
    return render_template("predict.html", city=city, location=location)

@app.route('/result')
@login_required
def result():
    pred     = int(request.args.get('pred', 0))
    low      = int(request.args.get('low', 0))
    high     = int(request.args.get('high', 0))
    city     = session.get('city', '')
    location = session.get('location', '')
    return render_template("result.html", prediction=pred, low=low, high=high,
                           city=city, location=location)

@app.route('/filter', methods=['GET','POST'])
@login_required
def filter_listings():
    city     = session.get('city', '')
    location = session.get('location', '')
    listings = []
    no_results = False

    if request.method == 'POST':
        try:
            budget = float(request.form['budget'])
            margin = float(request.form.get('margin', 15))
        except ValueError:
            flash("Please enter a valid budget.", "error")
            return render_template("filter.html", city=city, location=location, listings=[], no_results=False)

        low  = budget * (1 - margin/100)
        high = budget * (1 + margin/100)

        # Always filter by selected location first
        filtered = df[
            (df['City'] == city) &
            (df['Location'] == location) &
            (df['Price'] >= low) &
            (df['Price'] <= high)
        ].copy()

        # If no results in that location, widen to city but tell user
        if len(filtered) == 0:
            filtered = df[
                (df['City'] == city) &
                (df['Price'] >= low) &
                (df['Price'] <= high)
            ].copy()
            no_results = True  # means we fell back to city-wide

        filtered = filtered.sort_values('Price').head(10)
        listings = filtered[['Location','Price','Area','No. of Bedrooms',
                              'CarParking','LiftAvailable','Gymnasium','SwimmingPool']].to_dict('records')

    return render_template("filter.html", city=city, location=location,
                           listings=listings, no_results=no_results)

@app.route('/select_listing', methods=['POST'])
@login_required
def select_listing():
    # FIX: store SELECTED listing price separately, clear predicted price
    price              = int(float(request.form.get('price', 0)))
    location           = request.form.get('location', session.get('location', ''))
    session['selected_price']  = price
    session['predicted_price'] = None   # clear so payment uses selected price
    session['location']        = location
    session['payment_from']    = 'filter'
    return redirect(url_for('payment'))

@app.route('/payment', methods=['GET','POST'])
@login_required
def payment():
    # Use selected_price if coming from filter, predicted_price if from predict
    if session.get('payment_from') == 'filter':
        price = session.get('selected_price', 0)
    else:
        price = session.get('predicted_price', 0)

    if request.method == 'POST':
        session['payment_method'] = request.form.get('pay_method')
        session['final_price']    = price
        return redirect(url_for('payment_success'))

    back_url = url_for('result',
        pred=session.get('predicted_price', 0),
        low=round((session.get('predicted_price') or 0) * 0.92),
        high=round((session.get('predicted_price') or 0) * 1.08)
    ) if session.get('payment_from') == 'predict' else url_for('filter_listings')

    return render_template("payment.html", price=price,
                           city=session.get('city',''),
                           location=session.get('location',''),
                           back_url=back_url)

@app.route('/payment/success')
@login_required
def payment_success():
    return render_template("payment_success.html",
        name=session.get('user_name',''),
        price=session.get('final_price', 0),
        method=session.get('payment_method',''),
        city=session.get('city',''),
        location=session.get('location',''))

if __name__ == "__main__":
    app.run(debug=True)