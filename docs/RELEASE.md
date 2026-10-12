# Publication du fork HDR

Pour l’état temporaire des builds du 12 octobre 2026 et les actions restantes,
consulter [le document de reprise](REPRISE.md). Les procédures ci-dessous
décrivent le workflow ; elles ne prouvent pas à elles seules une publication.

Les dépôts actifs sont `Ta2b/mpv-AnimeJaNai-HDR` (branche `hdr-3.8`) et
`Ta2b/AnimeJaNaiManager-HDR` (branche `hdr-settings-0.8`). Windows conserve
ses noms d’assets. Linux et Windows sont joints à la même release et utilisent la même version.
Les notes identifient Linux comme expérimental tant que les essais physiques
NVIDIA et HDR ne sont pas terminés.

## Workflows conservés

| Workflow | Rôle |
|---|---|
| HDR tests | Tests Lua et shaders dans mpv/libplacebo ; réutilisé avant publication |
| Platform checks | Banques, conflits, IPC, Manager, interface et compilations Windows/Linux ; fidélité SPAN avec Vulkan logiciel |
| Deploy | Contrôles, builds indépendants, puis publication centralisée |
| Build AnimeJaNai Manager (HDR) | Tests et builds Windows/Linux, publication commune des deux plateformes |
| HDR tools sources | Sources des outils Windows présents dans le paquet |
| Upstream watch | Suivi des nouvelles releases amont |
| Build benchmark catalog | Publication du catalogue de résultats soumis |

Le workflow de l’ancienne image Ubuntu 22.04 est supprimé : le fork construit
son lecteur Wayland sur Ubuntu 24.04 sans image privée. L’ancien `release.yml`
du Manager est supprimé au profit du workflow HDR commun. Les sources du
Manager sont publiées dans leur dépôt : aucun patch inter-dépôts n’est rejoué.

## Sources et versions

- `release-version.txt` : version Windows, actuellement **3.8.0.9**.
- `manager-source-ref.txt` : SHA exact du Manager utilisé par les contrôles
  et le build Linux. L’assembleur télécharge ses paquets via le tag immuable
  `hdr-<SHA>` ; le binaire et ses bibliothèques natives proviennent du même build.
- `player-source-ref.txt`, dans le Manager : SHA exact du lecteur qui fournit
  `AnimeJaNaiPlatform/PlatformServices.cs`.
- `installer/linux/build-native.sh` : références du lecteur, FFmpeg,
  Wayland, libass et libplacebo. mpv et `aji` conservent l’ABI TensorRT 9.
- `installer/linux/build-inference.sh` : références NCNN, RIFE et parseur
  AnimeJaNai ; les modèles SPAN sont convertis depuis les ONNX livrés.
- Les constantes restantes de `BuildMpvUpscale2xAnimeJaNai/Program.cs`
  fixent les dépendances Windows, TensorRT, CUDA et 7-Zip.

Quand l’ABI de `aji.h` change, reconstruire ensemble le filtre mpv et `aji`.
Les trois constantes Windows `MpvForkVersion`, `MpvForkBuildDate` et
`MpvForkGitHash` décrivent le même build et doivent être modifiées ensemble.
Ne pas déduire la version CUDA de la version TensorRT.

## Ordre de publication

1. Valider localement les changements nécessaires et mettre les documents à jour.
2. Publier les sources du lecteur puis du Manager sur leurs branches actives.
   Le workflow du Manager construit les deux plateformes et publie `hdr-<SHA>`
   ainsi que `latest-hdr-settings-0.8`. Ce tag roulant conserve les fichiers
   existants ; les builds indépendants ne publient jamais chacun de leur côté.
3. Vérifier les assets du Manager, puis pousser le commit du lecteur sur `release`.
   Un push sur cette branche lance `Deploy` avec les deux builds.
4. Vérifier les contrôles et les assets publiés. Aucun push forcé n’est nécessaire.

Les anciennes releases ne sont pas réécrites pour changer de version. Lorsqu’un
build est relancé, les assets du même nom peuvent être remplacés ; les fichiers
de l’autre plateforme restent présents. Les publications sont sérialisées et
les tests ne disposent que des droits de lecture.

## Dispatch manuel

```bash
# Les deux plateformes, dans une seule release.
gh workflow run deploy.yml -R Ta2b/mpv-AnimeJaNai-HDR --ref hdr-3.8 \
  -f release_version=3.8.0.9 -f platform=both

# Une seule plateforme.
gh workflow run deploy.yml -R Ta2b/mpv-AnimeJaNai-HDR --ref hdr-3.8 \
  -f release_version=3.8.0.9 -f platform=windows

```

`platform` remplace les anciens booléens contradictoires `windows_only` et
`linux_only`. La publication attend la réussite de toutes les plateformes
demandées ; un échec ne livre pas une release annoncée complète. Une version vide utilise `release-version.txt`. Les contrôles sont
obligatoires avant les builds. Le bundle NCNN/Vulkan vérifié par `Platform checks`
est réutilisé par le build Linux ; aucune deuxième conversion des mêmes modèles.
L’AppImage et l’overlay sont obligatoires pour déclarer le build Linux réussi.

## Assets et canaux

Windows publie la release stable `<version>` : Setup HDR, archive complète
`.7z.001`, overlay `.7z`, `manifest.json`, `packs.json` et composants Windows.
L’assembleur inclut le Manager HDR et ses bibliothèques, avec un alias
`AnimeJaNaiManager.exe` pour les anciennes intégrations.

Linux utilise **le même numéro et le même tag** que Windows. Ses noms incluent
`linux-x64` : portable `tar.zst`, AppImage, overlay,
`manifest-linux-x64.json`, `packs-linux-x64.json` et composants Linux.
Le numéro incorporé correspond au tag public, pour les téléchargements des
composants et les mises à jour. Les fichiers Linux n’écrasent aucun asset Windows.
Le statut expérimental de Linux est indiqué dans les notes de la release
commune ; il n’impose pas une deuxième release.

Le Manager publie `AnimeJaNaiManager-HDR.exe`, `AnimeJaNaiManager-HDR-x64.zip`
et `AnimeJaNaiManager-HDR-linux-x64.tar.zst` ensemble. Ses paquets excluent les
configurations et modèles pour préserver les réglages du lecteur.

Les artefacts de CI conservent aussi les paquets et les rapports de fidélité.
Les essais logiciels ne valident pas un écran HDR physique ni la RTX 4050.
Les conditions locales avec Twitch en arrière-plan ne constituent pas une
référence de performances. Voir [LINUX.md](LINUX.md),
[LINUX-INFERENCE.md](LINUX-INFERENCE.md) et [SETTINGS.md](SETTINGS.md).

## Vérification du nettoyage

Actionlint valide les workflows des deux dépôts. Les contrôles locaux passent :
239 assertions Lua, 14 transactions de banques, 14 régressions updater,
23 cas hors ligne, 13 cas de persistance du Manager et 13 contrôles d’interface.
Les shaders passent dans libplacebo sur la session Wayland disponible.
Le premier passage CI Windows a détecté un nom de dossier PCI invalide dans
la fixture de test sysfs : les deux-points sont remplacés seulement dans cette
fixture Windows, sans modifier la détection Linux du produit.

Les bundles Vulkan et mpv Wayland sont mis en cache sous une empreinte des
sources, scripts et modèles. Les contrôles de fidélité tournent aussi sur un
bundle restauré. Le build Linux réutilise le bundle Vulkan validé dans le même
workflow, puis construit les paquets. Cela évite de recompiler les dépendances
identiques à chaque ajustement documentaire ou relance de publication.

La sérialisation s’applique au job de publication, pour laisser les builds
indépendants progresser. Les contrôles devenus obsolètes sont annulés lors d’un
nouveau push ; un envoi d’assets déjà commencé se termine. Les fichiers de CI
sont aplatis avant l’envoi à GitHub et une liste SHA256SUMS accompagne la release.
Cette étape évite de traiter les sous-dossiers d’artefacts comme des fichiers.

L’override local du Manager ne copie que l’exécutable et les bibliothèques
natives : le répertoire `dotnet publish` contient aussi une configuration
standalone qui changerait la détection de son répertoire de données. Le lecteur
reste propriétaire des configurations et modèles. Le cache du lecteur Wayland
est enregistré dès sa validation, même si une étape ultérieure échoue. Les
erreurs de l’assembleur Linux sont remontées dans les annotations publiques de CI.

Le job Linux libère les SDK Android, Haskell et CodeQL préinstallés sur le
runner, pour laisser l’espace nécessaire aux dépendances, composants et
copies temporaires de l’AppImage. Les sources compilées du lecteur sont
supprimées après validation et sauvegarde de son bundle.

La vérification du lecteur hors du préfixe de compilation a révélé sa dépendance
à `wl_display_create_queue_with_name`, absente du client Wayland 1.22 du runner.
Le patch Linux utilise les deux files sans nom, avec la même distribution des
événements et les mêmes protocoles HDR. Cette adaptation est idempotente et le
marqueur de dépendance mpv est actualisé. Le cache NCNN est désormais limité aux
sources et modèles de la bibliothèque, indépendamment des adaptations de mpv.

Le 12 octobre 2026, le lecteur corrigé a été recompilé et vérifié localement
dans Ubuntu 24.04 avec `libwayland-client0` **1.22.0-2.1build1**, sans le
préfixe de compilation dans `LD_LIBRARY_PATH` : `mpv --version` et
`mpv --vf=help` passent, le filtre `animejanai-vulkan` est présent et ni mpv
ni libmpv n’importent plus `wl_display_create_queue_with_name`.
Les rapports sont `artifacts/workflow-wayland-queue-build.log` et
`artifacts/workflow-wayland-host-validation.log`. Ce contrôle de démarrage
est distinct des essais de lecture sur GPU et de la publication GitHub.

Le build GitHub du même jour confirme cette validation native et produit le
portable Linux ; Windows termine également son build. L’étape AppImage s’arrête
ensuite avec le code 127 : le workflow cherchait `7zz` dans `publish/`, alors
que l’assembleur le place dans le sous-dossier versionné du lecteur. L’AppImage
et l’overlay utilisent désormais explicitement cet exécutable fourni, sans
dépendre d’un 7-Zip installé sur le runner. Les erreurs du script AppImage sont
également remontées dans les annotations publiques lors de la relance.

## Cache des téléchargements du build Linux

Les ONNX SPAN d’origine sont versionnés dans le dépôt ; leur conversion et le
backend Vulkan bénéficient déjà d’un cache compilé. L’assembleur possède aussi
un cache d’archives activé par `ANIMEJANAI_DOWNLOAD_CACHE`. Une clé SHA-256 de
l’URL sépare les versions de RIFE, TensorRT, CUDA et des autres composants.
Chaque archive réutilisée est contrôlée contre son empreinte enregistrée ; les
empreintes NVIDIA fixées dans les sources restent vérifiées par l’assembleur.
Les URL contenant un segment `latest`, notamment yt-dlp, sont exclues.

Le workflow restaure les archives des builds antérieurs et sauvegarde les
téléchargements complets après l’assemblage, avant le packaging : un échec
AppImage ultérieur ne les fait pas perdre. Un changement de version télécharge
uniquement les nouvelles URL et conserve les composants inchangés. Aucun arbre
d’installation ni réglage utilisateur n’est mis dans ce cache. Pour les builds
locaux, définir cette variable vers un dossier persistant ; sans elle, le
comportement de téléchargement habituel est conservé sur Windows et Linux.

Dix contrôles locaux passent dans `tests/download-cache` : réutilisation sans
HTTP et hors ligne, nouvelles versions, corruptions et empreintes invalides,
téléchargement interrompu, exclusion de `latest`, désactivation et nettoyage.
Le contrôle est ajouté à la matrice CI Windows/Linux. Cet ajout vise les
prochains builds ; la relance de release déjà en cours n’est pas interrompue.
Les sorties `bin/` et `obj/` des projets de test sont exclues du suivi Git.
