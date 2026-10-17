# Publication du fork HDR

## Procédure actuelle — 3.8.0.29, 14 octobre 2026

La **[3.8.0.29 est publiée sur Windows, Linux et macOS](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/releases/tag/3.8.0.29)**,
16 assets `uploaded`, source `6fa85bbe932cbcd5725f26b0107c9142b4c7388a`.
[Windows 38570902971](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/actions/runs/38570902971),
[Linux 38570902856](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/actions/runs/38570902856)
et [macOS 38570902519](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/actions/runs/38570902519)
sont terminés avec succès. Les versions 3.8.0.24 à 3.8.0.28 sont également
présentes dans les releases GitHub.

Depuis `6eb4971`, trois workflows remplacent l'ancien Deploy et ses contrôles :

| Workflow actuel | Publication |
|---|---|
| `release-windows.yml` | Windows : Setup, archive, overlay et index de composants |
| `release-linux.yml` | Linux : moteurs, portable/AppImage/overlay, pack ORT/OpenVINO et index |
| `release-macos.yml` | Apple Silicon : moteur partagé, application et benchmark |

Les trois partent sur `release`, publient leurs assets indépendamment sur le tag
lu dans `release-version.txt` et ne contiennent **aucun job de tests**. Une erreur
sur une plateforme n'empêche plus les deux autres de publier. Il faut donc
vérifier les fichiers de chacune avant d'annoncer une release complète.
Les branches `try/**` construisent et archivent des artefacts sans publier.
Un push documentaire sur `hdr-3.8` ne déclenche plus les anciens workflows de tests.

### Pour une future release

1. Publier les sources sur `hdr-3.8`. Si le Manager change, épingler sa source et
   vérifier la présence du paquet correspondant à son SHA immuable.
2. Mettre `release-version.txt` au numéro de la nouvelle version, puis pousser
   le commit retenu sur `release` sans réécrire les anciennes releases.
3. Suivre les trois workflows indépendants et contrôler leurs assets et index.
   Chaque build peut être relancé via `workflow_dispatch` sur le ref voulu :
   `gh workflow run release-linux.yml --ref release` (idem Windows/macOS).
   `rebuild_packs=true` existe sous Windows/Linux pour reconstruire les packs.
4. Conserver les anciennes releases référencées par les index. L'Updater compare
   les versions de contenu des packs ; il ne retélécharge que ce qui a changé.

TensorRT est sorti de l'AppImage ; ORT/OpenVINO Linux et les composants « core »
utilisent des packs. L'absence d'un composant lourd dans une archive principale
ne prouve pas qu'il a été supprimé du produit. Les manifests/index sont la
référence de disponibilité, avec les assets qu'ils pointent.

La chaîne warp RIFE du moteur partagé est maintenant livrée en 3.8.0.29.
Le backend NVIDIA `warp-chain`, installé séparément, et la branche CUDA Graph
`perf-rife-cuda-graphs-20261014` sont deux branches distinctes : leur présence
locale ne prouve pas qu'elles sont dans les paquets Windows/Linux, qui consomment
encore `AjiVersion=v0.11.1`. Voir [l'état courant](archive/2026-10-17/chantiers/ETAT-PROJET.md) et
[le chantier 165 Hz](archive/2026-10-17/chantiers/CHANTIER-RIFE-165HZ.md) pour la matrice des moteurs.

## Archive — procédure et publications jusqu'à la 3.8.0.23

Les workflows, commandes `deploy.yml`, conditions de tests et états ci-dessous
sont ceux de l'ancien système. Ils sont conservés pour expliquer les builds et
les preuves précédentes ; **ne pas les utiliser comme procédure actuelle**.

## Publication confirmée au 14 octobre 2026

**[3.8.0.23 publiée sur Windows, Linux et macOS](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/releases/tag/3.8.0.23)**,
15 assets `uploaded`. Commit de livraison `aab89ba` ;
[Deploy 38479416318](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/actions/runs/38479416318)
et [macOS 38479416046](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/actions/runs/38479416046)
réussis. Deux correctifs de CI ont été nécessaires : fixture de chemins AppImage
portable entre Windows/Linux et contrôle Mac adapté au libellé d'échauffement.

Le code suivant `30a3e83` a sa propre CI réussie sur `hdr-3.8`, mais n'est pas dans
cette release. La branche NVIDIA `f4fcd17` n'est pas intégrée à la dépendance
`AjiVersion=v0.11.1`. Ne pas remplacer les assets 3.8.0.23 avec ces nouveaux lots ;
une future livraison devra avoir son numéro et ses références propres.
[État consolidé](archive/2026-10-17/chantiers/ETAT-PROJET.md), [relais performances](archive/2026-10-17/chantiers/CHANTIER-PERFORMANCE-RELAIS.md).
Les étapes datées du 12 octobre plus bas restent un historique de packaging.

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

- `release-version.txt` : version commune de la release (Windows, Linux, macOS).
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
   Ce push lance trois workflows indépendants : `Release Windows`, `Release Linux`
   et `Release macOS`. Chacun construit sa plateforme et ajoute ses fichiers à la
   release de `release-version.txt` (créée par le premier qui termine) ; l’échec
   de l’un ne retient pas les autres, et il suffit de relancer celui qui a échoué.
   Ils n’exécutent aucun test. Les fichiers qu’une installation attend pour proposer
   la mise à jour (overlay, AppImage, application macOS) sont envoyés en dernier.
4. Vérifier les assets publiés. Aucun push forcé n’est nécessaire.

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

## Component packs reused across releases

The component packs (TensorRT runtime, per-GPU builder resources, RIFE models) are about 5 GB
per release and change only with the `TrtVersion` / `RifeModelsVersion` pins. Deploy therefore
downloads the previous release's `packs*.json` and `manifest*.json` before assembling
(`ANIMEJANAI_REUSE_PACKS_DIR`, `ANIMEJANAI_REUSE_PACKS_URL`). In `EmitComponentPacks`, a pack is
**not archived and not uploaded** when all of these hold: same asset name, same dep version in
the previous and the new manifest, same extracted size (`installed_bytes`). Its entry in the new
index then carries a `url` to the asset in the earlier release; the Updater downloads from that
`url` when present, otherwise from the asset of the installed release as before. A reused entry
keeps its `url` in later releases, so the chain always points at the release that really holds
the file.

- Do not delete an old release whose packs are still referenced by a newer `packs*.json`.
- To publish every pack again (after deleting old releases, or in doubt), run Deploy manually
  with `rebuild_packs`.
- The AppImage step needs the Linux `trt-runtime` pack; when it was reused, the workflow fetches
  it from the `url` in the index.
- Re-running Deploy for a version that is already the latest release does not reuse anything.

**Status on 14 October 2026: exercised by the 3.8.0.23 publication.** Both
published `packs.json` and `packs-linux-x64.json` contain ten entries and all ten
have a `url` pointing to an earlier release (including 3.8.0.9). The release has
15 assets because unchanged component packs are referenced instead of uploaded
again. Preserve those older releases. A fresh physical component installation
was not repeated in this session; publishing the index does not prove that case.
