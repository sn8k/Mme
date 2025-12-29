# Agents et responsabilités du projet Motion Frontend

| Agent | Rôle principal | Responsabilités détaillées | Livrables clés |
| --- | --- | --- | --- |
| **Product Owner (PO)** | Vision produit & priorisation | Formaliser les besoins utilisateurs (professionnels de la vidéosurveillance), maintenir le backlog, valider les spécificités fonctionnelles listées dans [docs/cahier_des_charges.md](docs/cahier_des_charges.md). | Roadmap, user stories, critères d’acceptation. |
| **Architecte Système** | Cohérence backend/frontend | Définir l’architecture technique (templates Jinja, endpoints Tornado, scripts installateur), valider la compatibilité Raspberry Pi OS, arbitrer les choix RTSP/MJPEG. | Diagrammes d’architecture, checklist technique. |
| **Lead Frontend** | Implémentation UI/UX | Reproduire les templates, CSS et JS décrits dans [TODOs/TODO_frontend.md](TODOs/TODO_frontend.md), assurer l’i18n, optimiser les performances, encadrer le design responsive. | Templates `base.html`, `main.html`, `version.html`, assets CSS/JS. |
| **Dev Backend & Intégrations** | API & services Raspberry Pi | Exposer les endpoints (config, médias, update, Wi-Fi, LEDs), interfacer Motion, gérer RTSP server + MJPEG, orchestrer le script `.sh` (install/update/uninstall) et implémenter l’infrastructure de logs multi-niveaux configurable depuis le frontend. | Handlers Tornado, scripts système, API interne, pipeline de logs. |
| **DevOps & CI** | Automatisation & packaging | Industrialiser les builds, publier les releases GitHub, maintenir l’installeur shell, superviser les tests matériels (Pi 3B+/4), automatiser la mise à jour des numéros de version de fichiers et de `requirements.txt`. | Pipelines CI, artefacts release, script `install_motion_frontend.sh`, contrôles de version. |
| **QA / Test** | Validation fonctionnelle | Construire plans de test (UI, flux vidéo, stockage SMB, Wi-Fi), exécuter tests sur matériel cible, reporter anomalies, valider i18n. | Rapports de test, scénarios reproductibles. |
| **Documentation & Support** | Guides & support | Rédiger une documentation complète et vivante (technique/utilisateur/opérateur), FAQ, procédures d’update, former les équipes support, maintenir le changelog global, orchestrer la mise à jour des traductions et le suivi des numéros de version par fichier. | Documentation utilisateur/admin, changelog versionné, guide i18n, référentiel de versions. |

## Règles de maintien continu
- **Changelog** : doit être mis à jour avant toute release publique ; validation conjointe PO + Documentation.
- **Requirements** : `requirements.txt` mis à jour dès qu’une dépendance Python change, avec traçabilité dans le changelog.
- **Scripts d’installation** : revue technique obligatoire pour chaque modification et tests sur Pi 3B+/4.
- **agents.md** : révision immédiate en cas de changement majeur d’organisation.
- **Multilingue** : toute nouvelle fonctionnalité doit inclure les clés i18n (au moins en fr/en) et documenter la procédure d’ajout de locales supplémentaires.
- **Documentation** : maintenir un corpus complet (technique/utilisateur/opérateur) versionné et publié avec chaque release.
- **Versionnement fichier** : chaque fichier doit posséder un numéro de version propre suivant le schéma `X.Y.Z` (majeur/mineur/hotfix avec suffixe lettre facultatif) et être incrémenté lors des modifications significatives ; la CI vérifie la cohérence des numéros.
- **Journalisation** : les loglevels (INFO, WARNING, ERROR, CRITICAL, DEBUG très bavard) doivent être testés, documentés et configurables via le frontend.

## Coordination
- **Cérémonies** : stand-up hebdo, revue/retro bi-hebdo, point matériel (Pi) dédié.
- **Outils** : Issues GitHub pour dev, Kanban pour suivi PO, Matrix/Slack pour synchronisation rapide.
- **Critères de done** : fonctionnalité documentée, couverte par tests, intégrée dans l’installeur, validée sur Pi 3B+ et Pi 4.

## Sujets à clarifier
1. Modalités exactes de contrôle des LEDs (GPIO vs sysfs).
2. Format audio souhaité pour RTSP (AAC, PCM) et licences associées.
3. Stratégie de distribution des traductions supplémentaires.
4. Sécurisation HTTPS (auto-signé vs intégration Let’s Encrypt).


## OBLIGATIONS :
- changelog global a conserver a jour systematiquement.
- requirements.txt conserver a jour systematiquement.
- creer une documentation globale : **[docs/TECHNICAL_DOCUMENTATION.md](docs/TECHNICAL_DOCUMENTATION.md)** et la conserver a jour systematiquement.
- projet cross platform windows/raspberrypi os sous debian trixie.