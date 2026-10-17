-- WESKER: esquema inicial. Pégalo en Supabase > SQL Editor y ejecútalo una vez.
-- Principio: el cliente NUNCA escribe quién es ni cuándo; lo decide el servidor (auth.uid(), now()).

create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text not null,
  nombre text not null default '',
  role text not null default 'VIEWER' check (role in ('ADMIN','OPERATOR','MAINTENANCE','VIEWER')),
  activo boolean not null default true,
  created_at timestamptz not null default now()
);

create table public.presence (
  user_id uuid not null references auth.users(id) on delete cascade,
  client text not null check (client in ('desktop','web')),
  version text not null default '',
  last_seen timestamptz not null default now(),
  primary key (user_id, client)
);

create table public.audit_log (
  id bigint generated always as identity primary key,
  ts timestamptz not null default now(),
  user_id uuid,
  email text,
  action text not null,
  detail jsonb not null default '{}'
);

create table public.app_settings (key text primary key, value text not null);
insert into public.app_settings values ('min_version', '0.1.0');

create or replace function public.is_admin() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from profiles where id = auth.uid() and role = 'ADMIN' and activo);
$$;

create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  insert into profiles (id, email, nombre)
  values (new.id, new.email, coalesce(new.raw_user_meta_data->>'nombre', split_part(new.email, '@', 1)));
  return new;
end $$;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();

-- Seguridad por filas: sin política = nadie accede por la API directa.
alter table public.profiles enable row level security;
alter table public.presence enable row level security;
alter table public.audit_log enable row level security;
alter table public.app_settings enable row level security;

create policy profiles_read on public.profiles for select to authenticated using (id = auth.uid() or is_admin());
create policy profiles_admin_update on public.profiles for update to authenticated using (is_admin()) with check (is_admin());
create policy audit_admin_read on public.audit_log for select to authenticated using (is_admin());
create policy settings_read on public.app_settings for select to authenticated using (true);
create policy settings_admin_write on public.app_settings for all to authenticated using (is_admin()) with check (is_admin());
-- audit_log no tiene política de insert/update/delete: solo se escribe con log_event() y no se puede alterar.

create or replace function public.log_event(p_action text, p_detail jsonb default '{}') returns void
language sql security definer set search_path = public as $$
  insert into audit_log (user_id, email, action, detail)
  select id, email, left(p_action, 60), coalesce(p_detail, '{}') from profiles where id = auth.uid() and activo;
$$;

create or replace function public.log_failed_login(p_email text) returns void
language sql security definer set search_path = public as $$
  insert into audit_log (user_id, email, action) values (null, left(p_email, 200), 'LOGIN_FAILED');
$$;

create or replace function public.heartbeat(p_client text, p_version text) returns void
language sql security definer set search_path = public as $$
  insert into presence (user_id, client, version, last_seen)
  select auth.uid(), p_client, left(p_version, 20), now()
  where exists (select 1 from profiles where id = auth.uid() and activo)
  on conflict (user_id, client) do update set version = excluded.version, last_seen = now();
$$;

create or replace function public.leave_presence(p_client text) returns void
language sql security definer set search_path = public as $$
  delete from presence where user_id = auth.uid() and client = p_client;
$$;

create or replace function public.online_users()
returns table (nombre text, role text, client text, version text, last_seen timestamptz)
language sql stable security definer set search_path = public as $$
  select p.nombre, p.role, pr.client, pr.version, pr.last_seen
  from presence pr join profiles p on p.id = pr.user_id
  where pr.last_seen > now() - interval '45 seconds'
    and exists (select 1 from profiles where id = auth.uid() and activo)
  order by p.nombre;
$$;

revoke execute on function public.log_event, public.heartbeat, public.leave_presence, public.online_users,
  public.log_failed_login from public, anon;
grant execute on function public.log_event, public.heartbeat, public.leave_presence, public.online_users to authenticated;
grant execute on function public.log_failed_login to anon, authenticated;

-- Después de crear tu usuario en Authentication > Users, hazte administrador:
-- update public.profiles set role = 'ADMIN', nombre = 'Pedro' where email = 'tu_correo@ejemplo.com';
