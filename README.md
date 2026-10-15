# mpv-AnimeJaNai HDR (fork)

**Portage Linux en cours, Windows conservé.** Le paquet de test inclut le
lecteur SDR Vulkan/Wayland et le Manager HDR. AnimeJaNai SPAN et RIFE 4.6
utilisent NCNN/Vulkan sur AMD et NVIDIA, avec Performance sans RIFE au premier démarrage. TensorRT reste
une option NVIDIA distincte. Les essais physiques HDR et RTX
4050 restent nécessaires ; Linux demeure expérimental dans les releases communes. Voir
[la documentation Linux](docs/LINUX.md) pour la construction, les tests et les limites.

**[3.8.0.31 publiée sur Windows, Linux et macOS](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/releases/tag/3.8.0.31).**
RIFE propose maintenant **Quality** (prédiction complète par instant) et **Fast**
(reconstruction/réutilisation temporelle). CUDA optimise les attentes, conversions,
captures et préparations communes ; le lecteur Linux livre la gestion des paires
et des sorties groupées. Les anciens réglages old/new restent reconnus.
Voir [le bilan, les limites et la suite](docs/CHANTIER-QUALITY-FAST.md).
Aucun nouveau benchmark ni contrôle de qualité sur GPU n'a été exécuté.

**Historique — 3.8.0.30 :** **[3.8.0.30 publiée sur Windows, Linux et macOS](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/releases/tag/3.8.0.30).**
MIGraphX + HIP natif pour RX 9070 XT et TensorRT + CUDA spécialisé sont embarqués,
avec les modèles actuels. Linux AMD nécessite un runtime ROCm 7.2 compatible.
Les builds et la publication ont réussi ; le fonctionnement et les gains GPU
restent à vérifier sur matériel. Voir [le checkpoint et les limites](docs/CHANTIER-GPU-SPECIALISE.md).

**Historique :** **État au 14 octobre 2026 :** [3.8.0.29 publiée sur Windows, Linux et macOS](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/releases/tag/3.8.0.29).
Le moteur partagé dispose de la nouvelle chaîne RIFE : upscale des sources une
seule fois, mouvement réutilisé par paire et lissage de la chronologie des dessins.
Dans cette ancienne version, la chaîne CUDA était installée séparément ;
la 3.8.0.30 embarque désormais les binaires spécialisés. Les paquets et mises à
jour sont allégés. Voir [l'état du projet](docs/ETAT-PROJET.md),
[le chantier 165 Hz](docs/CHANTIER-RIFE-165HZ.md) et
[le relais des premiers lots](docs/CHANTIER-PERFORMANCE-RELAIS.md).


Fork de [the-database/mpv-upscale-2x_animejanai](https://github.com/the-database/mpv-upscale-2x_animejanai), basé sur la version **3.8.0** (branche `hdr-3.8`, version publiée par défaut ; la branche `hdr` reste sur la 3.6.3). Il ajoute une conversion SDR → HDR soignée pour l'anime et s'adapte tout seul aux cartes NVIDIA et AMD :

- **NVIDIA** : RTX Video HDR (TrueHDR) et RTX Video Super Resolution après AnimeJaNai/RIFE (TensorRT).
- **AMD / Intel** : HDR calculé par mpv, AMD VideoSR, inférence DirectML, AMF ×2 en option sur tous les profils.
- **Fréquence d'écran automatique** (3.8.0) : une fréquence multiple de la cadence vidéo, RIFE compris.
- **Grading HDR commun** (`user-shaders/anime-hdr-grade.hook`) : noirs plus profonds, éclats locaux jusqu'au pic de l'écran, vibrance ICtCp limitée au gamut P3, peau protégée. **Ctrl+G** compare avec et sans.
- **Réglages dans le Manager** (Ctrl+E → [AnimeJaNai Manager HDR](https://github.com/Ta2b/AnimeJaNaiManager-HDR)) : mise à l'échelle finale, conversion SDR → HDR, moteur, intensités, et une seule section écran (suivi HDR du système, pic et gamut automatiques, OLED optionnel).
- Les fichiers du fork sont dans `user-scripts/`, `user-shaders/` et `hdr-tools/` (mis à jour par l'Updater du fork), plus `profiles/` et `script-opts/` (tes réglages, jamais écrasés).

**Releases** : mêmes fichiers que le projet original (installateur `mpv-AnimeJaNai-HDR-Setup-<version>.exe`, paquet complet `.7z`, overlay de mise à jour, `manifest.json`, packs de composants TensorRT / RIFE). Les versions suivent celle de base plus un numéro de révision du fork (`3.8.0.1`, `3.8.0.2`…). Pour publier une version : mettre son numéro dans `release-version.txt` puis pousser sur la branche `release` ; le workflow *Deploy* compile et publie la release (il crée le tag lui-même). L'Updater (Ctrl+U) et les composants du Manager se servent de ces releases. L'installateur a son propre identifiant et s'installe à côté du lecteur officiel, sans le remplacer.

Fichiers : `BuildMpvUpscale2xAnimeJaNai/mpv-upscale-2x_animejanai/` (overlay), avec la documentation dans `docs/ANALYSE.md` et `docs/PARTAGE.md`. Le constructeur (`Program.cs`) ajoute la section personnelle d'`input.conf` et télécharge le Manager HDR.

---

# Upscaling Anime with mpv-AnimeJaNai
[![Discord](https://img.shields.io/discord/1121653618173546546?label=Discord&logo=Discord&logoColor=white)](https://discord.gg/EeFfZUBvxj)

<a href="./demov3.webp?raw=1"><img src="demov3.webp"/></a>
<p align="center"><sup>(click image to enlarge)</sup></p>

## Overview

This project provides a collection of Real-ESRGAN Compact ONNX upscaling models, along with a custom build of mpv video player. The video player (currently Windows only), enables real-time upscaling of 1080p content to 4K by running these models using TensorRT (NVIDIA only) or DirectML (for AMD or Intel Arc). While the default configuration upscales using the 2x_AnimeJaNai models, it can be easily customized to utilize any Real-ESRGAN Compact ONNX models.

Join the [**JaNai Discord server**](https://discord.gg/EeFfZUBvxj) to get the latest news, download pre-release and experimental models, get support and ask questions, share your screenshots (use the `s` key in mpv), or share your feedback. 日本語も大丈夫です。

## Usage Instructions
Ensure your NVIDIA graphics drivers are up to date. Download and extract the [latest release archive](https://github.com/the-database/mpv-upscale-2x_animejanai/releases) of mpv-upscale-2x_animejanai. Open the video player at `mpvnet.exe`.

When playing a video for the first time, a TensorRT engine file will be created for the selected ONNX model. Playback will be paused and a command prompt box will open. Please make sure to wait while the engine is created. Engine creation only needs to happen once per model. Playback will resume on its own when finished.

To confirm upscaling status, press `ctrl+J` to view upscaling stats. This shows the current profile, and the currently running upscaling models if any. 

The player is preconfigured to upscale with the 2x_AnimeJaNai V3.1 models, and makes 3 upscaling profiles available by default. The available profiles are described in more detail below. Any of these profiles can be selected on the fly using the keybinding listed below. 

|Profile | Description | Keybinding | Minimum recommended GPU for upscaling 1080p to 4k |
|-|-|-|-|
|Quality | Highest quality model | `Shift+1` | RTX 4090|
|Balanced | High quality model which trades slight quality for major performance gains | `Shift+2` | RTX 3080|
|Performance | Fastest performance model which sacrifices a bit more quality  | `Shift+3` | RTX 3060|

The default upscaling profile is the Balanced profile which is recommended for users running an NVIDIA RTX 3080 or higher. 

## Updating

mpv-upscale-2x_animejanai checks for updates on startup. When a newer version is available, an
on-screen message appears; press `Ctrl+U` (or use the *AnimeJaNai > Install Update* menu) to install
it. mpv closes, the update is applied in place, and mpv reopens automatically.

Your customizations are preserved across updates: your profiles (`animejanai.conf`), your mpv
settings in `mpv-user.conf`, and any ONNX models you added to `animejanai/onnx/` are never
overwritten. Most updates are small because the large GPU runtime is only re-downloaded when it
actually changes. (Your previous `input.conf` is backed up to `input.conf.bak-<version>` before the
shipped keybindings are refreshed.)

> Note for users upgrading from a version before this updater existed: download the
> [latest release](https://github.com/the-database/mpv-upscale-2x_animejanai/releases) once
> manually; from then on updates are handled in place.

## Customizing Profiles and Other Settings

### Automatic Display Refresh Rate (Experimental, Windows)

Enable this option in Manager's **Profiles** tab and restart the player. With a
compatible AJN player build, it scans local video timestamps before playback
and chooses one display refresh for the whole episode, including across seeks.
Fixed-rate videos prefer an exact or near supported multiple. Mixed-rate videos
prefer a common multiple of all measured cadences; otherwise, AJN minimizes
estimated timing error weighted by each cadence's duration. Unverified inputs
use the highest supported progressive refresh at the current resolution.

Playback pauses with a notice before a needed switch and resumes after the
settling interval; manual pauses are preserved. Matching consecutive episodes
retain their rate. Scanning can add startup time, and your TV may briefly go
black during a change. The original refresh is restored at playback end or
normal player exit. The feature is off by default, does not
interpolate video, and does not change your `video-sync` setting. A display limited
to 60 Hz is supported, though arbitrary VFR cannot always have perfectly even
presentation on a fixed-refresh display. Windows driver/TV switching behavior
still needs testing on your hardware.

The setting requires all three updated components: Manager, the native mpv
player with `display-rate-match`, and `scripts/animejanai_backend.lua`.

### Profiles

Upscaling can be further customized using the AnimeJaNai Manager which can be launched by pressing `ctrl+E` from mpvnet. The Manager allows the setup of up to 9 custom slots and also the use of custom chains, conditional settings based on video resolution and framerate, downscaling to improve performance, and more. The default upscaling profile can also be set in the Manager. 

![image](https://github.com/the-database/mpv-upscale-2x_animejanai/assets/25811902/76a8db5b-8c67-4b0c-911a-9b02598fb37a)


All other mpv settings can be configured by adding them to `mpv-upscale-2x_animejanai/portable_config/mpv-user.conf` (see the [mpv manual](https://mpv.io/manual/stable/) for all options). Put your custom mpv options in `mpv-user.conf` rather than `mpv.conf` — `mpv-user.conf` is applied last (so it overrides the defaults) and is never overwritten when you update, so your settings survive upgrades. Likewise, add custom keybindings to `mpv-upscale-2x_animejanai/portable_config/input-user.conf` (same syntax as `input.conf`); they override the shipped bindings and are also preserved across updates. 

By default, screenshots can be taken with the `s` key and are stored in `mpv-upscale-2x_animejanai/portable_config/screenshots`. 

## Setup for AMD or Intel Arc users.

mpv-upscale-2x_animejanai is configured to use TensorRT by default for optimal performance, but TensorRT requires an NVIDIA GPU. Users with AMD or Intel Arc GPUs can use DirectML instead. See the [wiki page](https://github.com/the-database/mpv-upscale-2x_animejanai/wiki/Setup-for-AMD-or-Intel-Arc-users) for detailed instructions. 

## 2x_AnimeJaNai Models
The 2x_AnimeJaNai models are a collection of real-time 2x Real-ESRGAN Compact, UltraCompact, and SuperUltraCompact models designed specifically for doubling the resolution of HD and SD models. 

### 2x_AnimeJaNai HD V3 Models

Most HD anime are [not produced in native 1080p resolution](https://guide.encode.moe/encoding/descaling.html) but rather have a production resolution between 720p and 1080p. When the anime is distributed to consumers via TV broadcast, web streaming, or home video, the video is scaled up to 1080p, leading to scaling artifacts and a loss of image clarity in the source video. The aim of these models is to address these scaling and blur-related issues while upscaling to deliver a result that appears as if the anime was originally mastered in 4K resolution.

The development of the V3 models spanned over seven months, during which over 100 release candidate models were trained and meticulously refined. The V3 models introduce several notable improvements compared to their V2 counterparts, including:
- More faithful appearance to original source
- Improved handling of oversharpening artifacts, ringing, aliasing
- Better at preserving intentional blur in scenes using depth of field
- More accurate line colors, darkness, and thickness
- Better preservation of soft shadow edges

Overall, the V3 models yield significantly more natural and faithful results compared to the V2 models. 

### 2x_AnimeJaNai SD V1 Models

2x_AnimeJaNai SD V1 models are in development. The latest release of mpv-upscale-2x_animejanai includes an early beta model for 2x_AnimeJaNai SD V1. While the 2xAnimeJaNai HD models can also work well for some SD sources, those models were specifically trained to upscale HD anime and don't always work well for SD sources. The SD models are designed to upscale SD anime to appear as if the anime was mastered in HD resolution. With sufficient hardware, these models can be stacked with the HD models to upscale SD anime to 4k resolution. 

## Benchmarks
[Benchmarks](https://github.com/the-database/mpv-upscale-2x_animejanai/wiki/Benchmarks) for various hardware configurations tested against various upscaling configurations are available on the wiki. 

## Support for Other Media Players
Any media player which supports external DirectShow filters should be able to run these models, by using [avisynth_filter](https://github.com/CrendKing/avisynth_filter) to get VapourSynth running in the video player. 

## Prerendering Videos using Other Graphics Cards
The 2x_AnimeJaNai_V2 ONNX models can be used on a PC with any graphics card to render upscaled videos, even when using graphics cards not fast enough for realtime playback. Please see the [AnimeJaNaiConverterGui](https://github.com/the-database/AnimeJaNaiConverterGui) project to create upscaled video files using a Windows GUI. Other options include [chaiNNer](https://github.com/chaiNNer-org/chaiNNer) or [VSGAN-tensorrt-docker](https://github.com/styler00dollar/VSGAN-tensorrt-docker), which are multiplatform options for Windows and non-Windows users.

## Related Projects
- [MangaJaNai](https://github.com/the-database/mangajanai): Upscale manga with ESRGAN models
- [VideoJaNai](https://github.com/the-database/VideoJaNai): Windows GUI for upscaling videos with extremely fast performance
- [traiNNer-redux](https://github.com/the-database/traiNNer-redux): Software for training upscaling models

## Acknowledgements
- [Upscale Wiki](https://upscale.wiki/wiki/Main_Page) and associated Discord server
- [422415](https://github.com/422415) for significant assistance in dataset preparation and continuous feedback during development of V2 models
- Community feedback on V1 models
- [MPV_lazy](https://github.com/hooke007/MPV_lazy) and [vs-mlrt](https://github.com/AmusementClub/vs-mlrt)
- [traiNNer-redux](https://github.com/joeyballentine/traiNNer-redux)
- [Dataset Destroyer](https://github.com/Kim2091/helpful-scripts/tree/main/Dataset%20Destroyer)
- [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN)
- [OpenModelDB](https://openmodeldb.info/)
- [getnative](https://github.com/Infiziert90/getnative) and [anibin](https://anibin.blogspot.com/)

### Publication Windows et Linux

Les releases du fork réunissent les fichiers Windows et Linux sous la même
version. Windows conserve ses noms d’assets ; les paquets Linux portent
`linux-x64`. Linux reste expérimental pour les essais physiques NVIDIA/HDR.
Les contrôles précèdent les builds indépendants et la publication commune.
Voir [le guide de release](docs/RELEASE.md).
