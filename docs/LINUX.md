# Portage Linux du fork HDR

## Situation actuelle — 3.8.0.29 (14/10/2026 à 20 h 45 (Paris))

La **3.8.0.29 est publiée sur les trois plateformes**, depuis `6fa85bb`.
Les releases Windows/Linux/macOS sont indépendantes et n'ont plus de jobs de
tests. Le code RIFE partagé `30a3e83` est maintenant dépassé et intégré par les
lots suivants : `d639dc1` / `b3f9d5d` ajoutent la chaîne warp et la chronologie
des dessins. La branche NVIDIA CUDA Graph `f4fcd17` reste isolée.

Lire [l'état consolidé courant](archive/2026-10-17/chantiers/ETAT-PROJET.md) et
[le chantier 3.8.0.24–29 / 165 Hz](archive/2026-10-17/chantiers/CHANTIER-RIFE-165HZ.md). Les sections datées
3.8.0.23 ci-dessous restent un historique des preuves de cette session, pas
l'état global actuel. La chaîne warp est livrée dans le moteur partagé ;
**elle ne l'est pas dans NCNN/Vulkan ni dans les binaires Windows amont**.
Les modèles sont conservés, mais cette stratégie et le lissage des dessins
changent le rendu temporel ; l'ancien mode est conservé.

État au 14 octobre 2026 : **3.8.0.23 publiée sur Linux, Windows et macOS**.
Linux fournit portable, AppImage et overlay et reste expérimental, en particulier
pour la validation HDR physique et RTX 4050. La cible initiale est Fedora,
GNOME et Wayland, sur processeur Intel avec RX 6500 ou RTX 4050 mobile.

La release inclut les optimisations exactes NCNN/Vulkan et la préparation CPU du
moteur partagé. La suite RIFE `30a3e83` a passé sa CI, mais n'est pas dans ces
binaires ; la branche NVIDIA `f4fcd17` reste à intégrer. Voir
[l'état courant](archive/2026-10-17/chantiers/ETAT-PROJET.md) et [le relais performances](archive/2026-10-17/chantiers/CHANTIER-PERFORMANCE-RELAIS.md).
Aucun nouveau benchmark local après la consigne d'arrêt de l'utilisateur.

L'extension AnimeJaNai/RIFE AMD et NVIDIA est suivie dans
[`LINUX-INFERENCE.md`](LINUX-INFERENCE.md), actualisé à chaque avancée.

## Architecture et réglages

- `AnimeJaNaiPlatform` détecte les adaptateurs PCI/sysfs et les périphériques
  Vulkan. Le diagnostic distingue l'adaptateur choisi pour l'inférence, le
  périphérique Vulkan et les GPU des connecteurs d'écran actifs. Un portable
  hybride peut rendre sur NVIDIA et afficher via Intel.
- `linux-playback.lua` utilise Vulkan/Wayland, `auto-safe` sur AMD/Intel et NVDEC
  sur NVIDIA, avec le repli logiciel de mpv. Sur une installation neuve, Performance sans RIFE est actif si le backend est disponible. DirectML n'est jamais sélectionné sous Linux.
- Les banques `linux-amd` et `linux-nvidia` sont distinctes de `amd` et `nvidia`.
  L'utilitaire et le Manager partagent le même code .NET de synchronisation :
  empreinte SHA-256, verrou, écritures atomiques et refus des modifications
  concurrentes. L'ancien état `{vendor,hash}` est migré en `{vendor,hash,bank}`.
  Un fichier actif sans état connu est sauvegardé dans `profiles/untracked-*.conf`
  avant la première sélection. Les conflits conservent les deux fichiers.
- Le lanceur crée un répertoire privé et un socket par instance sous
  `$XDG_RUNTIME_DIR` (repli privé dans `/tmp` si absent). Le Manager reçoit
  `ANIMEJANAI_IPC_PATH` et envoie `animejanai-reload-options`. Ctrl+E l'ouvre.
- `linux_hdr_output=auto` suit les préférences Wayland. `sdr` force SDR ; `pq` demande d'abord l'activation manuelle
  HDR dans GNOME sur un écran compatible. Le grading exige une sortie PQ
  négociée et un mpv disposant de `target-colorspace-hint-strict`.
  Les métadonnées HDR du fichier ne prouvent jamais l'état HDR de l'écran.
- Ctrl+G compare le grading personnalisé, naturel et désactivé ; Ctrl+Alt+P
  affiche la mire en PQ ; Ctrl+Alt+H écrit aussi `animejanai/diagnostic-hdr.txt`.
  Cette dernière distingue demande, négociation et validation physique restante.
- `hdr_backend=auto` et `vsr=auto` utilisent mpv. RTX Video natif, AMF et changement
  automatique de fréquence restent des fonctions Windows. Les demandes
  incompatibles sont signalées et utilisent le rendu mpv.

Sur NVIDIA, la banque de départ utilise TensorRT : Ctrl+1 « Balanced · 1080p → 2160p » (profil de
démarrage), Ctrl+2 « Performance · 1080p → 2160p + RIFE ×2 », Ctrl+3 « Performance · 720p → 1440p »,
Ctrl+4 la même avec RIFE ×2, Ctrl+5 « RIFE ×2 · source resolution » ; RIFE 4.26 Quality jusqu'à 31 i/s,
upscale seul au-delà. Au premier lancement, le lanceur télécharge TensorRT, ses noyaux et les modèles RIFE
ONNX dont ces profils ont besoin. Sur AMD, la banque utilise NCNN/Vulkan : Ctrl+1 active AnimeJaNai
Performance en 360p vers 720p, Ctrl+2 ajoute RIFE 4.6 ×2, Ctrl+3 active RIFE seul à la résolution source,
Ctrl+4 traite en 720p vers 1440p, Ctrl+5 propose une base plus légère 240p vers 480p, Ctrl+6 combine une
base 180p vers 360p et RIFE ×2. Ctrl+0 revient à la lecture normale. Le Manager change de moteur avec les
profils (contrat des profils, §5 bis) et propose « Add recommended profiles » pour le moteur choisi ; les
réglages existants sont préservés.
Pour Vulkan, les modèles SPAN Performance/Balanced Standard/Sharp sont convertis depuis les
poids ONNX fournis ; aucune substitution de modèle n'est faite. Les sources SDR
à dimensions paires sont acceptées ; modèles temporels, SD Compact et sources
PQ/HLG ne sont pas pris en charge par ce premier pont RGB24. Le calcul tourne
sur le GPU Vulkan explicitement choisi, avec décodage logiciel et transferts
CPU/GPU. Le débit dépend du profil et du GPU ; aucun temps réel 4K/RIFE n'est promis.

TensorRT reste une option **NVIDIA seulement**, ABI aji 9, nécessitant `libaji.so`,
`libaji_trt.so`, TensorRT 11.3, `trtexec`, les ONNX RIFE et les kernels appropriés.
Le choix Vulkan du Manager fonctionne sans ces composants. RIFE Vulkan 4.6 et
RIFE TensorRT 4.26 sont des modèles distincts. Une configuration TensorRT
exemple est fournie dans `native/linux-vulkan/linux-nvidia-tensorrt.conf`.
Une erreur d'initialisation coupe l'inférence pour la session ; rouvrir la vidéo
permet la lecture normale. Les anciennes banques personnalisées sont préservées :
pour un essai immédiat, extraire le nouveau paquet dans un dossier neuf.

## Construire le paquet SDR de test

Prévoir .NET 10, LuaJIT, Git, zstd, puis un checkout du Manager
`Ta2b/AnimeJaNaiManager-HDR`, branche `hdr-settings-0.8`, à côté de ce dépôt.
Les changements sont publiés dans le dépôt du Manager. `manager-source-ref.txt`
fixe le commit utilisé en CI ; aucun patch n’est rejoué.

Le bundle mpv amont `2026-10-09-19c0fcf` omet Wayland. L'assembleur le refuse.
Construire la version native avec Wayland obligatoire :

```sh
# Sur Ubuntu 24.04, également utilisable dans un conteneur rootless depuis Fedora :
sudo apt-get install build-essential git cmake python3-venv meson ninja-build pkg-config nasm \
  libass-dev libvulkan-dev libxkbcommon-dev libwayland-dev libxml2-dev libffi-dev \
  libexpat1-dev liblua5.2-dev liblcms2-dev libx11-dev libxrandr-dev libxss-dev \
  libxcursor-dev libxi-dev libxpresent-dev libxinerama-dev libpulse-dev libasound2-dev \
  libshaderc-dev spirv-cross libspirv-cross-c-shared-dev glslang-dev libfreetype-dev \
  libfontconfig-dev libfribidi-dev libharfbuzz-dev libunibreak-dev autoconf automake libtool
installer/linux/build-native.sh /chemin/build-natif /chemin/bundle-natif
MPV_LINUX_LOCAL=/chemin/bundle-natif tools/build-linux-test.sh
```

Le build natif conserve le commit mpv de Windows, compile FFmpeg, libplacebo,
libass et les protocoles nécessaires. Il inclut `$PREFIX/share/pkgconfig` :
omettre ce chemin masquait les protocoles Wayland. Les bibliothèques du pilote
et les bibliothèques Wayland du système ne sont pas embarquées : une ancienne
`libwayland-client` peut empêcher le chargement des pilotes Mesa récents.
Le système cible doit fournir Wayland **1.23 ou plus** et Vulkan ; la base de
compilation est Ubuntu 24.04, glibc 2.39.

Le résultat est dans `artifacts/linux-test/`, avec un `tar.zst` et une arborescence
portable. `--sdr-only` évite les téléchargements NVIDIA/RIFE ; il est réservé aux
paquets Linux de test et ne produit pas de packs d'inférence. `AJ_DOTNET`,
`AJ_MANAGER_SOURCE` et `AJ_LINUX_OUTPUT` personnalisent les outils et sorties.
Extraire dans un dossier neuf puis lancer `./mpv-animejanai fichier.mkv`.

Pour construire le paquet avec **AnimeJaNai et RIFE Vulkan** :

```sh
python3 -m venv /chemin/python-modeles
/chemin/python-modeles/bin/pip install onnx==1.23.2 numpy==2.5.4
AJ_PYTHON=/chemin/python-modeles/bin/python bash installer/linux/build-inference.sh \
  /chemin/build-vulkan /chemin/bundle-vulkan \
  BuildMpvUpscale2xAnimeJaNai/mpv-upscale-2x_animejanai/animejanai/onnx
MPV_LINUX_LOCAL=/chemin/bundle-natif VULKAN_LOCAL=/chemin/bundle-vulkan \
  tools/build-linux-test.sh 3.8.0.8-linux-test.2
```

La conversion exige Python uniquement pendant la construction. Le lecteur
embarque NCNN et les modèles RIFE et ne nécessite ni Python ni CUDA pour Vulkan.
Le backend natif vise Ubuntu 24.04 ou plus récent (compilation dans cette base
pour la compatibilité Fedora). Avec `VULKAN_LOCAL`, le script assemble avec
`--vulkan-only`, sans télécharger TensorRT. Le build natif installe le nouveau
filtre Linux sans modifier les filtres Windows.

Pour un paquet complet : publier le helper dans `publish/platform-linux-x64`,
le Manager dans `MANAGER_HDR_LOCAL`, définir `MPV_LINUX_LOCAL` et `VULKAN_LOCAL`, puis lancer
l'assembleur avec `--target linux-x64 --packs`. TensorRT et RIFE sont alors des
composants optionnels du Manager. Les binaires et bibliothèques natives du
Manager, le helper, le lanceur et les banques manquantes figurent dans l'overlay.

## Paquets, mises à jour et releases

**Benchmark de lecture sous Linux (3.8.0.19).** *Run Benchmarks* du Manager lance la même série que
sous Windows : gabarits Balanced (1010) et Performance (1011) sur les cinq clips fournis, hors
écran, résultat dans `animejanai/benchmark.txt` au format que *Submit Benchmark* lit. Il demande le
moteur TensorRT (NVIDIA). Le Manager affiche la progression dans une fenêtre ; la fermer arrête la
mesure. L'AppImage relie `animejanai/benchmarks` de l'image dans le dossier de données à chaque
lancement, et l'outil prend le lecteur de l'image (`ANIMEJANAI_MPV`). Deux défauts corrigés dans
`AnimeJaNaiBenchmark` : il mesurait pendant la construction d'un moteur, quand le filtre laisse
passer les images telles quelles (615 i/s affichés en 720p, soit le décodage seul) ; et la sortie
du lecteur, jamais lue, remplissait son tube et le bloquait pendant la construction. Mesuré sur
RTX 4070 Ti, lecteur ouvert à côté : Performance 720p 237 i/s, Balanced 720p 129 i/s.

**Intégration au bureau (AppImage, depuis la 3.8.0.17).** Lancée sans fichier, l'AppImage ouvre la
fenêtre du lecteur et attend un fichier (glisser-déposer). À chaque lancement normal, elle
enregistre son entrée de menu et ses associations vidéo (`mpv-animejanai-hdr.desktop`), et les
repointe si le fichier a été déplacé, renommé ou remplacé par une version plus récente : « Ouvrir
avec » fonctionne sans passer par le terminal. Elle ne devient jamais le lecteur par défaut d'elle-même :
ce choix se fait dans le bureau, ou par `--install --default`. `--uninstall` retire l'entrée et
arrête cet enregistrement automatique ; `--install` le rétablit. L'archive portable garde `install.sh`.

`installer/linux/package-tarball.sh` produit le portable ;
`installer/linux/build-appimage.sh` produit ensuite l'AppImage.
L'AppImage utilise `$XDG_DATA_HOME/AnimeJaNai-HDR-linux`, séparé du projet amont.
Elle actualise scripts, shaders et outils HDR à chaque lancement et conserve
banques, réglages, moteurs et fichiers utilisateur. Les téléchargements pointent
vers `Ta2b/mpv-AnimeJaNai-HDR`. Le Manager et l'updater utilisent le même
répertoire modifiable pour installer les composants ; l'AppImage actualise le
manifeste et la version et relie `7zz`. `ANIMEJANAI_OFFLINE=1` désactive ses téléchargements
automatiques de composants ; le profil par défaut ne les déclenche pas. Un composant inchangé
depuis une release antérieure est pris à l'adresse que donne `packs-linux-x64.json`.

**Mise à jour de l'AppImage (depuis la 3.8.0.21).** Le lecteur annonce une nouvelle version au
démarrage ; Ctrl+U vérifie de nouveau puis lance `AnimeJaNaiUpdater --apply`. L'updater
télécharge l'AppImage de la release à côté de l'ancienne pendant que la vidéo continue, la
contrôle (`SHA256SUMS`, en-tête ELF), attend la fermeture du lecteur, met le nouveau fichier
à la place de l'ancien (sous le nom de la nouvelle version quand l'ancien nom portait la
sienne) et relance le lecteur sur le même fichier. Le dossier de données n'est pas touché.
L'AppImage doit être dans un dossier où l'on peut écrire. Les versions jusqu'à la 3.8.0.20
n'ont pas cette mise à jour : la 3.8.0.21 se télécharge une dernière fois à la main.

Sur toutes les plateformes, l'updater lit les releases sur les pages de GitHub
(`releases/latest`, `releases/expanded_assets/TAG`) et non par son API, limitée à soixante
requêtes anonymes par heure et par adresse internet ; l'API reste la seconde voie.

Les noms d’assets Windows sont conservés. Les contrôles et compilations Windows
et Linux sont indépendants. Par défaut `Deploy` construit les deux plateformes
sur un push `release`, puis un job commun joint leurs assets à **la même release**.
Une plateforme demandée en échec bloque cette publication commune. Linux est
identifié comme expérimental dans les notes, avec les limites de validation
physique NVIDIA/HDR. `platform=windows|linux` permet un build ciblé sans retirer
les assets déjà publiés de l’autre plateforme. Voir [RELEASE.md](RELEASE.md).
Le Manager publie également les deux plateformes dans **un seul job**.

Les builds réutilisent le lecteur natif et le backend Vulkan compilés. Les
modèles SPAN d’origine sont déjà dans le dépôt. Le cache d’archives de
l’assembleur (`ANIMEJANAI_DOWNLOAD_CACHE`) évite également de retélécharger les
composants versionnés, dont RIFE et TensorRT, lorsqu’ils n’ont pas changé.
Les fichiers sont contrôlés à la réutilisation ; les liens `latest` restent
actualisés. Voir [les détails du cache](RELEASE.md#cache-des-téléchargements-du-build-linux).

## Validation à conserver

```sh
tests/hdr/run.sh luajit
dotnet run --project tests/platform/PlatformTests.csproj
dotnet run --project tests/download-cache/DownloadCacheTests.csproj
dotnet run --project ../AnimeJaNaiManager-HDR/tests/ProfileRoundTrip
python3 tests/updater-regressions/generate.py artifacts/updater-checks
dotnet run --project artifacts/updater-checks
python3 tests/hdr/shader_check.py
python3 tests/platform/package_check.py
# Avec le paquet construit et un GPU Vulkan disponible :
python tests/inference/model_parity.py /chemin/bundle-vulkan BuildMpvUpscale2xAnimeJaNai/mpv-upscale-2x_animejanai/animejanai/onnx --device "nom exact Vulkan" --report artifacts/parity.json
python3 tests/inference/pts_check.py /chemin/paquet --device "nom exact Vulkan" --report artifacts/cadence.json
```

Les 161 tests Lua Windows sont conservés ; les tests Linux couvrent les branches
sans Windows, les GPU hybrides, l'absence de TensorRT et la négociation HDR.
Les tests .NET couvrent migration et conflits de banques, refus de DirectML,
socket Unix, conservation des commentaires, sauvegarde/relecture et mise à jour
des banques. La suite des shaders calcule ses résultats sur un tampon PQ forcé :
elle vérifie le shader, **pas le HDR physique de l'écran**. Sur une session locale,
`AJ_NO_XVFB=1 AJ_GPU_CONTEXT=waylandvk AJ_VULKAN_DEVICE='nom exact'` permet d'utiliser
le vrai GPU ; la CI utilise Xvfb/lavapipe.

Sur la session Wayland locale, le test d'exécution crée une copie temporaire du
paquet et ouvre le Manager par le raccourci de mpv :

```sh
dotnet build ../AnimeJaNaiManager-HDR/tests/ProfileRoundTrip
python3 tests/platform/runtime_check.py /chemin/arborescence-portable \
  --report artifacts/linux-runtime.json \
  --manager-writer ../AnimeJaNaiManager-HDR/tests/ProfileRoundTrip/bin/Debug/net10.0/ProfileRoundTrip.dll
# Ajouter --appimage /chemin/paquet.AppImage pour tester l'AppImage avec des données isolées.
```

L'option `--manager-writer` utilise la classe de sauvegarde du Manager pour
vérifier le rechargement effectif par socket et les commentaires. Elle alterne
PQ et SDR dans la copie temporaire ; le système et les réglages d'origine
restent inchangés.

Pour chaque paquet, extraire une installation neuve et une seconde copie dédiée
aux mises à jour. Vérifier Ctrl+E, modification/sauvegarde, rechargement live,
commentaires, profils et fonctionnement hors ligne. Sur RTX 4050, mesurer la
construction puis la réutilisation du moteur, les images perdues et la mémoire
GPU avec `nvidia-smi`, d'abord sans RIFE puis avec ×2, pendant au moins un épisode.
Sur les deux PC, le HDR physique demande un écran compatible, GNOME HDR activé,
comparaison SDR/HDR natif, grading, mire, sous-titres et retour SDR.

## État de la validation locale (paquet précédent)

Validation du paquet `3.8.0.8-linux-test.2` sur Fedora / GNOME / Wayland :

| Vérification | Résultat |
| --- | --- |
| LuaJIT | 161 tests existants + 53 tests Linux réussis |
| Transactions de banques .NET | 14 cas réussis, dont concurrence et migration |
| Manager HDR | 9 cas réussis ; patch appliqué et testé depuis une copie propre |
| Mises à jour | 14 cas réussis ; fixtures de verrouillage Windows ignorées sous Linux |
| AppRun hors ligne | 23 cas réussis, préservation des réglages et moteurs |
| Shaders libplacebo | Réussite sur Vulkan AMD, dont le contexte Wayland natif |
| Portable et AppImage | Lecture des cinq clips fournis, Ctrl+E, sauvegarde/rechargement IPC, diagnostic et nettoyage du socket |
| Compilations | Helper, updater et Manager compilés pour Linux et Windows ; exécution Windows à tester sur Windows |
| AnimeJaNai/RIFE Vulkan AMD | Portable et AppImage : profils 1, 2, 3, 5, 6, recherche et changement de résolution réussis |
| Fidélité SPAN | Quatre modèles, deux tailles chacun, comparaison ONNX Runtime réussie |
| Cadence RIFE | 2× et 1,5× : horodatages, nombre d’images et fin de fichier réussis |
| NVIDIA Vulkan / TensorRT | Code et chemins disponibles ; RTX 4050 non accessible pour un essai physique |
| HDR physique | Non validé : négociation PQ et shaders ne suffisent pas à certifier le rendu de l'écran |

Le rendu local utilise la RX 6500 ; les connecteurs actifs sont rattachés à Intel.
Le décodage observé est logiciel. Ces essais valident le fonctionnement et la
stabilité dans cette session, **pas les performances** : RX 6500 modeste et
stream Twitch 1080p en arrière-plan, selon la précision de l'utilisateur.
Les images perdues, latences et relevés mémoire sont des observations sous
charge concurrente. Ils ne donnent ni limite intrinsèque du GPU, ni débit
isolé, ni comparaison Windows/Linux. La mémoire est celle de tout le GPU,
pas du seul processus. Voir les conditions et rapports dans `LINUX-INFERENCE.md`.

## Simplification du Manager

La page commune et les nouveaux défauts sont décrits dans [SETTINGS.md](SETTINGS.md).
Les volets avancés sont repliés. Une seule description d’écran sert à tous les GPU.
Les anciennes clés restent lisibles ; les défauts Performance/Natural ne réinitialisent
pas une installation personnalisée. `linux_hdr_output=auto` ne certifie pas le HDR physique.

## Compatibilité du client Wayland

Le mpv épinglé utilise deux créations de files avec un nom de diagnostic,
introduites dans Wayland 1.23. Le constructeur Linux utilise l’API de file sans
nom, identique pour la distribution des événements, afin que le binaire fonctionne
aussi avec le client Wayland 1.22 d’Ubuntu 24.04. Les protocoles colorimétriques
et les règles de confirmation HDR restent les mêmes. Les bibliothèques Wayland
proviennent du système. La vérification du bundle s’exécute hors du préfixe de
compilation, avant sa mise en cache, et les dépendances du rendu gardent l’ABI 9
TensorRT / ABI 1 Vulkan.
