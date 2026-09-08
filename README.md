# predictive-operations-control  (Ongoing)

Dataset - https://www.kaggle.com/datasets/nayanack/delhivery


Streamlit - https://delivery-route-intelligence.streamlit.app/

#  Delhivery Route Intelligence — Predictive Operations Control Tower

A predictive analytics system built on Delhivery's real logistics trip data that forecasts delivery time more accurately than the existing map-based (OSRM) estimate, flags high-risk corridors before they breach SLA, explains *why* in plain language via an AI assistant, and automates daily risk alerting.

> **Status:** Capstone project — core pipeline complete (Data → SQL → EDA → ML → AI → BI → Automation → Deployment).

---

##  Problem Statement

Delhivery estimates delivery times using OSRM (a map-based routing engine), but real-world factors — traffic, hub congestion, loading delays, route type — cause actual delivery time to diverge sharply from this estimate. This leads to:

- Unreliable customer-facing ETAs
- No visibility into *which* corridors/hubs are chronically unreliable
- A purely **reactive** process — problems surface only after SLA breach

**Objective:** predict delivery time more accurately than OSRM, proactively flag high-risk corridors, explain root causes in business language, and automate alerting — moving operations from reactive to proactive.

---

## 🗂️ Dataset

Real Delhivery trip data (public snapshot, ~22 days, September 2018):

- **144,867** segment-level records → aggregated to **14,787** unique trips
- Key fields: `trip_uuid`, `route_type` (FTL/Carting), `source_center`, `destination_center`, `actual_time`, `osrm_time`, `osrm_distance`, `actual_distance_to_destination`

*Limitation acknowledged: the dataset is a static historical snapshot, not a live feed — this shapes the automation design.*

---


---

## 📊 Project Phases

### Data Engineering
- Aggregated segment-level rows into one row per trip (`trip_uuid`), using appropriate logic per column (first/last for source/destination, sum for time/distance)
- Extracted `source_state`, `destination_state`, `source_city_code`, `destination_city_code` from embedded hub-name text
- Engineered 10 features: `osrm_error`, `delay_percentage`, `delay_flag`, `is_interstate`, `corridor_id`, `distance_category`, `route_efficiency`, `time_efficiency`, and time-based features (hour, day, weekend, quarter)
- Ran full data validation (negative values, duplicates, missing states/cities)
- Output: a full cleaned dataset (`trip_level_cleaned.csv`) + a leakage-free ML-ready dataset (`trip_level_ml_ready.csv`)

### SQL Data Warehouse (PostgreSQL)
- Star schema: `fact_trips` (measures) + `dim_center`, `dim_route_type`, `dim_date` (dimensions), connected via foreign keys
- 5 reusable SQL views: `corridor_performance`, `hub_performance`, `route_type_performance`, `interstate_performance`, `time_based_performance`
- Analytical SQL: window functions (`RANK`, `ROW_NUMBER`) and CTEs to identify top-risk corridors and hubs per state
- **Design principle:** business logic lives once in SQL views — a single source of truth consumed identically by Python, Power BI, and n8n

### Exploratory Data Analysis
Key findings:
| Insight | Detail |
|---|---|
| **96.2%** of trips | exceed the delay threshold vs. OSRM estimate |
| **Intrastate vs Interstate** | 156% vs 108% average delay — same-state trips are *more* delayed |
| **Distance vs Delay** | 0–100km trips: 180.8% avg delay → 600+km trips: 101% (inverse relationship) |
| **Time-of-day** | Early-morning trips (0–10 AM) show the highest delay % |

### Machine Learning
Three models, each solving a distinct business question:

| Model | Type | Result |
|---|---|---|
| **ETA Prediction** | Regression (Random Forest, benchmarked vs. XGBoost/Linear/Decision Tree) | MAE **328 min** vs OSRM baseline **2,008 min** → **84% error reduction** |
| **Delay Risk** | Classification (Random Forest, threshold-tuned) | Recall on minority "On-Time" class improved 48% → 70% (threshold 0.5 → 0.3) |
| **Corridor Risk Tiers** | Clustering (K-Means, K=3) | 121 corridors → 17 Critical / 101 Watch / 3 Stable |

**Validation:** an ablation test — training the ETA model *without* any OSRM-derived features — still beat the raw OSRM baseline by 70% (MAE 590.92 min), confirming the engineered features carry genuine predictive signal, not just a repetition of OSRM's own number.

### AI Operations Assistant
- Built on the **Groq API** (free tier, `openai/gpt-oss-120b`)
- **Retrieval-grounded, not free-form:** real corridor data is fetched from PostgreSQL first; the LLM only explains/summarizes that data — it cannot invent numbers
- Structured prompt design: **Role, Task, Constraints, Output Format, Few-Shot Example, Fallback**
- Output returned as strict JSON: `root_cause`, `recommended_action`, `business_impact`
- Tested across Critical / Watch / Stable tiers, with fallback handling for unknown corridors

### Power BI Dashboard
Two focused pages, connected live to the PostgreSQL warehouse:
- **Network Overview** — KPI cards, route-type split, top-10 worst corridors, distance/interstate/hour-of-day trends, state slicer
- **Corridor & Hub Intelligence** — ranked corridor/hub performance tables with risk tiers, model performance (our MAE vs. OSRM baseline)

### Automation (n8n)
```
Schedule Trigger → PostgreSQL Query (all corridors) → IF (avg_delay_pct > 150%)
→ Aggregate → Single consolidated alert email
```
- Business-logic threshold lives in the **IF node**, not the SQL query — a deliberate separation between data-retrieval and business rules
- *Honest limitation:* the dataset is a static historical snapshot, so automation is demonstrated on a manually-triggered batch rather than a live daily feed. The pipeline logic itself is production-ready and would work unchanged against a live database.

### Deployment (Streamlit)
- Guided route selection: pick a departure state → pick a real historical route (only routes with 3+ trips shown; same-city routes excluded to avoid inflated-distance artifacts)
- Live ETA prediction using the saved Random Forest model, with an adjustable OSRM-time slider
- One-click AI root-cause analysis tab with color-coded risk badges
- Speed-sanity check to warn against unrealistic input combinations

---

## 🛠️ Tech Stack

| Layer | Tools |
|---|---|
| Data Processing | Python, Pandas, NumPy |
| Database | PostgreSQL |
| Machine Learning | Scikit-learn, XGBoost |
| AI Assistant | Groq API |
| BI Dashboard | Power BI |
| Automation | n8n |
| Deployment | Streamlit |
| Version Control | Git / GitHub |

---

## 📁 Repository Structure

```
delhivery-route-intelligence/
├── data/
│   ├── raw/                        # original dataset (untouched)
│   └── processed/                  # cleaned, ML-ready, corridor risk tiers
├── notebooks/
│   ├── 01_data_cleaning.ipynb
│   ├── 02_sql_warehouse.ipynb
│   ├── 03_eda.ipynb
│   ├── 04_model_eta_prediction.ipynb
│   ├── 05_model_delay_risk.ipynb
│   ├── 06_model_corridor_clustering.ipynb
│   └── 07_ai_assistant.ipynb
├── sql/
│   └── delhivery_dw.sql            # schema, keys, views, analytical queries
├── models/                         # saved .pkl models & encoders
├── app/
│   ├── ai_assistant.py             # AI assistant module (Groq + prompt engineering)
│   └── streamlit_app.py            # deployed app
├── dashboard/
│   └── predictive_ops.pbix         # Power BI dashboard
├── .env                            # API keys (not committed)
├── .gitignore
└── README.md
```

---

## ⚙️ Setup & Run Locally

```bash
# 1. Clone the repo
git clone <repo-url>
cd delhivery-route-intelligence

# 2. Create virtual environment & install dependencies
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 3. Set up environment variables
# Create a .env file in the project root:
echo "GROQ_API_KEY=your_key_here" > .env

# 4. Set up PostgreSQL
# Create a database named delhivery_dw, then run:
psql -d delhivery_dw -f sql/delhivery_dw.sql

# 5. Run the Streamlit app
streamlit run app/streamlit_app.py
```

---

## 🎯 Key Results

- **84% reduction** in ETA prediction error vs. Delhivery's own OSRM baseline (Random Forest, MAE 328 min vs. 2,008 min)
- **70%** delay-risk recall on the minority On-Time class after threshold tuning (severe 96/4 class imbalance)
- **17 Critical-tier corridors** identified — carrying the highest average trip volume, making them the highest-priority, highest-impact targets for operational intervention
- A fully working, end-to-end pipeline from raw data to a deployed, AI-explained, automatically-alerting application

---

## 🔭 Future Improvements

- Replace historical-average distance lookups with live routing API calls for city pairs with sparse data
- Expand automation to connect to a live operations database instead of a static snapshot
- Add SHAP-based feature attribution to make the AI assistant's explanations even more directly tied to model internals
- Extend the corridor clustering to incorporate weather and holiday-calendar data if/when available

---

## 👤 Author

Harshith Raj Purohit
