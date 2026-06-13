import os
from datetime import date, timedelta
from fastapi import APIRouter, HTTPException, Depends
from models.schemas import SimulateWellnessRequest
from services.supabase_client import supabase
from routers.auth import get_current_user

router = APIRouter(prefix="/api/v1/elder/wellness", tags=["Wellness"])

# Global in-memory simulation state as fallback if Supabase table is missing
SIMULATION_STATE = "STABLE"

# Helper to generate dummy history based on active state
def generate_history(state: str, num_days: int = 14):
    history = []
    base_date = date.today()
    
    # Define state characteristics
    if state == "STABLE":
        score = 88
        step_base, step_var = 7000, 800
        speak_base, speak_var = 120.0, 15.0 # in minutes
        hand_base, hand_var = 90.0, 5.0
    elif state == "MONITORING":
        score = 72
        step_base, step_var = 5200, 500
        speak_base, speak_var = 90.0, 10.0
        hand_base, hand_var = 75.0, 4.0
    elif state == "SUPPORT_NEEDED":
        score = 52
        step_base, step_var = 3400, 400
        speak_base, speak_var = 60.0, 8.0
        hand_base, hand_var = 60.0, 5.0
    else: # DECLINE
        score = 35
        step_base, step_var = 1500, 300
        speak_base, speak_var = 25.0, 5.0
        hand_base, hand_var = 38.0, 4.0
        
    for i in range(num_days - 1, -1, -1):
        day = base_date - timedelta(days=i)
        # Add some random variation
        import random
        random.seed(day.toordinal()) # Deterministic variation based on date
        
        day_steps = int(step_base + random.randint(-step_var, step_var))
        day_speak = round(speak_base + random.uniform(-speak_var, speak_var), 1)
        day_hand = round(hand_base + random.uniform(-hand_var, hand_var), 1)
        
        # Gradually decrease if decline state
        if state == "DECLINE" and i < 7:
            # First week was slightly better than the last week
            day_steps = int(day_steps * (1.2 if i >= 7 else 0.8))
            day_speak = round(day_speak * (1.2 if i >= 7 else 0.7), 1)
            day_hand = round(day_hand * (1.1 if i >= 7 else 0.9), 1)
            
        history.append({
            "recorded_date": day.isoformat(),
            "steps": day_steps,
            "speaking_duration_min": day_speak,
            "hand_activity_score": day_hand,
            "care_priority_score": score
        })
        
    return history, score

@router.get("")
def get_wellness(current_user: dict = Depends(get_current_user)):
    """Retrieve the wellness metrics, weekly trends, and suggestions for the elder."""
    user_id = current_user["sub"]
    role = current_user["role"]
    
    if role != "elder":
        raise HTTPException(status_code=403, detail="Only elders can view their wellness dashboard")
        
    # Get elder profile ID
    profile_res = supabase.table("elder_profiles").select("id, care_score").eq("user_id", user_id).execute()
    if not profile_res.data:
        raise HTTPException(status_code=404, detail="Elder profile not found")
        
    elder_id = profile_res.data[0]["id"]
    current_db_score = profile_res.data[0].get("care_score", 100)
    
    # Try fetching from Database
    try:
        db_history_res = supabase.table("elder_wellness_trends").select("*").eq("elder_id", elder_id).order("recorded_date", desc=True).limit(14).execute()
        
        # If there are records in the database, calculate actual values from DB
        if db_history_res.data and len(db_history_res.data) >= 7:
            history = db_history_res.data
            # Reverse history to chronological order for charts
            history.reverse()
            
            latest_score = history[-1].get("care_priority_score", current_db_score)
            
            # Calculate weekly trends (last 7 days vs previous 7 days)
            recent_week = history[-7:]
            prev_week = history[-14:-7] if len(history) >= 14 else history[:-7]
            
            if prev_week:
                recent_steps = sum(d["steps"] for d in recent_week) / len(recent_week)
                prev_steps = sum(d["steps"] for d in prev_week) / len(prev_week)
                mobility_change = round(((recent_steps - prev_steps) / (prev_steps or 1)) * 100, 1)
                
                recent_speak = sum(d["speaking_duration_min"] for d in recent_week) / len(recent_week)
                prev_speak = sum(d["speaking_duration_min"] for d in prev_week) / len(prev_week)
                social_change = round(((recent_speak - prev_speak) / (prev_speak or 1)) * 100, 1)
            else:
                mobility_change = -12.0 # Default fallback trend if not enough history
                social_change = -18.0
                
            # Count assistance requests
            reqs_res = supabase.table("assistance_requests").select("id").eq("elder_id", elder_id).execute()
            reqs_count = len(reqs_res.data) if reqs_res.data else 0
            
            show_alert = latest_score < 40
            
        else:
            # If DB table exists but has no data, default to using simulator fallback
            raise Exception("No data in DB")
            
    except Exception as e:
        # Fallback to Simulator / In-Memory Mock Mode
        history, latest_score = generate_history(SIMULATION_STATE, 14)
        
        # Calculate trends based on state
        if SIMULATION_STATE == "STABLE":
            mobility_change = -1.2
            social_change = 0.5
            show_alert = False
        elif SIMULATION_STATE == "MONITORING":
            mobility_change = -5.4
            social_change = -6.2
            show_alert = False
        elif SIMULATION_STATE == "SUPPORT_NEEDED":
            mobility_change = -12.0
            social_change = -15.4
            show_alert = False
        else: # DECLINE
            mobility_change = -28.5
            social_change = -34.8
            show_alert = True
            
        # Mock requests count based on state
        reqs_count = 2 if SIMULATION_STATE in ["SUPPORT_NEEDED", "DECLINE"] else 0

    # Format recommendations & suggestions
    if latest_score >= 80:
        recommendation = "Independent"
        suggestion_text = "Great job! You've maintained your activity levels this week."
    elif latest_score >= 60:
        recommendation = "Periodic monitoring"
        suggestion_text = "Your speaking duration has decreased slightly this week. Connecting with friends or family can positively support well-being."
    elif latest_score >= 40:
        recommendation = "Additional support may be beneficial"
        suggestion_text = "Your walking activity has reduced recently. Consider taking short daily walks or discussing this change with your healthcare provider."
    else:
        recommendation = "High-priority caregiving recommended"
        suggestion_text = "Your activity levels and social interactions have shown a consistent decline. Setting up a caregiver visit is highly recommended."

    # Retrieve family contacts mapped to this elder
    family_contacts = []
    try:
        family_res = supabase.table("family_profiles").select("relationship, users(name, phone)").eq("elder_id", elder_id).execute()
        if family_res.data:
            for item in family_res.data:
                u_info = item.get("users", {})
                if u_info:
                    family_contacts.append({
                        "relationship": item["relationship"],
                        "name": u_info.get("name"),
                        "phone": u_info.get("phone")
                    })
    except Exception:
        pass

    if not family_contacts:
        family_contacts = [
            {"relationship": "Son", "name": "Takeshi Tanaka", "phone": "+81-90-8765-4321"},
            {"relationship": "Daughter", "name": "Yuko Tanaka", "phone": "+81-90-5555-1234"}
        ]

    # Calculate averages (last 7 days)
    recent_week = history[-7:] if len(history) >= 7 else history
    steps_average = int(sum(d["steps"] for d in recent_week) / len(recent_week)) if recent_week else 0
    speaking_average = round(sum(d["speaking_duration_min"] for d in recent_week) / len(recent_week), 1) if recent_week else 0.0

    return {
        "care_priority_score": latest_score,
        "recommendation": recommendation,
        "mobility_change_pct": mobility_change,
        "social_change_pct": social_change,
        "assistance_requests_count": reqs_count,
        "suggestion_text": suggestion_text,
        "show_high_priority_alert": show_alert,
        "history": history,
        "simulation_mode": SIMULATION_STATE,
        "family_contacts": family_contacts,
        "steps_average": steps_average,
        "speaking_average": speaking_average
    }

@router.post("/simulate")
def simulate_wellness(body: SimulateWellnessRequest, current_user: dict = Depends(get_current_user)):
    """Developer endpoint to simulate wellness state (overwrites DB or updates in-memory)."""
    user_id = current_user["sub"]
    role = current_user["role"]
    
    if role != "elder":
        raise HTTPException(status_code=403, detail="Only elders can trigger wellness simulation")
        
    state = body.state.upper()
    if state not in ["STABLE", "MONITORING", "SUPPORT_NEEDED", "DECLINE"]:
        raise HTTPException(status_code=400, detail="Invalid simulation state")
        
    # Update global simulation state
    global SIMULATION_STATE
    SIMULATION_STATE = state
    
    # Get elder profile ID
    profile_res = supabase.table("elder_profiles").select("id").eq("user_id", user_id).execute()
    if not profile_res.data:
        raise HTTPException(status_code=404, detail="Elder profile not found")
        
    elder_id = profile_res.data[0]["id"]
    
    # Update care_score in elder_profiles table to reflect active state
    history, score = generate_history(state, 14)
    try:
        supabase.table("elder_profiles").update({"care_score": score}).eq("id", elder_id).execute()
        
        # Try writing simulation history to elder_wellness_trends table
        # 1. Clean up existing logs
        supabase.table("elder_wellness_trends").delete().eq("elder_id", elder_id).execute()
        
        # 2. Insert new logs
        db_entries = []
        for h in history:
            db_entries.append({
                "elder_id": elder_id,
                "recorded_date": h["recorded_date"],
                "steps": h["steps"],
                "speaking_duration_min": h["speaking_duration_min"],
                "hand_activity_score": h["hand_activity_score"],
                "care_priority_score": h["care_priority_score"]
            })
        supabase.table("elder_wellness_trends").insert(db_entries).execute()
        
    except Exception as e:
        # If DB table does not exist, that's fine — fallback will run using global SIMULATION_STATE
        pass
        
    return {"status": "success", "simulated_state": state, "care_priority_score": score}
