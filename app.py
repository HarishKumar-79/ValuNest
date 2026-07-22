import os, sqlite3, pickle, re, json, secrets, base64, urllib.parse, urllib.request, urllib.error, hashlib
from urllib.parse import quote_plus
import numpy as np
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
from datetime import datetime
from calendar import monthrange

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = "houseprice_secret_2025"
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024

BASE          = os.path.dirname(os.path.abspath(__file__))
DB            = os.path.join(BASE, "users.db")
CSV           = os.path.join(BASE, "merged_files.csv")
UPLOAD_FOLDER = os.path.join(BASE, "static", "uploads")
ALLOWED_EXT   = {'png','jpg','jpeg','gif'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

model        = pickle.load(open(os.path.join(BASE,"model.pkl"),"rb"))
feature_cols = pickle.load(open(os.path.join(BASE,"feature_cols.pkl"),"rb"))
df           = pd.read_csv(CSV)
CITIES       = sorted(df['City'].dropna().unique().tolist())

ADMIN_EMAIL    = os.environ.get("ADMIN_EMAIL", "admin@house.com")
ADMIN_PASSWORD = "admin123"
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "")
FIREBASE_API_KEY = os.environ.get("FIREBASE_API_KEY", "")
FIREBASE_AUTH_DOMAIN = os.environ.get("FIREBASE_AUTH_DOMAIN", "")
FIREBASE_PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID", "")
FIREBASE_APP_ID = os.environ.get("FIREBASE_APP_ID", "")
SMS_PROVIDER = os.environ.get("SMS_PROVIDER", "").strip().lower()
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER", "")

CITY_COORDS = {
    'Bangalore':(12.9716,77.5946),'Mumbai':(19.0760,72.8777),
    'Delhi':(28.7041,77.1025),'Hyderabad':(17.3850,78.4867),
    'Chennai':(13.0827,80.2707),'Kolkata':(22.5726,88.3639),
}

def allowed_file(f): return '.' in f and f.rsplit('.',1)[1].lower() in ALLOWED_EXT

def get_db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def ensure_column(c, table, column, definition):
    existing = [row[1] for row in c.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in existing:
        c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

def get_setting(key, default_value=''):
    with get_db() as c:
        row = c.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
        return row['value'] if row else default_value

def set_setting(key, value):
    with get_db() as c:
        c.execute("""INSERT INTO app_settings (key, value) VALUES (?, ?)
                     ON CONFLICT(key) DO UPDATE SET value=excluded.value""", (key, str(value)))
        c.commit()

def is_google_email(email):
    return bool(re.search(r'@(gmail\.com|googlemail\.com)$', email or '', re.I))

def google_maps_search_url(location, city):
    query = f"{location}, {city}, India"
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(query)}"

def google_maps_embed_url(location, city):
    query = f"{location}, {city}, India"
    return f"https://www.google.com/maps?q={quote_plus(query)}&output=embed"

def oauth_enabled():
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GOOGLE_REDIRECT_URI)

def firebase_enabled():
    return bool(FIREBASE_API_KEY and FIREBASE_AUTH_DOMAIN and FIREBASE_PROJECT_ID and FIREBASE_APP_ID)

def firebase_config():
    if not firebase_enabled():
        return {}
    return {
        "apiKey": FIREBASE_API_KEY,
        "authDomain": FIREBASE_AUTH_DOMAIN,
        "projectId": FIREBASE_PROJECT_ID,
        "appId": FIREBASE_APP_ID,
    }

def verify_firebase_id_token(id_token):
    if not firebase_enabled():
        return None, "Firebase Google sign-in is not configured."
    if not id_token:
        return None, "Missing Firebase ID token."
    endpoint = f"https://identitytoolkit.googleapis.com/v1/accounts:lookup?key={urllib.parse.quote(FIREBASE_API_KEY)}"
    payload = json.dumps({"idToken": id_token}).encode("utf-8")
    request_obj = urllib.request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request_obj, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            error_data = json.loads(exc.read().decode("utf-8"))
            message = error_data.get("error", {}).get("message", "Firebase token verification failed.")
        except Exception:
            message = "Firebase token verification failed."
        return None, message
    except Exception:
        return None, "Could not contact Firebase to verify sign-in."

    users = data.get("users") or []
    if not users:
        return None, "Firebase token is not valid."
    firebase_user = users[0]
    providers = firebase_user.get("providerUserInfo") or []
    has_google_provider = any(provider.get("providerId") == "google.com" for provider in providers)
    if not has_google_provider:
        return None, "Please sign in with a real Google account."
    if not firebase_user.get("emailVerified"):
        return None, "Google email must be verified."
    email = (firebase_user.get("email") or "").strip().lower()
    return {
        "sub": firebase_user.get("localId", ""),
        "email": email,
        "email_verified": True,
        "name": firebase_user.get("displayName") or email.split("@")[0],
        "picture": firebase_user.get("photoUrl", ""),
    }, None

def build_google_auth_url():
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online",
        "prompt": "select_account",
        "state": secrets.token_urlsafe(16),
    }
    session['google_oauth_state'] = params["state"]
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)

def exchange_google_code(code):
    data = urllib.parse.urlencode({
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))

def fetch_google_userinfo(access_token):
    req = urllib.request.Request(
        "https://openidconnect.googleapis.com/v1/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))

def google_signup_or_login(google_profile):
    email = (google_profile.get("email") or "").strip().lower()
    if not google_profile.get("email_verified"):
        return None, "Google email must be verified."
    name = (google_profile.get("name") or google_profile.get("given_name") or "Google User").strip()
    photo = google_profile.get("picture") or ""
    google_sub = google_profile.get("sub") or ""
    with get_db() as c:
        user = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user:
            c.execute("UPDATE users SET name=?, photo=?, google_sub=?, oauth_provider='google' WHERE id=?",
                      (name, photo, google_sub, user["id"]))
            c.commit()
            user = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        else:
            placeholder_password = secrets.token_urlsafe(24)
            hashed = generate_password_hash(placeholder_password)
            c.execute(
                "INSERT INTO users (name,email,password,plain_password,photo,status,google_sub,oauth_provider) VALUES (?,?,?,?,?,?,?,?)",
                (name, email, hashed, "", photo, "active", google_sub, "google"),
            )
            c.commit()
            user = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    return user, None

def make_otp():
    return f"{secrets.randbelow(1000000):06d}"

def send_sms_otp(phone_number, otp):
    if not phone_number:
        return False, "Please add your mobile number in profile first."
    body = f"HomeFinder OTP: {otp}. Do not share this code with anyone."
    if SMS_PROVIDER == "twilio" and TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER:
        endpoint = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
        payload = urllib.parse.urlencode({
            "To": phone_number,
            "From": TWILIO_FROM_NUMBER,
            "Body": body,
        }).encode("utf-8")
        request_obj = urllib.request.Request(endpoint, data=payload, method="POST")
        auth = base64.b64encode(f"{TWILIO_ACCOUNT_SID}:{TWILIO_AUTH_TOKEN}".encode("utf-8")).decode("utf-8")
        request_obj.add_header("Authorization", f"Basic {auth}")
        request_obj.add_header("Content-Type", "application/x-www-form-urlencoded")
        with urllib.request.urlopen(request_obj, timeout=20) as response:
            return True, json.loads(response.read().decode("utf-8"))
    return False, "SMS provider is not configured."

def netbanking_otp_required():
    return SMS_PROVIDER == "twilio" and bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER)

def store_pending_netbanking_otp(bank_name, otp, expires_at):
    session["nb_otp"] = otp
    session["nb_otp_expires"] = expires_at
    session["nb_otp_bank"] = bank_name

def pending_netbanking_otp_valid(entered_otp):
    stored_otp = session.get("nb_otp")
    expires_at = session.get("nb_otp_expires")
    if not stored_otp or not expires_at:
        return False
    if datetime.now().timestamp() > float(expires_at):
        return False
    return entered_otp == stored_otp

def calculate_emi(principal, months, annual_rate=0.12):
    if not months or months <= 0:
        return 0
    monthly_rate = annual_rate / 12
    factor = (1 + monthly_rate) ** months
    if factor == 1:
        return principal / months
    return principal * monthly_rate * factor / (factor - 1)

def add_months(source_date, months):
    month_index = source_date.month - 1 + months
    year = source_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(source_date.day, monthrange(year, month)[1])
    return source_date.replace(year=year, month=month, day=day)

def init_db():
    with get_db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL, plain_password TEXT NOT NULL,
            phone TEXT DEFAULT '', address TEXT DEFAULT '',
            photo TEXT DEFAULT '', status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("""CREATE TABLE IF NOT EXISTS password_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL, plain_password TEXT NOT NULL,
            changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("""CREATE TABLE IF NOT EXISTS login_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL, user_name TEXT NOT NULL,
            action TEXT NOT NULL,
            logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("""CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL, user_name TEXT NOT NULL,
            city TEXT NOT NULL, location TEXT NOT NULL,
            price REAL NOT NULL, payment_method TEXT,
            txn_id TEXT DEFAULT '', booking_type TEXT DEFAULT 'predicted',
            status TEXT DEFAULT 'cart', paid_at TIMESTAMP,
            booked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("""CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            sender_name TEXT NOT NULL,
            sender_role TEXT NOT NULL,
            receiver_id INTEGER,
            receiver_name TEXT DEFAULT '',
            receiver_role TEXT NOT NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("""CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT '')""")
        c.execute("""CREATE TABLE IF NOT EXISTS password_resets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT NOT NULL UNIQUE,
            expires_at TIMESTAMP NOT NULL,
            used INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        ensure_column(c, "users", "google_sub", "TEXT DEFAULT ''")
        ensure_column(c, "users", "oauth_provider", "TEXT DEFAULT ''")
        ensure_column(c, "bookings", "payment_bank", "TEXT DEFAULT ''")
        ensure_column(c, "bookings", "emi_tenure", "INTEGER DEFAULT 0")
        ensure_column(c, "bookings", "emi_rate", "REAL DEFAULT 0")
        ensure_column(c, "bookings", "emi_monthly", "REAL DEFAULT 0")
        ensure_column(c, "bookings", "emi_total_payable", "REAL DEFAULT 0")
        ensure_column(c, "bookings", "emi_next_date", "TEXT DEFAULT ''")
        ensure_column(c, "messages", "sender_email", "TEXT DEFAULT ''")
        ensure_column(c, "messages", "receiver_email", "TEXT DEFAULT ''")
        c.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)", ("emi_rate", "12"))
        c.commit()

init_db()

@app.context_processor
def inject_helpers():
    return dict(
        is_google_email=is_google_email,
        google_maps_search_url=google_maps_search_url,
        google_maps_embed_url=google_maps_embed_url,
        oauth_enabled=oauth_enabled(),
        firebase_enabled=firebase_enabled(),
        firebase_config=firebase_config(),
        admin_email=ADMIN_EMAIL,
    )

def validate_password(pw):
    errs=[]
    if len(pw)<8: errs.append("At least 8 characters")
    if not re.search(r'[A-Z]',pw): errs.append("One uppercase letter (A-Z)")
    if not re.search(r'[a-z]',pw): errs.append("One lowercase letter (a-z)")
    if not re.search(r'[0-9]',pw): errs.append("One number (0-9)")
    if not re.search(r'[!@#$%^&*(),.?\":{}|<>]',pw): errs.append("One special character (!@#$%)")
    return errs

def login_required(f):
    @wraps(f)
    def d(*a,**k):
        if 'user_id' not in session: return redirect(url_for('login'))
        return f(*a,**k)
    return d

def admin_required(f):
    @wraps(f)
    def d(*a,**k):
        if not session.get('admin'): return redirect(url_for('admin_login'))
        return f(*a,**k)
    return d

def any_auth_required(f):
    @wraps(f)
    def d(*a,**k):
        if not session.get('admin') and 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*a,**k)
    return d

# ===== AUTH =====
@app.route('/')
def index():
    if 'user_id' in session: return render_template('home.html')
    return redirect(url_for('login'))

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'GET' and (firebase_enabled() or oauth_enabled()):
        return render_template("register.html")
    if request.method=='POST':
        if firebase_enabled() or oauth_enabled():
            flash("Please use Google sign-in to create an account.","error")
            return render_template("register.html")
        name=request.form['name'].strip()
        email=request.form['email'].strip().lower()
        pw=request.form['password']
        confirm=request.form['confirm']
        if not is_google_email(email):
            flash("Please register with a Google email address such as @gmail.com.","error")
            return render_template("register.html",name=name,email=email)
        errs=validate_password(pw)
        if errs: return render_template("register.html",pw_errors=errs,name=name,email=email)
        if pw!=confirm:
            flash("Passwords do not match.","error")
            return render_template("register.html",name=name,email=email)
        hashed=generate_password_hash(pw)
        try:
            with get_db() as c:
                c.execute("INSERT INTO users (name,email,password,plain_password) VALUES (?,?,?,?)",(name,email,hashed,pw))
                c.commit()
                uid=c.execute("SELECT id FROM users WHERE email=?",(email,)).fetchone()['id']
                c.execute("INSERT INTO password_history (user_id,plain_password) VALUES (?,?)",(uid,pw))
                c.commit()
            flash("Account created! Please log in.","success")
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash("Email already registered.","error")
    return render_template("register.html")

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'GET' and (firebase_enabled() or oauth_enabled()):
        return render_template("login.html")
    if request.method=='POST':
        if firebase_enabled() or oauth_enabled():
            flash("Please use Google sign-in to access your account.","error")
            return render_template("login.html")
        email=request.form['email'].strip().lower()
        pw=request.form['password']
        with get_db() as c:
            user=c.execute("SELECT * FROM users WHERE email=?",(email,)).fetchone()
        if user:
            if user['status']=='blocked':
                flash("Your account has been blocked. Contact admin.","error")
                return render_template("login.html")
            if check_password_hash(user['password'],pw):
                session['user_id']=user['id']
                session['user_name']=user['name']
                session['user_photo']=user['photo'] or ''
                # Log login
                with get_db() as c:
                    c.execute("INSERT INTO login_logs (user_id,user_name,action) VALUES (?,?,?)",
                              (user['id'],user['name'],'login'))
                    c.commit()
                return redirect(url_for('index'))
        flash("Invalid email or password.","error")
    return render_template("login.html")

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        with get_db() as c:
            user = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user:
            token = secrets.token_urlsafe(32)
            expires_at = datetime.now().timestamp() + 3600 # 1 hour validity
            with get_db() as c:
                c.execute("INSERT INTO password_resets (user_id, token, expires_at) VALUES (?, ?, ?)",
                          (user['id'], token, expires_at))
                c.commit()
            reset_link = url_for('reset_password', token=token, _external=True)
            flash(f"Password reset link created successfully! Link: {reset_link}", "success")
            return redirect(url_for('reset_password', token=token))
        else:
            flash("If that email address is registered, a password reset link has been generated.", "info")
            return redirect(url_for('forgot_password'))
    return render_template("forgot_password.html")

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    now = datetime.now().timestamp()
    with get_db() as c:
        reset_req = c.execute("SELECT * FROM password_resets WHERE token=? AND used=0 AND expires_at > ?", (token, now)).fetchone()
    if not reset_req:
        flash("Invalid or expired password reset link.", "error")
        return redirect(url_for('forgot_password'))
    
    if request.method == 'POST':
        pw = request.form['password']
        confirm = request.form['confirm']
        errs = validate_password(pw)
        if errs:
            return render_template("reset_password.html", pw_errors=errs, token=token)
        if pw != confirm:
            flash("Passwords do not match.", "error")
            return render_template("reset_password.html", token=token)
        
        hashed = generate_password_hash(pw)
        with get_db() as c:
            c.execute("UPDATE users SET password=?, plain_password=? WHERE id=?", (hashed, pw, reset_req['user_id']))
            c.execute("UPDATE password_resets SET used=1 WHERE id=?", (reset_req['id'],))
            c.execute("INSERT INTO password_history (user_id, plain_password) VALUES (?, ?)", (reset_req['user_id'], pw))
            c.commit()
        flash("Your password has been reset successfully! Please log in.", "success")
        return redirect(url_for('login'))
        
    return render_template("reset_password.html", token=token)

@app.route('/auth/firebase/google', methods=['POST'])
def firebase_google_auth():
    payload = request.get_json(force=True, silent=True) or {}
    role = (payload.get("role") or "user").strip().lower()
    google_profile, error = verify_firebase_id_token(payload.get("idToken", ""))
    if error:
        return {"ok": False, "error": error}, 400

    if role == "admin":
        if google_profile["email"] != ADMIN_EMAIL.lower():
            return {"ok": False, "error": "This Google account is not allowed for admin login."}, 403
        session.clear()
        session["admin"] = True
        session["admin_name"] = google_profile.get("name") or "Administrator"
        return {"ok": True, "redirect": url_for("admin_dashboard")}

    user, error = google_signup_or_login(google_profile)
    if error:
        return {"ok": False, "error": error}, 400
    if user["status"] == "blocked":
        return {"ok": False, "error": "Your account has been blocked. Contact admin."}, 403

    session.clear()
    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    session["user_photo"] = user["photo"] or ""
    session["user_email"] = user["email"]
    with get_db() as c:
        c.execute("INSERT INTO login_logs (user_id,user_name,action) VALUES (?,?,?)",
                  (user["id"], user["name"], "login"))
        c.commit()
    return {"ok": True, "redirect": url_for("index")}

@app.route('/auth/google/start')
def google_auth_start():
    if not oauth_enabled():
        flash("Google sign-in is not configured yet.","error")
        return redirect(url_for('login'))
    return redirect(build_google_auth_url())

@app.route('/auth/google/callback')
def google_auth_callback():
    if not oauth_enabled():
        flash("Google sign-in is not configured yet.","error")
        return redirect(url_for('login'))
    if request.args.get("state") != session.get("google_oauth_state"):
        flash("Google sign-in state mismatch. Please try again.","error")
        return redirect(url_for('login'))
    code = request.args.get("code")
    if not code:
        flash("Google sign-in did not return a code.","error")
        return redirect(url_for('login'))
    try:
        token_data = exchange_google_code(code)
        google_profile = fetch_google_userinfo(token_data.get("access_token", ""))
        user, error = google_signup_or_login(google_profile)
        if error:
            flash(error, "error")
            return redirect(url_for('login'))
        session.clear()
        session['user_id'] = user['id']
        session['user_name'] = user['name']
        session['user_photo'] = user['photo'] or ''
        session['user_email'] = user['email']
        with get_db() as c:
            c.execute("INSERT INTO login_logs (user_id,user_name,action) VALUES (?,?,?)",
                      (user['id'], user['name'], 'login'))
            c.commit()
        flash("Signed in with Google successfully.","success")
        return redirect(url_for('index'))
    except Exception as exc:
        print("Google auth error:", exc)
        flash("Google sign-in failed. Please try again.","error")
        return redirect(url_for('login'))

@app.route('/logout')
def logout():
    # Log logout BEFORE clearing session
    if 'user_id' in session:
        uid=session['user_id']
        uname=session.get('user_name','')
        try:
            with get_db() as c:
                c.execute("INSERT INTO login_logs (user_id,user_name,action) VALUES (?,?,?)",
                          (uid,uname,'logout'))
                c.commit()
        except Exception as e:
            print("Logout log error:",e)
    session.clear()
    return redirect(url_for('login'))

# ===== PROFILE =====
@app.route('/profile', methods=['GET','POST'])
@login_required
def profile():
    with get_db() as c:
        user=c.execute("SELECT * FROM users WHERE id=?",(session['user_id'],)).fetchone()
    if request.method=='POST':
        name=request.form['name'].strip()
        phone=request.form.get('phone','').strip()
        address=request.form.get('address','').strip()
        email=request.form['email'].strip().lower()
        if not is_google_email(email):
            flash("Please keep a Google email address such as @gmail.com.","error")
            return render_template("profile.html",user=user)
        photo=user['photo']
        if 'photo' in request.files:
            file=request.files['photo']
            if file and file.filename and allowed_file(file.filename):
                fname=secure_filename(f"user_{session['user_id']}_{file.filename}")
                file.save(os.path.join(UPLOAD_FOLDER,fname))
                photo=fname
        new_pw=request.form.get('new_password','').strip()
        if new_pw:
            errs=validate_password(new_pw)
            if errs:
                flash("Password does not meet requirements.","error")
                return render_template("profile.html",user=user,pw_errors=errs)
            conf=request.form.get('confirm_password','').strip()
            if new_pw!=conf:
                flash("Passwords do not match.","error")
                return render_template("profile.html",user=user)
            old_pw=request.form.get('old_password','').strip()
            if not check_password_hash(user['password'],old_pw):
                flash("Current password is incorrect.","error")
                return render_template("profile.html",user=user)
            hashed=generate_password_hash(new_pw)
            with get_db() as c:
                c.execute("UPDATE users SET name=?,email=?,phone=?,address=?,photo=?,password=?,plain_password=? WHERE id=?",
                          (name,email,phone,address,photo,hashed,new_pw,session['user_id']))
                c.execute("INSERT INTO password_history (user_id,plain_password) VALUES (?,?)",
                          (session['user_id'],new_pw))
                c.commit()
        else:
            with get_db() as c:
                c.execute("UPDATE users SET name=?,email=?,phone=?,address=?,photo=? WHERE id=?",
                          (name,email,phone,address,photo,session['user_id']))
                c.commit()
        session['user_name']=name
        session['user_photo']=photo
        flash("Profile updated successfully!","success")
        return redirect(url_for('profile'))
    return render_template("profile.html",user=user)

@app.route('/settings', methods=['GET','POST'])
@any_auth_required
def settings():
    if session.get('admin'):
        settings_owner = {
            "name": "Admin",
            "email": ADMIN_EMAIL,
            "role": "admin",
        }
    else:
        with get_db() as c:
            user = c.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
        settings_owner = dict(user)
        settings_owner["role"] = "user"
    if request.method == 'POST':
        if session.get('admin'):
            set_setting("emi_rate", request.form.get("emi_rate", "12"))
            flash("Admin settings saved.","success")
        else:
            flash("Settings saved locally for this session.","success")
        return redirect(url_for('settings'))
    return render_template("settings.html", owner=settings_owner, emi_rate=float(get_setting("emi_rate", "12")))

@app.route('/admin/profile')
@admin_required
def admin_profile():
    with get_db() as c:
        total_users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        recent_logs = c.execute("SELECT * FROM login_logs ORDER BY logged_at DESC LIMIT 20").fetchall()
    return render_template("admin_profile.html",
        name="Admin",
        email=ADMIN_EMAIL,
        total_users=total_users,
        recent_logs=recent_logs)

@app.route('/messages', methods=['GET'])
@any_auth_required
def messages():
    if session.get('admin'):
        with get_db() as c:
            inbox = c.execute("SELECT * FROM messages ORDER BY created_at DESC").fetchall()
            users = c.execute("SELECT id, name, email FROM users ORDER BY name ASC").fetchall()
        return render_template("messages.html", inbox=inbox, users=users, role="admin")
    with get_db() as c:
        inbox = c.execute(
            "SELECT * FROM messages WHERE sender_id=? OR receiver_id=? OR receiver_role='admin' ORDER BY created_at DESC",
            (session['user_id'], session['user_id']),
        ).fetchall()
    return render_template("messages.html", inbox=inbox, role="user")

@app.route('/messages/send', methods=['POST'])
@any_auth_required
def send_message():
    subject = request.form.get('subject', '').strip()
    body = request.form.get('body', '').strip()
    if not subject or not body:
        flash("Subject and message are required.","error")
        return redirect(url_for('messages'))
    if session.get('admin'):
        receiver_id = request.form.get('receiver_id')
        receiver_name = request.form.get('receiver_name', '')
        if not receiver_id:
            flash("Choose a user to send the message.","error")
            return redirect(url_for('messages'))
        with get_db() as c:
            user = c.execute("SELECT * FROM users WHERE id=?", (int(receiver_id),)).fetchone()
            c.execute("""INSERT INTO messages
                (sender_id,sender_name,sender_email,sender_role,receiver_id,receiver_name,receiver_email,receiver_role,subject,body)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (0, 'Admin', ADMIN_EMAIL, 'admin', int(receiver_id), user['name'] if user else receiver_name, user['email'] if user else '', 'user', subject, body))
            c.commit()
        flash("Message sent to user.","success")
        return redirect(url_for('messages'))
    with get_db() as c:
        user = c.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
        c.execute("""INSERT INTO messages
            (sender_id,sender_name,sender_email,sender_role,receiver_id,receiver_name,receiver_email,receiver_role,subject,body)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (session['user_id'], session['user_name'], user['email'] if user else '', 'user', None, 'Admin', ADMIN_EMAIL, 'admin', subject, body))
        c.commit()
    flash("Message sent to admin.","success")
    return redirect(url_for('messages'))

# ===== MAP =====
@app.route('/map')
@login_required
def property_map():
    with get_db() as c:
        bookings=c.execute("SELECT * FROM bookings WHERE user_id=? AND status='confirmed' ORDER BY paid_at DESC",
                           (session['user_id'],)).fetchall()
    import random
    properties=[]
    for b in bookings:
        city=b['city']
        coords=CITY_COORDS.get(city,(20.5937,78.9629))
        lat=coords[0]+random.uniform(-0.05,0.05)
        lng=coords[1]+random.uniform(-0.05,0.05)
        properties.append({'city':city,'location':b['location'],'price':b['price'],
                           'paid_at':b['paid_at'] or '','lat':round(lat,4),'lng':round(lng,4)})
    return render_template("map.html",properties=properties)

# ===== MAIN PAGES =====
@app.route('/city', methods=['GET','POST'])
@login_required
def select_city():
    if request.method=='POST':
        session['city']=request.form['city']
        return redirect(url_for('select_location'))
    return render_template("city.html",cities=CITIES)

@app.route('/location', methods=['GET','POST'])
@login_required
def select_location():
    city=session.get('city',CITIES[0])
    locations=sorted(df[df['City']==city]['Location'].dropna().unique().tolist())
    if request.method=='POST':
        session['location']=request.form['location']
        return redirect(url_for('choose_option'))
    return render_template("location.html",city=city,locations=locations)

@app.route('/options')
@login_required
def choose_option():
    return render_template("options.html",city=session.get('city',''),location=session.get('location',''))

@app.route('/predict', methods=['GET','POST'])
@login_required
def predict():
    city=session.get('city','')
    location=session.get('location','')
    if request.method=='POST':
        try:
            area=float(request.form['area'])
            bedrooms=float(request.form['bedrooms'])
            bathrooms=float(request.form['bathrooms'])
            resale=float(request.form['resale'])
            parking=float(request.form['parking'])
            lift=float(request.form['lift'])
            gym=float(request.form.get('gym',0))
            pool=float(request.form.get('pool',0))
            security=float(request.form.get('security',0))
            power=float(request.form.get('power',0))
            club=float(request.form.get('club',0))
        except ValueError:
            flash("Please enter valid numbers.","error")
            return render_template("predict.html",city=city,location=location)
        row={col:0 for col in feature_cols}
        row['Area']=area; row['No. of Bedrooms']=bedrooms; row['Resale']=resale
        row['CarParking']=parking; row['LiftAvailable']=lift; row['Gymnasium']=gym
        row['SwimmingPool']=pool; row['24X7Security']=security
        row['PowerBackup']=power; row['ClubHouse']=club
        city_col=f'City_{city}'
        if city_col in row: row[city_col]=1
        pred=model.predict(pd.DataFrame([row])[feature_cols])[0]
        if pred<100000:
            return render_template("predict.html",city=city,location=location,
                                   error="Could not estimate a valid price. Please try different values.")
        low=round(pred*0.92); high=round(pred*1.08)
        session['predicted_price']=round(pred)
        session['payment_from']='predict'
        session['booking_type']='predicted'
        return redirect(url_for('result',pred=round(pred),low=low,high=high))
    return render_template("predict.html",city=city,location=location)

@app.route('/result')
@login_required
def result():
    pred=int(request.args.get('pred',0))
    low=int(request.args.get('low',0))
    high=int(request.args.get('high',0))
    city=session.get('city','')
    location=session.get('location','')
    return render_template("result.html",prediction=pred,low=low,high=high,city=city,location=location)

@app.route('/filter', methods=['GET','POST'])
@login_required
def filter_listings():
    city=session.get('city','')
    location=session.get('location','')
    listings=[]; no_results=False
    if request.method=='POST':
        try:
            budget=float(request.form['budget'])
            margin=float(request.form.get('margin',15))
        except ValueError:
            flash("Please enter a valid budget.","error")
            return render_template("filter.html",city=city,location=location,listings=[],no_results=False)
        low=budget*(1-margin/100); high=budget*(1+margin/100)
        with get_db() as c:
            taken=c.execute("SELECT location FROM bookings WHERE city=? AND status IN ('cart','confirmed')",(city,)).fetchall()
        taken_locs=[t['location'] for t in taken]
        filtered=df[(df['City']==city)&(df['Location']==location)&(df['Price']>=low)&(df['Price']<=high)].copy()
        if len(filtered)==0:
            filtered=df[(df['City']==city)&(df['Price']>=low)&(df['Price']<=high)].copy()
            no_results=True
        filtered=filtered.sort_values('Price').head(10)
        listings=filtered[['Location','Price','Area','No. of Bedrooms','CarParking','LiftAvailable','Gymnasium','SwimmingPool']].to_dict('records')
        for l in listings: l['is_taken']=l['Location'] in taken_locs
    return render_template("filter.html",city=city,location=location,listings=listings,no_results=no_results)

@app.route('/select_listing', methods=['POST'])
@login_required
def select_listing():
    price=int(float(request.form.get('price',0)))
    location=request.form.get('location',session.get('location',''))
    session['selected_price']=price; session['predicted_price']=None
    session['location']=location; session['payment_from']='filter'
    session['booking_type']='budget_filter'
    return redirect(url_for('payment'))

@app.route('/add_to_cart_filter', methods=['POST'])
@login_required
def add_to_cart_filter():
    price=int(float(request.form.get('price',0)))
    location=request.form.get('location',session.get('location',''))
    city=session.get('city','')
    with get_db() as c:
        existing=c.execute("SELECT id FROM bookings WHERE user_id=? AND city=? AND location=? AND status='cart'",
                           (session['user_id'],city,location)).fetchone()
        if not existing:
            c.execute("INSERT INTO bookings (user_id,user_name,city,location,price,booking_type,status) VALUES (?,?,?,?,?,'budget_filter','cart')",
                      (session['user_id'],session['user_name'],city,location,price))
            c.commit()
            flash("House added to cart! Pay later from My History.","success")
        else:
            flash("Already in your cart.","error")
    return redirect(url_for('filter_listings'))

@app.route('/add_to_cart', methods=['POST'])
@login_required
def add_to_cart():
    price=session.get('selected_price',0) if session.get('payment_from')=='filter' else session.get('predicted_price',0)
    city=session.get('city',''); location=session.get('location','')
    booking_type=session.get('booking_type','predicted')
    with get_db() as c:
        existing=c.execute("SELECT id FROM bookings WHERE user_id=? AND city=? AND location=? AND status='cart'",
                           (session['user_id'],city,location)).fetchone()
        if not existing:
            c.execute("INSERT INTO bookings (user_id,user_name,city,location,price,booking_type,status) VALUES (?,?,?,?,?,?,'cart')",
                      (session['user_id'],session['user_name'],city,location,price,booking_type))
            c.commit()
            flash("Added to cart! Pay later from My History.","success")
        else:
            flash("Already in your cart.","error")
    return redirect(url_for('user_history'))

@app.route('/payment', methods=['GET','POST'])
@login_required
def payment():
    price=session.get('selected_price',0) if session.get('payment_from')=='filter' else session.get('predicted_price',0)
    if request.method=='POST':
        method=request.form.get('pay_method')
        txn_id=request.form.get('txn_id','')
        if method == 'Net Banking' and netbanking_otp_required():
            if not pending_netbanking_otp_valid(request.form.get('nb_otp','').strip()):
                flash("Please verify the OTP sent to your mobile number.","error")
                return redirect(url_for('payment'))
        session['payment_method']=method
        session['txn_id']=txn_id
        session['final_price']=price
        session['payment_bank']=request.form.get('nb_bank') or request.form.get('emi_bank') or ''
        session['emi_tenure']=None
        session['emi_monthly']=None
        session['emi_total_payable']=None
        session['emi_next_date']=None
        session['emi_rate']=float(get_setting("emi_rate", "12"))
        city=session.get('city',''); location=session.get('location','')
        booking_type=session.get('booking_type','predicted')
        paid_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if method == 'EMI':
            emi_tenure = int(request.form.get('emi_tenure', 6))
            emi_rate = float(get_setting("emi_rate", "12"))
            emi_monthly = round(calculate_emi(price, emi_tenure, emi_rate / 100))
            next_emi_date = add_months(datetime.now(), 1)
            session['emi_tenure'] = emi_tenure
            session['emi_rate'] = emi_rate
            session['emi_monthly'] = emi_monthly
            session['emi_total_payable'] = round(emi_monthly * emi_tenure)
            session['emi_next_date'] = next_emi_date.strftime("%d %b %Y")
        with get_db() as c:
            existing=c.execute("SELECT id FROM bookings WHERE user_id=? AND city=? AND location=? AND status='cart'",
                               (session['user_id'],city,location)).fetchone()
            if existing:
                c.execute("""UPDATE bookings SET payment_method=?,txn_id=?,status='confirmed',paid_at=?,
                             payment_bank=?,emi_tenure=?,emi_rate=?,emi_monthly=?,emi_total_payable=?,emi_next_date=?
                             WHERE id=?""",
                          (method,txn_id,paid_at,session['payment_bank'],session['emi_tenure'],
                           session['emi_rate'],session['emi_monthly'],session['emi_total_payable'],
                           session['emi_next_date'],existing['id']))
            else:
                c.execute("""INSERT INTO bookings
                    (user_id,user_name,city,location,price,payment_method,txn_id,booking_type,status,paid_at,
                     payment_bank,emi_tenure,emi_rate,emi_monthly,emi_total_payable,emi_next_date)
                    VALUES (?,?,?,?,?,?,?,?,'confirmed',?,?,?,?,?,?,?)""",
                          (session['user_id'],session['user_name'],city,location,price,method,txn_id,booking_type,paid_at,
                           session['payment_bank'],session['emi_tenure'],session['emi_rate'],
                           session['emi_monthly'],session['emi_total_payable'],session['emi_next_date']))
            c.commit()
        return redirect(url_for('payment_success'))
    back_url=url_for('result',pred=session.get('predicted_price',0),
                     low=round((session.get('predicted_price') or 0)*0.92),
                     high=round((session.get('predicted_price') or 0)*1.08)
                    ) if session.get('payment_from')=='predict' else url_for('filter_listings')
    city=session.get('city',''); location=session.get('location','')
    return render_template("payment.html",price=price,city=city,location=location,back_url=back_url,
                           emi_rate=float(get_setting("emi_rate", "12")),
                           netbanking_otp_required=netbanking_otp_required())

@app.route('/payment/send-otp', methods=['POST'])
@login_required
def payment_send_otp():
    bank = (request.form.get('bank') or '').strip()
    if not bank:
        return {"ok": False, "error": "Select your bank first."}, 400
    if not netbanking_otp_required():
        session.pop("nb_otp", None)
        session.pop("nb_otp_expires", None)
        session["nb_otp_bank"] = bank
        return {"ok": True, "skip_otp": True, "message": "SMS OTP is not configured. OTP skipped for this demo payment."}
    with get_db() as c:
        user = c.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    phone = (user['phone'] or '').strip()
    if not phone:
        return {"ok": False, "error": "Add your mobile number in profile first."}, 400
    otp = make_otp()
    expires_at = datetime.now().timestamp() + 300
    store_pending_netbanking_otp(bank, otp, expires_at)
    try:
        sent, result = send_sms_otp(phone, otp)
        if not sent:
            return {"ok": False, "error": result}, 400
    except Exception as exc:
        print("OTP send error:", exc)
        return {"ok": False, "error": "Failed to send OTP."}, 500
    return {"ok": True, "message": "OTP sent to your mobile number."}

@app.route('/payment/success')
@login_required
def payment_success():
    return render_template("payment_success.html",
        name=session.get('user_name',''),price=session.get('final_price',0),
        method=session.get('payment_method',''),txn_id=session.get('txn_id',''),
        city=session.get('city',''),location=session.get('location',''),
        emi_tenure=session.get('emi_tenure'),emi_monthly=session.get('emi_monthly'),
        emi_total_payable=session.get('emi_total_payable'),emi_next_date=session.get('emi_next_date'),
        payment_bank=session.get('payment_bank',''),emi_rate=session.get('emi_rate'))

@app.route('/receipt/<int:booking_id>')
@any_auth_required
def receipt(booking_id):
    with get_db() as c:
        booking = c.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
        if not booking:
            flash("Receipt not found.","error")
            return redirect(url_for('admin_dashboard') if session.get('admin') else url_for('user_history'))
        if not session.get('admin') and booking['user_id'] != session.get('user_id'):
            flash("You cannot view this receipt.","error")
            return redirect(url_for('user_history'))
    return render_template("receipt.html", booking=booking, is_admin=bool(session.get('admin')))

@app.route('/pay_cart/<int:booking_id>', methods=['GET','POST'])
@login_required
def pay_cart(booking_id):
    with get_db() as c:
        booking=c.execute("SELECT * FROM bookings WHERE id=? AND user_id=?",(booking_id,session['user_id'])).fetchone()
    if not booking:
        flash("Booking not found.","error")
        return redirect(url_for('user_history'))
    if request.method=='POST':
        method=request.form.get('pay_method')
        txn_id=request.form.get('txn_id','')
        if method == 'Net Banking' and netbanking_otp_required():
            if not pending_netbanking_otp_valid(request.form.get('nb_otp','').strip()):
                flash("Please verify the OTP sent to your mobile number.","error")
                return redirect(url_for('pay_cart', booking_id=booking_id))
        paid_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        session['payment_method']=method
        session['txn_id']=txn_id
        session['final_price']=booking['price']
        session['city']=booking['city']
        session['location']=booking['location']
        session['payment_bank']=request.form.get('nb_bank') or request.form.get('emi_bank') or ''
        session['emi_tenure']=None
        session['emi_monthly']=None
        session['emi_total_payable']=None
        session['emi_next_date']=None
        session['emi_rate']=float(get_setting("emi_rate", "12"))
        if method == 'EMI':
            emi_tenure = int(request.form.get('emi_tenure', 6))
            emi_rate = float(get_setting("emi_rate", "12"))
            emi_monthly = round(calculate_emi(booking['price'], emi_tenure, emi_rate / 100))
            next_emi_date = add_months(datetime.now(), 1)
            session['emi_tenure'] = emi_tenure
            session['emi_rate'] = emi_rate
            session['emi_monthly'] = emi_monthly
            session['emi_total_payable'] = round(emi_monthly * emi_tenure)
            session['emi_next_date'] = next_emi_date.strftime("%d %b %Y")
        with get_db() as c:
            c.execute("""UPDATE bookings SET payment_method=?,txn_id=?,status='confirmed',paid_at=?,
                         payment_bank=?,emi_tenure=?,emi_rate=?,emi_monthly=?,emi_total_payable=?,emi_next_date=?
                         WHERE id=?""",
                      (method,txn_id,paid_at,session['payment_bank'],session['emi_tenure'],
                       session['emi_rate'],session['emi_monthly'],session['emi_total_payable'],
                       session['emi_next_date'],booking_id))
            c.commit()
        return redirect(url_for('payment_success'))
    return render_template("pay_cart.html",booking=booking,emi_rate=float(get_setting("emi_rate", "12")),
                           netbanking_otp_required=netbanking_otp_required())

@app.route('/remove_cart/<int:booking_id>', methods=['POST'])
@login_required
def remove_cart(booking_id):
    with get_db() as c:
        c.execute("DELETE FROM bookings WHERE id=? AND user_id=? AND status='cart'",(booking_id,session['user_id']))
        c.commit()
    flash("Removed from cart.","success")
    return redirect(url_for('user_history'))

@app.route('/history')
@login_required
def user_history():
    with get_db() as c:
        cart=c.execute("SELECT * FROM bookings WHERE user_id=? AND status='cart' ORDER BY booked_at DESC",(session['user_id'],)).fetchall()
        purchased=c.execute("SELECT * FROM bookings WHERE user_id=? AND status='confirmed' ORDER BY paid_at DESC",(session['user_id'],)).fetchall()
    return render_template("user_history.html",cart=cart,purchased=purchased,name=session.get('user_name',''))

# ===== ADMIN =====
@app.route('/admin/login', methods=['GET','POST'])
def admin_login():
    if session.get('admin'):
        return redirect(url_for('admin_dashboard'))
    if request.method=='POST':
        email=request.form['email'].strip().lower()
        pw=request.form['password']
        if email==ADMIN_EMAIL and pw==ADMIN_PASSWORD:
            session.clear()
            session['admin']=True
            session['admin_name']="Administrator"
            return redirect(url_for('admin_dashboard'))
        flash("Invalid admin credentials.","error")
    return render_template("admin_login.html")

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('admin_login'))

@app.route('/admin')
@admin_required
def admin_dashboard():
    with get_db() as c:
        users=c.execute("SELECT * FROM users ORDER BY id DESC").fetchall()
        bookings=c.execute("SELECT * FROM bookings ORDER BY id DESC").fetchall()
        recent_logs=c.execute("SELECT * FROM login_logs ORDER BY logged_at DESC LIMIT 10").fetchall()
        older_logs=c.execute("SELECT * FROM login_logs ORDER BY logged_at DESC LIMIT -1 OFFSET 10").fetchall()
    confirmed=[b for b in bookings if b['status']=='confirmed']
    cart_items=[b for b in bookings if b['status']=='cart']
    total_revenue=sum(b['price'] for b in confirmed)
    active_users=sum(1 for u in users if u['status']=='active')
    blocked_users=sum(1 for u in users if u['status']=='blocked')
    return render_template("admin_dashboard.html",
        users=users,bookings=bookings,confirmed=confirmed,cart_items=cart_items,
        recent_logs=recent_logs,
        older_logs=older_logs,
        total_users=len(users),total_bookings=len(bookings),
        total_revenue=total_revenue,active_users=active_users,blocked_users=blocked_users)

@app.route('/admin/view_user/<int:user_id>')
@admin_required
def view_user(user_id):
    with get_db() as c:
        user=c.execute("SELECT * FROM users WHERE id=?",(user_id,)).fetchone()
        bookings=c.execute("SELECT * FROM bookings WHERE user_id=? ORDER BY id DESC",(user_id,)).fetchall()
        pw_history=c.execute("SELECT * FROM password_history WHERE user_id=? ORDER BY changed_at DESC",(user_id,)).fetchall()
        login_logs=c.execute("SELECT * FROM login_logs WHERE user_id=? ORDER BY logged_at DESC",(user_id,)).fetchall()
        login_count=c.execute("SELECT COUNT(*) FROM login_logs WHERE user_id=? AND action='login'",(user_id,)).fetchone()[0]
        logout_count=c.execute("SELECT COUNT(*) FROM login_logs WHERE user_id=? AND action='logout'",(user_id,)).fetchone()[0]
    return render_template("view_user.html",user=user,bookings=bookings,
                           pw_history=pw_history,login_logs=login_logs,
                           login_count=login_count,logout_count=logout_count)

@app.route('/admin/edit_user/<int:user_id>', methods=['GET','POST'])
@admin_required
def edit_user(user_id):
    with get_db() as c:
        if request.method=='POST':
            name=request.form['name'].strip(); email=request.form['email'].strip().lower()
            status=request.form['status']; new_pw=request.form.get('password','').strip()
            if not is_google_email(email):
                user=c.execute("SELECT * FROM users WHERE id=?",(user_id,)).fetchone()
                flash("Admin can only save Google email addresses.","error")
                return render_template("edit_user.html",user=user)
            if new_pw:
                errs=validate_password(new_pw)
                if errs:
                    user=c.execute("SELECT * FROM users WHERE id=?",(user_id,)).fetchone()
                    flash("Password does not meet requirements.","error")
                    return render_template("edit_user.html",user=user,pw_errors=errs)
                hashed=generate_password_hash(new_pw)
                c.execute("UPDATE users SET name=?,email=?,status=?,password=?,plain_password=? WHERE id=?",(name,email,status,hashed,new_pw,user_id))
                c.execute("INSERT INTO password_history (user_id,plain_password) VALUES (?,?)",(user_id,new_pw))
            else:
                c.execute("UPDATE users SET name=?,email=?,status=? WHERE id=?",(name,email,status,user_id))
            c.commit()
            flash("User updated.","success")
            return redirect(url_for('admin_dashboard'))
        user=c.execute("SELECT * FROM users WHERE id=?",(user_id,)).fetchone()
    return render_template("edit_user.html",user=user)

@app.route('/admin/remove_booking/<int:booking_id>', methods=['POST'])
@admin_required
def remove_booking(booking_id):
    with get_db() as c:
        c.execute("DELETE FROM bookings WHERE id=?",(booking_id,))
        c.commit()
    flash("Booking removed.","success")
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/edit_booking/<int:id>', methods=['GET','POST'])
@admin_required
def edit_booking(id):
    with get_db() as c:
        if request.method=='POST':
            c.execute("UPDATE bookings SET price=?,city=?,location=?,payment_method=?,status=? WHERE id=?",
                      (float(request.form['price']),request.form['city'].strip(),
                       request.form['location'].strip(),request.form['payment_method'].strip(),
                       request.form['status'],id))
            c.commit()
            flash("Booking updated.","success")
            return redirect(url_for('admin_dashboard'))
        booking=c.execute("SELECT * FROM bookings WHERE id=?",(id,)).fetchone()
    return render_template("edit_booking.html",booking=booking)

@app.route('/admin/remove_user/<int:user_id>', methods=['POST'])
@admin_required
def remove_user(user_id):
    with get_db() as c:
        c.execute("DELETE FROM bookings WHERE user_id=?",(user_id,))
        c.execute("DELETE FROM password_history WHERE user_id=?",(user_id,))
        c.execute("DELETE FROM login_logs WHERE user_id=?",(user_id,))
        c.execute("DELETE FROM users WHERE id=?",(user_id,))
        c.commit()
    flash("User removed.","success")
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/block_user/<int:user_id>', methods=['POST'])
@admin_required
def block_user(user_id):
    with get_db() as c:
        c.execute("UPDATE users SET status='blocked' WHERE id=?",(user_id,))
        c.commit()
    flash("User blocked.","success")
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/unblock_user/<int:user_id>', methods=['POST'])
@admin_required
def unblock_user(user_id):
    with get_db() as c:
        c.execute("UPDATE users SET status='active' WHERE id=?",(user_id,))
        c.commit()
    flash("User unblocked.","success")
    return redirect(url_for('admin_dashboard'))

if __name__=="__main__":
    app.run(debug=True)
