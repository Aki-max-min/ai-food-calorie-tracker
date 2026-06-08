"""
app_frontend.py

Streamlit frontend for Indian Food Calorie Tracker.
Modern, mobile-responsive UI with Red/Orange/Yellow/White palette.

Color scheme:
- Primary Red: #DC2626
- Secondary Orange: #EA580C
- Accent Yellow: #FBBF24
- Background White: #FFFFFF
- Text Dark: #1F2937
"""

import streamlit as st
import requests
import json
from datetime import datetime
from PIL import Image
import io

# ── Page Config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Food Calorie Tracker",
    page_icon="🍛",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Styling ───────────────────────────────────────────────────────────────────

st.markdown("""
<style>
    * {
        color: #1F2937;
    }
    
    .main {
        background-color: #FFFFFF;
    }
    
    /* Header */
    .stMarkdown h1 {
        color: #DC2626;
        font-size: 2.5rem;
        font-weight: 800;
        margin-bottom: 0.5rem;
    }
    
    .stMarkdown h2 {
        color: #EA580C;
        font-size: 1.8rem;
        font-weight: 700;
        margin-top: 1.5rem;
    }
    
    .stMarkdown h3 {
        color: #DC2626;
        font-size: 1.3rem;
    }
    
    /* Buttons */
    .stButton > button {
        background-color: #DC2626;
        color: white;
        font-weight: 600;
        padding: 0.75rem 2rem;
        border-radius: 0.5rem;
        border: none;
        width: 100%;
        transition: all 0.3s ease;
    }
    
    .stButton > button:hover {
        background-color: #B91C1C;
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(220, 38, 38, 0.3);
    }
    
    /* Cards */
    .metric-card {
        background: linear-gradient(135deg, #FEF2F2 0%, #FEF9E7 100%);
        border-left: 4px solid #DC2626;
        padding: 1.5rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
    
    .dish-card {
        background-color: #FFFBEB;
        border: 2px solid #FBBF24;
        border-radius: 0.5rem;
        padding: 1.5rem;
        margin: 1rem 0;
    }
    
    .ingredient-row {
        background-color: #F3F4F6;
        padding: 0.75rem;
        margin: 0.5rem 0;
        border-radius: 0.25rem;
        display: flex;
        justify-content: space-between;
        font-size: 0.95rem;
    }
    
    /* Input fields */
    .stNumberInput, .stSelectbox, .stFileUploader {
        margin: 1rem 0;
    }
    
    /* Progress bar */
    .stProgress > div > div {
        background-color: #EA580C;
    }
    
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] button {
        color: #666;
        font-weight: 600;
    }
    
    .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] {
        color: #DC2626;
        border-bottom: 3px solid #DC2626;
    }
    
    /* Success/Warning/Error */
    .stSuccess {
        background-color: #F0FDF4 !important;
        color: #15803D !important;
    }
    
    .stWarning {
        background-color: #FFFBEB !important;
        color: #B45309 !important;
    }
    
    .stError {
        background-color: #FEF2F2 !important;
        color: #DC2626 !important;
    }
    
    /* Responsive */
    @media (max-width: 768px) {
        .stMarkdown h1 {
            font-size: 1.8rem;
        }
        .stMarkdown h2 {
            font-size: 1.3rem;
        }
    }
</style>
""", unsafe_allow_html=True)

# ── Config ────────────────────────────────────────────────────────────────────

# FIX 1: Safe secrets access — avoids secrets.toml KeyError crash
try:
    API_BASE_URL = st.secrets["API_BASE_URL"]
except Exception:
    API_BASE_URL = "http://localhost:8000"

REQUEST_TIMEOUT = 30

# ── Helper functions ──────────────────────────────────────────────────────────

@st.cache_data
def get_utensils():
    """Fetch available utensils from API."""
    try:
        response = requests.get(f"{API_BASE_URL}/utensils", timeout=REQUEST_TIMEOUT)
        if response.status_code == 200:
            return response.json()
        return []
    except Exception as e:
        st.error(f"Failed to load utensils: {str(e)}")
        return []


def analyze_image(image_file, utensil_id, fill_level):
    """Send image to backend for analysis."""
    try:
        files = {"image": ("image.jpg", image_file, "image/jpeg")}
        data = {
            "fill_level": fill_level
        }
        if utensil_id:
            data["utensil_id"] = utensil_id
        
        with st.spinner("🔄 Analyzing meal... (2-4 seconds)"):
            response = requests.post(
                f"{API_BASE_URL}/analyze",
                files=files,
                data=data,
                timeout=REQUEST_TIMEOUT
            )
        
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 429:
            st.error("⏳ Rate limit exceeded. Max 10 uploads per hour. Try again later.")
            return None
        elif response.status_code == 413:
            st.error("📦 Image too large. Max 5MB.")
            return None
        else:
            error_msg = response.json().get("error", "Unknown error")
            st.error(f"Analysis failed: {error_msg}")
            return None
    
    except requests.Timeout:
        st.error("⏱️ Request timeout. Server not responding.")
        return None
    except Exception as e:
        st.error(f"Error: {str(e)}")
        return None


def get_meal_history():
    """Fetch meal history from API."""
    try:
        response = requests.get(f"{API_BASE_URL}/history?limit=20", timeout=REQUEST_TIMEOUT)
        if response.status_code == 200:
            return response.json()
        return []
    except Exception as e:
        st.warning(f"Could not load history: {str(e)}")
        return []


def get_daily_summary():
    """Get today's calorie total."""
    try:
        response = requests.get(f"{API_BASE_URL}/summary", timeout=REQUEST_TIMEOUT)
        if response.status_code == 200:
            return response.json()
        return {"meals": 0, "total_kcal": 0}
    except Exception:
        return {"meals": 0, "total_kcal": 0}


# ── Main UI ───────────────────────────────────────────────────────────────────

st.markdown("""
<div style="text-align: center; margin-bottom: 2rem;">
    <h1>🍛 Food Calorie Tracker</h1>
    <p style="font-size: 1.1rem; color: #666; margin-top: -1rem;">
        Upload a photo of your meal and get instant calorie estimates
    </p>
</div>
""", unsafe_allow_html=True)

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_analyze, tab_utensils, tab_history = st.tabs(
    ["📸 Analyze Meal", "🥄 Manage Utensils", "📊 History"]
)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1: ANALYZE MEAL
# ══════════════════════════════════════════════════════════════════════════════

with tab_analyze:
    col1, col2 = st.columns([1, 1], gap="large")
    
    with col1:
        st.markdown("### 📸 Upload Your Meal")
        
        uploaded_file = st.file_uploader(
            "Choose an image (JPEG, PNG, or WebP)",
            type=["jpg", "jpeg", "png", "webp"],
            help="Photo should be well-lit with utensil visible for better estimation"
        )
        
        if uploaded_file:
            st.image(uploaded_file, caption="Your meal", use_column_width=True)
        
        st.markdown("---")
        st.markdown("### ⚙️ Portion Settings")
        
        utensils = get_utensils()
        utensil_options = {u["name"]: u["id"] for u in utensils}
        utensil_options["None (estimate from photo)"] = None
        
        selected_utensil = st.selectbox(
            "Which utensil? (optional)",
            options=list(utensil_options.keys()),
            help="Having a utensil profile helps us estimate portion size more accurately"
        )
        utensil_id = utensil_options[selected_utensil]
        
        fill_level = st.slider(
            "How full is the utensil?",
            min_value=0.1,
            max_value=1.0,
            value=0.85,
            step=0.05,
            help="0.85 = 85% full (typical serving)"
        )
        
        st.info(
            "💡 **Tips for best results:**\n"
            "- Good lighting (natural light preferred)\n"
            "- Place utensil on a neutral background\n"
            "- Take photo from directly above\n"
            "- Ensure food fills the frame"
        )
    
    with col2:
        st.markdown("### 📊 Results")
        
        if uploaded_file:
            if st.button("🚀 Analyze Meal", use_container_width=True):
                # Read image bytes
                image_bytes = uploaded_file.read()
                
                # Analyze
                result = analyze_image(image_bytes, utensil_id, fill_level)
                
                if result:
                    st.session_state["last_analysis"] = result
                    
                    # FIX 2: Guard total_kcal from None before formatting
                    total_kcal = float(result.get("total_kcal") or 0)
                    st.markdown(f"""
                    <div style="background: linear-gradient(135deg, #DC2626 0%, #EA580C 100%); 
                                color: white; padding: 2rem; border-radius: 1rem; text-align: center; margin: 1rem 0;">
                        <div style="font-size: 0.9rem; opacity: 0.9;">Total Calories</div>
                        <div style="font-size: 3.5rem; font-weight: 800;">{total_kcal:.0f}</div>
                        <div style="font-size: 0.9rem; opacity: 0.9;">kcal</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Display dishes
                    dishes = result.get("dishes", [])
                    if dishes:
                        st.markdown("**Detected Dishes:**")
                        for i, dish in enumerate(dishes):
                            # FIX 3: Guard dish fields from None
                            dish_name = dish.get("dish_name") or "Unknown Dish"
                            subtotal_kcal = float(dish.get("subtotal_kcal") or 0)
                            confidence = dish.get("confidence") or "N/A"
                            weight_g = float(dish.get("weight_g") or 0)

                            with st.expander(
                                f"🍽️ {dish_name} - {subtotal_kcal:.0f} kcal "
                                f"(confidence: {confidence})"
                            ):
                                col_a, col_b, col_c = st.columns(3)
                                with col_a:
                                    st.metric("Weight", f"{weight_g:.0f}g")
                                with col_b:
                                    st.metric("Calories", f"{subtotal_kcal:.0f} kcal")
                                with col_c:
                                    st.metric("Confidence", confidence)
                                
                                # Ingredients breakdown
                                st.markdown("**Ingredients:**")
                                for ingredient in dish.get("ingredients", []):
                                    # FIX 4: Guard ingredient fields from None
                                    ing_name = ingredient.get("name") or "Unknown"
                                    ing_grams = float(ingredient.get("grams") or 0)
                                    ing_kcal = float(ingredient.get("kcal") or 0)
                                    st.markdown(
                                        f"• **{ing_name}**: {ing_grams:.0f}g "
                                        f"({ing_kcal:.0f} kcal)"
                                    )
                                
                                if dish.get("notes"):
                                    st.caption(f"📝 {dish['notes']}")
                    
                    # From cache indicator
                    if result.get("from_cache"):
                        st.info("⚡ Result from cache (faster response)")
                    
                    # Estimation method
                    st.caption(f"📍 {result.get('estimation_method', 'Image analysis')}")
        
        else:
            st.info("👈 Upload an image to get started!")
        
        # Daily summary
        st.markdown("---")
        st.markdown("### 📅 Today's Summary")

        # FIX 5: Null-safe daily summary — the primary crash fix
        summary = get_daily_summary()
        meal_count = summary.get("meals", 0) or 0
        total_kcal_today = float(summary.get("total_kcal") or 0)

        col_1, col_2 = st.columns(2)
        with col_1:
            st.metric("Meals Logged", meal_count)
        with col_2:
            st.metric("Total Calories", f"{total_kcal_today:.0f}")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2: MANAGE UTENSILS
# ══════════════════════════════════════════════════════════════════════════════

with tab_utensils:
    col1, col2 = st.columns([1, 1], gap="large")
    
    with col1:
        st.markdown("### ➕ Add New Utensil")
        
        with st.form("new_utensil_form"):
            name = st.text_input("Name (e.g., 'Small Bowl')")
            utensil_type = st.selectbox(
                "Type",
                ["bowl", "plate", "glass", "cup", "katori", "spoon", "other"]
            )
            diameter = st.number_input("Diameter (cm)", min_value=0.0, step=0.1)
            depth = st.number_input("Depth (cm)", min_value=0.0, step=0.1)
            volume = st.number_input("Volume (ml)", min_value=0.0, step=10.0)
            notes = st.text_area("Notes (optional)")
            
            if st.form_submit_button("✅ Add Utensil", use_container_width=True):
                try:
                    payload = {
                        "name": name,
                        "type": utensil_type,
                        "diameter_cm": diameter if diameter > 0 else None,
                        "depth_cm": depth if depth > 0 else None,
                        "volume_ml": volume if volume > 0 else None,
                        "notes": notes if notes else None,
                    }
                    response = requests.post(f"{API_BASE_URL}/utensils", json=payload)
                    if response.status_code == 201:
                        st.success(f"✅ Added '{name}'!")
                        st.rerun()
                    else:
                        st.error(response.json()["detail"])
                except Exception as e:
                    st.error(f"Failed to add utensil: {str(e)}")
    
    with col2:
        st.markdown("### 📋 Your Utensils")
        
        utensils = get_utensils()
        if utensils:
            for u in utensils:
                with st.expander(f"🥄 {u.get('name', 'Unnamed')} ({u.get('type', 'unknown')})"):
                    # FIX 6: Guard utensil fields — None from DB shows "N/A" instead of crashing
                    st.write(f"**Volume:** {u.get('volume_ml') or 'N/A'} ml")
                    st.write(f"**Diameter:** {u.get('diameter_cm') or 'N/A'} cm")
                    st.write(f"**Depth:** {u.get('depth_cm') or 'N/A'} cm")
                    if u.get("notes"):
                        st.write(f"**Notes:** {u['notes']}")
                    
                    if st.button(f"🗑️ Delete", key=f"delete_{u['id']}", use_container_width=True):
                        try:
                            requests.delete(f"{API_BASE_URL}/utensils/{u['id']}")
                            st.success("Deleted!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to delete: {str(e)}")
        else:
            st.info("No utensils saved yet. Create one above!")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3: HISTORY
# ══════════════════════════════════════════════════════════════════════════════

with tab_history:
    st.markdown("### 📊 Recent Meals")
    
    history = get_meal_history()
    if history:
        for meal in history:
            # FIX 7: Guard all history fields from None
            meal_name = meal.get("dish_name") or "Unknown Dish"
            meal_kcal = float(meal.get("total_kcal") or 0)
            meal_date = (meal.get("logged_at") or "")[:10] or "Unknown date"

            with st.expander(f"🍽️ {meal_name} - {meal_kcal:.0f} kcal - {meal_date}"):
                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    st.metric("Calories", f"{meal_kcal:.0f}")
                with col_b:
                    # FIX 8: Guard weight_g from None
                    weight_g = float(meal.get("weight_g") or 0)
                    st.metric("Weight", f"{weight_g:.0f}g")
                with col_c:
                    # FIX 9: Guard fill_level from None
                    fill_level = float(meal.get("fill_level") or 0)
                    st.metric("Fill Level", f"{fill_level * 100:.0f}%")
                
                if meal.get("utensil_name"):
                    st.write(f"**Utensil:** {meal['utensil_name']}")
                
                st.write("**Ingredients:**")
                for ing in meal.get("ingredients", []):
                    ing_name = ing.get("name") or "Unknown"
                    ing_grams = float(ing.get("grams") or 0)
                    ing_kcal = float(ing.get("kcal") or 0)
                    st.write(f"• {ing_name}: {ing_grams:.0f}g ({ing_kcal:.0f} kcal)")
    else:
        st.info("No meal history yet. Analyze your first meal!")

# ── Footer ────────────────────────────────────────────────────────────────────

st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #999; font-size: 0.85rem; margin-top: 2rem;">
    <p>🍛 Indian Food Calorie Tracker | Powered by Gemini 1.5 Flash</p>
    <p>Estimates are approximate. For precise nutrition info, consult a dietitian.</p>
</div>
""", unsafe_allow_html=True)