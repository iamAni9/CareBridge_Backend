from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends

from models.schemas import UpdateLocationRequest, UpdateAvailabilityRequest
from routers.auth import get_current_user
from services.supabase_client import supabase

router = APIRouter(prefix="/api/v1/volunteer", tags=["Volunteer"])


def require_volunteer(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role") != "volunteer":
        raise HTTPException(status_code=403, detail="Volunteer role required")
    return current_user


@router.patch("/location")
def update_location(body: UpdateLocationRequest, volunteer: dict = Depends(require_volunteer)):
    """Update volunteer's lat, lng, and last_seen."""
    user_id = volunteer["sub"]

    result = supabase.table("volunteer_profiles").update({
        "lat": body.lat,
        "lng": body.lng,
        "last_seen": datetime.now(timezone.utc).isoformat(),
    }).eq("user_id", user_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Volunteer profile not found")

    return {"status": "ok"}


@router.patch("/availability")
def update_availability(body: UpdateAvailabilityRequest, volunteer: dict = Depends(require_volunteer)):
    """Toggle volunteer availability."""
    user_id = volunteer["sub"]

    result = supabase.table("volunteer_profiles").update({
        "is_available": body.is_available,
    }).eq("user_id", user_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Volunteer profile not found")

    return result.data[0]


@router.get("/profile")
def get_profile(volunteer: dict = Depends(require_volunteer)):
    """Get full volunteer profile with user info."""
    user_id = volunteer["sub"]

    # Get user info
    user_result = supabase.table("users").select("name, phone").eq("id", user_id).execute()
    if not user_result.data:
        raise HTTPException(status_code=404, detail="User not found")

    # Get volunteer profile
    profile_result = supabase.table("volunteer_profiles").select("*").eq("user_id", user_id).execute()
    if not profile_result.data:
        raise HTTPException(status_code=404, detail="Volunteer profile not found")

    profile = profile_result.data[0]
    profile.update(user_result.data[0])

    return profile
