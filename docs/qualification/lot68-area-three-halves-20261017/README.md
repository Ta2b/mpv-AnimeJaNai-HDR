# AH-360 — Area 3:2 exact

Le profil 1080→720 utilise une réduction 3:2 sur les deux axes. Dans ce cas, chaque pixel de destination couvre deux pixels par axe, de poids `(2,1)/3` ou `(1,2)/3` suivant sa parité. Le kernel calcule désormais la somme entière des quatre valeurs, puis `(somme+4)/9`. Le maximum est `9*65535=589815`, sans débordement uint32. La garde des dimensions utilise des produits 64 bits.

La référence utilisait des poids demi-entiers, des produits quarts et une aire 2,25 exactement représentables en double. Le quotient a un dénominateur 9 : aucune valeur ne peut tomber exactement à une demi-unité. L'arrondi entier est donc identique, sans approximation. Tous les autres rapports gardent le corps générique inchangé. Les coordonnées incluent les mêmes crops et strides ; pas de nouvelle conversion, de modèle, de tampon, d'ordre ou de synchronisation.

Un seul contrôle natif avant/après, Linux RTX4070Ti / CUDA13.4 : mêmes plans YUV444P16 1920×1080 vers1280×720, tirage déterministe contenant les65536codes16bits et blocs0/65535. Les **2 764 800 valeurs de sortie sont exactes**, ancien kernel/candidat/oracle entier. Padding et descripteurs inchangés, propriétaires équilibrés, aucun appel neuronal ou copie pixelsCPU. Arrêt après cette conclusion ; aucun essai de géométrie, de no-op ou de chaîne déjà concluant n'est répété. [Reçu](receipt.json).

SHA256 commun de sortie : `8909fb2f351eb3143b2a010af2254a1bcd238717c484fc6ed2b7785ac7d2fb7f`. Kernel avant `1d9ca93cd2cc5e4ce5e944a5179d21687e7c9ab853f360f02bbfd96d19ca5b5d`, après `3b8bd6716b3ccbc8b79d7a2de7d283f480b2ae914717c5af4ff6c50d212622d9`. Pipeline reconstruit identique : `9432437367c4a94488940e9c305d9a31782b7ccabe8287c6dda73dc76bee7bf0`. TRT inchangé. Backend `3447cd8dc1e6649cf9e8e75656c951ebc91f4d5d`.

Bénéfice établi statiquement sur le cas3:2 : coordonnées d'empreinte, boucles d'intersection, accumulations/divisions FP64 et arrondi générique retirés. Accès pixels et résultat conservés. **Aucun gain FPS mesuré**, et cette simplification seule ne résout pas la marge de débit Quality×4 encore manquante. Hors3:2, seul le test uniforme de sélection est ajouté ; aucun bénéfice revendiqué pour ces géométries.

Compilation portable CUDA SM75/80/86/89/90/100/120 avec PTX de repli ; pipelineGLIBC2.38 / GLIBCXX3.4.30, sans RPATH local, TrueHDR conservé. La compilation multi-SM n'est pas une qualification des autres GPUs. Ni Windows ni AMD/Intel/macOS ne reçoivent ici un chemin qui n'existe pas dans leur moteur.

Reproduction : `tests/inference/area_ratio32_probe.py SPEC.json`, chemins explicites `library`, `trt`, `reference_kernel`, `candidate_kernel`, `output` (dossier neuf). Aucun média privé ni compilation de modèle. La validation GPU est terminée ; prochaine action : livrer le bundle avec provenance par module, puis vérifier le fatbin réellement empaqueté avant Done.
