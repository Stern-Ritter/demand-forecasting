-- Seed roles
-- roles.name is a SQLAlchemy Enum(RoleName). SQLAlchemy stores enum MEMBER NAMES
-- (USER/ADMIN) by default, so these labels must be upper-case to match the type.
-- (seed.py splits the file naively on the statement terminator, so keep
--  comments free of that character.)
INSERT INTO roles (id, name, created_at, updated_at)
VALUES
  (1, 'USER',  NOW(), NOW()),
  (2, 'ADMIN', NOW(), NOW())
ON CONFLICT DO NOTHING;

-- Seed demo user  (password: demo1234)
-- hash generated with bcrypt rounds=12
INSERT INTO users (id, login, email, display_name, password_hash, is_active, role_id, created_at, updated_at)
VALUES (
  1,
  'demo',
  'demo@example.com',
  'Demo User',
  '$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW',
  true,
  1,
  NOW(),
  NOW()
)
ON CONFLICT DO NOTHING;

-- Balance for demo user (1000 credits)
INSERT INTO balances (id, value, currency, user_id, created_at, updated_at)
VALUES (1, 1000.0, 'RUB', 1, NOW(), NOW())
ON CONFLICT DO NOTHING;
