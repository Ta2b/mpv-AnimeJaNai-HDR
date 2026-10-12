# Partager l’installation (NVIDIA ↔ AMD)

Copier le dossier complet **mpv-AnimeJaNai**, pas seulement `portable_config` : les DLL DirectML et les modèles AnimeJaNai/RIFE du dossier `animejanai` sont nécessaires. Les moteurs TensorRT (`.engine`) ne servent qu’au PC NVIDIA.

## Ce qui s’adapte tout seul

| | PC NVIDIA | PC AMD / Intel |
|---|---|---|
| Inférence | TensorRT + NVDEC | DirectML + D3D11VA |
| Banque de profils | `profiles/nvidia` (RIFE selon profil) | `profiles/amd` (sans RIFE, AMF ×2 sur Ctrl+4) |
| Mise à l’échelle finale | RTX VSR | AMD VideoSR 1.0, repli D3D11 |
| SDR → HDR | RTX TrueHDR + grading `rtx` | MPV + grading `mpv` |
| HDR Windows | `windows_hdr=follow` | `windows_hdr=follow` |
| Écran | `display_peak`, `display_gamut`, `display_oled` | mêmes paramètres d’écran |

La carte est détectée au démarrage ; la carte dédiée est préférée à l’iGPU. La cible de résolution est **l’écran où se trouve MPV** (`target_resolution=auto`) ; les proportions sont conservées.

## Raccourcis

| Raccourci | Action |
|---|---|
| **Ctrl+0** | Désactiver AnimeJaNai (HDR et mise à l’échelle finale restent actifs). |
| **Ctrl+1** | Profil 1 « 1080p » : réduction 540p, RIFE ×2 sur NVIDIA, puis ×2 et VSR. |
| **Ctrl+2** | Profil 2 « 4K » : 1080p natif → 2160p, sans RIFE. Le plus net. |
| **Ctrl+3** | Profil 3 « 2K » : réduction 720p, RIFE ×2 sur NVIDIA, ×2 → 1440p, VSR → écran. Sur NVIDIA, modèle Balanced : trop lourd pour une RTX 4070 Ti avec TrueHDR et VSR en 2160p (voir `ANALYSE.md`). |
| **Ctrl+4** | Profil 4. Sur NVIDIA : « 2K Performance », le profil 3 avec le modèle Performance. Sur AMD : variante libre du 2K. Un profil vide est refusé avec un message. |
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
| Convert SDR to HDR when HDR output is active | `hdr_conversion` |
| SDR to HDR Backend : Auto / RTX Video HDR / mpv | `hdr_backend` |
| Enable HDR grading | `grade` |
| Black Depth (%) | `shadows` |
| Also Enhance Native HDR Videos | `grade_native_hdr` |
| With RTX Video HDR > Highlight Boost / Color Vibrance (%) | `highlights_rtx` / `vibrance_rtx` |
| With mpv Conversion > SDR White Level / Highlight Boost / Color Vibrance | `paper_white` / `highlights` / `vibrance` |
| Display : Windows HDR, Peak Brightness, Color Gamut, OLED | `windows_hdr`, `display_peak`, `display_gamut`, `display_oled` |
| Look Preset : Natural / Vivid / Maximum (remplit les curseurs, toujours modifiables) | `shadows`, `highlights*`, `vibrance*` |
| Subtitle Brightness (nits) | `subtitle_white` |
| Match RIFE to Display Refresh / Max RIFE Factor | `rife_display_sync` / `rife_max_factor` |
| TensorRT Engines (panneau TensorRT) : taille, *Delete Outdated*, *Delete All* | fichiers `.engine` du dossier `animejanai/onnx` |

Le Manager écrit directement `script-opts/animejanai_hdr_auto.conf` en conservant les commentaires, puis prévient le lecteur ouvert par son canal IPC (`input-ipc-server=mpvpipe` dans `mpv.conf`). Les pourcentages correspondent aux fractions du fichier (85 % = 0.85). Une seule section décrit l’écran, indépendamment du GPU ; les détails sont repliés.

*Delete Outdated* supprime les moteurs TensorRT compilés pour une autre version de TensorRT ou un autre GPU (ils seraient recompilés de toute façon) ; *Delete All* demande un second clic. Les moteurs manquants sont recompilés à la lecture suivante, ce qui prend quelques minutes par modèle.

Téléchargement : release `latest-hdr-settings` (base 0.6.0, pour AnimeJaNai 3.6.3) ou `latest-hdr-settings-0.8` (base 0.8.0, pour 3.8.0) du dépôt GitHub `Ta2b/AnimeJaNaiManager-HDR`, à placer à côté de `AnimeJaNaiManager.exe`. Chaque push sur une de ces branches recompile l'exe et met à jour sa release. L'Updater ne remplace pas ce fichier : après une mise à jour majeure d'AnimeJaNai, il faudra reporter ces changements sur le Manager correspondant.

## Réglages : `portable_config/script-opts/animejanai_hdr_auto.conf`

### Écran (commun à tous les GPU)

`display_peak=auto` et `display_gamut=auto` laissent le système et mpv fournir
les informations disponibles. `display_oled=no` ne présume pas la technologie
de dalle ; activer OLED uniquement après confirmation. `windows_hdr=follow`
respecte l’état HDR Windows. Les anciennes clés par GPU sont acceptées si les
clés communes correspondantes sont absentes, pour préserver les réglages existants.

Une installation neuve démarre en Performance Standard sans RIFE (Ctrl+9 sous
Windows, Ctrl+1 sous Linux). Les profils précédents restent sélectionnables.
Voir [SETTINGS.md](SETTINGS.md) pour les défauts et la migration.

### Rendu HDR (commun aux deux PC)

| Réglage | Défaut | Effet |
|---|---|---|
| `grade` | `yes` | `no` = sortie HDR neutre. |
| `paper_white` | 203 | Blanc SDR en nits quand MPV convertit. Plus haut = image globalement plus lumineuse. |
| `shadows` | 0.15 | Noirs plus profonds (0 à 0,8). Seuls les tons sous ~50 nits bougent. Baisser si les détails sombres disparaissent. |
| `highlights` | 0.50 | Éclats quand MPV convertit (0 à 1). À 1, un éclat blanc isolé atteint le pic ; les grands aplats montent au plus de 50 %. |
| `highlights_rtx` | 0.25 | Renfort des éclats par-dessus RTX TrueHDR (0 à 1), à partir de la moitié du pic. Les aplats et la peau ne bougent pas. |
| `vibrance` / `vibrance_rtx` | 0.15 / 0.10 | Couleurs plus vives (0 à 0,8), sans sortir du gamut. La peau est exclue et les couleurs déjà saturées sont ménagées. |
| `grade_native_hdr` | `no` | `yes` applique aussi le grading aux sources déjà HDR. |
| `subtitle_white` | 200 | Blanc des sous-titres en nits sur une sortie HDR (80 à 1000). |

### Moteur HDR et mise à l’échelle

| Réglage | Valeurs |
|---|---|
| `hdr_conversion` | `yes` / `no`. `no` : les vidéos SDR restent SDR et le HDR Windows n'est jamais modifié. |
| `hdr_backend` | `auto` (RTX sur NVIDIA, MPV ailleurs), `rtx`, `mpv`. `mpv` sur NVIDIA permet de comparer avec TrueHDR. |
| `vsr` | `auto`, `nvidia`, `amd`, `classic` (D3D11), `no`. Une valeur incompatible avec la carte se replie sur `classic`. |
| `target_resolution` | `auto` ou une taille fixe, par exemple `2560x1440`. |
| `windows_hdr` | `enable` : MPV active le HDR Windows puis le restaure. `follow` : suivre l’état de Windows. |
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

## Un seul aspect HDR pour tous les GPU

Trois réglages décrivent l'aspect HDR, dans la section HDR du Manager : **contraste**, **saturation** (0 à 200, 100 neutre) et **gris moyen** (10 à 100). Ce sont les réglages de RTX Video HDR (`rtx_contrast`, `rtx_saturation`, `rtx_middle_gray`), et ils pilotent les deux conversions :

| Conversion | Où | Comment elle suit ces réglages |
|---|---|---|
| RTX Video HDR, sortie Vulkan | NVIDIA | directement : le moteur les transmet à TrueHDR |
| mpv, avec *Match the mpv conversion to RTX Video HDR* (`mpv_truehdr_look=yes`, défaut) | AMD, Intel, `hdr_backend=mpv`, ou aucune chaîne active | le shader applique la courbe mesurée sur TrueHDR pour ces mêmes valeurs, puis le même grading (`highlights_rtx`, `vibrance_rtx`, `shadows`) |
| RTX Video HDR, sortie Direct3D 11 | NVIDIA | **pas automatiquement** : TrueHDR lit les curseurs de l'application NVIDIA. Y mettre les mêmes valeurs, ou passer en Vulkan |

Les lois ont été mesurées sur RTX TrueHDR avec des mires, sur toute la plage des curseurs (`D:\AnimeJaNai-devtxprobe`) :

| Réglage | Effet mesuré sur TrueHDR | Dans le shader |
|---|---|---|
| Gris moyen *m* | le gris 50 % sort à environ *m* nits ; le blanc reste au pic | base 4 × *m*, montée vers le pic d'exposant 6 × (50 / *m*)^0,35 |
| Contraste | puissance autour du gris moyen : 0,65 / 0,74 à 0 ; 1,38 / 1,28 à 200 (sous / au-dessus du pivot) | mêmes exposants |
| Saturation | écart à la luminance × 0,81 à 0 ; × 1,19 à 200 | même facteur |
| Pic de l'écran | le blanc SDR va au pic (vérifié à 400, 600 et 1000 nits) | idem |

Écart du shader avec TrueHDR sur les mires grises : ± 10 % sur presque toute la plage (jusqu'à − 23 % au gris moyen 10, réglage extrême), ± 10 % sur les couleurs courantes, jusqu'à + 20 % sur les primaires pures. Sur deux images d'un épisode et quatre réglages différents, le PSNR entre les deux conversions va de 29 à 44 dB. TrueHDR est un réseau de neurones : sur des images réelles il peut s'écarter de la courbe mesurée sur mires.

Décocher la case rend à mpv sa conversion d'origine (blanc SDR à `paper_white`, éclats par zone, `highlights` et `vibrance`). `mpv_contrast`, `mpv_saturation` et `mpv_middle_gray` sont retirés : encore acceptés dans un ancien fichier, ils n'ont plus d'effet.

## Sortie Vulkan ou Direct3D 11 (NVIDIA)

*Render API* dans le Manager (`render_api` dans le fichier) choisit comment le lecteur affiche l'image sur une carte NVIDIA. Relancer le lecteur après un changement.

| | Direct3D 11 (défaut) | Vulkan |
|---|---|---|
| RTX TrueHDR et RTX VSR | filtres du lecteur, curseurs de l'application NVIDIA | dans le moteur AnimeJaNai, en CUDA ; curseurs dans le Manager (`rtx_vsr_quality`, `rtx_contrast`, `rtx_saturation`, `rtx_middle_gray`) |
| Trajet des images | passage par la mémoire vive entre CUDA et D3D11 | elles restent dans la mémoire du GPU |
| NVIDIA Smooth Motion | sans effet | actif (le compteur NVIDIA double) |
| Grading, sous-titres, mire | identiques | identiques |

Le mode Vulkan demande `aji_trt_rtx.dll`, `aji_rtx.dll`, `nvngx_truehdr.dll`, `nvngx_vsr.dll` et `cudart64_12.dll` dans `animejanai/inference`. Ces fichiers ne font pas partie des versions publiées ; ils se compilent avec `D:\AnimeJaNai-dev\aji-rtx` et ne sont pas touchés par les mises à jour. S'ils manquent, ou quand aucune chaîne AnimeJaNai n'est active (Ctrl+0, source hors plage), le lecteur convertit lui-même en HDR, comme sur AMD. Le moteur d'origine `aji_trt.dll` n'est pas modifié : Direct3D 11 fonctionne exactement comme avant.

**Dessins tenus** (*Reuse Held Frames*, `skip_held_frames`) : un anime répète chaque dessin sur deux ou trois images. En mode Vulkan, une image dont tous les blocs de 32x32 pixels sont identiques à la dernière image traitée reprend son résultat, au lieu de repasser dans RIFE, le modèle, VSR et TrueHDR. `held_threshold` est l'écart toléré par bloc, en niveaux sur 255 (0,40 par défaut). Mesuré sur 60 s, sans image perdue dans les deux cas : profil 4, GPU de 90 % à 81 % ; profil 2, de 60 % à 52 %. La charge en pointe ne change pas : les scènes en mouvement sont traitées comme avant.

Limites du mode Vulkan : RIFE doit rester « avant la mise à l'échelle » (réglage des profils fournis) ; un profil NVIDIA de l'application NVIDIA est lié au dossier du lecteur, donc Smooth Motion se règle pour le `mpvnet.exe` de ce dossier. AMD et Intel utilisent toujours Direct3D 11.

Mesures sur RTX 4070 Ti, épisode 1080p, 3840x2160 HDR : profil 2 (TrueHDR seul) 53 % de GPU, profil 4 (RIFE x2, VSR qualité 2, TrueHDR) 84 % en moyenne et 98 % en pointe, sans image perdue en 24 s.

## Banques de profils

Les banques éditables sont `portable_config/profiles/nvidia/animejanai.conf` et `portable_config/profiles/amd/animejanai.conf`. Au démarrage, la banque du GPU est copiée dans `animejanai/animejanai.conf`, la copie que le Manager édite (Ctrl+E). Au démarrage suivant, les modifications faites dans le Manager sont reportées dans leur banque. `profiles/active-bank.json` sert à attribuer ces modifications à la bonne banque : le garder. Si les deux fichiers ont été modifiés séparément, le conflit est signalé et aucun fichier n’est écrasé.

## Mises à jour AnimeJaNai

`AnimeJaNaiUpdater.exe` (Ctrl+U) télécharge les versions du dépôt `Ta2b/mpv-AnimeJaNai-HDR`, pas celles du projet d'origine. Ne pas utiliser l'installeur ni l'Updater d'origine sur ce dossier : ils remettraient les scripts et le Manager sans HDR.

Une mise à jour remplace `scripts/`, `shaders/`, `user-scripts/`, `user-shaders/`, `hdr-tools/`, `mpv-animejanai.conf`, `input-animejanai.conf`, les modèles AnimeJaNai, les deux Managers et les bibliothèques `aji`. Elle conserve `mpv.conf`, `input.conf` (section personnelle sous le marqueur), `script-opts/animejanai_hdr_auto.conf`, `profiles/` et `animejanai/animejanai.conf`. Une modification faite à la main dans un dossier remplacé est perdue : la faire dans le dépôt, puis publier une version.

Les bibliothèques `aji` et le lecteur sont ceux du projet d'origine, sans modification (`aji` v0.11.1, mêmes empreintes). Ce qui est propre à ce fork : les scripts de `user-scripts/` et `hdr-tools/`, le shader de grading et le Manager HDR.

Ne pas repasser `load-scripts=yes`, sinon les contrôleurs officiels tourneraient en double. Après une mise à jour majeure, relancer et vérifier Ctrl+Alt+H.
