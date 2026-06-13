"""
Seed script — generates proper bcrypt hashes and seeds the database via Supabase API.
Run: python seed_db.py
"""
import os
from dotenv import load_dotenv
from passlib.context import CryptContext

load_dotenv()

from services.supabase_client import supabase

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
PASSWORD = "password123"
password_hash = pwd_context.hash(PASSWORD)

print(f"Using bcrypt hash: {password_hash}")

# Seed users
users = [
    {
        "id": "00000000-0000-0000-0000-000000000001",
        "email": "hana@example.com",
        "password_hash": password_hash,
        "role": "elder",
        "name": "Hana Tanaka",
        "phone": "+81-90-1234-5678",
    },
    {
        "id": "00000000-0000-0000-0000-000000000002",
        "email": "kenji@example.com",
        "password_hash": password_hash,
        "role": "volunteer",
        "name": "Kenji Mori",
        "phone": "+81-90-2345-6789",
    },
    {
        "id": "00000000-0000-0000-0000-000000000003",
        "email": "yuki@example.com",
        "password_hash": password_hash,
        "role": "volunteer",
        "name": "Yuki Sato",
        "phone": "+81-90-3456-7890",
    },
    {
        "id": "00000000-0000-0000-0000-000000000004",
        "email": "takeshi@example.com",
        "password_hash": password_hash,
        "role": "family",
        "name": "Takeshi Tanaka",
        "phone": "+81-90-8765-4321",
    },
    {
        "id": "00000000-0000-0000-0000-000000000005",
        "email": "yuko@example.com",
        "password_hash": password_hash,
        "role": "family",
        "name": "Yuko Tanaka",
        "phone": "+81-90-5555-1234",
    },
]

for user in users:
    try:
        supabase.table("users").upsert(user).execute()
        print(f"[OK] User: {user['name']} ({user['role']})")
    except Exception as e:
        print(f"[FAIL] User {user['name']}: {e}")

# Seed elder profile
try:
    existing = supabase.table("elder_profiles").select("id").eq("user_id", "00000000-0000-0000-0000-000000000001").execute()
    if existing.data:
        supabase.table("elder_profiles").update({
            "age": 78,
            "care_score": 67,
            "lat": 35.6762,
            "lng": 139.6503,
        }).eq("user_id", "00000000-0000-0000-0000-000000000001").execute()
    else:
        supabase.table("elder_profiles").insert({
            "user_id": "00000000-0000-0000-0000-000000000001",
            "age": 78,
            "care_score": 67,
            "lat": 35.6762,
            "lng": 139.6503,
        }).execute()
    print("[OK] Elder profile: Hana Tanaka")
except Exception as e:
    print(f"[FAIL] Elder profile: {e}")

# Seed volunteer profiles
vol_profiles = [
    {
        "user_id": "00000000-0000-0000-0000-000000000002",
        "is_available": True,
        "lat": 35.6800,
        "lng": 139.6520,
    },
    {
        "user_id": "00000000-0000-0000-0000-000000000003",
        "is_available": False,
        "lat": 35.6900,
        "lng": 139.6600,
    },
]

for vp in vol_profiles:
    try:
        existing = supabase.table("volunteer_profiles").select("id").eq("user_id", vp["user_id"]).execute()
        if existing.data:
            supabase.table("volunteer_profiles").update({
                "is_available": vp["is_available"],
                "lat": vp["lat"],
                "lng": vp["lng"],
            }).eq("user_id", vp["user_id"]).execute()
        else:
            supabase.table("volunteer_profiles").insert(vp).execute()
        print(f"[OK] Volunteer profile: user_id={vp['user_id']}")
    except Exception as e:
        print(f"[FAIL] Volunteer profile: {e}")

# Seed default wellness trends (if table exists)
try:
    from datetime import date, timedelta
    import random
    
    # Check if elder profile exists
    elder_res = supabase.table("elder_profiles").select("id").eq("user_id", "00000000-0000-0000-0000-000000000001").execute()
    if elder_res.data:
        elder_id = elder_res.data[0]["id"]
        
        # Check if table exists
        supabase.table("elder_wellness_trends").select("id").limit(1).execute()
        
        # Clear existing logs
        supabase.table("elder_wellness_trends").delete().eq("elder_id", elder_id).execute()
        
        # Generate 14 days of STABLE history
        base_date = date.today()
        trends = []
        for i in range(14):
            day = base_date - timedelta(days=i)
            random.seed(day.toordinal())
            trends.append({
                "elder_id": elder_id,
                "recorded_date": day.isoformat(),
                "steps": int(7200 + random.randint(-800, 800)),
                "speaking_duration_min": round(120.0 + random.uniform(-15.0, 15.0), 1),
                "hand_activity_score": round(90.0 + random.uniform(-5.0, 5.0), 1),
                "care_priority_score": 88
            })
            
        supabase.table("elder_wellness_trends").insert(trends).execute()
        print("[OK] Wellness trends: seeded 14 days of mock history for Hana Tanaka")
except Exception as e:
    print("[INFO] Wellness trends seeding skipped (table 'elder_wellness_trends' may not exist yet)")

# Seed family profiles (if table exists)
try:
    family_profiles = [
        {
            "user_id": "00000000-0000-0000-0000-000000000004",
            "relationship": "Son"
        },
        {
            "user_id": "00000000-0000-0000-0000-000000000005",
            "relationship": "Daughter"
        }
    ]
    
    # We need to get Hana Tanaka's actual profile UUID from elder_profiles first
    elder_res = supabase.table("elder_profiles").select("id").eq("user_id", "00000000-0000-0000-0000-000000000001").execute()
    if elder_res.data:
        h_profile_id = elder_res.data[0]["id"]
        for fp in family_profiles:
            fp["elder_id"] = h_profile_id
            
            existing = supabase.table("family_profiles").select("id").eq("user_id", fp["user_id"]).execute()
            if existing.data:
                supabase.table("family_profiles").update({
                    "elder_id": fp["elder_id"],
                    "relationship": fp["relationship"]
                }).eq("user_id", fp["user_id"]).execute()
            else:
                supabase.table("family_profiles").insert(fp).execute()
            print(f"[OK] Family profile: user_id={fp['user_id']} ({fp['relationship']})")
except Exception as e:
    print(f"[INFO] Family profiles seeding skipped (table 'family_profiles' may not exist yet)")

print("\n[SUCCESS] Seed complete! Demo credentials:")
print(f"  Elder:     hana@example.com / {PASSWORD}")
print(f"  Volunteer: kenji@example.com / {PASSWORD}")
print(f"  Volunteer: yuki@example.com / {PASSWORD}")
print(f"  Family:    takeshi@example.com / {PASSWORD} (Son)")
print(f"  Family:    yuko@example.com / {PASSWORD} (Daughter)")
