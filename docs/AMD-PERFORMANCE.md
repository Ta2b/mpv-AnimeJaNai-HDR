# Pistes AMD / Windows — 14 octobre 2026

## Mise en œuvre en cours

L’étude ci-dessous est antérieure à la décision d’intégrer MIGraphX + HIP natif
sur Windows/Linux et TensorRT + CUDA spécialisé. La cible est RX 9070 XT.
La préparation anticipée des moteurs est abandonnée. Lire
[le relais précis du chantier](CHANTIER-GPU-SPECIALISE.md) pour le code, les
builds et les limites actuelles ; cette étude ne décrit pas une release livrée.

## Statut et contraintes

Recherche documentaire et lecture du code uniquement. Aucun moteur modifié,
aucun test ou benchmark lancé. Les gains ci-dessous sont des hypothèses,
pas des résultats AMD mesurés. Priorité : performance, modèles conservés,
qualité actuelle préservée ; difficulté du chantier sans influence sur le choix.

La 3.8.0.29 possède la nouvelle chaîne RIFE dans le moteur partagé et la
branche CUDA, mais pas dans Windows DirectML ni NCNN/Vulkan. Voir
[CHANTIER-RIFE-165HZ.md](CHANTIER-RIFE-165HZ.md).

Constats statiques :

- `../animejanai-inference-rtx/src/aji_dml.cpp`, `model_open` : ORT DML1 partage
  déjà le device et la queue D3D12 ; I/O binding sur ressources GPU, graphe
  optimisé et warmup déjà présents. Ne pas les présenter comme du travail neuf.
  La fonction attend exactement une entrée et une sortie : exposer flow/mask
  impose de généraliser les sorties et leur allocation. Elle ne fixe pas les
  dimensions symboliques avant création de session ; vérifier si les modèles
  concernés en ont avant de proposer des overrides.
- `native/linux-vulkan/aji_vulkan.cpp` impose RIFE 4.6 / code 46. Porter une
  chaîne basée sur 4.26 nécessite d'abord une conversion et les opérateurs
  compatibles avec ces mêmes poids. Les modèles AnimeJaNai temporels sont
  également refusés actuellement.
- Ce code expose déjà les choix Winograd, SGEMM et cooperative matrices. Le
  choix désactivant Winograd est spécifique NVIDIA, seul cas mesuré dans ce
  commentaire ; ne pas le généraliser automatiquement à AMD.

## Options et ordre proposé

Le plafond maximal de performance n'est pas mesuré : un moteur spécialisé AMD
est le chantier au potentiel le plus ambitieux, mais peut perdre contre une
bibliothèque constructeur. L'ordre ci-dessous privilégie les leviers concrets
du projet, sans pénaliser leur difficulté ; il ne classe pas des FPS connus.

1. **Porter la nouvelle chaîne sur DirectML/D3D12 Windows.** Flow/mask sur GPU,
   endpoints upscalés une seule fois, warp/mélange HLSL, caches par paire,
   chronologie des dessins et PTS conservés, buffers persistants. La réutilisation
   du flow pour plusieurs instants relève du mode `new` et change le rendu :
   conserver `old` et l'inférence par instant pour le chemin de référence.
2. **MIGraphX via Windows ML sur RDNA 3+.** Nouvelle alternative native à étudier
   pour les mêmes ONNX, avec compilation par résolution, cache et allocation
   GPU. Vérifier particulièrement GridSample, sorties flow/mask, partitions CPU,
   précision et interop avec décodage/affichage Direct3D. L'EP n'est pas une
   garantie de prise en charge intégrale ou de gain pour RIFE/SPAN.
3. **Moteur spécialisé AMD Vulkan ou HIP.** Compilation des graphes actuels,
   convolutions adaptées à SPAN/RIFE, fusion bias/activation et opérations
   mémoire quand équivalentes, poids préarrangés, planification/allocation
   statiques, kernels propres à RDNA 2/3/4. Accélération matricielle selon les
   capacités réellement exposées. Même chaîne GPU complète : aucun aller-retour
   CPU image et nombre minimal de soumissions/barrières nécessaires. Vulkan
   Windows exige une interop D3D/Vulkan supportée ou un chemin vidéo Vulkan.
   HIP permet de réutiliser une partie des kernels CUDA ; TensorRT lui-même
   doit être remplacé par MIGraphX ou une autre exécution des graphes.
4. **DirectML spécialisé.** Fixer les formes symboliques pertinentes avant
   création des sessions ; améliorer les partitions et fusions ; envisager
   un graphe DirectML natif avec shaders HLSL pour les opérations coûteuses.
   L'ORT existant rejoue déjà des commandes : retirer ORT n'assure pas un gain.
5. **IREE/Vulkan.** Compiler les modèles actuels via un frontend compatible
   vers MLIR/SPIR-V, spécialiser par architecture/résolution et intégrer son
   runtime au lecteur. Alternative à l'écriture d'un compilateur complet ;
   couverture ONNX/RIFE et performances à établir.
6. **Portage NCNN/Vulkan complet.** Utile Windows et Linux, anciennes Radeon
   comprises selon leurs capacités. Charger les mêmes modèles, exposer les
   sorties RIFE, warp GPU, réutilisation mémoire et intégration mpv native.
   Le simple port de l'algorithme ne rend pas les kernels génériques NCNN
   meilleurs que DirectML. Conserver comme moteur disponible avant tout
   changement automatique de backend.

Ces travaux peuvent se combiner. Le socle commun est la chaîne GPU, les caches,
la planification vidéo et les interfaces du lecteur ; l'exécuteur neuronal
doit rester substituable. Précompilation à l'installation réduit surtout le
démarrage ; concurrence bornée et suppression des synchronisations CPU peuvent
améliorer le débit si le GPU n'est pas déjà saturé.

## Compatibilité officiellement documentée au moment de la recherche

- Windows ML propose MIGraphX en téléchargement dynamique : Windows 11 24H2
  build 26100+, AMD RDNA 3+, pilote AMD version 25.10.13.09+. Cela remplace
  l'hypothèse historique « MIGraphX seulement Linux » pour cette distribution.
  Les RX 6000 RDNA 2 ne satisfont pas cette exigence d'EP.
  [Microsoft, EP disponibles](https://learn.microsoft.com/en-us/windows/ai/new-windows-ml/supported-execution-providers).
- HIP est l'analogue de la plateforme de programmation CUDA ; le SDK Windows
  existe, avec une couverture matérielle et logicielle à vérifier séparément.
  MIGraphX est l'analogue fonctionnel d'un compilateur/exécuteur de graphes tel
  TensorRT, pas une compatibilité avec ses plans binaires.
  [AMD HIP Windows](https://www.amd.com/en/developer/resources/rocm-hub/hip-sdk.html),
  [plugin ORT AMD et construction Windows](https://github.com/onnxruntime/onnxruntime-ep-amdgpu/blob/main/README.md).
- DirectML reste supporté, les nouvelles fonctionnalités vont vers WinML.
  Connaître les formes avant création de session facilite fusions, layouts et
  prétraitement des poids. WinML sélectionne/distribue les EP ; son adoption
  seule n'accélère pas nécessairement une inférence.
  [ORT DirectML](https://onnxruntime.ai/docs/execution-providers/DirectML-ExecutionProvider.html).
- AMD documente WMMA RDNA 3, dont entrées FP16 et accumulation FP32. Sous
  Vulkan, interroger le support et les formats/sizes de cooperative matrices ;
  ne pas supposer cette capacité sur toutes les Radeon ou tous les pilotes.
  [AMD WMMA](https://gpuopen.com/learn/wmma_on_rdna3/),
  [Khronos cooperative matrices](https://docs.vulkan.org/refpages/latest/refpages/source/VK_KHR_cooperative_matrix.html).
- IREE possède un backend Vulkan Windows/Linux et un backend HIP/ROCm ; les
  exigences de chaque runtime doivent être vérifiées indépendamment.
  [IREE Vulkan](https://iree.dev/guides/deployment-configurations/gpu-vulkan/).

## Qualité et reprise

Poids conservés ne signifie pas images identiques. Réutilisation des flows,
timing des dessins, précision, ordre des accumulations et Winograd peuvent
modifier le résultat. Pas d'INT8/INT4, baisse de résolution ou changement de
modèle proposés comme optimisation transparente. Un backend de référence et
l'ancien mode restent nécessaires ; la validation qualité demeure à effectuer
avant d'affirmer l'équivalence, lorsque les tests seront de nouveau autorisés.

L'assembleur CPU ne remplace pas l'accélération GPU des convolutions. Des
intrinsics ou portions d'assembleur GPU HIP peuvent viser un kernel précis.
Le Vulkan portable passe par SPIR-V et compilation du pilote ; écrire toute
la chaîne en assembleur ne garantit aucun avantage.

Prochaine décision : GPU AMD cibles et compatibilité minimale Windows. Proposition
de branches : socle DirectML/D3D12 commun puis MIGraphX RDNA 3+ ; backend
Vulkan spécialisé pour Windows/Linux et Radeon plus anciennes. Aucune de ces
branches n'a été créée dans cette étude.

## Précision utilisateur : RX 9070 XT et préparation anticipée

Cible désormais confirmée : **Radeon RX 9070 XT (RDNA 4)**. La famille satisfait
l'exigence RDNA 3+ de Windows ML MIGraphX, sous réserve du système et du pilote.
Le choix proposé pour cette cible est une chaîne spécialisée **MIGraphX + HIP**,
avec DirectML comme référence. MIGraphX et HIP ne sont pas concurrents : le
premier compile les modèles, le second sert aux kernels personnalisés. Un moteur
HIP intégral et un moteur Vulkan spécialisé ont un plafond théorique ambitieux,
mais aucune supériorité relative n'est établie sur nos modèles et cette carte.

La préparation anticipée doit être une fonctionnalité commune à tous les EP :

- TensorRT : plans compilés et timing cache ;
- MIGraphX : graphes compilés sérialisés / caches de tuning si l'intégration
  retenue les expose ; ne pas supposer que l'EP Windows offre toutes les options
  documentées pour le SDK Linux ;
- HIP/CUDA spécialisés : kernels compilés par architecture, poids préarrangés,
  plans d'exécution et choix des variantes ;
- Vulkan : SPIR-V distribué, création anticipée des pipelines et cache local
  du pilote, plus préparation des poids et plans mémoire.

Dans `rtx-warp/src/aji_trt.cpp`, `start_async_build` et le timing cache existent
déjà : c'est la compilation à la première utilisation, pas la préparation des
profils avant lecture. Le nouveau chantier consiste à programmer cette dernière
en réutilisant les mêmes calculs de formes, réglages et noms de cache.

Préparer les profils actifs, les formes internes réelles (réduction, padding
RIFE, sortie SPAN/HDR), puis 720p/1080p ; invalider selon modèle, graphe
flow/mask, précision, dimensions, backend, GPU et versions pertinentes.
Écriture atomique, verrou par moteur, reprise après interruption, espace disque
borné et statut visible. Ne pas reconstruire tous les caches aveuglément.
Une priorité CPU basse ne protège pas la lecture de la charge GPU : différer
le tuning jusqu'à l'inactivité ou arrêter/différer les travaux concurrents.
La première lecture immédiate peut encore précéder la fin de préparation.

Compilation anticipée réduit le délai de première utilisation ; elle n'ajoute
pas directement des FPS au moteur déjà compilé. Le tuning anticipé peut fournir
de meilleurs choix de kernels. CUDA Graphs, allocations et contexte GPU restent
à préparer en mémoire à chaque lancement, indépendamment du cache sur disque.

Pour NVIDIA, proposition : TensorRT avec orchestration CUDA spécialisée et
plugins ciblés, puis remplacement éventuel des sous-graphes démontrés coûteux.
Un moteur CUDA intégral peut battre TensorRT sur des formes/opérations précises,
sans garantie sur l'ensemble du graphe. Vulkan spécialisé peut aussi dépasser
une implémentation TensorRT imparfaite, mais aucune propriété de l'API ne lui
donne un avantage automatique sur CUDA/TensorRT.

Sources supplémentaires : [compatibilité TensorRT](https://docs.nvidia.com/deeplearning/tensorrt/latest/inference-library/engine-compatibility.html),
[plugins TensorRT](https://docs.nvidia.com/deeplearning/tensorrt/11.4.0/performance/optimization.html),
[MIGraphX compilation et tuning (Linux)](https://rocm.docs.amd.com/projects/AMDMIGraphX/en/develop/migraphx-driver.html),
[cache de pipelines Vulkan](https://docs.vulkan.org/spec/latest/chapters/pipelines.html#pipelines-cache).

Statut inchangé : proposition et inspection uniquement, aucun test ni benchmark,
aucune fonctionnalité de précompilation implémentée pendant cette recherche.
