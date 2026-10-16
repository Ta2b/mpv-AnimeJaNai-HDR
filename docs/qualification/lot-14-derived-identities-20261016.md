# Lot 14 — identités motion et métadonnées temporelles, non livré

AH-242 reste **In Progress**. Source backend isolée `66cd7d120c2520a9793c40f5d6faed1153fabab6`, Windows compile/link success 38840752269, Linux multi-SM construit et testé. Cette branche n’est pas incluse dans .45/.46/.47 ni dans le lot 17 ; aucun pin livré ne la référence. Ce rapport est un checkpoint de qualification, pas une clôture.

## Résultats établis

- Motion : le même modèle RIFE figé complet fournit le moteur picture et l’export motion. Recette `rife-motion-outputs` v1 dans le contrat partagé v3 ; validation du graphe et de tous les poids externes. Graphe généré identique à l’ancienne transformation, **0 octet différent**, SHA `8236d3e6681f3576ec78becb771e209cc3c67bf8ea99ebbcd513a96ec40d5781`. Hit warm sans réécriture. Modification de poids externes sous les mêmes nom/taille/mtime : identité et export changent, ancien snapshot intact.
- Classification temporelle : le graphe et ses poids sont figés **avant** la lecture du rang/type/fenêtre ; même snapshot fourni au builder. Remplacement T3→T5 à taille/mtime identiques : référence échoue (-5), candidat actif (1), rayon 2 ; sortie identique au contexte frais/même plan, **0 octet différent**. Remplacement fp32 sous taille/mtime identiques : refus explicite avant builder. Réseau rank-5 synthétique déclaré, sans qualification visuelle d’un modèle anime temporel.
- Modèle temporel entièrement statique : référence échoue (-5, profils explicites interdits par TRT11), candidat actif (1), rayon 1 et inférence réelle. Suppression limitée aux placeholders automatiques de profils ; options utilisateur restantes conservées.
- Fast motion natif : même SPAN/picture et même plan motion contrôlé, référence/candidat **0 octet différent**, cache/frais exact au sein de chaque contexte. Un seul véritable builder motion neuf, puis aucun nouveau builder pour les contrôles.

Utilité distincte des FPS : intégrité des dérivés et classification du programme réellement compilé ; aucune modification de l’algorithme ONNX, des modèles ni de Quality. Temps uniques de configure Fast : référence warm 0,6588 s ; candidat cold avec nouveau plan 14,2614 s ; candidat warm même plan 0,6296 s. Pas de gain FPS, ni accélération warm établie.

## Question de qualité non résolue

Le plan motion reconstruit indépendamment change **17 372 octets**, delta max **38/255**, sur une sortie NV12 256×144. Luma : 14 264 octets, moyenne absolue 0,8617, p99=9, PSNR 41,78 dB. Chroma : 3 108 octets, max5, moyenne0,1833, PSNR54,78 dB. Ces métriques mesurent une différence, pas une qualité perceptuelle garantie. Inspection du seul couple PNG : pas de dégradation manifeste à cette résolution, insuffisant pour conclure sur les contours/instants d’une séquence.

Contrôle complémentaire précisément motivé : nouveau plan sur ancien et nouveau runtime, **0 octet différent**. L’écart est donc isolé aux octets du plan reconstruit ; le graphe exporté et le changement de runtime ne l’expliquent pas. Cela **n’établit pas** l’équivalence numérique/perceptuelle de plans indépendants. Qualification de cette reconstruction **non concluante** ; lot non publié, ticket ouvert.

Premier contrôle complémentaire interrompu par OOM pendant le jeu utilisateur : diagnostic conservé, aucune validation inventée. Après fin du jeu, reprise du seul contrôle manquant avec `/bin/false` comme builder : succès, aucun builder supplémentaire. Une tentative SPAN échouée pendant l’OOM figure séparément dans les appels ; elle ne compte pas comme second builder motion. Les essais CPU/temporal et les cas GPU conclusifs n’ont pas été rejoués. Les fichiers originaux de référence ne sont pas modifiés : seules les copies de fixture ont reçu les plans contrôlés.

## Artefacts et suite

`tests/cache/derived_identity_check.py SPEC --phase motion|temporal|static` ; `motion_identity_cli.cpp`, `derived_gpu_keys.cpp`, `motion_native_check.py SPEC --isolate-rebuild`. Receipts réutilisés par cas. Artefacts dans `artifacts/performance/lots-20261016/lot-14/` : `motion-summary.json`, `temporal-summary.json`, `static-summary.json`, `fast/summary.json`, appels/logs/NPZ/plans indépendants préservés et PNG de comparaison. Jira commentaires 10053, 10055 et 10059.

Ne pas clore AH-242 ni intégrer cette branche tant que la décision de qualité de la migration/reconstruction reste non établie. Les identités de fenêtres à l’exécution sont AH-261, séparées de l’identité des programmes compilés ici. Le lot 17 part du backend livré .44 et n’embarque pas ce lot partiel.
