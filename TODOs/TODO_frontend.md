# TODO Frontend – motionUI

Objectif : décrire tout le nécessaire pour reconstruire à l’identique l’interface web actuelle (HTML, CSS, JS, i18n, assets, flux). Les points ci-dessous doivent permettre de repartir de zéro et d’obtenir le même rendu et le même comportement.

## 1. Structure générale (templates Jinja2)
- Recréer `templates/base.html` : balises meta mobile/PWA, favicon/logo, manifest, inclusion des CSS/JS de base (jquery, timepicker, mousewheel, css-browser-selector). Paramètre `static_path` et version cache-buster `v={{version}}` obligatoires.
- Recréer `templates/main.html` :
  - Macro `config_item` générant les lignes de formulaires selon `config['type']` (str, pwd, number, range, bool, choices, html, separator) et posant les classes `section`, `main-config`/`camera-config`, ids `*Entry/*Select/*Slider/*Switch/*Html`, attributs `depends`, `validate`, `unit`, etc.
  - Bloc `style` ajoutant `css/ui.css`, `css/main.css`, optionnel `css/frame.css` si `frame=True`.
  - Bloc `script` ajoutant `js/ui.js`, `js/main.js`, optionnel `js/frame.js` si `frame=True`.
  - Bloc inline JS pour i18n : charge `gettext.min.js`, fichiers JSON `motion_frontend.<lingvo>.json`, définit `i18n`, `adminUsername`, `frame`, `hasLocalCamSupport`, `hasNetCamSupport`, `maskWidth`.
  - Header avec logo, boutons settings/logout, select `#cameraSelect`, bouton `#remCameraButton`, bouton `#applyButton`, hostname.
  - Sections principales : "Preferences", "General Settings" (identifiants, version, update, reboot), backup/restore.
  - Boucle `main_sections` : rend chaque section additionnelle (Network, Hardware, Meeting, RTSP, etc.) via `config_item`.
  - Bloc caméra (quand `camera_id`) : sections Device, File storage, Text Overlay, Video Streaming, Still Images, Movies, Motion Detection, Motion Notifications, Working Schedule + boucle `camera_sections` pour sections additionnelles caméra.
  - Frame mode (quand `frame=True`) : conteneur vidéo et overlays (non affiché dans les captures mais présent dans template plus bas).
- Recréer `templates/version.html` (page de version) et `templates/manifest.json` (PWA) si présents.

## 2. Assets statiques à fournir
- CSS : `static/css/main.css`, `ui.css`, `frame.css`, `jquery.timepicker.min.css` (styles globaux, layout, sliders, switches, modales, viewer image/vidéo, mobile responsive). Conserver classes `.settings-section-title`, `.settings`, `.settings-item`, `.button`, `.styled`, `.help-mark`, etc.
- JS vendors : `jquery.min.js`, `jquery.timepicker.min.js`, `jquery.mousewheel.min.js`, `css-browser-selector.min.js`, `gettext.min.js`.
- JS app : `static/js/ui.js` (helpers UI), `main.js` (coeur applicatif), `frame.js` (mode iframe/miniview), `version.js` (affichage version), traductions `motion_frontend.<lang>.json` (en, fr, etc.).
- Images : `static/img/motion-frontend-logo.svg` (logo/fav), éventuels PNG/ico si utilisés par CSS.
- Fonts : contenus de `static/fnt/` si référencés par CSS.

## 3. Logique JavaScript (main.js)
- Variables globales : cookies (`meye_username`, `meye_password_hash`), cache frames, flags fullscreen/single view, refresh intervals, regex de validation (device name, filename, dirname, email, webhook URL), factors de framerate/résolution.
- Polyfills/Utils : extensions Object/Array/String pour compatibilité navigateurs anciens.
- i18n : usage de `window.i18n()` chargé depuis inline script (main.html) avec fichiers JSON.
- Initialisation :
  - Déterminer `basePath`, `staticPath`, récupérer `adminUsername`, `frame`, supports cam.
  - Récupérer config initiale (requête AJAX vers backend `/config/` et `/config/list` côté serveur Tornado) et peupler formulaires via classes `*.main-config` / `*.camera-config` et ids `*Entry/Select/Switch/Slider/Html`.
  - Peupler `#cameraSelect`, gérer ajout/suppression caméra, état single view / multi.
- Formulaires et dépendances :
  - Appliquer attributs `depends` pour masquer/afficher inputs selon switches.
  - Valider via regex/attributs `min/max/decimals/unit`.
  - Bouton `Apply` pousse les diffs via AJAX (pushConfigs/pushConfigReboot), reboot si requis.
- Sections additionnelles :
  - Utilise `main_sections` (camera=False) et `camera_sections` (camera=True) renvoyés par backend ; chaque section contient `configs` passés à `config_item`.
  - Gestion des classes `additional-section` et `additional-section-main` pour la visibilité non-admin.
- Media/preview :
  - Chargement des frames caméra (MJPEG) avec cache `cameraFramesCached`, timers `refreshInterval`, gestion erreurs (fallback, disable refresh).
  - Actions snapshot/movie (boutons non visibles dans capture mais gérés par JS).
- Overlays/UX :
  - Modales, spinners, progress bars, tooltips `help-mark`, sliders (range inputs stylés), checkboxes stylées.
  - Fullscreen toggle, layout columns, fit vertical, dimmer sliders.
- Auth :
  - Login/logout via cookies, signature cleaning regex `signatureRegExp`, hash mot de passe.
- Meeting/RTSP :
  - Champs meeting backend (device key/token, heartbeat) et RTSP server options, reliés aux configs renvoyées par backend.
- Frame mode (frame.js) :
  - Affichage d’un flux unique embarqué (iframe) avec contrôles limités, rafraîchissement séparé.

## 4. Logique JavaScript (ui.js / frame.js / version.js)
- `ui.js` : interactions génériques (dialogs, sliders, validation, tooltips, drag/drop ?), initialisation des composants `styled`.
- `frame.js` : mode intégré pour affichage caméra seule (utilisé quand `frame=True`), gère rafraîchissement, taille, overlays minimalistes.
- `version.js` : récupère la version du backend et l’affiche (page `version.html`).

## 5. CSS : points clés à reproduire
- `main.css` : thème sombre, layout flex header, conteneurs sections, tables `.settings`, sliders horizontaux, switches stylés, boutons `.button`, `.apply-button`, `.update-button`, `.backup-button`, `.restore-button`, etc. Gestion responsive (viewport mobile), hide/show classes, `.hidden`, `.minimize.open` pour accordéons.
- `ui.css` : styles communs (typographie, inputs `.styled`, tooltips `.help-mark`, modales, overlays, progress, messages d’erreur/succès).
- `frame.css` : styles spécifiques au mode iframe/mini-embed (cam frame, overlay info, controls réduits).
- Timepicker CSS pour champs horaires (working schedule, etc.).

## 6. Internationalisation
- Fichiers JSON `static/js/motion_frontend.<lang>.json` (plusieurs locales). Clés alignées avec gettext messages utilisés dans templates et main.js.
- Inline i18n loader dans main.html : charge JSON selon `settings.lingvo`, `i18n.setLocale(...)`.
- Tous les textes UI passent par `{{ _() }}` côté template ou `i18n.gettext()` côté JS.

## 7. Connexions backend à prévoir
- Endpoints (côté Tornado handlers) que le frontend appelle typiquement :
  - Auth: `/login/` (POST), logout via cookie clear.
  - Config main: `/config/` (GET/POST), `/config/list/` (GET) pour caméras, `/config/<id>/` (GET/POST) pour caméra.
  - Media: `/picture/<id>/`, `/movie/<id>/`, `/frame/<id>/` pour flux JPEG/MJPEG.
  - Update/version: `/version/`, `/update/`.
  - Meeting/RTSP: endpoints dédiés exposés par handlers correspondants.
- Les paramètres `main_sections` et `camera_sections` viennent de `config.get_additional_structure(camera=False/True)` ; chaque item a `section`, `type`, `choices`, `depends`, `reboot`, etc. Le frontend ne doit pas filtrer : il rend tout ce que le backend fournit.

## 8. Comportements UI spécifiques
- Accordéons : chaque section a un header `.settings-section-title` avec flèche `.minimize` (classe `open` quand déplié). Le JS applique `markHideLogic` pour masquer les lignes selon dépendances et état admin.
- Boutons Apply/Backup/Restore/Update/Reboot : actions AJAX + feedback visuel, reboot optionnel si `reboot=true` dans configs modifiées.
- Dépendances : attribut `depends` sur `tr` géré côté JS pour show/hide (ex: `depends="wifiEnabled"` ou `!wifiUseDhcp`).
- Validation : regex côté JS doit matcher celles de `config.py` (deviceNameValidRegExp, filenameValidRegExp, dirnameValidRegExp, emailValidRegExp, webHookUrlValidRegExp).
- Cookies : mémorisation username/hash pour login auto.
- Caméras : select `#cameraSelect`, suppression `#remCameraButton`, mise à jour dynamique de sections caméra.
- Layout : sliders pour Layout Columns, Fit Frames vertically, Frame rate dimmer, Resolution dimmer ; rafraîchissement des frames en fonction de ces paramètres.

## 9. Données et cache-busting
- Toutes les ressources statiques sont appelées avec `?v={{version}}` (Jinja) ; assurez-vous de propager `version` dans le contexte.
- Le frontend attend `staticPath` global (injecté dans base.html) pour construire les URLs des assets.

## 10. À reconstruire / vérifier pour une copie conforme
- Pages/templates : `base.html`, `main.html`, `version.html`, `manifest.json`.
- CSS : `main.css`, `ui.css`, `frame.css`, `jquery.timepicker.min.css`.
- JS : `main.js`, `ui.js`, `frame.js`, `version.js`, vendors jQuery/timepicker/mousewheel/gettext/css-browser-selector.
- Assets : logo SVG (favicon/apple-touch), fonts éventuels, images.
- i18n : tous les JSON de locale.
- Règles de build/serve : none (fichiers servis tels quels), assurer encodage UTF-8, cache-buster par version.
- Interactions AJAX : respecter endpoints config/media/auth/update, gestion des réponses success/error, reboot flag.

Checklist finale :
- [ ] Implémenter templates Jinja 1:1 avec macros et attributs dépendances.
- [ ] Restituer les styles (classes, couleurs, layout) via main.css/ui.css/frame.css.
- [ ] Reproduire la logique JS principale (initialisation, fetch/push config, dépendances, cam frames, UI state) depuis main.js/ui.js/frame.js.
- [ ] Servir vendors JS/CSS et fichiers de locale.
- [ ] Exposer les endpoints backend attendus et passer `main_sections` / `camera_sections` au template.
- [ ] Vérifier cache-buster version et variable `staticPath`.
- [ ] Tester en mode sans caméra et avec caméra pour valider affichage des sections et flux.
