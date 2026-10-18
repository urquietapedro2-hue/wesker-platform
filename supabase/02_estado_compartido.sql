-- WESKER v1.2.0: estado compartido de los gemelos.
-- Ejecútalo UNA vez en Supabase > SQL Editor, DESPUÉS de schema.sql y ANTES de publicar la v1.2.0.
-- Regla: una sola persona publica cada nodo; las demás lo ven. El servidor decide quién y cuándo.

create table if not exists public.node_state (
  node_id text primary key check (node_id in ('ALBERT-01', 'ZENO-01')),
  state jsonb not null default '{}',
  publisher uuid references auth.users(id) on delete set null,
  publisher_name text,
  version bigint not null default 0,
  updated_at timestamptz not null default now()
);
insert into public.node_state (node_id) values ('ALBERT-01'), ('ZENO-01') on conflict do nothing;

alter table public.node_state enable row level security;  -- sin políticas: solo se usa mediante las funciones

-- Publicar: exige rol de control. Si otra persona publicó en los últimos 10 s, responde OCUPADO:nombre.
create or replace function public.publish_state(p_node text, p_state jsonb, p_force boolean default false)
returns bigint language plpgsql security definer set search_path = public as $$
declare me profiles%rowtype; cur node_state%rowtype; nueva bigint;
begin
  select * into me from profiles where id = auth.uid() and activo;
  if not found or me.role not in ('ADMIN', 'OPERATOR', 'MAINTENANCE') then raise exception 'SIN_PERMISO'; end if;
  if length(p_state::text) > 12000 then raise exception 'ESTADO_GRANDE'; end if;
  select * into cur from node_state where node_id = p_node for update;
  if not found then raise exception 'NODO_DESCONOCIDO'; end if;
  if cur.publisher is not null and cur.publisher <> me.id and cur.updated_at > now() - interval '10 seconds'
     and not (p_force and me.role = 'ADMIN') then
    raise exception 'OCUPADO:%', coalesce(cur.publisher_name, '?');
  end if;
  update node_state
     set state = p_state, publisher = me.id, publisher_name = coalesce(nullif(me.nombre, ''), me.email),
         version = version + 1, updated_at = now()
   where node_id = p_node returning version into nueva;
  return nueva;
end $$;

-- Dejar de publicar (solo suelta el nodo quien lo tiene).
create or replace function public.release_node(p_node text) returns void
language sql security definer set search_path = public as $$
  update node_state set publisher = null where node_id = p_node and publisher = auth.uid();
$$;

-- Leer: devuelve los dos nodos; el estado completo solo si cambió desde la versión que el cliente ya tiene.
-- publisher_name viene vacío si nadie publicó en los últimos 10 s (= sin señal).
create or replace function public.get_states(p_known jsonb default '{}')
returns table (node_id text, version bigint, publisher_name text, changed boolean, state jsonb)
language sql stable security definer set search_path = public as $$
  select s.node_id, s.version,
         case when s.publisher is not null and s.updated_at > now() - interval '10 seconds' then s.publisher_name end,
         s.version is distinct from (p_known ->> s.node_id)::bigint,
         case when s.version is distinct from (p_known ->> s.node_id)::bigint then s.state end
  from node_state s
  where exists (select 1 from profiles where id = auth.uid() and activo);
$$;

revoke execute on function public.publish_state, public.release_node, public.get_states from public, anon;
grant execute on function public.publish_state, public.release_node, public.get_states to authenticated;
