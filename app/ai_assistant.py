"""
AI Operations Assistant Module
Provides natural-language, root-cause explanations for corridor delay risk,
grounded in real operational data (no hallucinated numbers).
"""

import os
import json
import pandas as pd
from dotenv import load_dotenv
from groq import Groq

# Load environment variables (works regardless of where this is called from,
# as long as .env is at the project root)
load_dotenv()
api_key = os.getenv("GROQ_API_KEY")
client = Groq(api_key=api_key)

# Load data once when the module is imported (not on every function call)
corridor_stats = pd.read_csv('data/processed/corridor_risk_tiers.csv')
trip_df = pd.read_csv('data/processed/trip_level_cleaned.csv')


def get_corridor_context(corridor_id):
    """Builds a factual, real-data summary of a corridor's performance."""
    row = corridor_stats[corridor_stats['corridor_id'] == corridor_id]

    if row.empty:
        return f"No data found for corridor: {corridor_id}"

    row = row.iloc[0]
    corridor_trips = trip_df[trip_df['corridor_id'] == corridor_id]
    route_breakdown = corridor_trips.groupby('route_type')['delay_percentage'].mean().round(2).to_dict()

    context = f"""
Corridor: {corridor_id}
Risk Tier: {row['risk_tier']}
Total Trips: {row['total_trips']}
Average Delay %: {row['avg_delay_pct']:.2f}%
Delay Rate (% of trips delayed): {row['delay_rate']*100:.2f}%
Route Type Breakdown (avg delay % by type): {route_breakdown}
"""
    return context


def build_system_prompt():
    """Structured prompt: Role, Task, Constraints, Output Format, Few-Shot, Fallback."""
    return """
### ROLE ###
You are a senior logistics operations analyst working for Delhivery, India's largest logistics company. You specialize in explaining delivery delay risks to non-technical operations managers in clear business language.

### TASK ###
Given real operational data about a specific delivery corridor, explain why it is classified as high-risk (or otherwise), and provide one clear, actionable recommendation the operations team can act on immediately.

### CONSTRAINTS ###
- Use ONLY the data provided in the user message. Never invent numbers, percentages, or facts not explicitly given.
- Do not mention weather, traffic accidents, or any external cause unless it is present in the given data.
- Do not use technical ML/statistics jargon.
- Each field must be a single, concise sentence or two. No markdown formatting inside the JSON values.
- Respond with VALID JSON ONLY. No text before or after. No markdown code fences.

### OUTPUT FORMAT ###
{
  "corridor_id": "<the corridor id>",
  "risk_tier": "<the risk tier from the data>",
  "root_cause": "<why this corridor has this risk level, based only on given numbers>",
  "recommended_action": "<one specific, practical action>",
  "business_impact": "<what happens if not addressed>"
}

### FEW-SHOT EXAMPLE ###
Example Input Data:
Corridor: Delhi_Haryana
Risk Tier: Watch
Total Trips: 396
Average Delay %: 129.19%
Delay Rate: 93.69%
Route Type Breakdown: {'Carting': 145.30, 'FTL': 98.20}

Example Output:
{
  "corridor_id": "Delhi_Haryana",
  "risk_tier": "Watch",
  "root_cause": "This corridor shows a moderate but consistent delay pattern, with Carting trips at 145% average delay performing notably worse than FTL trips at 98%, suggesting local handling is the main contributor.",
  "recommended_action": "Review hub loading and dispatch procedures specifically for Carting-mode shipments on this route, since FTL trips on the same corridor perform significantly better.",
  "business_impact": "If unaddressed, this corridor risks escalating from Watch to Critical tier as delay rates are already above 90%."
}

### FALLBACK ###
If the corridor data provided says "No data found" or is missing key fields, respond with this exact JSON:
{
  "corridor_id": "unknown",
  "risk_tier": "unknown",
  "root_cause": "Insufficient data available for this corridor.",
  "recommended_action": "Verify the corridor ID or check if it meets the minimum trip volume threshold.",
  "business_impact": "Cannot be assessed without sufficient data."
}
"""


def ask_ai_assistant(corridor_id, user_question=None):
    """
    Main function: given a corridor ID, returns a structured dict with
    root cause, recommended action, and business impact.
    This is the function Streamlit (Phase 8) will import and call directly.
    """
    context = get_corridor_context(corridor_id)

    if user_question is None:
        user_question = f"Explain the risk for corridor: {corridor_id}"

    user_prompt = f"""
Here is the real operational data for this corridor:

{context}

Question: {user_question}
"""

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.3,
        response_format={"type": "json_object"}
    )

    raw_output = response.choices[0].message.content

    try:
        result = json.loads(raw_output)
    except json.JSONDecodeError:
        result = {"error": "Failed to parse AI response as JSON", "raw": raw_output}

    return result