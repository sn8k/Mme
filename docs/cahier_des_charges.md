# Cahier des charges – Centre de vidéosurveillance Motion Frontend

- Recréer un frontend complet et professionnel (Motion Frontend) pour piloter Motion et son backend web depuis un navigateur moderne en conservant l'ergonomie historique détaillée dans [TODOs/TODO_frontend.md](TODOs/TODO_frontend.md).
- Permettre l'administration centralisée de plusieurs caméras IP/USB, la configuration réseau/Raspberry Pi, et la supervision des flux audio/vidéo en direct ou enregistrés.
- Garantir la compatibilité avec un déploiement headless sur Raspberry Pi OS (Debian Trixie) exécutant Motion + backend Tornado via Raspberry Pi 3B+ et 4.
- Assurer que le projet est développé sous Windows (VS Code) avec un cycle complet de test et de debug sur cette plateforme, ce qui impose une solution out-of-the-box cross-platform (Windows pour le dev, Raspberry Pi OS pour la prod).

## 2. Plateformes cibles et contraintes matérielles
- **Matériel** : Raspberry Pi 3B+ (armv7l) et Raspberry Pi 4 (aarch64) équipés de caméras CSI, USB UVC ou flux RTSP externes.
- **Système** : Raspberry Pi OS 64 bits basé sur Debian Trixie, mises à jour de sécurité activées.
- **Accès réseau** : Wi-Fi et Ethernet, possibilité de NAS SMB pour le stockage.
- **Budget CPU/RAM** : interface web légère (≤ 50 MB RAM côté backend), rafraîchissement MJPEG configurable pour éviter la saturation.

## 3. Architecture logicielle
- **Frontend** : stack HTML/CSS/JS vanilla avec Jinja2 côté backend. Templates principaux `base.html`, `main.html`, `version.html`, `manifest.json`, assets `static/css/*.css`, `static/js/*.js` décrits dans [TODOs/TODO_frontend.md](TODOs/TODO_frontend.md).
- **Backend** : API REST/Tornado déjà présente (endpoints `/config/`, `/config/list/`, `/config/<id>/`, `/frame/<id>/`, `/picture/<id>/`, `/movie/<id>/`, `/login/`, `/update/`, `/version/`, etc.). Le frontend ne doit pas imposer d’hypothèses supplémentaires.
- **Flux** : RTSP (audio + vidéo) via serveur embarqué, flux MJPEG pour aperçu rapide, transfert fichiers (photos/vidéos) par HTTP.
- **Stockage** : configuration pour stockage local (microSD, SSD USB) + montage SMB.

## 4. Modules fonctionnels
1. **Tableau de bord caméra**
   - Sélecteur de caméras, ajout/suppression, affichage hostname, boutons Apply/Backup/Restore/Update/Logout.
   - Flux MJPEG rafraîchi, indicateurs d’état (fps, résolution) et overlays configurables.
2. **Paramétrage système principal**
   - Préférences globales, identifiants admin, version logicielle, déclenchement reboot/update, configuration meeting backend/RTSP.
   - Gestion Wi-Fi : SSID, sécurité, DHCP/static, puissance radio, LED (activation/désactivation, PWM).
   - Gestion matérielle : LED caméra, rotation, IR-cut, GPU split.
3. **Paramétrage caméra** (par caméra)
   - Device (format vidéo, résolution, codecs audio/vidéo, framerate, orientation, exposition).
   - Text Overlay, Video Streaming (HLS/RTSP/MJPEG, limitation bande passante), Still Images, Movies.
   - Stockage : dossier local, quota, retention, partages SMB (chemin, auth, test de montage).
   - Motion Detection : zones, sensibilité, masques, scheduler, notifications (email, webhook, MQTT, SMS).
   - Working Schedule : calendrier via timepicker, exceptions.
4. **RTSP Server & Streaming**
   - Activation/désactivation, choix des ports, profils (main/substream), audio PCM/AAC, authentification.
   - Support MJPEG pour compatibilité legacy.
5. **Mises à jour / maintenance**
   - Bouton UI pour actionner `/update/` : vérifie dernière release GitHub, propose changelog, applique script `.sh`.
   - Suivi de version (`version.html`, `version.js`), affichage commit backend.
6. **Journalisation avancée**
   - Backends et services embarquent un logger commun avec niveaux INFO, WARNING, ERROR, CRITICAL, DEBUG.
   - Le niveau est paramétrable depuis le frontend via une API REST `POST /logging/config` (payload `{ "level": "INFO" }`), persisté côté backend (Pi) et appliqué dynamiquement.
   - Le mode DEBUG doit être extrêmement bavard (requêtes, réponses, timings, hooks matériels) afin de diagnostiquer le matériel à distance.
   - Export et rotation des logs accessibles depuis l’interface (téléchargement, purge, taille max configurable). La configuration inclut la profondeur d’historique et les destinations (fichier, syslog optionnel).
7. **Sécurité**
   - Authentification par cookies hashés (`meye_username`, `meye_password_hash`), gestion rôles admin/utilisateur.
   - Forcer HTTPS recommandé, compatibilité avec reverse proxy.

## 5. Exigences UI/UX
- Style sombre identique aux captures de l'interface historique (classes `.settings-section-title`, `.settings-item`, `.button`, `.help-mark`, etc.).
- Accordéons configurables avec icônes, dépendances dynamiques (attribut `depends`).
- Responsiveness : viewport mobile, colonnes réarrangées < 768 px.
- Internationalisation complète via JSON `motion_frontend.<lang>.json`, loader `gettext`. Toute chaîne UI doit passer par i18n.
- Accessibilité : navigation clavier, contrastes ≥ 4.5:1, labels explicites.
- Performances : chargement initial ≤ 3 s sur Pi 3B+ via Chromium, resources servies avec cache-busting `?v={{version}}`.

## 6. Installateur et mises à jour
- **Script `install_motion_frontend.sh`** :
  - Modes `install`, `update`, `uninstall` (paramètre CLI ou menu interactif).
  - Télécharge/clône le dépôt GitHub, installe dépendances apt (nginx/lighttpd optionnel, Motion, Python, node/yarn si nécessaire), configure systemd services.
  - Pour `update`, récupère dernière release tag, applique migrations front/backend, relance services.
  - Pour `uninstall`, arrête services, supprime fichiers optionnels, conserve sauvegardes configurées.
- **Fonction Update UI** :
  - Vérifie la version distante (GitHub API), déclenche script shell via backend.
  - Feedback visuel (progress, logs, redémarrage requis).

## 7. Intégrations matérielles Raspberry Pi
- Gestion LEDs (power, activity, camera) via `/sys/class/leds/*` ou API rpi-led-control.
- Paramétrage Wi-Fi via `wpa_supplicant`, `nmcli` ou `raspi-config nonint` (à définir avec backend), tests de connectivité.
- Contrôle caméra (focus, servo, IR-cut) via scripts python/gpio. Prévoir API backend pour relayer les commandes.

## 8. Sécurité, robustesse, observabilité
- Journalisation UI (console + backend) des erreurs AJAX.
- Vérification d’intégrité du script installateur (hash SHA256 publié dans release).
- Politique CORS restreinte, cookies `SameSite=Strict`, `HttpOnly` quand possible.
- Monitoring : exposer métriques basiques (charge CPU, utilisation stockage) via sections additionnelles.

## 9. Acceptation et validation
- Reproduire tous les comportements listés dans [TODOs/TODO_frontend.md](TODOs/TODO_frontend.md) y compris macros Jinja, dépendances et endpoints.
- Tests à prévoir :
  - Un Pi 3B+ + Pi Camera + stockage SMB.
  - Un Pi 4 + 2 caméras (CSI + RTSP) + audio micro USB.
  - Scénarios install/update/uninstall via script `.sh`.
  - Vérification flux RTSP audio+vidéo et MJPEG simultanés.
  - Validation i18n (fr, en) et thème responsive.

## 10. Livrables
- Templates, JS, CSS, assets fidèles à l'interface historique.
- Script installateur `.sh` documenté.
- Documentation utilisateur (guide d’installation, guide admin, release notes).
- Agents/responsabilités décrits dans [docs/agents.md](docs/agents.md).

## 11. Gouvernance de maintenance continue
- Tenir un changelog global public à jour à chaque évolution fonctionnelle ou technique, publié avec les releases.
- Mettre à jour systématiquement `requirements.txt` dès qu’une dépendance Python change (version ou ajout/suppression).
- Versionner tous les scripts d’installation/mise à jour/suppression, avec revue obligatoire pour chaque modification impactant les Raspberry Pi.
- Mettre à jour [docs/agents.md](docs/agents.md) lors de tout changement majeur de rôles ou de responsabilités projet.
- Concevoir l’interface pour être pleinement multilingue : ajout simplifié de nouvelles traductions `motion_frontend.<lang>.json`, processus documenté et testé dans la CI.
- Rédiger et maintenir une documentation complète (technique, utilisateur, opérateur) incluant procédures d’installation, d’update, de dépannage et d’i18n.
- Assigner un numéro de version à chaque fichier du dépôt et l’incrémenter à chaque modification significative ; documenter ces versions dans le changelog et les en-têtes de fichiers.
- **Stratégie de numérotation** : schéma `X.Y.Z` (majeur/mineur/hotfix). `X` s’incrémente pour les changements structurants ou incompatibles, `Y` (0-100) pour les ajouts/révisions mineures, `Z` (0-100) pour les corrections ponctuelles ; un suffixe lettre (`a`, `b`, etc.) peut être ajouté pour distinguer des variantes intermédiaires.
