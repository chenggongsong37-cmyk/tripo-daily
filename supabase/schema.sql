create table if not exists public.daily_reports (
  report_date date primary key,
  generated_at timestamptz not null default now(),
  markdown text not null,
  html text not null,
  status jsonb not null default '{}'::jsonb,
  items jsonb not null default '[]'::jsonb
);

alter table public.daily_reports enable row level security;
-- Server-side access uses the service_role key, which bypasses RLS.
-- Do not expose SUPABASE_SERVICE_ROLE_KEY in browser code.
