# Reprise du travail — 12 octobre 2026

## Mise à jour du 12 octobre, 20 h (heure de Paris) : 3.8.0.9 publiée

**La release 3.8.0.9 est publiée avec Windows et Linux**
([Deploy 38285035504](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/actions/runs/38285035504), commit `8fbdc88`).
Les 31 assets attendus sont présents : Setup et archive Windows, portable `tar.zst` et AppImage
Linux, deux overlays, `manifest.json` / `manifest-linux-x64.json`, `packs.json` /
`packs-linux-x64.json`, les composants des deux plateformes et `SHA256SUMS`. Les sections
« Objectif restant », « Builds à suivre » et « Actions de reprise » ci-dessous décrivent l'état
antérieur ; elles sont conservées pour l'historique.

- **Cause de l'échec AppImage.** L'image Ubuntu 24.04 hébergée n'a pas ImageMagick :
  `build-appimage.sh` retombait sur un PNG écrit à la main dont le flux zlib est invalide, et
  linuxdeploy le rejetait (« IDAT: incorrect data check »). Une vraie icône 256x256 est
  maintenant suivie (`installer/linux/animejanai.png`) et le script échoue clairement si elle
  manque. La correction précédente du chemin de `7zz` était juste mais ne traitait pas ce point.
- **Durée du Deploy.** Les builds démarrent en parallèle des tests (seule la publication les
  attend), Windows réutilise le cache de téléchargements, les archives passent au niveau 5 sur
  tous les cœurs, les artefacts sont envoyés sans recompression, Inno Setup n'est installé que
  s'il manque. Build Windows : 14,9 min → 10,9 min, caches encore vides. Durée totale de ce
  run : 19 min, dont assembleur Linux 8,6 min (cache vide) et publication 4,5 min.
  Ce qui reste coûteux : l'assembleur retélécharge et recompresse environ 5 Go de composants
  TensorRT et RIFE à chaque version, et la publication les renvoie, alors qu'ils ne changent
  qu'avec les versions fixées dans `Program.cs`.
- **Vérifié sous Windows** (RTX 4070 Ti, installation réelle avec des réglages antérieurs) :
  l'overlay 3.8.0.9 conserve le pic 1000 nits, OLED, Display P3, le profil par défaut 4 et la
  banque (empreinte inchangée) ; `AnimeJaNaiPlatform.exe --activate-bank` n'est appelé qu'au
  premier démarrage ; lecture correcte en Direct3D 11 et en Vulkan ; le Manager HDR démarre et
  ne modifie pas le fichier de réglages à l'ouverture. Non vérifié : l'interface du Manager
  elle-même (aucun clic), et toute la partie Linux, qui ne peut pas tourner sur ce poste.
- **Corrigé après la release (sur `hdr-3.8`, pour la version suivante)** : le profil 9, profil
  de démarrage des installations neuves, n'était pas sélectionnable au clavier sous Windows
  (`animejanai-select` refusait les numéros au-delà de 4 et `Ctrl+9` était sur `ignore`).
- **Reprise des composants inchangés (écrite, compilée, pas encore exercée).** Deploy récupère
  l'index des packs de la release précédente ; un pack dont la version de dépendance et la taille
  extraite n'ont pas changé n'est ni recompressé ni renvoyé, et son entrée de `packs*.json` porte
  une `url` vers la release qui le contient. L'Updater suit cette `url`. Détail et précautions
  dans `RELEASE.md`. **La prochaine release est son premier essai réel** : vérifier le journal
  de l'assembleur, les `url` de l'index, et l'installation d'un composant sur une installation
  neuve. En cas de doute, relancer Deploy avec `rebuild_packs`.
- **Un seul aspect HDR (sur `hdr-3.8`, pour la version suivante).** `rtx_contrast`,
  `rtx_saturation` et `rtx_middle_gray` pilotent RTX Video HDR et la conversion mpv ;
  `mpv_truehdr_look=yes` par défaut ; Manager `4aad542` épinglé. Lois mesurées sur TrueHDR,
  détail dans `PARTAGE.md`. Vérifié sous Windows dans le lecteur (PSNR 29 à 44 dB entre les deux
  conversions sur quatre réglages). **Non vérifié sous Linux** : la conversion mpv y passe par
  `linux-hdr.lua`, à contrôler avec une sortie PQ réelle.
- **Portage du backend NCNN/Vulkan sous Windows : étudié et abandonné.** Mesure du calcul pur,
  sans aucune copie, sur RTX 4070 Ti : 28 ms par image en Performance 720p, soit environ 6 fois
  plus lent que TensorRT sur la même carte et que DirectML sur une carte comparable. Une réécriture
  sans copie ne comblerait pas cet écart. Détail et outil de mesure dans `LINUX-INFERENCE.md`.
- **Moteur ONNX Runtime (MIGraphX / OpenVINO) : branché, non validé sur matériel.**
  `native/linux-ort`, même interface que le moteur Vulkan ; reconnu par `linux-playback.lua` et
  proposé dans le Manager sous Linux. Validé sur le fournisseur CPU ; **jamais exécuté sur
  MIGraphX ni OpenVINO** (essais prévus par l'utilisateur). Pas de RIFE dans ce moteur.
  TrueHDR sous Linux : impossible avec le SDK RTX Video disponible (Windows seulement).
  Mode d'essai et limites dans `LINUX-INFERENCE.md`.
- **Mode Vulkan Windows : il existe déjà.** Depuis la 3.8.0.5, `render_api=vulkan` fait
  tourner RTX VSR et TrueHDR dans le moteur TensorRT (`aji_trt_rtx.dll`, compilé localement,
  voir `PARTAGE.md`). La phrase « le moteur Vulkan Windows est reporté » plus bas vise
  uniquement un portage du backend NCNN/Vulkan de Linux vers Windows.

État vérifié à **17 h 38, heure de Paris (15 h 38 UTC)**. Les builds ci-dessous
peuvent terminer après cet instant : consulter leurs résultats avant toute relance.
Le travail s’arrête ici à la demande de l’utilisateur pour préserver son quota.

## Objectif restant

Terminer et vérifier la publication **3.8.0.9 avec Windows et Linux dans la
même release GitHub**, puis documenter son résultat. Les sources sont poussées ;
**la release du lecteur n’est pas encore publiée à cet instant** : l’API du tag
`3.8.0.9` répond 404. Ne pas annoncer la publication comme acquise.

## Dépôts et commits

| Dépôt | Branche | Dernier état poussé avant ce document |
|---|---|---|
| `Ta2b/mpv-AnimeJaNai-HDR` | `hdr-3.8` | `797f690`, cache des téléchargements et exclusion des sorties de tests |
| Même dépôt | `release` | `28a7098`, correction du chemin de 7-Zip pour AppImage/overlay |
| `Ta2b/AnimeJaNaiManager-HDR` | `hdr-settings-0.8` | `d25a510c43da4278199c95b5f7e9917ab8d92c82` |

Le dépôt principal est `/goinfre/hcombaud/mpv-AnimeJaNai-HDR`. Le Manager est
dans `/goinfre/hcombaud/AnimeJaNaiManager-HDR`. `manager-source-ref.txt` fixe
`d25a510…` ; le Manager fixe le lecteur à
`94b657159728af44599c5d4da57d2ddd5b1156f1` pour le service partagé de banques.
Ce service n’a pas changé depuis cette référence. Aucune mise à jour du Manager
n’est nécessaire pour les dernières corrections du packaging.

Les commits postérieurs à `28a7098` ajoutent le cache de l’assembleur, ses tests
et la documentation. **Ils ne sont pas dans le workflow de release déjà lancé**.
Ils sont prévus pour les prochains builds ; ne pas interrompre le build actuel
uniquement pour les inclure. L’arborescence de travail n’a aucune modification
de code en attente. `.vscode/` est un dossier utilisateur non suivi, à conserver.

## Builds à suivre d’abord

- [Deploy 38270855225](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/actions/runs/38270855225),
  commit `28a7098` : préparation, tests HDR, Vulkan et contrôles Manager/plateforme
  Windows/Linux **réussis**. Le build Linux assemble les composants ; le build
  Windows exécute l’assembleur. Les deux sont encore en cours.
- [Platform checks 38271496602](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/actions/runs/38271496602),
  commit `797f690` : contrôles Windows/Linux et fidélité Vulkan **en cours**.
  Cette matrice inclut les dix nouveaux contrôles du cache de téléchargement.
- Le Manager est déjà publié sur les deux plateformes :
  [release hdr-d25a510…](https://github.com/Ta2b/AnimeJaNaiManager-HDR/releases/tag/hdr-d25a510c43da4278199c95b5f7e9917ab8d92c82).
  Assets vérifiés : `AnimeJaNaiManager-HDR.exe`, `AnimeJaNaiManager-HDR-x64.zip`,
  `AnimeJaNaiManager-HDR-linux-x64.tar.zst`. Son build `38261074218` a réussi.

## Corrections déjà effectuées : ne pas repartir de zéro

- `611c486` : mpv utilisait `wl_display_create_queue_with_name`, absente du
  client Wayland 1.22 d’Ubuntu 24.04. Le patch Linux idempotent utilise les files
  sans nom, sans changer les protocoles HDR. Démarrage et filtre validés dans
  Ubuntu 24.04 **sans préfixe de compilation** ; validation GitHub réussie et
  cache natif enregistré dans le précédent Deploy `38267839276`.
- Ce précédent Deploy a aussi **réussi le build Windows et le portable Linux**,
  puis échoué à l’étape AppImage avec le code 127. Le workflow exposait
  `publish/` dans PATH, mais `7zz` est dans le sous-dossier versionné du lecteur.
  `28a7098` utilise le chemin explicite de ce binaire pour l’AppImage et l’overlay.
  Les erreurs AppImage sont maintenant remontées dans les annotations publiques.
  C’est la correction que la relance actuelle doit confirmer.
- Le paquet Manager local ne copie que son exécutable et ses bibliothèques
  natives : copier tout `dotnet publish` ajoutait une configuration standalone
  qui changeait le choix de son répertoire de données.
- Les assets sont aplatis avant publication pour éviter l’envoi de dossiers.
  Le job de publication seul est sérialisé ; il attend toutes les plateformes
  demandées. Les assets Windows gardent leurs noms ; Linux porte `linux-x64`.
- Les SDK inutiles du runner Linux sont supprimés pour libérer l’espace.
  Le cache natif est enregistré avant l’assemblage, même si le packaging échoue.

Le cache d’archives ajouté dans `e2ebd11` utilise `ANIMEJANAI_DOWNLOAD_CACHE` :
clé par URL, empreinte vérifiée à la réutilisation, téléchargements incomplets
non enregistrés, liens `latest` exclus. Les vérifications NVIDIA fixées dans
les sources restent appliquées. Les ONNX SPAN sont déjà versionnés et le bundle
NCNN/Vulkan converti est déjà caché. Dix tests locaux et la compilation de
l’assembleur passent. Le résultat Windows/Linux des nouveaux tests reste à lire.
`797f690` retire du suivi les `bin/` et `obj/` accidentellement inclus avec ces
tests et étend leurs exclusions ; aucune sortie générée ne reste dans HEAD.

## Validation disponible et limites

Les contrôles locaux antérieurs passent : **239 assertions Lua** (dont les
161 initiales), 14 banques, 14 updater, 23 cas hors ligne, 13 persistance Manager,
13 interface et les shaders dans libplacebo. Le portable et l’AppImage locaux
3.8.0.9 ont été testés en lecture Wayland sur AMD RX 6500 : ouverture du Manager,
IPC privé, sauvegarde/rechargement avec commentaires, profils SPAN/RIFE,
recherche et changements de résolution. Les quatre SPAN ont été comparés à
leurs ONNX. Ces paquets locaux précèdent la dernière correction Wayland.

**Aucun benchmark de performance** : GPU faible et Twitch 1080p en arrière-plan,
charge non contrôlée. RTX 4050/TensorRT et écran HDR physique restent à valider.
Linux demeure expérimental dans les notes de la release commune.

Les choix utilisateur sont acquis : Performance sans RIFE au premier démarrage,
conversion SDR→HDR quand la sortie HDR est disponible, grading Natural actif
en HDR, luminosité/gamut automatiques, OLED désactivé, section écran commune.
Préserver les réglages existants. Le portage du backend NCNN/Vulkan de Linux vers
Windows est **reporté à plus tard** ; ne pas l’ajouter ou modifier les choix DirectML maintenant.
(Le mode `render_api=vulkan` de Windows, avec TensorRT et RTX Video, est distinct et existe déjà.)

## Actions de reprise

1. Consulter les deux runs ci-dessus. En cas d’échec, lire l’étape et les
   annotations ; corriger seulement l’erreur constatée et documenter la correction.
2. Si Deploy réussit, vérifier [la release 3.8.0.9](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/releases/tag/3.8.0.9) :
   Setup et archive Windows, portable `tar.zst` et AppImage Linux, deux overlays,
   `manifest.json`/`manifest-linux-x64.json`, `packs.json`/`packs-linux-x64.json`,
   composants optionnels des deux plateformes et `SHA256SUMS`.
   Contrôler versions, noms et assets réellement présents avant d’annoncer le succès.
3. Confirmer les nouveaux contrôles de cache sur Windows/Linux. Enregistrer
   les liens et résultats finaux dans `RELEASE.md` et actualiser ce document.
   Pousser les documents sur `hdr-3.8`, sans relancer un Deploy réussi.
4. Si une correction de build est indispensable, pousser le commit sur
   `hdr-3.8`, puis `git push origin HEAD:release`. Aucun push forcé.

L’accès SSH GitHub fonctionne comme **Ta2b**. `gh` est installé mais non
authentifié ; aucun token GitHub n’est configuré et le connecteur GitHub n’est
pas connecté. Les lectures REST publiques fonctionnent, les logs complets des
jobs demandent une authentification. Lire les erreurs publiques via
`/actions/runs/<id>/jobs`, puis `check_run_url + '/annotations'`.
La publication autorisée passe par le workflow et son `GITHUB_TOKEN`.

## Outils et preuves locales

- .NET : `/goinfre/hcombaud/.animejanai-tools/dotnet/dotnet`.
- Actionlint : `/goinfre/hcombaud/.animejanai-tools/bin/actionlint`.
- `.animejanai-tools` utiles sont dans **`/goinfre/hcombaud/`**, pas dans le dépôt.
- Containers Podman Ubuntu 24.04 disponibles ; image native
  `localhost/animejanai-native-dev:24.04`, montage des outils en `/work`.
  Les arbres Meson natifs utilisent ces chemins de container : ne pas lancer
  leur Ninja directement sur l’hôte.
- Paquets et Manager locaux : `artifacts/linux-release/`.
- Preuves : `artifacts/workflow-*.log`, `workflow-linux-runtime.json`,
  `workflow-appimage-runtime.json`, `workflow-wayland-host-validation.log`,
  `workflow-download-cache-tests.log` et `reprise-ci-state.json`.
  `artifacts/` est ignoré, conservé localement. Les rapports runtime n’ont pas de
  clé générale `passed` ; vérifier leurs contrôles et le code de sortie.
- `artifacts/watch-release.py` suit Deploy `38270855225` par l’API publique.
  Respecter sa limite de requêtes ; un suivi par minute suffit.
- Un essai local du packaging complet a échoué parce que Fedora n’avait pas
  `dpkg-deb`. Cela ne concerne pas le runner Ubuntu. L’archive NVIDIA déjà
  téléchargée est dans `artifacts/nvidia-packages/` : ne pas la retélécharger.

Pour le détail pérenne, lire [RELEASE.md](RELEASE.md), [LINUX.md](LINUX.md),
[LINUX-INFERENCE.md](LINUX-INFERENCE.md), [SETTINGS.md](SETTINGS.md) et
[DEVELOPMENT.md](DEVELOPMENT.md), ainsi que les documents du Manager.
