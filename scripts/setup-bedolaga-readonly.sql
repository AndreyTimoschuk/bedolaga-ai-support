-- Run this on the Bedolaga / Remnawave bot Postgres as a superuser or table owner.
-- Creates a read-only role for n8n and compatibility views for support cards.
--
-- Replace CHANGE_ME_PASSWORD before running.
--
-- Example:
--   docker exec -i remnawave_bot_db psql -U svc_bedolaga_pg -d remnawave_bot < scripts/setup-bedolaga-readonly.sql

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'n8n_readonly') THEN
    CREATE ROLE n8n_readonly LOGIN PASSWORD 'CHANGE_ME_PASSWORD';
  ELSE
    ALTER ROLE n8n_readonly WITH LOGIN PASSWORD 'CHANGE_ME_PASSWORD';
  END IF;
END
$$;

ALTER ROLE n8n_readonly SET default_transaction_read_only = on;
GRANT CONNECT ON DATABASE remnawave_bot TO n8n_readonly;
GRANT USAGE ON SCHEMA public TO n8n_readonly;

DROP VIEW IF EXISTS n8n_compat.keys CASCADE;
DROP VIEW IF EXISTS n8n_compat.users CASCADE;
DROP VIEW IF EXISTS public.n8n_keys CASCADE;
DROP VIEW IF EXISTS public.n8n_users CASCADE;

CREATE VIEW public.n8n_users AS
SELECT
  u.id,
  u.telegram_id AS tg_id,
  u.username,
  u.first_name,
  u.last_name,
  u.status,
  u.language,
  u.auth_type,
  u.email,
  u.email_verified,
  round(COALESCE(u.balance_kopeks, 0)::numeric / 100.0, 2) AS balance,
  CASE
    WHEN EXISTS (
      SELECT 1 FROM subscriptions s
      WHERE s.user_id = u.id
        AND COALESCE(s.is_trial, false) = true
        AND s.status::text = ANY (ARRAY['active', 'trial'])
    ) THEN true
    WHEN COALESCE(u.has_had_paid_subscription, false) = false THEN true
    ELSE false
  END AS trial,
  u.has_had_paid_subscription AS had_paid,
  u.has_made_first_topup AS first_topup,
  u.created_at,
  u.updated_at,
  u.last_activity,
  u.cabinet_last_login,
  u.remnawave_uuid,
  u.referral_code,
  u.used_promocodes,
  u.partner_status,
  u.restriction_topup,
  u.restriction_subscription,
  NULLIF(u.restriction_reason::text, '') AS restriction_reason,
  pg.name AS promo_group,
  ref.telegram_id AS referrer_tg_id,
  ref.username AS referrer_username,
  (SELECT count(*)::int FROM users r WHERE r.referred_by_id = u.id) AS referrals_count,
  (SELECT count(*)::int FROM tickets t WHERE t.user_id = u.id AND t.status IN ('open', 'answered')) AS open_tickets,
  (SELECT count(*)::int FROM tickets t WHERE t.user_id = u.id) AS tickets_total,
  round(COALESCE((
    SELECT sum(t.amount_kopeks)::numeric / 100.0
    FROM transactions t
    WHERE t.user_id = u.id AND t.is_completed = true AND t.type = 'deposit'
  ), 0), 2) AS total_deposits,
  (
    SELECT round(t.amount_kopeks::numeric / 100.0, 2)
    FROM transactions t
    WHERE t.user_id = u.id AND t.is_completed = true AND t.type = 'deposit'
    ORDER BY COALESCE(t.completed_at, t.created_at) DESC
    LIMIT 1
  ) AS last_deposit_amount,
  (
    SELECT COALESCE(t.completed_at, t.created_at)
    FROM transactions t
    WHERE t.user_id = u.id AND t.is_completed = true AND t.type = 'deposit'
    ORDER BY COALESCE(t.completed_at, t.created_at) DESC
    LIMIT 1
  ) AS last_deposit_at,
  (
    SELECT t.payment_method
    FROM transactions t
    WHERE t.user_id = u.id AND t.is_completed = true AND t.type = 'deposit'
    ORDER BY COALESCE(t.completed_at, t.created_at) DESC
    LIMIT 1
  ) AS last_deposit_method,
  (
    SELECT t.type
    FROM transactions t
    WHERE t.user_id = u.id AND t.is_completed = true
    ORDER BY COALESCE(t.completed_at, t.created_at) DESC
    LIMIT 1
  ) AS last_tx_type,
  (
    SELECT round(t.amount_kopeks::numeric / 100.0, 2)
    FROM transactions t
    WHERE t.user_id = u.id AND t.is_completed = true
    ORDER BY COALESCE(t.completed_at, t.created_at) DESC
    LIMIT 1
  ) AS last_tx_amount,
  (
    SELECT COALESCE(t.completed_at, t.created_at)
    FROM transactions t
    WHERE t.user_id = u.id AND t.is_completed = true
    ORDER BY COALESCE(t.completed_at, t.created_at) DESC
    LIMIT 1
  ) AS last_tx_at,
  round(COALESCE(u.lifetime_used_traffic_bytes, 0)::numeric / 1073741824, 2) AS lifetime_traffic_gb
FROM users u
LEFT JOIN promo_groups pg ON pg.id = u.promo_group_id
LEFT JOIN users ref ON ref.id = u.referred_by_id;

CREATE VIEW public.n8n_keys AS
SELECT
  s.id,
  u.telegram_id AS tg_id,
  COALESCE(NULLIF(s.remnawave_short_uuid::text, ''), NULLIF(s.remnawave_short_id::text, ''), '-') AS email,
  (EXTRACT(epoch FROM s.end_date) * 1000)::bigint AS expiry_time,
  COALESCE(t.name, s.status, '-') AS server_id,
  s.status,
  s.is_trial,
  s.start_date,
  s.end_date,
  s.subscription_url,
  s.device_limit,
  s.traffic_limit_gb,
  round(COALESCE(s.traffic_used_gb, 0)::numeric, 2) AS traffic_used_gb,
  s.purchased_traffic_gb,
  s.autopay_enabled,
  s.autopay_days_before,
  s.modem_enabled,
  s.is_daily_paused,
  s.remnawave_uuid AS sub_remnawave_uuid,
  s.connected_squads::text AS connected_squads
FROM subscriptions s
JOIN users u ON u.id = s.user_id
LEFT JOIN tariffs t ON t.id = s.tariff_id;

CREATE SCHEMA IF NOT EXISTS n8n_compat;
CREATE VIEW n8n_compat.users AS SELECT * FROM public.n8n_users;
CREATE VIEW n8n_compat.keys AS SELECT * FROM public.n8n_keys;

GRANT USAGE ON SCHEMA n8n_compat TO n8n_readonly;
GRANT SELECT ON public.n8n_users TO n8n_readonly;
GRANT SELECT ON public.n8n_keys TO n8n_readonly;
GRANT SELECT ON n8n_compat.users TO n8n_readonly;
GRANT SELECT ON n8n_compat.keys TO n8n_readonly;
GRANT SELECT ON public.users TO n8n_readonly;
GRANT SELECT ON public.subscriptions TO n8n_readonly;
GRANT SELECT ON public.tariffs TO n8n_readonly;
GRANT SELECT ON public.transactions TO n8n_readonly;
GRANT SELECT ON public.tickets TO n8n_readonly;
GRANT SELECT ON public.promo_groups TO n8n_readonly;

ALTER ROLE n8n_readonly SET search_path = n8n_compat, public;
