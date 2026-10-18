# Contrat des profils v2 : étapes seules, HDR global

Décidé le 18 octobre 2026 après le diagnostic du Manager (AH-379, AH-403 à AH-406). Ce contrat lie le Manager, les scripts du lecteur (`portable_config/hdr-tools`), le résolveur partagé (`AnimeJaNaiPlatform --profile-plan`) et les moteurs. Il remplace les règles « clés héritées + étapes » et « conversion HDR dans les profils » des [étages d'interpolation](INTERPOLATION-STAGES.md).

## 1. Principes

1. **Une seule représentation** : un profil est une liste de règles (conditions de résolution et de cadence), chaque règle une liste ordonnée d'étapes (`resize`, `interpolate`, `upscale`). Le Manager n'écrit plus les clés héritées (`chain_N_rife*`, `chain_N_model_M_*`) ; le lanceur les régénère à l'exécution quand la chaîne est exprimable par le moteur hérité.
2. **Le HDR est un réglage global**, pas une étape : `désactivé`, `conversion mpv` (tonemapping du rendu) ou `NVIDIA TrueHDR` (dans le moteur, si le SDK et les modules sont présents). Le lecteur l'applique toujours au même endroit : après la dernière étape d'inférence, avant l'affichage. Plus d'étape `hdr` dans les profils ; une étape `hdr` lue dans un ancien fichier est ignorée (voir §5).
3. **Le fichier source n'est jamais lu par un moteur** : le lecteur fabrique une copie d'exécution normalisée (§4). Un ancien moteur ou un ancien Manager ne peuvent plus désynchroniser deux représentations.
4. **Ce qui est indisponible est grisé avec sa cause**, jamais écrit en silence sous une autre forme (pas de repli `nvidia-truehdr → mpv` muet, pas d'étape créée inactive sans raison).

## 2. `animejanai.conf` écrit par le Manager

```
[global]
config_version=4
backend=TensorRT            # Vulkan, MIGraphX, OpenVINO, DirectML, CoreML… selon la plateforme
rife_engine=quality         # politique par défaut : quality | fast (old/new acceptés en lecture)
rife_drawings=yes
default_slot=3
logging=yes
[slot_N]
profile_name=…
chain_K_min_resolution=0x0  chain_K_max_resolution=1920x1080  chain_K_min_fps=0  chain_K_max_fps=61
chain_K_pipeline_version=1
chain_K_stage_count=3
chain_K_stage_J_id=…        # [A-Za-z0-9_-]{1,64}, unique dans la règle
chain_K_stage_J_kind=resize | interpolate | upscale
chain_K_stage_J_method=area | spline36 | bilinear | rife | onnx
chain_K_stage_J_runtime=tensorrt | cuda | vulkan | …   # cuda pour area
chain_K_stage_J_enabled=yes|no
chain_K_stage_J_model=…     # nom ONNX (upscale) ou code RIFE (426)
chain_K_stage_J_factor_numerator=2  chain_K_stage_J_factor_denominator=1   # interpolate seulement
chain_K_stage_J_policy=quality|fast
# options par étape : resize → target_height | target_percent (+ legacy_geometry=linux:tensorrt pour une
# réduction importée d'un ancien profil) ; interpolate → ensemble, scene_detect_threshold ;
# upscale → frames, temporal_scene_threshold
```

Interdits dans un fichier v4 : `hdr_stage_controlled`, les étapes `kind=hdr`, les clés `chain_K_rife*` et `chain_K_model_M_*`, les clés `chain__*` (numéro de règle vide). Le Manager les supprime à la première sauvegarde (§5) et refuse d'écrire une règle sans numéro.

## 3. Réglages HDR globaux (`script-opts/animejanai_hdr_auto.conf`)

| Clé | Valeurs | Sens |
|---|---|---|
| `hdr_conversion` | `yes` / `no` | conversion SDR → HDR active |
| `hdr_backend` | `mpv` / `rtx` | `mpv` : tonemapping du rendu (gpu-next, shader `anime-hdr-grade`) ; `rtx` : NVIDIA TrueHDR dans le moteur. `auto` (anciens fichiers) = `rtx` si disponible, sinon `mpv`. |
| `linux_hdr_output` | `auto` / `pq` / `sdr` | sortie Wayland ; la conversion n'a d'effet qu'en PQ négocié |
| `rtx_contrast`, `rtx_saturation`, `rtx_middle_gray`, `paper_white`, `highlights`, `vibrance`, `mpv_truehdr_look`, `grade`, `shadows`… | inchangés | une seule apparence, partagée par les deux conversions |

`conversion_in_profiles` est retiré : le lecteur l'ignore (toujours `no`), le Manager le supprime.

Disponibilité de TrueHDR (Linux) : `libaji_trt_rtx.so` et `libaji_rtx.so` dans `inference/`, SDK Maxine à `ANIMEJANAI_VFX_SDK` ou `/usr/local/VideoFX` (`lib/libVideoFX.so`, `lib/libNVCVImage.so`, `features/nvvfxtruehdr/lib/libnvVFXTrueHDR.so`), GPU NVIDIA, backend TensorRT, sortie PQ. Le Manager et le lecteur appliquent la même liste (§6).

## 4. Ce que fait le lecteur (Linux, `hdr-tools/linux-playback.lua`)

À chaque sélection de profil :

1. **Normalisation** (`stages.normalize(text, platform)`) du fichier source : suppression des étapes `hdr` (renumérotation), de `hdr_stage_controlled`, des clés `chain__*` et de toutes les clés héritées ; puis, pour chaque règle, **projection héritée** régénérée depuis les étapes actives quand la chaîne est exprimable par le moteur hérité (une seule étape RIFE, modèles ONNX en séquence, réduction `spline36`/`bilinear` importée (`legacy_geometry`) remontée dans `resize_height_before_upscale`/`resize_factor_before_upscale` du modèle qui suit, runtime égal au backend) : `chain_K_rife=yes|no`, `rife_model`, `rife_factor_*`, `rife_before_upscale`, `rife_ensemble`, `rife_scene_detect_threshold`, `chain_K_model_M_name`, `_resize_*`, `_frames`, `_temporal_scene_threshold`. Une chaîne non exprimable reçoit `chain_K_rife=no` et aucun modèle : le moteur l'exécute par le pipeline ordonné.
2. **Instantané immuable** (`runtime.store`) de ce texte : le résolveur, la banque de profils et le moteur lisent le même contenu.
3. **Route** (`stages.resolve`) : règle sélectionnée, `legacy_equivalent` (projection réussie), politique RIFE de l'étape, facteur de cadence cumulé. Plus de champs `hdr`/`hdr_stage_controlled`.
4. **HDR** : `hdr_wanted = profil actif et hdr_conversion et backend résolu = rtx et TrueHDR disponible`. Route héritée : `animejanai-rtx.conf` écrit (`hdr=yes`) et moteur `libaji_trt_rtx.so` ; sinon le fichier est supprimé. Route ordonnée : `runtime.prepare` ajoute une étape `hdr` (`id=global-hdr`, `method=nvidia-truehdr`, `runtime=cuda`, `sdk_root`, `peak`, `contrast`, `saturation`, `middle_gray` depuis les réglages) en fin de règle dans la copie d'exécution. `user-data/animejanai-pipeline-configured` publie `hdr={method='nvidia-truehdr'}` dans ce cas ; `linux-hdr.lua` confirme la conversion par la sortie PQ/BT.2020 réelle. Backend `mpv` : `linux-hdr.lua` applique le shader de conversion quand la sortie PQ est négociée. `hdr_conversion=no` : rien.
5. **Copie d'exécution** (`runtime.prepare`) : `[global] rife_engine` = politique de la règle quand elle est projetable ; étape HDR injectée si demandée ; sinon texte normalisé inchangé.

Windows (`user-scripts/animejanai_slot.lua`, `animejanai_hdr_auto.lua`) et macOS consomment les mêmes fonctions ; `pipeline-hdr.lua` ne surcharge plus les réglages par le profil (`options(base, route)` rend `base`).

## 5. Migration des anciens fichiers (Manager, à l'ouverture ; lecteur, à la normalisation)

| Trouvé | Manager (écrit v4) | Lecteur (copie d'exécution) |
|---|---|---|
| règle avec clés héritées seules (`config_version ≤ 3`) | étapes `legacy-model-N` / `legacy-rife` / `legacy-model-N-resize` (inchangé) | projection depuis les étapes générées |
| étape `kind=hdr` activée | supprimée ; si c'était la première rencontrée : `hdr_conversion=yes` et `hdr_backend` = `rtx` (nvidia-truehdr) ou `mpv` ; ses `contrast`/`saturation`/`middle_gray`/`peak` recopiés dans les réglages globaux **seulement** s'ils valent les défauts (100/100/50/1000) ou si l'utilisateur confirme (avis une fois) | ignorée, message d'information une fois |
| étape `kind=hdr` inactive | supprimée | ignorée |
| `hdr_stage_controlled`, `conversion_in_profiles` | supprimés | ignorés |
| `chain__*` | supprimés | ignorés |
| clés héritées à côté d'étapes | supprimées (les étapes font foi) | remplacées par la projection |
| étape `nvidia-fruc` | conservée, inactive, « technologie retirée » | ignorée si inactive ; erreur si active (inchangé) |

Le Manager affiche un avis unique listant ce qu'il a changé et garde une sauvegarde (`backups/`).

## 6. Disponibilité des technologies

Le Manager lit les modules dans `ANIMEJANAI_DATA_DIR/inference` ; sous AppImage ces entrées sont des liens vers l'image montée (`/tmp/.mount_*`), **pendants** quand le Manager n'est pas lancé par le lecteur. `AppRun` exporte `ANIMEJANAI_IMAGE_DIR=$HERE` ; quand un fichier manque ou que son lien est pendant, le Manager lit `$ANIMEJANAI_IMAGE_DIR/animejanai/inference/<fichier>`. Causes affichées, par priorité : GPU non NVIDIA ; backend ≠ TensorRT ; module absent (nom) ; SDK absent (chemin attendu, bouton « Importer le SDK ») ; sortie non PQ (lien vers Réglages).

## 7. Contrôles

- Lua : `tests/player/interpolation_stages_check.lua`, `legacy_policy_projection_check.lua`, `linux_profile_snapshot_check.lua`, `interpolation_launch_check.lua`, `chain_cleanup_launch_check.lua`, `tests/hdr/run_hdr_stage_tests.lua`, `run_mpv_stage_tests.lua`, `run_linux_tests.lua` : mis à jour pour ce contrat (plus d'étape HDR de profil ; projection depuis les étapes ; HDR global).
- Manager : `tests/ProfileRoundTrip` (migration v3 → v4, purge, HDR global), rendu sans tête `tests/NavigationUi` (captures).
- Preuve utilisateur : journal `currentanimejanai.log` cohérent avec le profil affiché (étapes, résolution de sortie, ligne `Applied RTX Video` seulement quand TrueHDR est choisi).
