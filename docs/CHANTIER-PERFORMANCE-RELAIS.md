# Chantier performances — document de relais

## Suite SVP du 14 octobre — lot RIFE codé après la 3.8.0.23

Demande utilisateur : travailler sur les pistes SVP pendant le build. **Tests
locaux toujours arrêtés.** Aucun benchmark, test de parité ou essai de lecture
lancé pour ce nouveau lot. Modèles, poids, types de calcul, filtres de couleur,
padding et critères de coupe conservés dans le code. **Aucun gain mesuré ni
parité des pixels démontrée pour ce lot** : les résultats précédents de 516
images concernent le moteur de la 3.8.0.23, pas ces nouvelles modifications.

### Moteur partagé (Mac / ORT)

Base `785983c`, branche `hdr-3.8`, changements de ce lot dans
`native/linux-ort/aji_ort.cpp` et `exec_ort.cpp` :

- Décision dessin tenu/coupe conservée par paire. Chaque endpoint reçoit une
  identité renouvelée quand ses octets RGB changent, distincte de son compteur
  d'utilisation. Les identités ne sont pas des adresses de décodeur. Un changement
  de source ou une reconfiguration invalide la décision ; les règles existantes
  et les compteurs par sortie restent les mêmes. Réduit les parcours répétés
  pour ×4/×8 ou une même paire rappelée ; **pas de gain systématique en ×2**.
- Buffer et descripteur de sortie RIFE ORT préalloués, FP16 ou FP32 selon le
  modèle, à la même taille paddée. L'appel ORT écrit dans ce buffer au lieu
  d'allouer une nouvelle sortie à chaque interpolation. La conversion RGB24
  reste inchangée. `AJI_RIFE_OUTPUT_BUFFER=0` garde l'allocation précédente.
- `AJI_RIFE_PAIR_CACHE=0` permet la comparaison avec la décision recalculée à
  chaque instant. Statistiques : `RIFE pair decisions` / `RIFE pair decision hits`.

Compilation **Release de `libaji_ort.so` réussie** avec ORT C++ 1.24.1 dans
`artifacts/performance/svp-rife-shared/build/`, journaux `configure.log` et
`build.log`. Binaire de référence copié avant compilation :
`svp-rife-shared/reference-libaji_ort.so`, issu du lot précédent. Les builds et
rapports immuables de `rife-cpu-prep` et `resume-ncnn` sont préservés.

### Backend NVIDIA / TensorRT, copie Git isolée

Le dépôt voisin avait des changements d'une autre session dans
`aji-rtx-linux/aji_rtx_vfx.cpp` et un binaire non suivi : **préservés**.
Worktree dédié : `artifacts/performance/svp-rife-trt/source`, base `2577252`,
branche [perf-rife-cuda-graphs-20261014](https://github.com/Ta2b/animejanai-inference-rtx/tree/perf-rife-cuda-graphs-20261014).
Commit poussé : **`f4fcd17df4686c9978e49359a12a5c6d53128f72`**. Instructions propres au backend dans
`docs/PERFORMANCE-RIFE.md` de cette branche.

- CUDA Graph capturant **le réseau TensorRT RIFE seulement**, un par contexte,
  avec entrée/sortie fixes. Pas de modification du contexte après capture.
  Échauffement hors capture, capture sur stream privé non bloquant, replay sur
  le stream appelant. Le timestep, les copies de source et les conversions
  restent vivants hors du graphe. Échec de capture/replay : chemin normal
  pour cette configuration. `AJI_RIFE_CUDA_GRAPH=0` désactive la capture.
- Plan de timestep conservé tant que ses bits float sont identiques. En ×2,
  `.5` n'est plus rempli à chaque sortie ; même kernel de conversion FP16.
- Score de coupe rapatrié dans un float épinglé, avec allocation pageable
  précédente si l'allocation épinglée échoue. **La synchronisation CPU de coupe
  reste présente** : le retour public `AJI_SCENE` exige encore cette décision.
- Libération graphe/stream avant tenseurs ; float épinglé libéré au teardown.
  Log de teardown : replays, timestep updates/hits. ABI publique inchangée.
- Le workflow de build Linux accepte désormais `perf-rife-**`. Il compile la
  bibliothèque CUDA complète et archive un binaire ; il ne publie pas de release
  et ne lance pas de benchmark. Le paquet du lecteur utilise encore la librairie
  amont `AjiVersion=v0.11.1` : **ces changements NVIDIA ne sont pas installés dans
  la 3.8.0.23**. Intégration au paquet et compilation Windows restent à faire.

Compilation **de l'unité C++**, deux versions de headers : TensorRT 10.9 du SDK
VideoFX local et 11.3.0.99 téléchargé depuis NVIDIA, headers CUDA 12.8 dans les
deux cas. Objets et journaux sous `svp-rife-trt/` : `aji_trt-candidate.o`,
`aji_trt-trt11-candidate.o`, `build-object.log`, `build-object-trt11.log`.
Ce n'est pas une édition de liens CUDA complète ni une validation GPU.
Le SDK local était hors du PATH ; aucune installation système faite.
Les headers Debian sont extraits sous `trt11/` sans installer le paquet.

Référence de capture et durée de vie :
[documentation NVIDIA](https://docs.nvidia.com/deeplearning/tensorrt/latest/performance/optimization.html#inference-with-cuda-graphs).

### État de la release et reprise

**3.8.0.23 Mac publiée**, application, SHA-256, notice et paquet de benchmark
présents dans [la release](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/releases/tag/3.8.0.23).
Sources de cette release : `aab89ba`, qui précède ce lot. Build Windows réussi ;
contrôles Vulkan/ORT/HDR/plateforme réussis ; packaging Linux encore en cours au
moment de ce checkpoint. Suivi : run Deploy `38479416318`. Ne pas réécrire les
assets de cette version avec les modifications du lot SVP.

Manifeste et patch locaux de ce lot : `svp-rife-shared/checkpoint.json`,
`shared.patch`, et `svp-rife-trt/backend.patch`. Les SHAs des commits et les runs
complémentaires sont enregistrés dans le checkpoint après push.

Prochaines étapes : attendre les compilations CI, intégrer le backend construit
au paquet avec une référence immuable, puis, lorsque des essais seront à nouveau
souhaités, comparer les modes désactivés/activés sur les mêmes sorties.
**Ne pas lancer de tests locaux sur la base de cette liste sans tenir compte de
la consigne d'arrêt toujours active.** Une compilation seule ne démontre ni
accélération ni fidélité. RIFE natif Core ML/Metal, buffers GPU partagés entre
SPAN/RIFE et contextes GPU concurrents ne sont pas implémentés dans ce lot.
Une API orientée paire sera nécessaire pour réduire les attentes NVIDIA sans
identifier faussement une image par un pointeur GPU réutilisé.

## Livraison 3.8.0.23 — état du 14 octobre 2026

**Consigne utilisateur la plus récente : arrêter les tests locaux, terminer le
code, committer, pousser et publier une release.** Aucun nouveau test ni
benchmark local après cette consigne. Les contrôles existants de publication
GitHub restent actifs. Les poids, modèles, précision et profils sont conservés.

Base du lot : `894c94fa09bdc4169ca832634416d34bb4fb8d98` (3.8.0.22),
branche `hdr-3.8`. Version de livraison : **3.8.0.23**. Le push sur `release`
déclenche Deploy (Windows/Linux) et macOS ; seul un fichier effectivement joint
à la release prouve sa publication. Commit moteur **`089b6b50696765f1af54e70f5a56217533300177`**, poussé sur les
deux branches. Builds lancés : [macOS](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/actions/runs/38479119500)
et [Deploy initial](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/actions/runs/38479119497).
Au moment de ce checkpoint, archives non encore publiées. Les références
locales finales et le suivi des workflows sont consignés dans
`artifacts/performance/rife-cpu-prep/publication.json`.

Le lot NCNN précédent est inclus dans cette livraison ; ses snapshots et
rapports restent intacts dans `resume-ncnn/`. Les sections suivantes décrivent
leur état historique, notamment les mentions « non commité ». Pour reprendre,
utiliser cette section et le commit de livraison, pas ces anciens statuts.

### Suivi après les correctifs et piste SVP

Commit de publication corrigé : `aab89ba7ded15d81dc279a83cea2cb39440f6e90`.
Runs à suivre : [Deploy](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/actions/runs/38479416318)
et [macOS](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/actions/runs/38479416046).
Dernier état observé : build Windows réussi ; contrôles plateforme Windows/Linux,
ORT et HDR réussis ; étape Vulkan encore en cours. Moteur Mac réussi, application
Mac encore en construction. **Publication des assets non encore confirmée.**
Aucun nouveau test local lancé. Les premières tentatives restent dans l'historique
ci-dessus ; utiliser ces nouveaux runs pour le suivi courant.

L'utilisateur confirme son ancien cas SVP : **RIFE 4.26, TensorRT, source 1080p,
AnimeJaNai ×2, écran 1080p**. La résolution réellement reçue par RIFE reste inconnue.
Analyse, sources et priorités consignées dans `OPTIMISATIONS-MOTEURS.md`, section
« Piste SVP ». Commits documentaires `ed11c53` / `13b9828` sur `hdr-3.8` seulement :
ils ne relancent pas la release et n'ajoutent aucune optimisation non construite
à ses binaires. Les pistes renforcées sont concurrence GPU bornée, CUDA Graphs
RIFE, réduction des attentes CPU et RIFE natif/résident sur Apple. Ni changement
de modèle ni interpolation à résolution réduite activés.

### Code livré dans le moteur partagé

- `pixel_workers.{h,cpp}` et `engine.h` : pool permanent de sept helpers au
  maximum, plus le thread appelant, partagé entre les conversions CPU. Même
  découpage des plages et mêmes opérations de pixels qu'avant. Les appels
  simultanés partagent le pool ; un appel imbriqué sur un helper s'exécute
  localement. Tous les travaux sont rejoints avant propagation d'une exception.
  `AJI_PIXEL_POOL=0` conserve les threads par appel, pour comparaison ultérieure.
- `exec_ort.cpp`, RIFE : table byte/FP16 initialisée de façon sûre entre threads,
  suppression de la seconde comparaison de A après promotion de B, plan du
  timestep réécrit seulement si ses bits float changent, descripteur du tenseur
  d'entrée ORT conservé pendant la vie de l'interpolateur. Les lignes de travail
  FP16 sont conservées par thread ; les sorties FP32 n'en allouent plus.
- `AJI_RIFE_PROFILE=1` mesure séparément préparation CPU, appel ORT, conversion
  de sortie et attente de l'upscale simultané. Hors de ce mode, aucun nouveau
  chronométrage par phase. Compteurs de préparation, cache, promotion et timestep
  dans les statistiques. L'ABI publique du pont reste inchangée.
- `ort_test.cpp` : temps cumulé d'upscale lu après chaque intervalle source,
  avec exclusion de l'échauffement (`AJI_TEST_WARMUP`). L'ancien endpoint en
  cache pouvait masquer tout le calcul de l'intervalle. Les colonnes deviennent
  `upscale work` et `other` : le résidu n'est pas un temps de copies. Les travaux
  simultanés ne doivent pas être additionnés comme une durée séquentielle.
  Médiane/p95/max et signalement des longues pauses ; copies de diagnostic trio
  uniquement sur demande. Ce dernier changement réduit le coût du **benchmark**,
  pas le coût du lecteur, et ne doit pas être annoncé comme un gain moteur.
- `native/macos-bench/bench.command` : mesures plus longues, échauffement explicite,
  phases RIFE, essais NPU supplémentaires et classement indépendant de la locale.
  `caffeinate -di` protège temporairement contre la veille automatique ; cela ne
  garantit pas l'absence de verrouillage ou de suspension manuelle. Désactivation
  possible avec `AJI_BENCH_STAY_AWAKE=0`. Notice du paquet actualisée.
- CI : les exécutables de vérification du pool sont compilés avec le moteur et
  appelés par les workflows Linux/macOS. La vérification de reconnaissance
  Vulkan et sa dépendance `tiles.{cpp,h}` sont incluses dans la clé de cache.

Le pool profite aux préparations/conversions du moteur partagé, notamment sur
Mac (Core ML natif, Metal et ORT). RIFE reste exécuté par son interpolateur ORT.
Le backend Windows TensorRT/DirectML distinct n'est pas réécrit dans ce lot.

### Preuves déjà obtenues avant l'arrêt des tests

Artefacts : `artifacts/performance/rife-cpu-prep/`. Le snapshot initial comprend
`starting-tree`, `starting.patch` et `starting-manifest.json`. Une copie des
sources d'avant ce lot est dans `reference-source/` ; les anciens lots 1 à 3 et
`resume-ncnn` ne sont ni remplacés ni modifiés.

| Travail terminé avant la dernière consigne | Résultat et trace |
|---|---|
| Compilation Release référence et candidat, ORT C++ 1.24.1, mêmes dépendances | `reference-build/libaji_ort.so`, `candidate-build/libaji_ort.so`, journaux de build ; dernier build terminé |
| Quatre modèles SPAN et RIFE 4.26 / 4.25 / 4.22 lite livrés, provider CPU | `tests/inference/ort_pixel_cache.py` : **17 cas, 516 images par variante**, quatre variantes, **2 064 sorties identiques à l'octet**, `parity.json` / `parity.log` |
| Variantes de cette comparaison | Référence immuable, candidat pool off + profiling on, pool on + profiling on, pool on + profiling off ; pas de tolérance numérique |
| Scénarios | Avant/après, ×2/×4/5:2, resize, coupes, deux SPAN, reconfigure, strides, adresses réutilisées, mutation de source et chroma d'un octet |
| Pool de workers | Plages vides/petites/irrégulières, six appelants simultanés et 600 batches, imbrication, persistance, exceptions et reprise réussies ; mode off également exercé |
| ThreadSanitizer du pool | Terminé avec code 0 ; cinq groupes PASS dans `tsan.log` |
| Détecteur partagé | 33 contrôles de `tiles_test.cpp` réussis |
| Syntaxe des scripts et workflows | Python, bash et lecture YAML exécutés avant l'arrêt ; **pas une exécution macOS** |

SHA-256 de la référence ORT :
`bc5403e36dd42a80b9652b323f554c1f85a841aa6830fc54659c832ed9f18c49`.
SHA-256 du candidat comparé :
`85e671d7d22f10a1f25623306fcd04bb508b732dbdd4c357a5d03aab1368c7f1`.
Les empreintes des modèles sont dans `parity.json`. Les ONNX RIFE viennent de
l'archive officielle déjà utilisée par le paquet Mac ; seuls leurs noms de
dimensions sont adaptés par `name_rife_dims.py`, sans changement des poids.
Le manifeste final archive les sources, binaires et rapports de ce lot.

**Aucun gain chiffré établi pour ce nouveau lot CPU/RIFE.** Aucun microbenchmark
ni benchmark de bout en bout lancé. Ne pas convertir les timings du contrôle
CPU en promesse de performances, ni attribuer un effet de pool à la suppression
des copies du programme de mesure. La parité exacte CPU ne prouve pas la parité
sur les providers GPU/NPU ou les autres pilotes.

### Correctif nécessaire à la publication

Le contrôle Windows de Deploy échoue dans `tests/updater-regressions/Cases.cs`,
ligne 243 : l'assertion attend un chemin contenant seulement `/`, mais la méthode
inchangée `AppImageTarget` utilise les séparateurs natifs de `Path.Combine`.
Même échec observé dans la CI précédant ce lot (run `38468269139`). Correction :
construire les chemins d'entrée **et** attendus avec `Path.Combine(root, "Apps", …)`.
Pas de suppression de contrôle ni de modification du produit. Aucun lancement
local de test ; la CI de publication exécutera le contrôle corrigé. Ce correctif
est poussé sur les deux branches avec la même version 3.8.0.23 ; le build macOS
initial, dont les sources moteur sont identiques, peut continuer.

Le premier build macOS (`38479119500`) compile le moteur et passe les contrôles
du pool, mais s'arrête sur un `grep` attendant l'ancien libellé
`average after the first frame`. L'outil écrit désormais
`average after warmup (1 source frames):`. Le contrôle est adapté à ce nouveau
format, sans supprimer l'assertion ; un nouveau push de ce workflow relance la
construction et la publication Mac. Ce premier run n'a publié aucun fichier.

### Mesures Mac et suite du chantier

La session du Mac s'est verrouillée pendant le benchmark 3.8.0.21. Les
classements et l'incident Balanced à 3 535,9 ms restent provisoires ; le
verrouillage est une explication possible, pas une cause démontrée. Ne pas
écarter un moteur sur cette seule série. Le Mac n'est pas accessible ici.

Pour une reprise autorisée de mesures : comparer pool on/off avec mêmes poids,
profil, sortie et programme de mesure, session déverrouillée ; isoler préparation,
transferts, inférence et attente, dans les deux ordres RIFE. Une mesure de qualité
sur Mac et une mesure de vitesse restent distinctes. **Ne pas relancer ces tests
sans tenir compte de la demande actuelle de l'utilisateur de les arrêter.**

Prochains chantiers de code : chaîne SPAN/RIFE résidente sur GPU et cache des
calculs indépendants du timestep, puis spécialisation des graphes des backends
PC. Ils ne sont pas implémentés ici. Conserver poids et précision des opérations
sensibles. Aucun nouveau modèle RIFE, assembleur maison, changement automatique
d'ordre ou backend Windows annoncé comme terminé.

## Reprise NCNN/Vulkan — lot terminé, checkpoint de relais

Reprise depuis HEAD `894c94f` (3.8.0.22), branche `hdr-3.8`. Les modifications
NCNN non commitées et la correction de la clé de cache CI sont préservées dans
`artifacts/performance/resume-ncnn/starting-tree`, avec `starting.patch` et
`starting-manifest.json`. Une référence C++ du HEAD commité est conservée dans
`resume-ncnn/reference-source/aji_vulkan.cpp` ; les références des lots 1 à 3
restent intactes. Aucun commit, push ou changement de l'installation utilisateur.

**État : ce lot est construit et validé ; les séries de mesures sont terminées.**
Le chantier général reste ouvert. Les modèles restent
inchangés. GPU initialement observé à 98 % / 7 Go ; l'utilisateur a libéré le GPU
pour les tests, charge ensuite observée à 15 % / 2 Go (bureau actif). Ne pas
confondre la parité exacte et les limites du mode de similarité expérimental.
Les lots 7 à 9 sont désormais dans `hdr-3.8` : les indications de branches dans
les sections historiques ci-dessous décrivent leur état à l'époque.

Audit CPU : une zone de 3×3 pixels changée de 16 niveaux est déclarée identique
par les seuils 1,5 / 24 (`resume-ncnn/check-sameness.cpp`, exécuté). C'est une
limite réelle de la règle, pas une preuve d'absence de baisse de qualité.
**Correction décidée : exact par défaut dans NCNN ; similarité opt-in via
`AJI_VK_SAME=similar` ou un seuil explicite.** Les réglages du moteur partagé
déjà livré ne sont pas changés. `AJI_VK_SAME=exact` prévaut désormais sur les
deux variables de seuil (elles pouvaient auparavant annuler le mode exact).
Le compteur est nommé `Held RIFE outputs reused`, car il compte les sorties
intermédiaires évitées, pas les paires. Le mode exact du détecteur partagé évite
désormais l'allocation inutilisée de son tableau de sommes, résultat inchangé.

Validation intermédiaire achevée : compilation Release et 33 contrôles CPU de
`tiles_test.cpp` réussis, puis **18 cas GPU, 657 images par variante**, sorties
identiques à l'octet au HEAD commité avec cache désactivé. Variantes : cache
désactivé, cache CPU seul, caches CPU + RIFE GPU. Rapport `strict-parity.json`,
binaire intermédiaire `candidate/libaji_vulkan.so`. Le premier lancement avait
un mauvais chemin RIFE (sous-dossier au lieu de racine) ; conservé séparément
dans `strict-parity-invalid-path.{json,log}`, corrigé sans changement de code.

Optimisation exacte supplémentaire construite ensuite : `scene_changed` ne
parcourt plus les trois plans float quand la détection des coupes est désactivée
ou que les deux vues désignent le même tenseur immuable. L'inférence RIFE reste
exécutée en mode exact, y compris entre deux images strictement identiques.
Binaire final en test : `final-candidate/libaji_vulkan.so`, SHA-256
`74e29caff5a907851a2f0cb383f4c5155c09be8165a3e5ffaade33e932d60f74`.
Référence HEAD, mêmes dépendances et réglages de convolution :
`reference/libaji_vulkan.so`, SHA-256
`d36191e5205d10b50254d635afeb5f37978150cfa3316614e6e12645ab88ca8e`.
Les commandes de compilation de cette référence sont dans
`reference-build-commands.txt`. Elles remplacent uniquement l'objet du pont
dans le lien CMake courant ; pas de comparaison avec le Winograd des lots 1–3.

### Vérifications du binaire final

| Vérification exécutée localement | Résultat / rapport dans `resume-ncnn` |
|---|---|
| `vulkan_cache.py`, référence committée, 18 configurations, 657 images par variante | Parité à l'octet pour les trois variantes du candidat : cache off, cache CPU seul, cache CPU + RIFE GPU. `final-strict-parity.json` |
| `vulkan_sameness.py`, 128×96 puis 144×104 puis retour | Défaut sans variables et `exact` avec seuils 8 / 255 : chacun des 225 résultats identique à l'octet à la référence. `sameness.json` |
| Similarité opt-in, mêmes configurations | Ancre conservée, fade +2 et objet +64 rejetés, pitch respecté, cache vidé à reconfigure. Le mouvement réel de 3×3 à +16 est effacé : **3 215 octets de sortie SPAN différents**, ce mode n'est pas équivalent en qualité. `sameness.json` |
| Nouvelle commande de CI, même bibliothèque des deux côtés, tailles 64×64 / 80×72 / 64×64 | 225 résultats par variante, contrôles réussis. GPU NVIDIA local, **pas une exécution du pilote logiciel de la CI**. `sameness-ci-settings.json` |
| Ancien filtre mpv, vidéo mobile FFV1 12 images, 720p, après ×4 et avant ×2 | 45 / 23 images de sortie, pixels RGB décodés et PTS identiques. `playback.json`, script `playback.py` |
| Filtre en avance de l'AppImage 3.8.0.20 locale, même vidéo, après ×4, avant ×2 et avant 5/2 | 45 / 23 / 28 images, mêmes pixels et PTS entre référence et candidat ; mêmes résultats avec `ahead=1` et `ahead=6`. Fin de fichier comprise. `playback-current.json`, script `playback-current.py` |

Le lecteur 3.8.0.20 est extrait dans `resume-ncnn/squashfs-root`, lancé directement
avec `--no-config --load-scripts=no --hwdec=no` et ses bibliothèques propres. Aucun
changement à l'installation ni aux fichiers de configuration de l'utilisateur.
Ces tests n'ont pas exercé le seek/pause en lecture interactive, ni le filtre sur
Mac. Les sections historiques « pas exécuté » ci-dessous ne tenaient pas encore
compte de cette vérification du filtre en avance.

CI : la clé du bundle inclut désormais `native/linux-ort/tiles.cpp` et `tiles.h`.
Une étape `vulkan_sameness.py` est ajoutée, rapport archivé. Le test de cache exact
force `AJI_VK_SAME=exact`. Le YAML est lu avec succès ; GitHub Actions et les GPU
AMD/Intel/Mac ne sont pas exécutés dans cette reprise.

### Mesures de cette reprise, caches activés des deux côtés

RTX 4070 Ti, pilote 615.78.08, bureau actif. SPAN Sharp1 Performance, entrées
synthétiques 1280×720, RIFE 4.6 ×4, poids identiques. Cinq essais alternés par
cas, 24 paires avec échauffement exclu. `run-benchmarks.py`, rapports
`benchmark-scd-off.json` et `benchmark-scd-on.json`, environnement et commandes
dans `benchmark-environment.json`. Les durées ci-dessous sont les médianes des
durées par essai ; le facteur est la médiane des rapports référence/candidat de
chaque essai, donc ne correspond pas nécessairement au rapport des deux durées.

| Cas | Référence HEAD, ms / intervalle source | Candidat, ms / intervalle source | Facteur médian et plage des 5 essais |
|---|---:|---:|---|
| SPAN seul, changeant | 38,51 | 42,20 | ×0,912 ; 0,876–1,001 ; écart suspect vérifié ci-dessous |
| SPAN seul, tenu | 3,05 | 2,88 | ×1,001 ; 0,986–1,186 ; pas de gain confirmé |
| RIFE après ×4, coupes désactivées | 186,75 | 159,45 | **×1,142 ; 1,042–1,209**, gain dans chacun des cinq essais |
| RIFE avant ×4, coupes désactivées | 184,80 | 185,52 | ×0,994 ; 0,930–1,033 ; pas de gain confirmé |
| RIFE après ×4, seuil de coupe 0,15 | 171,96 | 160,63 | ×1,054 ; 0,904–1,148 ; variation trop large pour attribuer un gain |
| RIFE avant ×4, seuil de coupe 0,15 | 178,39 | 183,31 | ×0,966 ; 0,921–0,990 ; petit ralentissement observé, à surveiller |

**Contrôle de l'écart SPAN :** seconde série de cinq essais avec 64 paires,
référence 38,61 / candidat 38,84 ms, facteur médian ×0,985 (0,915–1,062).
Témoin comparant **le même binaire de référence à lui-même**, mêmes caches et
64 paires : 41,12 / 40,27 ms, facteur médian ×1,030 (0,943–1,052). Le ralentissement
de 9 % de la première série n'est donc pas confirmé ; le bruit de mesure empêche
d'attribuer les petits écarts au code. Rapports `benchmark-span-repeat.json`,
`benchmark-span-control.json`, `benchmark-span-environment.json`, script
`run-span-confirmation.py`. Agrégation dans `benchmark-summary.json`.

Conclusion limitée : le parcours évité quand les coupes sont désactivées accélère
RIFE après upscale dans ce test. Aucun gain global promis, ni gain établi avec
la détection active ou sur SPAN. La charge du bureau reste présente (40 % relevés
avant une série), ce ne sont pas des mesures isolées de laboratoire. Aucun
benchmark de la similarité approximative présenté comme un gain sans perte.
Les ratios du test de parité ont une référence **sans cache** et incluent les
anciens lots : ne pas les attribuer aux changements de cette reprise.

### Pourquoi continuer à optimiser RIFE après upscale

Question utilisateur pendant cette reprise : RIFE avant upscale serait-il
toujours plus rentable ? **Non, le cache peut inverser le classement.** Avec S
le coût d'un upscale d'image source, Rb/Rh les coûts de RIFE basse/haute résolution
et un facteur F entier, hors première image et coupes : avant ≈ F×S + (F−1)×Rb ;
après avec extrémités en cache ≈ S + (F−1)×Rh. Après gagne si Rh−Rb < S. Sans
cache, les upscales répétés pénalisaient fortement l'ordre après. Le coût réel
dépend des modèles, tailles, matériel et contenu ; il faut aussi comparer le
rendu. Dans le candidat testé ici sans coupe, après ×4 ≈159 ms contre avant
≈186 ms. Cela ne justifie aucun changement automatique de l'ordre des profils.

### Reprendre depuis ce checkpoint

- Base `894c94fa09bdc4169ca832634416d34bb4fb8d98`, modifications **non commitées**.
  `resume-ncnn/final.patch` et `final-manifest.json` décrivent l'état final ; le
  manifeste comprend les SHA des sources, binaires, rapports et poids. Ne pas
  confondre `candidate/` (intermédiaire) et `final-candidate/` (validé et mesuré).
- Aucun test ou benchmark de cette reprise ne reste lancé. Pour une nouvelle
  expérience, utiliser un nouveau sous-dossier et de nouveaux rapports : conserver
  ces preuves et les références immuables des lots 1 à 3.
- Recompilation : CMake existant dans `artifacts/performance/vulkan-build-v2`,
  dépendances épinglées sous `artifacts/performance/build-work`, outils sous
  `artifacts/performance/python/bin`. Commandes de référence dans
  `reference-build-commands.txt`, journaux `configure.log` / `build-final.log`.
  Les scripts locaux de lecteur/mesure reproduisent exactement les appels.
- Prochaine priorité de mesure : profiler CPU/transferts/temps GPU, puis essais
  prolongés des **deux ordres**, sur contenu réel et avec détection des coupes
  active. Conserver le petit ralentissement observé avant ×4 dans le suivi ; ne
  pas le masquer par le gain après ×4 sans coupe.
- Prochain chantier de calcul : chaîne SPAN/RIFE résidente sur GPU et préparation
  partagée des instants RIFE, en identifiant les dépendances réelles au timestep.
  Les poids et les couches sensibles gardent leur précision. Comparer chaque
  sortie au binaire de référence, pas seulement les FPS. Un export « v2 » des
  mêmes poids peut être une expérience de graphe ; aucun modèle n'est remplacé.
- Contrôles encore à faire : seek/pause interactifs du filtre en avance, GitHub
  Actions avec Vulkan logiciel, GPU AMD/Intel et Mac. Les modifications du dépôt
  voisin RTX appartiennent à l'autre session et ne sont pas touchées.

## Suite du 13 octobre 2026 (autre session) — lots 4 à 6

Trois changements faits après les lots 1 à 3, dans une autre session. Ce qui a été exécuté
et ce qui ne l'a pas été est indiqué pour chacun : l'utilisateur fait lui-même les essais
dans le lecteur.

### Lot 4 — choix des noyaux de convolution NCNN (mesuré sur RTX 4070 Ti)

NCNN calcule par défaut les convolutions 3x3 par transformées de Winograd, et sait utiliser
les unités matricielles du GPU (matrices coopératives). Mesure de SPAN seul, images toutes
nouvelles, cache désactivé, 20 à 30 images par cas, bureau actif :

| Cas | Winograd (défaut NCNN) | Produit direct | Gain |
|---|---:|---:|---:|
| Performance 540p | 19,4 ms | 16,7 ms | ×1,16 |
| Performance 720p | 42,7 ms | 35,7 ms | ×1,20 |
| Performance 1080p | 116,1 ms | 94,8 ms | ×1,22 |
| Balanced 720p | 61,9 ms | 44,1 ms | ×1,40 |

Autres combinaisons, Performance 720p : sans unités matricielles 43,0 ms avec Winograd et
53,0 ms sans. Sans unités matricielles, Winograd reste donc le plus rapide ; avec elles,
c'est le produit direct.

Écart avec ONNX Runtime CPU sur une image de bruit 720p : Performance, plus grand écart 5
niveaux au lieu de 10 et 0,009 % des valeurs à plus de 2 niveaux au lieu de 0,134 % ;
Balanced, 3 au lieu de 7. Le produit direct est donc aussi le plus fidèle.

**Activé** dans `aji_vulkan.cpp` pour les GPU NVIDIA qui exposent les matrices coopératives ;
les autres GPU gardent le choix de NCNN (non mesurés). Variables de mesure, 1 ou 0 :
`AJI_VK_WINOGRAD`, `AJI_VK_WINOGRAD43`, `AJI_VK_COOPMAT`, `AJI_VK_SGEMM`.
Conséquence : sur NVIDIA, la sortie SPAN n'est plus identique à l'octet à la bibliothèque
initiale des lots 1 à 3 (elle est plus proche de la référence ONNX). La comparaison de la CI,
qui oppose la même bibliothèque avec et sans cache sur un pilote logiciel, n'est pas touchée.

RIFE 4.6 : même essai, **aucun gain** (720p : 20,5 contre 21,1 ms ; 1440p : 90,4 contre
85,9 ms, dans le bruit). Son arithmétique en FP16 casse l'image (écart jusqu'à 241 niveaux) :
à ne pas activer. RIFE n'est pas modifié. À 1440p, RIFE coûte environ 90 ms par image
interpolée sur ce moteur : seul l'ordre RIFE avant SPAN peut tenir le temps réel.

### Lot 5 — le moteur calcule en avance (filtre `vf_animejanai_vulkan.c`)

Le filtre faisait chaque appel au moteur dans le fil du lecteur, image par image : chaque
image devait tenir seule dans le temps entre deux images. Le moteur tourne maintenant sur un
fil à lui et garde jusqu'à `ahead` images sources d'avance (option du filtre, 6 par défaut,
1 = comme avant ; 640 Mo d'images au plus). Seule la moyenne doit tenir : un panoramique est
payé par le temps gagné sur les dessins tenus, que le moteur reprend presque gratuitement.
Les images sortent dans l'ordre ; un seek attend la fin de l'image en cours puis vide tout ;
un changement de format attend que le moteur soit au repos. Concerne tous les moteurs du
pont (NCNN/Vulkan, ONNX Runtime, Core ML, Metal), donc Linux et macOS.
**Vérifié : compilation contre les en-têtes du mpv épinglé, sans avertissement. Pas exécuté
dans mpv.** Premier essai à faire : lecture, seek, pause, fin de fichier, RIFE.

### Lot 6 — reprise par zones dans le moteur partagé (`native/linux-ort`)

`engine_reuse=tiles` coupait toute image en quatre tuiles, y compris quand tout bouge (16 %
de calcul en plus à cause des recouvrements). Il y a maintenant deux découpes : le plan
d'une image entièrement nouvelle (une tuile, ou le partage entre processeurs) et une grille
fine de zones d'environ 320x240 (4x3 en 720p, `engine_areas`, `AJI_AREAS`) avec ses propres
exécuteurs. Seules les zones changées sont calculées, et seulement si c'est plus court que
l'image entière (temps mesurés, nombre de pixels avant qu'ils existent). Le fichier de
statistiques ajoute `Areas:` et `Area devices:`.
**Vérifié : tests unitaires des découpes, et sortie identique à l'octet à l'image entière
(ONNX Runtime CPU, 640x360, coin mobile). Pas exécuté sur Mac.** Le gain réel dépend du taux
de zones immobiles des vidéos : `reused since start` (Ctrl+j) le donne.

### Lot 7 — budget par dessin (branche `perf-budget-par-dessin`, pas dans `hdr-3.8`)

Gardé sur une branche à part tant que le lot 5 n'est pas validé dans le lecteur : il touche
le même filtre.

`[global] engine_boost=yes` (moteur partagé, avec `engine_reuse=frame` et un profil à un
modèle) : un dessin qui reste plusieurs images à l'écran n'est calculé qu'une fois, puis
repris. Quand le temps qu'il reste à l'écran couvre le modèle plus lourd de la même famille
(Performance -> Balanced), c'est celui-ci qui le calcule. Règle : temps du modèle lourd
<= 0,8 x nombre d'images où le dessin est tenu x durée d'une image. Chaque dessin paie donc
pour lui-même ; un panoramique reste en Performance. Le modèle lourd est compilé à
l'ouverture du profil, pas en cours de lecture.

Pour connaître la durée d'un dessin, le moteur demande au filtre les deux images sources
suivantes (`aji_vk_upcoming`, entrée facultative du pont, ABI inchangée) ; le filtre ne
démarre alors une image qu'une fois ces deux-là décodées. Sans `engine_boost`, le moteur n'en
demande aucune et le filtre se comporte comme au lot 5.

`Recent ms`, que lit le choix automatique du profil, ne compte pas le surcoût du modèle
lourd : c'est du temps libre utilisé, pas un besoin du profil. Ligne `Boost:` dans les
statistiques (part des images calculées avec le modèle lourd, ou raison de son absence).

**Vérifié (ONNX Runtime CPU, 320x180)** : dessins tenus trois images -> image finale
identique à l'octet à celle du profil Balanced ; toutes images nouvelles à 24 i/s -> aucune
image en modèle lourd, sortie identique au profil Performance ; `engine_reuse=tiles` -> refus
avec sa raison. **Pas exécuté : le filtre dans mpv, ni aucun Mac.** À juger à l'œil : le
passage d'un modèle à l'autre entre un plan fixe et un mouvement.

### Lot 8 — trois processeurs sur Mac (branche `perf-mac-rife`)

La cible `GPU+NPU+CPU` existait déjà dans le moteur (liste de processeurs séparés par `+`,
grille 3x2). Elle est maintenant dans le Manager (« GPU + Neural Engine + CPU »), normalisée
quel que soit l'ordre, et le paquet de mesure la compare aux autres. Avec Metal, le NPU et le
CPU passent par Core ML. Réserve connue : le CPU décode aussi la vidéo ; c'est la mesure sur
le Mac qui dira si le troisième processeur apporte quelque chose.

### Lot 9 — RIFE dans le moteur partagé, donc sur Mac (branche `perf-mac-rife`)

Le moteur partagé (`native/linux-ort`) interpole maintenant : RIFE 4.x tel que le projet
l'exporte (une entrée de 11 plans), exécuté par ONNX Runtime. Sur Mac, Core ML le fait
tourner quel que soit le moteur qui upscale (ONNX Runtime, Core ML natif ou Metal), sur le
processeur de `[global] engine_rife_device` (`auto`, `gpu`, `npu`, `cpu`). Les moteurs ONNX
Runtime de Linux (CPU, OpenVINO, MIGraphX) en héritent.

Ce qui est fait pour le coût :
- une paire d'images est convertie une fois quel que soit le nombre d'instants, et la seconde
  image d'une paire n'est pas reconvertie quand elle devient la première de la suivante ;
- deux images qui sont le même dessin (seuil de `engine_reuse`) ne sont pas interpolées : la
  sortie est ce dessin, déjà calculé ;
- une coupe de scène (seuil du profil, 0,15) n'est pas interpolée ;
- avant l'upscale (défaut des profils), RIFE calcule à la taille d'entrée du premier modèle
  et l'image obtenue est upscalée comme une image ; après, chaque image source n'est upscalée
  qu'une fois et gardée pour ses deux paires ;
- le modèle est compilé à l'ouverture du profil sur deux images grises : un fournisseur qui
  ne sait pas l'exécuter est détecté là, et le profil joue alors sans interpolation
  (`RIFE: requested, not available: raison` dans les statistiques) ;
- `Recent ms` est ramené à l'image source, pour que le choix automatique du profil compare
  toujours au temps entre deux images sources.

Paquet Mac : trois modèles (`rife_v4.26`, `rife_v4.25`, `rife_v4.22_lite`), dont les deux
dimensions libres sont nommées `height` et `width` (`name_rife_dims.py`) : Core ML n'accepte
que des entrées de taille connue. Le Manager propose RIFE par profil dès que ces modèles sont
là, et le processeur de RIFE dans Global Settings.

**Vérifié (ONNX Runtime CPU)** : l'image interpolée par le moteur est identique à l'octet à
celle du modèle exécuté directement, avec et sans bordure de remplissage ; dessins tenus trois
images : 2 interpolations pour 6 images tenues ; dossier de modèles absent : le profil joue
sans interpolation. **Inconnu tant que la CI macOS ou un Mac n'a pas tourné** : si Core ML
prend tout le modèle (cinq `GridSample`, des `Resize` dans les deux sens) ou le découpe avec
des retours sur le CPU, ce qui déciderait de sa vitesse. Les étapes « RIFE through Core ML »
et « RIFE through the player » de la CI le disent par annotations, sans bloquer.

Ordre de grandeur à garder en tête : avant l'upscale et en x2, une image source coûte une
interpolation et deux upscales. Sur un anime animé « sur deux », une image sur deux est tenue
et ne coûte rien : la moyenne retombe près d'un upscale et demie par image source, et le
tampon d'avance (lot 5) absorbe les à-coups. Sur un panoramique, tout est à calculer.

- avant l'upscale, l'image qui suit est upscalée pendant que l'image intermédiaire est
  interpolée : les deux calculs ne dépendent pas l'un de l'autre. Une image source coûte alors
  le plus long des deux plus un upscale, au lieu de leur somme plus un upscale, quand ils sont
  sur deux processeurs. Sortie identique à l'octet (vérifié sur CPU, où le gain est déjà de
  124 à 106 ms par image source en 320x180). `AJI_RIFE_PARALLEL=0` pour comparer.

Piste non faite : un exécuteur RIFE natif (Metal ou Core ML sans ONNX Runtime), à décider
après avoir vu ce que Core ML fait du modèle.

### Lot 10 — reconnaître un dessin tenu dans une vidéo compressée (mesuré)

**Constat en lecture réelle** (PC de l'utilisateur, RTX 4070 Ti, AppImage 3.8.0.20, épisode
1080p x264 de 24 min, profil TensorRT : 1080p ramené à 720p, RIFE 4.26 x3, SPAN Performance,
RTX TrueHDR, sortie 2560x1440 à 71,9 i/s sur écran 4K) : carte graphique à 95-98 %, et
**530 images perdues sur 1440 en 20 secondes** (`frame-drop-count`). L'étage d'affichage de mpv
ne coûte que 2,3 ms par image (dont 1,0 ms de mise à l'échelle `ewa_lanczossharp` vers 4K et
1,0 ms de shaders de rendu HDR). C'est la chaîne du moteur qui sature : par image source,
2 interpolations, 3 upscales, 3 TrueHDR.

**Cause mesurée sur le même épisode** (9 minutes, luma 720p, processeur seul). Le moteur ne
reprend un résultat que si le pire bloc de 32x32 diffère de moins de 0,40 niveau en moyenne.
Or une vidéo compressée ne répète jamais un dessin à l'identique :

| Mesure sur l'épisode | Résultat |
|---|---|
| Images identiques à l'octet à la précédente | 0,0 % |
| Images reprises avec le seuil 0,40 | 4 à 9 % |
| Dessins réellement tenus | 45 à 58 % |
| Écart du pire bloc sur un dessin tenu | 0,4 à 1,5 niveau, médiane 0,6 |
| Écart du pire octet sur un dessin tenu (720p) | 7 en médiane, 19 au plus |
| Écart du pire octet quand quelque chose bouge | 34 ou plus |

Monter le seul seuil de moyenne ne suffit pas : à 1,5 niveau il laisse passer 1,5 % des
images où un petit objet bouge (quelques pixels très différents que la moyenne du bloc dilue).

**Moteur partagé (macOS, ONNX Runtime) : deux limites au lieu d'une** (`Sameness`, `tiles.h`).
Une image est le même dessin si aucun bloc de 32x32 ne diffère de plus de
`engine_reuse_threshold` en moyenne (1,5 par défaut) **et** si aucun octet ne diffère de plus
de `engine_reuse_peak` (24 par défaut ; 0 = sans limite). La première limite voit ce qui
change un peu partout (fondu), la seconde un petit objet qui bouge. Calibrage sur l'épisode,
en RGB : à 720p, 98,3 % des dessins tenus reconnus et 0,00 % d'images en mouvement reprises à
tort ; à 1080p, 96,5 % et 0,00 %. La valeur 0,40 écrite dans les banques existantes vaut
désormais « défaut ». Le code du moteur lui-même, passé sur les 9 minutes :

| Extrait de 3 minutes | Images reprises avant | Maintenant |
|---|---:|---:|
| à partir de 2 min | 2,7 % | 35,0 % |
| à partir de 10 min | 2,5 % | 54,8 % |
| à partir de 16 min 40 | 1,7 % | 36,3 % |

Cela vaut pour la reprise d'images entières, la reprise par zones, le budget par dessin et
RIFE (pas d'interpolation entre deux images du même dessin). Le test coûte 0,29 ms en 720p
et 0,70 ms en 1080p ; il est écrit en deux boucles pour que le compilateur produise les deux
instructions dédiées (`psadbw` et `pmaxub`), une boucle unique perdait la première.
**Limite : un seul épisode, un seul encodage.** Un encodage plus bruité reconnaîtra moins de
dessins tenus (erreur du côté sûr).

**Moteur TensorRT (PC NVIDIA)** : il n'a que la limite de moyenne. Son défaut passe de 0,40 à
0,70 (`held_threshold`), la bande de 0,40 à 0,70 ne contenant que du bruit sur l'épisode
(aucun pixel au-delà de 24 niveaux) : 26 à 51 % d'images reprises au lieu de 8 à 12 %. La
valeur 0,40 restée dans les fichiers de réglages vaut « défaut ». Pour aller à 45-57 % sans
risque il faut la seconde limite dans le noyau CUDA `k_block_diff` du dépôt privé (non fait :
pas de compilateur CUDA sur ce PC, la compilation passe par la CI de ce dépôt).

**Moteur NCNN/Vulkan** : ses caches (lots 1 à 3) comparent à l'octet près, donc ne reprennent
aucune image différente à cause de la compression. L'adaptation à la même règle est maintenant
écrite dans l'arbre de travail, non commitée : `aji_vulkan.cpp`, `aji_vulkan.h`,
`CMakeLists.txt` et `tests/inference/vulkan_cache.py`. CMake compile `native/linux-ort/tiles.cpp` ;
`AJI_VK_SAME=exact` conserve le chemin de comparaison exacte pour les tests de parité.
Le chemin de similarité peut également éviter RIFE entre deux dessins reconnus identiques.

**Point de reprise retrouvé grâce au dernier message de l'autre IA :** vérifier les listes
de sources dans les clés de cache des builds. Vérification faite : la clé `vulkan-cache` de
`.github/workflows/linux-port.yml` omettait `native/linux-ort/tiles.cpp` et `tiles.h`.
Ces deux dépendances ont été ajoutées à `hashFiles`. Le script de build utilise CMake et
n'énumère pas ces sources séparément ; le cache du lecteur mpv est distinct et n'a pas besoin
de ces fichiers. YAML et présence des deux fichiers dans la clé vérifiés localement.
Pas de compilation ou de validation GPU supplémentaire pendant cette vérification ; la
validation de l'adaptation NCNN reste à consigner avant de l'annoncer comme terminée.

Non mesuré : le coût de chaque étage TensorRT (RIFE, SPAN, TrueHDR) ; le harnais attend que la
carte graphique soit libre.

### Constat sur l'assembleur

La boucle de comparaison d'images (`window_unchanged`) est déjà compilée en `psadbw` par GCC
et Clang : une version écrite à la main n'apporterait rien. Les gains de ces lots viennent
du choix des noyaux, de l'ordonnancement et du calcul évité.

## État à lire en premier — fin du 13 octobre 2026, lots 1 à 3 terminés

**Lot 2 terminé : conserver sur GPU les entrées préparées de RIFE 4.6.**
Empreintes du checkpoint du lot 1 contrôlées avant modification : toutes
conformes. Sources et binaire mesuré copiés dans `artifacts/performance/phase-1/`.
La référence initiale et `phase-1.patch` restent intacts. Construction complète
terminée. Validation exacte contre l'ancienne bibliothèque : **18 scénarios,
657 images par mode, quatre modes**, tous identiques octet pour octet. Rapport
`rife-gpu-cache-parity.json`, `passed=true`. Benchmark 720p isolé contre le lot 1
terminé ; contrôle dans le même binaire également terminé : ×1,0285 médian
après SPAN ×4, dispersion ×0,906–1,082. Gain faible et bruité, pas une promesse
de gain garanti. Pas de modification des shaders, poids, précision ou arrondis.
Validation mpv du lot 2 **PASS** (`playback-golden-v2.log/json`) : 45 images
après SPAN ×4 et 23 avant SPAN ×2, pixels décodés et PTS identiques.
Sources et binaire du lot 2 préservés dans `artifacts/performance/phase-2/`.
**Lot 3 : conserver les RGB24 préparés par source et transmettre directement
les RGB24 de RIFE lorsqu'il termine la chaîne.** Construction incrémentale et
validation stricte terminées : **PASS**,
18 scénarios, 657 images par mode, contre la référence initiale ;
`rife-rgb-cache-parity.log/json`. Benchmark 720p du lot 3 contre le lot 2
**terminé** : après SPAN ×4, 232,80 → 169,34 ms/intervalle, ratio médian apparié
**×1,3247** (×1,302–1,450). Avant SPAN ×4 : 201,51 → 201,44 ms, ×0,9992
(×0,867–1,035), aucun gain supplémentaire prouvé.
Sources et binaire préservés dans `phase-3/`, empreinte binaire
`1d0c6719aa755b5326cba6971d0bdf92c1904fd2332c651b1cf94a79c7b5bedf`.
**Benchmark combiné terminé**, `combined-benchmark-720p.log/json`,
`passed=true` : RIFE après SPAN ×4, **×2,8712** médian apparié
(×2,832–2,957) contre la bibliothèque initiale. Les ratios des lots isolés
n'ont pas été multipliés. **Vidéo mpv du lot 3 PASS**,
`playback-golden-v3.log/json`, référence initiale contre le binaire `phase-3/` :
45 images après SPAN ×4 et 23 avant SPAN ×2, pixels décodés et PTS identiques.
**Aucun build, test ou benchmark encore en cours.** Les modèles et empreintes
des sources du lot 3 ont été contrôlés après tous les tests : conformes au
binaire conservé, identique dans les quatre rapports décisifs du lot 3.

| Résultat combiné 720p, vs bibliothèque initiale | Référence (ms/intervalle) | Lot 3 | Ratio médian apparié |
|---|---:|---:|---:|
| SPAN, sources différentes | 44,45 | 46,04 | ×0,9654 ; plage 0,916–1,006 |
| SPAN, sources identiques | 45,35 | 3,09 | ×14,8893 ; plage 13,969–17,639 |
| RIFE après SPAN ×4 | 493,10 | 173,83 | ×2,8712 ; plage 2,832–2,957 |
| RIFE avant SPAN ×4 | 237,76 | 222,10 | ×1,0964 ; plage 1,010–1,125 |

Un intervalle ×4 produit quatre images. Ratio médian de chaque essai apparié,
différent du ratio des deux médianes affichées. Pas de mesure des FPS du lecteur
ni de validation du temps réel. SPAN sur sources nouvelles : aucun gain prouvé,
petit surcoût possible du cache à réduire ; les chiffres sont conservés tels
qu'observés. Conditions et profil précis dans la section du lot 3.

**Évolution Git pendant le travail :** HEAD est maintenant
`fb98aea75296b73712fcc036b790de51922e1f42`, commit auteur Tatoub du
13 octobre à 20 h 16 min 45 s, apparu indépendamment des commandes de cette
session. Il inclut les lots 1/2 et le début du cache RGB du lot 3, ainsi qu'un
changement utilisateur dans `tests/updater-regressions/Cases.cs` que cette
session n'a pas édité. Ne pas l'annuler/amender. Branche `hdr-3.8`, version
`3.8.0.19` ; les bibliothèques de référence restent celles décrites ci-dessous.
En fin de session, seules les modifications depuis ce HEAD dans
`aji_vulkan.cpp` (sortie RGB directe), `vulkan_cache.py` (son contrôle) et ce
document restent non commitées. Aucun fichier du dépôt d'inférence voisin
n'a été modifié par cette session.

### Lot 1 terminé

Le premier lot NCNN/Vulkan est implémenté et validé sur RTX 4070 Ti. Il a été
inclus dans le commit utilisateur indiqué ci-dessus. Cette session n'a exécuté
aucun commit/push/release ni remplacé l'installation utilisateur.
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
- CI ajoutée ; statut distant non consulté dans cette session. Windows/macOS et autres GPU non
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
`phase-1/libaji_vulkan.so`. La source courante inclut les lots 2 et 3.

**Les builds et tests du lot 1 sont terminés.** Fichiers concernés au lot 1 :
`native/linux-vulkan/aji_vulkan.cpp`, `aji_vulkan.h`, workflow
`.github/workflows/linux-port.yml`, lien de reprise dans `docs/REPRISE.md`,
nouveaux `tests/inference/vulkan_cache.py` et présent document. Le rapport
`docs/OPTIMISATIONS-MOTEURS.md` précède ce chantier et est maintenant suivi.
Ces fichiers sont désormais suivis dans le commit utilisateur. Les binaires
et preuves sont uniquement sous `artifacts/performance/`.
Un patch complet (fichiers suivis et nouveaux fichiers inclus) est conservé
dans `artifacts/performance/phase-1.patch`, avec les empreintes des sources et
du binaire dans `phase-1/checkpoint-manifest.json`. Conserver ce checkpoint
historique intact. Le checkpoint courant est `checkpoint-manifest-v3.json`,
avec `phase-3.patch` (diff depuis le HEAD utilisateur) et
`performance-full.patch` (tous les fichiers du chantier depuis la référence
initiale, excluant le changement utilisateur de l'updater). À régénérer après
une modification, en conservant les snapshots historiques.

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

## Implémentation du lot 1 — historique

**Lot 1 : premier cache révision 2 implémenté et validé sur le GPU indiqué.** Le moteur
`native/linux-vulkan/aji_vulkan.cpp` contient maintenant un cache LRU de deux
sources identifiées par comparaison de tous les octets RGB actifs, préparation
des extrémités selon l'ordre RIFE/SPAN, et cache du packing/décision de scène
par paire. Chaque source mémorisée est clonée avant une opération qui la
modifierait. `configure` efface ces caches. `AJI_VK_CACHE=0` désactive le cache
pour les comparaisons ; le défaut est activé dans la copie de travail.
Ajout de compteurs SPAN/RIFE/préparation/cache dans le fichier de statistiques.
Aucune publication demandée ou effectuée par cette session. Les autres
plateformes nécessitent leurs propres vérifications avant d'y valider ces gains.

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
Le statut de la CI distante n'a pas été consulté pendant cette session.

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

### Lot 2 terminé — preuves et construction

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
- Contrôle additionnel **terminé**, `rife-gpu-cache-control-720p.log/json` :
  même candidat `vulkan-build-v2/libaji_vulkan.so` dans les deux modes,
  `--reference-cache 1` (cache GPU désactivé pour la référence), mêmes 24 paires
  et 5 essais. Le premier benchmark montre une variation SPAN seul alors que
  ce lot ne s'exécute pas sans RIFE : ce contrôle écarte les différences de
  construction et aide à quantifier le bruit du bureau.
- Premier benchmark vs lot 1 : RIFE après SPAN ×4, 244,18 → 228,41 ms,
  ratio médian apparié ×1,065 (×1,056–1,069). Avant SPAN ×4 : 218,66 →
  214,07 ms, ×1,0215 (×1,002–1,056). Contrôle même binaire : après SPAN
  240,10 → 232,98 ms, ×1,0285 (×0,906–1,082) ; avant SPAN 220,73 →
  218,45 ms, ×1,0178 (×0,925–1,052). Variabilité visible : ne pas présenter
  le +6,5 % du premier essai comme un gain garanti du cache GPU seul.
- Validation mpv du lot 2 **PASS**, script `playback-golden-v2.py` :
  référence initiale contre `phase-2/libaji_vulkan.so`, motif en mouvement
  720p, après SPAN ×4 et avant SPAN ×2. 45 et 23 images respectivement,
  RGB décodés et PTS identiques. Reports séparés de ceux du lot 1.

### Lot 3 — validation et benchmark

Les vecteurs RGB24 de la paire du lot 2 sont recalculés sur A et B à chaque
nouvelle paire, y compris A qui était B dans la paire précédente. Les conserver
avec chaque source préparée permet de n'en calculer qu'un nouveau par intervalle.
Les deux vecteurs de paire sont remplacés par deux vecteurs de source ; mêmes
octets et conversion NCNN, sans approximation. Conserver le binaire du lot 2
comme nouvelle référence et valider ce changement séparément avant activation.
Implémentation C++ faite ; sorties d'extrémité après SPAN réutilisent également
ces RGB24 lorsqu'ils existent déjà. Nouveau compteur `RIFE RGB preparations`.
Quand RIFE est en fin de chaîne, son post-traitement retourne déjà des octets
RGB24. Le chemin optimisé les copie par ligne vers la sortie au lieu de les
dépaqueter en floats puis de les repaqueter en octets ; `RIFE direct RGB outputs`
compte ce chemin. RIFE avant SPAN conserve ses conversions et le calcul SPAN.
Les vues à `timestep=0` restent valides jusqu'à la copie car leurs vecteurs sont
possédés par les sources du contexte, sans nouvelle préparation avant la copie.
Le contrôle et la validation mpv du lot 2 sont terminés. Construction
incrémentale terminée, journal `v3-build.log`. La validation mpv du lot 2 a
utilisé le binaire immuable `phase-2/libaji_vulkan.so`, indépendant de cette
construction. Comparaison stricte du lot 3 terminée : **PASS**, 18 scénarios,
657 images par mode, quatre modes, sorties identiques octet pour octet.
Les compteurs vérifient une conversion RGB par source et la sortie RGB directe
pour chaque appel RIFE en fin de chaîne, y compris `timestep=0`.
Benchmark 720p **terminé** contre `phase-2/libaji_vulkan.so`,
`--reference-cache 1 --reference-rife-cache 1`, 24 paires et 5 essais alternés.
La référence conserve donc le cache GPU du lot 2 : le gain mesuré est celui
du cache RGB et de la suppression du détour par les floats, pas un mélange
avec les lots antérieurs.
`--reference-rife-cache 1` ajouté au banc de test pour conserver le cache GPU
du lot 2 dans la référence du benchmark du lot 3. Résultats :

| Cas 720p | Lot 2 (ms/intervalle) | Lot 3 | Ratio médian apparié et plage |
|---|---:|---:|---:|
| SPAN, sources différentes | 45,46 | 45,52 | ×0,9986 ; 0,977–1,051 |
| SPAN, sources identiques | 2,919 | 3,004 | ×0,965 ; 0,924–1,015 |
| RIFE après SPAN ×4 | 232,80 | 169,34 | ×1,3247 ; 1,302–1,450 |
| RIFE avant SPAN ×4 | 201,51 | 201,44 | ×0,9992 ; 0,867–1,035 |

Un intervalle ×4 produit quatre sorties. Bureau actif, aucun autre test GPU
simultané. Sur SPAN seul et RIFE avant SPAN, aucun gain supplémentaire prouvé ;
le petit écart sur les sources identiques reste visible dans le rapport.
Compteurs après SPAN ×4 sur 24 paires : 25 SPAN, 72 RIFE, 25 uploads +
119 réutilisations GPU, 25 conversions RGB (au lieu de 48 par paires),
72 sorties RGB directes ; tenseurs d'entrée RIFE : 44 236 800 octets.
Avant SPAN : 0 sortie RGB directe et 11 304 960 octets de tenseurs RIFE.

**Benchmark combiné terminé** contre la référence initiale, mêmes 24 paires,
5 essais alternés, 720p ; `combined-benchmark-720p.log/json`, `passed=true`.
Les résultats isolés ci-dessus ne sont pas multipliés pour reconstituer un
gain global. Profil mesuré : **Sharp1 Performance SPANF3 b5f48 FP16 + RIFE
4.6**, une étape SPAN, sans redimensionnement, ensemble désactivé et seuil SCD
désactivé (0), sources 1280×720, sorties 2560×1440. Le benchmark utilise le
gradient animé et les variations locales définis dans le script, pas une
lecture vidéo chronométrée. Le bureau reste actif ; aucune fréquence GPU
verrouillée, aucune autre validation GPU simultanée. Les quatre modèles SPAN
sont vérifiés en qualité, ce benchmark n'étend pas ses gains mesurés aux quatre.

Vidéo mpv du lot 3 : **PASS**, `playback-golden-v3.log/json` ; motif en mouvement
720p, 45 images après SPAN ×4 et 23 avant SPAN ×2, pixels RGB décodés et PTS
identiques à la bibliothèque initiale. Le script exige plusieurs images
distinctes. Le binaire conservé dans `phase-3/` a servi à ce test et au
benchmark combiné ; il est identique à celui de la parité et du benchmark isolé.

### Commandes exactes du lot 3

Exécutées depuis la racine du dépôt. Les noms de rapports ci-dessous désignent
les preuves existantes ; utiliser de nouveaux noms en cas de nouvelle expérience.
Ne pas refaire ces tests terminés sans changement ou nouvelle question à vérifier.

```bash
# Construction incrémentale après les changements C++ du lot 3.
PATH="$PWD/artifacts/performance/python/bin:$PATH" \
cmake --build artifacts/performance/vulkan-build-v2 -j 6 \
  > artifacts/performance/v3-build.log 2>&1

# Parité exacte, quatre modes, 18 scénarios, 657 images par mode.
artifacts/performance/python/bin/python tests/inference/vulkan_cache.py \
  --reference artifacts/performance/reference-bundle/inference/libaji_vulkan.so \
  --candidate artifacts/performance/vulkan-build-v2/libaji_vulkan.so \
  --models artifacts/performance/reference-bundle/onnx \
  --rife artifacts/performance/reference-bundle/rife-vulkan \
  --device 'NVIDIA GeForce RTX 4070 Ti' \
  --report artifacts/performance/rife-rgb-cache-parity.json \
  > artifacts/performance/rife-rgb-cache-parity.log 2>&1

# Lot 3 isolé : référence lot 2 avec ses deux caches actifs.
artifacts/performance/python/bin/python tests/inference/vulkan_cache.py \
  --reference artifacts/performance/phase-2/libaji_vulkan.so \
  --reference-cache 1 --reference-rife-cache 1 \
  --candidate artifacts/performance/vulkan-build-v2/libaji_vulkan.so \
  --models artifacts/performance/reference-bundle/onnx \
  --rife artifacts/performance/reference-bundle/rife-vulkan \
  --device 'NVIDIA GeForce RTX 4070 Ti' \
  --benchmark --width 1280 --height 720 --pairs 24 --trials 5 \
  --report artifacts/performance/rife-rgb-cache-benchmark-720p.json \
  > artifacts/performance/rife-rgb-cache-benchmark-720p.log 2>&1

# Ensemble des lots : référence initiale vs binaire conservé du lot 3.
artifacts/performance/python/bin/python tests/inference/vulkan_cache.py \
  --reference artifacts/performance/reference-bundle/inference/libaji_vulkan.so \
  --candidate artifacts/performance/phase-3/libaji_vulkan.so \
  --models artifacts/performance/reference-bundle/onnx \
  --rife artifacts/performance/reference-bundle/rife-vulkan \
  --device 'NVIDIA GeForce RTX 4070 Ti' \
  --benchmark --width 1280 --height 720 --pairs 24 --trials 5 \
  --report artifacts/performance/combined-benchmark-720p.json \
  > artifacts/performance/combined-benchmark-720p.log 2>&1

# Pixels et PTS dans le vrai mpv, hors installation utilisateur.
artifacts/performance/python/bin/python artifacts/performance/playback-golden-v3.py \
  > artifacts/performance/playback-golden-v3.log 2>&1
```

Le script mpv utilise explicitement le binaire immuable de `phase-3/` ; pour
une future version, adapter une copie du script et conserver des rapports séparés.
La reproduction du lot 2 requiert son script de test archivé dans
`phase-2/tests/inference/vulkan_cache.py` : le script courant exige les nouveaux
compteurs RGB qui n'existaient pas dans ce binaire historique.

Empreintes des bibliothèques : référence initiale
`2479666406e255c20bdb9fd28cb507c3e1ec61eb8552d39fe896eed5ce4dfb90` ;
lot 1 `94c2cf029a4ff3d036c3237be883b777d3a6930b16c3001c48a39bc56d86cb4e` ;
lot 2 `f7b2653782f36ebd0c365a201ee89a31bad0fc3704604f6524c40dabf7bf9647` ;
lot 3 `1d0c6719aa755b5326cba6971d0bdf92c1904fd2332c651b1cf94a79c7b5bedf`.
Sources C++ du lot 3 :
`8c294a0be2959aa5c7e7df3c014e46eb80ee599b6dd90ff758d21142c30ad9d2`.
Rapports : empreintes des quatre modèles convertis et de RIFE 4.6 enregistrées ;
modèles référence/candidat identiques. Aucun changement de précision/résolution.

Configuration complète initiale du lot 2, réutilisée par la construction
incrémentale du lot 3 (historique des commandes exécutées) :

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

Les validations du lot 2 après cette compilation sont toutes terminées :
parité exacte contre la référence initiale, vidéo mpv et benchmark alterné
contre `phase-1/libaji_vulkan.so` avec `--reference-cache 1`. Ne pas attribuer
au lot 2 les gains du lot 1.

### Suite après validation du lot 3

1. Partir de l'arbre de travail et du résumé en tête. Tous les tests indiqués
   sont terminés et les résultats sont recopiés ; contrôler les empreintes du
   checkpoint courant avant un nouveau changement, sans relancer les validations
   terminées. Les snapshots `phase-1/`, `phase-2/`, `phase-3/` sont immuables.
2. Ne pas reconstruire la référence ni refaire les expériences rejetées sans
   nouvelle raison. Pour le code courant, utiliser la construction CMake
   incrémentale dans `vulkan-build-v2` ; elle ne recompile que les objets
   modifiés. `build-candidate.py` appartient au lot 1 et utilise le RIFE
   d'origine : il ne convient plus au code courant avec le cache GPU.
3. Prochain gain de structure : supprimer les conversions et transferts entre
   SPAN/RIFE et travailler les noyaux pointwise/warp réellement dominants, en
   conservant les arrondis intermédiaires. Le moteur spécialisé reste l'objectif ;
   les lots actuels ne constituent pas sa réalisation complète. Le prochain
   pont doit conserver sur GPU la sortie RGB24 de RIFE avant SPAN, sa
   conversion/normalisation et l'inférence SPAN, avec exactement les arrondis
   actuels. La détection des coupes doit conserver son accumulation actuelle.
   Avant ce chantier plus large, vérifier un gain direct : `scene_changed`
   accumule encore toutes les différences même lorsque le seuil est désactivé.
   Retourner immédiatement `false` si `!(threshold>0)` conserve le résultat
   actuel et évite ce parcours. Même possibilité pour deux sources déjà
   reconnues identiques, sans supprimer l'inférence RIFE(A,A,t), dont l'identité
   avec A n'est pas démontrée. **Pas encore implémenté ni mesuré** ; à vérifier
   séparément avec la référence du lot 3 et les scénarios de coupes activées.
4. Pour réduire le coût du cache sur sources nouvelles, étudier une extension
   optionnelle du pont qui transmet des identifiants **garantis par le lecteur**
   pour les images immuables. Conserver le chemin ABI 1 et la comparaison exacte
   en repli. Ne pas utiliser un pointeur comme identifiant ni remettre les IDs
   à zéro après un seek avec le même contexte. L'extension n'est pas implémentée.
5. Étudier ensuite la préparation RIFE par paire dans TensorRT/DirectML et les
   segments CUDA Graph encore absents. Préserver les modifications utilisateur
   préexistantes dans le dépôt d'inférence voisin. Aucun de ses fichiers n'a été
   édité pendant cette session, y compris les lots 2 et 3.
6. Continuer à mettre ce document à jour avant chaque arrêt. Ne publier aucune
   version comme « validée toutes plateformes » avec ces seules preuves NVIDIA.
