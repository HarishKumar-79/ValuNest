"""
HomeFinder — Advanced ML Model Training Pipeline
Compares Random Forest, XGBoost, LightGBM, CatBoost, and Gradient Boosting.
Selects the best model by R² score and saves it for production use.
"""

import os
import json
import pickle
import warnings
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split, RandomizedSearchCV
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error

warnings.filterwarnings("ignore")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "merged_files.csv")


def load_and_prepare_data():
    """Load dataset, handle missing values, engineer features."""
    print("=" * 60)
    print("HOMEFINDER — ML MODEL TRAINING PIPELINE")
    print("=" * 60)

    df = pd.read_csv(CSV_PATH)
    print(f"\n📊 Dataset: {df.shape[0]} rows × {df.shape[1]} columns")

    # Drop rows with missing target
    df = df.dropna(subset=["Price"])

    # Remove extreme outliers (top/bottom 1%)
    q_low = df["Price"].quantile(0.01)
    q_high = df["Price"].quantile(0.99)
    df = df[(df["Price"] >= q_low) & (df["Price"] <= q_high)]
    print(f"   After outlier removal: {df.shape[0]} rows")

    # Separate features and target
    target = df["Price"].copy()

    # All numeric amenity columns (binary 0/1)
    amenity_cols = [
        "Resale", "MaintenanceStaff", "Gymnasium", "SwimmingPool",
        "LandscapedGardens", "JoggingTrack", "RainWaterHarvesting",
        "IndoorGames", "ShoppingMall", "Intercom", "SportsFacility",
        "ATM", "ClubHouse", "School", "24X7Security", "PowerBackup",
        "CarParking", "StaffQuarter", "Cafeteria", "MultipurposeRoom",
        "Hospital", "WashingMachine", "Gasconnection", "AC", "Wifi",
        "Children'splayarea", "LiftAvailable", "BED", "VaastuCompliant",
        "Microwave", "GolfCourse", "TV", "DiningTable", "Sofa",
        "Wardrobe", "Refrigerator",
    ]

    numeric_cols = ["Area", "No. of Bedrooms"]

    # Fill missing values
    for col in amenity_cols:
        if col in df.columns:
            df[col] = df[col].fillna(0).astype(int)
    for col in numeric_cols:
        if col in df.columns:
            df[col] = df[col].fillna(df[col].median())

    # Feature engineering: total amenity score
    available_amenities = [c for c in amenity_cols if c in df.columns]
    df["AmenityScore"] = df[available_amenities].sum(axis=1)

    # Price per sqft (derived feature)
    df["PricePerSqft_area"] = df["Area"].apply(lambda x: max(x, 1))  # avoid div by 0

    # Encode City as dummies
    df = pd.get_dummies(df, columns=["City"], drop_first=True)
    city_cols = [c for c in df.columns if c.startswith("City_")]

    # Final feature list
    feature_cols = numeric_cols + available_amenities + ["AmenityScore"] + city_cols

    # Drop Location (too many categories, not useful for regression)
    features = df[feature_cols].copy()

    print(f"   Features: {len(feature_cols)} columns")
    print(f"   Target range: ₹{target.min():,.0f} — ₹{target.max():,.0f}")

    return features, target, feature_cols


def train_and_compare(X_train, X_test, y_train, y_test):
    """Train multiple models and compare performance."""
    print("\n" + "=" * 60)
    print("TRAINING & COMPARING MODELS")
    print("=" * 60)

    # Scale features
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    models = {}
    results = {}

    # 1. Random Forest
    print("\n🌲 Training Random Forest...")
    rf = RandomForestRegressor(
        n_estimators=200, max_depth=20, min_samples_split=5,
        min_samples_leaf=2, n_jobs=-1, random_state=42
    )
    rf.fit(X_train, y_train)
    models["Random Forest"] = (rf, False)  # (model, needs_scaling)
    results["Random Forest"] = evaluate_model(rf, X_test, y_test)

    # 2. Gradient Boosting
    print("📈 Training Gradient Boosting...")
    gb = GradientBoostingRegressor(
        n_estimators=200, max_depth=6, learning_rate=0.1,
        min_samples_split=5, min_samples_leaf=3, random_state=42
    )
    gb.fit(X_train, y_train)
    models["Gradient Boosting"] = (gb, False)
    results["Gradient Boosting"] = evaluate_model(gb, X_test, y_test)

    # 3. XGBoost
    try:
        from xgboost import XGBRegressor
        print("🚀 Training XGBoost...")
        xgb = XGBRegressor(
            n_estimators=300, max_depth=8, learning_rate=0.08,
            subsample=0.8, colsample_bytree=0.8,
            reg_alpha=0.1, reg_lambda=1.0,
            n_jobs=-1, random_state=42, verbosity=0
        )
        xgb.fit(X_train, y_train)
        models["XGBoost"] = (xgb, False)
        results["XGBoost"] = evaluate_model(xgb, X_test, y_test)
    except ImportError:
        print("   ⚠ XGBoost not installed, skipping.")

    # 4. LightGBM
    try:
        from lightgbm import LGBMRegressor
        print("💡 Training LightGBM...")
        lgb = LGBMRegressor(
            n_estimators=300, max_depth=8, learning_rate=0.08,
            num_leaves=63, subsample=0.8, colsample_bytree=0.8,
            reg_alpha=0.1, reg_lambda=1.0,
            n_jobs=-1, random_state=42, verbose=-1
        )
        lgb.fit(X_train, y_train)
        models["LightGBM"] = (lgb, False)
        results["LightGBM"] = evaluate_model(lgb, X_test, y_test)
    except ImportError:
        print("   ⚠ LightGBM not installed, skipping.")

    # 5. CatBoost
    try:
        from catboost import CatBoostRegressor
        print("🐱 Training CatBoost...")
        cb = CatBoostRegressor(
            iterations=300, depth=8, learning_rate=0.08,
            l2_leaf_reg=3, random_seed=42, verbose=0
        )
        cb.fit(X_train, y_train)
        models["CatBoost"] = (cb, False)
        results["CatBoost"] = evaluate_model(cb, X_test, y_test)
    except ImportError:
        print("   ⚠ CatBoost not installed, skipping.")

    return models, results, scaler


def evaluate_model(model, X_test, y_test):
    """Compute MAE, RMSE, R² for a model."""
    preds = model.predict(X_test)
    mae = mean_absolute_error(y_test, preds)
    rmse = np.sqrt(mean_squared_error(y_test, preds))
    r2 = r2_score(y_test, preds)
    return {"MAE": round(mae, 2), "RMSE": round(rmse, 2), "R2": round(r2, 4)}


def print_results(results):
    """Display comparison table."""
    print("\n" + "=" * 60)
    print("MODEL COMPARISON RESULTS")
    print("=" * 60)
    print(f"{'Model':<22} {'R²':>8} {'MAE':>15} {'RMSE':>15}")
    print("-" * 60)
    for name, metrics in sorted(results.items(), key=lambda x: x[1]["R2"], reverse=True):
        print(f"{name:<22} {metrics['R2']:>8.4f} ₹{metrics['MAE']:>13,.0f} ₹{metrics['RMSE']:>13,.0f}")


def save_best_model(models, results, scaler, feature_cols):
    """Save the best model, scaler, feature list, and metrics."""
    best_name = max(results, key=lambda k: results[k]["R2"])
    best_model, needs_scaling = models[best_name]
    best_metrics = results[best_name]

    print(f"\n🏆 BEST MODEL: {best_name}")
    print(f"   R² = {best_metrics['R2']:.4f}")
    print(f"   MAE = ₹{best_metrics['MAE']:,.0f}")
    print(f"   RMSE = ₹{best_metrics['RMSE']:,.0f}")

    # Save model
    with open(os.path.join(BASE_DIR, "model.pkl"), "wb") as f:
        pickle.dump(best_model, f)

    # Save feature columns
    with open(os.path.join(BASE_DIR, "feature_cols.pkl"), "wb") as f:
        pickle.dump(feature_cols, f)

    # Save scaler
    with open(os.path.join(BASE_DIR, "scaler.pkl"), "wb") as f:
        pickle.dump(scaler, f)

    # Save metrics JSON (for display in the app)
    metrics_data = {
        "best_model": best_name,
        "metrics": best_metrics,
        "all_results": results,
        "feature_count": len(feature_cols),
    }
    with open(os.path.join(BASE_DIR, "model_metrics.json"), "w") as f:
        json.dump(metrics_data, f, indent=2)

    print(f"\n✅ Saved: model.pkl, feature_cols.pkl, scaler.pkl, model_metrics.json")
    return best_name, best_metrics


if __name__ == "__main__":
    # Load data
    features, target, feature_cols = load_and_prepare_data()

    # Split
    X_train, X_test, y_train, y_test = train_test_split(
        features, target, test_size=0.2, random_state=42
    )
    print(f"\n   Train: {X_train.shape[0]} rows | Test: {X_test.shape[0]} rows")

    # Train and compare
    models, results, scaler = train_and_compare(X_train, X_test, y_train, y_test)

    # Display results
    print_results(results)

    # Save best
    save_best_model(models, results, scaler, feature_cols)

    print("\n" + "=" * 60)
    print("TRAINING COMPLETE")
    print("=" * 60)