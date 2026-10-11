# MPV AnimeJaNai — installation personnelle

Lancer **mpvnet.exe**. Ctrl+E ouvre **AnimeJaNaiManager-HDR.exe**, le Manager avec une rubrique *Upscale / HDR* dans Global Settings. Il réutilise la fenêtre existante grâce à `portable_config/mpvnet.conf`. Le dossier contient AnimeJaNai 3.6.3 avec les chemins NVIDIA et AMD configurés.

| Emplacement | Fonction |
|---|---|
| `portable_config/mpv.conf` | Sortie vidéo D3D11, base HDR, debanding, sous-titres et profils manuels |
| `portable_config/input.conf` | Raccourcis et menus personnels |
| `portable_config/script-opts/animejanai_hdr_auto.conf` | **Tous les réglages** : GPU, mise à l’échelle, moteur HDR, écran par GPU (`*_nvidia` / `*_amd`), grading |
| `portable_config/scripts/` | Scripts officiels, remplaçables par l’Updater |
| `portable_config/user-scripts/` | Adaptation du backend, profils/AMF, contrôleur HDR (TrueHDR, VSR, grading) |
| `portable_config/hdr-tools/` | Chargeur, détection GPU, plan de grading (`hdr-grade.lua`) et exécutables HDR Windows |
| `portable_config/shaders/` | Shaders officiels, remplaçables par l’Updater |
| `portable_config/user-shaders/anime-hdr-grade.hook` | Grading HDR unique pour NVIDIA et AMD : noirs, éclats, vibrance, stabilité temporelle, ABL OLED |
| `portable_config/user-shaders/anime-hdr-calibration.hook` | Mire d'étalonnage HDR (Ctrl+Alt+P) |
| `animejanai/diagnostic-hdr.txt` | Dernier diagnostic Ctrl+Alt+H |
| `portable_config/cache/animejanai-*.json` | Détection du GPU et fréquence de l'écran, pour un démarrage rapide |
| `portable_config/profiles/nvidia/animejanai.conf` | Tes profils NVIDIA/TensorRT, avec leurs réglages RIFE |
| `portable_config/profiles/amd/animejanai.conf` | Équivalents AMD/DirectML, sans RIFE par défaut ; profil AMF optionnel |
| `animejanai/animejanai.conf` | Copie active de la banque détectée, utilisée aussi par le Manager |
| `portable_config/profiles/active-bank.json` | État de synchronisation des banques et des modifications du Manager |
| `animejanai/inference/` | Bibliothèques d’inférence et outils du Manager |
| `animejanai/onnx/`, `animejanai/rife/` | Modèles, moteurs TensorRT compilés et caches de compilation |
| `animejanai/benchmarks/` | Mesures de performance fournies avec le Manager |
| `Locale/` | Traductions de l’interface |
| `portable_config/watch_later/` | Positions de reprise des vidéos |
| `docs/` | Guide de partage et analyse de l’installation |

Les DLL et exécutables à la racine sont les composants du lecteur et de son interface. `mpv.exe` et `libmpv-2.dll` remplissent des rôles distincts ; leur taille proche n’en fait pas des doublons supprimables.

- [Partager avec un PC AMD](docs/PARTAGE.md)
- [Fonctionnement du rendu HDR et réglages](docs/ANALYSE.md)

Le cache de shaders `portable_config/cache/` et les sauvegardes du Manager peuvent réapparaître : ils sont générés pendant l’utilisation. Les moteurs `.engine` sont conservés pour éviter de longues recompilations. Ne pas déplacer les dossiers techniques sans adapter les chemins des filtres et du programme de mise à jour.

Raccourcis personnels : Ctrl+0…4 profils, **Ctrl+G** grading réglages / *Natural* / sans, **Ctrl+Alt+P** mire d'étalonnage, Ctrl+Alt+H diagnostic, b debanding. Les réglages enregistrés dans le Manager s'appliquent sans relancer le lecteur. Ctrl+U reste disponible. `mpv.conf` charge `hdr-tools/user-script-loader.lua`, qui découvre les scripts officiels et personnels dans des clients distincts. Une version personnelle de même nom prend la priorité : les deux contrôleurs ne tournent jamais en parallèle. Le backend personnel exécute le backend officiel actualisé avec la banque sélectionnée ; le contrôleur des slots/AMF reste personnel. La préservation est vérifiée avec les opérations de copie et de synchronisation de l’Updater 3.6.3, en modes léger et complet. Une future modification des API MPV/AnimeJaNai peut toujours demander une adaptation ; voir `docs/PARTAGE.md`.
