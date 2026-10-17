# AH357 — raccord natif de l’encodeur partagé : rejet pour Quality

Le nouveau raccord échoue au verrou numérique ; **aucune activation ni binaire candidat livré**. Le module de production reste4c1074ed…, identique à la référence. [Reçu natif](native-rejected.json), [journal de l’arrêt](qualification.log).

## Essai unique

RTX4070Ti, pilote615.78.08, TRT11.3.0.99/CUDA13. Après construction séparée des troisplans, aucun buildGPU pendant l’essai. Les mêmes deux sources privées720p du lot61 sont converties enYUV444P16BT709pleineplage pour l’ABI9 réelle, mêmes plans/policies et buffers pour les trois voies : référence livrée, candidat désactivé, candidat activé.

Candidat désactivé : trois phases.25/.5/.75 exactes à la référence livrée. Candidat activé : dès.25, **1 053 807/2 764 800valeurs uint16 diffèrent, écart maximal88**. Le consommateur a exécuté un encodeur et une tête complète ; le cache était actif,15Mio de features alloués. Pas de confusion avec un chemin pas exercé.

L’essai s’arrête immédiatement : phaseson suivantes, nouvellepaire/reset/legacy et chronométrage ne sont pas exécutés. Aucun gainmesuré ni jugement visuel à extrapoler de cet échec. Les tempsréseauAH356 précédents restent vrais pour leur cas propre ; ils ne qualifient pas ce raccord.

## Travail conservé pour diagnostic ciblé

[ContrôleCPU](converter-receipt.json) : le convertisseur C++ copie exactement opérateurs/poids/IO du découpagePython déjàaudité (encoder11nodes, tête315nodes, cinqwarps conservés). Les protobufs complets diffèrent par métadonnées/ordre de stockage ; la compilation des programmes séparés peut changer tactiques/arrondis, mais la cause précise n’a pas été établie. Ne pas écrire que ce mécanisme est prouvé.

[Patch candidat rejeté](candidate-rejected-backend.patch), basebackend118c272, commitlocal82c8295. Ce patch est une archive de recherche, **ne pas l’appliquer sur une branche de production**. Il contient convertisseur borné au SHA4.26, snapshots atomiques, tête à deux entrées, features parpaire, invalidations et repli. Le fichier `tests/inference/rife_encoder_runtime_check.py` contient le protocole réellement exécuté. Les plans/binaires/entrées détaillés restent privés dans `lot-83-rife-encoder-proof-20261017`, sans toucher l’installation ni les modèles utilisateur.

Toute future reprise doit cibler uniquement la phase.25 qui échoue, après hypothèse concrète : contrôler les bindings/features et localiser la première divergence du réseau complet. Ne pas rejouer les troisphasesoff, l’étudeAH356 ou benchmarker avant exactitude. Aucun seuil de tolérance silencieux dansQuality. Le parentAH73 garde les autres voies de performance ; AH357 se termine par cette décision de rejet, conformément à son critère explicite.
