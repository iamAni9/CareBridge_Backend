from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends

from models.schemas import CreateAssistanceRequest, UpdateStatusRequest
from routers.auth import get_current_user
from services.supabase_client import supabase
from services.matching import find_nearest_volunteer
from services.groq_service import generate_volunteer_briefing

router = APIRouter(prefix="/api/v1/assistance", tags=["Assistance"])


def require_elder(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role") != "elder":
        raise HTTPException(status_code=403, detail="Elder role required")
    return current_user


def require_volunteer(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role") != "volunteer":
        raise HTTPException(status_code=403, detail="Volunteer role required")
    return current_user


@router.post("/request")
def create_request(body: CreateAssistanceRequest, elder: dict = Depends(require_elder)):
    """
    Elder creates an assistance request.
    1. Get elder lat/lng
    2. Find nearest volunteer
    3. Generate AI briefing via Groq
    4. Insert request (ASSIGNED or PENDING)
    5. Mark volunteer unavailable
    """
    user_id = elder["sub"]

    # Get elder profile
    elder_profile = supabase.table("elder_profiles").select("*").eq("user_id", user_id).execute()
    if not elder_profile.data:
        raise HTTPException(status_code=404, detail="Elder profile not found")

    ep = elder_profile.data[0]

    # Get elder's user info for name
    elder_user = supabase.table("users").select("name").eq("id", user_id).execute()
    elder_name = elder_user.data[0]["name"] if elder_user.data else "Elder"

    # Find nearest volunteer
    nearest = find_nearest_volunteer(ep["lat"], ep["lng"])

    request_data = {
        "elder_id": ep["id"],
        "type": body.type.value,
        "elder_note": body.elder_note,
    }

    if nearest:
        # Generate AI briefing
        ai_message = generate_volunteer_briefing(
            elder_name=elder_name,
            request_type=body.type.value,
            distance_km=nearest["distance_km"],
            elder_note=body.elder_note,
            elder_age=ep.get("age"),
        )

        request_data.update({
            "status": "ASSIGNED",
            "volunteer_id": nearest["volunteer_id"],
            "ai_message": ai_message,
            "distance_km": nearest["distance_km"],
            "assigned_at": datetime.now(timezone.utc).isoformat(),
        })
    else:
        request_data["status"] = "PENDING"

    # Insert the request
    result = supabase.table("assistance_requests").insert(request_data).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create request")

    req = result.data[0]

    if nearest:
        # Set volunteer unavailable
        supabase.table("volunteer_profiles").update(
            {"is_available": False}
        ).eq("id", nearest["volunteer_id"]).execute()

        # Log event
        supabase.table("request_events").insert({
            "request_id": req["id"],
            "event_type": "ASSIGNED",
            "actor_id": user_id,
            "note": f"Auto-assigned to volunteer {nearest['distance_km']:.1f} km away",
        }).execute()

    # Enrich with volunteer name if assigned
    if nearest:
        vol_user = supabase.table("users").select("name").eq(
            "id", nearest["user_id"]
        ).execute()
        req["volunteer_name"] = vol_user.data[0]["name"] if vol_user.data else None

    req["elder_name"] = elder_name
    return req


@router.get("/active")
def get_active(elder: dict = Depends(require_elder)):
    """Get the elder's most recent PENDING or ASSIGNED request."""
    user_id = elder["sub"]

    # Get elder profile id
    ep = supabase.table("elder_profiles").select("id").eq("user_id", user_id).execute()
    if not ep.data:
        return None

    result = supabase.table("assistance_requests").select(
        "*, volunteer_profiles(user_id)"
    ).eq("elder_id", ep.data[0]["id"]).in_(
        "status", ["PENDING", "ASSIGNED", "EN_ROUTE"]
    ).order("created_at", desc=True).limit(1).execute()

    if not result.data:
        return None

    req = result.data[0]

    # Enrich with names
    elder_user = supabase.table("users").select("name").eq("id", user_id).execute()
    req["elder_name"] = elder_user.data[0]["name"] if elder_user.data else None

    if req.get("volunteer_id"):
        vol_profile = req.get("volunteer_profiles")
        if vol_profile and vol_profile.get("user_id"):
            vol_user = supabase.table("users").select("name").eq(
                "id", vol_profile["user_id"]
            ).execute()
            req["volunteer_name"] = vol_user.data[0]["name"] if vol_user.data else None
        # Clean up nested data
        req.pop("volunteer_profiles", None)

    return req


@router.get("/history")
def get_history(elder: dict = Depends(require_elder)):
    """Get elder's last 10 requests."""
    user_id = elder["sub"]

    ep = supabase.table("elder_profiles").select("id").eq("user_id", user_id).execute()
    if not ep.data:
        return []

    result = supabase.table("assistance_requests").select("*").eq(
        "elder_id", ep.data[0]["id"]
    ).order("created_at", desc=True).limit(10).execute()

    # Enrich with volunteer names
    requests = result.data or []
    for req in requests:
        if req.get("volunteer_id"):
            vp = supabase.table("volunteer_profiles").select("user_id").eq(
                "id", req["volunteer_id"]
            ).execute()
            if vp.data:
                vu = supabase.table("users").select("name").eq(
                    "id", vp.data[0]["user_id"]
                ).execute()
                req["volunteer_name"] = vu.data[0]["name"] if vu.data else None

    return requests


@router.patch("/{request_id}/status")
def update_status(
    request_id: str,
    body: UpdateStatusRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Update request status. 
    Elders can only cancel. Volunteers can transition states or cancel (triggering a re-match).
    """
    user_id = current_user["sub"]
    role = current_user["role"]

    # Get the request
    result = supabase.table("assistance_requests").select("*").eq("id", request_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Request not found")

    req = result.data[0]

    # Validate authorization & role constraints
    if role == "volunteer":
        # Get volunteer profile
        vp = supabase.table("volunteer_profiles").select("id").eq("user_id", user_id).execute()
        if not vp.data or req["volunteer_id"] != vp.data[0]["id"]:
            raise HTTPException(status_code=403, detail="Not authorized to update this request")
    elif role == "elder":
        # Get elder profile
        ep = supabase.table("elder_profiles").select("id").eq("user_id", user_id).execute()
        if not ep.data or req["elder_id"] != ep.data[0]["id"]:
            raise HTTPException(status_code=403, detail="Not authorized to update this request")
        if body.status.value != "CANCELLED":
            raise HTTPException(status_code=400, detail="Elders can only cancel requests")
    else:
        raise HTTPException(status_code=403, detail="Invalid role")

    # Validate transition
    current = req["status"]
    new_status = body.status.value
    valid_transitions = {
        "PENDING": ["CANCELLED"],
        "ASSIGNED": ["EN_ROUTE", "CANCELLED"],
        "EN_ROUTE": ["COMPLETED", "CANCELLED"],
    }

    if new_status not in valid_transitions.get(current, []):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from {current} to {new_status}",
        )

    update_data = {"status": new_status}

    if new_status == "COMPLETED":
        update_data["completed_at"] = datetime.now(timezone.utc).isoformat()
        if req.get("volunteer_id"):
            # Make volunteer available again
            supabase.table("volunteer_profiles").update(
                {"is_available": True}
            ).eq("id", req["volunteer_id"]).execute()

    elif new_status == "CANCELLED":
        # Make volunteer available again if assigned
        if req.get("volunteer_id"):
            supabase.table("volunteer_profiles").update(
                {"is_available": True}
            ).eq("id", req["volunteer_id"]).execute()

        # If volunteer cancelled: attempt to re-match the request to someone else
        if role == "volunteer":
            ep = supabase.table("elder_profiles").select("lat, lng").eq(
                "id", req["elder_id"]
            ).execute()
            if ep.data:
                new_volunteer = find_nearest_volunteer(ep.data[0]["lat"], ep.data[0]["lng"])
                if new_volunteer:
                    update_data.update({
                        "status": "ASSIGNED",
                        "volunteer_id": new_volunteer["volunteer_id"],
                        "distance_km": new_volunteer["distance_km"],
                        "assigned_at": datetime.now(timezone.utc).isoformat(),
                    })
                    supabase.table("volunteer_profiles").update(
                        {"is_available": False}
                    ).eq("id", new_volunteer["volunteer_id"]).execute()
                else:
                    update_data.update({
                        "status": "PENDING",
                        "volunteer_id": None,
                    })
        # If elder cancelled: request is closed completely, no re-match
        else:
            update_data.update({
                "status": "CANCELLED",
                "volunteer_id": None,
            })

    # Update request
    updated = supabase.table("assistance_requests").update(
        update_data
    ).eq("id", request_id).execute()

    # Log event
    supabase.table("request_events").insert({
        "request_id": request_id,
        "event_type": new_status,
        "actor_id": user_id,
    }).execute()

    return updated.data[0] if updated.data else req


@router.get("/volunteer/active")
def get_volunteer_active(volunteer: dict = Depends(require_volunteer)):
    """Get the request currently ASSIGNED to this volunteer."""
    user_id = volunteer["sub"]

    vp = supabase.table("volunteer_profiles").select("id").eq("user_id", user_id).execute()
    if not vp.data:
        return None

    result = supabase.table("assistance_requests").select("*").eq(
        "volunteer_id", vp.data[0]["id"]
    ).in_("status", ["ASSIGNED", "EN_ROUTE"]).order(
        "created_at", desc=True
    ).limit(1).execute()

    if not result.data:
        return None

    req = result.data[0]

    # Enrich with elder name
    ep = supabase.table("elder_profiles").select("user_id").eq("id", req["elder_id"]).execute()
    if ep.data:
        eu = supabase.table("users").select("name").eq("id", ep.data[0]["user_id"]).execute()
        req["elder_name"] = eu.data[0]["name"] if eu.data else None

    return req


@router.get("/volunteer/history")
def get_volunteer_history(volunteer: dict = Depends(require_volunteer)):
    """Get volunteer's last 10 completed requests."""
    user_id = volunteer["sub"]

    vp = supabase.table("volunteer_profiles").select("id").eq("user_id", user_id).execute()
    if not vp.data:
        return []

    result = supabase.table("assistance_requests").select("*").eq(
        "volunteer_id", vp.data[0]["id"]
    ).eq("status", "COMPLETED").order("completed_at", desc=True).limit(10).execute()

    requests = result.data or []
    for req in requests:
        ep = supabase.table("elder_profiles").select("user_id").eq("id", req["elder_id"]).execute()
        if ep.data:
            eu = supabase.table("users").select("name").eq("id", ep.data[0]["user_id"]).execute()
            req["elder_name"] = eu.data[0]["name"] if eu.data else None

    return requests
