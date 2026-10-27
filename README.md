# OPR Chantier — suivi de chantier & réserves

Application **hors ligne**, installable sur le **PC** (Edge, Chrome) comme sur le **téléphone** (iPhone, Android), pour
suivre un chantier visite après visite puis mener les **OPR** (opérations préalables à la réception).

👉 **Ouvrir / installer :** https://nicobatberger-design.github.io/opr-app/

- **Sur PC** : ouvrir le lien dans Edge → menu ⋯ → *Applications* → *Installer ce site en tant qu'application*
  (ou le bouton « Installer » de l'accueil). Aucun droit administrateur, aucun programme à télécharger.
- **Sur iPhone** : ouvrir le lien dans Safari → *Partager* → *Sur l'écran d'accueil*.

## Ce qu'elle fait

- **Plusieurs chantiers**, chacun avec ses infos (adresse, MOA, MOE, entreprises).
- **Suivi de chantier** : visites numérotées (date, météo, effectifs, présents, avancement), points à suivre
  (à faire, qualité, sécurité, info), priorité, échéance, entreprise concernée, photos ; un point reste ouvert d'une
  visite à l'autre jusqu'à ce qu'il soit soldé, les échéances dépassées ressortent en rouge.
- **Compte rendu de visite** en PDF : points ouverts regroupés par entreprise, points soldés, plans annotés, diffusion.
- **OPR** : réserves qualifiées (mineure, majeure, bloquante), levée des réserves, **procès-verbal** en PDF.
  Un point de suivi peut être reporté en réserve d'un geste.
- **Plans annotés** : import d'un plan PDF (une ou plusieurs pages), d'une photo ou d'une capture ; on touche (ou on
  clique) l'endroit, le point s'y épingle. Zoom au doigt ou à la molette.
- **Transfert** d'un chantier entre le téléphone et le PC par fichier, sauvegarde complète, export Excel (CSV).

## Choix techniques

- **Aucun serveur, aucun compte** : tout reste sur l'appareil (IndexedDB). Rien ne part sur Internet.
- **Fonctionne sans réseau** (service worker), ce qui compte au fond d'un sous-sol ou d'un bâtiment en travaux.
- Un fichier HTML/JavaScript ; seule bibliothèque : [pdf.js](https://mozilla.github.io/pdf.js/) (Apache 2.0) dans
  `lib/`, chargée uniquement pour importer un plan PDF.
- Les fichiers importés sont traités comme non fiables (textes échappés, images vérifiées).
- Icônes rendues depuis `icons/icon.svg` par `outils/generer-icones.py`.

## Comment elle a été faite

Conçue à partir d'un besoin de terrain du bâtiment, puis écrite avec une IA (Claude Code). Le code est généré ; la
conception et les règles métier sont humaines.
