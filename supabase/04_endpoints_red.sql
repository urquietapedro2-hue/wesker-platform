-- WESKER v1.5.0: registro de IPs de los nodos (una dirección por red y por nodo). Ejecutar UNA vez en Supabase > SQL Editor.
-- Las IPs viven aquí, no en el código. Leen los roles de control; solo ADMIN escribe; todo cambio queda en la auditoría.
-- RLS habilitado SIN políticas a propósito: la tabla solo se toca mediante las funciones (acceso directo denegado).

create table if not exists public.node_endpoints (
  node_id text not null check (node_id ~ '^[A-Z0-9-]{3,20}$'),
  red text not null check (char_length(red) between 1 and 30),
  ip inet not null check (family(ip) = 4 and masklen(ip) = 32),
  puerto integer not null check (puerto between 1 and 65535),
  updated_at timestamptz not null default now(),
  updated_by uuid references auth.users(id) on delete set null,
  primary key (node_id, red)
);
alter table public.node_endpoints enable row level security;

create or replace function public.list_endpoints()
returns table (node_id text, red text, ip text, puerto integer, updated_at timestamptz)
language sql stable security definer set search_path = public as $$
  select e.node_id, e.red, host(e.ip), e.puerto, e.updated_at
  from node_endpoints e
  where exists (select 1 from profiles where id = auth.uid() and activo and role in ('ADMIN', 'OPERATOR', 'MAINTENANCE'))
  order by e.node_id, e.red;
$$;

create or replace function public.set_endpoint(p_node text, p_red text, p_ip text, p_puerto integer) returns void
language plpgsql security definer set search_path = public as $$
declare dir inet;
begin
  if not exists (select 1 from profiles where id = auth.uid() and activo and role = 'ADMIN') then raise exception 'SIN_PERMISO'; end if;
  dir := p_ip::inet;
  if family(dir) <> 4 or masklen(dir) <> 32 or dir <<= '127.0.0.0/8' or dir <<= '224.0.0.0/4' or dir = '0.0.0.0' then
    raise exception 'IP_NO_VALIDA';
  end if;
  insert into node_endpoints (node_id, red, ip, puerto, updated_by) values (p_node, left(trim(p_red), 30), dir, p_puerto, auth.uid())
  on conflict (node_id, red) do update set ip = excluded.ip, puerto = excluded.puerto, updated_at = now(), updated_by = auth.uid();
  insert into audit_log (user_id, email, action, detail)
  select id, email, 'ENDPOINT_SET', jsonb_build_object('nodo', p_node, 'red', left(trim(p_red), 30), 'ip', host(dir), 'puerto', p_puerto)
  from profiles where id = auth.uid();
end $$;

create or replace function public.delete_endpoint(p_node text, p_red text) returns void
language plpgsql security definer set search_path = public as $$
begin
  if not exists (select 1 from profiles where id = auth.uid() and activo and role = 'ADMIN') then raise exception 'SIN_PERMISO'; end if;
  delete from node_endpoints where node_id = p_node and red = p_red;
  insert into audit_log (user_id, email, action, detail)
  select id, email, 'ENDPOINT_DELETE', jsonb_build_object('nodo', p_node, 'red', p_red) from profiles where id = auth.uid();
end $$;

revoke execute on function public.list_endpoints, public.set_endpoint, public.delete_endpoint from public, anon;
grant execute on function public.list_endpoints, public.set_endpoint, public.delete_endpoint to authenticated;
