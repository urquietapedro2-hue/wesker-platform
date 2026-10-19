-- WESKER v1.3.0: endurecimiento de seguridad (recomendado). Ejecutar UNA vez en Supabase > SQL Editor.
-- No crea tablas nuevas: el RLS de todas las existentes sigue habilitado y estas funciones mantienen su ejecución restringida.

-- 1) Los usuarios nuevos nacen INACTIVOS: no entran hasta que un Admin ponga activo = true en la tabla profiles.
--    (Si el registro público estuviera abierto por error, un desconocido no podría ver nada.)
--    Los usuarios que ya existen NO cambian.
alter table public.profiles alter column activo set default false;

-- 2) Límite al registro público de intentos fallidos: como máximo 30 por minuto en total,
--    para que nadie pueda llenar la bitácora de basura. El resto se descarta sin error.
create index if not exists audit_log_action_ts on public.audit_log (action, ts);

create or replace function public.log_failed_login(p_email text) returns void
language sql security definer set search_path = public as $$
  insert into audit_log (user_id, email, action)
  select null, left(p_email, 200), 'LOGIN_FAILED'
  where (select count(*) from audit_log where action = 'LOGIN_FAILED' and ts > now() - interval '1 minute') < 30;
$$;

-- Para activar a un usuario nuevo (después de crearlo en Authentication > Users):
-- update public.profiles set activo = true, role = 'OPERATOR', nombre = 'Nombre' where email = 'correo@ejemplo.com';
