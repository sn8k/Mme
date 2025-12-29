Meeting API – Technical Encyclopedia (Backend REST)


Version: 3.4.33
Date: 2025-06-25
Sources : Code backend fourni (juin 2025, v3.4.3+)

Documentation exhaustive, à jour, orientée développeurs, ops, devops, QA.



Table of Contents

Introduction & Principles

Workflows & Best Practices

Authentication & Security

Tunnels (Reverse Tunnel)

Devices (DeviceController)

Flash (Firmware & Distributions)

Device Designer (Admin)

Logs (Device Logs)

Device Availability

Device Relations

SSH Keys Management

Status (Heartbeat, Last Seen)

Metrics & System Monitoring

ForceCommand: Key Management & Tunnel Ports

Global Config & Environment

Glossary



Introduction & Principles

La Meeting API est un backend REST de gestion IoT/Edge orienté :

Provisioning et onboarding sécurisé de devices (clé unique, token, autorisation)

Gestion dynamique et industrialisée de tunnels (SSH, HTTP, VNC, SCP) via reverse proxy Node.js/Meeting

Monitoring temps réel, heartbeat, suivi des états, logging centralisé

Provisionning firmware/distribution, inventory, configuration (avec stockage arborescent)

Gestion de la sécurité SSH à grande échelle (authorized_keys dynamique, tokenisation, audit)

Tout est accessible via REST, structure /api/

Retour JSON systématique (sauf endpoints bruts : SSH key, upload)

Endpoints versionnés/documentés

Sécurité et audit by design : chaque opération critique est logguée, horodatée, corrélée au device/user concerné



Workflows & Best Practices

Exemples de Workflows Typiques

➡️ Onboarding d’un device (zero-touch/provisionning)

Génération d’une clé device via /api/devices/generate-key (admin ou agent d’enrôlement)

Enregistrement (manual ou auto) : /api/devices/manual-create ou /api/devices/generate-and-register (body complet)

Association d’une clé SSH (PUT /api/devices/{device_key}/ssh-key)

Activation/autorisation via /api/devices/{device_key}/authorize (flash)

Premier heartbeat (POST /api/devices/{device_key}/online)

Appels de service/tunnel ou provisioning (ex : /api/devices/{device_key}/service)

➡️ Ouverture d’un tunnel reverse (SSH/HTTP/VNC/SCP)

Demande par /api/devices/{device_key}/service (POST, body : { "service": "ssh" })

Si tunnel existant : réponse immédiate (port/URL)

Sinon : port libre réservé en base et renvoyé immédiatement (le proxy s’ouvre via /api/tunnels)

➡️ Provisionning firmware/distribution

Création du type/distribution (admin : /api/flash/create-type & /api/flash/create-distribution)

Upload firmware (/api/flash/upload)

Flash request via /api/devices/{device_key}/flash-request

Best Practices

Utilisez le Content-Type approprié (application/json partout sauf upload)

Vérifiez toujours les codes HTTP, tous les cas d’erreur sont renseignés

Ne stockez jamais de token/clé SSH côté client : faites toujours un handshake/déclaratif

Utilisez les endpoints heartbeat pour le monitoring actif (au moins 1/minute recommandé)

Purge logs périodique : /api/devices/{device_key}/purge-logs (limite nombre d’entrées, RGPD…)

Supervisez les statuts de tunnel : /api/tunnels et /api/devices/{device_key}/availability

Idempotence : tous les endpoints PUT/POST sont idempotents ou clairement documentés

Authentification : respectez les headers tokens et payloads, évitez l’exposition d’API critiques



Authentication & Security

Tokens

Certains endpoints nécessitent X-Meeting-Ssh-Token (récupérable côté serveur SSH ou config)

Admin/maintenance : login/password configurable (voir config.php)

Log et audit : chaque modification de device, clé, distribution, etc., est logguée avec timestamp

Best practice : n’exposez jamais vos endpoints de flash/autorisation sur internet sans filtrage (IP, VPN, firewall)

Gestion des droits : chaque device a un statut authorized et un nombre de tokens (token_count) : seul un device autorisé ET disposant de tokens peut être utilisé pour tunnel/flash

Notes sécurité :

Upload limité à certains types de fichiers (pas de contrôle AV dans le backend par défaut)

Suppression/modification device/token/type protégée par vérification d’intégrité

Anti-spam/anti-abus : endpoints logs et heartbeat gèrent le double appel, anti-flap, anti-flood par delta/valeur en base



Tunnels (Reverse Tunnel)

Description & Architecture

La gestion des tunnels Meeting repose sur :

Un backend PHP REST (vous lisez la doc…)

Un proxy Node.js/Meeting pour l’orchestration et l’ouverture effective des ports

Un workflow agent côté device (polling + push)

Table SQL tunnel_ports pour le suivi des ports actifs
Colonnes : device_key, service, port (public), local_port (port interne au device), expires_at.

Endpoints

1. Lister tous les tunnels actifs

GET /api/tunnels

Description : Liste les tunnels reverse actifs. Utilisable pour monitoring, troubleshooting, allocation dynamique.

Réponse :

{ "tunnels": [ { "device_key": "...", "service": "ssh", "port": 9050, "local_port": 22, "expires_at": "2025-06-01 16:10:00" }, ... ] }


Notes : Requiert droits admin/backoffice. Retourne tous les tunnels ouverts (quel que soit le service).

2. Demander l’ouverture d’un tunnel pour un device (SSH/HTTP/VNC/SCP)

POST /api/devices/{device_key}/service

Payload attendu :

{ "service": "ssh" }


Réponse :

Si tunnel existant :

{ "port": 9051, "url": "ssh -p 9051 device@clusterTO83.meeting.ygsoft.fr" }


Si aucun tunnel trouvé :

{ "port": 9051, "url": "ssh -p 9051 device@clusterTO83.meeting.ygsoft.fr" }


Notes : le tunnel créé est enregistré en base et visible immédiatement via
/api/tunnels afin que le proxy l'ouvre sans délai.

Erreurs :

400 (service manquant/non supporté)

403 (device non autorisé/pas de token)

404 (device introuvable)

202 (en attente)

Notes :

Nécessite que le device soit autorisé (authorized=1) ET en ligne (heartbeat < 60s)

Le tunnel ne sera disponible qu’après polling par l’agent device

3. (Legacy) Vérifier une demande de tunnel en attente

GET /api/devices/{device_key}/tunnel-pending

Description : Ancien mécanisme basé sur des fichiers `tunnel_requests`. Toujours disponible pour rétro‑compatibilité, mais la version 2.x du proxy n’en dépend plus.

Réponse :

{ "pending": true, "request": { "tunnel_id": "...", ... } }


ou

{ "pending": false }

4. Reporter l’état d’un tunnel ouvert (agent → backend)

POST /api/devices/{device_key}/tunnel-status

Payload attendu :

{ "service": "ssh", "port": 9051, "url": "...", "upnp": "...", "error": "..." }


Réponse :

{ "ok": true, "status": { ... } }


Best practices : toujours reporter l’état complet (port, url, erreurs le cas échéant)

5. Vérifier l’autorisation tunnel d’un device

POST /api/devices/{device_key}/authorize-tunnel

Description : Pré-check pour s’assurer que le device a le droit d’ouvrir un tunnel (tokens, autorisation…)

Réponse :

{ "ok": true, "device_key": "...", ... }


ou

{ "ok": false, "error": "No tokens left" }


Utilisation : étape recommandée avant chaque workflow d’ouverture de tunnel côté client



Devices (DeviceController)

Rôle et architecture

Le module Devices centralise la gestion du cycle de vie des équipements :

Création (auto ou manuelle), enregistrement, suppression

Mise à jour atomique et sécurisée des services (SSH/VNC/HTTP/SCP), types, notes, bundles

Provisionnement distribué (liens flash/distribution)

Gestion fine des relations (parent, ghost, numéro de série, etc.)

Accès paginé, recherche par préfixe, extraction bulk pour interface admin/devops

Haute traçabilité (logs, workflow de synchronisation, anti-collision device_key)

Endpoints détaillés

1. Lister tous les devices (paginé)

GET /api/devices

Description : Liste paginée des devices.Paramètres :

limit : nombre max de résultats (défaut : 25, max : 100)

offset : index de départ (défaut : 0)

prefix : filtre les device_key commençant par ce préfixe (optionnel, uppercase)

Réponse :

{
  "devices": [ { "device_key": "...", ... } ],
  "total": 123,
  "limit": 25,
  "offset": 0
}


Notes : Utilisation typique : interface admin, batch export, monitoring.

2. Générer une clé device (unique, non enregistrée)

GET /api/devices/generate-key

Description : Génère une nouvelle device_key (et token_code) non enregistrée : à utiliser pour onboarding manuel ou automatisé.

Réponse :

{ "devicekey": "ABCD...", "token_code": "xyz123" }


3. Générer ET enregistrer un device

POST /api/devices/generate-and-register

Description : Génère device_key, token, ssid/password wifi, enregistre en BDD.

Réponse :

{
  "devicekey": "...",
  "token_code": "...",
  "ap_ssid": "...",
  "ap_password": "...",
  "http_pw_low": "...",
  "http_pw_medium": "...",
  "http_pw_high": "..."
}


Notes : Lance la synchronisation des clés SSH côté serveur.

4. Création manuelle d’un device

POST /api/devices/manual-create

Payload attendu :

{
  "devicekey": "....",
  "token_code": "...",
  "device_type": "...",
  "distribution": "...",
  "product_serial": "..." // facultatif, auto-généré sinon
}


Réponse :

{
  "devicekey": "...",
  "token_code": "...",
  "ap_ssid": "...",
  "ap_password": "...",
  "http_pw_low": "...",
  "http_pw_medium": "...",
  "http_pw_high": "...",
  "device_type": "...",
  "distribution": "...",
  "product_serial": "..."
}


Erreurs : device_key ou serial déjà utilisé : 409 Conflict.Champs manquants ou invalides : 400 Bad Request.

6. Supprimer un device

DELETE /api/devices/{device_key}

Réponse :

Succès : { "success": true } (et synchronisation clé SSH)

Not found : 404 + { "error": "Device not found" }

6. Obtenir les détails d’un device

GET /api/devices/{device_key}

Réponse :

{
  "device_key": "...",
  "device_name": "...",
  "product_serial": "...",
  "authorized": true,
  "device_type": "...",
  "distribution": "...",
  "token_code": "...",
  "token_count": 0,
  "note": "...",
  "ip_address": "...",
  "parent_device_key": "...",
  "bundles": [ ... ],
  "ghost_candidate_url": "...",
  "ap_ssid": "...",
  "ap_password": "...",
  "http_pw_low": "...",
  "http_pw_medium": "...",
  "http_pw_high": "...",
  "services": ["ssh", "vnc", "http", "scp"]
}


Notes :

Liste complète des attributs (intégration frontend/admin)

Les services actifs sont listés dans l’array services.

7. Modifier les services actifs d’un device

PUT /api/devices/{device_key}

Payload attendu :

{ "services": ["ssh", "http", ...] }


Réponse :

Succès : { "success": true }

Nothing to update : 400 Bad Request

Not found : 404

8. Lire ou modifier la note d’un device

GET /api/devices/{device_key}/note

PUT /api/devices/{device_key}/note

Payload attendu (PUT) :{ "note": "max 2000 chars" }

Réponse (GET) : { "note": "..." }

Réponse (PUT) : { "success": true, "note": "..." }

Erreurs : note trop longue : 400

9. Lister les types de device

GET /api/devices/device-types

Réponse : { "device_types": [ ... ] }

10. Lister les distributions pour un type de device

GET /api/devices/device-types/{type}/distributions

Réponse : { "distributions": [ ... ] }

11. Lire/écrire le fichier distrib.json d’un device

GET /api/devices/{device_key}/distrib-json

PUT /api/devices/{device_key}/distrib-json

Payload attendu (PUT) : JSON libre (config/distribution du device)

Réponse (GET) : contenu JSON du fichier

Réponse (PUT) : { "success": true }

Erreurs : 404 si device ou distrib inconnue, 400 JSON invalide

12. Lister les services disponibles sur un device

GET /api/devices/{device_key}/service

Réponse : { "services": ["ssh", "vnc", "http", "scp"] }

13. Télécharger la clé privée PPK d’un device

GET /api/devices/{device_key}/private-ppk

Réponse : fichier .ppk (Content-Type: application/octet-stream)
Header : X-PPK-Passphrase avec le mot de passe généré

Erreurs : 404 si clé privée absente, 500 si conversion échoue



Flash (Firmware & Distributions)

Rôle et architecture

Gestion centralisée des firmwares, distributions, binaires pour tous les devices.

Workflows complets pour :

Création de nouveaux types de device (arborescence storage)

Ajout d’une distribution/famille firmware à un type

Upload de binaires (multipart)

Listing, suppression, MAJ, provisionnement automatisé

Association dynamique à un device donné (stockage optimisé)

Endpoints détaillés

1. Lister les fichiers de distribution associés à un device

GET /api/flash/{device_key}/distribution-files

Description : Récupère la liste de tous les fichiers binaires (firmware, scripts, blobs…) de la distribution actuellement associée à ce device.

Réponse :

{
  "devicetype": "rpi4",
  "distribution": "prod",
  "files": [ "firmware.bin", ... ]
}


Erreurs :

404 : device inconnu ou chemin inexistant

400 : paramètres manquants (type ou distrib)

2. Uploader un fichier de distribution

POST /api/flash/upload

Payload : POST multipart (champs : devicetype, distribution, file)

Description : Permet d’uploader tout fichier dans la distribution spécifiée, pour le type concerné.

Réponse : { "success": true, "file": "firmware.bin" }

Erreurs :

400 : paramètres/file manquants

500 : échec upload (droit, disque…)

3. Créer un nouveau type de device

POST /api/flash/create-type

Payload attendu : { "devicetype": "rpi5" }

Description : Initialise une arborescence de stockage pour ce nouveau type.

Réponse : { "success": true, "devicetype": "rpi5" }

Erreurs :

400 : type invalide

409 : déjà existant

500 : échec création

4. Créer une nouvelle distribution pour un type donné

POST /api/flash/create-distribution

Payload attendu : { "devicetype": "rpi4", "distribution": "nightly" }

Description : Ajoute un répertoire de distribution firmware à un type existant.

Réponse : { "success": true, "devicetype": "rpi4", "distribution": "nightly" }

Erreurs :

400 : param manquant/invalide

409 : déjà existante

500 : échec création

6. Supprimer un fichier de distribution

DELETE /api/flash/{device_type}/{distribution}/{filename}

Description : Supprime définitivement un binaire/firmware d’une distribution d’un type donné.

Réponse : { "success": true }

Erreurs :

404 : fichier inexistant

500 : suppression échouée

6. Lister tous les types de device disponibles

GET /api/flash/device-types

Réponse : { "device_types": [ "rpi4", "esp32", ... ] }

7. Lister toutes les distributions pour un type donné

GET /api/flash/{device_type}/distributions

Réponse : { "distributions": [ "prod", "nightly", ... ] }

Erreurs :

404 : type non existant

8. Flash (consommer un token)

POST /api/devices/{device_key}/flash-request

Description : Décrémente un token, loggue l’opération et autorise le provisioning côté device.

Réponse : { "success": true, "tokens_left": 1 }

Erreurs :

404 : device inconnu

403 : plus de tokens

500 : échec interne

9. Autoriser/interdire un device (pour le flash)

PUT /api/devices/{device_key}/authorize

Payload attendu : { "authorized": 1 } ou { "authorized": 0 }

Réponse : { "success": true, "authorized": 1 }

10. Définir le nombre de tokens pour un device

PUT /api/devices/{device_key}/tokens

Payload attendu : { "token_count": 3 }

Réponse : { "success": true, "token_count": 3 }

Erreurs : 400 si non entier

11. Changer la distribution d’un device

PUT /api/devices/{device_key}/distribution

Payload attendu : { "distribution": "nightly" }

Réponse : { "success": true, "distribution": "nightly" }

Erreurs : 400 si manquant

12. Changer le token_code d’un device

PUT /api/devices/{device_key}/token-code

Payload attendu : { "token_code": "abc456" }

Réponse : { "success": true, "token_code": "abc456" }



Workflows associés :

Provisionning complet = création type > création distrib > upload > flash-request

Possibilité de provisionner plusieurs devices avec la même distribution, via les endpoints device/distribution associés

Bonnes pratiques :

Toujours vérifier l’existence du type/distribution avant upload

Purger ou archiver les anciens firmwares pour éviter la saturation disque

Contrôler les droits d’accès backend sur le dossier de stockage (flash_storage_root)

Auditer et logguer chaque opération critique (upload/suppression) pour traçabilité
Device Designer (Admin)
-----------------------

Interface web accessible sous `/admin/device_designer.php` permettant de créer, modifier (fork), lister et supprimer les `device_types`. Elle transfère automatiquement le token de session vers Distrib Builder et demande ce même token pour toute suppression. La page affiche aussi l'historique des actions DeviceType extrait du `backend_api.log` (trié du plus récent au plus ancien).


Logs (Device Logs)

Rôle et architecture

Centralisation de l’historique des connexions (events "Connected", IP, host, remote) par device

Purge simple et conforme RGPD/log-retention

Extraction optimisée (tri desc, extraction complète ou partielle)

Idéal pour le diagnostic, l’audit, le monitoring fin et la traçabilité de présence/reconnexions

Endpoints détaillés

1. Récupérer l’ensemble des logs d’un device

GET /api/devices/{device_key}/logs

Description : Retourne tous les événements de connexion pour un device donné, triés du plus récent au plus ancien

Réponse :

[
  { "timestamp": "2025-05-31 16:22:10", "event": "Connected", "host": "server-01", "remote": "192.168.1.23" },
  ...
]


Notes : Chaque ligne logguée lors d’un heartbeat/réactivation ou connexion effective

Erreurs :

Retourne [] si aucun log trouvé

404 si device inconnu

2. Purger tous les logs d’un device

POST /api/devices/{device_key}/purge-logs

Description : Supprime tous les événements de connexion stockés pour ce device (remise à zéro RGPD ou nettoyage bulk)

Réponse : { "success": true }

Best practices

Limitez la volumétrie des logs côté base (cf. paramètre status_max_logs)

Utilisez la purge régulière pour les devices à forte fréquence de heartbeat

Extraction/log download côté interface admin : batch/CSV recommandé

Audit : croiser les logs de connexion avec les logs de tunnels pour détection d’anomalie



Device Availability

Rôle et architecture

Vérifie la disponibilité/présence d’un device via le champ last_seen.

Timeout configurable (device_heartbeat_timeout), synchrone avec le heartbeat/online reporting.

Pas de dépendance log, pas de spam : simple, robuste, exploitable dans tous les workflows d’orchestration et de monitoring.

Endpoints détaillés

1. Vérifier la disponibilité d’un device

GET /api/devices/{device_key}/availability

Description : Statut "Available" si le device a émis un heartbeat récemment, "Disconnected" sinon, timestamp du dernier heartbeat.

Réponse :

{
  "status": "Available", // ou "Disconnected", "Unknown"
  "last_heartbeat": "2025-05-31 15:12:41",
  "since": "2025-05-31 15:12:41",
  "uptime": 58
}


status : Available / Disconnected / Unknown

uptime : secondes depuis le dernier heartbeat

last_heartbeat : horodatage UTC du dernier online

Erreurs :

Device inconnu : valeurs "Unknown"

Best practices

Utilisez cet endpoint pour piloter l’automatisation (fermeture automatique de tunnels, alertes monitoring, …)

Ajustez le timeout à la criticité du device (via config ou supervision devops)

Poller la disponibilité juste avant toute opération sensible (tunnel, update firmware…)

Intégrer l’uptime comme metric dans les dashboards



Device Relations

Rôle et architecture

Gestion des relations et attributs avancés entre devices : parent/enfant, ghost (candidat de récupération), bundles (groupe d’appareils), numéro de série, type.

API atomiques (une propriété par endpoint), idéales pour interface graphique, automatisation, configuration évolutive.

Permet la gestion d’inventaires complexes, la traçabilité matérielle, et la gestion d’ensembles logiques (bundles, clusters…).

Endpoints détaillés

1. Définir le parent d’un device

PUT /api/devices/{device_key}/parent

Payload attendu : { "parent_device_key": "..." }

Réponse : { "success": true, "parent_device_key": "..." }

Utilisation : Organigrammes hiérarchiques, remplacements, topologies dynamiques.

2. Déclarer un device comme ghost candidate

PUT /api/devices/{device_key}/ghost

Payload attendu : { "ghost_candidate_url": "..." }

Réponse : { "success": true, "ghost_candidate_url": "..." }

Utilisation : Gestion de pièces détachées, appareils orphelins, “auto-discover”.

3. Définir les bundles d’un device

PUT /api/devices/{device_key}/bundles

Payload attendu : { "bundles": ["dev1", "dev2", ...] }

Réponse : { "success": true, "bundles": "[...]" }

Utilisation : Gestion de clusters, licences, multi-device, synchronisation de firmware.

4. Mettre à jour le numéro de série d’un device

PUT /api/devices/{device_key}/product-serial

Payload attendu : { "product_serial": "V1-S01-00123" }

Réponse : { "success": true, "product_serial": "V1-S01-00123" }

Utilisation : Inventaire, gestion du SAV, logs de production.

5. Changer le type de device

PUT /api/devices/{device_key}/device-type

Payload attendu : { "device_type": "rpi4" }

Réponse : { "success": true, "device_type": "rpi4" }

Utilisation : Migration, conversion, upgrade matériel.

Best practices

Ne pas modifier massivement (batch) sans audit (pour éviter perte de liens hiérarchiques)

Toujours logger les changements critiques d’attributs (cf. logs back)

Utiliser avec validation de cohérence business côté client

Idéal pour synchronisation entre CMDB/inventory externe et Meeting



Device Types (DeviceTypeController)
----------------------------------

Le modèle `device_types` référence les différents matériels gérés par Meeting : nom, préfixe de série, plateforme, services par défaut, distribution parente et statut. Il permet de dupliquer un type existant pour créer rapidement des variantes. Le champ `icon_path` pointe vers l’icône enregistrée dans le dossier configuré `device_type_icon_dir`; lors de la création ou de la mise à jour d’un type, l’API accepte un fichier `icon` en multipart et met à jour ce champ automatiquement.

1. Lister tous les types

GET /api/device-types

Réponse : { "device_types": [ ... ] }

2. Créer un type de device

POST /api/device-types

Payload attendu : { "name": "Raspberry Pi 5", "serial_prefix": "RPI5" }

Réponse : { "success": true, "id": 3 }

3. Mettre à jour un type

PUT /api/device-types/{id}

Payload : { "platform": "arm64", "status": "active" }

Réponse : { "success": true }

4. Dupliquer un type existant

POST /api/device-types/{id}/fork

Payload attendu : { "name": "RPI5-clone", "serial_prefix": "RPI5B" }

Réponse : { "success": true, "id": 4 }
5. Fusionner un fork avec l'original

POST /api/device-types/{id}/merge

Réponse : { "success": true }


6. Supprimer (soft) un type

DELETE /api/device-types/{id}

Réponse : { "success": true }


SSH Keys Management

Rôle et architecture

Gestion centralisée et sécurisée des clés SSH pour tous les devices (AuthorizedKeysCommand, inventory)

Support du workflow devops/cloud-init/IoT onboarding (clé unique par device)

API pensée pour usage direct par serveur SSH (token ou 127.0.0.1), et interface admin

Endpoints détaillés

1. Récupérer toutes les clés SSH publiques pour un user

GET /api/ssh-keys?user={username}

Header optionnel : X-Meeting-Ssh-Token

Description : Liste les clés publiques autorisées pour ce user (filtre : devices autorisés, non révoqués, associées à ce user)

Réponse :

{ "keys": [ "ssh-rsa AAAA...", ... ] }


Erreurs :

401 si token absent/incorrect hors localhost

400 si user manquant

404 si aucune clé

2. Associer ou mettre à jour la clé publique SSH d’un device

PUT /api/devices/{device_key}/ssh-key

Payload attendu : { "ssh_public_key": "ssh-ed25519 ..." }

Réponse : { "success": true }

Erreurs :

400 clé manquante ou format invalide

404 device inconnu

3. Lister tous les devices avec clé SSH pour un user

GET /api/ssh-keys/devices?user={username}

Header optionnel : X-Meeting-Ssh-Token

Réponse :

{ "devices": [ { "device_key": "...", "ssh_public_key": "...", "authorized": 1, "revoked": 0 }, ... ] }


Erreurs :

401 si token absent/incorrect hors localhost

400 si user manquant

(Non routés/Not Implemented) :

GET/DELETE /api/devices/{device_key}/ssh-key : non exposés, 501

4. Obtenir la clé publique SSH du serveur

GET /api/ssh-hostkey

Réponse : texte brut compatible `ssh-keyscan`

Exemple :

```
meeting.ygsoft.fr ssh-ed25519 AAAAB3Nza...
```

Utilisé par ygs-agent pour mettre à jour `~/.ssh/known_hosts`.

Best practices

Utiliser l’API pour synchroniser automatiquement authorized_keys sur cluster/serveurs

Toujours régénérer la clé device à l’onboarding, ne jamais réutiliser une ancienne

Gérer la révocation côté device OU via attribut en base (revoked)

Auditer et logger tout changement de clé (compliance)



Status (Heartbeat, Last Seen)

Rôle et architecture

Centralise la gestion du “heartbeat” : savoir si un device est en ligne, détecter une déconnexion, stocker l’IP, piloter la présence dans l’infra.

Met à jour en temps réel les timestamps et l’adresse IP du device à chaque signalement online.

Historique et anti-spam intégrés (évite les doublons et le spam des logs).

Endpoints détaillés

1. Déclarer un device en ligne (heartbeat)

POST /api/devices/{device_key}/online

Payload optionnel : { "ip_address": "...", "services": { "ssh":1, ... }, "note": "..." }

Effets :

Met à jour last_seen et l’adresse IP du device.

Peut mettre à jour dynamiquement les services actifs et la note associée au device.

Écrit un événement Connected dans les logs, mais uniquement si le dernier état n’était pas déjà “Connected” (anti-spam).

Réponse :

{ "ok": true, "ip_address": "192.168.1.23", "last_seen": "2025-06-01 14:22:10" }


Erreurs :

404 : device non trouvé

Mauvais format : body JSON invalide, champs manquants

2. Dernière activité (“last seen”) d’un device

GET /api/devices/{device_key}/last-seen

Réponse :

{ "device_key": "ABCDEF...", "last_seen": "2025-06-01 15:22:10" }


Erreurs :

404 : device non trouvé

Best practices

Appeler régulièrement l’endpoint /online pour chaque device actif (1x/min minimum recommandé)

Toujours renseigner l’IP et les services actifs pour une supervision efficace

Utiliser le “last_seen” pour toute décision de monitoring/tunnel/maintenance

Purger les logs avec /purge-logs pour éviter les historiques démesurés



Metrics & System Monitoring

Rôle et architecture

Permet de superviser en temps réel l’état du serveur backend et de la base de données.

Expose des métriques systèmes avancées (CPU, RAM, disque, uptime, users, réseau), et les principales métriques SQL (taille BDD, nb connexions, etc.).

Utilisable en dashboard devops, alerte, ou healthcheck automatisé.

Endpoints détaillés

1. Récupérer les métriques systèmes

GET /api/metrics?action=get

Description : Retourne l’état global système et BDD (charge, mémoire, disque, PHP process, température, users, etc.)

Réponse :

{
  "success": true,
  "metrics": {
    "cpu": { "loadavg_1min": 0.12, ... },
    "memory": { "total_mb": 1928, ... },
    "disk": { "total_bytes": ..., ... },
    "uptime_sec": 43210,
    "temperature_c": 47.2,
    "users_logged_in": 2,
    "network": { "interface": "eth0", "rx_bytes": 12345678, ... },
    "php_process": { "memory_usage_bytes": ..., ... },
    "php_version": "8.2.10",
    "db_metrics": { "connected": true, "num_tables": 23, ... },
    "timestamp": "2025-06-01T16:45:22+00:00"
  }
}


Erreurs :

500 si la collecte échoue

2. Récupérer le log API metrics

GET /api/metrics?action=logs[&lines=N]

Description : Retourne les N dernières lignes du log interne de l’API metrics (défaut : 100)

Réponse :

{ "success": true, "log": [ "...", ... ] }


Erreurs :

500 si log non trouvable

3. Export Prometheus (optionnel)

GET /api/metrics?action=prometheus

Description : (Si activé) Format compatible Prometheus, pour integration monitoring externe

Best practices

Superviser /metrics en healthcheck automatisé (uptimerobot, statuspage, etc.)

Exploiter /metrics?action=logs pour les analyses d’incident ou les audits post mortem

Récupérer régulièrement le dump Prometheus si intégré à un cluster de supervision

Adapter les alertes sur les seuils critiques (RAM/disque/température…)



ForceCommand: Key Management & Tunnel Ports

Rôle et architecture

Gère le provisioning et la validation des clés SSH côté ForceCommand (mode SSH proxy : jumpbox ou bastion)

Assure l’attribution de ports de tunnel dynamiques et robustes (en reverse)

S’appuie principalement sur la table SQL device_keys pour les associations clé↔device.
Les clés envoyées via `/api/devices/{device_key}/ssh-key` sont automatiquement répliquées dans cette table.

Vérifie la présence/online avant toute allocation

Endpoints détaillés

1. Enregistrer une clé publique pour un device

POST /api/forcecommand/register_device_key

Payload attendu : { "device_key": "...", "pubkey": "ssh-ed25519 ..." }

Réponse : { "status": "ok" }

Erreurs :

400 : champs manquants

500 : erreur SQL

2. Valider une clé publique

POST /api/forcecommand/validate_device_key

Payload attendu : { "pubkey": "ssh-ed25519 ..." }

Réponse :

Success : { "status": "ok", "device_key": "..." }

Fail : { "status": "invalid" } (401)

3. Récupérer la clé publique d’un device

GET /api/forcecommand/get_device_key?device_key=...

Retourne la clé publique stockée pour ce device. Si aucune entrée n’existe dans
`device_keys`, la valeur de `devices.ssh_public_key` est renvoyée et répliquée dans
`device_keys`.

Réponse : SSH public key (plain/text) ou { "status": "not_found" }

4. Attribuer dynamiquement un port de tunnel à un device

POST /api/devices/{device_key}/request-tunnel-port

Payload optionnel : { "device_key": "...", "service": "ssh" } (params GET possibles)

Réponse : { "status": "ok", "port": 9055 }

Préconditions : Device autorisé et “online” (last_seen < forcecommand_max_last_seen)

Erreurs :

400 : device_key manquant

403 : device non autorisé

404 : device inconnu

503 : pas de port libre/disponible

6. Supprimer une clé publique device (forcecommand)

DELETE /api/forcecommand/remove_device_key

Payload attendu : { "device_key": "..." }

Réponse : { "status": "ok", "deleted": 1 } ou { "status": "not_found", "deleted": 0 }

Best practices

Ne jamais attribuer le même port à plusieurs devices (gestion atomique transactionnelle)

Purger les clés non utilisées à intervalle régulier (sécurité, hygiène infra)

Intégrer ces endpoints dans le workflow d’onboarding automatisé

Toujours valider l’état online/autorisé d’un device avant toute allocation de port



Users (UserController)
----------------------

Gestion simple des utilisateurs pouvant accéder à Meeting. Table SQL `builder_users` avec rôles, token, mot de passe et clé SSH optionnelle.

1. Lister les utilisateurs

GET /api/users

Réponse : { "users": [ { "id": 1, "username": "alice" }, ... ] }

2. Récupérer un utilisateur

GET /api/users/{id}

Réponse : { "id": 1, "username": "alice", "role": "admin" }

3. Créer un utilisateur

POST /api/users

Payload : { "username": "bob", "password": "secret", "role": "user", "authorized": 1 }

Réponse : { "success": true, "id": 2 }

4. Mettre à jour un utilisateur

PUT /api/users/{id}

Payload partiel (username, password, role, ssh_pubkey, authorized)

Réponse : { "success": true }

5. Obtenir toutes les clés SSH autorisées

GET /api/users/authorized-keys

Retourne un fichier texte contenant toutes les clés publiques des utilisateurs autorisés (accessible uniquement depuis localhost).
Un code `403` est renvoyé si l'appel n'est pas effectué en local.
Voir `docs/ssh_keys_walkthrough.md` pour un guide pas à pas.
Le script `resident_tools/ygs-UserKeysSync.sh` permet d'automatiser cette synchronisation.
Il ajoute les nouvelles clés sans supprimer celles déjà présentes dans `authorized_keys`.
Cette route est disponible à partir de `api/index.php` v3.10.4.

Meeting Users (Authentication)
------------------------------

La table `meeting_users` définit les comptes permettant de se connecter au service Meeting.

Colonnes principales :
- `id` INT auto_increment
- `username` VARCHAR(64) UNIQUE
- `role` ENUM('admin', 'user')
- `ssh_pubkey` TEXT optionnelle
- `authorized` TINYINT(1)
- `created_at` DATETIME
- `updated_at` DATETIME

Endpoints principaux :
1. **POST /api/auth/login** – retourne un jeton d'authentification.
   Payload : `{ "username": "alice", "password": "secret" }`.
2. **POST /api/auth/logout** – invalide le jeton actif (header `Authorization`).
3. **GET /api/auth/me** – informations sur l'utilisateur courant.

Workflow d'authentification :
1. L'administrateur crée un compte dans `admin/user_manager.php` et y associe la clé publique.
2. L'utilisateur se connecte via `/api/auth/login` pour obtenir son jeton.
3. Il charge sa clé privée dans `ssh-agent` ou Pageant pour un accès SSH transparent.

Global Config & Environment

Rôle

Centralise toute la configuration technique, de la BDD aux chemins de stockage, tokens, logfiles, sécurité, plage de ports, timeouts…

Permet le déploiement 100% automatisé et reproductible sur tout environnement (dev, prod, cloud, on-premise)

Principaux paramètres (/api/config.php)

db_host, db_name, db_user, db_pass, db_charset : connexion SQL

user_key_sync_script : script de synchronisation des clés utilisateurs

admin_user/admin_pass : accès temporaire admin

device_heartbeat_timeout : timeout disponibilité (s)

tunnel_requests_dir/tunnel_status_dir : chemins fichiers tunnels

tunnel_logfile/tunnel_debug_logfile : logs tunnels reverse

tunnel_host : nom d’hôte pour gén. URL de tunnel

forcecommand_port_min/port_max : plage de ports dynamiques

forcecommand_max_last_seen/reservation_duration : timeouts allocation tunnel/présence

flash_storage_root/storage_path : stockage firmware/distrib

key_sync_script : chemin script sync clés

server_pubkey_date/server_key_last_deploy : metadonnees de la cle serveur (generation, dernier deploiement)

metrics_logfile/metrics_api_url : logs et endpoints de supervision
user_keys_sync_logfile : log du script de synchronisation des cles utilisateurs

status_logfile/status_max_logs : logs de présence

device_logfile/device_note_logfile : logs par device
ygscreen_logfile : log du backend YGScreen (upload, playlist, erreurs ffmpeg)

Serveur NTP interne : permet la synchronisation horaire des devices.
NTP_PORT : port d'écoute (123 par défaut)
NTP_LOG : chemin du fichier de log
Script d'installation : tools/setup-files/install_ntp_server.sh
Script client : tools/setup-files/install_ygs_ntpclient.sh

Player / Digital Signage
------------------------

POST /api/player/upload

* Upload d'une vidéo pour un device. Paramètres `device_key`, `mode`, `order`, `title` et fichier `video`.
* Convertit la vidéo via ffmpeg (option `-f mp4` pour permettre des fichiers sans extension) puis stocke le fichier converti.
* Retourne `{ "ok": true, "hash": "<sha1>" }`.

GET /api/player/playlist/{device_key}

* Paramètre d'URL : `device_key`.
* Récupère le fichier `playlist.json` du device.
* Si la playlist n'existe pas, elle est créée avec les médias du dossier `medias_library/imposed_medias`.

GET /api/player/media/{device_key}/{dir}/{file}

* Paramètres d'URL : `device_key`, `dir`, `file`.
* Télécharge un média spécifique.

POST /api/player/clear-cache/{device_key}

* Paramètre d'URL : `device_key`.
* Supprime tous les médias du device (hors `playlist.json` et `default`).
* Retourne `{ "ok": true }`.

### Workflow complet
1. L'admin charge une vidéo avec `POST /api/player/upload`.
2. Le backend convertit la vidéo et met à jour la playlist.
3. L'agent récupère la playlist via `GET /api/player/playlist/{device_key}` puis télécharge chaque média via `GET /api/player/media/{device_key}/{dir}/{file}`.
4. En cas de nettoyage, `POST /api/player/clear-cache/{device_key}` efface le répertoire avant resynchronisation.


Bonnes pratiques

Versionner la config dans un repo privé

Ne jamais exposer/committer de secrets dans un repo public

Utiliser des variables d’environnement pour toutes les données critique