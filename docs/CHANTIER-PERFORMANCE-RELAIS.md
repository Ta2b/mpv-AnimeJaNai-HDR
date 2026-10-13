# Chantier performances — document de relais

## État à lire en premier — reprise du 13 octobre 2026

**Lot 2 en cours : conserver sur GPU les entrées préparées de RIFE 4.6.**
Empreintes du checkpoint du lot 1 contrôlées avant modification : toutes
conformes. Sources et binaire mesuré copiés dans `artifacts/performance/phase-1/`.
La référence initiale et `phase-1.patch` restent intacts. Construction complète
terminée. Validation exacte contre l'ancienne bibliothèque : **18 scénarios,
657 images par mode, quatre modes**, tous identiques octet pour octet. Rapport
`rife-gpu-cache-parity.json`, `passed=true`. Benchmark 720p isolé contre le lot 1
terminé ; un contrôle du cache GPU activé/désactivé dans le même binaire est
**en cours** pour isoler l'effet du lot 2. Pas de modification des shaders,
poids, précision ou arrondis. Validation mpv à effectuer ensuite.
Sources et binaire du lot 2 préservés dans `artifacts/performance/phase-2/`.
**Lot 3 débuté : conserver les RGB24 préparés par source, au lieu de les
recalculer deux fois à chaque nouvelle paire.** Pas encore construit ni validé.

### Lot 1 terminé

Le premier lot NCNN/Vulkan est implémenté et validé sur RTX 4070 Ti ; il reste
local, sans commit/push/release ni remplacement de l'installation utilisateur.
Les modèles, leur précision, les résolutions et les seuils restent inchangés.

- Cache exact des sources et extrémités ; préparation RIFE par paire ; reprise
  des sorties RGB24 répétées ; réutilisation de l'extrémité déjà calculée sur
  une coupe détectée avec la règle existante.
- Validation finale : **14 scénarios, 483 images par mode**, ancienne
  bibliothèque / candidat sans cache / candidat avec cache, sorties identiques
  octet pour octet. `cache-parity-final.log/json`.
- Benchmark final 720p : 24 paires, 5 essais alternés, warm-up exclu ; résultats
  dans `cache-v2-benchmark-720p.log/json` (table ci-dessous). Aucun autre test
  GPU simultané, bureau actif.
- PTS/EOF dans mpv : PASS, facteurs 2 et 3/2. Comparaison vidéo complète sur
  un motif **en mouvement** 720p : **PASS**, 45 images après SPAN ×4 et 23
  avant SPAN ×2, RGB décodés et PTS identiques. `playback-golden.log/json`.
- L'essai de fusion NCNN conserve pixels/poids testés mais ne démontre pas de
  gain : **non activé**, uniquement dans les artefacts expérimentaux.
- CI ajoutée mais non exécutée à distance. Windows/macOS et autres GPU non
  testés par ce lot ; aucun changement dans leurs moteurs pour l'instant.

| Cas 1280×720 | Référence, médiane par intervalle | Candidat | Accélération médiane appariée |
|---|---:|---:|---:|
| SPAN seul, sources toutes différentes | 40,54 ms | 40,46 ms | ×0,999 (neutre) |
| SPAN seul, sources identiques | 40,12 ms | 2,65 ms | ×15,12 |
| RIFE après SPAN ×4 | 453,84 ms | 212,69 ms | ×2,118 |
| RIFE avant SPAN ×4 | 216,52 ms | 196,55 ms | ×1,101 |

Un intervalle ×4 produit quatre images de sortie. Ces mesures ne sont pas des
FPS d'affichage ni une validation du temps réel. Sur sources nouvelles, les
essais appariés varient de ×0,921 à ×1,024 : aucun gain prouvé dans ce cas et
le coût du cache doit encore être travaillé. Sur RIFE après SPAN, ×2,097–2,141.

Référence SHA256 : consulter `cache-parity-final.json`. Candidat mesuré SHA256 :
`94c2cf029a4ff3d036c3237be883b777d3a6930b16c3001c48a39bc56d86cb4e`.
Cette empreinte identifie le candidat du lot 1, désormais conservé dans
`phase-1/libaji_vulkan.so`. La source courante inclut les adaptations du lot 2.

**Les builds et tests du lot 1 sont terminés.** Arbre de travail non commité :
`native/linux-vulkan/aji_vulkan.cpp`, `aji_vulkan.h`, workflow
`.github/workflows/linux-port.yml`, lien de reprise dans `docs/REPRISE.md`,
nouveaux `tests/inference/vulkan_cache.py` et présent document. Le rapport
`docs/OPTIMISATIONS-MOTEURS.md` précède ce chantier et reste également non suivi.
Les binaires et preuves sont uniquement sous `artifacts/performance/`.
Un patch complet (fichiers suivis et nouveaux fichiers inclus) est conservé
dans `artifacts/performance/phase-1.patch`, avec les empreintes des sources et
du binaire dans `checkpoint-manifest.json`. À régénérer après toute modification.

## Mandat utilisateur et règles de qualité

Commencer les optimisations de performance en conservant les modèles actuels.
Ne pas développer pour l'instant le nouveau modèle conjoint interpolation /
super-résolution. La priorité est la performance sans baisse de qualité ; le
temps et la complexité ne sont pas des critères de rejet. Conserver un état
exact et reprenable à chaque étape. L'utilisateur a autorisé le travail de
développement et de validation, pas demandé une publication de release.

Ne pas remplacer, quantifier, entraîner ou élaguer les poids. Ne pas changer
les résolutions, les facteurs RIFE, la précision de calcul ou les seuils de
réutilisation pour embellir les chiffres. Premier objectif : transformations
qui suppriment des calculs redondants avec sorties RGB identiques octet pour
octet à la référence. Toute divergence doit être expliquée et résolue avant
activation de l'optimisation concernée.

## Point de départ

- Dépôt lecteur : `/home/ta2b/Documents/mpv-AnimeJaNai-HDR`, branche `hdr-3.8`,
  HEAD `d4969ebdc0d68db47e0a2ca531a30936174bd943`, version `3.8.0.19`.
- Avant ce chantier : seul `docs/OPTIMISATIONS-MOTEURS.md` est non suivi ; il
  contient l'analyse précédente et le classement sans critère de difficulté.
- Dépôt d'inférence voisin : `/home/ta2b/Documents/animejanai-inference-rtx`.
  Modifications utilisateur préexistantes : `aji-rtx-linux/aji_rtx_vfx.cpp`
  modifié et `aji-rtx-linux/libaji_rtx.so` non suivi. Les préserver.
- Hôte : CachyOS Linux, NVIDIA RTX 4070 Ti 12 Go, pilote `615.78.08`.
  GPU observé à 15 % / 30,77 W au début : activité de bureau non contrôlée.
- Compilateurs `g++`, `gcc`, `clang++` présents. `cmake` et `ninja` absents
  du PATH hôte au début. Docker disponible, outils antérieurs dans
  `/home/ta2b/.animejanai-tools` ; inventaire initial terminé, outils retenus ci-dessous.
- Aucun `AGENTS.md` trouvé dans le dépôt ou ses parents.

## Premier lot choisi

Cache exact des images sources et extrémités SPAN dans NCNN/Vulkan, préparation
RIFE une fois par paire, avec une option permettant de comparer à la référence
sans cache. Ces changements s'attaquent à une redondance certaine, sans
modifier les convolutions ou les poids. Puis étudier le moteur spécialisé et
les graphes/fusions à partir des mesures obtenues.

Le code initial `native/linux-vulkan/aji_vulkan.cpp` réexécute SPAN sur A et B
pour chaque instant interpolé lorsque RIFE est après l'upscaling. En ×4, cela
représente 7 upscalings par intervalle (3 fois A+B et la sortie B), contre une
nouvelle extrémité à calculer si les anciennes sont correctement réutilisées.
RIFE avant SPAN répète resize/préparation des sources ; chaque intermédiaire
doit néanmoins toujours être passé dans SPAN.

Le pont ABI 1 ne transmet pas d'identifiant d'image ni de PTS au moteur. Un
cache fondé sur les pointeurs serait incorrect : les décodeurs réutilisent les
buffers. Exiger une comparaison exacte des pixels actifs, indépendante du
stride et des octets de padding, et invalider lors de `configure`. Examiner
aussi les alias ncnn::Mat : la normalisation est en place, donc les caches ne
doivent pas être altérés par un appel ultérieur.

## État exact actuel

**Phase : premier cache révision 2 implémenté et validé sur le GPU indiqué.** Le moteur
`native/linux-vulkan/aji_vulkan.cpp` contient maintenant un cache LRU de deux
sources identifiées par comparaison de tous les octets RGB actifs, préparation
des extrémités selon l'ordre RIFE/SPAN, et cache du packing/décision de scène
par paire. Chaque source mémorisée est clonée avant une opération qui la
modifierait. `configure` efface ces caches. `AJI_VK_CACHE=0` désactive le cache
pour les comparaisons ; le défaut est activé dans la copie de travail.
Ajout de compteurs SPAN/RIFE/préparation/cache dans le fichier de statistiques.
La publication et les vérifications sur les autres plateformes restent à faire.

La référence immutable est extraite avec `git archive d4969eb` dans
`artifacts/performance/reference-source`. La compilation a été faite via :

```bash
PATH="$PWD/artifacts/performance/python/bin:$PATH" \
VULKAN_SDK=/home/ta2b/Documents/AnimeJaNai-AutoHDR/vulkan-headers \
AJ_PYTHON="$PWD/artifacts/performance/python/bin/python" AJ_BUILD_JOBS=6 \
bash artifacts/performance/reference-source/installer/linux/build-inference.sh \
  "$PWD/artifacts/performance/build-work" \
  "$PWD/artifacts/performance/reference-bundle" \
  "$PWD/BuildMpvUpscale2xAnimeJaNai/mpv-upscale-2x_animejanai/animejanai/onnx" \
  > artifacts/performance/reference-build.log 2>&1
```

Construction de référence terminée avec succès. Bibliothèque immutable :
`artifacts/performance/reference-bundle/inference/libaji_vulkan.so`, modèles
convertis inchangés dans `reference-bundle/onnx`, RIFE 4.6 dans
`reference-bundle/rife-vulkan`.

Le candidat est construit avec le même compilateur et les mêmes flags, objets
NCNN/RIFE/parser et bibliothèques : seul `aji_vulkan.cpp.o` diffère. Script
reproductible (artefact ignoré) :
`artifacts/performance/python/bin/python artifacts/performance/build-candidate.py`.
Les commandes complètes sont dans `artifacts/performance/candidate/commands.txt`.
Bibliothèque : `artifacts/performance/candidate/libaji_vulkan.so`.

Le test réel `tests/inference/vulkan_cache.py` compare les trois modes en
processus séparés : ancienne bibliothèque, candidat cache désactivé et candidat
cache activé. Il vérifie octet pour octet les sorties, l'immutabilité des
entrées, le padding de sortie, des buffers réutilisés, un changement d'un seul
octet chroma, strides avec padding changeant, réconfigurations, SPAN
Performance/Balanced, chaînes à deux modèles, RIFE seul/avant/après, coupes et
facteur rationnel 5/2.

La première exécution utilisait deux noms de clés RIFE incorrects dans l'outil
de test (`rife_factor_num/den` et `rife_scd_threshold`). Le parser les ignorait :
RIFE n'était pas activé. **Les résultats de cette première exécution sont
invalides pour RIFE et pour tout gain annoncé** ; conservés sous
`cache-initial-inactive.log/json`. Les clés sont corrigées en
`rife_factor_numerator/denominator` et `rife_scene_detect_threshold`.
Le test vérifie désormais le facteur négocié, le chargement et les appels
réels RIFE, les préparations de paires et le compte exact d'inférences SPAN.
Les exécutions corrigées utilisent la commande suivante (voir le rapport final en tête) :

```bash
artifacts/performance/python/bin/python tests/inference/vulkan_cache.py \
  --reference artifacts/performance/reference-bundle/inference/libaji_vulkan.so \
  --candidate artifacts/performance/candidate/libaji_vulkan.so \
  --models artifacts/performance/reference-bundle/onnx \
  --rife artifacts/performance/reference-bundle/rife-vulkan \
  --device 'NVIDIA GeForce RTX 4070 Ti' \
  --report artifacts/performance/cache-parity.json \
  > artifacts/performance/cache-parity.log 2>&1
```

**Validation corrigée terminée : PASS**, 12 scénarios, 416 images par mode.
Chaque sortie candidat avec/sans cache est identique octet pour octet à
l'ancienne bibliothèque. Les compteurs vérifient que RIFE tourne réellement,
que le changement d'un seul octet de chroma invalide la source et que les
réconfigurations ne réutilisent pas les anciens résultats.

La comparaison des quatre SPAN livrés avec leurs ONNX d'origine passe aussi
(64×64 et 96×96, contrôles déjà existants) : `onnx-parity.log/json`.
Ce contrôle ONNX a la tolérance historique du projet ; la comparaison
ancienne bibliothèque/candidat, elle, n'a aucune tolérance.

Premier benchmark 1280×720, 12 paires, 3 essais alternés par scénario terminé :
`cache-benchmark-720p.log/json`. Gain médian observé environ ×2,15 pour RIFE
après SPAN ×4, ×1,09 avant SPAN, ×4,74 sur sources identiques. Sur sources
toutes différentes sans RIFE, coût supplémentaire d'environ 2–4 %.
**Mesures préliminaires** : le test ONNX a tourné pendant le début du premier
benchmark ; le bureau reste actif. Refaire une mesure séquentielle et conserver
la distinction entre scènes identiques et entièrement nouvelles.

Le test cache est ajouté au job CI `vulkan-backend` : même bibliothèque en mode
sans cache comme référence, mode avec cache comme candidat, driver logiciel.
Le test de développement utilise en plus l'ancienne bibliothèque immutable.
La CI distante n'a pas encore été exécutée pour ces changements.

**Révision 2 validée, résultats définitifs en tête.** Les chiffres ci-dessus décrivent
la première version du cache, conservés dans `cache-v1-parity.json` et
`cache-v1-benchmark-720p.json`. Le code vient d'ajouter :
- packing RGB24 paresseux des extrémités déjà demandées : les images tenues
  évitent aussi la conversion flottants→octets ; aucun packing/copie de sortie
  supplémentaire sur une source jamais redemandée ;
- sur une coupe déjà décidée par le même seuil qu'avant, reprise de
  l'extrémité précédente, même si RIFE est avant SPAN, au lieu de repasser
  cette image connue dans SPAN pour chaque instant.
Ces deux transformations ont passé une première comparaison stricte des
416 images. Le test a ensuite été renforcé avec trois sources identiques
consécutives (pour exercer la reprise RGB24 déjà packée) et un stride de
sortie changeant à chaque appel. **Exécution renforcée PASS : 461 images par
mode**, 12 scénarios, comparaisons strictes et compteurs corrects.

AppImage 3.8.0.16 extraite sous `artifacts/performance/player/squashfs-root`.
Le mpv possède bien `animejanai-vulkan` ; son dossier `mpv/` apporte Lua 5.2.
Paquet de test par liens préparé sous `artifacts/performance/playback-package`,
avec bibliothèque candidate et modèles de référence. Aucun lecteur utilisateur
n'a été remplacé. **Contrôle PTS/EOF PASS**, RIFE seul ×2 et 3/2 sur le clip
réel de benchmark : `playback-pts.log/json`. Commande :

```bash
artifacts/performance/python/bin/python tests/inference/pts_check.py \
  artifacts/performance/playback-package --device 'NVIDIA GeForce RTX 4070 Ti' \
  --report artifacts/performance/playback-pts.json
```

## Expérience de fusion NCNN, séparée du code activé

Le binaire `artifacts/performance/ncnnoptimize` a été compilé depuis la source
NCNN épinglée et la même archive `libncnn.a`. Commande dans le journal de
session ; flags `-O3 -DNDEBUG -std=c++17 -fopenmp`, include NCNN source/build et
Vulkan, lien libncnn/libvulkan/libSPIRV/libglslang. Les quatre modèles sont
optimisés avec flag `0` (pas de changement de stockage des poids) dans
`artifacts/performance/optimized-models` ; `optimizer.log` garde les fusions.
Les modèles de production et les modèles de référence ne sont pas modifiés.

Comparaison stricte terminée : `optimized-graph-parity.log/json`.
Le test accepte maintenant `--candidate-models`, `--candidate-cache`, `--case`,
`--width/--height` pour isoler des variantes ou vérifier une résolution de lecture.
**Expérience terminée et non retenue dans la production.** Les poids `.bin`
des quatre variantes optimisées sont identiques octet pour octet aux poids
NCNN de référence. Les pixels comparés passent l'égalité stricte en 64p puis
en 1280×720 sur les quatre modèles (Sharp1/Standard, Performance/Balanced).
Rapports : `optimized-graph-parity.json`, `optimized-graph-parity-720p.json`.
Mais le benchmark isolant la fusion (cache désactivé des deux côtés, 24 paires,
5 essais alternés) donne médiane d'intervalle 39,71 ms pour la référence et
40,13 ms pour la variante : aucun gain démontré. `optimized-graph-benchmark-720p`
`.log/json`. **Aucune modification du convertisseur ou des modèles livrés.**

## Commandes des mesures finales

Benchmark révision 2 terminé avec succès, commande :

```bash
artifacts/performance/python/bin/python tests/inference/vulkan_cache.py \
  --reference artifacts/performance/reference-bundle/inference/libaji_vulkan.so \
  --candidate artifacts/performance/candidate/libaji_vulkan.so \
  --models artifacts/performance/reference-bundle/onnx \
  --rife artifacts/performance/reference-bundle/rife-vulkan \
  --device 'NVIDIA GeForce RTX 4070 Ti' \
  --report artifacts/performance/cache-v2-benchmark-720p.json \
  --benchmark --width 1280 --height 720 --pairs 24 --trials 5 \
  > artifacts/performance/cache-v2-benchmark-720p.log 2>&1
```

Tous les autres tests GPU sont arrêtés pendant ce benchmark. Le bureau reste
actif. État GPU et empreintes : `gpu-environment.csv`, `library-sha256.txt`.
Script de comparaison des pixels et PTS à travers le vrai mpv, en 720p :
`artifacts/performance/playback-golden.py`. Il génère un motif en mouvement
`testsrc2` à 24000/1001 i/s, exporte 12 sources en FFV1, puis compare les RGB
décodés et PTS : RIFE après SPAN ×4 et avant SPAN ×2. La première tentative
sur les 12 premières images du clip de benchmark ne donnait qu'une image
distincte : contrôle trop faible pour les mouvements, conservé séparément dans
`playback-golden-static*`. Le script exige désormais plusieurs images distinctes.

Syntaxe Python vérifiée par `py_compile`, workflow YAML chargé avec PyYAML et
présence de la nouvelle étape contrôlée ; `git diff --check` passe.

Le venv `artifacts/performance/python` contient CMake 4.4.4, Ninja 1.13.2,
ONNX 1.23.2, ONNX Runtime 1.31.0 et NumPy 2.5.4. Compilateur GCC hôte
16.2.1 (20260810).
En-têtes Vulkan existants réutilisés en lecture seule depuis
`/home/ta2b/Documents/AnimeJaNai-AutoHDR/vulkan-headers` ; loader hôte
`/usr/lib/libvulkan.so`. Docker n'est pas utilisé.
Sources téléchargées par le script : NCNN `d8227bbe4f0357640319a69660fe399664d8acc0`,
RIFE NCNN `a7532fc3f9f8f008cd6eecd6f2ffe2a9698e0cf7`, aji `v0.11.1`.

Sources déjà lues : `aji_vulkan.cpp`, `aji_vulkan.h`, `smoke.cpp`,
`native/linux-vulkan/CMakeLists.txt`, le job `vulkan-backend` de
`.github/workflows/linux-port.yml`, `native/linux-ort/CMakeLists.txt`.

## Validations exigées et preuves à conserver

- Construction Release de la référence immutable et du candidat avec les
  mêmes dépendances/flags, modèles et GPU.
- Test comparatif dans le moteur réel : sorties identiques pour tous les
  instants, RIFE avant/après SPAN, facteurs ×2/×4/rationnels, scènes coupées,
  sources identiques ou différentes, buffers réutilisés, strides et padding,
  nouvelles tailles et reconfiguration.
- Comptage des vrais appels SPAN/RIFE et du travail réutilisé, avec warm-up
  séparé des mesures.
- Benchmark de chaîne à données identiques, essais alternés référence/candidat,
  activité GPU enregistrée. Ne pas présenter une mesure de bureau chargé comme
  un plafond matériel.
- Tests dans le lecteur après validation du moteur si un mpv compatible est
  disponible. Ne pas modifier l'installation utilisateur pour les essais.
- Artefacts lourds et journaux dans `artifacts/performance/` (ignoré par Git) ;
  résultats décisifs et commandes exactes recopiés dans ce document.

## Prochaine action pour la relève

### Lot 2 en cours — état intermédiaire

- `rife_frame_cache.h` conserve deux tenseurs d'entrée RIFE préparés dans un
  allocateur Vulkan réservé jusqu'à leur destruction. Les commandes restent
  synchrones. Compteurs d'uploads, réutilisations et octets des tenseurs ajoutés.
- `rife-v4-cache.patch` ajoute l'appel interne `process_cached` à la version
  RIFE épinglée. Même prétraitement, réseau, ensemble temporel et post-traitement.
  L'API du pont reste ABI 1. `AJI_VK_RIFE_GPU_CACHE=0` désactive seulement ce lot.
- CMake vérifie les SHA256 des deux sources RIFE et applique le patch à des
  copies dans le répertoire de build, sans éditer le checkout téléchargé.
  La configuration complète a réussi dans `artifacts/performance/vulkan-build-v2`.
  **Construction Release complète terminée**, journal `v2-build.log`.
- `vulkan_cache.py` étendu : modes référence / sans caches / cache CPU seulement /
  caches CPU et GPU ; cas ensemble avant/après SPAN et RIFE seul ×8. Nouveaux
  flags `--reference-cache` et `--candidate-rife-cache` pour isoler les lots en
  benchmark. Syntaxe Python, workflow YAML et couverture des fichiers du cache
  CI vérifiés ; `git diff --check` passe. Comparaison exacte contre la référence
  initiale **PASS** : `rife-gpu-cache-parity.log/json`, 18 scénarios,
  657 images par mode, quatre modes. Ajout également du cas `timestep=0` ; ces
  appels ne comptent pas comme préparation GPU, le retour à l'extrémité reste
  celui de RIFE. Par exemple RIFE avant SPAN ×4 : 9 uploads + 51 hits,
  au lieu de 60 préparations ; RIFE seul ×8 : 9 uploads + 131 hits.
- **Premier benchmark 720p terminé**, `rife-gpu-cache-benchmark-720p.log/json` :
  référence `phase-1/libaji_vulkan.so` avec `--reference-cache 1`, candidat
  `vulkan-build-v2/libaji_vulkan.so`, 24 paires, 5 essais alternés, warm-up exclu.
  Aucun autre test GPU simultané. Les chiffres des tests d'égalité 64×64
  ne doivent pas servir de conclusion de performance.
- Contrôle additionnel **en cours**, `rife-gpu-cache-control-720p.log/json` :
  même candidat `vulkan-build-v2/libaji_vulkan.so` dans les deux modes,
  `--reference-cache 1` (cache GPU désactivé pour la référence), mêmes 24 paires
  et 5 essais. Le premier benchmark montre une variation SPAN seul alors que
  ce lot ne s'exécute pas sans RIFE : ce contrôle écarte les différences de
  construction et aide à quantifier le bruit du bureau.

### Lot 3 en cours — état intermédiaire

Les vecteurs RGB24 de la paire du lot 2 sont recalculés sur A et B à chaque
nouvelle paire, y compris A qui était B dans la paire précédente. Les conserver
avec chaque source préparée permet de n'en calculer qu'un nouveau par intervalle.
Les deux vecteurs de paire sont remplacés par deux vecteurs de source ; mêmes
octets et conversion NCNN, sans approximation. Conserver le binaire du lot 2
comme nouvelle référence et valider ce changement séparément avant activation.
Implémentation C++ faite ; sorties d'extrémité après SPAN réutilisent également
ces RGB24 lorsqu'ils existent déjà. Nouveau compteur `RIFE RGB preparations`.
La compilation attend la fin du contrôle du lot 2 pour ne pas remplacer le
binaire en cours de benchmark ni charger le CPU pendant les mesures.
`--reference-rife-cache 1` ajouté au banc de test pour conserver le cache GPU
du lot 2 dans la référence du futur benchmark du lot 3. Ce dernier n'a encore
aucune preuve de performance ou de qualité.
- Configuration exécutée :

```bash
PATH="$PWD/artifacts/performance/python/bin:$PATH" \
VULKAN_SDK=/home/ta2b/Documents/AnimeJaNai-AutoHDR/vulkan-headers \
cmake -S native/linux-vulkan -B artifacts/performance/vulkan-build-v2 \
  -DCMAKE_BUILD_TYPE=Release \
  -DNCNN_SOURCE="$PWD/artifacts/performance/build-work/ncnn-source" \
  -DRIFE_SOURCE="$PWD/artifacts/performance/build-work/rife-source" \
  -DAJI_SOURCE="$PWD/artifacts/performance/build-work/inference-source" \
  > artifacts/performance/v2-configure.log 2>&1
PATH="$PWD/artifacts/performance/python/bin:$PATH" \
cmake --build artifacts/performance/vulkan-build-v2 -j 6 \
  > artifacts/performance/v2-build.log 2>&1
```

Après compilation : égalité stricte de tous les scénarios contre la référence
initiale ; vidéo mpv ; benchmark alterné contre `phase-1/libaji_vulkan.so`
avec `--reference-cache 1`. Ne pas attribuer au lot 2 les gains du lot 1.

### Suite après validation du lot 2

1. Partir de l'arbre de travail et du résumé en tête. Tous les tests indiqués
   sont terminés et les résultats sont recopiés ; contrôler les empreintes du
   checkpoint avant un nouveau changement, sans relancer les validations terminées.
2. Ne pas reconstruire la référence ni refaire les expériences rejetées sans
   nouvelle raison. Le script `build-candidate.py` réutilise les objets NCNN/RIFE
   pour reconstruire le seul objet du moteur qui change.
3. Prochain gain de structure : supprimer les conversions et transferts entre
   SPAN/RIFE et travailler les noyaux pointwise/warp réellement dominants, en
   conservant les arrondis intermédiaires. Le moteur spécialisé reste l'objectif ;
   le premier lot ne constitue pas sa réalisation complète.
4. Pour réduire le coût du cache sur sources nouvelles, étudier une extension
   optionnelle du pont qui transmet des identifiants **garantis par le lecteur**
   pour les images immuables. Conserver le chemin ABI 1 et la comparaison exacte
   en repli. Ne pas utiliser un pointeur comme identifiant ni remettre les IDs
   à zéro après un seek avec le même contexte. L'extension n'est pas implémentée.
5. Étudier ensuite la préparation RIFE par paire dans TensorRT/DirectML et les
   segments CUDA Graph encore absents. Préserver les modifications utilisateur
   préexistantes dans le dépôt d'inférence voisin. Aucun de ses fichiers n'a été
   édité pendant ce premier lot.
6. Continuer à mettre ce document à jour avant chaque arrêt. Ne publier aucune
   version comme « validée toutes plateformes » avec ces seules preuves NVIDIA.
