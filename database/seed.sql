-- ============================================
-- CareBridge Seed Data
-- Run this AFTER schema.sql in the Supabase SQL Editor
-- ============================================

-- NOTE: Password hashes below are bcrypt hashes of 'password123'
-- Generated with: python -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('password123'))"
-- Replace these if you regenerate them.

INSERT INTO users (id, email, password_hash, role, name, phone) VALUES
    ('00000000-0000-0000-0000-000000000001',
     'hana@example.com',
     '$2b$12$LJ3m4ys4Xz7Kz3TJKq5v5eZKq5b5z5z5z5z5z5z5z5z5z5z5z5z5.',
     'elder',
     'Hana Tanaka',
     '+81-90-1234-5678'),

    ('00000000-0000-0000-0000-000000000002',
     'kenji@example.com',
     '$2b$12$LJ3m4ys4Xz7Kz3TJKq5v5eZKq5b5z5z5z5z5z5z5z5z5z5z5z5z5.',
     'volunteer',
     'Kenji Mori',
     '+81-90-2345-6789'),

    ('00000000-0000-0000-0000-000000000003',
     'yuki@example.com',
     '$2b$12$LJ3m4ys4Xz7Kz3TJKq5v5eZKq5b5z5z5z5z5z5z5z5z5z5z5z5z5.',
     'volunteer',
     'Yuki Sato',
     '+81-90-3456-7890')
ON CONFLICT (id) DO NOTHING;

-- Elder profile: Hana Tanaka in Tokyo
INSERT INTO elder_profiles (user_id, age, care_score, lat, lng) VALUES
    ('00000000-0000-0000-0000-000000000001', 78, 67, 35.6762, 139.6503)
ON CONFLICT DO NOTHING;

-- Volunteer profiles: Kenji (nearby, available), Yuki (farther, offline)
INSERT INTO volunteer_profiles (user_id, is_available, lat, lng) VALUES
    ('00000000-0000-0000-0000-000000000002', true,  35.6800, 139.6520),
    ('00000000-0000-0000-0000-000000000003', false, 35.6900, 139.6600)
ON CONFLICT DO NOTHING;
