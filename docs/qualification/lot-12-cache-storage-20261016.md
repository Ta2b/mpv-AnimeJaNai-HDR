# Lot 12 — erreurs disque/quota des caches Linux

Base player `01f93fbb746e561f1049a2f1b6a1590c63ca461b` / 3.8.0.42, backend référence `694537a6dada3c0aec11947cdc5a6bda86c2c91b`, candidat `650c2a71f5c8bca8cfa52805e0db1c17dad8aa67`. Périmètre Linux flow/snapshots/plans TensorRT. Modèles et worktree utilisateur préservés ; aucune saturation du disque utilisateur.

## Changement

Diagnostics avec opération, chemin, erreur système et action de récupération. Les erreurs asynchrones sont publiées avant le flag de fin et conservées par clé : pas de boucle automatique de rebuild ; réouvrir le contexte/vidéo permet de réessayer après correction.

Les caches complets sans staging orphelin restent lisibles sans verrou en écriture. Une référence illisible retourne une erreur et n’est pas remplacée. Un builder qui retourne zéro avec un fichier non vide n’est pas suffisant : TensorRT désérialise le nouveau plan avant sa publication atomique. Les contextes d’exécution d’un cache incompatible sont libérés avant les allocations de validation. Un rename refusé ne peut pas valoir succès au seul motif qu’une ancienne référence existe. Si le parent interdit le nettoyage, données/propriété du staging restent disponibles pour la reprise après restauration des permissions.

## Essais ciblés et conclusions

Même Linux, RTX4070Ti/pilote 615.78.08/TRT11.3, RIFE4.26/SPAN inchangés. GPU : entrée NV12 anime 128×72, SPAN 2× Quality, mêmes plans pour les comparaisons de référence. Un second jeu de paramètres textuellement distinct mais effectif équivalent force une nouvelle identité de test, sans changer les poids/opérateurs. Builder optimisation 0/workspace 64 MiB.

| Question | Avant → après | Protection/qualité |
|---|---|---|
| Publication refusée par permissions | Faux succès `true` → erreur `false` avec chemin/cause/action | Référence `REFERENCE` intacte ; propriété conservée puis staging récupéré après permissions rétablies |
| Quota | Injection native **EDQUOT** après écriture réelle de 64 octets | Diagnostic quota exploitable, rollback et nouvelle demande réussis ; graphes/références exacts |
| Permission Unix | Refus réel de création sous répertoire non inscriptible | Diagnostic permission/action, référence intacte, reprise après restauration |
| Flow, vrai disque plein | tmpfs privé **32 MiB**, 256 KiB laissés avant export réel | ENOSPC réel, aucun staging incomplet publié, référence conservée, reprise après libération, graphes exacts |
| Flow complet en lecture seule | Échec de verrou en écriture → cache consommé | Graphes récupérés exacts |
| TensorRT, vrai disque plein | Builder réel dans le même tmpfs privé, échec async puis nouveau contexte après libération | Aucun plan partiel publié ; erreur avec octets disponibles/action ; reprise réussie, référence intacte |
| TensorRT complet en lecture seule | Configure `-5` → `1` | Sortie de référence **0 octet changé** |
| Engine terminé illisible | **1 rebuild non demandé → 0**, erreur permission visible | Inode et SHA de référence conservés après ; permissions rétablies : **0 octet changé** |
| Enfant retournant zéro avec plan tronqué 64 octets | Publication du plan tronqué et **2 appels → aucune publication et 1 appel** | Erreur async latched, `FAILED` et cause visibles ; référence intacte |

Les namespaces user/mount sont privés et disparaissent avec les fixtures. Le vrai ENOSPC n’utilise que le tmpfs de test. EDQUOT est **une injection de retour d’erreur**, pas une prétendue activation de politique de quota sur le filesystem utilisateur.

Temps de processus observés, uniques : refus de lecture de plan 3,3693 / 0,3141 s (avant reconstruit, après signale l’erreur), restauration 0,3645 / 0,3643 s ; cache GPU lecture seule 0,3150 s en échec avant / 0,3642 s avec inférence après ; reprise après libération 3,2691 / 3,1184 s. Les parcours ne font pas le même travail en cas d’erreur ; ces nombres ne sont pas un benchmark FPS. Bénéfice établi par les états, **2→1 / 1→0 builders indus**, références conservées et exactitude avec le même plan.

Le premier pilote space a échoué au remount util-linux (UID hôte rejoué dans un namespace à un seul UID). Les assertions ENOSPC/rollback/reprise déjà passées ont été conservées dans `before-space-assertions.json`, sans rejouer la panne ; leurs hash/durées détaillés n’avaient pas été persistés et ne sont pas inventés. Le contrôle en lecture seule manquant a été exécuté avec remount direct. Journal de chaque appel désormais persistant. Les cas concluants sont arrêtés.

## Reproduction et décision

Pilotes : `tests/cache/disk_errors_check.py SPEC --phase portable` ; `unshare -Urnm … disk_errors_check.py SPEC --phase space` ; `disk_gpu_check.py SPEC --phase host` ; `unshare -Urnm … disk_gpu_check.py SPEC --phase space`. Worker ABI9 `key_lock_gpu_worker.py`, fixture format-agnostique `publication_refusal.cpp`, shim de test `interrupt_write.c` avec errno explicite. Les fixtures sont propres au chantier ; le shim n’est pas chargé par le produit.

Artefacts `artifacts/performance/lots-20261016/lot-12/` : specs/arguments par processus, JSON, NPY, compteurs de sous-processus, diagnostics et journaux. `portable-summary.json`, `space-summary.json`, `gpu-space-summary.json`, `gpu-host-summary.json` sont concluants. Les temps/conditions exacts figurent dans ces reçus ; les lacunes du premier pilote sont explicites.

Conserver : meilleure intégrité de publication, références protégées, caches lecture seule utilisables, erreurs/reprise compréhensibles et pas de rebuild automatique inutile. Aucune modification arithmétique ni de modèle, aucun gain FPS revendiqué. Le contrôle du binaire final et la livraison **3.8.0.43** suivent en arrière-plan. Windows/Apple/providers restent un autre périmètre ; leur compilation ne vaut pas qualification matérielle/native des transactions.
