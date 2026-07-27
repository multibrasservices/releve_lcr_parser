-- ============================================================
-- Migration 002 — lcr.zoomali.io — PARAMÈTRES RÉSERVÉS AUX ADMINS
-- Le compte 512 et le journal d'une société pilotent l'import GADM : une erreur
-- ici bloque l'import pour tout le monde. Lecture ouverte à tous les utilisateurs
-- du service, ÉCRITURE réservée à super_admin / user_admin (rôle porté par
-- user_services.role, comme gadm_is_super_admin sur gadm.zoomali.io).
-- ============================================================

create or replace function public.lcr_is_admin()
returns boolean language sql stable security definer set search_path = public
as $$
  select exists (
    select 1
    from user_services us
    join services s on s.id = us.service_id
    where us.user_id = auth.uid()
      and us.role in ('super_admin', 'user_admin')
      and s.url in ('https://lcr.zoomali.io', 'https://lcr.zoomali.io/')
  );
$$;
grant execute on function public.lcr_is_admin() to authenticated;

-- Sociétés : tout le monde lit, seuls les admins écrivent
drop policy if exists lcr_societes_acces on lcr_societes;

create policy lcr_societes_lecture on lcr_societes
  for select to authenticated
  using (public.lcr_has_access());

create policy lcr_societes_ecriture on lcr_societes
  for all to authenticated
  using (public.lcr_is_admin()) with check (public.lcr_is_admin());

-- Les tireurs (mapping 401) restent éditables par tout utilisateur du service :
-- c'est le geste quotidien de comptabilisation, pas un réglage structurant.
