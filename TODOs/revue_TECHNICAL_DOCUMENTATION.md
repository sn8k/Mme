# Revue de `docs/TECHNICAL_DOCUMENTATION.md` (incoherences / risques)

Objectif
- Pointer les incoherences internes du document, les ecarts avec le repo, et les strategies potentiellement risqu?es si on suit la doc a la lettre.

## 1) Incoherences internes au document
- Versions contradictoires:
  - En-tete: "Version : 0.38.0" + "Date : 29 decembre 2025".
  - Footer: "Document genere ... Motion Frontend v0.3.0".
  - Le fichier annonce aussi "File Version: 1.22.0" (encore un autre numero).
  => Risque: impossible de savoir quelle version du produit/de la doc est decrite.

- Prerequis Python incoherents:
  - Section stack: "Python 3.11+".
  - Section update/repair: "Python 3.13+".
  => Risque: confusion sur la cible (et sur Raspberry Pi OS Trixie, la dispo exacte depend du repo Debian).

- Versionnement des fichiers incoherent / obsol?te:
  - Plusieurs numeros de version listes (arborescence + section 10.3) ne correspondent pas entre eux (ex: `main.html`/`main.js` ont plusieurs versions indiquees dans le meme document).
  => Risque: la section "Versions actuelles" n est plus une source fiable.

- i18n annoncee "complete (fr/en/de/es/it)" alors que le repo ne contient que `motion_frontend.fr.json` et `motion_frontend.en.json`.
  => Risque: sur-promesse fonctionnelle / attentes QA faussees.

- Annexes dependances trop reductrices:
  - Annexe A ne liste que tornado/jinja2, alors que `requirements.txt` inclut aussi aiohttp, bcrypt, opencv-python, numpy, etc.
  => Risque: documentation d installation incomplette.

## 2) Ecarts doc <-> implementation (risques de bug si on suit la doc)
- "Page version":
  - La doc decrit `templates/version.html` + `static/js/version.js` comme une page.
  - Dans le routing Tornado, `/version/` est un endpoint JSON (`VersionHandler`), et il n y a pas d URL evidente qui render `version.html`.
  => Risque: la doc induit qu une page est accessible, alors qu en pratique on ne peut pas la joindre (sauf ajout de route).

- Meeting: exemple de reponse avec `server_url: https://meeting.example.com`.
  - Dans le projet, l installeur / la config par defaut mentionnent plutot `https://meeting.ygsoft.fr`.
  => Risque: confusion sur la configurabilite et l environnement cible.

- Vendor frontend:
  - La doc dit "jQuery: manipulation DOM" + timepicker, etc.
  - Le JS du projet est majoritairement vanilla; jQuery/timepicker semblent charges mais pas utilises.
  => Risque: doc obsolete, et poids/perf inutiles si on continue a charger ces libs.

- Frame endpoint:
  - La doc indique "Retourne image PNG (placeholder en dev)".
  - En pratique l endpoint renvoie souvent `image/jpeg` (et peut renvoyer SVG si RTSP actif).
  => Risque: attentes fausses cote client/outillage.

## 3) Strategies potentiellement mauvaises / a risque (design / exploitation)
- Charger HLS.js depuis un CDN (`cdn.jsdelivr.net`) dans le template de base:
  - En production videosurveillance, reseaux souvent isoles (pas d Internet), ou politiques strictes.
  - Dependence a un tiers pour un composant critique d affichage.
  => Strategie plus robuste: vendoriser HLS.js dans `static/vendor/` et documenter la mise a jour.

- Strategie "auto-repair" apres update (via install script) telle que decrite:
  - Le repair implique des operations systeme (systemd, dependances, potentiellement apt) qui demandent des privileges.
  - Le serveur tourne typiquement en utilisateur de service non-root: le repair peut echouer silencieusement (la doc dit qu un echec est juste un warning).
  => Risque: systeme partiellement casse apres update, et l UI indique "succes".
  => Strategie: expliciter le modele de privilege (polkit/sudoers) ou separer clairement "update applicatif" vs "maintenance systeme".

- Versionnement "strict par fichier" dans la doc:
  - Tres couteux a maintenir manuellement, et la doc elle-meme montre des versions desynchronisees.
  => Strategie: automatiser (CI) et limiter a des zones clefs, sinon la doc devient rapidement fausse.

## 4) Recommandations (actionnables)
- Stabiliser le meta-versioning de la doc:
  - Un seul numero de version de document + reference explicite a une version applicative (tag/commit).
- Mettre a jour la table "versions actuelles" a partir des headers `File Version` (script CI).
- Aligner la doc sur les features reelles (page version, langues i18n, headers/Content-Type du frame).
- Documenter la strategie offline: vendoriser HLS.js et clarifier les prerequis reseau pour update/meeting.
- Clarifier le modele de privilege pour repair/maintenance (quoi tourne en root, quoi tourne en user de service).

Note
- Cette revue se base sur le contenu de `docs/TECHNICAL_DOCUMENTATION.md` et une comparaison rapide avec les fichiers du repo.
