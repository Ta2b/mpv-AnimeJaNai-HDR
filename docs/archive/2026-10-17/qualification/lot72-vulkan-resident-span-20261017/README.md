# AH-351 — SPAN vers SPAN résident Vulkan

Le 17 octobre 2026, Linux / NVIDIA RTX 4070 Ti, driver615.78.08. Deux vrais modèles SPAN Performance différents, entrée de contours/dégradés128×128, puis256×256 et512×512. Modèles, poids, options NCNN et frontières inchangés. [Reçu](receipt.json), [hashes des modèles privés copiés](model-hashes.json), configurations jointes.

## Résultat et décision

- Ancien binaire .93, candidat avec ablation off et candidat on : **pixels RGB24 exacts**, SHA256 `2a83161af4b3b29bc77adf0d7e99c5dae823abe28af2784e24534a3e7f0e2f9d` ; deux inférences dans chaque cas. Padding de sortie intact.
- Deux adaptateurs hôte (un par modèle) deviennent un segment avec **un upload initial et un download final explicites**, comptés aux vrais appels NCNN. Aucun adaptateur hôte à l’intérieur du segment. Les copies éventuelles internes du driver ne sont pas présentées comme supprimées.
- Une seule observation courte après la première sortie, trois appels complets par voie : médiane **3.214 → 2.337 ms**, soit environ **27.3%** de temps en moins pour ce petit cas. Plages visibles dans le reçu ; aucune extrapolation à720p, FPS affichés ou autres GPU. Arrêt après cette conclusion suffisante.
- Resize50% entre les modèles : voie hôte conservée et pixels exacts au binaire de base. Erreur contrôlée au second modèle avant soumission : destination inchangée, erreur latched, refus de réutilisation, reconfigure puis sortie exacte.
- Le shader réellement utilisé conserve les deux multiplications F32. Contrôle du domaine FP16 fini dans196608cases par stockage cible (F32 et F16), valeurs finales F32 bit à bit identiques aux conversions/multiplications CPU. Les codes NaN/Inf de la grille de bits sont remplacés par zéro ; aucun résultat sur leur propagation n’est revendiqué.

Utilité établie : transfert intermédiaire supprimé et gain local observé, qualité préservée sur ces contrôles. Activation pour les segments éligibles ; `AJI_VK_RESIDENT_SPAN=0` conserve l’ablation sans changer les profils. Aucun changement de modèle, de précision, de Winograd/cooperative-matrix ou de stratégie AMD/Intel.

## Implémentation et ownership

`aji_vulkan.cpp` choisit des segments maximaux sur le même device, au moins deux SPAN, toutes les couches sur Vulkan et aucun resize effectif intermédiaire. L’éligibilité des couches est calculée une fois au chargement. Premier resize/normalisation et dernier denormalize/ABI RGB24 restent ceux de la référence. Une préparation ou un endpoint encore hôte reste hôte.

`span_resident.h` convertit la sortie vers le F32 unpacked de référence, fait255 puis la constante F32 exacte1/255 avec `precise`, puis la conversion NCNN de l’upload suivant. Aucun clamp/cast RGB8 ajouté entre SPAN. Le compilateur utilise le device effectivement choisi ; la surcharge NCNN avec longueur explicite évite sa troncature de chaîne. Le premier essai a détecté cette erreur de raccord et s’est arrêté ; seule sa correction a été rejouée.

Workspace synchrone : allocateurs récupérés en dernier, après tensors/extractors/commandes. Owners des frontières conservés jusqu’à la complétion, pas de thread ou second ordonnanceur. Échec de soumission/wait : device idle avant libération et contexte refusé jusqu’à reconfigure ; l’essai de défaut porte sur un échec avant soumission, pas une perte physique de GPU. Aucune sortie partielle publiée.

## Sources, build et livraison

Base PLAYER `04b3cb524a85fc54f6c05abc4441fef79682e98d` (.93). NCNN `d8227bbe4f0357640319a69660fe399664d8acc0`, RIFE `a7532fc3f9f8f008cd6eecd6f2ffe2a9698e0cf7`, parseurv0.11.1 (`8cb3c65`). Source amont et installation utilisateur intacts. Build Linux local complet de base, puis seul objet du pont candidat recompilé/liée contre les mêmes NCNN/RIFE/parser ; aucun réglage noyau changé. Le reçu distingue les deux hashes de bibliothèques locales.

Après le contrôle, seuls le cache d’éligibilité statique, la réservation des owners et l’index explicite du même device0 ont été finalisés/compilés ; shader et calculs inchangés. La release .94 a reconstruit et livré le module complet, hash `031dc1f8befc57cecc1d6f976ffc64e984219e8ec8fb38a2a657020c435f9857`. Marqueur et source vérifiés ; une sortie native du paquet égale à la référence acquise, avec2inférences/1upload/1download/0adaptateurhôte. Trois CI et15assets vérifiés ; [reçu de livraison](../../jira/release-20261017-3.8.0.94.json). AH351 Done. Mesure et scénarios concluants non répétés.

Linux Vulkan/NVIDIA qualifié. AMD, Intel et MoltenVK non exécutés ; aucun résultat matériel inventé. RIFE→SPAN résident et jonction vers le rendu restent dans AH131, qui ne peut pas être clos avec cette première tranche. Le bundle spécialisé CUDA et les chemins Metal/CoreML restent inchangés.
