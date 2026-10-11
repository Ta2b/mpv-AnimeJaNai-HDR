# Partager l’installation (NVIDIA ↔ AMD)

Copier le dossier complet **mpv-AnimeJaNai**, pas seulement `portable_config` : les DLL DirectML et les modèles AnimeJaNai/RIFE du dossier `animejanai` sont nécessaires. Les moteurs TensorRT (`.engine`) ne servent qu’au PC NVIDIA.

## Ce qui s’adapte tout seul

| | PC NVIDIA (RTX 4070 Ti) | PC AMD (RX 9070 XT) / Intel |
|---|---|---|
| Inférence | TensorRT + NVDEC | DirectML + D3D11VA |
| Banque de profils | `profiles/nvidia` (RIFE selon profil) | `profiles/amd` (sans RIFE, AMF ×2 sur Ctrl+4) |
| Mise à l’échelle finale | RTX VSR | AMD VideoSR 1.0, repli D3D11 |
| SDR → HDR | RTX TrueHDR + grading `rtx` | MPV + grading `mpv` |
| HDR Windows | `mode` (défaut `follow`) | `amd_mode` (défaut `enable`) |
| Écran | `peak_nvidia`, `gamut_nvidia`, `oled_nvidia` | `peak_amd`, `gamut_amd`, `oled_amd` |

La carte est détectée au démarrage ; la carte dédiée est préférée à l’iGPU. La cible de résolution est **l’écran où se trouve MPV** (`target_resolution=auto`) ; les proportions sont conservées.

## Raccourcis

| Raccourci | Action |
|---|---|
| **Ctrl+0** | Désactiver AnimeJaNai (HDR et mise à l’échelle finale restent actifs). |
| **Ctrl+1** | Profil 1 « 1080p » : réduction 540p, RIFE ×2 sur NVIDIA, puis ×2 et VSR. |
| **Ctrl+2** | Profil 2 « 4K » : 1080p natif → 2160p, sans RIFE. Le plus net. |
| **Ctrl+3** | Profil 3 « 2K » : réduction 720p, RIFE ×2 sur NVIDIA, ×2 → 1440p, VSR → écran. Sur NVIDIA, modèle Balanced : trop lourd pour une RTX 4070 Ti avec TrueHDR et VSR en 2160p (voir `ANALYSE.md`). |
| **Ctrl+4** | Profil 4. Sur NVIDIA : « 2K Performance », par défaut, le profil 3 avec le modèle Performance. Sur AMD : variante libre du 2K. Un profil vide est refusé avec un message. |
| **Ctrl+G** | Grading HDR : réglages du Manager → look *Natural* → sans grading, puis retour. Le HDR et la chaîne vidéo restent actifs. |
| **Ctrl+Alt+P** | Mire d'étalonnage HDR (voir plus bas). Même touche pour la retirer ; elle disparaît aussi à la fin de la vidéo. |
| **b** | Debanding activé / désactivé. |
| **Ctrl+Alt+H** | Diagnostic : sortie, écran, VSR, HDR Windows, TrueHDR, cible MPV, grading et ses paramètres, profil AnimeJaNai, RIFE calé sur l'écran, images perdues. Aussi écrit dans `animejanai/diagnostic-hdr.txt`, à joindre à un signalement. |

Ctrl+E ouvre le Manager, Ctrl+U installe une mise à jour. Les réglages HDR enregistrés dans le Manager s'appliquent tout de suite à la vidéo en cours (message « Reglages HDR appliques ») ; le calage RIFE s'applique à partir de la vidéo suivante.

## Réglages dans le Manager (Ctrl+E)

**Ctrl+E** ouvre `AnimeJaNaiManager-HDR.exe` : le Manager officiel (0.6.0 pour AnimeJaNai 3.6.3, 0.8.0 pour 3.8.0) avec une rubrique supplémentaire dans **Global Settings**, sous *GPU Subtitle Rendering*. Si cet exe est absent, Ctrl+E ouvre le Manager d'origine et le signale.

| Réglage du Manager | Clé du fichier |
|---|---|
| Upscale to Display : Auto / RTX Video Super Resolution / AMD VideoSR / Standard / Off | `vsr` |
| Extra Frame Generation : Off / AMD AMF x2 | `frame_generation` |
| Target Resolution | `target_resolution` |
| SDR to HDR Conversion (grise tout ce qui suit quand décoché) | `hdr_conversion` |
| SDR to HDR Backend : Auto / RTX Video HDR / mpv | `hdr_backend` |
| HDR Enhancement > Enhance HDR Picture | `grade` |
| Black Depth (%) | `shadows` |
| Also Enhance Native HDR Videos | `grade_native_hdr` |
| With RTX Video HDR > Highlight Boost / Color Vibrance (%) | `highlights_rtx` / `vibrance_rtx` |
| With mpv Conversion > SDR White Level / Highlight Boost / Color Vibrance | `paper_white` / `highlights` / `vibrance` |
| Display on NVIDIA PC / on AMD / Intel PC : Windows HDR, Peak Brightness, Color Gamut, OLED | `mode` / `amd_mode`, `peak_*`, `gamut_*`, `oled_*` |
| Look Preset : Natural / Vivid / Maximum (remplit les curseurs, toujours modifiables) | `shadows`, `highlights*`, `vibrance*` |
| Subtitle Brightness (nits) | `subtitle_white` |
| Match RIFE to Display Refresh / Max RIFE Factor | `rife_display_sync` / `rife_max_factor` |
| TensorRT Engines (panneau TensorRT) : taille, *Delete Outdated*, *Delete All* | fichiers `.engine` du dossier `animejanai/onnx` |

Le Manager écrit directement `script-opts/animejanai_hdr_auto.conf` en conservant les commentaires, puis prévient le lecteur ouvert par son canal IPC (`input-ipc-server=mpvpipe` dans `mpv.conf`). Les pourcentages correspondent aux fractions du fichier (85 % = 0.85). Le bloc *(this PC)* indique l'écran utilisé sur le PC courant.

*Delete Outdated* supprime les moteurs TensorRT compilés pour une autre version de TensorRT ou un autre GPU (ils seraient recompilés de toute façon) ; *Delete All* demande un second clic. Les moteurs manquants sont recompilés à la lecture suivante, ce qui prend quelques minutes par modèle.

Téléchargement : release `latest-hdr-settings` (base 0.6.0, pour AnimeJaNai 3.6.3) ou `latest-hdr-settings-0.8` (base 0.8.0, pour 3.8.0) du dépôt GitHub `Ta2b/AnimeJaNaiManager-HDR`, à placer à côté de `AnimeJaNaiManager.exe`. Chaque push sur une de ces branches recompile l'exe et met à jour sa release. L'Updater ne remplace pas ce fichier : après une mise à jour majeure d'AnimeJaNai, il faudra reporter ces changements sur le Manager correspondant.

## Réglages : `portable_config/script-opts/animejanai_hdr_auto.conf`

### Écran du PC AMD

À adapter une fois sur le PC de l’ami :

- `peak_amd` : pic de l’écran en nits (par exemple 600), ou `auto` pour la valeur annoncée par Windows.
- `oled_amd=yes` si c’est un OLED ; `auto` sinon.
- `gamut_amd=display-p3` convient à la plupart des écrans HDR.

Faire aussi l’**étalonnage HDR Windows** sur ce PC.

### Rendu HDR (commun aux deux PC)

| Réglage | Défaut | Effet |
|---|---|---|
| `grade` | `yes` | `no` = sortie HDR neutre. |
| `paper_white` | 203 | Blanc SDR en nits quand MPV convertit. Plus haut = image globalement plus lumineuse. |
| `shadows` | 0.30 | Noirs plus profonds (0 à 0,8). Seuls les tons sous ~50 nits bougent. Baisser si les détails sombres disparaissent. |
| `highlights` | 0.85 | Éclats quand MPV convertit (0 à 1). À 1, un éclat blanc isolé atteint le pic ; les grands aplats montent au plus de 50 %. |
| `highlights_rtx` | 0.50 | Renfort des éclats par-dessus RTX TrueHDR (0 à 1), à partir de la moitié du pic. Les aplats et la peau ne bougent pas. |
| `vibrance` / `vibrance_rtx` | 0.30 / 0.20 | Couleurs plus vives (0 à 0,8), sans sortir du gamut. La peau est exclue et les couleurs déjà saturées sont ménagées. |
| `grade_native_hdr` | `no` | `yes` applique aussi le grading aux sources déjà HDR. |
| `subtitle_white` | 200 | Blanc des sous-titres en nits sur une sortie HDR (80 à 1000). |

### Moteur HDR et mise à l’échelle

| Réglage | Valeurs |
|---|---|
| `hdr_conversion` | `yes` / `no`. `no` : les vidéos SDR restent SDR et le HDR Windows n'est jamais modifié. |
| `hdr_backend` | `auto` (RTX sur NVIDIA, MPV ailleurs), `rtx`, `mpv`. `mpv` sur NVIDIA permet de comparer avec TrueHDR. |
| `vsr` | `auto`, `nvidia`, `amd`, `classic` (D3D11), `no`. Une valeur incompatible avec la carte se replie sur `classic`. |
| `target_resolution` | `auto` ou une taille fixe, par exemple `2560x1440`. |
| `mode` / `amd_mode` | `enable` : MPV active le HDR Windows puis le restaure. `follow` : suivre l’état de Windows. |
| `rife_display_sync` | `yes` : le facteur RIFE de la vidéo est choisi pour que chaque image reste affichée le même nombre de rafraîchissements (23,976 i/s : ×2 à 144 Hz, ×5/3 à 120 Hz, ×5/2 à 60 Hz ou 120 Hz si `rife_max_factor=3`). Sans facteur adapté, celui du profil est gardé. Ignoré quand AnimeJaNai règle lui-même la fréquence de l'écran (`display_rate_match=yes`, AnimeJaNai 3.8). |
| `rife_max_factor` | Facteur maximal autorisé pour ce calage (2 par défaut). À 3, un écran à 120 Hz reçoit ×5/2 (59,94 i/s), trop lourd pour une RTX 4070 Ti : environ 49 images perdues par seconde. |

## Mire d'étalonnage (Ctrl+Alt+P)

Pendant une vidéo en sortie HDR, Ctrl+Alt+P remplace l'image par des patchs de luminance absolue (le grading est suspendu dessous) :

- **Noirs** 0,005 à 1 nit : le dernier patch distinct du fond indique jusqu'où les ombres restent visibles. S'il en manque beaucoup, baisser *Black Depth*.
- **Rampe et gris** 5 à 300 nits : le blanc papier (203) et les tons moyens ; l'EOTF Boost de l'écran les éclaircit.
- **Éclats** 400 à 4000 nits : le premier patch qui ne s'éclaircit plus par rapport au précédent est le pic réel. Le reporter dans *Peak Brightness* et dans l'étalonnage HDR Windows.

## Génération d'images en plus de RIFE

- **AMD AMF x2** (*Extra Frame Generation* dans le Manager, `frame_generation=amf`) : filtre `amf_frc` du lecteur, placé après AnimeJaNai et RIFE, actif sur **tous les profils** et même avec AnimeJaNai désactivé. Il est ignoré au-delà de 31 i/s en source. S'il échoue, il est désactivé jusqu'au redémarrage du lecteur.
- **NVIDIA Smooth Motion** : fonction du pilote, à activer dans l'app NVIDIA, *Graphics* → *Program Settings* → `mpvnet.exe` → *Smooth Motion*. Elle double les images affichées, RIFE compris. Aucun réglage du lecteur ne la pilote.
- **AMD Fluid Motion Frames** : fonction du pilote, dans AMD Software: Adrenalin Edition.
- N'activer qu'une génération d'images à la fois, en plus de RIFE.

## Points propres à AMD (non testés sur la RX 9070 XT)

- AMD VideoSR passe par la RAM (sortie AMF téléchargée en P010) : coût à mesurer. En cas d’échec, repli classique pour le fichier courant.
- AMF ×2 : voir la section précédente. Le cumul avec RIFE est possible en activant RIFE dans un profil AMD.
- Commencer par Ctrl+3 et vérifier les images perdues avec Ctrl+Alt+H.

## Banques de profils

Les banques éditables sont `portable_config/profiles/nvidia/animejanai.conf` et `portable_config/profiles/amd/animejanai.conf`. Au démarrage, la banque du GPU est copiée dans `animejanai/animejanai.conf`, la copie que le Manager édite (Ctrl+E). Au démarrage suivant, les modifications faites dans le Manager sont reportées dans leur banque. `profiles/active-bank.json` sert à attribuer ces modifications à la bonne banque : le garder. Si les deux fichiers ont été modifiés séparément, le conflit est signalé et aucun fichier n’est écrasé.

## Mises à jour AnimeJaNai

`AnimeJaNaiUpdater.exe` (Ctrl+U) télécharge les versions du dépôt `Ta2b/mpv-AnimeJaNai-HDR`, pas celles du projet d'origine. Ne pas utiliser l'installeur ni l'Updater d'origine sur ce dossier : ils remettraient les scripts et le Manager sans HDR.

Une mise à jour remplace `scripts/`, `shaders/`, `user-scripts/`, `user-shaders/`, `hdr-tools/`, `mpv-animejanai.conf`, `input-animejanai.conf`, les modèles AnimeJaNai, les deux Managers et les bibliothèques `aji`. Elle conserve `mpv.conf`, `input.conf` (section personnelle sous le marqueur), `script-opts/animejanai_hdr_auto.conf`, `profiles/` et `animejanai/animejanai.conf`. Une modification faite à la main dans un dossier remplacé est perdue : la faire dans le dépôt, puis publier une version.

Les bibliothèques `aji` et le lecteur sont ceux du projet d'origine, sans modification (`aji` v0.11.1, mêmes empreintes). Ce qui est propre à ce fork : les scripts de `user-scripts/` et `hdr-tools/`, le shader de grading et le Manager HDR.

Ne pas repasser `load-scripts=yes`, sinon les contrôleurs officiels tourneraient en double. Après une mise à jour majeure, relancer et vérifier Ctrl+Alt+H.
