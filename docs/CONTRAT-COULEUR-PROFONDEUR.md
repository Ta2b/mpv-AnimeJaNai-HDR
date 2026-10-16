# Couleur, profondeur et frontières d'inférence — REF-05

Lot27 / AH-274 sous AH-15. Base3.8.0.58 ; le transport complet et les clients natifs restentAH-275, en coordination avec les surfacesAH-49 et la soumissionAH-50. Ce contrat décrit les routes existantes et les invariants à appliquer ; il n'assimile pas une métadonnée conservée à une fidélité numérique démontrée.

## Séparer source, traitement et présentation

Une image sourceSDR10bits peut être traitée par le pontRGB24 : les calculs neuronaux FP16/FP32 ne rétablissent pas les bits perdus à cette frontière8bits. Une sortieHDR ajoutée par TrueHDR/mpv en aval ne démontre pas que l'inférence a traité une sourceHDR ou conservé sa précision. Le gamut et la plage ne sont pas certifiés par le seul tag de sortie.

Toute nouvelle sélection de moteur/format doit déclarer les frontières de profondeur, conversion de gamut/plage et dither, accepter explicitement le compromis ou conserver une voie admissible. Les formats/espaces non pris en charge doivent produire un refus/repli explicite. Une voie haute profondeur est distincte (COL-02/AH-188) ; aucun renommage «FP16» ne transforme RGB24 en entrée haute profondeur.

La référence inclut : matrice, primaires, transfert, plage, chroma siting, crop actif, orientation, profondeur significative et alignement du conteneur, ordre de clamp/quantification/arrondi, dither, métadonnéesHDR dynamiques si pertinentes, modèle et conversions avant/entre/après réseaux. Voir aussi [précision par opérateur](CONTRAT-PRECISION-MOTEURS.md).

## Données qui traversent réellement les interfaces

| Donnée | Pont partagé RGB24 ABI1 | Backend natif ABI9 | Règle pour le transport versionné restant |
|---|---|---|---|
| Matrice/plage | Les pixels sont convertis enRGB24 par mpv avant le moteur ; pas de champs couleur dansABI1 | `aji_frame.matrix/range` (601/709/2020NC, limited/full) | Distinguer matrice source, matrice du buffer et inconnue ; ne pas forcer709 silencieusement |
| Primaires/transfert | Restent dans `mp_image_params` côté lecteur et copiés aux sorties ; moteur sans paramètres dédiés | Pas de champs dédiés dans `aji_frame` ; tags détenus par le clientmpv | Transport séparé de matrice ; les identités/caches couvrent une conversion effective changée |
| Chroma siting | Consommé par la conversionmpv avantRGB ; tag conservé côté lecteur | Champ `siting`, left/center/topleft ; RIFE a sa préparation dédiée | Les phases des conversions de référence sont conservées ; un tag seul ne prouve pas la bonne interpolation |
| Crop/orientation/aspect | `mp_image_copy_attributes`, crop redimensionné par rapports entiers, pixel aspect conservé dans le pont ; pas transmis au moteur | Dimensions/planes/strides, pas de rectangle/orientation dédié dansABI9 | Décrire vue active, crop, orientation et moment d'application ; pas de lecture hors de la vue |
| Profondeur/format | Contrat d'entrée/sortie **RGB24,3×8bits**, distinct des tenseurs du réseau | NV12, P010, YUV444P16, 44410/12MSB CUDA ; RGB10A2 DML selon chemin | Profondeur significative et stockage séparés ; capacité du client/provider négociée, pas déduite du fabricant |
| Clamp/arrondi/dither | Règles du provider/convertisseur à chaque frontière ; voir ci-dessous | Quantification explicite des kernels vidéo | Conserver toute opération numérique lors du retrait d'un transport ; dither absent/inconnu reste distinct d'un dither activé |
| HDR dynamique | Attributsmpv côté lecteur ; ABI1 n'en reçoit pas | Tags côté client, pas de descripteurHDR dynamiqueABI9 complet | Ownership/durée et invalidation explicites selon données réellement consommées |

Sources des champs actuels : [aji_vulkan.h](../native/linux-vulkan/aji_vulkan.h), [pont mpv partagé](../native/linux-vulkan/vf_animejanai_vulkan.c), backend compagnon [include/aji.h](https://github.com/Ta2b/animejanai-inference-rtx/blob/66fcd9ded3310d009c5402e1a9f43900da59a690/include/aji.h). ABI1 etABI9 sont conservées ; le tableau ne prétend pas que les champs manquants sont déjà implémentés.

Le pontmpv partagé demandeRGB24, refuse PQ/HLG à sa configuration et replannifie/incrémente sa génération sur changement statique des paramètres. Le moteur lui-même ne reçoit pas ces tags couleur. `mp_image_params_static_equal` ignore les métadonnéesHDR dynamiques : ne pas en déduire une couverture universelle des futurs cachesHDR. Les sortiescopient les attributs, adaptent crop/dimensions/cadence ; cela conserve des tags et la géométrie, pas une preuve de restitution des niveaux/gamut. Sourcesmpv du lecteur : `video/mp_image.c`, `player/command.c` et filtres compagnons compilés.

## Frontières numériques à conserver

| Route | Opérations observées / limites |
|---|---|
| ORT partagéCPU/providers | PixelsRGB24 normalisés enFLOAT puis stockageHALF si déclaré ; sortie tensor→FLOAT si nécessaire, multiplication255, ajout0,5 et clamp0..255 avant conversionbyte. Chaque exécuteur écritRGB24 ; supprimer ce passage exige de reproduire ses valeurs intermédiaires |
| MIGraphX natif pontRGB24 | HIP packingnormalisation et unpacking `clip(value×255+0,5,0,255)`→byte ; calculs de warpfloat avec quantification finale explicite. Cette route est distincte de l'interopD3D12 |
| Metal natifSPAN | UInt8→HALF, normalisationHALF ; clamp0..1→×255→roundHALF→UInt8. Ne pas remplacer sa règle par celle d'ORT sans qualification |
| CoreML natifSPAN | Image d'entrée8bits etMLProgram ; sortieclip→×255→round explicite dans le convertisseur puis image8bits. Les sommes internes restent une question de précision séparée |
| NCNN/Vulkan | SPAN normalise/dénormalise les tenseurs ; plusieurs stepsSPAN peuvent conserver un tenseur flottant entre eux. RIFE4.6 consomme/produit des pixelsRGB8 et la sortie est packée. Ne pas inventer une quantificationbyte à chaque stepSPAN de cette route |
| CUDA natif | Préparation/post enFLOAT, tenseursRGBFP16 ; chroma4:2:0 resamplé en passes séparées,4:4:4 distinct. Sortie `clamp(rintf(value/qdiv),0,qmax)×qdiv` : P010 qdiv64/qmax1023,44412MSB qdiv16/qmax4095,44416 qdiv1/qmax65535. Pas de dither ajouté dans cette fonction |
| RIFE natifCUDA | Préparation dédiée BT.709 comme sa référence actuelle, paddingstudio-black, grid/casts et round-trip YUV existants. Ceci ne qualifie pas toutes les matrices/plages/crops possibles. Un raccord direct futur doit reproduire le round-trip observable avant de proposer une variante haute précision |
| PrésentationHDR | TrueHDR/grade/mpv agissent après les réseauxSDR selon la route. PackedRGBA8/10bits et tagsPQ/2020 sont des frontières de traitement, pas des preuves de conservation du gamut d'entrée |

Sources : [exec_ort.cpp](../native/linux-ort/exec_ort.cpp), [hip_kernels.hip](../native/amd/hip_kernels.hip), [exec_metal.mm](../native/apple/exec_metal.mm), [convert_models.py](../native/apple/convert_models.py), [aji_vulkan.cpp](../native/linux-vulkan/aji_vulkan.cpp), backend [kernels.cu](https://github.com/Ta2b/animejanai-inference-rtx/blob/66fcd9ded3310d009c5402e1a9f43900da59a690/src/kernels.cu). Les conversions généralesmpv/FFmpeg peuvent avoir leurs propres choix de filtre/dither : non relevés ici, donc inconnus plutôt qu'«absents».

## Diagnostic livré dans le lecteur Linux

Le rapportHDR existant (`animejanai-hdr-status`) ajoute deux lignes : faits de la source **avant filtres** et frontière d'inférence sélectionnée. Le descripteur est aussi disponible à la demande sous `user-data/animejanai-color-contract` : source/attributs, origine de chaque champ, profondeur connue, classificationHDR/SDR/inconnue et route. Aucun observateur permanent ni écriture de paramètres vidéo ajouté.

Exemple : source `yuv420p10le`, transfertbt.1886, primaires2020, pontpartagé → **«Inference : RGB8bitsSDR | quantification10→8bits»**. Une sourceopaque conserve «profondeur inconnue». `video-dec-params` est prioritaire, `video-params` complète seulement les champsauto/inconnus ; aucune lecture de `video-out-params` pour classifier la source. Le format matériel `hw-pixelformat` peut établir la profondeur deNVDEC ; la profondeur n'est jamais déduite d'`average-bpp`, du nom duGPU ni deFP16.

PQ/HLG/DolbyVision restentHDR même si la sortie après filtres estSDR ; une sortiePQ ajoutée après une sourceSDR ne la reclassifie pasHDR. Une baliseTrueHDR aval active est décrite comme balise, sans certifier l'effet duSDK. Un filtre désactivé donne «inférence inactive». La route native indique une profondeur effective à consulter selon négociation, sans promettre16bits à partir du seul nom TensorRT. L'outil ne change aucun filtre/choix de décodage/rendu/pixel.

## Qualification courte et décision

Vérification Lua dans un dossier de fixtures isolé : source10bitsSDR/2020/range/crop/rotation, format matérielP010 avec défauts résolus etHDR, sourceopaque,8bits, voie native12bits, filtre désactivé et inconnu. Métadonnées source inchangées, origines explicites. Contrôle du **vrai rapport lecteur avant/après** via le harnessmpv existant, mêmes propriétés : absence du diagnostic avant, frontière10→8 après ; sourceSDR conservée malgré une sortiePQ. Le rapport n'écrit que la propriété de diagnostic, aucun paramètre de vidéo. Arrêt après ces contrôles concluants, sans rejouer la suiteHDR historique. SyntaxeLua et liens locaux vérifiés.

Artefacts locaux `artifacts/performance/lots-20261016/lot-27/diagnostic-check.lua`/`.log`, référence extraite de la révision3.8.0.58 et fichiersfixture. Aucun essai neuronal ni mesureFPS : aucun moteur/flux vidéo modifié. Utilitéétablie = réductionRGB24 et inconnues rendues visibles et contrat exploitable avant les prochains raccordsGPU. Aucune préservation de gamut ni qualification matérielle supplémentaire inventée.

Livraison3.8.0.59 pourAH-274, Done après publication vérifiée. **AH-15 reste In Progress** : AH-275 porte les champs/consommateurs natifs manquants ; AH-49/50 les mécanismes de surfaces/complétion. Les détails de fidélité/haute profondeur restentAH-187/188. Le périmètre du parent n'est pas fermé par le diagnostic.
