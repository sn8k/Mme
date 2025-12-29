<!-- File Version: 1.19.0 -->
# Motion Frontend - Documentation Technique Complète

> **Version** : 0.32.0  
> **Date de mise à jour** : 29 décembre 2025  
> **Plateformes cibles** : Windows (développement), Raspberry Pi OS Debian Trixie (production)

---

## Table des matières

1. [Vue d'ensemble](#1-vue-densemble)
2. [Architecture du projet](#2-architecture-du-projet)
3. [Backend Python/Tornado](#3-backend-pythontornado)
4. [Frontend HTML/CSS/JS](#4-frontend-htmlcssjs)
5. [Authentification](#5-authentification)
6. [API REST](#6-api-rest)
7. [Configuration et paramètres](#7-configuration-et-paramètres)
8. [Scripts d'installation et lancement](#8-scripts-dinstallation-et-lancement)
9. [Internationalisation (i18n)](#9-internationalisation-i18n)
10. [Versionnement des fichiers](#10-versionnement-des-fichiers)
11. [Guide de développement](#11-guide-de-développement)
12. [Dépannage](#12-dépannage)

---

## 1. Vue d'ensemble

### 1.1 Description du projet

**Motion Frontend** est une interface web de contrôle pour systèmes de vidéosurveillance basés sur Motion. Elle remplace l'interface legacy par une solution moderne, légère et responsive, servie par un backend Tornado sur Raspberry Pi.

### 1.2 Objectifs principaux

- Interface utilisateur moderne et responsive (vanilla HTML/CSS/JS via Jinja2)
- Cross-platform : développement Windows, déploiement Raspberry Pi
- Performance optimisée pour les contraintes CPU/RAM du Pi 3B+/4
- Internationalisation complète (fr/en/de/es/it)
- Versionnement strict par fichier (schéma `X.Y.Z`)

### 1.3 Stack technique

| Composant | Technologie |
|-----------|-------------|
| Backend | Python 3.11+, Tornado 6.x |
| Templates | Jinja2 |
| Frontend | HTML5, CSS3 (variables), JavaScript ES6+ (vanilla) |
| Authentification | Sessions sécurisées (cookies signés Tornado) |
| Persistance | JSON file (`config/motion_frontend.json`) |

---

## 2. Architecture du projet

### 2.1 Structure des répertoires

```
MmE/
├── backend/                    # Code serveur Python
│   ├── __init__.py
│   ├── audio_detector.py      # Détection audio cross-platform (v0.1.0)
│   ├── camera_detector.py     # Détection caméras cross-platform (v0.1.0)
│   ├── config_store.py        # Stockage configuration (v0.21.0)
│   ├── handlers.py            # Handlers HTTP Tornado (v0.22.0)
│   ├── jinja.py               # Configuration Jinja2 (v0.1.3)
│   ├── meeting_service.py     # Service Meeting API heartbeat (v0.4.0)
│   ├── mjpeg_server.py        # Serveur MJPEG streaming dédié (v0.9.0)
│   ├── rtsp_server.py         # Serveur RTSP avec FFmpeg (v0.3.0)
│   ├── server.py              # Point d'entrée serveur (v0.15.0)
│   ├── settings.py            # Paramètres serveur (v0.1.0)
│   ├── updater.py             # Module de mise à jour GitHub (v1.0.0)
│   └── user_manager.py        # Gestion utilisateurs bcrypt (v0.1.0)
│
├── config/                     # Fichiers de configuration persistés
│   ├── audio/                 # Configs individuelles des périphériques audio
│   │   └── {id}.json         # Configuration audio {id}
│   ├── cameras/               # Configs individuelles des caméras
│   │   ├── 1.json            # Configuration caméra 1
│   │   └── {id}.json         # Configuration caméra {id}
│   └── motion_frontend.json   # Configuration principale (sans caméras)
│
├── templates/                  # Templates Jinja2
│   ├── base.html              # Template de base (v0.2.0)
│   ├── login.html             # Page de connexion (v0.2.0)
│   ├── main.html              # Dashboard principal (v0.11.0)
│   ├── version.html           # Page version
│   └── manifest.json          # Web App Manifest
│
├── static/                     # Assets statiques
│   ├── css/
│   │   ├── ui.css             # Variables CSS et base (v0.2.2)
│   │   ├── main.css           # Styles dashboard (v0.10.0)
│   │   ├── login.css          # Styles login (v0.2.0)
│   │   └── frame.css          # Styles frame vidéo
│   ├── js/
│   │   ├── ui.js              # Utilitaires UI (v0.2.1)
│   │   ├── main.js            # Logique principale (v0.13.0)
│   │   ├── frame.js           # Gestion frames vidéo
│   │   ├── version.js         # Page version
│   │   └── motion_frontend.{lang}.json  # Catalogues i18n
│   ├── img/                   # Images et logos
│   ├── vendor/                # Librairies tierces
│   └── manifest.json          # PWA manifest
│
├── scripts/                    # Scripts d'automatisation
│   ├── install_motion_frontend.sh    # Installeur Raspberry Pi OS (v1.3.0)
│   ├── install_motion_frontend.ps1   # Installeur Windows
│   └── run_motion_frontend.ps1       # Lanceur développement
│
├── docs/                       # Documentation
│   ├── agents.md              # Rôles et responsabilités
│   ├── cahier_des_charges.md  # Spécifications
│   └── TECHNICAL_DOCUMENTATION.md  # Ce document
│
├── TODOs/                      # Suivi des tâches
│   └── TODO_frontend.md
│
├── CHANGELOG.md               # Historique des versions (v0.30.0)
└── README.md                  # Guide de démarrage (v0.4.0)
```
### 2.2 Diagramme de flux

```
┌─────────────┐     HTTP      ┌─────────────────┐
│   Browser   │ ◄───────────► │  Tornado Server │
└─────────────┘               └────────┬────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    │                  │                  │
              ┌─────▼─────┐    ┌───────▼───────┐   ┌──────▼──────┐
              │  Handlers │    │  ConfigStore  │   │   Jinja2    │
              └───────────┘    └───────────────┘   └─────────────┘
                    │                  │
              ┌─────▼─────┐    ┌───────▼───────┐
              │  API REST │    │  JSON File    │
              └───────────┘    └───────────────┘
```

---

## 3. Backend Python/Tornado

### 3.1 Point d'entrée : `server.py`

Le serveur Tornado est démarré via `backend/server.py` :

```python
# Lancement direct
python -m backend.server --host 0.0.0.0 --port 8765

# Options disponibles
--host          # Interface réseau (défaut: 0.0.0.0)
--port          # Port d'écoute (défaut: 8765)
--root          # Racine du projet
--template-path # Chemin des templates (défaut: templates)
--static-path   # Chemin des assets (défaut: static)
--environment   # Environnement (development/production/staging)
--log-level     # Niveau de log (DEBUG/INFO/WARNING/ERROR/CRITICAL)
```

### 3.2 Handlers HTTP (`handlers.py`)

| Handler | Route | Méthode | Description |
|---------|-------|---------|-------------|
| `LoginHandler` | `/login` | GET/POST | Page de connexion |
| `LogoutHandler` | `/logout` | GET | Déconnexion |
| `MainHandler` | `/` | GET | Dashboard principal (authentifié) |
| `VersionHandler` | `/version` | GET | Informations de version (JSON) |
| `ConfigMainHandler` | `/api/config/main/` | GET/POST | Configuration générale |
| `ConfigListHandler` | `/api/config/list/` | GET | Liste des caméras |
| `ConfigCameraHandler` | `/api/config/camera/{id}/` | GET/POST | Configuration caméra |
| `LoggingConfigHandler` | `/api/logging/` | POST | Niveau de log |
| `HealthHandler` | `/health` | GET | Healthcheck |
| `FrameHandler` | `/frame/{id}/` | GET | Frame vidéo (PNG) |

### 3.3 ConfigStore (`config_store.py`)

Classe de stockage en mémoire gérant :

- **Général** : hostname, langue, versions, comptes admin/utilisateur
- **Affichage** : nombre de previews (1-32), qualité
- **Réseau** : Wi-Fi principal/secours, mode IP (DHCP/statique)
- **Caméras** : liste, configuration par caméra
- **Backup** : sauvegarde/restauration

```python
class ConfigStore:
    def get_main_config() -> Dict[str, List[Dict]]
    def get_cameras() -> List[Dict]
    def get_camera_config(camera_id: str) -> Dict
    def save_main_config(payload: Dict) -> Dict
    def save_camera_config(camera_id: str, payload: Dict) -> Dict
```

### 3.4 Jinja2 (`jinja.py`)

Configuration de l'environnement Jinja2 :

- **Autoescaping** : activé pour HTML/XML
- **Extensions** : `jinja2.ext.do` (pour éviter shadowing de `_()`)
- **Globals** : fonction `_()` pour traduction (stub identity)

---

## 4. Frontend HTML/CSS/JS

### 4.1 Templates Jinja2

#### `base.html` (v0.2.0)
Template parent définissant :
- Métadonnées HTML5
- Chargement CSS/JS vendor (jQuery, Gettext, Timepicker)
- Blocs extensibles : `title`, `styles`, `body`, `scripts`

#### `login.html` (v0.2.0)
Page de connexion avec :
- Formulaire login/password
- Checkbox "Se souvenir de moi" (cookie 30 jours)
- Messages d'erreur stylisés

#### `main.html` (v0.4.2)
Dashboard principal avec :
- Header : logo, sélecteur caméra, boutons action, déconnexion
- Sidebar rétractable : configuration par sections
- Zone preview : grille adaptative 1/2/4/8/16/32 caméras
- Status bar : FPS, résolution, bande passante

### 4.2 Styles CSS

#### Variables CSS (`ui.css`)

```css
:root {
    --bg: #0c0e14;
    --bg-elevated: #161b27;
    --border: #2b3142;
    --text: #f3f6ff;
    --text-muted: #a6b0c8;
    --accent: #2ec4ff;
    --danger: #ff4d6d;
    --success: #2be0a0;
}

body.theme-light {
    --bg: #f5f7fa;
    --bg-elevated: #ffffff;
    /* ... */
}
```

#### Layout principal (`main.css`)

- **Grid CSS** : sidebar + preview area
- **Sidebar** : 320-420px, rétractable
- **Preview Grid** : adaptatif selon `data-preview-count`
- **Responsive** : breakpoint 1024px (sidebar overlay mobile)

### 4.3 JavaScript

#### `ui.js` (v0.2.1)
Utilitaires globaux :
- `motionFrontendUI.onReady(callback)` : file d'attente DOMContentLoaded
- `motionFrontendUI.setStatus(message)` : mise à jour status bar
- `motionFrontendUI.showToast(message, type)` : notifications toast

#### `main.js` (v0.5.0)
Logique principale :
- Gestion état (`state.cameraId`, `state.isDirty`, etc.)
- API fetch avec credentials
- Toggle sidebar/theme
- Dirty tracking (bouton sauvegarde conditionnel)
- Grille preview dynamique

```javascript
// Fonctions principales
loadMainConfig()        // Charge config générale
loadCameraConfig(id)    // Charge config caméra
pushConfigs(payload)    // Sauvegarde configuration
updatePreviewGrid()     // Met à jour grille previews
checkDirty()           // Vérifie modifications
```

---

## 5. Authentification

### 5.1 Système de gestion des utilisateurs

Le module `user_manager.py` (v0.1.0) gère l'authentification avec hachage sécurisé des mots de passe.

#### Architecture

```python
from backend.user_manager import get_user_manager, UserRole

# Singleton pour accès global
manager = get_user_manager()

# Authentification
user = manager.authenticate("admin", "password")
if user:
    print(f"Connected as {user.username} ({user.role.value})")
```

#### Modèle User

```python
@dataclass
class User:
    username: str
    password_hash: str
    role: UserRole  # ADMIN, USER, VIEWER
    enabled: bool = True
    must_change_password: bool = False
    created_at: str = ""
    last_login: Optional[str] = None
```

### 5.2 Hachage des mots de passe

- **Algorithme principal** : bcrypt (12 rounds)
- **Fallback** : SHA256 si bcrypt non disponible
- **Migration** : hashes SHA256 legacy sont convertis en bcrypt à la connexion

```python
# Hachage avec bcrypt (recommandé)
hash = manager._hash_password("mypassword")
# -> "$2b$12$..."

# Vérification (détecte automatiquement bcrypt ou SHA256)
manager._verify_password("mypassword", hash)
```

### 5.3 Flux de connexion

1. Utilisateur accède à `/` → redirection `/login` si non authentifié
2. POST `/login` avec `username`, `password`, `remember_me`
3. Appel `UserManager.authenticate()` :
   - Vérifie utilisateur existe et est activé
   - Vérifie mot de passe (bcrypt ou SHA256)
   - Met à jour `last_login`
   - Migre hash SHA256 → bcrypt si nécessaire
4. Création session avec token aléatoire (64 hex chars)
5. Cookie sécurisé `session_id` (httponly)
   - `remember_me` coché : expire dans 30 jours
   - Non coché : cookie de session
6. Si `must_change_password` : redirection vers `/?change_password=1`

### 5.4 Rôles utilisateur

| Rôle | Valeur | Permissions |
|------|--------|-------------|
| ADMIN | `admin` | Toutes (gestion utilisateurs, config système) |
| USER | `user` | Configuration caméras, visualisation |
| VIEWER | `viewer` | Visualisation seule |

### 5.5 Utilisateurs par défaut

| Username | Password | Rôle |
|----------|----------|------|
| admin | admin | ADMIN |

⚠️ **À changer en production !** Lors de la première connexion, le flag `must_change_password` force le changement.

### 5.6 Stockage utilisateurs

Fichier `config/users.json` :
```json
{
    "admin": {
        "username": "admin",
        "password_hash": "$2b$12$...",
        "role": "admin",
        "enabled": true,
        "must_change_password": true,
        "created_at": "2025-01-14T10:00:00",
        "last_login": "2025-01-14T12:30:00"
    }
}
```

### 5.7 API de gestion des mots de passe

#### Changer son mot de passe
```
POST /api/user/password/
{
    "current_password": "oldpass",
    "new_password": "newpass",
    "confirm_password": "newpass"
}
```

#### Reset admin (admin uniquement)
```
POST /api/users/reset-password/
{
    "username": "john",
    "new_password": "temppass",
    "must_change_password": true
}
```

### 5.8 Déconnexion

GET `/logout` :
1. Suppression session du store
2. Suppression cookie `session_id`
3. Redirection vers `/login`

---

## 6. API REST

### 6.1 Endpoints publics

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `/health` | GET | `{"status": "ok"}` |
| `/version` | GET | Versions frontend/backend |
| `/login` | GET/POST | Authentification |

### 6.2 Endpoints authentifiés

#### Utilisateur courant
```
GET  /api/user/me/
POST /api/user/password/
```

**Réponse GET /api/user/me/** :
```json
{
    "username": "admin",
    "role": "admin",
    "enabled": true,
    "must_change_password": false,
    "created_at": "2025-01-14T10:00:00",
    "last_login": "2025-01-14T12:30:00"
}
```

#### Gestion des utilisateurs (admin uniquement)
```
GET    /api/users/           # Liste tous les utilisateurs
POST   /api/users/           # Créer un utilisateur
DELETE /api/users/           # Supprimer un utilisateur
POST   /api/users/reset-password/  # Reset mot de passe
POST   /api/users/enable/    # Activer/désactiver utilisateur
```

#### Configuration générale
```
GET  /api/config/main/
POST /api/config/main/
```

**Réponse GET** :
```json
{
    "general": [...],
    "display_settings": [...],
    "network_manager": [...],
    "backup": [...]
}
```

#### Liste des caméras
```
GET /api/config/list/
```

**Réponse** :
```json
{
    "cameras": [
        {"id": "1", "name": "Workshop", "enabled": true},
        {"id": "2", "name": "Warehouse", "enabled": true}
    ]
}
```

#### Configuration caméra
```
GET  /api/config/camera/{camera_id}/
POST /api/config/camera/{camera_id}/
```

#### Ajout de caméra
```
POST /api/config/camera/add/
```

**Corps de la requête** :
```json
{
    "name": "Nouvelle caméra",
    "device_url": "rtsp://192.168.1.100/stream"
}
```

**Réponse** :
```json
{
    "status": "ok",
    "camera": {
        "id": "3",
        "name": "Nouvelle caméra",
        "enabled": true
    }
}
```

#### Suppression de caméra
```
DELETE /api/config/camera/{camera_id}/delete/
```

**Réponse** :
```json
{
    "status": "ok",
    "removed": "3"
}
```

#### Détection automatique de caméras
```
GET /api/cameras/detect/
GET /api/cameras/detect/?include_filtered=true
```

**Réponse** :
```json
{
    "cameras": [
        {
            "device_path": "0",
            "name": "Microsoft LifeCam HD-5000",
            "driver": "Image",
            "bus_info": "USB\\VID_045E&PID_076D...",
            "capabilities": [],
            "is_capture_device": true,
            "source_type": "dshow"
        }
    ],
    "filter_patterns": ["bcm2835-isp", "unicam"],
    "platform": "windows"
}
```

**Plateformes supportées** :
- **Windows** : DirectShow via WMI/PowerShell, fallback ffmpeg ou OpenCV
- **Linux** : v4l2 via `v4l2-ctl`, fallback scan `/dev/video*`

**Types de sources** (`source_type`) :
- `dshow` : DirectShow (Windows)
- `v4l2` : Video4Linux2 (Linux)
- `usb` : Webcam USB (Linux)
- `csi` : Interface CSI Raspberry Pi

#### Détection des capacités d'une caméra
```
GET /api/cameras/capabilities/<device_path>
```

**Exemple de réponse** :
```json
{
  "supported_resolutions": ["640x480", "800x600", "1280x720", "1920x1080"],
  "current_resolution": "640x480",
  "max_fps": 30,
  "backend": "DirectShow",
  "error": null
}
```

Cette API permet de découvrir dynamiquement les résolutions supportées par une caméra pour proposer des options adaptées dans l'interface.

#### Gestion des filtres de caméras
```
GET    /api/cameras/filters/     # Liste les patterns de filtre
POST   /api/cameras/filters/     # Remplace tous les patterns
PUT    /api/cameras/filters/     # Ajoute un pattern
DELETE /api/cameras/filters/     # Supprime un pattern
```

**Exemples** :

Ajouter un filtre :
```json
PUT /api/cameras/filters/
{"pattern": "DeskJet|scanner"}
```

Supprimer un filtre :
```json
DELETE /api/cameras/filters/
{"pattern": "bcm2835-isp"}
```

**Patterns par défaut** (Raspberry Pi) :
- `bcm2835-isp` : ISP du Pi (pas une vraie caméra)
- `unicam` : Interface CSI interne
- `rp1-cfe` : Interface CSI du Pi 5

#### Détection automatique de périphériques audio
```
GET /api/audio/detect/
GET /api/audio/detect/?include_filtered=true
```

**Réponse** :
```json
{
    "devices": [
        {
            "device_id": "hw:0,0",
            "name": "HDA Intel PCH: ALC892 Analog",
            "driver": "snd_hda_intel",
            "card_number": "0",
            "device_number": "0",
            "channels": 2,
            "sample_rate": 48000,
            "is_input": true,
            "source_type": "alsa"
        }
    ],
    "filter_patterns": ["hdmi", "spdif"],
    "platform": "linux"
}
```

**Plateformes supportées** :
- **Windows** : PowerShell/WMI (Get-PnpDevice, Get-CimInstance), fallback FFmpeg DirectShow
- **Linux** : ALSA via `arecord -l` et `arecord -L`, fallback `/proc/asound/cards`

**Types de sources** (`source_type`) :
- `dshow` : DirectShow (Windows)
- `wasapi` : Windows Audio Session API
- `alsa` : Advanced Linux Sound Architecture
- `usb_audio` : Périphérique USB audio

#### Liste des périphériques audio configurés
```
GET /api/config/audio/list/
```

**Réponse** :
```json
{
    "devices": [
        {"id": "1", "name": "Microphone USB", "enabled": true},
        {"id": "2", "name": "Micro Webcam", "enabled": false}
    ]
}
```

#### Configuration d'un périphérique audio
```
GET  /api/config/audio/{audio_id}/
POST /api/config/audio/{audio_id}/
```

**Réponse GET** :
```json
{
    "identifier": "1",
    "name": "Microphone USB",
    "enabled": true,
    "device_id": "hw:1,0",
    "sample_rate": 48000,
    "channels": 2,
    "bit_depth": 16,
    "volume": 80,
    "noise_reduction": true,
    "codec": "aac",
    "bitrate": 128,
    "linked_camera_id": "1"
}
```

#### Sections de configuration audio (pour UI)
```
GET /api/config/audio/{audio_id}/sections/
```

Retourne les sections de configuration formatées pour l'affichage dynamique dans l'UI.

#### Ajout d'un périphérique audio
```
POST /api/config/audio/add/
```

**Corps de la requête** :
```json
{
    "name": "Nouveau microphone",
    "device_id": "hw:1,0"
}
```

**Réponse** :
```json
{
    "status": "ok",
    "device": {
        "id": "1",
        "name": "Nouveau microphone",
        "enabled": true
    }
}
```

#### Suppression d'un périphérique audio
```
POST /api/config/audio/{audio_id}/delete/
```

**Réponse** :
```json
{
    "status": "ok",
    "removed": "1"
}
```

#### Gestion des filtres de périphériques audio
```
GET  /api/audio/filters/     # Liste les patterns de filtre
POST /api/audio/filters/     # Ajoute ou supprime un pattern
```

**Ajouter un filtre** :
```json
POST /api/audio/filters/
{"action": "add", "pattern": "hdmi|spdif"}
```

**Supprimer un filtre** :
```json
POST /api/audio/filters/
{"action": "remove", "pattern": "hdmi"}
```

**Patterns par défaut** :
- `hdmi` : Sorties HDMI (pas des entrées)
- `spdif` : Sorties numériques S/PDIF
- `monitor` : Périphériques de monitoring

#### API RTSP Streaming
```
GET  /api/rtsp/                    # Statut serveur RTSP et disponibilité FFmpeg
GET  /api/rtsp/{camera_id}/        # Statut du stream RTSP pour une caméra
POST /api/rtsp/{camera_id}/        # Démarrer/arrêter le stream RTSP
```

**Réponse GET /api/rtsp/** :
```json
{
    "ffmpeg_available": true,
    "ffmpeg_version": "6.1.1",
    "streams": {
        "1": {
            "camera_id": "1",
            "is_running": true,
            "rtsp_url": "rtsp://{host}:8554/cam1",
            "has_audio": true,
            "error": null,
            "started_at": "2025-12-29T14:30:00"
        }
    }
}
```

**Démarrer un stream RTSP** :
```json
POST /api/rtsp/1/
{
    "action": "start",
    "video_bitrate": 2000
}
```

**Réponse** :
```json
{
    "status": "ok",
    "camera_id": "1",
    "is_running": true,
    "rtsp_url": "rtsp://{host}:8554/cam1",
    "has_audio": true,
    "rtsp_port": 8554,
    "error": null
}
```

**Arrêter un stream RTSP** :
```json
POST /api/rtsp/1/
{"action": "stop"}
```

**Fonctionnement** :
- Utilise FFmpeg pour capturer vidéo (V4L2/DirectShow) et audio (ALSA/DirectShow).
- Encode en H.264 (libx264) avec preset `ultrafast` et tune `zerolatency` pour faible latence.
- Audio encodé en AAC, Opus, MP3 ou PCM selon la configuration du périphérique audio lié.
- Chaque caméra a son propre port RTSP : `8554 + (camera_id - 1)`.
- Le flux audio est automatiquement muxé si un périphérique audio est lié à la caméra (`linked_camera_id`).

**Prérequis** :
- FFmpeg doit être installé et accessible dans le PATH.
- Sur Windows : FFmpeg avec support DirectShow.
- Sur Linux : FFmpeg avec support V4L2 et ALSA.

#### API Meeting (heartbeat)
```
GET  /api/meeting/     # Statut du service Meeting
POST /api/meeting/     # Contrôle du service
```

#### API Update (GitHub releases)
```
GET  /api/update/                    # Vérifier les mises à jour disponibles
POST /api/update/                    # Exécuter une action de mise à jour
```

**Vérifier les mises à jour** :
```
GET /api/update/
GET /api/update/?include_prereleases=true
```

**Réponse** :
```json
{
    "current_version": "0.27.0",
    "latest_version": "0.28.0",
    "update_available": true,
    "latest_release": {
        "tag_name": "v0.28.0",
        "version": "0.28.0",
        "name": "Release 0.28.0",
        "body": "### New Features\n- GitHub update functionality...",
        "published_at": "2025-12-29T10:00:00Z",
        "html_url": "https://github.com/sn8k/Mme/releases/tag/v0.28.0",
        "zipball_url": "https://api.github.com/repos/sn8k/Mme/zipball/v0.28.0",
        "prerelease": false
    },
    "error": null
}
```

**Exécuter une mise à jour** :
```json
POST /api/update/
{
    "action": "update",
    "include_prereleases": false
}
```

**Réponse** :
```json
{
    "success": true,
    "message": "Successfully updated from 0.27.0 to 0.28.0. Please restart the server.",
    "old_version": "0.27.0",
    "new_version": "0.28.0",
    "requires_restart": true,
    "error": null
}
```

**Actions disponibles** :
- `check` : Vérifier les mises à jour disponibles (par défaut)
- `update` : Télécharger et appliquer la mise à jour depuis les releases
- `check_source` : Vérifier les informations du code source (branche)
- `update_source` : Mettre à jour depuis le code source (branche main)
- `status` : Obtenir le statut actuel de mise à jour

**Mise à jour depuis le code source (développement)** :

Permet de mettre à jour directement depuis une branche Git (par défaut `main`) pour obtenir les dernières modifications de développement, même sans release officielle.

```json
POST /api/update/
{
    "action": "check_source",
    "branch": "main"
}
```

**Réponse** :
```json
{
    "current_version": "0.28.0",
    "branch": "main",
    "source_info": {
        "branch": "main",
        "commit_sha": "abc1234",
        "commit_message": "Fix: resolve camera detection issue",
        "commit_date": "2025-12-29T15:30:00Z",
        "html_url": "https://github.com/sn8k/Mme/tree/main",
        "zipball_url": "https://github.com/sn8k/Mme/archive/refs/heads/main.zip"
    },
    "error": null
}
```

**Exécuter une mise à jour depuis le source** :
```json
POST /api/update/
{
    "action": "update_source",
    "branch": "main"
}
```

**Fonctionnement** :
1. Vérifie la dernière release sur GitHub (https://github.com/sn8k/Mme)
2. Compare les versions avec le semantic versioning (X.Y.Z avec suffixe lettre optionnel)
3. Télécharge l'archive ZIP de la release
4. Crée une sauvegarde automatique dans `backups/`
5. Extrait et applique les fichiers (sauf `config/` pour préserver les paramètres utilisateur)
6. Exécute `pip install -r requirements.txt` pour les nouvelles dépendances
7. Nécessite un redémarrage du serveur pour appliquer les changements

**Configuration optionnelle** :
- Variable d'environnement `GITHUB_TOKEN` : Token GitHub pour augmenter la limite de requêtes API (60 → 5000 req/h)

**Fichiers mis à jour** :
- `backend/` : Code serveur
- `static/` : Assets frontend
- `templates/` : Templates Jinja2
- `docs/` : Documentation
- `scripts/` : Scripts d'installation
- `requirements.txt`, `CHANGELOG.md`, `README.md`, `agents.md`

**Fichiers préservés** :
- `config/` : Configuration utilisateur (caméras, audio, paramètres)
- `logs/` : Journaux d'exécution
- `backups/` : Sauvegardes précédentes

**Actions POST disponibles** :

| Action | Description |
|--------|-------------|
| `start` | Démarre le service heartbeat |
| `stop` | Arrête le service heartbeat |
| `heartbeat` | Envoie un heartbeat manuel (test) |
| `configure` | Reconfigure le service avec les paramètres actuels |

**Exemple démarrage** :
```json
POST /api/meeting/
{"action": "start"}
```

**Réponse** :
```json
{
    "status": "ok",
    "service": {
        "enabled": true,
        "is_running": true,
        "server_url": "https://meeting.example.com",
        "device_key": "ABCDEF123456",
        "heartbeat_interval": 60,
        "last_heartbeat": "2025-12-28T14:30:00",
        "last_heartbeat_success": true,
        "last_error": null
    }
}
```

**Protocole Meeting** :
Le service envoie périodiquement un POST à l'endpoint Meeting :
```
POST {server_url}/api/devices/{device_key}/online
```

**Payload heartbeat** :
```json
{
    "ip_address": "192.168.1.100",
    "services": {"ssh": 0, "http": 1, "vnc": 0},
    "note": "Motion Frontend - 2025-12-28 14:30:00"
}
```

#### Frame vidéo
```
GET /frame/{camera_id}/
```
Retourne image PNG (placeholder en dev).

---

## 7. Configuration et paramètres

### 7.1 Persistance de configuration

La configuration est stockée dans un fichier JSON externe : `config/motion_frontend.json`.

#### Caractéristiques :
- **Chargement automatique** au démarrage du serveur
- **Création automatique** si le fichier est absent (avec valeurs par défaut)
- **Sauvegarde automatique** après chaque modification
- **Non-bloquant** : l'absence du fichier ne provoque pas d'erreur

#### Structure du fichier JSON :

```json
{
  "version": "1.0",
  "hostname": "motion-frontend-dev",
  "theme": "dark",
  "language": "fr",
  "logging_level": "INFO",
  "display": {
    "preview_count": 4,
    "preview_quality": "medium"
  },
  "network": {
    "wifi_ssid": "",
    "wifi_password": "",
    "wifi_fallback_ssid": "",
    "wifi_fallback_password": "",
    "wifi_interface": "wlan0",
    "ip_mode": "dhcp",
    "static_ip": "",
    "static_gateway": "",
    "static_dns": ""
  },
  "auth": {
    "admin_username": "admin",
    "admin_password": "",
    "user_username": "user",
    "user_password": ""
  },
  "camera_filter_patterns": [
    "bcm2835-isp",
    "unicam",
    "rp1-cfe"
  ],
  "audio_filter_patterns": [
    "hdmi",
    "spdif",
    "monitor"
  ],
  "meeting": {
    "server_url": "",
    "device_key": "",
    "token_code": "",
    "heartbeat_interval": 60
  }
}
```

> **Note** : Les caméras et périphériques audio ne sont plus stockés dans la configuration principale. Chaque caméra a son propre fichier dans `config/cameras/{id}.json` et chaque périphérique audio dans `config/audio/{id}.json`.

### 7.2 Configuration individuelle des caméras

Chaque caméra est stockée dans un fichier JSON séparé : `config/cameras/{id}.json`

```json
{
  "identifier": "1",
  "name": "Camera Entrée",
  "enabled": true,
  "device_settings": {
    "device": "/dev/video0"
  },
  "stream_url": "",
  "mjpeg_port": 8081,
  "resolution": "1280x720",
  "framerate": 15,
  "rotation": 0,
  "brightness": 0,
  "contrast": 0,
  "saturation": 0,
  "stream_resolution": "1280x720",
  "stream_framerate": 15,
  "jpeg_quality": 80,
  "motion_detection_enabled": true,
  "motion_threshold": 1500,
  "motion_frames": 1,
  "record_movies": true,
  "record_stills": false,
  "pre_capture": 0,
  "post_capture": 0
}
```

#### Résolution Capture vs Stream

| Paramètre | Rôle | Exemple |
|-----------|------|---------|
| `resolution` | Résolution de capture (input) | Caméra capture en 1920x1080 |
| `stream_resolution` | Résolution de sortie MJPEG (output) | Stream diffusé en 1280x720 |

**Workflow interne** :
1. Capture de la frame à `resolution` (ex: 1920x1080)
2. `cv2.resize()` vers `stream_resolution` (ex: 1280x720)
3. Application du text overlay sur la frame redimensionnée
4. Encodage JPEG et diffusion

Ceci permet de capturer en haute résolution pour une meilleure qualité de détection de mouvement tout en diffusant à une résolution plus basse pour économiser la bande passante.
```

#### Méthodes ConfigStore :
| Méthode | Description |
|---------|-------------|
| `_load_config()` | Charge la config principale depuis le fichier JSON |
| `_load_all_cameras()` | Charge toutes les configs caméras depuis `config/cameras/` |
| `_load_all_audio_devices()` | Charge toutes les configs audio depuis `config/audio/` |
| `_save_config()` | Sauvegarde la config principale |
| `_save_camera_config(id)` | Sauvegarde une config caméra individuelle |
| `_save_audio_config(id)` | Sauvegarde une config audio individuelle |
| `save_now()` | Force une sauvegarde immédiate |
| `reload()` | Recharge la config depuis le disque |
| `add_camera()` | Ajoute une caméra (crée son fichier JSON) |
| `remove_camera()` | Supprime une caméra (supprime son fichier JSON) |
| `add_audio_device()` | Ajoute un périphérique audio (crée son fichier JSON) |
| `remove_audio_device()` | Supprime un périphérique audio (supprime son fichier JSON) |
| `get_camera_filter_patterns()` | Retourne les patterns de filtre caméras |
| `set_camera_filter_patterns()` | Définit les patterns de filtre caméras |
| `get_audio_filter_patterns()` | Retourne les patterns de filtre audio |
| `add_audio_filter_pattern()` | Ajoute un pattern de filtre audio |
| `remove_audio_filter_pattern()` | Supprime un pattern de filtre audio |

### 7.3 Configuration individuelle des périphériques audio

Chaque périphérique audio est stocké dans un fichier JSON séparé : `config/audio/{id}.json`

```json
{
  "identifier": "1",
  "name": "Microphone USB",
  "enabled": true,
  "device_id": "hw:1,0",
  "sample_rate": 48000,
  "channels": 2,
  "bit_depth": 16,
  "volume": 80,
  "noise_reduction": false,
  "codec": "aac",
  "bitrate": 128,
  "linked_camera_id": ""
}
```

#### Paramètres de configuration audio :
| Paramètre | Type | Valeur par défaut | Description |
|-----------|------|-------------------|-------------|
| `identifier` | str | Auto-généré | Identifiant unique du périphérique |
| `name` | str | - | Nom d'affichage |
| `enabled` | bool | `true` | Périphérique actif |
| `device_id` | str | - | Identifiant système (ex: `hw:0,0`, chemin ALSA) |
| `sample_rate` | int | `48000` | Fréquence d'échantillonnage (Hz) |
| `channels` | int | `2` | Nombre de canaux (1=mono, 2=stéréo) |
| `bit_depth` | int | `16` | Profondeur en bits (8, 16, 24, 32) |
| `volume` | int | `80` | Volume de capture (0-100) |
| `noise_reduction` | bool | `false` | Activer la réduction de bruit |
| `codec` | str | `"aac"` | Codec audio (aac, opus, mp3, pcm) |
| `bitrate` | int | `128` | Bitrate en kbps |
| `linked_camera_id` | str | `""` | ID de la caméra liée (pour sync A/V) |

### 7.4 Sections de configuration

#### General Settings
| Paramètre | Type | Description |
|-----------|------|-------------|
| `frontendVersion` | str (readonly) | Version du frontend |
| `motionVersion` | str (readonly) | Version de Motion |
| `updateStatus` | str (readonly) | État des mises à jour |
| `hostname` | str | Nom d'hôte système |
| `language` | choices | Langue (fr/en/de/es/it) |
| `adminUsername` | str | Login administrateur |
| `adminPassword` | pwd | Mot de passe admin |
| `userUsername` | str | Login utilisateur |
| `userPassword` | pwd | Mot de passe utilisateur |

#### Display Settings
| Paramètre | Type | Description |
|-----------|------|-------------|
| `previewCount` | choices | Nombre de previews (1/2/4/8/16/32) |
| `previewQuality` | choices | Qualité (low/medium/high) |

#### Network Manager
| Paramètre | Type | Description |
|-----------|------|-------------|
| `wifiSsid` | str | SSID Wi-Fi principal |
| `wifiPassword` | pwd | Mot de passe Wi-Fi |
| `wifiFallbackSsid` | str | SSID Wi-Fi secours |
| `wifiFallbackPassword` | pwd | Mot de passe secours |
| `wifiInterface` | choices | Interface (wlan0/wlan1) |
| `ipMode` | choices | Mode IP (dhcp/static) |
| `staticIp` | str | Adresse IP statique |
| `staticGateway` | str | Passerelle |
| `staticDns` | str | Serveur DNS |

#### Meeting (Service de présence)
| Paramètre | Type | Description |
|-----------|------|-------------|
| `meetingServerUrl` | str | URL du serveur Meeting (ex: https://meeting.example.com) |
| `meetingDeviceKey` | str | Clé unique du device (fournie par Meeting) |
| `meetingTokenCode` | pwd | Token d'authentification Meeting |
| `meetingHeartbeatInterval` | number | Intervalle heartbeat en secondes (10-3600) |
| `meetingStatus` | html | Indicateur de statut du service |

**Fonctionnement du service Meeting** :

Le service Meeting fonctionne **en permanence** dès qu'il est configuré. Il envoie périodiquement un signal de présence ("heartbeat") au serveur Meeting pour indiquer que l'appareil est en ligne.

**Workflow** :
1. L'utilisateur configure les paramètres Meeting (URL serveur, device key, token)
2. Le service démarre **automatiquement** dès que l'URL et la Device Key sont renseignées
3. À chaque intervalle configuré, un heartbeat est envoyé
4. Le statut est affiché en temps réel dans l'interface :
   - **Non configuré** : URL ou Device Key manquante
   - **Connexion en cours...** : Démarrage du service
   - **✓ Connecté** : Dernier heartbeat réussi
   - **⚠ Erreur** : Échec du heartbeat (avec message)

**Payload envoyé au serveur Meeting** :
```json
{
    "ip_address": "192.168.1.100",
    "services": {"ssh": 0, "http": 1, "vnc": 0},
    "note": "Motion Frontend - 2025-12-28 14:30:00"
}
```

### 7.5 Sections de configuration caméra

Les configurations caméra sont organisées en sections thématiques dans l'interface UI :

#### Périphérique (`camera_device`)
| Paramètre | Type | Description |
|-----------|------|-------------|
| `deviceName` | str | Nom de la caméra |
| `deviceUrl` | str | Source vidéo (URL RTSP ou chemin device) |

#### Paramètres vidéo (`camera_video`) — Capture/Entrée
| Paramètre | Type | Description |
|-----------|------|-------------|
| `resolution` | choices | Résolution de capture (VGA à 4K) |
| `framerate` | number | Images/sec capture (1-60) |
| `rotation` | choices | Rotation image (0°/90°/180°/270°) |

#### Image (`camera_image`)
| Paramètre | Type | Description |
|-----------|------|-------------|
| `brightness` | range | Luminosité (-100 à 100) |
| `contrast` | range | Contraste (-100 à 100) |
| `saturation` | range | Saturation (-100 à 100) |

#### Streaming (`camera_streaming`) — Sortie MJPEG
| Paramètre | Type | Description |
|-----------|------|-------------|
| `streamEnabled` | bool | Activer/désactiver le streaming |
| `mjpegPort` | number | Port HTTP dédié du stream MJPEG (8081 par défaut, chaque caméra son port) |
| `streamUrl` | html (readonly) | URL complète du stream dédié: `http://<ip>:<mjpeg_port>/stream/` |
| `streamResolution` | choices | Résolution de sortie (QVGA à 1080p) |
| `streamFramerate` | number | FPS de sortie (1-30) |
| `jpegQuality` | range | Qualité JPEG (10-100%) |

> **Note Architecture MJPEG** (v0.22.0) : Chaque caméra dispose de son propre serveur HTTP dédié sur un port configurable. Cam 1 = port 8081, Cam 2 = port 8082, etc. Les clients externes (VLC, Synology Surveillance Station, ONVIF) doivent utiliser l'URL dédiée `http://<ip>:<mjpeg_port>/stream/`. La preview dans l'interface web utilise le serveur Tornado principal comme fallback.

> **Note Performance** : La séparation capture/streaming permet d'optimiser la bande passante en capturant à haute résolution pour l'enregistrement tout en diffusant à résolution réduite pour le monitoring réseau.

#### Détection de mouvement (`camera_motion`)
| Paramètre | Type | Description |
|-----------|------|-------------|
| `motionEnabled` | bool | Activer détection mouvement |
| `motionThreshold` | number | Seuil de détection (1-100000) |
| `motionFrames` | number | Images consécutives requises (1-100) |

#### Enregistrement (`camera_recording`)
| Paramètre | Type | Description |
|-----------|------|-------------|
| `recordMovies` | bool | Enregistrer les vidéos |
| `recordStills` | bool | Enregistrer des images fixes |
| `preCapture` | number | Secondes avant événement (0-60) |
| `postCapture` | number | Secondes après événement (0-300) |

### 7.6 Types de champs supportés

| Type | Rendu HTML | Description |
|------|------------|-------------|
| `str` | `<input type="text">` | Texte simple |
| `pwd` | `<input type="password">` | Mot de passe |
| `number` | `<input type="number">` | Numérique |
| `bool` | `<input type="checkbox">` | Booléen |
| `choices` | `<select>` | Liste déroulante |
| `range` | `<input type="range">` | Slider |
| `separator` | `<h4>` | Séparateur visuel |
| `html` | Raw HTML | Contenu personnalisé |

---

## 8. Scripts d'installation et lancement

### 8.1 Installeur Raspberry Pi OS (`install_motion_frontend.sh`)

Script shell complet pour l'installation automatisée sur Raspberry Pi OS (Debian Trixie).

#### 8.1.1 Installation rapide

```bash
# Installation avec la branche main (défaut)
curl -sSL https://raw.githubusercontent.com/sn8k/Mme/main/scripts/install_motion_frontend.sh | sudo bash
```

#### 8.1.2 Installation avec choix de branche

```bash
# Affiche un menu interactif pour choisir la branche
curl -sSL https://raw.githubusercontent.com/sn8k/Mme/main/scripts/install_motion_frontend.sh | sudo bash -s -- --branch
```

#### 8.1.3 Désinstallation

```bash
curl -sSL https://raw.githubusercontent.com/sn8k/Mme/main/scripts/install_motion_frontend.sh | sudo bash -s -- --uninstall
```

#### 8.1.4 Mise à jour

```bash
# Mise à jour depuis la branche main
curl -sSL https://raw.githubusercontent.com/sn8k/Mme/main/scripts/install_motion_frontend.sh | sudo bash -s -- --update

# Mise à jour avec choix de branche
curl -sSL https://raw.githubusercontent.com/sn8k/Mme/main/scripts/install_motion_frontend.sh | sudo bash -s -- --update --branch
```

#### 8.1.5 Réparation

```bash
# Vérifie et répare l'installation existante
curl -sSL https://raw.githubusercontent.com/sn8k/Mme/main/scripts/install_motion_frontend.sh | sudo bash -s -- --repair
```

La fonction de réparation effectue les vérifications suivantes :
- **Répertoires** : Vérifie la présence de `/opt/motion-frontend` et ses sous-répertoires (backend, static, templates, config, logs)
- **Utilisateur système** : Vérifie que l'utilisateur `motion-frontend` existe et appartient aux groupes requis
- **Environnement Python** : Vérifie l'environnement virtuel et les dépendances installées
- **Service systemd** : Vérifie que le service existe et est activé au démarrage
- **Permissions** : Vérifie les propriétaires et droits d'accès des fichiers
- **Configuration** : Vérifie la présence des fichiers de configuration

Actions automatiques :
- Création des répertoires manquants (config, logs)
- Ajout de l'utilisateur aux groupes manquants
- Réinstallation des dépendances Python si nécessaire
- Recréation du service systemd si absent
- Correction des permissions

**Important** : La réparation ne consomme pas de token Meeting. Si la configuration Meeting est absente, elle peut être ajoutée interactivement mais sans validation brûlant un token.

#### 8.1.6 Options de ligne de commande

| Option | Description |
|--------|-------------|
| `--help`, `-h` | Affiche l'aide |
| `--branch`, `-b` | Menu de sélection de branche |
| `--uninstall`, `-u` | Désinstalle le projet |
| `--update` | Met à jour l'installation existante |
| `--repair` | Vérifie et répare l'installation |
| `--device-key KEY` | Device Key pour le service Meeting |
| `--token TOKEN` | Token code pour le service Meeting |
| `--skip-meeting` | Ne pas configurer le service Meeting |

#### 8.1.7 Fonctionnement détaillé

**Étapes d'installation** :
1. Vérification système (Linux/Debian, architecture, Raspberry Pi)
2. Vérification de la connexion Internet
3. Installation des dépendances système :
   - `python3`, `python3-pip`, `python3-venv`, `python3-dev`
   - `git`, `curl`, `wget`, `build-essential`
   - `ffmpeg`, `v4l-utils`, `alsa-utils`
   - `python3-opencv`, `libopencv-dev`
4. Création de l'utilisateur système `motion-frontend`
5. Ajout aux groupes : `video`, `audio`, `gpio`, `i2c`, `spi`
6. Téléchargement du code source depuis GitHub
7. Création de l'environnement virtuel Python
8. Installation des dépendances Python (`requirements.txt`)
9. Configuration par défaut
10. Création du service systemd
11. Démarrage automatique du service

**Répertoires créés** :

| Chemin | Description |
|--------|-------------|
| `/opt/motion-frontend/` | Répertoire d'installation principal |
| `/opt/motion-frontend/.venv/` | Environnement virtuel Python |
| `/opt/motion-frontend/config/` | Configuration de l'application |
| `/etc/motion-frontend/` | Configuration système (réservé) |
| `/var/log/motion-frontend/` | Journaux d'exécution |

**Service systemd** :

```ini
[Unit]
Description=Motion Frontend - Web Interface for Video Surveillance
After=network-online.target

[Service]
Type=simple
User=motion-frontend
Group=motion-frontend
WorkingDirectory=/opt/motion-frontend
ExecStart=/opt/motion-frontend/.venv/bin/python -m backend.server --host 0.0.0.0 --port 8765
Restart=always
RestartSec=5

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

**Commandes de gestion du service** :

```bash
# Statut
sudo systemctl status motion-frontend

# Démarrer
sudo systemctl start motion-frontend

# Arrêter
sudo systemctl stop motion-frontend

# Redémarrer
sudo systemctl restart motion-frontend

# Logs en temps réel
sudo journalctl -u motion-frontend -f
```

**Identifiants par défaut** :
- Utilisateur : `admin`
- Mot de passe : `admin` (à changer à la première connexion)

#### 8.1.7 Désinstallation

La désinstallation :
1. Arrête et désactive le service systemd
2. Supprime le fichier service
3. Propose de sauvegarder la configuration
4. Supprime le répertoire d'installation
5. Supprime les logs
6. Propose de supprimer l'utilisateur et le groupe système

Les dépendances système (python3, ffmpeg, etc.) ne sont pas supprimées.

### 8.2 Lanceur Windows (`run_motion_frontend.ps1`)

```powershell
# Usage simple
.\scripts\run_motion_frontend.ps1

# Options avancées
.\scripts\run_motion_frontend.ps1 `
    -PythonExe ".venv\Scripts\python.exe" `
    -Host "127.0.0.1" `
    -Port 9000 `
    -NoBrowser
```

**Fonctionnement** :
1. Démarre `backend/server.py` en arrière-plan
2. Sonde `/health` jusqu'à succès (timeout 30s)
3. Ouvre le navigateur par défaut

### 8.3 Installeur Windows (`install_motion_frontend.ps1`)

```powershell
# Installation
.\scripts\install_motion_frontend.ps1 -Mode install -TargetPath C:\MotionFrontend

# Mise à jour
.\scripts\install_motion_frontend.ps1 -Mode update -TargetPath C:\MotionFrontend

# Désinstallation
.\scripts\install_motion_frontend.ps1 -Mode uninstall -TargetPath C:\MotionFrontend

# Avec archive ZIP
.\scripts\install_motion_frontend.ps1 -Mode install -ArchivePath release.zip
```

---

## 9. Internationalisation (i18n)

### 9.1 Langues supportées

| Code | Langue | Fichier |
|------|--------|---------|
| `fr` | Français | `motion_frontend.fr.json` |
| `en` | English | `motion_frontend.en.json` |

### 9.2 Utilisation dans les templates

```jinja2
{{ _('Texte à traduire') }}
```

### 9.3 Ajout d'une nouvelle langue

1. Créer `static/js/motion_frontend.{code}.json`
2. Ajouter l'option dans `config_store.py` (section `language`)
3. Documenter dans le changelog

---

## 10. Versionnement des fichiers

### 10.1 Convention

Chaque fichier possède un numéro de version au format `X.Y.Z` :
- **X** (majeur) : changements incompatibles
- **Y** (mineur) : nouvelles fonctionnalités rétrocompatibles
- **Z** (patch) : corrections de bugs

### 10.2 Déclaration

```python
# Python
# File Version: 0.3.0

# HTML/Jinja2
{# File Version: 0.2.0 #}
<!-- File Version: 0.2.0 -->

# CSS/JS
/* File Version: 0.5.0 */

# Markdown
<!-- File Version: 1.0.0 -->
```

### 10.3 Versions actuelles des fichiers

| Fichier | Version |
|---------|---------|
| `backend/config_store.py` | 0.17.0 |
| `backend/handlers.py` | 0.15.0 |
| `backend/jinja.py` | 0.1.3 |
| `backend/mjpeg_server.py` | 0.7.0 |
| `backend/server.py` | 0.1.0 |
| `backend/settings.py` | 0.1.0 |
| `templates/base.html` | 0.2.0 |
| `templates/login.html` | 0.2.0 |
| `templates/main.html` | 0.4.2 |
| `static/css/ui.css` | 0.2.2 |
| `static/css/main.css` | 0.3.1 |
| `static/css/login.css` | 0.2.0 |
| `static/js/ui.js` | 0.2.1 |
| `static/js/main.js` | 0.24.0 |

---

## 11. Guide de développement

### 11.1 Prérequis

- Python 3.11+
- pip / pipenv / poetry
- Node.js (optionnel, pour outils frontend)

### 11.2 Installation environnement dev

```bash
# Cloner le repo
git clone <repo_url> MmE
cd MmE

# Créer environnement virtuel
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac

# Installer dépendances
pip install tornado jinja2
```

### 11.3 Lancement en développement

```bash
# Via script PowerShell (Windows)
.\scripts\run_motion_frontend.ps1

# Via Python directement
python -m backend.server --log-level DEBUG
```

### 11.4 Structure d'un handler

```python
class MonHandler(BaseHandler):
    @tornado.web.authenticated  # Si authentification requise
    async def get(self) -> None:
        # Logique GET
        self.write_json({"data": "value"})

    async def post(self) -> None:
        payload = tornado.escape.json_decode(self.request.body or b"{}")
        # Traitement
        self.write_json({"status": "ok"})
```

### 11.5 Ajout d'une section de configuration

1. **Backend** (`config_store.py`) :
```python
def get_main_config(self):
    return {
        # ...
        "ma_section": [
            {"id": "param1", "label": "Mon paramètre", "type": "str", "value": ""},
        ],
    }
```

2. **Handler** (`handlers.py`) :
```python
template_context = {
    # ...
    "ma_section": main_sections.get("ma_section", []),
}
```

3. **Template** (`main.html`) :
```jinja2
{% set builtin_main_sections = [
    # ...
    {'slug': 'ma_section', 'title': _('Ma Section'), 'configs': ma_section|default([])},
] %}
```

---

## 12. Dépannage

### 12.1 Erreurs courantes

#### Port déjà utilisé
```
OSError: [WinError 10048] Une seule utilisation de chaque adresse de socket
```
**Solution** : Arrêter le processus Python existant ou changer de port.

#### Template non trouvé
```
jinja2.exceptions.TemplateNotFound
```
**Solution** : Vérifier `--template-path` et structure des fichiers.

#### Cookie invalide
```
tornado.web.MissingArgumentError: HTTP 400: Bad Request
```
**Solution** : Vider les cookies du navigateur et se reconnecter.

### 12.2 Logs

Les logs sont configurables via `--log-level` :
- `DEBUG` : très verbeux, pour développement
- `INFO` : informations générales
- `WARNING` : alertes non bloquantes
- `ERROR` : erreurs traitées
- `CRITICAL` : erreurs fatales

### 12.3 Healthcheck

```bash
curl http://localhost:8765/health
# {"status": "ok"}
```

---

## Annexes

### A. Dépendances Python

```
tornado>=6.0
jinja2>=3.0
```

### B. Dépendances Frontend (vendor)

| Librairie | Version | Usage |
|-----------|---------|-------|
| jQuery | 3.x | Manipulation DOM |
| Gettext.js | - | Internationalisation |
| jQuery Timepicker | - | Sélecteur horaire |
| jQuery Mousewheel | - | Scroll amélioré |
| CSS Browser Selector | - | Détection navigateur |

### C. Liens utiles

- [Tornado Documentation](https://www.tornadoweb.org/)
- [Jinja2 Documentation](https://jinja.palletsprojects.com/)
- [Motion Project](https://motion-project.github.io/)

---

*Document généré le 28 décembre 2025 - Motion Frontend v0.3.0*
