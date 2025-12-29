# Rapport incoherences - execution cross-platform (Windows + Raspberry Pi OS Debian Trixie)

Contexte
- Analyse statique du code du projet.
- Objectif: verifier la coherence de fonctionnement sur Windows et Raspberry Pi OS Debian Trixie, en particulier avec camera USB sur RPi 3B+.

Incoherences / risques majeurs
1) Ouverture MJPEG avec backend Windows sur Linux si device est numerique
- Impact (RPi/Linux): si la camera est configuree avec un device numerique ("0", "1"), OpenCV est ouverte avec CAP_DSHOW (backend Windows). Sur Linux cela echoue ou ouvre un device invalide, donc pas de flux MJPEG.
- Impact (Windows): comportement attendu (CAP_DSHOW) si device numerique.
- Cause: conversion en int sans verifier la plateforme, puis CAP_DSHOW force.
- References: `backend/mjpeg_server.py:824`, `backend/mjpeg_server.py:1118`.

2) Resolution de device video ne convertit pas index numerique en /dev/videoN
- Impact (RPi/Linux): `resolve_video_device` retourne "0" si la config contient "0". Ce chemin n existe pas et tombe sur le point (1). Flux MJPEG/RTSP peut echouer.
- Impact (Windows): pas concerne.
- Cause: pas de mapping explicite des indices vers /dev/videoN.
- Reference: `backend/config_store.py:57`.

3) Demarrage RTSP tente un `sudo` depuis un service non root
- Impact (RPi/Linux): le service tourne en utilisateur systeme, sans sudo interactif. `sudo systemctl start mediamtx` peut echouer (pas de TTY, pas de droits), donc RTSP indisponible.
- Impact (Windows): non concerne.
- Cause: tentative de demarrer MediaMTX via sudo dans le process applicatif.
- Reference: `backend/rtsp_server.py:573`.

4) RTSP ne tient pas compte de Motion en cours d utilisation
- Impact (RPi/Linux): si Motion utilise deja la camera USB, demarrage RTSP tente un acces direct au device (FFmpeg) et echoue (device busy). Le code ne stoppe que MJPEG interne, pas Motion.
- Impact (Windows): non concerne.
- References: `backend/server.py:311`, `backend/handlers.py:347`.

Incoherences / risques cross-platform
5) MJPEG depend d OpenCV dans le venv, mais l installeur Linux installe OpenCV systeme
- Impact (RPi/Linux): si `opencv-python` ne fournit pas de wheel ARM, l import cv2 echoue dans le venv. Comme le venv n utilise pas `--system-site-packages`, `python3-opencv` n est pas visible, donc MJPEG desactive.
- Impact (Windows): `opencv-python` pip fonctionne en general.
- Cause: le venv est isole, mais l installateur installe OpenCV systeme au lieu d injecter dans le venv.
- References: `scripts/install_motion_frontend.sh:749`, `requirements.txt`.

6) Systeme d auto-detection Motion base sur port global 8081
- Impact (RPi/Linux): en multi-camera Motion, le port peut differer. L auto-detection peut indiquer Motion actif alors que la camera cible n a pas de stream accessible, ce qui casse la preview en mode auto.
- Impact (Windows): non concerne (Motion non utilise).
- Cause: `is_motion_running()` checke un port par defaut et un process global, pas par camera.
- References: `backend/system_info.py:218`, `backend/handlers.py:684`.

Observations mineures
7) Detection camera/controls depend de `v4l2-ctl` et `arecord`
- Impact (RPi/Linux): si `v4l-utils` / `alsa-utils` manquent, la detection degrade vers /dev/video* et /proc/asound. Fonctionnel mais moins fiable. L installeur installe bien ces paquets, mais une installation manuelle peut casser la detection.
- Impact (Windows): non concerne.
- References: `backend/camera_detector.py`, `backend/audio_detector.py`, `scripts/install_motion_frontend.sh`.

Synthese
- Les points 1 et 2 sont critiques pour RPi + camera USB si la config utilise un index numerique.
- Les points 3 et 4 affectent la fiabilite RTSP en production Linux.
- Le point 5 peut desactiver le MJPEG sur RPi selon l environnement Python.
- Le point 6 touche la logique auto Motion sur Linux.

Notes
- Ce rapport respecte la contrainte cross-platform: les impacts sont indiqu?s pour Windows et pour Raspberry Pi OS Debian Trixie.
- Aucune modification de code effectuee.
