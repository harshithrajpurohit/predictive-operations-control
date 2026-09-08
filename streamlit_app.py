import streamlit as st
import pandas as pd
import joblib
import sys
import json

sys.path.append('.')
from app.ai_assistant import client, build_system_prompt

st.set_page_config(page_title="Delhivery Route Intelligence", layout="wide")

# =========================================================
# CUSTOM STYLING
# =========================================================
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 800;
        background: linear-gradient(90deg, #1C7293, #F2994A);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0;
    }
    .sub-header {
        color: #9FB8E0;
        font-size: 1.1rem;
        margin-top: 0;
    }
    .metric-card {
        background: linear-gradient(135deg, #1C2536, #2A3550);
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #3C477F;
        text-align: center;
    }
    .risk-critical {
        background-color: #E74C3C;
        color: white;
        padding: 6px 16px;
        border-radius: 20px;
        font-weight: 700;
        display: inline-block;
    }
    .risk-watch {
        background-color: #F2994A;
        color: white;
        padding: 6px 16px;
        border-radius: 20px;
        font-weight: 700;
        display: inline-block;
    }
    .risk-stable {
        background-color: #1C7293;
        color: white;
        padding: 6px 16px;
        border-radius: 20px;
        font-weight: 700;
        display: inline-block;
    }
    .ai-box {
        background-color: #1A2332;
        border-left: 4px solid #F2994A;
        padding: 16px 20px;
        border-radius: 8px;
        margin-bottom: 12px;
    }
</style>
""", unsafe_allow_html=True)

# =========================================================
# LOAD DATA & MODELS
# =========================================================
@st.cache_resource
def load_models():
    eta_model = joblib.load('models/eta_prediction_model.pkl')
    label_encoders = joblib.load('models/label_encoders_eta.pkl')
    return eta_model, label_encoders

@st.cache_data
def load_reference_data():
    corridor_stats = pd.read_csv('data/processed/corridor_risk_tiers.csv')
    trip_df = pd.read_csv('data/processed/trip_level_cleaned.csv')
    return corridor_stats, trip_df

eta_model, label_encoders = load_models()
corridor_stats, trip_df = load_reference_data()

@st.cache_data
def build_route_options():
    """Build a list of real source-center -> destination-center pairs that exist in the dataset,
    with enough volume to be statistically meaningful, along with their historical averages."""
    route_summary = trip_df.groupby(
        ['source_state', 'source_city_code', 'destination_state', 'destination_city_code', 'route_type']
    ).agg(
        trip_count=('trip_uuid', 'count'),
        avg_distance=('actual_distance_to_destination', 'mean'),
        avg_osrm_time=('osrm_time', 'mean'),
        avg_delay_pct=('delay_percentage', 'mean')
    ).reset_index()

    route_summary = route_summary[route_summary['trip_count'] >= 3]

    # Exclude same-city routes - these represent intra-hub movement, not meaningful
    # source-to-destination trips, and can show inflated distances due to multi-stop paths
    route_summary = route_summary[
        route_summary['source_city_code'] != route_summary['destination_city_code']
    ]

    route_summary = route_summary.sort_values('trip_count', ascending=False)

    route_summary['label'] = (
        route_summary['source_city_code'] + " (" + route_summary['source_state'] + ")  →  " +
        route_summary['destination_city_code'] + " (" + route_summary['destination_state'] + ")  |  " +
        route_summary['route_type'] + "  ·  " + route_summary['trip_count'].astype(str) + " trips"
    )
    return route_summary

route_options = build_route_options()

# =========================================================
# HEADER
# =========================================================
st.markdown('<p class="main-header">🚚 Delhivery Route Intelligence</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Predictive Operations Control Tower — ETA Prediction & AI Risk Analysis</p>', unsafe_allow_html=True)

col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
with col_kpi1:
    st.markdown(f'<div class="metric-card"><h3>📦 {len(route_options)}</h3><p>Known Routes</p></div>', unsafe_allow_html=True)
with col_kpi2:
    st.markdown(f'<div class="metric-card"><h3>📍 {len(corridor_stats)}</h3><p>Corridors Tracked</p></div>', unsafe_allow_html=True)
with col_kpi3:
    critical_count = len(corridor_stats[corridor_stats['risk_tier'] == 'Critical'])
    st.markdown(f'<div class="metric-card"><h3>🔴 {critical_count}</h3><p>Critical Corridors</p></div>', unsafe_allow_html=True)

st.write("")
st.divider()

# =========================================================
# ROUTE SELECTION (Step 1: State -> Step 2: Filtered Routes)
# =========================================================
st.header("🔍 Select a Route to Analyze")

col_step1, col_step2 = st.columns([1, 2])

with col_step1:
    available_source_states = sorted(route_options['source_state'].unique())
    selected_source_state = st.selectbox(
        "Departure State",
        available_source_states
    )

# Filter routes to only those departing from the selected state
filtered_routes = route_options[route_options['source_state'] == selected_source_state]

with col_step2:
    selected_label = st.selectbox(
        f"Routes from {selected_source_state} ({len(filtered_routes)} available)",
        filtered_routes['label'].tolist()
    )

selected_row = filtered_routes[filtered_routes['label'] == selected_label].iloc[0]

source_state = selected_row['source_state']
source_city = selected_row['source_city_code']
destination_state = selected_row['destination_state']
destination_city = selected_row['destination_city_code']
route_type = selected_row['route_type']
distance_km = selected_row['avg_distance']
avg_osrm_time = selected_row['avg_osrm_time']

osrm_time_input = st.slider(
    "Adjust OSRM Estimated Time (minutes) — defaults to historical average",
    min_value=max(1.0, avg_osrm_time * 0.6),
    max_value=avg_osrm_time * 1.4,
    value=float(avg_osrm_time),
    step=5.0
)

# ---------- IMPLIED SPEED SANITY CHECK ----------
implied_speed = (distance_km / (osrm_time_input / 60)) if osrm_time_input > 0 else 0
if implied_speed < 5 or implied_speed > 100:
    st.warning(f"⚠️ This implies an average speed of {implied_speed:.0f} km/hr, which is unusual for this route. Prediction may be less reliable.")

analyze_clicked = st.button("🚀 Analyze This Route", type="primary", use_container_width=True)

# =========================================================
# RESULTS
# =========================================================
if analyze_clicked:

    tab1, tab2 = st.tabs(["📊 ETA Prediction", "🤖 AI Root-Cause Analysis"])

    # ---------- ML PREDICTION ----------
    input_data = pd.DataFrame({
        'osrm_time': [osrm_time_input],
        'osrm_distance': [distance_km],
        'segment_osrm_time': [osrm_time_input],
        'segment_osrm_distance': [distance_km],
        'source_state': [source_state],
        'destination_state': [destination_state],
        'source_city_code': [source_city],
        'destination_city_code': [destination_city],
        'is_interstate': [1 if source_state != destination_state else 0],
        'corridor_id': [f"{source_state}_{destination_state}"],
        'creation_year': [2018],
        'creation_month': [9],
        'creation_day': [15],
        'is_weekend': [0],
        'creation_hour': [10],
        'creation_quarter': [3],
    })

    high_card_cols = ['source_state', 'destination_state', 'source_city_code',
                       'destination_city_code', 'corridor_id']
    for col in high_card_cols:
        le = label_encoders[col]
        input_data[col] = input_data[col].apply(
            lambda x: le.transform([x])[0] if x in le.classes_ else -1
        )

    for rt in ['FTL', 'Carting']:
        input_data[f'route_type_{rt}'] = 1 if route_type == rt else 0

    if distance_km <= 100:
        cat = '0-100km'
    elif distance_km <= 300:
        cat = '100-300km'
    elif distance_km <= 600:
        cat = '300-600km'
    else:
        cat = '600+km'
    for dc in ['0-100km', '100-300km', '300-600km', '600+km']:
        input_data[f'distance_category_{dc}'] = 1 if cat == dc else 0

    for day in ['Monday', 'Saturday', 'Sunday', 'Thursday', 'Tuesday', 'Wednesday']:
        input_data[f'creation_day_name_{day}'] = 1 if day == 'Wednesday' else 0

    model_columns = eta_model.feature_names_in_
    for col in model_columns:
        if col not in input_data.columns:
            input_data[col] = 0
    input_data = input_data[model_columns]

    predicted_time = eta_model.predict(input_data)[0]

    with tab1:
        st.subheader(f"{source_city} → {destination_city}")
        st.caption(f"Route Type: {route_type}  ·  Distance: {distance_km:.0f} km")

        c1, c2, c3 = st.columns(3)
        c1.metric("🎯 Predicted Delivery Time", f"{predicted_time:.0f} min")
        c2.metric("🗺️ OSRM Estimate", f"{osrm_time_input:.0f} min")
        c3.metric("📈 Difference", f"{predicted_time - osrm_time_input:+.0f} min",
                   delta=f"{((predicted_time - osrm_time_input) / osrm_time_input * 100):.0f}%")

   

    # ---------- AI ANALYSIS ----------
    with tab2:
        corridor_id = f"{source_state}_{destination_state}"
        row = corridor_stats[corridor_stats['corridor_id'] == corridor_id]

        with st.spinner("🧠 AI analyzing route data..."):
            if row.empty:
                context = f"No corridor-level data found for: {corridor_id}"
                risk_tier_display = "Unknown"
            else:
                row = row.iloc[0]
                risk_tier_display = row['risk_tier']
                corridor_trips = trip_df[trip_df['corridor_id'] == corridor_id]
                route_breakdown = corridor_trips.groupby('route_type')['delay_percentage'].mean().round(2).to_dict()

                context = f"""
Corridor: {corridor_id}
Source Center: {source_city}, Destination Center: {destination_city}
Risk Tier: {row['risk_tier']}
Total Trips: {row['total_trips']}
Average Delay %: {row['avg_delay_pct']:.2f}%
Delay Rate: {row['delay_rate']*100:.2f}%
Route Type Breakdown (avg delay % by type): {route_breakdown}
This specific trip: OSRM Estimate = {osrm_time_input:.0f} min, Model Predicted Actual Time = {predicted_time:.0f} min
"""

            user_prompt = f"""Here is the real operational data for this corridor:
{context}

Question: Why is the route from {source_city} to {destination_city} classified this way, and what should be done about it?"""

            response = client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[
                    {"role": "system", "content": build_system_prompt()},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                response_format={"type": "json_object"}
            )
            result = json.loads(response.choices[0].message.content)

        badge_class = {"Critical": "risk-critical", "Watch": "risk-watch", "Stable": "risk-stable"}.get(risk_tier_display, "risk-watch")
        st.markdown(f'<span class="{badge_class}">{risk_tier_display.upper()} RISK</span>', unsafe_allow_html=True)
        st.write("")

        st.markdown(f'<div class="ai-box">🔴 <b>Root Cause</b><br>{result.get("root_cause")}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="ai-box">✅ <b>Recommended Action</b><br>{result.get("recommended_action")}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="ai-box">⚠️ <b>Business Impact</b><br>{result.get("business_impact")}</div>', unsafe_allow_html=True)