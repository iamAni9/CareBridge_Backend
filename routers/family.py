import os
from datetime import date, timedelta
from fastapi import APIRouter, HTTPException, Depends
from routers.auth import get_current_user
from services.supabase_client import supabase
import routers.wellness as wellness

router = APIRouter(prefix="/api/v1/family", tags=["Family"])

def require_family(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role") != "family":
        raise HTTPException(status_code=403, detail="Family role required")
    return current_user

@router.get("/dashboard")
def get_family_dashboard(family: dict = Depends(require_family)):
    """Retrieve parent elder's health metrics, weekly wellness report, and alerts."""
    user_id = family["sub"]
    
    # 1. Resolve mapped elder from family_profiles
    try:
        mapping_res = supabase.table("family_profiles").select("elder_id, relationship").eq("user_id", user_id).execute()
        if not mapping_res.data:
            # Fallback for demo: if no DB profile is mapped, link Takeshi or Yuko to Hana Tanaka
            # Find Hana Tanaka's profile
            hana_res = supabase.table("elder_profiles").select("id").eq("user_id", "00000000-0000-0000-0000-000000000001").execute()
            if hana_res.data:
                elder_id = hana_res.data[0]["id"]
                family_email = family.get("email")
                if not family_email:
                    if family.get("sub") == "00000000-0000-0000-0000-000000000004" or "takeshi" in family.get("name", "").lower():
                        family_email = "takeshi@example.com"
                    else:
                        family_email = "yuko@example.com"
                relationship = "Son" if family_email == "takeshi@example.com" else "Daughter"
            else:
                raise HTTPException(status_code=404, detail="No mapped elder found for this account")
        else:
            elder_id = mapping_res.data[0]["elder_id"]
            relationship = mapping_res.data[0]["relationship"]
    except Exception:
        # DB schema fallback (if family_profiles table doesn't exist yet)
        # Find Hana Tanaka's profile
        hana_res = supabase.table("elder_profiles").select("id").eq("user_id", "00000000-0000-0000-0000-000000000001").execute()
        if hana_res.data:
            elder_id = hana_res.data[0]["id"]
            family_email = family.get("email")
            if not family_email:
                if family.get("sub") == "00000000-0000-0000-0000-000000000004" or "takeshi" in family.get("name", "").lower():
                    family_email = "takeshi@example.com"
                else:
                    family_email = "yuko@example.com"
            relationship = "Son" if family_email == "takeshi@example.com" else "Daughter"
        else:
            raise HTTPException(status_code=404, detail="No mapped elder found for this account")

    # 2. Get parent's user name
    profile_res = supabase.table("elder_profiles").select("user_id, care_score").eq("id", elder_id).execute()
    if not profile_res.data:
        raise HTTPException(status_code=404, detail="Elder profile not found")
    
    elder_user_id = profile_res.data[0]["user_id"]
    current_db_score = profile_res.data[0].get("care_score", 100)
    
    elder_user_res = supabase.table("users").select("name").eq("id", elder_user_id).execute()
    parent_name = elder_user_res.data[0]["name"] if elder_user_res.data else "Parent"

    # 3. Retrieve wellness data (similar to wellness.py)
    try:
        db_history_res = supabase.table("elder_wellness_trends").select("*").eq("elder_id", elder_id).order("recorded_date", desc=True).limit(14).execute()
        
        if db_history_res.data and len(db_history_res.data) >= 7:
            history = db_history_res.data
            history.reverse()
            latest_score = history[-1].get("care_priority_score", current_db_score)
            
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
                mobility_change = -12.0
                social_change = -18.0
                
            show_alert = latest_score < 40
        else:
            raise Exception("No DB wellness data")
            
    except Exception:
        # Fallback to shared Simulator state
        history, latest_score = wellness.generate_history(wellness.SIMULATION_STATE, 14)
        if wellness.SIMULATION_STATE == "STABLE":
            mobility_change = -1.2
            social_change = 0.5
            show_alert = False
        elif wellness.SIMULATION_STATE == "MONITORING":
            mobility_change = -5.4
            social_change = -6.2
            show_alert = False
        elif wellness.SIMULATION_STATE == "SUPPORT_NEEDED":
            mobility_change = -12.0
            social_change = -15.4
            show_alert = False
        else: # DECLINE
            mobility_change = -28.5
            social_change = -34.8
            show_alert = True

    # 4. Get active assistance requests for this elder
    active_requests = []
    try:
        reqs_res = supabase.table("assistance_requests").select("*").eq("elder_id", elder_id).order("created_at", desc=True).limit(5).execute()
        if reqs_res.data:
            active_requests = reqs_res.data
            # Enrich requests with volunteer name
            for req in active_requests:
                if req.get("volunteer_id"):
                    vol_res = supabase.table("volunteer_profiles").select("user_id").eq("id", req["volunteer_id"]).execute()
                    if vol_res.data:
                        v_user_res = supabase.table("users").select("name").eq("id", vol_res.data[0]["user_id"]).execute()
                        req["volunteer_name"] = v_user_res.data[0]["name"] if v_user_res.data else None
    except Exception:
        pass

    if latest_score >= 80:
        recommendation = "Independent"
    elif latest_score >= 60:
        recommendation = "Periodic monitoring"
    elif latest_score >= 40:
        recommendation = "Additional support may be beneficial"
    else:
        recommendation = "High-priority caregiving recommended"

    return {
        "parent_name": parent_name,
        "relationship": relationship,
        "care_priority_score": latest_score,
        "recommendation": recommendation,
        "mobility_change_pct": mobility_change,
        "social_change_pct": social_change,
        "alert_active": show_alert,
        "history": history,
        "active_requests": active_requests,
        "simulation_mode": wellness.SIMULATION_STATE
    }
