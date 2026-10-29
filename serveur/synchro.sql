-- ==================================================================
-- OPR Chantier — relais de synchronisation (Supabase / PostgreSQL), v2
-- Chiffré de bout en bout : le serveur ne reçoit que du chiffré
-- (chantiers et images sont chiffrés sur l'appareil, AES-GCM).
-- L'accès passe uniquement par les fonctions opr_* : le schéma opr
-- n'est pas exposé par l'API et la clé publique n'y a aucun droit.
-- Les photos s'effacent du serveur 60 jours après leur envoi (elles
-- restent sur les appareils) ; les plans sont gardés.
-- Script complet et rejouable : à exécuter dans l'éditeur SQL du projet.
-- ==================================================================
create schema if not exists opr;

create table if not exists opr.espaces (
  espace text primary key,                 -- sha256 de la clé d'accès dérivée du code de synchro
  cree timestamptz not null default now(),
  vu timestamptz not null default now()
);
alter table opr.espaces add column if not exists octets bigint not null default 0;   -- place occupée par l'espace
create table if not exists opr.docs (
  espace text not null references opr.espaces(espace) on delete cascade,
  id text not null,
  rev bigint not null,
  data text,                               -- chantier chiffré (base64), null si supprimé
  supprime boolean not null default false,
  maj timestamptz not null default now(),
  primary key (espace, id)
);
create index if not exists docs_espace_rev on opr.docs (espace, rev);
create table if not exists opr.images (
  espace text not null references opr.espaces(espace) on delete cascade,
  h text not null,                         -- empreinte HMAC de l'image (calculée sur l'appareil)
  data bytea not null,                     -- image chiffrée
  cree timestamptz not null default now(),
  primary key (espace, h)
);
alter table opr.images add column if not exists photo boolean not null default true;   -- false = plan (jamais effacé)
create index if not exists images_photo_cree on opr.images (espace, cree) where photo;
create table if not exists opr.expirees (  -- photos effacées après 60 jours : à ne pas redemander ni renvoyer
  espace text not null references opr.espaces(espace) on delete cascade,
  h text not null,
  expire timestamptz not null default now(),
  primary key (espace, h)
);
create sequence if not exists opr.rev_seq;
alter table opr.espaces enable row level security;
alter table opr.docs enable row level security;
alter table opr.images enable row level security;
alter table opr.expirees enable row level security;

drop function if exists public.opr_images_garder(text, text[]);
drop function if exists public.opr_image_poser(text, text, text);

create or replace function opr.espace_de(p_cle text) returns text
language sql stable set search_path = '' as $$
  select e.espace from opr.espaces e
  where p_cle ~ '^[0-9a-f]{64}$' and e.espace = encode(sha256(convert_to(p_cle,'UTF8')),'hex')
$$;

-- Quota : le premier espace créé (celui de Nico) a presque toute la place ; un autre espace (essais) 25 Mo.
create or replace function opr.quota(p_esp text) returns bigint
language sql stable set search_path = '' as $$
  select case when p_esp = (select e.espace from opr.espaces e order by e.cree, e.espace limit 1)
    then 400::bigint * 1024 * 1024 else 25::bigint * 1024 * 1024 end
$$;
create or replace function opr.place(p_esp text, p_ajout bigint) returns boolean
language sql stable set search_path = '' as $$
  select p_ajout <= 0 or (
    (select e.octets from opr.espaces e where e.espace = p_esp) + p_ajout <= opr.quota(p_esp)
    and pg_database_size(current_database()) + p_ajout <= 470::bigint * 1024 * 1024)
$$;

-- Ouvre (ou crée, 3 espaces au plus) l'espace correspondant à la clé d'accès.
create or replace function public.opr_ouvrir(p_cle text, p_creer boolean) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare v_esp text; v_n int;
begin
  if p_cle is null or p_cle !~ '^[0-9a-f]{64}$' then return jsonb_build_object('ok',false,'erreur','cle'); end if;
  v_esp := encode(sha256(convert_to(p_cle,'UTF8')),'hex');
  update opr.espaces set vu = now() where espace = v_esp;
  if found then return jsonb_build_object('ok',true); end if;
  if not coalesce(p_creer,false) then return jsonb_build_object('ok',false,'erreur','inconnu'); end if;
  perform pg_advisory_xact_lock(424242);
  select count(*) into v_n from opr.espaces;
  if v_n >= 3 then return jsonb_build_object('ok',false,'erreur','limite'); end if;
  insert into opr.espaces(espace) values (v_esp) on conflict do nothing;
  return jsonb_build_object('ok',true,'cree',true);
end $$;

-- Chantiers modifiés depuis la révision p_depuis ; efface au passage les photos de plus de 60 jours.
create or replace function public.opr_tirer(p_cle text, p_depuis bigint) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare v_esp text := opr.espace_de(p_cle); v_oct bigint;
begin
  if v_esp is null then return jsonb_build_object('ok',false,'erreur','inconnu'); end if;
  update opr.espaces set vu = now() where espace = v_esp and vu < now() - interval '1 hour';
  with x as (
      delete from opr.images i where i.espace = v_esp and i.photo and i.cree < now() - interval '60 days'
      returning i.h, octet_length(i.data) as n),
    t as (insert into opr.expirees(espace,h) select v_esp, x.h from x on conflict do nothing)
  select coalesce(sum(x.n),0) into v_oct from x;
  if v_oct > 0 then update opr.espaces set octets = greatest(0, octets - v_oct) where espace = v_esp; end if;
  return jsonb_build_object('ok',true,'docs', coalesce((
    select jsonb_agg(jsonb_build_object('id',d.id,'rev',d.rev,'data',d.data,'supprime',d.supprime) order by d.rev)
    from opr.docs d where d.espace = v_esp and d.rev > coalesce(p_depuis,0)), '[]'::jsonb));
end $$;

-- Envoi d'un chantier ; refusé (conflit) si un autre appareil l'a modifié depuis p_base.
-- Une écriture à la fois par espace : les révisions deviennent visibles dans l'ordre (aucune n'est sautée au tirage).
create or replace function public.opr_pousser(p_cle text, p_id text, p_base bigint, p_data text, p_supprime boolean) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
  v_esp text := opr.espace_de(p_cle);
  v_sup boolean := coalesce(p_supprime,false);
  v_len bigint := case when coalesce(p_supprime,false) then 0 else coalesce(length(p_data),0) end;
  v_rev bigint; v_old bigint; v_new bigint;
begin
  if v_esp is null then return jsonb_build_object('ok',false,'erreur','inconnu'); end if;
  if p_id is null or p_id !~ '^[A-Za-z0-9_-]{1,64}$' then return jsonb_build_object('ok',false,'erreur','id'); end if;
  if not v_sup and (p_data is null or v_len > 6000000) then return jsonb_build_object('ok',false,'erreur','taille'); end if;
  perform pg_advisory_xact_lock(hashtext('opr:' || v_esp));
  select d.rev, coalesce(length(d.data),0) into v_rev, v_old from opr.docs d where d.espace = v_esp and d.id = p_id;
  if v_rev is not null and v_rev <> coalesce(p_base,0) then
    return jsonb_build_object('ok',false,'conflit',true,'rev',v_rev);
  end if;
  v_old := coalesce(v_old,0);
  if not opr.place(v_esp, v_len - v_old) then return jsonb_build_object('ok',false,'erreur','plein'); end if;
  v_new := nextval('opr.rev_seq');
  insert into opr.docs(espace,id,rev,data,supprime,maj)
    values (v_esp, p_id, v_new, case when v_sup then null else p_data end, v_sup, now())
    on conflict (espace,id) do update set rev = excluded.rev, data = excluded.data, supprime = excluded.supprime, maj = excluded.maj;
  update opr.espaces set octets = greatest(0, octets + v_len - v_old) where espace = v_esp;
  return jsonb_build_object('ok',true,'rev',v_new);
end $$;

-- Images à envoyer : ni présentes, ni déjà effacées après 60 jours.
create or replace function public.opr_images_manquantes(p_cle text, p_h text[]) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare v_esp text := opr.espace_de(p_cle);
begin
  if v_esp is null then return jsonb_build_object('ok',false,'erreur','inconnu'); end if;
  if coalesce(cardinality(p_h),0) > 500 then return jsonb_build_object('ok',false,'erreur','taille'); end if;
  return jsonb_build_object('ok',true,'manquantes', coalesce((
    select jsonb_agg(x.h) from unnest(p_h) as x(h)
    where not exists (select 1 from opr.images i where i.espace = v_esp and i.h = x.h)
      and not exists (select 1 from opr.expirees e where e.espace = v_esp and e.h = x.h)), '[]'::jsonb));
end $$;

-- Dépôt d'une image chiffrée (p_plan = plan, jamais effacé), dans la limite du quota.
create or replace function public.opr_image_poser(p_cle text, p_h text, p_data text, p_plan boolean default false) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare v_esp text := opr.espace_de(p_cle); v_bin bytea; v_n int;
begin
  if v_esp is null then return jsonb_build_object('ok',false,'erreur','inconnu'); end if;
  if p_h is null or p_h !~ '^[0-9a-f]{32}$' then return jsonb_build_object('ok',false,'erreur','id'); end if;
  if p_data is null or length(p_data) > 12000000 then return jsonb_build_object('ok',false,'erreur','taille'); end if;
  if exists (select 1 from opr.images i where i.espace = v_esp and i.h = p_h) then return jsonb_build_object('ok',true); end if;
  v_bin := decode(p_data,'base64');
  if not opr.place(v_esp, octet_length(v_bin)) then return jsonb_build_object('ok',false,'erreur','plein'); end if;
  insert into opr.images(espace,h,data,photo) values (v_esp, p_h, v_bin, not coalesce(p_plan,false)) on conflict do nothing;
  get diagnostics v_n = row_count;
  if v_n > 0 then update opr.espaces set octets = octets + octet_length(v_bin) where espace = v_esp; end if;
  return jsonb_build_object('ok',true);
end $$;

create or replace function public.opr_images_lire(p_cle text, p_h text[]) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare v_esp text := opr.espace_de(p_cle);
begin
  if v_esp is null then return jsonb_build_object('ok',false,'erreur','inconnu'); end if;
  return jsonb_build_object('ok',true,'images', coalesce((
    select jsonb_object_agg(i.h, translate(encode(i.data,'base64'), E'\n', ''))
    from opr.images i where i.espace = v_esp and i.h = any(p_h[1:10])), '{}'::jsonb));
end $$;

create or replace function public.opr_etat(p_cle text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare v_esp text := opr.espace_de(p_cle);
begin
  if v_esp is null then return jsonb_build_object('ok',false,'erreur','inconnu'); end if;
  return jsonb_build_object('ok',true,
    'chantiers', (select count(*) from opr.docs d where d.espace = v_esp and not d.supprime),
    'photos', (select count(*) from opr.images i where i.espace = v_esp and i.photo),
    'plans', (select count(*) from opr.images i where i.espace = v_esp and not i.photo),
    'octets', (select e.octets from opr.espaces e where e.espace = v_esp),
    'quota', opr.quota(v_esp),
    'base', pg_database_size(current_database()));
end $$;

-- Efface l'espace et tout son contenu (bouton « Arrêter la synchronisation » de l'appli).
create or replace function public.opr_effacer(p_cle text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare v_esp text := opr.espace_de(p_cle);
begin
  if v_esp is null then return jsonb_build_object('ok',false,'erreur','inconnu'); end if;
  delete from opr.espaces where espace = v_esp;
  return jsonb_build_object('ok',true);
end $$;

update opr.espaces e set octets =
  coalesce((select sum(octet_length(i.data)) from opr.images i where i.espace = e.espace),0)
  + coalesce((select sum(length(d.data)) from opr.docs d where d.espace = e.espace),0);

grant execute on function public.opr_ouvrir(text,boolean) to anon, authenticated;
grant execute on function public.opr_tirer(text,bigint) to anon, authenticated;
grant execute on function public.opr_pousser(text,text,bigint,text,boolean) to anon, authenticated;
grant execute on function public.opr_images_manquantes(text,text[]) to anon, authenticated;
grant execute on function public.opr_image_poser(text,text,text,boolean) to anon, authenticated;
grant execute on function public.opr_images_lire(text,text[]) to anon, authenticated;
grant execute on function public.opr_etat(text) to anon, authenticated;
grant execute on function public.opr_effacer(text) to anon, authenticated;

select 'OPR Chantier : synchro v2 installée ✓' as resultat;
