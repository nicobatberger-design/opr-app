# OPR · Réserves

Application web **hors ligne** pour relever les réserves d'un chantier directement sur le plan, puis éditer le
**procès-verbal d'OPR** (opérations préalables à la réception).

👉 **Essayer :** https://nicobatberger-design.github.io/opr-app/ (s'installe sur le téléphone comme une application)

## Ce qu'elle fait

- **Plans annotés** : on importe le plan (photo ou image), on touche l'endroit, la réserve s'y épingle.
- **Réserves qualifiées** : gravité bloquante, majeure ou mineure ; suivi des réserves levées ; filtres.
- **Photos de terrain** prises avec l'appareil du téléphone, compressées pour rester légères.
- **Procès-verbal** généré à partir des réserves, à imprimer ou enregistrer en PDF.
- **Sauvegarde et transfert** d'un chantier complet en fichier JSON.

## Choix techniques

- **Aucun serveur, aucun compte** : tout reste dans le navigateur (IndexedDB). Rien ne part sur Internet.
- **Fonctionne sans réseau** (service worker), ce qui compte au fond d'un sous-sol ou d'un bâtiment en travaux.
- Un seul fichier HTML/JavaScript, sans dépendance.

## Comment elle a été faite

Conçue à partir d'un besoin de terrain du bâtiment, puis écrite avec une IA (Claude Code). Le code est généré ; la
conception et les règles métier sont humaines.
