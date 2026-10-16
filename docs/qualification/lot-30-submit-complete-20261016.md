# Lot 30 — Submit/Complete CPU et durée de vie des surfaces

Ticket [AH-280](https://tatoub.atlassian.net/browse/AH-280), parent AH-50. Extension optionnelle Linux x86-64 CPU/ORT 1.24.1, après le contrat Surface v1 du lot 29. Quality, Fast, modèles et ABI historiques conservés. Les fences et consommateurs GPU restent AH-281/AH-279 ; le lecteur mpv utilise encore son pont historique.

## Comportement livré

`surface_async.h` définit Enable, Submit, Complete, Drain et Disable avec négociation versionnée. Une file de 1 à 64 emplacements possède un worker persistant. Elle prend exclusivement le contexte configuré jusqu'à Disable ; les appels de calcul/configuration historiques sont refusés pendant cette période. Sans activation, aucun worker supplémentaire et comportement historique conservé.

Submit copie les descripteurs et retient chaque owner une seule fois, sans attendre le calcul ou une place libre. La saturation renvoie Busy et ticket zéro sans acquisition. Les buffers restent immuables et alloués jusqu'à complétion ; l'emprunt sans callbacks exige une promesse explicite. Les callbacks doivent être thread-safe, sans exception, réentrée ni attente de cette file. Le worker utilise des copies empruntées sous les références de la file, sans double acquisition.

Les tickets monotones survivent aux désactivations/réactivations du même contexte. Complete est une consultation sans attente : Pending ne permet aucune réutilisation ; Finished, Failed ou Cancelled ne sont publiés qu'après la fin du travail et des libérations. L'erreur différée et son message appartiennent au ticket. Les résultats terminés non consommés occupent toujours un emplacement : ni calcul ni historique de résultats ne peuvent croître sans borne.

Drain est l'opération d'attente explicite, distincte de Submit/Complete. Il peut annuler les travaux non démarrés, laisse finir celui en cours, puis invalide les états dérivés pour un seek. DropResults retire les anciens tickets. Disable et destruction annulent/drainent avant de libérer les modèles. La dernière revue a assuré que le pointeur de file reste stable jusqu'à l'arrêt du worker, avant son reset.

La seule dépendance négociée est le contenu hôte déjà prêt. Une queue externe ou une fence native est refusée explicitement. Les types CUDA/HIP/D3D12/Metal/Vulkan sont représentables dans l'en-tête, sans prétendre être implémentés.

## Essais courts nécessaires

Client C ABI réel [surface_async_check.cpp](../../tests/inference/surface_async_check.cpp), compilé sans NDEBUG. Des barrières contrôlées dans les callbacks établissent Pending jusqu'à libération, saturation sans attente de calcul/acquisition, copie des descripteurs, borne des résultats, consommation, tickets monotones, annulation et destruction sûres. Copie CPU 4×2 exacte, destinations des travaux annulés intactes, acquisitions/libérations équilibrées ; refus des appels concurrents historiques, des entrées invalides, fences et queues externes. Aucun modèle nécessaire à ces contrôles de contrat.

| Calcul réel sur le worker, mêmes entrées/options/modèles/machine que la référence | Référence valide réutilisée | Résultat |
|---|---|---|
| Quality CPU RIFE 4.26 + SPAN, 128×72 | Lot 24 `integrated-quality/after.npz`, `warm-middle` | Une sortie exacte, zéro octet différent |
| Fast CPU, 256×72, SPAN tuilé 2×1, deux exécuteurs | Lot 25 `pruned-fast/after.npz`, `warm-middle` | Une sortie exacte, zéro octet différent |

Les strides et sentinelles de sortie sont préservés ; les trois owners sont acquis une seule fois et les descripteurs originaux restent identiques. Une erreur ORT injectée par contexte vérifie Failed, le message et les références libérées, sans répéter une inférence réussie. Les suites déjà concluantes du lot 29 ne sont pas rejouées.

CMake Release réussi, syntaxe C de l'en-tête et diff-check réussis. Tous les exports précédents sont conservés, six symboles optionnels ajoutés. Artefacts locaux `artifacts/performance/lots-20261016/lot-30/` : `contract.log`, `quality.log`, `fast.log`, deux sorties RGB et résumés JSON, `qualification.json`, journaux de build. Binary SHA-256 : `7573c99fcb6003dd4b5f321637d8ba3c984a479d6259ac5cde821fd085ec15cd`.

Commandes : compiler le client avec `c++ -std=c++17 -O2 -pthread tests/inference/surface_async_check.cpp -I native/common -I native/linux-vulkan -ldl`, puis `CLIENT LIB` pour le contrat ou `CLIENT LIB CONF MODELS RIFE WIDTH DEVICE OUTPUT_RGB` pour une sortie neuronale ; les deux modes neuronaux utilisent la sonde ORT test-only du lot 29 pour l'erreur différée.

## Décision et livraison

Conserver : bénéfice fonctionnel établi pour une soumission sans attente de calcul, un résultat différé explicite et une durée de vie bornée/sûre. Ce prérequis ne revendique aucun gain FPS ni chevauchement GPU. Qualification limitée au Linux CPU disponible ; aucune validation matérielle universelle.

Release prévue **3.8.0.62** avec les pins GPU/Manager inchangés depuis .60. AH-280 reste In Progress jusqu'à publication vérifiée ; parents AH-50/AH-49 et intégrations natives restent ouverts.
