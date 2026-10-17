# Lot 04 — AH-30 / CAC-03, 15 octobre 2026

Version prévue : **3.8.0.35**, parent `52f440f`. Sources isolées ; backend d’origine, modèles et pins inchangés. Portée : `load_rife` du moteur partagé Linux/macOS ; les engines GPU Windows sont un chemin distinct, non changé.

## Changement

La clé comprend les octets du graphe capturé, SHA-256 de toutes les ressources externes déclarées et version `rife-flow-outputs-v2`. Le lecteur de métadonnées suit le schéma [ONNX 1.19.1](https://github.com/onnx/onnx/blob/v1.19.1/onnx/onnx.proto), sous-graphes, attributs tensors, initializers creux et fonctions inclus. La copie garde les chemins relatifs des poids et contrôle son identité. Un chemin absolu/échappant au dossier ou métadonnées tronquées est refusé plutôt qu’omis. Le repli RIFE existant demeure disponible si l’export échoue.

La fonction séparée `cached_rife_flow` contrôle le checksum du graphe exporté et des ressources copiées. Un hit ne réécrit pas. Un miss produit un dossier unique, contrôle/ferme les écritures puis le renomme atomiquement. Deux builders peuvent produire la même clé : un résultat complet est retenu. Un ancien cache invalide est préservé en quarantaine ; les anciens NAME.flow.onnx ne sont ni importés ni supprimés. Le cache compilé du provider reçoit aussi le sous-dossier de l’identité source, pour ne pas partager le nom générique `rife.flow` entre sources.

## Essais et résultat

`tests/cache/rife_flow_check.py` compile les sources C++17 réelles avec warnings en erreurs et crée des graphes/poids via ONNX. Modification de poids mêmes nom/taille/mtime et modification de graphe : nouvelle clé. Initializers et poids copiés identiques. Cache altéré détecté/préservé/reconstruit, hit sans réécriture, deux processus simultanés rendent la même sortie complète. Poids de sous-graphes/tensors creux/fonctions détectés ; poids manquant, chemin non sûr et protobuf tronqué refusés. Tous concluants, essais non prolongés.

`tests/cache/rife_flow_inference.py` charge les bibliothèques avant (lot 03) et après dans deux processus, même machine, même paire réelle du clip anime (128x72), SPAN et RIFE4.26 (`fd6b06538898c9a94d20f0fe55febceadbcde5ad64952240733b7275ef4c9d59`), Fast x4 sans retiming ni reuse approximatif. Trois instants 1/4, 1/2, 3/4 : **zéro octet de sortie différent**, même export flow octet pour octet, voie motion réellement active. Coût de configuration observé une fois : 217,8029 ms -> 363,0445 ms. Appels 6,392/0,148/0,107 ms avant, 5,619/0,169/0,111 ms après : ces échantillons ne qualifient aucun gain FPS. Build/link `aji_ort` Linux réussi. L’isolation additionnelle du cache compilé a été revue et compilée ; ce paramètre n’est pas consommé par le provider CPU testé.

Artefacts locaux : `artifacts/performance/lots-20261015/lot-04/{contract,inference,build.log}` du worktree utilisateur. Utile comme correction de fidélité des poids et du cache ; pas une accélération. Les modèles et la référence Quality restent identiques ; aucune régression numérique constatée sur le cas CPU ciblé.

## Limites et décision

CAC-03 : critères d’identité/export, poids et lectures/écritures couverts ; prêt pour Done après publication qualifiée du lot et consignation Jira. Cela ne valide pas une vitesse GPU ni l’identité générale des caches compilés, options/runtime/GPU : AH-28 reste ouvert. Transaction limitée à ces exports : pas de locks/quota/arrêt brutal qualifiés pour tous les caches (CAC-05 reste ouvert). API Apple/AMD/Intel absentes localement : qualification GPU partielle, aucune conclusion inventée. Le remplacement atomique est qualifié sur Linux ; les builds macOS restent à suivre.

Connecteur Jira absent : In Progress de début et commentaire préparés, pas appliqués. Ne jamais annoncer le ticket Done avant synchronisation réelle. Les releases .33 et .34 ont terminé leurs trois workflows avec succès pendant ce lot (.33 : 15 assets, .34 : 16 assets uploaded). La release suivante pourra commencer pendant les builds .35.
