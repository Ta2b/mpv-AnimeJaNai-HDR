# Lot 22 — spécialisation des formes connues ORT CPU

AH-266 sous AH-64 ; reste natif/rank-5 AH-267. Base .53 `c153b17657d0d9416607a170ed579c928f27992e`, source moteur `75879262488bbd4e3b7ab8e5730014b090b991d0`. Worktree isolé ; sources utilisateur player/backend/Manager préservées. ORT CPU1.24.1, mêmes entrées/options/poids/machine, ablation `AJI_ORT_SPECIALIZE_SHAPES=0/1` dans le même binaire ; bindings du lot21 activés dans les deux branches.

## Manque corrigé et décision

SPAN expose `[1,3,height,width]`, déjà fixé par overrides nommés. RIFE4.26 livré expose `[1,11,-1,-1]` sans noms : ces overrides le laissaient dynamique. Le moteur prépare désormais le seul input rank-4 connu par son contrat, **par axe**, avant CreateSession : batch1, canaux3 ou11, taille spatiale ou paddée. Il découvre la métadonnée ONNX et refuse les dimensions fixes incompatibles ou un symbole réutilisé pour deux valeurs connues contradictoires.

Seule la métadonnée de forme d’entrée change dans une copie mémoire. Les nœuds, poids, sorties, noms et autres champs du modèle conservent leurs octets ; les dénotations de dimension sont conservées. Les poids externes sont résolus relativement au dossier absolu du modèle original via l’option officielle ORT, sans réécrire le modèle installé ni produire un cache de graphe supplémentaire. La copie mémoire est chargée synchroniquement puis libérée. Préparation et copies temporaires ajoutent un coût potentiel au configure ; aucune baisse RAM/démarrage revendiquée.

**Utilité retenue : contrat statique complet réellement transmis au compilateur**, prérequis pour préparation/mémoire/providers à forme fixe. Ce n’est pas une accélération CPU démontrée : le nombre de nœuds ne diminue pas et les coûts courts ne permettent pas de gain FPS. L’entrée et la sortie RIFE n’ont plus de dimensions libres dans le graphe optimisé. Quality reste identique sur les cas exercés.

Activation par défaut limitée au provider CPU/SDK24+ qualifié. `AJI_ORT_SPECIALIZE_SHAPES=0` conserve la voie précédente ; autres providers, SDK plus anciens, rangs/signatures non pris en charge gardent la voie existante avec overrides nommés. Cette route ne prétend pas ajouter le support rank-5 au moteur partagé qui le refuse déjà. L’option1 permet un essai natif explicite ; qualification des autres moteurs/OS dans AH-267.

## Essais courts et preuves

Build CMake Release/AVX/F16C ; interposeur test C API contre le SDK1.24.1 capture le modèle réellement fourni à CreateSession, le graphe optimisé et les formes exposées par la session créée. Captures au configure, hors fenêtre chaude. Comparaison indépendante des modèles : après restauration de la seule forme d’entrée, modèle complet sérialisé identique ; aucun changement de poids/nœud/sortie.

| Chemin | Forme RIFE réellement compilée avant→après | Dimensions libres I/O du graphe optimisé | Nœuds optimisés | Pixels |
|---|---|---:|---:|---|
| Quality, RIFE+SPAN FP16, 128×72 | `[1,11,-1,-1]`→`[1,11,128,128]` | 4→0 | 483→483 | 8 sorties, 0 octet différent |
| Fast motion + deux exécuteurs/tuiles SPAN, 256×72 | `[1,11,-1,-1]`→`[1,11,128,256]` | 8→0 | 484→484 | 8 sorties, 0 octet différent |

Premier intervalle exclu, puis deux nouvelles paires seulement ; warm-up, endpoints et source après reconfiguration aussi comparés. Le compte des dimensions libres Fast inclut les trois sorties image/flow/mask. SPAN reste entièrement statique et à47 nœuds dans les deux branches. Poids installés identiques à .53 : SPAN SHA256 `72246eded3aab52f8d1a71613c0a1d900734b358d1820b62eb36f1ed376e1cf4`, RIFE `fd6b06538898c9a94d20f0fe55febceadbcde5ad64952240733b7275ef4c9d59`.

Coûts muraux uniques des deux paires : Quality100,11→69,23ms ; Fast128,50→132,69ms. **Gain temporel/FPS non concluant** : série courte, charge bureau/alimentation non contrôlées ; aucun essai prolongé automatiquement. Pas de conclusion sur énergie/chauffe/RAM ni tous les matériels.

Métadonnées : batch/axes portant des noms arbitraires fixés ; champ de dénotation préservé ; modèle déjà fixe inchangé ; géométrie fixe incompatible et symbole contradictoire refusés ; rank-5 et multi-input retournent Unsupported sans transformation ; modèle tronqué rejeté. Fixture FP32 réelle via l’ABI : Add avec biais externe dans `weights/bias.bin`, Resize nearest×2 avec scales inline, répertoire de travail `/tmp`, même contexte64×32→80×48. Oracle indépendant de duplication des pixels exact off/on, padding de stride intact, poids externes inchangés. Deux sources par géométrie, aucune ancienne forme conservée après remplacement des modèles.

### Diagnostics conservés et essais non répétés

- Spike de l’API officielle Model Editor : GetInputTypeInfo restait `[1,11,-1,-1]` après SetGraphInputs/Finalize. Cette voie est écartée ; aucune validation de spécialisation inventée.
- Première assertion de bénéfice « moins de nœuds » démentie par les captures : 483→483. Pixels et formes déjà conclusifs réutilisés, sans relancer le modèle ; seuls les reçus sont enrichis avec le résultat statique réel. La décision conserve un prérequis explicite, sans annoncer une fusion/gain de vitesse.
- Le premier contrôle rank-5 détectait un conflit d’axe avant d’identifier son rang. Correction : rang contrôlé d’abord ; seul ce chemin et les contrôles restants exécutés ensuite. La voie rank-4 et ses sorties acquises sont inchangées ; son binaire de qualification est conservé séparément.
- Le harness réutilisait `fixed.onnx` pour deux fixtures ; le nom du résultat est corrigé en `good-fixed.onnx`. La fixture de poids externes Resize/scales échouait aussi sur la référence ORT avant inférence, car cette version ne lit pas ces scales externes pendant son shape inference. Elle est remplacée uniquement pour l’essai runtime par un biais Add externe et scales inline. Les contrôles de métadonnées déjà passés sont repris depuis leur phase, sans nouveaux essais neuronaux.

Artefacts `artifacts/performance/lots-20261016/lot-22/` : specs/logs/NPZ/stats/reçus Quality/Fast, captures entrée/optimisé/formes, `metadata/summary.json`, diagnostics précédents, builds et binaire rank-4 qualifié conservé. Binaire final SHA256 `dcb1afcb98d550499aed92dded8fa5886af47360be78fce2273c512603eafe30`. Tests : `ort_shapes_check.py quality.spec.json`, `fast.spec.json` ; `ort_shapes_metadata_check.py metadata.spec.json`, reprise ciblée des gardes puis `--external-only`. Compilation syntaxique Python et `git diff --check` réussis.

## Livraison et piste concrète suivante

Release **3.8.0.54**, source partagée Linux/macOS ; pin GPU spécialisé inchangé. AH-266 entièrement implémenté et qualifié Linux CPU, clôture après publication vérifiée. AH-64/AH-267 ouverts ; compilation native ≠ qualification matérielle.

Les captures RIFE montrent51 ReorderInput,52 ReorderOutput et41 Cast (Quality), conservés malgré les formes fixes. C’est une piste, pas encore la preuve d’un goulet : **AH-268** sous le ticket existant AH-70 étudie leur coût réel sur ORT CPU, avec comparaison ciblée du layout/optimisation, pixels et décision de conservation. **AH-269** conserve les layouts des autres moteurs/matériels. Aucun doublon de backlog global créé.
