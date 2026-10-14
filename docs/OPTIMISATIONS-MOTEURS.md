# Optimisation des moteurs et de RIFE — analyse du 13 octobre 2026

## Situation actuelle — 3.8.0.29 (14/10/2026 à 20 h 45 (Paris))

La **3.8.0.29 est publiée sur les trois plateformes**, depuis `6fa85bb`.
Les releases Windows/Linux/macOS sont indépendantes et n'ont plus de jobs de
tests. Le code RIFE partagé `30a3e83` est maintenant dépassé et intégré par les
lots suivants : `d639dc1` / `b3f9d5d` ajoutent la chaîne warp et la chronologie
des dessins. La branche NVIDIA CUDA Graph `f4fcd17` reste isolée.

Lire [l'état consolidé courant](ETAT-PROJET.md) et
[le chantier 3.8.0.24–29 / 165 Hz](CHANTIER-RIFE-165HZ.md). Les sections datées
3.8.0.23 ci-dessous restent un historique des preuves de cette session, pas
l'état global actuel. La chaîne warp est livrée dans le moteur partagé ;
**elle ne l'est pas dans NCNN/Vulkan ni dans les binaires Windows amont**.
Les modèles sont conservés, mais cette stratégie et le lissage des dessins
changent le rendu temporel ; l'ancien mode est conservé.

Analyse statique du lecteur à `d4969eb`, des modèles ONNX livrés, du dépôt local
`../animejanai-inference-rtx` et des documentations officielles. Ce document
propose des expériences ; aucune modification de moteur ni nouvelle mesure de
performance n'a été réalisée pour cette analyse. Il couvre les familles de
pistes pertinentes, sans prétendre épuiser tous les algorithmes possibles.

Le chantier d'implémentation a avancé depuis cette analyse. L'état courant, les
mesures exécutées et les commandes pour reprendre sont consignés dans
[CHANTIER-PERFORMANCE-RELAIS.md](CHANTIER-PERFORMANCE-RELAIS.md). La reprise
NCNN/Vulkan conserve le mode exact par défaut : la reconnaissance approximative
des dessins reste une option, car les tests montrent qu'elle peut effacer de
petits mouvements de faible contraste. Le lot 3.8.0.23 ajoute un pool CPU
persistant et réduit les préparations RIFE redondantes dans le moteur partagé.
Les modèles restent inchangés ; aucun gain chiffré n’est encore établi pour ce
nouveau lot. Les mesures locales sont arrêtées à la demande de l’utilisateur.

## État de réalisation au 14 octobre 2026

[État consolidé du projet](ETAT-PROJET.md). **3.8.0.23 publiée sur les trois
plateformes**, depuis `aab89ba`. Suite moteur partagé : **`30a3e83`**, poussée sur
`hdr-3.8`, CI Mac et plateforme réussie, non incluse dans cette release.
Suite NVIDIA : **`f4fcd17`**, branche `perf-rife-cuda-graphs-20261014` du dépôt
voisin, unité C++ compilée contre deux versions de headers, build complet et
intégration non confirmés. Aucun nouveau test local ni gain chiffré pour ces lots.

Les points du catalogue sont des pistes, pas une liste entièrement implémentée.
Workers persistants, préparations RIFE réutilisées et mesure correcte sont livrés.
Décision par paire/sortie ORT réutilisée sont codées dans le moteur partagé ;
la capture CUDA RIFE est codée dans la branche NVIDIA. RIFE natif Apple,
interopération GPU SPAN/RIFE et concurrence multi-contextes restent à construire.

DirectML, TensorRT, OpenVINO, MIGraphX et NCNN sont des moteurs d'exécution.
SPAN/AnimeJaNai et RIFE sont les modèles qu'ils exécutent. On peut modifier la
chaîne du lecteur, le graphe équivalent, les noyaux ou les modèles entraînés :
ces interventions ont des coûts et des effets sur la qualité différents.

Le retour utilisateur sur la dernière application macOS classe Core ML natif
GPU+NPU devant Metal GPU+NPU. C'est une observation qualitative sur cette
machine ; elle ne fournit pas un facteur d'accélération ni un classement universel.

## Piste SVP — complément du 14 octobre 2026

Retour utilisateur : une RTX 2070 Super arrivait à combiner AnimeJaNai ×2 et
RIFE ×2 via SVP, contrairement à son autre configuration AnimeJaNai/RIFE.
C'est un indice de différence de chaîne, pas encore une comparaison contrôlée :
l'utilisateur confirme **RIFE 4.26, TensorRT, source 1080p, AnimeJaNai ×2,
écran 1080p**. La résolution réellement interpolée, l'ordre des filtres et la
version du runtime restent inconnus. Un écran 1080p ne prouve pas que RIFE
recevait du 1080p : le redimensionnement d'affichage peut survenir après les
filtres. SVP pouvait recevoir la source avant upscale, une sortie 4K, ou une
sortie déjà redimensionnée ; aucune de ces chaînes n'est confirmée.
SVP documente effectivement `frc.frame.resize=-1` (réduire à la taille écran)
et `1` (adapter à l'écran), ce qui rend l'hypothèse de redimensionnement plausible,
sans établir sa position par rapport à AnimeJaNai dans l'ancienne installation.
Source : [réglages SVP](https://www.svp-team.com/wiki/Manual:All_settings). Une
équivalence graphique approximative avec un M4 Pro ne prédit pas les performances
RIFE, particulièrement quand le chemin Mac emploie aussi le Neural Engine.

Sources primaires consultées : [documentation SVP RIFE](https://www.svp-team.com/docs/rife-ai/),
[interface vstrt](https://github.com/AmusementClub/vs-mlrt/blob/master/vstrt/README.md)
et [wrapper vs-mlrt](https://github.com/AmusementClub/vs-mlrt/blob/master/scripts/vsmlrt.py).
SVP documente TensorRT et ncnn/Vulkan, plusieurs threads GPU et une optimisation
par résolution. Le plugin TensorRT référencé propose `num_streams` et
`use_cuda_graph`. Le wrapper expose aussi la spécialisation de forme et deux
implémentations ONNX de RIFE. Cela ne prouve pas quels réglages l'utilisateur
avait activés dans SVP, au-delà de TensorRT confirmé.

Priorités renforcées, en conservant les modèles et sans lancer de nouveaux tests :

1. **Chaîne GPU asynchrone avec concurrence bornée.** Plusieurs contextes et jeux
   de buffers peuvent préparer/exécuter des images indépendantes et éviter des
   creux entre décodage, RIFE, upscale et affichage. Préserver l'ordre de sortie,
   les PTS et une file bornée. Le filtre en avance existe déjà ; il ne suffit pas
   à rendre chaque étape d'inférence concurrente. Le gain dépend de la saturation
   du GPU et de la mémoire disponible, pas du seul nombre de threads.
2. **Étendre les CUDA Graphs au chemin RIFE NVIDIA.** Dans le dépôt voisin,
   `src/aji_trt.cpp:aji_infer_rife` appelle directement `enqueueV3`, contrairement
   au chemin spatial capturé. Le code relit le score de coupe sur CPU via
   `cudaMemcpyAsync` puis `cudaStreamSynchronize` avant la préparation des entrées.
   Une préparation par paire et une décision anticipée ou restant sur GPU sont
   des pistes pour réduire ces attentes, en conservant exactement la règle de
   coupe. Aucun code du dépôt voisin n'est modifié pour cette analyse.
3. **RIFE natif sur Apple et intermédiaires résidents.** Dans notre moteur partagé,
   `load_rife` appelle toujours `make_ort_interpolator`. Choisir Metal ou Core ML
   natif pour SPAN ne sélectionne donc pas un RIFE natif équivalent. Étudier la
   compilation de l'actuel RIFE dans Core ML/Metal et la liaison directe des
   tenseurs SPAN/RIFE, sans retour RGB CPU entre étages. Faisabilité et bénéfice
   restent à démontrer ; ne pas promettre que le NPU prend tout le graphe.
4. **Comparer les exports du même RIFE et la spécialisation de forme.** Le
   wrapper vs-mlrt sélectionne des graphes `rife` ou `rife_v2`, distincts d'un
   changement de génération entraînée. Garder poids, padding et précision
   sensibles ; un export différent n'est pas automatiquement identique à l'octet.
   Notre TensorRT a déjà FP16, cache de compilation/timings et builder niveau 5 :
   ces mécanismes ne sont pas des nouveautés à réimplémenter aveuglément.

Avant d'attribuer l'écart à ces optimisations, identifier le modèle et la taille
traitée : un upscale spatial ×2 quadruple le nombre de pixels présenté à RIFE
lorsqu'il est placé après, mais cet ordre évite d'upscaler chaque image interpolée.
Un autre modèle, `scale<1`, un crop ou l'interpolation classique de SVP changeraient
le travail/rendu demandé et ne prouveraient pas un gain à qualité constante.
Aucune de ces options n'est activée sur la seule base du souvenir rapporté.

**État : analyse documentaire et lecture du code seulement, aucun nouveau test,
aucun gain mesuré, aucune nouvelle implémentation dans la release 3.8.0.23.**

La suite de cette piste est maintenant codée : cache de décision par paire et
sortie préallouée dans le moteur partagé ; CUDA Graph RIFE, timestep conservé et
score de coupe épinglé dans une branche isolée du backend NVIDIA. Compilation
seulement, aucun nouveau test local ni gain mesuré. Ces changements sont
postérieurs aux binaires de la 3.8.0.23 ; détails et limites dans
[le relais](CHANTIER-PERFORMANCE-RELAIS.md).

## Constats dans les sources

| Constat | Preuve | Conséquence |
|---|---|---|
| Le pont ORT générique reçoit et restitue des pixels CPU. | `native/linux-ort/exec_ort.cpp`, `OrtExecutor::run` : `MemoryInfo::CreateCpu`, conversion planaire et `Session::Run`. | OpenVINO/MIGraphX ont une piste de réduction des transferts et conversions. |
| DirectML utilise déjà des ressources GPU et I/O Binding. | `../animejanai-inference-rtx/src/aji_dml.cpp`, `model_open`, `CreateGPUAllocationFromD3DResource`, `RunWithBinding`. | Une proposition générique « ajouter I/O Binding à DirectML » ne serait pas nouvelle. |
| DirectML ne fixe pas les dimensions symboliques avant `CreateSession` dans `model_open`. | Cette fonction reçoit `in_w/in_h`, mais n'appelle pas `AddFreeDimensionOverrideByName`. | Tester la spécialisation avant compilation, pour SPAN puis RIFE selon les noms de dimensions de chaque modèle. |
| Les SPAN Sharp1 livrés ont réellement des entrées FP16 `[1,3,height,width]`. | Inspection du protobuf ONNX : Performance 23 Conv, 10 Relu, 5 Tanh ; Balanced 35 Conv, 16 Relu, 8 Tanh. | Le coût ne se limite pas aux convolutions : opérations élémentaires, branches et layouts méritent un profilage. |
| TensorRT possède déjà FP16, cache de timings, niveau de construction 5 et CUDA Graphs pour la chaîne spatiale. | `../animejanai-inference-rtx/src/aji_trt.cpp`, `DEFAULT_TRT_ENGINE_SETTINGS`, `make_build_spec`, `infer_via_graph`. | Évaluer leur efficacité réelle et les portions non couvertes, plutôt que les présenter comme absents. |
| L'étage RTX Video désactive la capture de toute la chaîne spatiale. | `aji_trt.cpp`, configuration : les appels RTX ne sont pas capturables et `graph_ok=false`. | Une capture limitée à la portion SPAN/prétraitement peut être étudiée. |
| RIFE TensorRT/DirectML prépare de nouveau A et B et relit la détection de scène à chaque appel pour un timestep. | `aji_infer_rife` dans les deux fichiers précédents. | Une API orientée paire d'images permettrait des caches et moins de synchronisations. |
| RIFE après upscaling dans le backend NCNN recalcule les deux images agrandies à chaque timestep. | `native/linux-vulkan/aji_vulkan.cpp`, `aji_vk_process` : `a=upscale(c,a); b=upscale(c,b)`. | Redondance déterministe à éliminer, indépendamment de l'efficacité des convolutions. |
| Le convertisseur NCNN garde Conv et ReLU séparés. | `native/linux-vulkan/convert_span.py`. `installer/linux/build-inference.sh` ne lance pas `ncnnoptimize`. | Tester la fusion Conv/activation et la suppression des opérations inutiles. |
| NCNN possède déjà des chemins à matrices coopératives dans la version épinglée. | `d8227bbe…`, `src/option.cpp`, `src/layer/vulkan/convolution_vulkan.cpp`. | Leur utilisation effective doit être observée : l'option est déjà vraie par défaut. |
| Le moteur partagé récent sait déjà répartir les tuiles et reprendre des zones inchangées. | `native/linux-ort/aji_ort.cpp`, `tiles.cpp`. | Réutiliser cette orchestration là où elle apporte un gain, sans découper systématiquement tous les calculs. |

L'ancien benchmark NCNN rapporte 28,3 ms pour Performance 720p sur RTX 4070 Ti,
contre environ 4,4–4,5 ms pour la chaîne TensorRT dans les données historiques.
L'entrée reste alors sur le GPU et la sortie n'est pas rapatriée. Les copies
d'images n'expliquent donc pas cet écart. C'est un résultat de cette version,
de ce graphe et de cette configuration, pas une borne physique de Vulkan ni de
toutes les configurations futures de NCNN. Le chronométrage inclut aussi la
soumission et l'attente du travail : ajouter des timestamps GPU permettrait
de préciser le temps de calcul pur. Voir `docs/LINUX-INFERENCE.md` et
`native/vulkan-bench/bench.cpp`.

## Catalogue des expériences

« Sans réentraînement » signifie que les poids peuvent être conservés ; cela
n'implique pas une identité bit à bit après changement de précision ou d'ordre
des sommes. « Recherche » indique une piste à démontrer, pas un gain acquis.

### Chaîne commune : calcul, transferts et ordonnanceur

1. **Tracer les temps de chaque étage.** Décodage, resize, conversion, upload,
   chaque modèle, download, HDR et présentation. Employer des événements/timestamps
   GPU ; le temps CPU de soumission d'un appel asynchrone n'est pas sa durée GPU.
2. **Détecter les replis CPU internes.** Vérifier les partitions de graphe, casts,
   transpositions, GridSample et opérations de forme. Un fournisseur sélectionné
   ne prouve pas que tous les nœuds tournent sur le GPU/NPU.
3. **Garder les images sur le GPU.** Connecter les surfaces du décodeur, les tenseurs
   et le rendu. Intel : VAAPI/OpenVINO ; NVIDIA : NVDEC/CUDA ; Mac :
   CVPixelBuffer/IOSurface/Metal. AMD : évaluer les interopérations disponibles sur
   la combinaison VAAPI, DMA-BUF, Vulkan et ROCm. Ce dernier chemin n'est pas acquis.
4. **Garder les intermédiaires sur le GPU entre modèles.** Éviter le retour RGB24
   entre deux upscalers, ou entre interpolation et upscaling. Les chemins CUDA/DML
   en font déjà une partie ; vérifier surtout les raccords RIFE.
5. **Fusionner les opérations de pixels.** Couleur, normalisation, cast, layout,
   padding et resize en moins de noyaux ; sortie : crop, clamp et packing.
   Conserver la matrice couleur, le range, le chroma siting et les filtres choisis.
6. **Préallouer buffers et sorties.** Pools par forme, réutilisation des tensors,
   allocations après warm-up et plafonds de VRAM. Les vecteurs persistants existent
   déjà à plusieurs endroits ; cibler les allocations restantes.
7. **Chevaucher les étages.** Préparer l'image suivante pendant le calcul courant,
   avec files bornées et double/triple buffering. Si un transfert CPU est inévitable,
   comparer mémoire épinglée et copies asynchrones. Contrôler la latence ajoutée.
8. **Réduire les attentes CPU.** Préférer dépendances GPU et fences/events aux
   attentes bloquantes intermédiaires. Ne pas supprimer les barrières nécessaires.
9. **Utiliser un pool de threads permanent.** `parallel()` et le partage des tuiles
   créent actuellement des threads pour des travaux d'image. Mesurer cette dépense
   avant de remplacer le mécanisme et éviter la sursouscription entre exécutants.
10. **Réduire les coûts des statistiques.** Les moteurs écrivent un fichier à chaque
    image. Comparer une publication moins fréquente ou un canal IPC ; garder le
    diagnostic immédiat des erreurs et la mesure interne indépendante.
11. **Autotuner par appareil/modèle/forme.** Moteur, grille, précision et nombre de
    requêtes, avec mémoire du choix. Inclure latence de pointe, qualité, énergie et
    charge d'affichage dans la décision ; exclure compilation et sondes initiales.
12. **Distribuer le travail entre processeurs distincts.** Comparer tuiles GPU/NPU,
    ou RIFE sur un processeur et SPAN sur l'autre. Les dépendances, transferts et
    replis CPU peuvent annuler le gain. Ne pas extrapoler le résultat Apple aux PC.

### Graphes SPAN/ONNX, sans modifier les poids entraînés

13. **Fixer toutes les dimensions connues avant compilation.** Dimensions spatiales,
    batch et, pour RIFE, dimensions de grille. ORT générique le fait déjà pour les
    dimensions SPAN `height/width` ; DirectML est un candidat concret à compléter.
14. **Simplifier le graphe spécialisé.** Évaluer les constantes Shape/Gather/Mod,
    Pad/Slice inutiles aux tailles admissibles, casts et copies redondants. Garder
    une variante dynamique pour les tailles non couvertes.
15. **Adapter pixel-unshuffle à chaque moteur.** Comparer Reshape/Transpose,
    convolution de sélection et fusion avec la première convolution. Le correctif
    Core ML ne constitue pas automatiquement la variante la plus rapide ailleurs.
16. **Fusionner les activations et opérations élémentaires.** Conv+ReLU, puis
    Tanh/Mul/Add et épilogues compatibles. Les activations dépendantes du contenu
    et les non-linéarités empêchent de fusionner arbitrairement toutes les Conv.
17. **Fusionner les couches linéaires admissibles.** Composer certains 1x1/3x3 ou
    branches linéaires quand les dépendances et le padding le permettent. Vérifier
    d'abord si le modèle SPANF3 exporté et le runtime effectuent déjà la fusion.
18. **Limiter les conversions NCHW/NHWC et pack1/pack4.** Laisser les couches dans
    leur layout efficace. Mesurer les reformats internes, pas uniquement les I/O.
19. **Fusionner la sortie pixel-shuffle avec l'écriture de l'image.** Un épilogue
    spécialisé peut éviter une matérialisation intermédiaire volumineuse.
20. **Optimiser les recouvrements de tuiles.** Halo calculé depuis le réseau,
    grille ajustée au cache et à la taille minimale du runtime. Trop de tuiles
    répètent les bords et multiplient lancements et compilations.
21. **Étendre prudemment la réutilisation.** Cache exact d'images/zones identiques,
    puis seuil perceptuel en option. Inclure le halo dans la comparaison. Pour un
    modèle temporel, la fenêtre de plusieurs images doit entrer dans la clé.

### TensorRT et NVIDIA

22. **Profiler les couches et tactiques actuelles.** Les convolutions, reformats et
    lancements dominants dictent les priorités. Le niveau de builder 5 et le cache
    de timings sont déjà présents.
23. **Construire dans des conditions reproductibles.** Comparer engines construits
    GPU au repos et sous lecture ; rechercher les tactiques adaptées à une charge
    partagée avec le rendu. Workspace et VRAM sont à mesurer, pas à maximiser.
24. **Capturer les segments encore non couverts.** RIFE et la portion spatiale avant
    RTX Video sont des candidats. Buffers/adresses stables et absence d'interaction
    CPU au milieu sont des conditions à résoudre.
25. **Tester petits batches et concurrence bornée.** Tuiles ou timesteps RIFE, avec
    un contexte et des buffers par travail simultané. L'augmentation du débit peut
    augmenter la latence et la VRAM ; elle n'est pas un objectif suffisant.
26. **Comparer la persistance du cache L2 et les formats internes.** Seulement sur
    matériel compatible ; les petits tenseurs et le rendu partagé peuvent changer
    le résultat. Les canaux 48/64 sont déjà bien alignés pour de nombreux noyaux.
27. **Comparer TensorRT classique à TensorRT for RTX.** Le second a un chemin de
    compilation AOT/JIT et des optimisations de convolution FP16 batch 1 ; c'est un
    candidat réel pour SPAN/RIFE. Vérifier opérateurs, précision, interopération,
    coexistence avec RTX Video et déploiement. Le nom du dépôt local « inference-rtx »
    ne signifie pas qu'il utilise déjà TensorRT for RTX.
28. **Écrire des plugins ciblés.** Warp/GridSample, construction de grille, épilogue
    ou conversion coûteuse peuvent justifier CUDA/CUTLASS et éventuellement PTX.
    Un plugin doit battre le noyau existant sans casser une fusion plus bénéfique.

TensorRT 11 suit les types du graphe. Les anciens conseils `--fp16`, `--int8` ou
`--tacticSources=…` ne sont pas un plan valable : le code local les retire déjà.
Pour une nouvelle précision, modifier le graphe et respecter les possibilités
de la version installée. [Précision TensorRT](https://docs.nvidia.com/deeplearning/tensorrt/latest/inference-library/precision-control.html).

### DirectML et Windows

29. **Spécialiser les sessions avant création.** C'est le premier essai ciblé :
    passer les dimensions libres SPAN et inspecter celles de chaque RIFE. Mesurer
    initialization et inférence séparément. [Conseils DirectML](https://onnxruntime.ai/docs/execution-providers/DirectML-ExecutionProvider.html).
30. **Contrôler les partitions et formats.** Le modèle entier sur DML, versions
    d'opset compatibles, FP16 conservé et buffers GPU réutilisés. I/O Binding,
    queue DML1 et warm-up sont déjà dans le moteur.
31. **Réduire les copies D3D11/D3D12 et passages texture/buffer.** Les textures
    partagées évitent un rapatriement CPU, mais pas toutes les copies GPU.
32. **Optimiser les command lists et barrières.** Réutiliser les enregistrements
    admissibles, borner les allocateurs, maintenir la synchronisation entre APIs.
    Le moteur spatial dispose déjà d'un mécanisme asynchrone à tickets.
33. **Prototyper DirectML natif pour un SPAN fixe.** Compiler un graphe DirectML
    directement est possible ; cela permet un contrôle fin des bindings et
    shaders adjacents. Le fournisseur ORT compile déjà des sous-graphes DML : retirer
    ORT seul ne garantit pas un gain comparable à celui observé sur Mac.
34. **Évaluer Windows ML et ses fournisseurs matériels.** DirectML reste supporté,
    mais le développement de nouvelles fonctionnalités a migré vers Windows ML.
    Examiner support des OS, fonctionnement portable/hors ligne et providers,
    sans abandonner la voie DirectML de compatibilité.
    [Windows ML](https://learn.microsoft.com/en-us/windows/ai/new-windows-ml/overview).

### OpenVINO et Intel

35. **Optimiser d'abord le fournisseur actuel.** Formes fixes, FP16 GPU, cache,
    placement des nœuds et paramètres disponibles via `AJI_ORT_OPENVINO`.
36. **Comparer latence et débit contrôlé.** Tester le mode LATENCY puis un petit
    nombre de requêtes asynchrones. Éviter l'auto-batching qui retarde la lecture.
    [OpenVINO latency](https://docs.openvino.ai/2025/openvino-workflow/running-inference/optimize-inference/optimizing-latency.html).
37. **Ajouter un exécutant OpenVINO natif.** Départager appel direct et ORT à
    entrées/sorties comparables ; ensuite exploiter les capacités que le pont
    générique n'expose pas bien.
38. **Connecter des RemoteTensor aux surfaces vidéo.** OpenVINO documente les
    surfaces NV12 VAAPI sous Linux et les ressources OpenCL/DirectX partagées.
    Intégrer le prétraitement et garder les sorties accessibles au rendu, avec
    vérification des conversions couleur.
    [RemoteTensor GPU](https://docs.openvino.ai/2025/openvino-workflow/running-inference/inference-devices-and-modes/gpu-device/remote-tensor-api-gpu-plugin.html).
39. **Comparer GPU, NPU et distribution des modèles.** Les réseaux RIFE contiennent
    des opérateurs potentiellement moins adaptés au NPU. Vérifier support et coût
    de transfert avant tout partage du graphe ou des tuiles.

### MIGraphX, ROCm et AMD

40. **Activer et mesurer l'exhaustive tuning.** Le fournisseur local ne règle que
    device et FP16. Comparer le tuning aux choix par défaut, avec cache adapté aux
    versions du runtime et au GPU.
41. **Comparer les routes de convolution/layout.** MIOpen, rocMLIR et les options
    de compilation disponibles selon la version. hipBLASLt/rocBLAS concernent les
    GEMM réellement présents ; une variable GEMM n'accélère pas forcément toutes
    les convolutions. [MIGraphX EP](https://onnxruntime.ai/docs/execution-providers/MIGraphX-ExecutionProvider.html).
42. **Garder les tensors sur le GPU.** I/O Binding quand supporté, ou API MIGraphX
    native avec mémoire device et copies explicites maîtrisées. Le wrapper CPU
    actuel laisse une voie d'amélioration indépendante des tactiques.
43. **Étudier HIP Graphs et la concurrence.** Tester sur le programme compilé et
    les versions compatibles ; ne pas supposer une capture possible avec des
    allocations ou interactions hôte au milieu.
44. **Noyaux HIP/Composable Kernel ciblés.** Candidat après profilage, surtout pour
    opérations sans bonne fusion. Vérifier les instructions matricielles propres
    à l'architecture Radeon et sa compatibilité ROCm réelle.
    [Composable Kernel](https://rocm.docs.amd.com/projects/composable_kernel/en/latest/).

### NCNN/Vulkan et solutions de remplacement

45. **Optimiser les modèles convertis.** Lancer `ncnnoptimize`, comparer les graphes
    et les sorties ; la fusion Conv/activation existe dans l'outil épinglé.
    [ncnnoptimize](https://github.com/Tencent/ncnn/blob/d8227bbe4f0357640319a69660fe399664d8acc0/tools/ncnnoptimize.cpp).
46. **Observer les kernels choisis.** Winograd 2x3/4x3, SGEMM/direct, packings,
    accumulation FP16/FP32, matrices coopératives et tailles de workgroups.
    Plusieurs options sont déjà activées ; vérifier les voies effectivement prises.
    [Options épinglées](https://github.com/Tencent/ncnn/blob/d8227bbe4f0357640319a69660fe399664d8acc0/src/option.cpp),
    [Convolution épinglée](https://github.com/Tencent/ncnn/blob/d8227bbe4f0357640319a69660fe399664d8acc0/src/layer/vulkan/convolution_vulkan.cpp).
47. **Partager VkMat, allocations et soumissions entre étages.** Le pont actuel
    matérialise des ncnn::Mat CPU ; RIFE transforme aussi les images en RGB octets.
    Une chaîne persistante peut éviter ces retours et des attentes répétées.
48. **Créer quelques shaders SPAN spécialisés.** Tanh/Mul/Add, Reorg/PixelShuffle,
    puis convolutions dominantes si nécessaire. Sous-groupes, mémoire partagée,
    blocking et matrices coopératives sont les axes avant l'assembleur machine.
49. **Tester IREE sur SPAN puis RIFE.** Compilation du graphe en kernels et
    orchestration Vulkan/ROCm/CUDA/Metal ; vérifier import et couverture des
    opérateurs. C'est une alternative de compilateur, pas un changement d'API
    suffisant pour garantir une accélération.
    [IREE](https://iree.dev/), [Vulkan IREE](https://iree.dev/guides/deployment-configurations/gpu-vulkan/).
50. **Comparer MNN et, au besoin, TVM/autres compilateurs.** Prototypes isolés,
    mêmes poids/tailles/précision ; conserver uniquement les candidats qui
    améliorent la chaîne complète. Éviter de maintenir cinq nouveaux runtimes
    sans preuve. [MNN](https://github.com/alibaba/MNN).

Sur NVIDIA, TensorRT demeure le comparateur prioritaire ; sur Intel,
OpenVINO ; sur AMD Linux compatible, MIGraphX/ROCm. Un autre moteur Vulkan
garde un intérêt pour les appareils que ces routes ne couvrent pas.

### RIFE : optimisation de l'exécution et de la qualité

51. **API de paire persistante.** Préparer A/B une fois, demander plusieurs
    timesteps, puis réutiliser B comme A de la paire suivante. Cache des
    conversions, des images paddées et des décisions de scène.
52. **Éliminer les upscalings d'extrémités répétés en NCNN.** En RIFE après upscale
    ×4, le code actuel peut faire 7 appels à l'upscaler par intervalle : deux pour
    chacun des trois intermédiaires et un pour B. Un cache d'extrémités ramène
    cela à une nouvelle image source agrandie par intervalle après démarrage.
    Ce décompte n'est pas une accélération ×7 de la chaîne : RIFE et les copies
    restantes ont toujours un coût.
53. **Détecter scènes/dessins tenus une fois par paire.** TensorRT relit une valeur
    de scène sur le CPU puis attend le stream ; DML attend une fence et mappe un
    readback. Au minimum, supprimer les répétitions à ×3/×4/×8.
54. **Rendre la décision de scène asynchrone.** Remonter un statut dans un ticket,
    anticiper sur la paire suivante ou sélectionner la sortie côté GPU. Ce dernier
    choix peut conserver le calcul RIFE même sur une coupe : comparer le coût.
55. **Éviter les allers-retours YUV/RGB entre RIFE et SPAN.** Produire directement
    le tenseur du modèle suivant ; fusionner padding/prétraitement et crop/sortie.
56. **CUDA Graphs et timesteps groupés.** Capturer le calcul RIFE après la décision
    de scène et tester batch/concurrence sur les instants indépendants.
57. **Spécialiser grille et timestep.** Les quatre plans mesh/multipliers dépendent
    uniquement de la taille et sont déjà initialisés une fois dans le moteur.
    Les intégrer au graphe peut permettre du constant folding ; comparer aussi
    une variante t=0,5 ou les instants d'un facteur fixe, contre le coût de caches.
58. **Partager les features réellement indépendantes de t.** Certains modèles
    permettent de séparer encodeur et interpolation. Il faut inspecter le graphe
    précis ; les flots intermédiaires RIFE dépendent généralement de t. Réutiliser
    tout le flot pour trois instants différents serait une approximation.
59. **Accélérer warp/GridSample.** Fusion grille FP32, échantillonnage, mask/blend
    et épilogues, avec CUDA/HLSL/HIP/Metal selon le moteur. Cibler la bande passante
    et les casts ; préserver align_corners, padding et précision des coordonnées.
60. **Comparer variantes RIFE et ensemble.** Modèles légers, versions normales et
    ensemble sur un corpus anime. Le plus récent n'est pas automatiquement le plus
    rapide ni le meilleur subjectivement. NCNN est ici limité à 4.6 ; TRT/DML
    disposent d'une autre famille de versions, dont 4.26.
61. **Calcul du mouvement à résolution réduite.** Étudier un export RIFE avec
    pyramide/scale adaptée, puis synthèse haute résolution. Ce n'est pas simplement
    agrandir une sortie RIFE basse résolution ; les graphes ONNX livrés n'exposent
    pas forcément ce contrôle.
62. **Comparer l'ordre RIFE/SPAN.** RIFE avant upscale économise le calcul de
    mouvement haute résolution mais SPAN traite aussi les images générées. RIFE
    après upscale peut réutiliser les extrémités agrandies et traite plus de pixels.
    Comparer la chaîne entière et la qualité, pas RIFE seul.
63. **RIFE dans le moteur partagé/macOS.** Étendre Executor/Job aux deux images et
    au timestep, puis ajouter GridSample/warp et requêtes persistantes. La conversion
    native actuelle vise les SPAN spatiaux ; RIFE n'est pas un modèle à y déposer
    sans adaptation. Metal GPU est un premier candidat ; le NPU exige un contrôle
    explicite du support et du placement.
64. **Cadence et scènes anime.** Ne synthétiser que les instants utiles à la sortie,
    avec PTS rationnels/VFR corrects. Distinguer dessins volontairement tenus,
    coupes, fondus, pans, flashs et stroboscopie. Options esthétiques nécessaires
    pour préserver ou lisser l'animation sur deux/trois images.
65. **Réutilisation partielle avec mouvement.** Recherche : les déplacements et
    warps rendent le halo RIFE variable ; le halo SPAN ne suffit pas. Travailler
    sur régions avec contraintes de déplacement/confiance, puis vérifier coutures
    et occlusions. Une translation d'une sortie SPAN déjà calculée est également
    une approximation en présence de sous-pixels, bords et grille d'unshuffle.
66. **Rendu avant sous-titres et conversion HDR.** Éviter de faire interpoler texte
    et OSD externes ; les sous-titres incrustés exigent une stratégie différente.
    La conversion RIFE actuelle suit BT.709 : ne pas lui envoyer du PQ en supposant
    la fidélité d'un modèle HDR natif. Vérifier l'ordre effectif pour chaque moteur.
67. **Alternatives à RIFE.** NVOFA FRUC est un candidat NVIDIA Windows/Linux qui
    exploite le bloc optical flow ; il faut comparer sa qualité anime. AMT et
    EMA-VFI sont des comparateurs de recherche, avec un coût de conversion et
    d'intégration. Aucune garantie qu'ils battent RIFE en temps réel.
    [NVOFA FRUC](https://docs.nvidia.com/video-technologies/optical-flow-sdk/nvfruc-programming-guide/index.html),
    [AMT](https://github.com/MCG-NKU/AMT), [EMA-VFI](https://github.com/MCG-NJU/EMA-VFI),
    [Practical-RIFE](https://github.com/hzwer/Practical-RIFE).

### Précision, modèles entraînés et code bas niveau

68. **Précision mixte et quantification sélective.** FP16 existe déjà. INT8/FP8
    nécessitent support matériel/opérateurs, calibration anime et validation.
    Garder coordonnées RIFE et couches sensibles en précision supérieure ; ne pas
    confondre compression des poids et accélération des activations/convolutions.
69. **QAT si la calibration seule dégrade l'image.** Réentraîner en simulant la
    quantification ; préserver contours fins, aplats, gradients et stabilité
    temporelle. Une variante poids INT4 seule est moins prioritaire pour ces CNN.
70. **Réduire canaux/blocs par pruning structuré et distillation.** Le retrait
    aléatoire de canaux n'est pas une optimisation correcte. Avec réentraînement,
    48→32 canaux réduit théoriquement le coût des seules Conv internes C→C à
    environ 44 % ; ni le modèle complet ni les FPS ne suivent exactement ce ratio.
71. **Architectures plus efficaces.** Low-rank, convolutions groupées/depthwise,
    branches reparamétrées à l'inférence, espaces de features plus petits. Tester
    les kernels réels : un réseau à moins de FLOPs peut être plus lent si les
    fusions et unités matricielles sont moins bien utilisées.
72. **Modèles adaptés au contenu et au matériel.** Distiller des variantes pour
    SPAN rapide, NPU, codec/artefacts anime ou RIFE léger ; entraîner avec pertes
    de fidélité et temporelles. Ne pas multiplier les variantes sans corpus et
    sélection compréhensible pour l'utilisateur.
73. **SIMD CPU ciblé.** Conversions, resize, diff et packing : AVX2/F16C/NEON et
    bibliothèques existantes avant assembleur manuscrit. `exec_ort.cpp` utilise
    déjà F16C sur x86. Prévoir dispatch selon les capacités de la machine.
74. **Noyaux GPU spécialisés avant ISA manuscrite.** CUDA/CUTLASS, HIP/CK,
    HLSL/GLSL/Metal ; mesurer coalescence, occupancy, registres, mémoire partagée,
    instructions matricielles et reformats. PTX est une ISA intermédiaire, pas
    le code machine SASS final. L'ISA AMD/NVIDIA ne s'exécute pas sur le CPU ni
    sur toutes les générations de GPU.
75. **Assembler uniquement un noyau dominant démontré.** Un microkernel peut
    bénéficier d'instructions précises ; réécrire les bibliothèques fabricants
    complètes revient à un chantier de compilateur/runtime. Une optimisation
    d'une portion qui représente 5 % du temps, même divisée par deux, n'apporte
    qu'environ 2,6 % sur l'ensemble. [CUTLASS](https://docs.nvidia.com/cutlass/latest/overview.html).

Point de qualité crucial : `tools/convert_rife_fp16.py` du dépôt d'inférence
documente un historique où la grille entièrement FP16 fait passer la comparaison
avec la référence d'environ 48 à 32 dB. Le script maintient donc un îlot FP32
pour la construction des coordonnées et GridSample. Ces chiffres proviennent
de cet historique, pas d'une mesure exécutée aujourd'hui. Ils interdisent de
présenter « tout convertir en FP16 » comme une amélioration gratuite.

## Classement par potentiel maximal, sans critère de difficulté

À la demande de l'utilisateur, l'effort, la taille et la complexité du chantier
ne doivent pas réduire son rang. Le tableau suivant est une appréciation du
potentiel sur ce projet, pas un classement de facteurs d'accélération mesurés.
La machine, le modèle, le facteur RIFE et le contenu peuvent inverser plusieurs
rangs. Les chantiers se recouvrent : un moteur maison peut intégrer la plupart
des autres optimisations, et leurs gains ne s'additionnent pas indépendamment.
Matériel identique et résolution/cadence de sortie identiques sont les bases de
comparaison ; les changements de modèle demandent de démontrer une qualité
perceptuelle au moins équivalente.

| Rang | Chantier | Origine du potentiel | Condition de fidélité |
|---|---|---|---|
| 1 | Concevoir et entraîner un modèle conjoint interpolation + super-résolution, adapté au matériel | Mutualiser les features et reconstruire directement les images finales ; réduire le travail demandé avant de l'exécuter | Nouvelle architecture : fidélité anime et stabilité temporelle à démontrer |
| 2 | Inférence conditionnelle et réutilisation spatiale/temporelle | Ne recalculer que les images ou régions réellement nouvelles | Cache exact avec dépendances complètes ; mouvement compensé ou seuils perceptuels sont des approximations |
| 3 | Moteur/compilateur maison spécialisé pour SPAN et RIFE, de bout en bout | Noyaux matriciels optimisés par architecture, fusion des opérations, placements mémoire et ordonnanceur adaptés au réseau entier | Poids conservés possibles ; changements d'arrondi à valider |
| 4 | Éliminer les calculs répétés actuellement présents | Cache des extrémités agrandies et préparation RIFE par paire ; jusqu'à 7→1 appels SPAN par intervalle dans le cas NCNN après upscale ×4 | Même calcul utile et mêmes PTS ; aucun facteur ×7 promis pour la chaîne entière |
| 5 | Remplacer les convolutions et opérateurs dominants inefficaces | Moteurs fabricants ou microkernels spécialisés exploitant efficacement les unités matricielles ; écart NCNN/TRT historique d'environ 6 sur NVIDIA | Modèle/forme conservés, précision contrôlée ; pas de gain équivalent garanti face à TRT déjà performant |
| 6 | Quantification, pruning/distillation et sparsité matériellement accélérée | Réduire les opérations, les octets et augmenter le débit des unités arithmétiques | Calibration/réentraînement et qualité temporelle à vérifier ; couches sensibles en précision supérieure |
| 7 | RIFE multi-instant avec extraction de features partagée et warp spécialisé | Éviter de recalculer les portions indépendantes du timestep ; fusion grille/échantillonnage/blend | Identifier réellement les dépendances en t ; aucun cache arbitraire du flot |
| 8 | Chaîne entièrement résidente sur GPU | Éliminer transferts CPU, matérialisations RGB24 et conversions entre modèles | Couleurs/range/precision identiques ; interopération du décodeur et du rendu à construire |
| 9 | GPU + NPU ou plusieurs GPU déjà disponibles, avec orchestration adaptée | Exécuter des travaux indépendants sur des processeurs distincts | Les transferts et replis CPU peuvent annuler le bénéfice |
| 10 | Estimation de mouvement RIFE à échelles mieux adaptées | Réduire le calcul de mouvement, conserver une synthèse finale haute résolution | Adaptation/export/réentraînement selon le modèle ; qualité des déplacements à établir |
| 11 | Spécialisation des graphes, layouts et fusions existantes | Formes fixes, constantes calculées une fois, suppression de reformats et opérateurs auxiliaires | Même réseau ; comparer les sorties et le padding |
| 12 | Autotuning approfondi des tactiques, grilles et modes mémoire | Choisir la meilleure implémentation pour chaque GPU, modèle et forme | Gain propre à la configuration et à la charge réelle |
| 13 | Graph replay, requêtes asynchrones et réduction des attentes | Réduire le coût des lancements et chevaucher les étages | Débit et latence à mesurer séparément ; dépendances préservées |
| 14 | Optimisation SIMD/assembleur des tâches CPU restantes | Accélérer conversions, resize, diff et orchestration qui occupent réellement le CPU | Bénéfice borné par leur part du temps total |
| 15 | Traduction en assembleur sans changer algorithmes, mémoire ni ordonnanceur | Seules les différences de code machine produit pourraient apporter un gain | Gain pouvant être nul ou négatif ; aucun bénéfice lié au seul langage |

Le rang 1 est une piste de recherche : l'existence de méthodes conjointes est
établie, mais leur supériorité sur notre chaîne à qualité anime comparable n'a
pas été démontrée. Exemple de méthode :
[Zooming Slow-Mo, implémentation officielle CVPR 2020](https://github.com/Mukosame/Zooming-Slow-Mo-CVPR-2020).

Pour conserver les poids et la fonction des modèles actuels, considérer les
rangs 2 à 5 comme les principaux leviers, puis les rangs 7 à 9. Sur images
toutes nouvelles, le rang 2 ne supprime pas d'inférence et les rangs 3/5 remontent.
Un moteur maison à noyaux GPU en assembleur est bien inclus au rang 3 : son
potentiel vient de sa spécialisation et de son architecture, pas de son langage.
Réécrire en assembleur CPU un calcul actuellement exécuté sur GPU change de
processeur et ne constitue pas une accélération GPU comparable.

## Séquence de validation des expériences

Cette séquence organise les mesures et comparaisons. Elle n'est pas un classement
du potentiel maximal ni une limite sur l'ambition du chantier.

| Ordre | Chantier | Pourquoi commencer ici | Validation décisive |
|---|---|---|---|
| 1 | Instrumentation et corpus commun | Rend tous les comparatifs exploitables. | Timings GPU/chaîne, warm-up exclu, mêmes images et formes. |
| 2 | Cache des extrémités NCNN et préparation RIFE par paire | Travail répété visible dans les sources. | Décompte des appels, sorties équivalentes, seeks/PTS corrects. |
| 3 | Formes fixes DirectML et `ncnnoptimize` | Expériences ciblées sans nouveau runtime. | Latence, partitions/fusions, comparaison de tous les pixels. |
| 4 | Tuning et I/O GPU OpenVINO/MIGraphX | Pont CPU actuel et options peu explorées. | Test matériel Intel/AMD, transferts et replis mesurés. |
| 5 | Segments capturés TRT/RIFE et fusions de conversion | Infrastructure déjà en partie présente. | Timeline montrant moins de lancements/attentes sans latence accrue. |
| 6 | TensorRT for RTX et OpenVINO/MIGraphX natifs | Candidats concrets pour le déploiement et l'interopération. | Comparaison isolée puis lecteur complet. |
| 7 | NCNN kernels/interop et prototype IREE | Peut améliorer la route de compatibilité. | Battre le NCNN optimisé avec même précision et qualité. |
| 8 | RIFE natif Mac et moteurs d'interpolation alternatifs | Fonctionnalité manquante et nouvelles voies matérielles. | Support des opérateurs, qualité anime, cadence stable. |
| 9 | Quantification, distillation et microkernels | Gains possibles mais coût/risque de qualité plus élevés. | Courbe qualité/latence/énergie sur corpus représentatif. |

## Mesurer un gain utilisable

Comparer au minimum SPAN Performance et Balanced à 540p, 720p, 1080p ; RIFE
seul puis SPAN+RIFE ×2/×4 et facteurs rationnels ; réutilisation désactivée puis
activée. Mesurer calcul intégral sur images différentes et épisodes réels avec
dessins tenus. Les gains moyens de réutilisation ne décrivent pas les pointes
de calcul sur un pan ou une coupe.

Rapporter médiane, p95/p99, FPS effectifs, images perdues, temps de démarrage,
VRAM, consommation et comportement après échauffement. Les optimisations doivent
laisser une marge pour décodage/HDR/rendu : 41,7 ms à 24 i/s et 16,7 ms à 60 i/s
sont des budgets totaux, pas des budgets réservés au réseau.

Valider clips de traits fins, textures, aplats/gradients, mouvement rapide,
occlusions, fondus, sous-titres incrustés et coupes. Comparaison pixel/PSNR/SSIM
pour les transformations équivalentes ; examen visuel et temporel pour les
approximations. Un bon score spatial moyen ne suffit pas à certifier l'absence
de scintillement ou de contours déformés.

Les caches doivent dépendre des vrais identifiants/contenus d'images, formes,
profil, modèle, précision et paramètres couleur ; les pointeurs de textures
réutilisées ne sont pas des clés suffisantes. Invalider après seek, changement
de fichier, de résolution ou de configuration. Garder les mêmes PTS, règles de
fin de fichier et couleurs qu'avant.

Les sources propriétaires TensorRT/DirectML/Core ML ne se réécrivent pas en
place : l'application peut modifier ses graphes, ses raccords et ses noyaux,
ou proposer un moteur/plugin alternatif. La stratégie la plus crédible est de
supprimer le calcul et les transferts inutiles, puis de spécialiser les quelques
noyaux coûteux que les runtimes existants exécutent mal.
