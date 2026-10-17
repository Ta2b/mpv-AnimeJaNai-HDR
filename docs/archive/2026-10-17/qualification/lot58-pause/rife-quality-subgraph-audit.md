# Audit lecture seule — sous-graphe RIFE 4.26 Quality

**Conclusion : l'encodeur des deux images peut être calculé une fois par paire, sans supprimer aucune prédiction Quality. Son poids reste borné : environ 9,10 % des MACs nominaux convolutionnels des trois prédictions de Quality×4 seraient retirés. Aucun gain de temps/FPS n'a été mesuré.** Le batching des trois timesteps est une autre piste, plus intrusive : ce modèle est exporté avec un batch fixé à 1 et plusieurs réarrangements figés pour deux images.

## Référence et méthode

- Modèle demandé, lu sans écriture : `/home/ta2b/.local/share/AnimeJaNai-HDR-linux/animejanai/rife/rife_v4.26.onnx`.
- Taille : 11 391 709 octets ; SHA256 avant/après lecture `fd6b06538898c9a94d20f0fe55febceadbcde5ad64952240733b7275ef4c9d59`.
- Métadonnées : PyTorch 2.2.0, ONNX IR8 / opset16 ; entrée FP16 `[1,11,H,W]`, sortie FP16 `[1,3,H,W]`; 322 nœuds, 158 initializers.
- Sources relues : backend `/tmp/lot-58-backend-20261017`, SHA `61ba62753d0bbaa85734b19e7992be946ba92434` ; les chemins de conversion/modèle cités ne diffèrent pas de la base .84 `36f3d944…`.
- Lecteur CPU : `/home/ta2b/.animejanai-tools/venv-gpu/bin/python`, package ONNX 1.23.2. Aucune importation Torch/CUDA, inférence, compilation, écriture ONNX ni modification de poids. L'inférence de formes ONNX a seulement spécialisé une copie en mémoire à 768×1280. Aucun fichier du lot 59 AH-347 modifié.
- Données détaillées : `/tmp/rife-quality-subgraph-audit-20261017.json`. Les indices de nœud ci-dessous sont indexés à partir de zéro dans le modèle original ; les noms de tenseur servent de repère stable.

## 1. Coupe exacte candidate : sortie de l'encodeur

`/Split` (nœud1) sépare les 11 canaux en `[6,1,2,2]` : RGB A/B, timestep, grille, multiplicateurs. Seul `/Split_output_0` alimente l'encodeur. Son chemin est :

`RGB[1,6,H,W] → /Reshape [2,3,H,W] → /encode/cnn0 → LeakyRelu → cnn1 → LeakyRelu → cnn2 → LeakyRelu → cnn3 ConvTranspose → features[2,4,H,W]`.

Les nœuds5 à11 ne dépendent donc pas de t. La coupe naturelle est **`/encode/cnn3/ConvTranspose_output_0`**, FP16 `[2,4,H,W]`. Deux usages en aval restent intacts : `/Reshape_1_output_0` regroupe les features en `[1,8,H,W]` pour le premier bloc ; `/Concat_output_0` joint RGB/features en `[2,7,H,W]` pour les warps suivants.

Le timestep rejoint les données au nœud15 `/Concat_1`. Les cinq blocs `block0` à `block4`, leurs flots/masques et leurs cinq `GridSample` sont ensuite t-dépendants. Leur calcul doit rester complet à .25, .5 et .75. Aucune réutilisation du flot médian n'appartient à cette piste Quality.

Le cache actuel ne fait pas déjà ce travail : `prepare_rife_pair` et sa promotion conservent les conversions RGB d'entrée (`src/aji_trt.cpp:3741`, `3938`), tandis que `enqueue_rife_picture` rejoue tout le réseau plus la conversion de sortie (`3814`, `3850`). Un graphe CUDA réduit les soumissions CPU ; il réexécute l'encodeur. Le cache de plans TensorRT n'est pas un cache de features de la paire.

## 2. Coût nominal et portée réelle

À **1280×768 paddé** (entrée720p), comptage conventionnel Conv = nombre d'éléments de sortie × poids par filtre ; ConvTranspose = nombre d'éléments d'entrée × poids par canal. Les MACs incluent les termes nominaux aux bords paddés ; biais, activations, Resize, GridSample, copies, conversions et tactiques TensorRT sont exclus. Une MAC compte une multiplication-accumulation, pas deux opérations séparées.

| Sous-graphe | MACs nominaux par prédiction |
|---|---:|
| Encode cnn0, `[2,3,H,W]→[2,16,H/2,W/2]` | 212 336 640 |
| Encode cnn1, 16→16 | 1 132 462 080 |
| Encode cnn2, 16→16 | 1 132 462 080 |
| Encode cnn3 transposée, 16→4 | 503 316 480 |
| **Encodeur total** | **2 980 577 280** |
| block0 | 727 603 200 |
| block1 | 1 367 408 640 |
| block2 | 3 199 795 200 |
| block3 | 6 126 305 280 |
| block4 | 7 439 646 720 |
| **Réseau Conv/ConvTranspose total** | **21 841 336 320** |

L'encodeur représente **13,6465 %** de ce décompte. Quality×4 exécute trois prédictions : 65,524008960 GMAC nominaux. Un encodeur par paire, trois têtes complètes, évite deux encodeurs = **5,961154560 GMAC**, soit **9,0977 %** des MACs des trois réseaux. Les blocs3+4 représentent déjà 62,11 % du total par prédiction et restent t-dépendants. Ce calcul ne fournit ni un pourcentage de temps gagné ni une explication suffisante d'une forte baisse de framerate de la chaîne entière.

Le cache minimal de features coûte **16×H×W octets**, soit **15 Mio à1280×768** et **31,875 Mio à1920×1088**, hors workspace des moteurs. Il convient de commencer par cette seule coupe. Mettre aussi en cache `/Concat_output_0/cast32` ajouterait 52,5 Mio à720p ; le cast des RGB ajoute22,5 Mio. Leur coût d'exécution propre n'est pas établi, TensorRT peut fusionner ces opérations : aucune raison statique suffisante pour grossir le cache maintenant.

Une promotion de features B→A entre paires adjacentes peut encore éviter l'encodage de A. C'est une extension distincte : elle demanderait notamment de traiter un seul nouvel endpoint au lieu du batch2 actuel, donc une nouvelle qualification des tactiques et du cache. Ne pas l'inclure dans le premier essai borné.

## 3. Implémentation proposée, sans changer Quality

Première tranche proposée : **RIFE4.26 non-ensemble, cache par paire, batch des endpoints inchangé à2 ; pas de batching des timesteps et pas de promotion interpaire de features**.

1. Dériver deux programmes depuis le même modèle figé : encodeur produisant le tenseur nommé ci-dessus ; tête prenant l'entrée originale plus ce tenseur. Copier les nœuds/poids/attributs existants et les dtypes, sans réexport PyTorch ni nouvelle conversion globale de précision. Conserver dans la tête tous les raffinements, warps, masques, blend final et sortie RGB complète.
2. Garder le modèle monolithique comme fallback si topologie/type/modèle incompatibles ou si un moteur dérivé manque. Le backend `ModelEngine`/`load_engine` ne prend aujourd'hui qu'un nom d'entrée et impose batch1 (`src/aji_trt.cpp:241`, `941–966`). Une tête à deux entrées nécessite une gestion RIFE bornée des deux bindings/shapes, pas seulement un nouveau fichier ONNX.
3. Exécuter l'encodeur une seule fois après préparation réussie d'une nouvelle paire. Stocker ses features GPU stables, puis lancer la tête complète à chaque t demandé. Reprendre les identités explicites de paire et vues exactes, géométrie paddée, format/range, contexte et règles de reset/stream ; aucune identité déduite du seul pointeur. En cas d'erreur, ne pas publier un cache partiel. Détruire les graphes avant les buffers qu'ils capturent ; ordonner production/features/consommation avec les fences existants.
4. Ajouter une identité de programme dérivé distincte et versionnée, liée au SHA complet du modèle et à la coupe/recette. Le schéma de référence est `freeze_motion_model` (`src/model_identity.cpp:93`) et `docs/program-cache-contract.md` ; ne pas réutiliser les identifiants motion ni les moteurs complets existants. `src/onnx_flow.cpp` ne sait actuellement qu'ajouter/changer les sorties motion, sans scinder le réseau : un exporteur de coupe est un vrai nouveau travail.
5. Une comparaison numérique ciblée est nécessaire avant activation : même paire et trois t (.25/.5/.75), modèle/machine/forme/range identiques ; comparer RGB FP16 puis sortie YUV de référence, avec une nouvelle paire et reset pour couvrir le cache. Le but est de résoudre le risque de nouvelle compilation exposé ci-dessous. Aucun benchmark systématique ; une mesure courte seulement si un gain de temps est ensuite revendiqué. Ne pas réutiliser comme oracle une ancienne bibliothèque qui interprète Quality comme Fast.

## 4. Limites numériques de la coupe

La séparation est **exacte au niveau des dépendances et de l'algorithme**, mais ce n'est pas une preuve d'identité bit à bit des nouveaux plans TensorRT. La frontière engine impose une matérialisation FP16 et peut modifier fusion, layout, tactique et ordre d'accumulation. Le cache actuel documente déjà qu'une reconstruction à froid peut changer tactiques et numérique (`src/model_identity.cpp:109`). `--stronglyTyped` conserve les types ONNX ; il ne prouve pas à lui seul l'identité des résultats entre un réseau monolithique et deux réseaux.

Préserver strictement les îlots FP32 autour des grilles : tous les `GridSample` locaux prennent des données et grilles FP32 ; leur résultat est recasté FP16 avant le reste. `tools/convert_rife_fp16.py:39–52,74–99,135–138` définit les îlots et casts. Aucun remplacement par des grilles FP16 ni contournement du dernier warp/blend n'est compatible avec cette tranche Quality. Si la comparaison révèle une différence, la documenter et résoudre la compilation/frontière avant d'appeler cela une optimisation exacte ; ne pas la masquer sous une tolérance inventée.

## 5. Batching des trois timesteps : piste secondaire distincte

Un batch de .25/.5/.75 peut améliorer l'occupation et amortir certaines soumissions, mais **ne retire pas les calculs dépendants de t**. Batcher le modèle entier répéterait aussi l'encodeur, sauf partage explicite en amont. Le graphe CUDA existant amortit déjà une partie du coût de lancement ; le bénéfice supplémentaire du batch est inconnu.

Ce modèle n'est pas simplement compatible avec `--optShapes=input:3x11x768x1280` : entrée batch1, **15 Reshape avec dimensions fixes1/2**, notamment `[2,3,0,0]`, `[1,8,0,0]`, `[2,2,0,0]`, et **`/Split_5` nœud316 axis0 tailles `[1,1]`** avant le blend final. Il faut reprendre explicitement l'association paire/endpoint/phase. Remplacer aveuglément1→3 et2→6 peut mélanger les images entre phases au split final. Les intermédiaires des têtes et leur workspace peuvent grossir fortement ; aucune borne de pic mémoire n'a été mesurée.

Recommandation : commencer par la coupe encodeur/cache par paire avec tête batch1 inchangée. Étudier un batch de têtes séparément seulement si les mesures de la chaîne et une revue mémoire montrent une raison précise. Les deux options gardent les trois prédictions complètes ; aucune n'est implémentée dans ce rapport.

