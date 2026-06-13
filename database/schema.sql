-- ============================================
-- CareBridge Database Schema
-- Run this in the Supabase SQL Editor
-- ============================================

-- 1. Users
CREATE TABLE IF NOT EXISTS users (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email         text UNIQUE NOT NULL,
    password_hash text NOT NULL,
    role          text CHECK (role IN ('elder', 'volunteer', 'family')) NOT NULL,
    name          text NOT NULL,
    phone         text,
    created_at    timestamptz DEFAULT now()
);

-- 2. Elder Profiles
CREATE TABLE IF NOT EXISTS elder_profiles (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       uuid REFERENCES users(id) ON DELETE CASCADE,
    age           int,
    care_score    int DEFAULT 100,
    address       text,
    lat           float8 NOT NULL,
    lng           float8 NOT NULL,
    created_at    timestamptz DEFAULT now()
);

-- 3. Volunteer Profiles
CREATE TABLE IF NOT EXISTS volunteer_profiles (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       uuid REFERENCES users(id) ON DELETE CASCADE,
    is_available  boolean DEFAULT true,
    lat           float8 NOT NULL,
    lng           float8 NOT NULL,
    last_seen     timestamptz DEFAULT now(),
    created_at    timestamptz DEFAULT now()
);

-- 4. Assistance Requests
CREATE TABLE IF NOT EXISTS assistance_requests (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    elder_id         uuid REFERENCES elder_profiles(id) ON DELETE CASCADE,
    volunteer_id     uuid REFERENCES volunteer_profiles(id),
    type             text CHECK (type IN (
                       'GROCERIES','TRANSPORT','MEDICINE','FAMILY_CALL','CAREGIVER'
                     )) NOT NULL,
    status           text CHECK (status IN (
                       'PENDING','ASSIGNED','EN_ROUTE','COMPLETED','CANCELLED'
                     )) DEFAULT 'PENDING',
    ai_message       text,
    elder_note       text,
    distance_km      float8,
    created_at       timestamptz DEFAULT now(),
    assigned_at      timestamptz,
    completed_at     timestamptz
);

-- 5. Request Events (audit log)
CREATE TABLE IF NOT EXISTS request_events (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id    uuid REFERENCES assistance_requests(id) ON DELETE CASCADE,
    event_type    text,
    actor_id      uuid REFERENCES users(id),
    note          text,
    created_at    timestamptz DEFAULT now()
);


-- ============================================
-- Indexes
-- ============================================

CREATE INDEX IF NOT EXISTS idx_volunteer_available ON volunteer_profiles (is_available);
CREATE INDEX IF NOT EXISTS idx_volunteer_location ON volunteer_profiles (lat, lng);
CREATE INDEX IF NOT EXISTS idx_request_status ON assistance_requests (status);
CREATE INDEX IF NOT EXISTS idx_request_elder ON assistance_requests (elder_id);
CREATE INDEX IF NOT EXISTS idx_request_volunteer ON assistance_requests (volunteer_id);


-- ============================================
-- Nearest Volunteer Function (Haversine)
-- ============================================

CREATE OR REPLACE FUNCTION find_nearest_volunteer(
    elder_lat float8,
    elder_lng float8,
    radius_km float8 DEFAULT 10
)
RETURNS TABLE (
    volunteer_id uuid,
    user_id uuid,
    distance_km float8
)
LANGUAGE sql STABLE AS $$
    SELECT
        vp.id AS volunteer_id,
        vp.user_id,
        (6371 * acos(
            cos(radians(elder_lat)) * cos(radians(vp.lat)) *
            cos(radians(vp.lng) - radians(elder_lng)) +
            sin(radians(elder_lat)) * sin(radians(vp.lat))
        )) AS distance_km
    FROM volunteer_profiles vp
    WHERE vp.is_available = true
        AND (6371 * acos(
            cos(radians(elder_lat)) * cos(radians(vp.lat)) *
            cos(radians(vp.lng) - radians(elder_lng)) +
            sin(radians(elder_lat)) * sin(radians(vp.lat))
        )) <= radius_km
    ORDER BY distance_km ASC
    LIMIT 1;
$$;


-- ============================================
-- Row Level Security
-- ============================================

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE elder_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE volunteer_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE assistance_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE request_events ENABLE ROW LEVEL SECURITY;

-- Elders see only their own profile
CREATE POLICY elder_own_profile ON elder_profiles
    FOR ALL USING (user_id = auth.uid());

-- Elders see only their own requests
CREATE POLICY elder_own_requests ON assistance_requests
    FOR SELECT USING (
        elder_id IN (SELECT id FROM elder_profiles WHERE user_id = auth.uid())
    );

CREATE POLICY elder_insert_requests ON assistance_requests
    FOR INSERT WITH CHECK (
        elder_id IN (SELECT id FROM elder_profiles WHERE user_id = auth.uid())
    );

-- Volunteers see PENDING requests + their own assigned requests
CREATE POLICY volunteer_see_pending ON assistance_requests
    FOR SELECT USING (
        status = 'PENDING'
        OR volunteer_id IN (SELECT id FROM volunteer_profiles WHERE user_id = auth.uid())
    );

CREATE POLICY volunteer_update_assigned ON assistance_requests
    FOR UPDATE USING (
        volunteer_id IN (SELECT id FROM volunteer_profiles WHERE user_id = auth.uid())
    );

-- Service role bypass (for backend API calls)
-- Note: The backend uses the service role key, which bypasses RLS by default.


-- ============================================
-- Realtime
-- ============================================

ALTER PUBLICATION supabase_realtime ADD TABLE assistance_requests;
ALTER PUBLICATION supabase_realtime ADD TABLE volunteer_profiles;


-- ============================================
-- 6. Elder Wellness Trends (Smart Neckband sensor simulation)
-- ============================================

CREATE TABLE IF NOT EXISTS elder_wellness_trends (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    elder_id              uuid REFERENCES elder_profiles(id) ON DELETE CASCADE,
    recorded_date         date NOT NULL,
    steps                 int DEFAULT 0,
    speaking_duration_min float8 DEFAULT 0.0,
    hand_activity_score   float8 DEFAULT 100.0,
    care_priority_score   int DEFAULT 100,
    created_at            timestamptz DEFAULT now()
);

-- Index for querying wellness history in order
CREATE INDEX IF NOT EXISTS idx_wellness_elder_date ON elder_wellness_trends (elder_id, recorded_date DESC);


-- ============================================
-- 7. Family Profiles (mapping family members to elders)
-- ============================================

CREATE TABLE IF NOT EXISTS family_profiles (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       uuid REFERENCES users(id) ON DELETE CASCADE UNIQUE,
    elder_id      uuid REFERENCES elder_profiles(id) ON DELETE CASCADE,
    relationship  text NOT NULL,
    created_at    timestamptz DEFAULT now()
);

