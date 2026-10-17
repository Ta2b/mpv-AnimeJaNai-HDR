# Lot 23 — décision sur les layouts ORT CPU RIFE

AH-268 sous AH-70 ; autres moteurs/matériels AH-269. Base .54 `5b6331c0ad16a19a5cd0072647777ee9ae8928f8`, source `1e52038995fbf87939abba0181f36cf61fd67346`. Sources utilisateur préservées ; moteur compilé dans un worktree isolé. Même binaire, ORTCPU1.24.1, poids RIFE4.26/SPAN FP16, entrées/options/machine par branche.

## Question et changement livré

Les captures du lot22 montraient51 ReorderInput,52 ReorderOutput et41 Cast sur RIFE Quality ; les comptes seuls n’établissaient pas leur coût. Comparaison ciblée du niveau ORT_ALL3 (NCHWc actif) et ORT_EXTENDED2 pour RIFE seulement, afin d’éviter de modifier aussi SPAN.

Nouveaux overrides de diagnostic par réseau : `AJI_ORT_RIFE_OPT` et `AJI_ORT_SPAN_OPT` ; `AJI_ORT_OPT` reste le fallback global. **Défaut ORT_ALL3 conservé**, aucune nouvelle politique automatique ni modification des poids/précisions/copies/flux par défaut. Utilité fonctionnelle : isoler les choix de compilation et de layout d’un réseau, sans confondre son coût avec l’autre. Quelques lectures d’environnement au configure ; aucun nouveau travail par frame.

## Essai nécessaire et conclusion

`ort_cpu_layout_check.py quality.spec.json`/`ort_cpu_layout_probe.py`, vrais modèles via l’ABI, `AJI_ORT_SPECIALIZE_SHAPES=1`, bindings réutilisés1, global3/SPAN3 dans les deux branches, RIFE3→2. `AJI_RIFE_PROFILE=1` existant relevé par différence de deux snapshots avant/après fenêtre : exactement deux nouvelles inférences RIFE, premier intervalle/warm-up exclu. Captures C API indépendantes des modèles d’entrée, graphes optimisés et formes réellement compilées. Aucun test de lecture/affichage nécessaire à cette question CPU hors écran.

| Coût/structure | RIFE3 (référence) | RIFE2 (candidat) |
|---|---:|---:|
| Nœuds optimisés | 483 | 506 |
| ReorderInput / ReorderOutput | 51 / 52 | 0 / 0 |
| Cast | 41 | 167 |
| Inférence RIFE, total deux runs mesurés | 39,7629ms | 53,3293ms |
| Préparation RIFE, même fenêtre | 0,05486ms | 0,05513ms |
| Sortie RIFE, même fenêtre | 0,11654ms | 0,09377ms |
| Coût mural chaîne, deux paires | 48,7683ms | 60,5413ms |

SPAN reste identique dans toutes les captures, à47 nœuds, même forme, types et opérateurs ; modèle d’entrée RIFE également identique, le seul traitement est son optimiseur. Temps ORT complets RIFE distincts du coût de chaîne ; recouvrement existant conservé, pas d’addition trompeuse des timings.

**Échec d’équivalence des pixels : 4 305 octets changés sur les huit sorties comparées, écart maximal2/255.** Détail : warm-middle1472 octets/max1, middle-2=1760/max2, middle-3=1073/max1. Les cinq endpoints/sources, dont celle après reconfiguration, restent exacts. Aucune évaluation visuelle ni acceptation d’un compromis Quality inventée ; exigence d’équivalence de cette transformation fixée à zéro avant comparaison.

Décision suffisamment établie : **écarter RIFE2 du défaut Quality et conserver RIFE3**. Retirer les reformats n’est pas un bénéfice global quand conversions et coût augmentent, avec une sortie différente. Les temps sont des observations courtes, charge bureau/alimentation non contrôlées ; aucune performance soutenue/universelle ni pourcentage FPS revendiqué. La différence numérique suffit à écarter le défaut, même sans extrapoler les temps. Arrêt après ce cas : aucun nouvel essai Fast, aucun rerun ni prolongement.

La capacité diagnostique par réseau est conservée : le contrôle montre qu’elle change effectivement RIFE et laisse SPAN intact ; l’ancienne option globale et le défaut conservent leur comportement. Ce livrable est une décision de tuning et un contrôle de compilation ciblé, sans annoncer une optimisation retenue.

Artefacts locaux : `artifacts/performance/lots-20261016/lot-23/` : build, specs exactes, logs, NPZ, statistiques/profiling, graphes d’entrée/optimisés/formes et `rife-quality/summary.json`. Modèles/poids identiques à .53/.54, SHA dans les traces. `git diff --check`, syntaxe Python et build réussis. Aucun backend utilisateur d’origine modifié.

## Livraison et nouvelle piste

Release **3.8.0.55** avec overrides diagnostiques et rapport ; Quality garde ORT3. AH-268 complet dans son périmètre décisionnel Linux CPU, Done après publication vérifiée ; parent AH-70/AH-269 ouverts pour les autres moteurs/matériels. Compilation Linux/macOS n’est pas leur qualification universelle.

Le modèle d’entrée contient53 LeakyRelu FP16 ; les noms `_inlfunc_LeakyRelu_*` du graphe optimisé confirment leur expansion en Less/Mul/Where. **AH-270** sous AH-68 étudie une voie native/typée fidèle : préserver alpha, arrondis et transformations de précision ORT, vérifier le coût et la sortie avant tout défaut. **AH-271** conserve les autres activations/épilogues/runtimes. Cette piste n’est encore ni une implémentation ni un gain établi.
