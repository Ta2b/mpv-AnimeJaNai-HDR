# Lot 24 — activations RIFE CPU natives et fidèles

AH-270 sous AH-68 ; autres activations/runtimes/matériels AH-271. Base .55 `71bd9acfdbcd0b5bbe516fc37960f11ca8c3fc72`, source moteur `9f04bee0e42840be0c24237110e097ede91930a1`. Worktree isolé ; sources utilisateur préservées. Modèles et poids installés inchangés.

## Optimisation livrée

ORT1.24.1 CPU développait chacun des53 LeakyRelu FP16 du RIFE livré en Less/Mul/Where, exécutés en FLOAT avec alpha `0.20000000298023224`. Un opérateur CPU natif applique cette comparaison et multiplication en un passage, sans exposer de nouvelles fusions Conv/activation ni supprimer une frontière d’arrondi du programme de référence. La forme de sortie est inférée et validée ; métadonnées empruntées pendant la durée du tenseur, sans handle possédé par invocation. Une sous-normale négative dont la multiplication sous-déborde est normalisée en +0 comme le Mul de référence ; un input -0 lui-même est conservé.

La transformation en mémoire introduit CastFLOAT→opérateur natif→CastFLOAT16 ; les passes ORT retirent les conversions libres comme dans la référence. Les poids, alpha et tous les nœuds/champs non concernés sont préservés ; le fichier du modèle et les caches flow existants ne sont pas réécrits. Le domaine/opérateur est intégré à `libaji_ort`, sans nouvelle bibliothèque à installer, créé une fois et conservé jusqu’au déchargement du moteur. Aucun `InitApi` manuel dans le produit.

**Activation par défaut bornée au périmètre qualifié** : Linux x86-64, provider CPU, runtime ORT1.24.1, optimiseur ORT_ALL3 et contenu exact RIFE4.26 image ou son export flow v2. SHA256 complets, poids inclus : image `fd6b06538898c9a94d20f0fe55febceadbcde5ad64952240733b7275ef4c9d59`, flow `4d93a8a394cc1a1dd20d7efc2fcbace769f289dd655d0f76f941f533ffbbc216`. Un autre modèle/export/poids, runtime, provider, OS ou optimiseur conserve sa voie de référence. `AJI_ORT_CPU_ACTIVATIONS=0` désactive cette optimisation. Une erreur de préparation/compilation revient au graphe original en gardant l’interpolation active.

Le hash et les copies de préparation coûtent du temps/mémoire au configure ; aucun gain de démarrage/RAM totale annoncé. Il n’existe pas de nouveau cache compilé persistant CPU à invalider ; l’export original et ses poids restent la référence.

## Qualification courte

Même machine, modèles, réglages, entrées RGB24/strides et paramètres par comparaison ; références valides déjà acquises réutilisées. Premier intervalle exclu, deux nouvelles paires par candidat. Captures C API du vrai modèle chargé, formes et graphe optimisé ; toutes les sorties, dont warm-up/endpoints et source après reconfiguration, comparées bit à bit.

| Chemin réel | Nœuds optimisés avant→après | Autres calculs conservés | Sorties |
|---|---:|---|---|
| Quality RIFE+SPAN FP16, 128×72 | 483→377 | Conv53, Cast41, Reorder51/52, Add50 identiques | 8, 0 octet différent |
| Fast flow/mask + SPAN tuilé/deux exécuteurs, 256×72 | 484→378 | Conv53, Cast42, Reorder51/52, Add50 identiques | 8, 0 octet différent |

Chaque graphe remplace53 Less/53 Mul/53 Where par53 AjiLeakyReluF32 : **106 nœuds d’exécution et leurs matérialisations intermédiaires supprimés**, sans ajouter de calcul neuronal ni changer les convolutions/layouts. SPAN est identique à47 nœuds. La borne de descripteurs applicatifs du lot21 est conservée : créations MemoryInfo/tenseurs/handles possédés et demandes de sortie non préallouée restent à0 dans la fenêtre chaude. Les lectures de forme empruntée supplémentaires ne sont pas des allocations ; aucune promesse de zéro allocation interne ORT.

Quality : inférence RIFE de deux runs36,4194→29,7138ms ; chaîne46,3291→37,4392ms. Fast : chaîne132,6936→122,6149ms. **Gain temporel soutenu/FPS non concluant**, références réutilisées, observations courtes, état bureau/alimentation non contrôlé ; aucun prolongement automatique. Le bénéfice retenu et directement établi est la suppression des opérations/intermédiaires, avec parité des pixels. Profiling Quality identique dans les deux branches ; Fast sans profiling dans les deux branches.

Contrôle indépendant de l’opérateur, runtime SDK1.24.1 : un vecteur de56 valeurs FP32 de frontière/proximité (signes, ±0, sous-normales, normales minimales, extrêmes finis, ±inf, NaN/payloads). Comparaison byte à byte avec les vrais kernels ORT Less/Mul/Where. Premier échec limité à quatre sous-débordements négatifs (-0 candidat/+0 référence), corrigé ; vecteur en échec retesté, **56/56 identiques**. Aucun modèle concluant rejoué pour cette correction.

Contrôle structurel des deux graphes qualifiés : poids et nœuds non concernés identiques ; restaurer les nœuds transformés et retirer l’opset ajouté restitue le modèle complet. Changer un octet de contenu rend le graphe inéligible sans transformation. Deux contrôles configure-only : flag0 restitue exactement le graphe de référence ; erreur de compilation injectée dans la seule variante native revient également à ce graphe, toujours483 nœuds et facteur d’interpolation2 actif. Pas de répétition de frames pour ces contrôles.

### Diagnostics et voies écartées

Le prototype Cast/native LeakyRelu standard/Cast exposait de nouvelles fusions :483→337 nœuds mais2674 octets changés/max1, donc écarté. Désactiver ConvActivationFusion/ConvAddFusion ne retirait pas les fusions propres à NCHWc : graphe/pixels inchangés, pas de conclusion causale inventée ni répétition de cette variante. L’opérateur isolé permet ensuite la parité sans ces fusions.

Le premier DSO prototype partageait son état global C++ d’API avec le host : captures incomplètes (2 au lieu de4), mesures C API invalides. Diagnostic conservé et exclu de la qualification finale ; visibilité C++ cachée pour le prototype, puis opérateur intégré sans réinitialisation manuelle dans le produit. Les captures finales comprennent les4/6 sessions attendues, reconfiguration comprise.

Artefacts locaux : `artifacts/performance/lots-20261016/lot-24/`, specs/logs/NPZ/stats/captures/reçus des prototypes, `integrated-quality/summary.json`, `integrated-fast/summary.json`, `graph-check/summary.json`, `fallback/summary.json`, vecteur/diagnostic/final de l’opérateur et builds. Commandes : `cpu_leaky_relu_check`, `cpu_activation_graph_check.py graph.spec.json`, `ort_activation_check.py integrated-quality.spec.json`/`integrated-fast.spec.json`, `cpu_activation_fallback_check.py fallback.spec.json`. Build CMake Release AVX/F16C sans fast-math, syntaxe Python et `git diff --check` réussis. ABI publique `aji_vk_*` conservée.

## Décision et livraison

Conserver l’optimisation dans ce périmètre pour la réduction utile de matérialisations établie et la sortie exacte. Release **3.8.0.56**, pin GPU/Manager inchangé. Sources partagées compilées Linux/macOS ; activation native limitée au périmètre ci-dessus. AH-270 Done après publication vérifiée ; parent AH-68/AH-271 restent ouverts. Aucune qualification Apple/Windows/autre CPU/runtime inventée.

Piste suivante : le moteur CPU Fast utilise encore un graphe à trois sorties (image, flow, mask), tout en demandant flow/mask. Étudier une spécialisation aux seules sorties utiles et vérifier les kernels réellement évités avant de conclure à un gain ; aucun coût inutile encore mesuré pour cette piste.
