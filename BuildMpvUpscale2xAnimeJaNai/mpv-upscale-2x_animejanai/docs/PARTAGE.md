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
| **Ctrl+3** | Profil 3 « 2K », par défaut : réduction 720p, RIFE ×2 sur NVIDIA, ×2 → 1440p, VSR → écran. |
| **Ctrl+4** | AMD uniquement : profil 2K + AMF ×2 expérimental (sources ≤ 31 i/s). |
| **Ctrl+G** | Grading HDR avec / sans, pour comparer. Le HDR et la chaîne vidéo restent actifs. |
| **b** | Debanding activé / désactivé. |
| **Ctrl+Alt+H** | Diagnostic : sortie, écran, VSR, HDR Windows, TrueHDR, cible MPV, grading et ses paramètres, profil AnimeJaNai, images perdues. |

Ctrl+E ouvre le Manager, Ctrl+U installe une mise à jour. Fermer complètement MPV et le relancer après un changement de réglage.

## Réglages dans le Manager (Ctrl+E)

**Ctrl+E** ouvre `AnimeJaNaiManager-HDR.exe` : le Manager 0.6.0 compilé avec une rubrique supplémentaire dans **Global Settings**, sous *GPU Subtitle Rendering*. L'original reste accessible par le menu AnimeJaNai.

| Réglage du Manager | Clé du fichier |
|---|---|
| Upscale to Display : Auto / RTX Video Super Resolution / AMD VideoSR / Standard / Off | `vsr` |
| Target Resolution | `target_resolution` |
| SDR to HDR Conversion (grise tout ce qui suit quand décoché) | `hdr_conversion` |
| SDR to HDR Backend : Auto / RTX Video HDR / mpv | `hdr_backend` |
| HDR Enhancement > Enhance HDR Picture | `grade` |
| Black Depth (%) | `shadows` |
| Also Enhance Native HDR Videos | `grade_native_hdr` |
| With RTX Video HDR > Highlight Boost / Color Vibrance (%) | `highlights_rtx` / `vibrance_rtx` |
| With mpv Conversion > SDR White Level / Highlight Boost / Color Vibrance | `paper_white` / `highlights` / `vibrance` |
| Display on NVIDIA PC / on AMD / Intel PC : Windows HDR, Peak Brightness, Color Gamut, OLED | `mode` / `amd_mode`, `peak_*`, `gamut_*`, `oled_*` |

Le Manager écrit directement `script-opts/animejanai_hdr_auto.conf` en conservant les commentaires. Les pourcentages correspondent aux fractions du fichier (85 % = 0.85). Le bloc *(this PC)* indique l'écran utilisé sur le PC courant. Relancer le lecteur après une modification.

Source : branche `hdr-settings` du dépôt GitHub `Ta2b/AnimeJaNaiManager-HDR`. Chaque push recompile l'exe dans une release GitHub. L'Updater ne remplace pas ce fichier : après une mise à jour majeure d'AnimeJaNai, il faudra reporter ces changements sur le Manager correspondant.

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

### Moteur HDR et mise à l’échelle

| Réglage | Valeurs |
|---|---|
| `hdr_conversion` | `yes` / `no`. `no` : les vidéos SDR restent SDR et le HDR Windows n'est jamais modifié. |
| `hdr_backend` | `auto` (RTX sur NVIDIA, MPV ailleurs), `rtx`, `mpv`. `mpv` sur NVIDIA permet de comparer avec TrueHDR. |
| `vsr` | `auto`, `nvidia`, `amd`, `classic` (D3D11), `no`. Une valeur incompatible avec la carte se replie sur `classic`. |
| `target_resolution` | `auto` ou une taille fixe, par exemple `2560x1440`. |
| `mode` / `amd_mode` | `enable` : MPV active le HDR Windows puis le restaure. `follow` : suivre l’état de Windows. |

## Points propres à AMD (non testés sur la RX 9070 XT)

- AMD VideoSR passe par la RAM (sortie AMF téléchargée en P010) : coût à mesurer. En cas d’échec, repli classique pour le fichier courant.
- AMF ×2 (Ctrl+4) : filtre natif `amf_frc`, appliqué après AnimeJaNai. En cas d’erreur, retour automatique au profil 2 ; il peut falloir rouvrir le fichier. Le cumul avec RIFE est possible en activant RIFE dans le profil AMD 4.
- Commencer par Ctrl+3 et vérifier les images perdues avec Ctrl+Alt+H.

## Banques de profils

Les banques éditables sont `portable_config/profiles/nvidia/animejanai.conf` et `portable_config/profiles/amd/animejanai.conf`. Au démarrage, la banque du GPU est copiée dans `animejanai/animejanai.conf`, la copie que le Manager édite (Ctrl+E). Au démarrage suivant, les modifications faites dans le Manager sont reportées dans leur banque. `profiles/active-bank.json` sert à attribuer ces modifications à la bonne banque : le garder. Si les deux fichiers ont été modifiés séparément, le conflit est signalé et aucun fichier n’est écrasé.

## Mises à jour AnimeJaNai

L’Updater remplace `scripts/`, `shaders/`, `mpv-animejanai.conf` et `input-animejanai.conf`. Il préserve `mpv.conf`, `input.conf` (section personnelle sous le marqueur) et ne touche pas `user-scripts/`, `user-shaders/`, `hdr-tools/`, `profiles/` ni `script-opts/`. Ne pas repasser `load-scripts=yes`, sinon les contrôleurs officiels tourneraient en double. Après une mise à jour majeure, relancer et vérifier Ctrl+Alt+H.
