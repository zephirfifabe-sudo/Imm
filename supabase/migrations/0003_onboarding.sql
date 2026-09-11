-- KLOCK — Onboarding
--
-- La création d'une entreprise et de son premier utilisateur ADMIN doit être
-- atomique: soit les deux lignes existent, soit aucune. Comme aucune ligne
-- `users` n'existe encore au moment de la création, les policies RLS
-- classiques (qui dérivent company_id de la session) ne peuvent pas
-- s'appliquer ici — cette fonction s'exécute donc en security definer et
-- n'est exécutable que par service_role (jamais par anon/authenticated).

create or replace function create_company_with_admin(
  p_auth_user_id uuid,
  p_email text,
  p_company_name text,
  p_first_name text,
  p_last_name text
)
returns table (company_id uuid, user_id uuid)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_company_id uuid;
  v_user_id uuid;
begin
  insert into companies (name) values (p_company_name)
    returning id into v_company_id;

  insert into users (auth_user_id, company_id, email, first_name, last_name, role)
    values (p_auth_user_id, v_company_id, p_email, p_first_name, p_last_name, 'ADMIN')
    returning id into v_user_id;

  return query select v_company_id, v_user_id;
end;
$$;

revoke all on function create_company_with_admin(uuid, text, text, text, text) from public;
grant execute on function create_company_with_admin(uuid, text, text, text, text) to service_role;
