-- KLOCK — Corrections de pointage + audit log
--
-- Une correction ne doit jamais écraser silencieusement l'historique: la
-- valeur précédente, la nouvelle valeur, l'auteur et le motif sont toujours
-- journalisés (table `time_entry_corrections`), et l'opération elle-même
-- est tracée dans `audit_logs`. Les trois écritures (mise à jour du
-- pointage, ligne de correction, ligne d'audit) doivent réussir ou échouer
-- ensemble: elles sont donc regroupées dans une seule fonction Postgres,
-- comme `create_company_with_admin`.
--
-- Réservée au service_role: l'autorisation (qui a le droit de corriger)
-- est vérifiée côté application avant l'appel, pas ici.

create or replace function correct_time_entry(
  p_time_entry_id uuid,
  p_company_id uuid,
  p_new_occurred_at timestamptz,
  p_reason text,
  p_corrected_by uuid
)
returns table (correction_id uuid)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_previous timestamptz;
  v_correction_id uuid;
begin
  select occurred_at into v_previous
  from time_entries
  where id = p_time_entry_id and company_id = p_company_id
  for update;

  if v_previous is null then
    raise exception 'time_entry_not_found';
  end if;

  update time_entries
    set occurred_at = p_new_occurred_at
    where id = p_time_entry_id and company_id = p_company_id;

  insert into time_entry_corrections (
    company_id, time_entry_id, previous_occurred_at, new_occurred_at, reason, corrected_by
  ) values (
    p_company_id, p_time_entry_id, v_previous, p_new_occurred_at, p_reason, p_corrected_by
  )
  returning id into v_correction_id;

  insert into audit_logs (company_id, actor_user_id, action, entity_type, entity_id, metadata)
  values (
    p_company_id,
    p_corrected_by,
    'TIME_ENTRY_CORRECTED',
    'time_entry',
    p_time_entry_id,
    jsonb_build_object(
      'previous_occurred_at', v_previous,
      'new_occurred_at', p_new_occurred_at,
      'reason', p_reason
    )
  );

  return query select v_correction_id;
end;
$$;

revoke all on function correct_time_entry(uuid, uuid, timestamptz, text, uuid) from public;
grant execute on function correct_time_entry(uuid, uuid, timestamptz, text, uuid) to service_role;
