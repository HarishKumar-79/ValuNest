# ValuNest — Comprehensive Project Documentation

Welcome to the technical documentation for **ValuNest** (also referred to as **HomeFinder** in training modules), an advanced, feature-rich House Price Prediction and booking web application. 

This document describes the project structure, how the application functions, the technologies used, and the design decisions behind them.

---

## Table of Contents
1. [Project Overview](#1-project-overview)
2. [Key Features](#2-key-features)
3. [System Architecture & How It Works](#3-system-architecture--how-it-works)
    - [Phase A: Machine Learning Pipeline](#phase-a-machine-learning-pipeline)
    - [Phase B: Web Application Backend & API](#phase-b-web-application-backend--api)
    - [Phase C: Database & Data Persistence](#phase-c-database--data-persistence)
4. [Technology Stack: What is Used and Why](#4-technology-stack-what-is-used-and-why)
5. [Directory Structure](#5-directory-structure)
6. [Setup and Execution](#6-setup-and-execution)

---

## 1. Project Overview

**ValuNest** is an end-to-end web application that allows users to predict house prices across multiple major Indian cities based on physical dimensions, bedroom counts, location/city, and a detailed list of amenities (e.g., swimming pool, security, backup power, etc.). 

Beyond basic house price prediction, the platform functions as a full real estate booking portal, allowing users to:
* View predicted prices.
* Add properties to a booking cart.
* Simulate EMI (Equated Monthly Installment) structures for purchasing properties.
* Execute simulated payments and track booking logs.
* Message administrators directly on the platform.

---

## 2. Key Features

* **Multi-Model ML Comparison:** Pipeline compares multiple regression algorithms (Random Forest, Gradient Boosting, etc.) and picks the best one using statistical metrics ($R^2$, MAE, MSE).
* **Dual-Database Layer:** Implements a transparent fallback mechanism. If Supabase (Cloud PostgreSQL) credentials are provided, the app connects to the cloud. Otherwise, it falls back to a local SQLite database (`users.db`).
* **Authentication Options:** Supports email/password authentication alongside security measures like password history checks (preventing reuse of recent passwords), plus modern login methods:
  * Native Google OAuth 2.0.
  * Firebase Google Authentication integration.
* **Property Booking & Cart:** Simulates a checkout flow for simulated properties.
* **Built-in EMI Calculator:** Computes monthly payouts, total payable amounts, next due dates, and links them with bookings.
* **Platform Messaging:** Simple, secure user-to-admin inbox system.
* **Notification Integration:** Integrated with Twilio to support SMS alerts.

---

## 3. System Architecture & How It Works

### Phase A: Machine Learning Pipeline
Located in [train_model.py](file:///c:/Users/haris/Documents/DBMS/My%20files/Documents/VS_Code/project/house-price-prediction/train_model.py):
1. **Data Load:** Loads historical housing data from [merged_files.csv](file:///c:/Users/haris/Documents/DBMS/My%20files/Documents/VS_Code/project/house-price-prediction/merged_files.csv).
2. **Outlier Filtering & Preprocessing:**
   * Removes houses outside the 1st to 99th percentile price bracket to avoid skewed training.
   * Quantifies amenities into binary $0/1$ flags and creates a combined metric `AmenityScore`.
   * Standardizes continuous numeric variables (`Area` and `No. of Bedrooms`) using `StandardScaler`.
3. **Model Selection:** Fits regression algorithms, compares their R² scores, and pickles the best model into `model.pkl` along with feature column structures (`feature_cols.pkl`) so that predictions can be calculated instantly in the web application.

### Phase B: Web Application Backend & API
Located in [app.py](file:///c:/Users/haris/Documents/DBMS/My%20files/Documents/VS_Code/project/house-price-prediction/app.py):
1. On start, the Flask server loads the trained ML model from `model.pkl`.
2. When a user requests a prediction, the app formats their inputs into the correct one-hot encoded vector matching `feature_cols.pkl`, passes it to the ML model, and renders the result.
3. The server manages routing, user session state, and integrations for Google Login, Firebase token verification, and Twilio SMS.

### Phase C: Database & Data Persistence
Located in [db/](file:///c:/Users/haris/Documents/DBMS/My%20files/Documents/VS_Code/project/house-price-prediction/db):
* [db/schema.sql](file:///c:/Users/haris/Documents/DBMS/My%20files/Documents/VS_Code/project/house-price-prediction/db/schema.sql) defines the tables (`users`, `bookings`, `messages`, `password_history`, `login_logs`, `app_settings`, `password_resets`).
* [db/crud.py](file:///c:/Users/haris/Documents/DBMS/My%20files/Documents/VS_Code/project/house-price-prediction/db/crud.py) implements the CRUD interface. For every table operation (e.g., `create_user`, `get_bookings`), it check if Supabase is configured:
  * **If Configured:** Communicates with the Supabase API client.
  * **Fallback:** Performs standard SQL operations on the local SQLite file (`users.db`).

---

## 4. Technology Stack: What is Used and Why

| Technology | Role | Why It Was Chosen |
| :--- | :--- | :--- |
| **Python** | Core Programming Language | High performance in statistical computing, machine learning, and rapid web application development. |
| **Flask** | Web Application Framework | Lightweight, modular Python framework. It avoids heavy boilerplate, making it easy to embed ML inference pipelines directly into page routes. |
| **Pandas & NumPy** | Data Manipulation | High-performance libraries to handle structural data loading (`.csv`), math computations, and matrix arrays. |
| **Scikit-learn** | Machine Learning | Provides pre-implemented estimators (Random Forest, Gradient Boosting), scaling functions (`StandardScaler`), and splitters (`train_test_split`). |
| **Supabase** | Cloud PostgreSQL Database | Provides a remote database environment with auto-generated APIs, real-time sync, and rapid setup without needing server provisioning. |
| **SQLite** | Fallback Local Database | Serverless relational database engine stored as a single file. Perfect for local prototyping, offline capability, and easy setup. |
| **Firebase Auth & Google OAuth** | Modern Sign-In Protocols | Simplifies user sign-in by leveraging existing Google identity assertions, enhancing system security and onboarding. |
| **Twilio API** | SMS Dispatcher | Reliable cloud service to programmatically dispatch automated text messages to mobile phone lines. |
| **Pickle** | Object Serialization | Allows trained model parameters to be written to a static file (`model.pkl`) and loaded by the Flask server instantly on boot. |

---

## 5. Directory Structure

Below is the file tree illustrating where different components reside:

```
house-price-prediction/
│
├── db/                       # Database Interface layer
│   ├── crud.py               # Auto-switching data access functions (Supabase <-> SQLite)
│   ├── models.py             # Data wrapper classes (e.g., RowProxy for dict compatibility)
│   ├── schema.sql            # Database schema for Supabase
│   └── supabase_client.py    # Client initialization and connection checks
│
├── static/                   # Static assets (CSS, JS, Uploaded user photos)
│
├── templates/                # HTML Jinja templates for web pages
│
├── .env.example              # Template containing variables for external integrations
├── app.py                    # Main Flask application file and endpoint controllers
├── train_model.py            # ML pipeline for training, comparing, and saving models
├── requirements.txt          # Python dependencies
├── merged_files.csv          # Real estate dataset
├── model.pkl                 # Serialized best-performing ML model
├── feature_cols.pkl          # List of features used during model training
├── FIREBASE_SETUP.md         # Instructions for configuring Google Sign-in with Firebase
├── SUPABASE_SETUP.md         # Instructions for database setup on Supabase Cloud
└── PROJECT_DETAILS.md        # Comprehensive project details (This document)
```

---

## 6. Setup and Execution

1. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
2. **Train Model:**
   ```bash
   python train_model.py
   ```
3. **Configure Database & Credentials:**
   Copy `.env.example` to `.env` and fill in API keys if using Supabase, Twilio, Firebase, or Google OAuth.
4. **Launch Application:**
   ```bash
   python app.py
   ```
   Open your browser to `http://127.0.0.1:5000`.
