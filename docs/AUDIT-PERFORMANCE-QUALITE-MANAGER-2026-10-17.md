# Audit performances, qualité et Manager — 17 octobre 2026 (soir)

Complète [l'audit global du matin](AUDIT-GLOBAL-2026-10-17.md) après les livraisons .84 → .106. Objectif fixé par l'utilisateur : performances maximales sans perte de qualité, gains de qualité acceptés s'ils coûtent peu, jugement de l'interface et de l'expérience du Manager. Les recommandations ne sont pas des correctifs livrés.

## Base de preuve et limites

- Sources auditées : PLAYER `hdr-3.8` = `95b1735` (release 3.8.0.106, source `a688bef`), Manager `714d48e` (branche `perf-specialized-manager-add-step-20261017`), backend NVIDIA privé livré `118c272` (seule branche distante le contenant : `fix-legacy-quality-forwarding-20261017`), bundle GPU `dc53e6c`, mpv `the-database/mpv@19c0fcf` plus neuf patches de `native/linux-cuda/`, moteur partagé `the-database/animejanai-inference` v0.11.1. Tout est lu dans les checkouts isolés de `~/.animejanai-tools/work/`.
- Jira : la première passe a été faite sans connecteur Atlassian, depuis le snapshot des 333 tickets (`audit-20261017/tickets.json`), les reçus de release (`jira/release-*.json`) et ETAT-COURANT. Le connecteur a été activé ensuite dans la même session : la section 6 est relue sur les **369 tickets vivants** (JQL `project = AH`, 17 octobre au soir). Les décisions d'audit (conserver, reformuler…) restent celles du snapshot du matin.
- Aucune mesure GPU nouvelle : le GPU héberge le lecteur de l'utilisateur et le protocole interdit la mesure concurrente. Les chiffres viennent des traces `AJI_PIPELINE_TRACE` du lot 62 (`artifacts/performance/lots-20261017/quality-live-20261017/`) et du banc du 14 octobre (`~/.animejanai-tools/work/research/results-timing.txt`), même RTX 4070 Ti, TRT 11.3.
- Manager : rendu headless réel de `714d48e` par `tests/NavigationUi` sur une fixture sans moteurs ([captures](audit-20261017/manager-ui-3.8.0.106/)). Aucun profil utilisateur modifié ; installation utilisateur lue seulement.

## Verdict

Le moteur livré est sain et exact : caches de paire, promotion B→A, graphes CUDA, batch Quality, provenance par module. La chaîne de l'utilisateur (Area 720 → RIFE 4.26 Quality ×4 → SPAN 1440 → TrueHDR) tient en 46,4 ms par paire pour un budget de 41,7 ms à 24 i/s : il manque environ 5 ms, soit 10 %.

Le blocage n'est plus technique mais **méthodologique** : Quality exige l'identité bit à bit avec un plan TensorRT particulier. Ce critère a rejeté les deux seules pistes capables de rendre ces 5 ms (encodeur RIFE partagé AH-357, SPAN batch 4 AH-358) sur des écarts de l'ordre du bruit FP16, invisibles. Une reconstruction TensorRT ordinaire produit des écarts du même ordre. Remplacer ce critère par une équivalence numérique bornée contre une référence FP32 débloque un plan crédible de 6 à 12 ms de gain, listé en section 3, sans toucher aux modèles ni aux prédictions complètes.

Deux corrections de fidélité sont gratuites et prioritaires : la matrice BT.709 codée en dur dans RIFE (sources SD 601 traitées dans le mauvais espace) et le fichier moteur périmé encore présent dans l'installation de l'utilisateur (AH-330, In Progress depuis le 17 au matin sans livraison). Le Manager .106 est structurellement bon ; ses défauts sont de hiérarchie, de vocabulaire et de langue, pas d'architecture. Le processus produit trop de releases et trop de documentation pour trop peu de lecteurs.

## 1. Où passe le temps de la chaîne Quality ×4

Traces lot 62 (`lot62-native-batch.log`), paires chaudes 1 et 2, sortie 2560×1440, quatre images par paire :

| Étage | Temps par paire | Contenu |
|---|---:|---|
| Area 1080 → 720 | 0,8 ms | une image source par paire, kernel FP64 |
| RIFE + SPAN fusionnés (batch Quality) | 37,9 ms | 3 prédictions RIFE 720p + 4 SPAN 720p → 1440p |
| TrueHDR | 6,9 ms | 4 conversions 1440p, SDK sur stream par défaut, 3 synchronisations hôte par image |
| Total mesuré | 46,4 ms | budget 41,7 ms à 23,976 i/s (× 4 = 95,9 i/s affichées) |

Décomposition du bloc fusionné d'après le banc du 14 octobre, même GPU :

| Réseau | Temps | Note |
|---|---:|---|
| RIFE 4.26 à 1280×768 (720p paddé à 64) | 7,9 ms | 3 par paire ≈ 23,7 ms |
| SPAN Sharp1 Performance 720p → 1440p | 4,1 ms | 4 par paire ≈ 16,4 ms |
| SPAN Sharp1 Balanced 720p → 1440p | 7,5 ms | non affordable à ×4, affordable à ×2 |
| RIFE 4.15-lite / 4.22-lite / 4.25 | 6,4 / 7,8 / 8,4 ms | 4.26 est déjà parmi les plus rapides ; les « lite » ne rendent presque rien |
| RIFE 4.26-heavy | 34,3 ms | hors temps réel à ×4 |
| Warp + blend 1440p (chemin Fast) | 1,8 ms | explique le Fast ×4 à 18 ms |

Conclusion : la chaîne est **limitée par le calcul des réseaux** (≈ 87 % du temps), pas par les copies ni les synchronisations. Les optimisations de métadonnées, d'attentes et de copies déjà livrées (AH-345/346/347/354/355) ont rendu ce qu'elles pouvaient (baseline 55–59 ms → 46,4 ms). Il reste environ 1 à 2 ms de synchronisations évitables (16 attentes hôte par paire, dont 12 pour TrueHDR) et ~1 ms de bulle entre paires (un seul ticket en vol).

## 2. Le verrou : « exact » signifie aujourd'hui « identique à un plan TensorRT donné »

Les deux études rejetées :

| Étude | Écart constaté | Lecture |
|---|---|---|
| AH-357 encodeur RIFE partagé | 1 053 807 / 2 764 800 valeurs uint16 différentes, **max 88 sur 65 535** | 0,13 % de la dynamique : 0,34 niveau 8 bits, 1,4 niveau 10 bits au pire pixel |
| AH-358 SPAN batch 4 | 8 063 623 / 11 059 200 FP16 différentes, max abs 0,0107, **MSE 1,43e-7** | PSNR ≈ 68 dB ; RMS 0,1 niveau 8 bits, pire pixel 2,7 niveaux |

Ces écarts ont la signature d'un changement de tactiques TensorRT (ordre d'accumulation FP16, algorithme de convolution), pas d'une perte de qualité. Le [contrat de précision](CONTRAT-PRECISION-MOTEURS.md) le dit lui-même : « une reconstruction indépendante TensorRT peut changer les tactiques ». La référence `4c1074ed` est un plan construit avec `--builderOptimizationLevel=5`, qui choisit déjà les kernels les plus rapides, FP16 compris ; elle n'est pas un étalon de qualité, seulement un étalon de reproductibilité.

Recommandation (nouveau ticket, prérequis de toute suite sur AH-73/76/329) : **définir le critère Quality comme une équivalence bornée contre une référence FP32** (ONNX Runtime CPU ou plan TRT FP32 des mêmes poids), par exemple :

- erreur du candidat contre FP32 ≤ erreur de la référence livrée contre FP32, mesurée en MSE et en erreur max sur un jeu fixe de paires privées ;
- aucune valeur non finie, aucune dérive temporelle (même décision de coupure de scène, mêmes PTS) ;
- contrôle visuel d'une paire difficile (contours, occlusion) uniquement si l'erreur max dépasse 1 niveau 10 bits.

Ce critère conserve tout ce que « Quality » promet à l'utilisateur (prédictions complètes, modèles de référence, aucun raccourci temporel) et cesse d'interdire ce que TensorRT fait déjà à chaque rebuild. Les quatre premières lignes du plan ci-dessous dépendent de cette décision.

## 3. Plan d'optimisation sans perte perceptible

Gains estimés, non mesurés, par paire sur la chaîne de la section 1. Chaque ligne est un lot bornable, à mesurer avec la sonde existante (`tests/inference/pipeline_fusion_probe.py`, `AJI_PIPELINE_TRACE=1`) au repos GPU.

| # | Levier | Mécanisme | Gain estimé | Condition | Effort |
|---|---|---|---:|---|---|
| 1 | SPAN batch 4 (AH-358 / AH-76) | une inférence B4 au lieu de quatre B1 ; meilleure occupation du GPU à 720p | 2,5 à 5 ms | critère section 2 ; mesurer, la sonde AH-358 s'est arrêtée avant le timing | moyen, prototype existant |
| 2 | Encodeur RIFE indépendant de t partagé (AH-357 / AH-73) | 1 encodeur par paire au lieu de 3 | 0,5 à 1,5 ms | critère section 2 ; patch de recherche `lot83` conservé | moyen, prototype existant |
| 3 | Padding RIFE à 32 au lieu de 64 | 1280×736 au lieu de 1280×768 : 4,2 % de pixels en moins pour RIFE | ≈ 1 ms | vérifier l'alignement réel exigé par IFNet 4.26 ; bords seuls affectés | faible |
| 4 | Remise directe RGB FP16 RIFE → SPAN | supprimer l'aller-retour YUV16 entre les deux réseaux (2 kernels par intermédiaire) ; plus précis, pas moins | 0,5 à 1 ms | critère section 2 (quantification intermédiaire supprimée) | faible |
| 5 | TrueHDR sur le stream du pipeline | `NvVFX_SetCudaStream(stream)` au lieu de NULL, pack/unpack enchaînés, aucune attente hôte par image | 0,5 à 1,5 ms | qualifier le SDK installé sur stream explicite ; sortie HDR identique attendue | faible |
| 6 | Deux tickets en vol dans le lecteur | `capacity=2` côté `vf_animejanai-pipeline.patch`, double buffer des sorties | 0,5 à 2 ms de bulle, cadence plus régulière | +1 jeu de sorties en VRAM ; latence +1 paire | faible |
| 7 | Area fusionné dans la préparation RIFE | lire NV12 1080p directement vers RGB FP16 720p paddé, sans intermédiaire YUV16 720p | ≈ 0,5 ms | Area 3:2 déjà spécialisé ; une image par paire seulement | moyen |
| 8 | Supprimer les 16 attentes hôte par paire | remplacer `cuStreamSynchronize` par des événements, une seule attente finale | 0,3 à 1 ms | dépend de 5 pour TrueHDR | faible |

Total plausible : 6 à 12 ms, soit 35 à 40 ms par paire, sous le budget de 41,7 ms avec marge. Sans la décision de la section 2, seuls 5 à 8 restent accessibles (2 à 4 ms) et le budget n'est pas atteint. L'alternative explicite reste la politique Fast (18 ms sans HDR, approximation déclarée).

Ce qu'il ne faut pas faire : FP16 agressif, INT8, modèles « lite », réduction de résolution silencieuse, HDR avant interpolation (AH-333 : les réseaux ne sont pas qualifiés en PQ), ou présenter la somme de micro-gains comme un FPS mesuré.

## 4. Gains de qualité à faible coût

| Piste | Constat | Coût | Rattachement |
|---|---|---|---|
| Matrice couleur de RIFE | `prepare_rife_pair` et `rife_post_picture` imposent BT.709 (`aji_trt.cpp`, « Matrix hardcoded BT.709 like the reference ») alors que la surface transporte `matrix` et que le chemin SPAN l'utilise. Toute source SD 601 (DVD, anciennes séries) est interpolée dans le mauvais espace RGB, puis reconvertie : erreur de teinte sur les intermédiaires, invisible en 709 | nul : utiliser `a->matrix` | AH-275 / MP-01 ; corrige une vraie perte, pas un FPS |
| Dither avant TrueHDR | le SDK reçoit RGBA8 : les sorties 16 bits de SPAN sont tronquées à 8 bits (`pipeline_kernels.cu`, pack) ; banding possible sur les dégradés avant la courbe PQ | un dither ordonné ou bleu dans le kernel pack, ≈ 0,1 ms | MP-09 ; à juger sur une mire, l'anime plate peut préférer sans dither |
| Descale au lieu d'Area | la plupart des séries 1080p sont produites en 720–900p ; un descale avec le bon noyau (bicubic/bilinear) restitue mieux le dessin natif qu'Area avant l'upscale | identique à Area ; nécessite un choix de noyau par profil, pas de détection automatique au premier lot | nouveau sous-ticket d'AH-321 (algorithmes de downscale) |
| SPAN Balanced à ×2 | à ×2 (2 SPAN par paire), Balanced (7,5 ms) coûte 15 ms contre 8 ms : budget 41,7 ms largement respecté avec RIFE (7,9 ms) et HDR (3,5 ms) | aucun ; choix de profil | à exposer par l'estimation de budget du Manager (section 7) |
| Ensemble RIFE | doublerait RIFE (≈ 24 ms de plus) : à refuser dans un profil ×4, acceptable à ×2 | nul | idem |

## 5. Dépôts, binaires et livraison

| Dépôt / source | État lu | Constat |
|---|---|---|
| PLAYER `Ta2b/mpv-AnimeJaNai-HDR` | `hdr-3.8` = `95b1735`, 221 commits depuis le 13 octobre, pack `.git` 154 Mio | les branches `binaries/*` (une trentaine) stockent des `.so`/`.dll` dans Git ; chaque bundle alourdit l'historique. Préférer des assets de release ou LFS, identité par SHA-256 dans un manifeste |
| Checkout IDE (ce dossier) | branche `perf/specialized-gpu-20261014` à `55bbc85`, `release-version.txt` = 3.8.0.31, 10 docs modifiés et ~30 fichiers non suivis | les docs y sont relayées à la main et incohérentes (ETAT-COURANT cite des reçus absents ici ; l'audit du matin n'existe que dans ce checkout). Remplacer par un worktree propre de `hdr-3.8` et y committer les audits |
| Manager `Ta2b/AnimeJaNaiManager-HDR` | `714d48e` sur une branche de lot ; `origin/HEAD` → `main` ; CLAUDE.md déclare `hdr-settings-0.8` comme branche active ; ~30 branches `perf-specialized-*` | la source livrée n'est sur aucune branche de référence. Fusionner les pins livrés dans une seule ligne (tag par release), sinon le pin devient introuvable |
| Backend privé `animejanai-inference-rtx` | `118c272` livré, présent seulement sur `fix-legacy-quality-forwarding-20261017` ; `origin/HEAD` → `perf-specialized-lot58-engines-20261017` | même risque ; les binaires Linux sont compilés **localement** dans un Docker (`GPU-SOURCE.json`), Windows par CI. Faire produire Linux par la même image en CI pour une provenance vérifiable |
| mpv | pas de fork : `the-database/mpv@19c0fcf` + 9 patches appliqués à la compilation (`installer/linux/build-native.sh`) ; worktrees `mpv-hdr-stage-20261017` (12 fichiers modifiés) et `mpv-build-src` (7) non committés | la pile de patches est fragile (ordre, rejets) et les vraies sources vivent dans des worktrees sales. Créer un fork `Ta2b/mpv` branche `hdr-3.8` avec les patches en commits, épinglé par SHA |
| Bundle GPU `dc53e6c` | `GPU-SOURCE.json` par plateforme, hashes et features ; Windows DML/TRT `d5b3446`, Linux `463a0c7`→ modules `118c272/9d2c717/3447cd8` | bon modèle de provenance ; le manifeste ne couvre pas le Windows AMD réutilisé (« not-reused-in-this-bundle ») |
| Installation utilisateur | `version.txt` 3.8.0.104 (deux releases de retard), `libaji_trt_rtx.so` **régulier du 14 octobre** (`200ea558…`) toujours présent à côté des liens vers l'AppImage, plus trois `.bak` | reproduit sur la machine réelle le défaut A1/AH-330 : la route TrueHDR héritée (`stage_wanted` dans `linux-playback.lua`) sélectionnerait ce fichier périmé. La chaîne ordonnée charge le bon `libaji_trt.so`, donc les mesures Quality actuelles sont crédibles |
| Cadence de livraison | 33 reçus de release datés du 17 octobre, 6 le 16 | l'updater de chaque utilisateur est sollicité jusqu'à trente fois par jour, souvent sans changement moteur. Regrouper (une release par jour au plus) et distinguer un canal « essai » d'un canal « stable » |

Points de dette sans urgence : `MainWindowViewModel.cs` (1 995 lignes, modèle et vue mêlés), `MainWindow.axaml.cs` (690 lignes de code-behind pour import/export/benchmark), `Program.cs` de l'updater (2 072 lignes), quatre analyseurs du même profil (C filtre, Lua, C#, C++ backend, plus `AppRun`).

## 6. Jira

État vivant lu le 17 octobre au soir : **369 tickets**, 98 Done, 53 In Progress (47 hors epics), 218 To Do ; 228 tickets en Highest ou High, soit 62 % ; 51 tickets résolus et 237 mis à jour dans la seule journée du 17. Snapshot du matin pour comparaison : 333 tickets, 56 Done, 47 In Progress, 230 To Do ; décisions d'audit 162 conserver, 93 reformuler, 21 regrouper, 50 différer, 6 vérifier clôture, 1 retirer. Depuis : 36 tickets créés (AH-334 à AH-369), 31 d'entre eux Done.

Ce qui compte pour l'objectif de l'utilisateur, statuts vivants :

| Ticket | Statut vivant | Avis |
|---|---|---|
| AH-330 provenance du module chargé | **In Progress, Medium**, passé In Progress le 17 à 11 h 32 ; la description dit encore « travail planifié, non commencé », aucune livraison | à finir en premier : le défaut est vivant sur la machine de l'utilisateur (section 5) ; sans lui une mesure peut tester un autre moteur |
| AH-329 / AH-208 / AH-73 / AH-76 Quality ×4 | In Progress, priorités Medium / Medium / **Low** / Medium | l'objectif principal de l'utilisateur est porté par quatre tickets Medium ou Low alors que 228 tickets sont High ou Highest ; regrouper sous un seul lot « budget Quality ×4 » avec le critère de la section 2 comme première étape, puis les lignes 1 à 8 de la section 3 dans cet ordre |
| AH-368 burst stage-major | In Progress, Medium, prototype non qualifié | à suspendre : il réordonne des appels sans réduire le calcul ; gain attendu ≤ 1 ms, concurrent de la ligne 6 |
| AH-357 / AH-358 | Done par rejet (Low / High) | rouvrir seulement après la décision du critère ; leurs patches de recherche sont conservés |
| AH-275 / AH-15 couleur | To Do High / In Progress Highest | la matrice RIFE (section 4) en est la partie concrète, livrable en une journée |
| AH-333 HDR avant interpolation | To Do, Medium | maintenir différé : pas sans perte |
| AH-336 / AH-337 transaction et identité des packs | To Do, High | utiles mais sans effet FPS ; après AH-330 |
| AH-367 qualification GPU Windows | To Do, Medium | bloqué par le matériel ; ne pas le compter comme travail en cours |
| AH-154 NVIDIA FRUC | **In Progress, High** alors que FRUC est retiré du produit (AH-328 Done) | fermer avec renvoi vers AH-328 ; l'audit du matin l'avait déjà classé « retirer » |
| AH-224 / AH-226 Manager et installation | In Progress, High | nourrir avec la section 7 plutôt que de nouveaux enfants génériques |
| Epics AH-1 à AH-10 | 6 In Progress, 4 To Do | 47 éléments In Progress hors epics pour une personne : limiter à cinq lots réellement ouverts |

Hygiène : les descriptions longues collées dans Jira (jusqu'à 20 Ko, AH-330 en est un exemple) dupliquent les guides du dépôt ; un lien vers le guide et trois lignes d'état suffisent. 62 % du backlog en Highest/High rend les priorités illisibles : ne garder Highest que pour ce qui bloque l'objectif courant, et remonter les quatre tickets Quality ×4 en conséquence.

Tickets créés le 17 au soir à partir de ces propositions : AH-370 à AH-394 ; détail et correspondance dans [le programme d’amélioration](PROGRAMME-AMELIORATION-2026-10.md).

## 7. Manager : interface et expérience

Captures réelles de `714d48e` : [profils large](audit-20261017/manager-ui-3.8.0.106/profiles-wide.png), [profils étroit](audit-20261017/manager-ui-3.8.0.106/profiles-narrow.png), [moteurs](audit-20261017/manager-ui-3.8.0.106/engines-narrow.png), [réglages](audit-20261017/manager-ui-3.8.0.106/settings-narrow.png), [préparation](audit-20261017/manager-ui-3.8.0.106/preparation-wide.png). La fixture n'a aucun moteur installé : les mentions « Unavailable » et « Missing reader » montrent les messages d'erreur réels, pas l'état d'une installation complète.

Ce qui est bon : navigation stable à quatre pages ; liste des étapes dans l'ordre d'exécution avec activation, résumé et réordonnancement ; détail de l'étape sélectionnée ; conditions d'activation repliées ; sauvegarde automatique annoncée ; disposition étroite correcte (sélecteur de profil, icônes) ; page Préparer en trois étapes numérotées ; page Réglages courte et lisible ; une seule conversion HDR par profil, technologie choisie dans l'étape.

Défauts, par importance :

1. **Le résultat du profil est invisible sans défiler.** « Source → Downscale ≤720p → RIFE quality ×2 → SPAN → Display » et « 24 → 48 fps » sont en bas de l'éditeur. C'est la seule phrase qui dit à l'utilisateur ce qui va se passer ; la placer sous le nom du profil, avec résolution de sortie et cadence calculées.
2. **Aucune notion de coût.** Le Manager connaît le GPU (`ComponentManager.GpuText`), la page Diagnostics sait lancer des benchmarks, le banc a déjà les temps par réseau et par résolution. Afficher « ≈ 46 ms par image source, budget 42 ms à 24 i/s : ce profil ne tiendra pas la cadence sur cette carte » transformerait la section 3 en décision utilisateur (×2 au lieu de ×4, Performance au lieu de Balanced, Fast au lieu de Quality). C'est l'amélioration la plus utile pour l'objectif « performances maximales ».
3. **État contradictoire d'une étape** : case cochée et libellé « Unavailable » côte à côte (captures). Trois états distincts sont nécessaires : active, inactive, bloquée (avec cause et action). Les causes sont aujourd'hui des noms de fichiers concaténés sans séparateur (« Missing reader: libaji_trt.so Missing runtime: libnvinfer.so.11 … », `ProfileResolver` joint par espace) ; l'utilisateur doit lire « Moteur TensorRT non installé » et un bouton « Installer ».
4. **Nouvelle étape créée inactive**, à configurer puis cocher ; deux gestes là où un suffit, et c'est la zone du bug AH-369. Créer l'étape active avec une technologie par défaut disponible, inactive seulement si rien n'est exécutable.
5. **Vocabulaire instable** : rule/chain, step/stage, reader/engine/technology/backend, « Playback engine » pour le backend d'inférence, « Processing rule 1 » alors qu'une règle est surtout une condition de résolution/cadence. Fixer un lexique : profil → règle (condition) → étapes (traitement) → technologie.
6. **Langue** : interface entièrement en anglais, messages OSD du lecteur en français (« Profil Linux 3 vide », « Chaine non prise en charge… »), README en français. Pas de localisation (`.resx` absent). Choisir une langue par défaut et traduire l'autre ; au minimum harmoniser lecteur et Manager.
7. **Facteur RIFE saisi en fraction** (deux champs texte × num / den) alors que les cas utiles sont ×2, ×3, ×4 et « suivre l'écran » ; le lien avec « Match enabled RIFE profiles to display refresh » (page Réglages) n'apparaît pas dans l'étape. Proposer des préréglages et un rappel de la cadence écran.
8. **Modèle en zone de texte libre** (`FAComboBox` éditable pour RIFE et SPAN) : une faute de frappe crée un profil cassé sans message immédiat. Liste fermée des modèles présents, plus « importer un modèle ».
9. **Page Moteurs trop technique pour un premier lancement** : options TensorRT (forme d'entrée, niveau d'optimisation, arguments libres), chemins Python/sources/poids GMFSS et FFmpeg visibles d'emblée ; message « AnimeJaNaiUpdater.exe not found » affiché tel quel sur Linux (`ComponentManagerViewModel.cs:141`). Replier tout l'expert, distinguer « installer les composants recommandés » (un bouton) de « réglages avancés ».
10. **Bandeau d'état permanent** répété sur chaque page (« TensorRT unavailable… ») sans action : le rendre contextuel (une fois, avec bouton) ou le supprimer quand une action existe déjà dans la page.
11. Détails : « Startup profile · click to turn off » comme libellé de bouton ; « Profile actions » cache Dupliquer/Importer/Exporter/Supprimer ; les flèches ↑↓ sans glisser-déposer ; aucune confirmation visuelle de sauvegarde (le bandeau le dit en petit) ; « lossless-rgb » comme nom de format dans Préparer.

Architecture d'information proposée pour la page Profils : en-tête (nom, étoile démarrage, actions), **résumé calculé** (chaîne, résolution, cadence, coût estimé et verdict), liste des étapes avec trois états et une action par cause, détail de l'étape avec les réglages essentiels d'abord et « avancé » replié, règles d'activation en bas. Conserver Avalonia, le modèle et les tests headless existants ; c'est une réorganisation de vues, pas une refonte.

## 8. Documentation et processus

- 288 fichiers, 2,2 Mo et ~141 000 mots dans `docs/` du PLAYER, 76 rapports de qualification, 30 guides de reprise. La majorité est écrite pour des sessions IA, pas pour un lecteur humain : ETAT-COURANT et AGENTS.md sont denses, avec des jetons collés (« Source714d48e… », « AH369 Done ») issus d'un nettoyage d'espaces. Un humain ne peut pas s'y repérer en cinq minutes.
- Garder deux niveaux : un **STATUS d'une page** (version livrée, pins, trois priorités, un lien par preuve) écrit pour un humain, et les reçus/guides datés comme archives. Archiver les lots clos dans `docs/archive/` au lieu de les lister dans ETAT-COURANT.
- Le protocole de validation est juste ; ce qui manque est un **jeu de référence fixe** (trois paires privées, un profil, un script) réutilisé par toutes les études de performance, pour que deux lots soient comparables sans réexpliquer la sonde.

## 9. Feuille de route proposée

1. **Fidélité d'abord, une journée** : AH-330 sur l'installation réelle (retirer ou renommer le `libaji_trt_rtx.so` périmé avec reçu, diagnostic du module chargé) ; matrice couleur RIFE ; décision écrite du critère d'équivalence Quality (section 2) avec son script de mesure contre FP32.
2. **Budget Quality ×4, un lot borné** : TrueHDR sur stream + attentes (lignes 5 et 8), deux tickets en vol (6), puis SPAN batch 4 (1) et encodeur partagé (2) sous le nouveau critère, mesure avant/après sur le jeu de référence, livraison des seuls modules modifiés. Objectif : ≤ 41 ms par paire sur la chaîne de l'utilisateur.
3. **Manager, un lot UX** : résumé et coût estimé en tête de profil, trois états d'étape avec action, étapes créées actives, lexique et langue, Moteurs simplifié. Contrôles headless existants adaptés, aucune mesure vidéo.
4. **Processus** : fork mpv, binaires hors Git, une release par jour, STATUS humain, cinq lots ouverts au plus.

Les gains chiffrés de ce document sont des estimations issues des traces et du banc existants ; aucun FPS nouveau n'a été mesuré ici.
