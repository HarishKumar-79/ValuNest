import os
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score, mean_absolute_error
import pickle

base_dir = os.path.dirname(os.path.abspath(__file__))
data = pd.read_csv(os.path.join(base_dir, "merged_files.csv"))

# Encode City as dummy variables so the model understands location
data = pd.get_dummies(data, columns=['City'], drop_first=True)

# Features including city dummies and amenities
city_cols = [c for c in data.columns if c.startswith('City_')]
features = data[['Area', 'No. of Bedrooms', 'Resale', 'CarParking', 'LiftAvailable',
                  'Gymnasium', 'SwimmingPool', '24X7Security', 'PowerBackup', 'ClubHouse'] + city_cols]
target = data['Price']

X_train, X_test, y_train, y_test = train_test_split(
    features, target, test_size=0.2, random_state=42
)

model = LinearRegression()
model.fit(X_train, y_train)

preds = model.predict(X_test)
print(f"R2 score : {r2_score(y_test, preds):.2f}")
print(f"MAE      : Rs.{mean_absolute_error(y_test, preds):,.0f}")

# Save model AND feature column list (app.py needs this)
pickle.dump(model, open(os.path.join(base_dir, "model.pkl"), "wb"))
pickle.dump(list(features.columns), open(os.path.join(base_dir, "feature_cols.pkl"), "wb"))
print("Model trained and saved!")