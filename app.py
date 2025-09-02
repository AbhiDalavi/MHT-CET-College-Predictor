from flask import Flask, render_template, request
import pandas as pd

app = Flask(__name__)

# --- Load the Final Dataset ---
try:
    df = pd.read_csv('college_data.csv')
    df['Percentile'] = pd.to_numeric(df['Percentile'], errors='coerce')
    df.dropna(subset=['Percentile', 'Course'], inplace=True)
except FileNotFoundError:
    print("FATAL ERROR: college_data.csv not found!")
    exit()
except KeyError as e:
    print(f"FATAL ERROR: A column is missing from your CSV file: {e}")
    exit()

@app.route('/')
def index():
    categories = sorted(df['Category'].unique())
    branches = sorted(df['Course'].unique())
    return render_template('index.html', categories=categories, branches=branches)

@app.route('/predict', methods=['POST'])
def predict():
    user_percentile = float(request.form['percentile'])
    user_category = request.form['category']
    user_branch = request.form['branch']

    filtered_df = df[
        (df['Course'] == user_branch) &
        (df['Category'] == user_category)
    ]

    result_df = filtered_df[
        (filtered_df['Percentile'] >= user_percentile - 5) &
        (filtered_df['Percentile'] <= user_percentile + 5)
    ].copy()

    if not result_df.empty:
        result_df['Difference'] = (result_df['Percentile'] - user_percentile).abs()
        result_df = result_df.sort_values(by='Difference')

    results_list = result_df.to_dict('records')
    return render_template('results.html', results=results_list)

if __name__ == '__main__':
    app.run(debug=True)