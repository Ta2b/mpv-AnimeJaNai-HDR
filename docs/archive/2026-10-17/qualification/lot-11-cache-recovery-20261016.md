# Lot 11 — reprise des caches Linux après interruption

Base player `1c0605695e0dea38a9f162795c2b9c52594ed6fb` / 3.8.0.41, backend référence `62c1c5a7cdc5ae65e77f9e511913aa1e59e95972`, candidat `694537a6dada3c0aec11947cdc5a6bda86c2c91b`. Périmètre Linux flow RIFE, snapshots ONNX, plans TensorRT et export motion natif. Modèles, références et worktree utilisateur préservés.

## Contrat

Les nouveaux stagings portent une propriété explicite (version + clé). Sous le verrou de cette clé, ils sont orphelins et peuvent être retirés. Les répertoires inconnus/anciens, autres clés et marqueurs liés par symlink sont préservés. Un marqueur incomplet ou illisible ne prouve pas la propriété. Les données ONNX sont séparées des métadonnées dans `data/`, sans réserver un nouveau nom de poids externe.

TensorRT réserve son staging **après** acquisition du verrou : un waiter ne peut pas perdre ses fichiers. Un cache terminé peut nettoyer ses métadonnées orphelines sans attendre un producteur actif. Les exports motion utilisent aussi un staging à propriété explicite. Linux lance le builder par exec direct avec signal de mort du parent ; la course fork/setup vérifie le PID du parent. Préfixes d’environnement `NAME=value` et `env NAME=value` exercés. Un wait échoué ou un enfant tué ne vaut pas succès.

## Essais courts ciblés

Linux RTX4070Ti/pilote 615.78.08/TRT11.3, mêmes modèles RIFE4.26/SPAN et entrée NV12 anime 128×72. Le shim **de test seulement** interpose une écriture, écrit 64 octets, puis stoppe le processus. Le contrôleur tue exclusivement ses propres fixtures ; aucun hook de pause n’est livré dans les moteurs.

| Cas | Avant / après | Fidélité et protection |
|---|---|---|
| Flow interrompu | 1 / 0 staging orphelin après la demande suivante | Export final exact ; dossiers inconnus/autres clés conservés |
| Snapshot interrompu | 1 / 0 staging orphelin | Graphes finaux exacts, SHA SPAN `72246eded3aab52f8d1a71613c0a1d900734b358d1820b62eb36f1ed376e1cf4` |
| Parent TensorRT tué après écriture partielle | Builder survivant avant / arrêté avec le parent après ; orphan 1 / 0 | Aucun plan partiel publié ; demande suivante réussie |
| Builder seul tué | Erreur `AJI_ERR_ENGINE`, aucun plan ni staging partiel publié | Parent termine proprement |
| Arrêt entre publication et nettoyage | Cache `COMPLETE` conservé ; métadonnées orphelines nettoyées | Recovery non bloquante sous verrou actif ; inconnus préservés |
| Export motion natif interrompu | Demande suivante Fast active, orphan retiré | ONNX motion exact face à .41 |
| Poids externe nommé `.aji-stage-owner` | Flow et snapshot avant/après réussis | Octets du poids et graphes exacts, aucune collision de métadonnées |
| Propriété régulière ou liée | Marqueur régulier accepté, lien refusé | Répertoire utilisateur témoin conservé |

Les reconstructions TensorRT indépendantes de cet essai produisent **0 octet de sortie différent**, bien que les plans aient des SHA différents. Ce résultat local n’annule pas la limite antérieure des reconstructions indépendantes ; aucun essai supplémentaire avec plan partagé n’a été nécessaire ici. Configuration/reconstruction de reprise : **2,9875 / 2,9969 s** ; builder tué : erreur après 2,9250 s. Pas de gain FPS ni de latence statistique revendiqué. Les contrôles CPU de propriété/64 octets ne sont pas chronométrés par cas ; leurs résultats portent sur le fonctionnement et la conservation des fichiers.

Une collision de noms dans le **pilote** (binaire `flow-after` et dossier de cas) a interrompu la première orchestration. Une erreur de chemin lors de sa correction a rejoué une fois le témoin flow déjà concluant ; cette répétition est consignée, sans l’utiliser comme preuve supplémentaire. Checkpoints par cas ajoutés. La revue a ensuite séparé données/métadonnées pour éviter le conflit avec un vrai nom de poids externe : seuls les deux cas candidats flow/snapshot affectés ont été requalifiés ; témoins et contrat de récupération chaude ont été réutilisés. Le cas positif de collision a ensuite établi la conservation du poids. Aucun autre cas concluant n’a été répété.

## Reproduction et décision

Pilote `tests/cache/cache_recovery_check.py SPEC --phase portable|gpu|motion|collision`, shim `tests/cache/interrupt_write.c`, worker ABI9 `key_lock_gpu_worker.py`. Compilation du shim : `gcc -shared -fPIC -Wall -Wextra -Werror tests/cache/interrupt_write.c -ldl -o SHIM`. Les CLI flow et snapshot utilisent les sources de leur révision, C++17/O2/Wall/Wextra/Werror ; le CLI backend comprend les contrôles `ownership`, `published-orphan`, `recover`.

Artefacts `artifacts/performance/lots-20261016/lot-11/` : specs par processus avec commandes/préfixes, logs, marqueurs de checkpoint et fichiers partiels, JSON, NPY et versions du contrôle portable. Le layout final est documenté dans `portable-summary.json`; `portable-summary-pre-layout.json` conserve les observations précédentes. La comparaison GPU indique explicitement `independent_rebuild_exact`, sans inventer de comparaison à plan partagé.

Conserver : reprise sûre, aucun import partiel, suppression des orphelins dont la propriété est prouvée, arrêt du builder au décès du parent et références intactes. Les anciens temporaires sans preuve sont délibérément conservés. Les API Windows/Apple/providers et le traitement disque/quota restent des périmètres distincts ; aucune qualification de ces API, HDR physique ou épisode prolongé déduite de Linux.

Binaire Linux final multi-SM chargé avec le même plan de référence et un snapshot source créé selon le layout final : **0 octet de sortie changé**, 24 exports ABI conservés. SHA-256 `2279177a0854aa26dd98682b2058fb52e5fed8716ef426bc1143d762f64b4bad`. Windows NVIDIA/AMD build `38827967813` success, compilation/linking seulement. Pin `171220010f12298da39acead5269ad439d709bcc`. Publication **3.8.0.42** lancée ; état des assets suivi dans Jira pendant le lot suivant, sans attente inactive.
