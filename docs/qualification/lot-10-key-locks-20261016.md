# Lot 10 — coordination par clé des builders Linux

Base player `94d1cc7c0b07b0e91f1e4db79883ed59548ab20b` / 3.8.0.40. Backend référence `3f6f60fa58b5ed649bb94c11030d8e354a6d3fc0`, candidat `62c1c5a7cdc5ae65e77f9e511913aa1e59e95972`. Modèles, références Quality et worktree utilisateur préservés. Le périmètre de ce lot est entièrement Linux flow RIFE/TensorRT ; autres formats et plateformes restent distincts.

## Changement

Verrou interprocessus par clé, avec propriété détenue par le noyau et fichier stable. Le fichier n’est pas supprimé : unlink/recreate permettrait de verrouiller deux inodes différents pour la même clé. Le handle n’est pas hérité lors d’exec. Les clés indépendantes ont des verrous indépendants.

Le flow partagé revalide l’export après acquisition, avant transformation. TensorRT tient le verrou pendant le sous-processus et la publication ; un concurrent réutilise l’artefact publié puis le désérialise dans son propre contexte. Les octets rejetés par un consommateur sont fingerprintés : ils doivent être reconstruits ; la nouvelle version publiée par un pair est réutilisée. Un builder échoué conserve l’ancien artefact et retire son propre staging. L’export ONNX motion de Fast est coordonné lui aussi.

Le teardown d’un contexte asynchrone annule son attente de verrou. La vérification avant lancement et après publication du handle enfant ferme la fenêtre où le teardown pourrait manquer le processus lancé. Pas de changement arithmétique, de modèle ou de politique Quality/Fast.

## Essais nécessaires et résultats

Même Linux/RTX4070Ti/TRT11.3, pilote 615.78.08, mêmes fichiers SPAN et RIFE4.26. Entrée NV12 anime 128×72, SPAN 2×, configuration Quality sans RIFE pour isoler le builder ; builder optimisation 0/workspace 64 MiB. Les comparaisons numériques emploient le **même plan**, car deux reconstructions indépendantes ne garantissent pas le même arrondi (preuve antérieure conservée).

| Question | Essai court | Résultat |
|---|---|---|
| Travail flow dupliqué | Deux processus, source RIFE réelle ; observation inotify des stagings | **2 → 1** stagings créés, mêmes octets ONNX, deux consommateurs réussissent ; 0,3189 / 0,3219 s |
| Travail TensorRT dupliqué | Deux contextes/processus libérés ensemble, cache vide, trtexec réel compté par wrapper | **2 → 1** builders effectifs ; deux consommateurs du candidat exacts ; 2,9682 / 2,5172 s pour les deux processus |
| Fidélité backend | Consommateurs chauds avant/après avec le plan gagnant identique | **0 octet changé** ; configure 0,0323 / 0,0429 s |
| Échec puis attente | Premier sous-processus arrêté avec code 1, second déjà en attente, puis vrai trtexec | Premier retourne erreur, verrou libéré, second construit et infère correctement |
| Fermeture pendant attente | Verrou détenu par un autre processus, contexte async en attente, destruction demandée | Attente annulée en **0,0150 s**, aucun builder lancé ni staging restant ; producteur suivant réussit |
| Export motion natif | Deux configurations Fast simultanées ; plans chauds, export motion absent | Deux configurations Fast actives, export exact/complet, sorties SPAN identiques, aucun builder nécessaire |
| Cache invalide et concurrence | Deux consommateurs d’un plan volontairement corrompu | **Un seul** vrai builder répare, deux consommateurs réussissent avec sorties exactes |

Réduction de travail établie, sans extrapolation de FPS ni statistique de latence. Le coût du hash de validation au chargement du plan est ponctuel ; la mesure chaude courte ci-dessus ne prouve pas un gain. Les temps de compilation sont séparés des essais. La première tentative du pilote flow a refusé un chemin de fixture (nom de dossier identique au binaire) avant export ; corrigée et exclue, aucun résultat d’inférence inventé. Les cas concluants n’ont pas été rejoués.

Pilotes `tests/cache/key_lock_check.py SPEC --phase flow|gpu|remaining|motion|repair` et `key_lock_gpu_worker.py`. Artefacts `artifacts/performance/lots-20261016/lot-10/` : specs, commandes/arguments trtexec, logs natifs/contrôleur, compteurs, JSON et NPY. Les deux CLI flow compilent avec `g++ -std=c++17 -O2 -Wall -Wextra -Werror tests/cache/rife_flow_cli.cpp native/linux-ort/rife_flow_cache.cpp native/linux-ort/onnx_flow.cpp -o CLI`.

## Décision et livraison

Conserver : les demandes concurrentes coûtent un seul producteur, les chemins échec/annulation/revalidation aboutissent et le résultat numérique reste exact avec les mêmes plans. Ce lot ne certifie pas l’arrêt brutal du processus, le nettoyage de stagings orphelins, les quotas, .mlmodelc/providers ou le matériel Windows. Ces périmètres restent ouverts explicitement.

Linux multi-SM 75/80/86/89/90/100/120 + PTX120 compilé ; Windows compilation/linking en arrière-plan. Publication prévue **3.8.0.41** ; pin et preuves de publication complétés lors de la livraison, sans attente inactive des builds.
