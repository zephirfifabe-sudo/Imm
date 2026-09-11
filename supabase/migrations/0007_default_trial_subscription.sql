-- KLOCK — Abonnement d'essai par défaut
--
-- Le parcours d'onboarding ("je crée mon compte → j'ajoute mes employés")
-- doit fonctionner avant tout paiement. On rattache donc chaque nouvelle
-- entreprise au plan STARTER en statut 'trialing' dès sa création: cela
-- donne une limite d'employés cohérente dès le premier jour, que
-- l'entreprise choisisse ensuite de payer (Stripe Checkout) ou reste sur
-- l'essai. Remplace `create_company_with_admin` (même signature).

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
  v_starter_plan_id uuid;
begin
  insert into companies (name) values (p_company_name)
    returning id into v_company_id;

  insert into users (auth_user_id, company_id, email, first_name, last_name, role)
    values (p_auth_user_id, v_company_id, p_email, p_first_name, p_last_name, 'ADMIN')
    returning id into v_user_id;

  select id into v_starter_plan_id from plans where code = 'STARTER' limit 1;

  if v_starter_plan_id is not null then
    insert into subscriptions (company_id, plan_id, status)
      values (v_company_id, v_starter_plan_id, 'trialing');
  end if;

  return query select v_company_id, v_user_id;
end;
$$;

revoke all on function create_company_with_admin(uuid, text, text, text, text) from public;
grant execute on function create_company_with_admin(uuid, text, text, text, text) to service_role;
