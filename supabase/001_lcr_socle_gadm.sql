-- ============================================================
-- Migration 001 — lcr.zoomali.io — SOCLE MULTI-SOCIÉTÉ + PARAMÉTRAGE GADM
-- À exécuter dans Supabase (instance mutualisée VPS OVH, schema public).
--
-- Objet : passer de « relevé LCR → Excel de synthèse » à
--         « relevé LCR → écriture comptable JoGADM » :
--         1 PDF = 1 écriture = N lignes 401 (une par tireur) + 1 ligne 512.
--
-- Le mapping « Nom du Tireur » → compte 401 est une CONNAISSANCE MÉTIER : elle vit
-- en base, éditable dans l'app, jamais en dur dans le code (DAAT, pilier Apprenant).
--
-- Sécurité : la RLS est la barrière réelle (règle 13). Accès par APPARTENANCE au
-- service (user_services × services.url), jamais d'attribution en dur ici.
-- ============================================================

-- ───────────────────────── Sociétés ─────────────────────────
create table if not exists lcr_societes (
  id            uuid primary key default gen_random_uuid(),
  nom           text not null,
  -- Contrepartie unique de l'écriture : le compte banque (512…) crédité du total
  pcg_512       char(8) not null,
  -- Journal GADM (varie par société : Chabrières = 12 chez LAMPROIE/BAKITO, 15 chez COUSTUT)
  code_journal  text not null default '12',
  -- Codes du paramétrage GADM (table gadm_bm_codes) : DI = divers/OD, CA = LCR/traite
  nature        text not null default 'DI',
  reglement     text not null default 'CA',
  actif         boolean not null default true,
  created_at    timestamptz default now(),
  unique (nom)
);

-- ───────────────────────── Tireurs → compte fournisseur ─────────────────────
-- `tireur` = le « Nom du Tireur » tel qu'il sort du relevé, normalisé (majuscules,
-- espaces compactés) pour que le rapprochement soit déterministe.
create table if not exists lcr_tireurs (
  id          uuid primary key default gen_random_uuid(),
  societe_id  uuid not null references lcr_societes(id) on delete cascade,
  tireur      text not null,
  pcg_401     char(8) not null,
  created_at  timestamptz default now(),
  unique (societe_id, tireur)
);
create index if not exists lcr_tireurs_societe_idx on lcr_tireurs(societe_id);

-- ───────────────────────── RLS par appartenance au service ──────────────────
create or replace function public.lcr_has_access()
returns boolean language sql stable security definer set search_path = public
as $$
  select exists (
    select 1
    from user_services us
    join services s on s.id = us.service_id
    where us.user_id = auth.uid()
      and s.url in ('https://lcr.zoomali.io', 'https://lcr.zoomali.io/')
  );
$$;
grant execute on function public.lcr_has_access() to authenticated;

alter table lcr_societes enable row level security;
alter table lcr_tireurs  enable row level security;

drop policy if exists lcr_societes_acces on lcr_societes;
create policy lcr_societes_acces on lcr_societes
  for all to authenticated
  using (public.lcr_has_access()) with check (public.lcr_has_access());

drop policy if exists lcr_tireurs_acces on lcr_tireurs;
create policy lcr_tireurs_acces on lcr_tireurs
  for all to authenticated
  using (public.lcr_has_access()) with check (public.lcr_has_access());

-- ───────────────────────── Seed des sociétés à relevés LCR ──────────────────
-- Banque Chabrières uniquement (seule à émettre ces relevés). Comptes et journaux
-- repris du paramétrage GADM réel (identiques à 5115.zoomali.io).
insert into lcr_societes (nom, pcg_512, code_journal) values
  ('LAMPROIE', '51210004', '12'),
  ('BAKITO',   '51210004', '12'),
  ('COUSTUT',  '51210003', '15')
on conflict (nom) do nothing;
