# Cartographie frontend: relie / non relie

Relie (utilise)
- `templates/base.html` -> `static/manifest.json`, `static/css/jquery.timepicker.min.css`, `static/vendor/*.js`, HLS.js CDN.
- `templates/main.html` -> `static/css/ui.css`, `static/css/main.css`, `static/js/ui.js`, `static/js/main.js`.
- `templates/version.html` -> `static/css/ui.css`, `static/css/main.css`, `static/js/version.js`.
- `templates/login.html` -> `static/css/ui.css`, `static/css/login.css`.
- i18n chargee par `templates/main.html` -> `static/js/motion_frontend.fr.json`, `static/js/motion_frontend.en.json`.

Non relie / semble non utilise
- `templates/manifest.json` non reference (manifest servi: `static/manifest.json`).
- `static/js/frame.js` et `static/css/frame.css` peu probables en pratique: pas de `#cameraFrame` dans `templates/main.html` et `frame` est `False` par defaut.
- `static/vendor/jquery.min.js`, `static/vendor/jquery.mousewheel.min.js`, `static/vendor/jquery.timepicker.min.js` charges mais pas d usage evident dans `static/js/main.js` / `static/js/ui.js`.
- `static/css/jquery.timepicker.min.css` charge mais pas de timepicker detecte.
- `static/vendor/css-browser-selector.min.js` charge mais pas d usage explicite cote CSS/JS.

References cassees (liens vers fichiers absents)
- `templates/login.html` -> `static/img/logo.svg` absent.
- `templates/login.html` -> `static/favicon.ico` absent.
