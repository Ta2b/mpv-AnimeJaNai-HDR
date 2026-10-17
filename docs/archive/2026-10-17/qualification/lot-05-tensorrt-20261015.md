# CAC-04 / AH-31 — identité des engines TensorRT

Source initiale : `1468be6f24cac537407283d434bd5d542d642cf3`. Travail isolé, backend utilisateur intact. Companion player source `735a33d87d228b3b77718b6d918111ed83e476af` épinglée pour les SDKs Windows.

## Implémentation

Le nom compact `aji-v2-SHA256.engine` encode une identité encadrée du graphe, de tous ses poids externes déclarés, des réglages complets (formes/types/precision compris), du runtime TRT, build des headers, CUDA runtime/driver et du vrai device courant (nom, SM majeur/mineur, UUID). Les anciens noms longs/courts ne sont plus acceptés comme preuve de poids et restent sur disque pour retour arrière.

Le builder reçoit une copie contrôlée et stable `model.onnx` avec ses ressources externes aux chemins relatifs, sous `.aji-sources-v2/CONTENT`. Un remplacement du modèle pendant/après l’empreinte ne change pas cette copie. Cache source invalide conservé en quarantaine et reconstruit ; snapshots publiés par rename atomique. La primitive SHA-256 et le lecteur external_data sont synchronisés avec le companion `735a33d` (native/common/content_identity.h et native/linux-ort/onnx_flow.*).

Les engines sont écrits dans un dossier unique puis publiés après succès et fichier non vide. Un builder échoué ne supprime plus l’engine terminé d’un autre builder. Le timing cache est attaché au plan et reste hors des poids gelés. Pas de changement de calcul, de modèle, d’ABI ou de paramètres de précision.

## Essais courts

- `tests/model_identity_check.py` : oracle hashlib indépendant ; poids remplacés mêmes nom/taille/mtime : ancien nom CRC inchangé, nouvelle clé changée. Copie source initiale inchangée, séparation settings/runtime/device, chemins UTF-8, snapshot corrompu préservé/réparé, deux processus simultanés, poids manquant refusé. Publication : builder échoué ou fichier vide préservent un engine complet. Concluant.
- Build/link CUDA/TRT sous l’image locale Ubuntu baseline `aji-rtx-build`, SM89, sans toucher le backend utilisateur. ABI exportée comparée à la référence.
- `tests/engine_cache_gpu.py` : SPAN réel, clip anime trois sources 128x72 NV12, même modèle/settings/machine, Quality spatial/temporel inchangé. Builder réel TensorRT11.3, workspace64M et optimisation0 pour ce test borné. Avant : configuration froide 3,1267 s ; après : 2,7537 s ; hit candidat sans builder 0,0336 s. Ces mesures uniques ne prouvent aucun gain de FPS ni vitesse de construction reproductible.
- Refus effectif de l’engine après remplacement d’un poids sous le même nom : nouveau miss, builder `/bin/false` volontairement échoué, ancien engine complet inchangé. Pas de réutilisation silencieuse des vieux poids.
- Qualité : deux engines indépendamment reconstruits diffèrent sur 10 660 octets des trois sorties, **delta maximal 1/255**. Un seul approfondissement avec exactement le même engine dans les bibliothèques avant/après donne **zéro octet changé** ; le hit du candidat est également identique à son ouverture froide. Pas de preuve d’identité entre reconstructions ni de supériorité perceptuelle. Modèles, référence et anciens engines conservés.

Le premier lancement GPU échouait faute de chemin vers la bibliothèque builder SM89 ; artefacts conservés, hors comparaison. Bibliothèque déjà présente ajoutée au chemin du second essai, sans téléchargement ni changement de Strata. Modèle Strata résident et bureau actifs : ces essais sont fonctionnels/numériques, pas des mesures FPS. Essais concluants non répétés ; l’approfondissement était motivé par la différence des reconstructions.

Artefacts : `artifacts/performance/lots-20261015/lot-05/{contract,gpu,gpu-complete,build,abi.json}` dans le dépôt player utilisateur. Windows : builds NVIDIA/AMD success, run 38801311797, SHA exact d9d0a941d62f1dfcb3ed2f87018c4871aea12be7 ; compilation et linkage, pas d’inférence Windows qualifiée localement. Arrêt brutal, quota et timing-cache concurrent de tous les formats relèvent encore de CAC-05. Aucun gain FPS promis ; conservation pour correction de fidélité des poids.

AH-31 réellement In Progress ; commentaire Jira 10028 publié après rétablissement du connecteur sur le projet AH. Prérequis globaux AH-28/AH-32 partiels, aucun Done prématuré.

Binaires de production Windows/Linux épinglés dans le player par 9eee3504d82387035e4908909ca9621733fed68c. Linux multi-SM 75/80/86/89/90/100/120+PTX, Ubuntu baseline Docker, RPATH portable. Contrôle sur ce binaire empaqueté et même plan TensorRT : hit sans builder, trois sorties avant/après identiques (0 octet), 24 exports aji_ inchangés. SHA libaji_trt.so : 2cef3796af600b752fa0805ca6ff800b6d2ddfe4f42067b60390f1fbdbedac8c. Diagnostic initial du contrôle de packaging : mauvais nom SPAN, modèle non chargé ; exclu, nom corrigé. Le contrôle supplémentaire cible le binaire multi-SM nouvellement construit.

Release 3.8.0.36 : publication demandée après ce commit, état des assets à suivre. Aucun programme installé modifié. Le lot suivant AH-22 démarre sans attendre la fin des builds.
