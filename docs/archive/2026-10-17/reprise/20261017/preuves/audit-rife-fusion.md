# Audit ciblé RIFE / fusion — 17 octobre 2026

Lecture seule de `/tmp/animejanai-backend-remove-fruc-20261017`, HEAD `36f3d94491b51d334dc9420ce6d5192b086b0a8f`, et du patch filtre courant dans `lot-57-manager-ux-20261017`. Aucun GPU, profil utilisateur, commit, push ou ticket modifié. Référence .82/.83 et lot55 consultés pour éviter de reproposer les gains déjà acquis.

## Résultat de la revue

Quality reste sur les prédictions RGB complètes (`src/aji_trt.cpp:3809–3864`, appel `4078`) ; motion-only est protégé par `conf.rife_warp`, avant upscale, sans ensemble (`1242`, `1345`, `2576`). Le cache exact de préparation conserve les prédictions et le score scène, avec promotion seulement sur ID, vue et stream concordants (`3593–3619`, `3936–3951`). Les constats ci-dessous ne justifient donc pas une refonte de l'algorithme Quality.

Fast ×4 et plus est une approximation explicite : une prédiction de mouvement à t=0.5 sert les phases, même si le mouvement est grand (`3963–3975`, `4054–4060`), puis blend paramétré (`2646–2651`). Cette politique explique le gain déjà acquis ; il ne faut pas l'étendre à Quality. Le plan conserve l'exception Fast ×2 (`src/pipeline_config.cpp:193–205`) et la garde de resize avant fusion (`src/aji_pipeline.cpp:198–206`). Les nouveaux travaux FRUC/Spline36 n'ont pas modifié `aji_trt.cpp` depuis la référence fusion.

## 1. Prioritaire — score de mouvement inutile pour Fast facteur >3

- **Preuve :** `src/aji_trt.cpp:4013–4029` alloue/écrit/lit le maximum du flot ; `4046–4053` attend et décode le score. Or `4058–4060` impose, dès que `R.num/R.den > 3+1e-9`, `single = middle` et `prev_split = false`. Après configuration/reset, `prev_split=false`, donc `middle=true` pour chaque nouvelle paire ; le score ne participe jamais à la décision de ces facteurs.
- **Coût établi par code :** par nouvelle paire Fast ×4…×8 fusionnée : 1 memset scalaire, 1 réduction sur le flot, 1 copie device→host et 1 attente hôte de la fin du stream motion. Aucune économie de prédiction neuronale annoncée.
- **Alternative bornée :** garder exactement l'inférence motion à .5, les endpoints, la formule du blend et les compteurs ; court-circuiter le maximum pour les seuls facteurs >3 ; en mode overlap, enregistrer un événement de fin du mouvement et faire attendre le stream de restitution GPU (l'attente scalaire assurait aussi cette dépendance). Conserver la voie actuelle pour facteurs ≤3. Ne pas seulement supprimer le `scalar_wait`, ce qui introduirait une course.
- **Portée/validation :** TensorRT/CUDA Fast uniquement. Revue de l'ordre des streams + compilation ; essai court seulement si une incertitude de synchronisation subsiste. Gain de travail CPU/GPU établi, gain ms/FPS non mesuré.

## 2. Mémoire RIFE — deux buffers YUV de padding non utilisés dans la voie fusionnée

- **Preuve :** `src/aji_trt.cpp:3645–3668` alloue puis remplit systématiquement `R.pad_a` et `R.pad_b`. Avec `AJI_RIFE_FUSED_PRE` actif par défaut, les branches `3701–3712` sautent toutes les copies vers ces pads et `3744–3754` convertissent directement les sources avec padding dans `R.in_tensor`. Les deux pads ne sont alors jamais lus. `R.pad_o` reste nécessaire à la sortie complète.
- **Coût établi :** 12×pw×ph octets inutilisés par contexte RIFE YUV444P16 (11,25 MiB à 1280×768, 23,91 MiB à 1920×1088), plus six fills initiaux ; NV12/P010 : respectivement 3×pw×ph / 6×pw×ph octets. La voie ordonnée canonise toujours en 444P16.
- **Alternative bornée :** allouer/remplir uniquement les deux pads d'entrée lorsqu'on sélectionne réellement le fallback non fusionné ; garder le pad de sortie et les plans chroma nécessaires. Conserver un état d'initialisation distinct du format pour permettre la modification de l'ablation d'environnement entre appels, ou figer/documenter son choix au contexte.
- **Portée/validation :** Quality et Fast CUDA, aucune arithmétique ni prédiction changée. Revue des reprises allocation/format/teardown et compilation suffisent pour le bénéfice mémoire statique ; ne pas revendiquer de FPS.

## 3. Chaîne — N barrières CPU pour recopier les N sorties d'une paire

- **Preuve :** `src/aji_pipeline.cpp:304–311` lance trois copies 2D puis synchronise le stream. `414–417` rappelle cette fonction pour chaque sortie. Le filtre ne publie aucune sortie avant la complétion du ticket (`native/linux-cuda/vf_animejanai-pipeline.patch:191–205`) ; toutes les sources `points` et sorties du job vivent jusqu'à la fin de `run`.
- **Coût établi :** facteur F ⇒ 3F copies D2D et F attentes hôte de sortie ; charge transport = 6×W×H×F octets copiés, soit 88,47 Mo par paire à 2560×1440 ×4 (lecture+écriture DRAM = au moins deux fois cela). Le débit effectif n'est pas mesuré.
- **Alternative immédiate bornée :** déplacer l'attente hors de `copy` et synchroniser une seule fois après la boucle finale. Préserver copies, ordre du stream, owners, signal de complétion, et drainage d'erreur existant. F−1 barrières hôte supprimées ; aucune modification de pixels.
- **Suite plus large, séparée :** orienter les écritures du dernier étage directement vers les surfaces du job pour supprimer des copies finales, mais conserver un stockage possédé pour le dernier endpoint mis en cache. Cela demande une vraie refonte de destination/lifetime et n'est pas nécessaire au petit correctif de barrières.
- **Portée/validation :** pipeline CUDA ordonné, toutes politiques, aucun changement moteur/vidéo. Revue de la durée de vie et compilation. Les barrières des appels `aji_surface_process_v1` entre étages (`src/surface_cuda_impl.h:247,261`) sont un autre chantier : elles ne peuvent pas être retirées sans relier les streams de contextes distincts et de resize/HDR.

## Limites de fusion à ne pas masquer

Le lot55 prouve l'identité Quality pour les cas réellement comparés ; son cas quatre maillons utilise identité×1→Q2→F2→SPAN, pas deux vrais upscalers successifs. `pipeline_execution_block_end` regroupe aussi les upscalers consécutifs (`pipeline_config.cpp:204`), dont `run_steps` enchaîne les tenseurs FP16 sans aller-retour YUV (`aji_trt.cpp:2853–2876`). Ce comportement est déjà présent dans le plan de référence : ne pas déclarer soudain une régression .83, ni prétendre que l'ablation fusion=0 teste ces frontières (elle continue à grouper les upscalers). Si l'on change ce plan ultérieurement, définir la frontière numérique de référence et couvrir spécifiquement deux modèles non identité.

Décision proposée : aucun remplacement d'algorithme RIFE complet ; prendre d'abord 1 et 3 (travail redondant prouvé), puis 2 (mémoire). Ownership d'implémentation demandé au parent avant toute édition. AH-344/DirectML est volontairement hors périmètre de cette revue.
