from services.supabase_client import supabase


def find_nearest_volunteer(elder_lat: float, elder_lng: float, radius_km: float = 10) -> dict | None:
    """
    Call the Supabase RPC function to find the nearest available volunteer
    within the given radius using the Haversine formula.
    Returns dict with volunteer_id, user_id, distance_km or None.
    """
    result = supabase.rpc(
        "find_nearest_volunteer",
        {
            "elder_lat": elder_lat,
            "elder_lng": elder_lng,
            "radius_km": radius_km,
        },
    ).execute()

    if result.data and len(result.data) > 0:
        return result.data[0]
    return None
