# ValuNest — House Price Prediction & Booking Portal

ValuNest is an advanced, feature-rich Machine Learning web application designed to predict real estate prices across major Indian cities and facilitate simulated property bookings, EMI calculation, database persistence, and secure user management.

## 📖 Comprehensive Documentation

For detailed information about how the project works, why specific technologies were chosen, architecture details, and project components, please see:
👉 **[PROJECT_DETAILS.md](file:///c:/Users/haris/Documents/DBMS/My%20files/Documents/VS_Code/project/house-price-prediction/PROJECT_DETAILS.md)**

---

## 🚀 Quick Start Guide

### 1. Install Requirements
```bash
pip install -r requirements.txt
```

### 2. Train the Machine Learning Model
Compare Random Forest, Gradient Boosting, and other algorithms, then save the best model:
```bash
python train_model.py
```

### 3. Environment Variables Setup
Copy the example environment file and fill in details for external integrations (such as Supabase, Twilio, or Google/Firebase OAuth):
```bash
copy .env.example .env
```

### 4. Run the Web Server
Launch the Flask development server:
```bash
python app.py
```
Visit the local server in your browser: `http://127.0.0.1:5000`

---

## 🛠️ Tech Stack at a Glance
- **Backend:** Python, Flask
- **Data & Machine Learning:** Pandas, NumPy, Scikit-learn, Pickle
- **Database:** Supabase (Cloud PostgreSQL) or SQLite (Local fallback file `users.db`)
- **Authentication:** Custom Email/Password, Native Google OAuth, or Firebase Auth
- **Communications:** Twilio SMS API