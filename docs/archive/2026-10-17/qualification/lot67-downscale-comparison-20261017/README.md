# AH-352 — conclusion Area / Spline36

Une seule image synthétique 1920×1080 → 1280×720, mêmes plans YUV444P16 pleine plage BT.709, mêmes modules livrés .86/.87/.88. Linux RTX 4070 Ti ; aucun modèle neuronal, aucun fichier utilisateur modifié. Le raccord, l'oracle natif Spline36 et la géométrie sont déjà qualifiés dans le [lot57](../lot-57-native-fruc-removal-spline36-20261017.md) et livrés .84 ; ces essais ne sont pas répétés. Cette nouvelle observation compare seulement les compromis restants. [Reçu](receipt.json), [machine](machine.txt).

| Observation sur cette image | Area | Spline36 |
| --- | --- | --- |
| Dépassement sous le niveau bas d'un contour | 0 code16 | 547 codes16, environ 0,835 % de la pleine plage |
| Dépassement au-dessus du niveau haut | 0 code16 | 531 codes16, environ 0,810 % |
| RMS résiduel d'un damier source à Nyquist, autour de sa moyenne idéale | 2184,5 codes16 | 10,966 codes16 |
| Moyenne du damier, idéale 32767,5 | 32767,5 | 32760,0 |

Les niveaux du contour sont 13107/52428, suffisamment éloignés des limites pour observer les halos sans clipping. Spline36 atténue ici nettement plus le damier que l'intégration de boîte Area, au prix d'un petit halo autour du contour. Le biais de moyenne de 7,5 codes16 reste inclus dans son RMS : ce n'est pas une équivalence numérique. Une seule image ne classe pas les deux méthodes sur tous les contenus, tous les rapports de réduction ou la stabilité temporelle ; aucun score perceptuel n'est inventé.

Le code explique cette différence : Area intègre l'empreinte de chaque pixel avec des poids positifs directement dans les plans YUV16. Spline36 possède des lobes négatifs, un support élargi quand on réduit et deux passes séparables ; sa route native passe par RGB FP16. À ce rapport 3:2, Area lit quatre échantillons par plan/pixel ; Spline36 utilise dix taps par axe, des intermédiaires et les conversions de sa route. C'est un coût de travail et de stockage établi par les sources, **pas un gain FPS mesuré**. Aucun benchmark supplémentaire n'est nécessaire pour décider de conserver les deux choix.

Décision : Area reste une option sobre, sans dépassement créé par les poids du filtre ; Spline36 reste une alternative utile pour son filtrage et pour retrouver le redimensionneur natif historique, avec halos et frontières numériques propres à cette route. Aucun remplacement silencieux, réordonnancement ou changement de profil. Aucun choix universel « meilleur ». Les libellés Manager existent déjà et la sélection est effective ; aucune nouvelle méthode fictive ajoutée. L'exécution décrite est Linux CUDA uniquement, sans extrapolation Windows/AMD/Intel/macOS.

Reproduction ciblée : `tests/inference/downscale_comparison_probe.py SPEC.json`, avec chemins explicites `library`, `trt`, `kernel`, `output` (dossier neuf). Les sorties ne sont calculées qu'une fois par méthode, puis leurs régions définies dans le probe sont mesurées. Hash d'entrée et hashes des modules/sorties dans le reçu. Le probe ne compile aucun modèle et ne mesure aucun FPS. Les fichiers `.npy` synthétiques restent dans le dossier de qualification local.

Sources auditées : backend `d5b34469a3aa1cc30f107ba3122699d713de1dca`, `src/pipeline_kernels.cu:aji_pipeline_downscale`, `src/resample.h:spline36/compute`, `src/kernels.cu:aji_resize_plan_create`, `src/aji_pipeline.cpp:apply`. Bundle `ff27fba988b75e00c1348195266455ce0992428a` ; les trois hashes du reçu sont ceux de la livraison déjà vérifiée. Arrêt après cette conclusion ; le rendu et les moteurs du produit ne changent pas dans ce ticket.
