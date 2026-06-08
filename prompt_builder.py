"""
prompt_builder.py

Builds the structured prompt sent to the vision LLM.
The goal: give the model enough physical context (utensil dimensions,
fill level) so it can estimate portion weight — the hardest part of
calorie estimation from a photo.
"""

# ── Few-shot examples ─────────────────────────────────────────────────────────
# These are reference text examples injected into the prompt.
# Later you'll replace these with real images from your dataset.
# Format: dish → typical values when served in a standard katori (250ml).

FEW_SHOT_EXAMPLES = """
REFERENCE EXAMPLES (typical Indian home servings):

1. Dal Tadka in a katori (250ml, ~85% full):
   Weight: ~200g | Calories: ~180 kcal
   Ingredients: toor dal 80g (88 kcal), ghee 10g (90 kcal), onion 15g (6 kcal), tomato 20g (4 kcal), spices 5g (8 kcal)

2. Rajma in a katori (250ml, ~90% full):
   Weight: ~220g | Calories: ~260 kcal
   Ingredients: kidney beans 100g (127 kcal), oil 12g (106 kcal), onion 20g (8 kcal), tomato 25g (5 kcal), spices 8g (14 kcal)

3. Plain rice on a plate (28cm diameter):
   Weight: ~200g cooked | Calories: ~260 kcal
   Ingredients: cooked rice 200g (260 kcal)

4. Paneer Butter Masala in a bowl (300ml, ~80% full):
   Weight: ~240g | Calories: ~360 kcal
   Ingredients: paneer 80g (212 kcal), butter/oil 15g (111 kcal), tomato gravy 120g (48 kcal), cream 15g (52 kcal), spices 10g (18 kcal)

5. Chapati (single, medium):
   Weight: ~40g | Calories: ~120 kcal
   Ingredients: wheat flour 35g (114 kcal), ghee 1g (9 kcal)

6. Chicken Curry in a katori (250ml, ~85% full):
   Weight: ~200g | Calories: ~280 kcal
   Ingredients: chicken 100g (165 kcal), oil 15g (135 kcal), onion 20g (8 kcal), tomato 20g (4 kcal), spices 10g (18 kcal)

NOTE: For dry dishes (sabzi, stir fry) density is ~0.7–0.8 g/ml.
For wet curries and dals, density is ~0.95–1.0 g/ml.
"""


def build_utensil_context(utensil: dict | None, fill_level: float) -> str:
    """
    Converts a utensil profile dict into a human-readable context string.
    fill_level: 0.0 to 1.0 (e.g. 0.75 = 75% full)
    """
    if utensil is None:
        return (
            "No utensil profile provided. "
            "Estimate portion size from visual cues alone."
        )

    fill_pct = round(fill_level * 100)
    effective_volume = round((utensil.get("volume_ml") or 0) * fill_level, 1)

    lines = [
        f"UTENSIL: {utensil['name']} ({utensil['type']})",
    ]
    if utensil.get("diameter_cm"):
        lines.append(f"  Diameter: {utensil['diameter_cm']} cm")
    if utensil.get("depth_cm"):
        lines.append(f"  Depth: {utensil['depth_cm']} cm")
    if utensil.get("volume_ml"):
        lines.append(f"  Full capacity: {utensil['volume_ml']} ml")
    lines.append(f"  Current fill level: ~{fill_pct}% full")
    if effective_volume:
        lines.append(f"  Estimated food volume: ~{effective_volume} ml")
    if utensil.get("notes"):
        lines.append(f"  Notes: {utensil['notes']}")

    return "\n".join(lines)


def build_calorie_prompt(utensil: dict | None, fill_level: float) -> str:
    """
    Builds the complete system + user prompt for calorie estimation.
    The image is attached separately as base64 in the API call.
    """
    utensil_ctx = build_utensil_context(utensil, fill_level)

    prompt = f"""You are a nutrition expert specializing in Indian home cooking and the Indian Food Composition Tables (IFCT 2017).

Your task: analyze the food photo and return an accurate calorie estimate.

{utensil_ctx}

{FEW_SHOT_EXAMPLES}

INSTRUCTIONS:
1. Identify the dish(es) in the image.
2. Use the utensil dimensions and fill level above to estimate the total food weight in grams.
   - For wet dishes (dal, curry, sambar): density ≈ 0.95–1.0 g/ml
   - For dry dishes (sabzi, rice, roti): density ≈ 0.65–0.85 g/ml
3. Break down into major ingredients with gram estimates.
4. Calculate calories using IFCT 2017 values.
5. Pay special attention to hidden fats: ghee, oil, butter. Indian home cooking typically uses 10–20g fat per serving.

IMPORTANT RULES:
- If you see chapati/roti, count the number of pieces.
- If multiple dishes are visible, analyze each separately.
- Be conservative with rice — cooked rice is ~1.3x the dry weight.
- If the dish is unclear, state your best guess and note the uncertainty.

Return your response as valid JSON only, no extra text before or after:

{{
  "dishes": [
    {{
      "dish_name": "string",
      "confidence": "high|medium|low",
      "weight_g": number,
      "ingredients": [
        {{
          "name": "string",
          "grams": number,
          "kcal": number
        }}
      ],
      "subtotal_kcal": number,
      "notes": "string (optional)"
    }}
  ],
  "total_kcal": number,
  "estimation_method": "string (brief note on how you estimated the portion)"
}}"""

    return prompt


def parse_llm_response(raw_text: str) -> dict:
    """
    Safely parses the JSON response from the LLM.
    Handles cases where the model wraps JSON in markdown code fences.
    """
    import json
    import re

    text = raw_text.strip()

    # Strip markdown code fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        # Try to extract the first JSON object from the text
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        raise ValueError(f"Could not parse LLM response as JSON: {e}\n\nRaw: {raw_text[:300]}")