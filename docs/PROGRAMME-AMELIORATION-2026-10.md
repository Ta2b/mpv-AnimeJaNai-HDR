# Programme d'amélioration — octobre 2026

Écrit le 17 octobre 2026 au soir à partir de [l'audit performances, qualité et Manager](AUDIT-PERFORMANCE-QUALITE-MANAGER-2026-10-17.md). Objectif fixé par l'utilisateur : performances maximales sans perte de qualité, gains de qualité à faible coût, plus de choix d'interpolation, un logiciel plus complet, sur tous les GPU et tous les systèmes. Chaque piste a un ticket Jira ; les gains sont des estimations tant qu'ils ne sont pas mesurés sur le jeu de référence.

## 1. Étude : interpolation temps réel pour l'anime

### 1.1 Budgets réels à 24 i/s sur RTX 4070 Ti

Une paire source dure 41,7 ms. Coûts fixes mesurés pour une sortie 1440p : SPAN Performance 4,1 ms par image, TrueHDR 1,7 ms par image, Area 0,8 ms par paire (banc du 14 octobre, trace du lot 62).

| Facteur | Images interpolées par paire | Coût fixe (SPAN + HDR des sorties, Area) | Budget par image interpolée |
|---|---:|---:|---:|
| ×4 | 3 | 24,0 ms | **5,9 ms** |
| ×3 | 2 | 18,2 ms | **11,7 ms** |
| ×2 | 1 | 12,4 ms | **29 ms** |
| ×1,5 | 1 pour deux paires | 19,0 ms pour deux paires | **64 ms** |

Lecture immédiate : RIFE 4.26 (7,9 ms) dépasse le budget ×4 de 2 ms par image, d'où les 46,4 ms mesurés ; **×3 Quality tient le budget aujourd'hui** (2 × 7,9 + 18,2 ≈ 34 ms, 72 i/s sur un écran 165 Hz) ; HDR mpv au lieu de TrueHDR déplace 6,9 ms par paire hors du pipeline d'inférence vers le rendu ; SPAN Balanced (7,5 ms) ramène le budget ×2 à 22 ms.

### 1.2 Candidats et verdicts

| Méthode | Vitesse connue | Intérêt anime | Facteur réaliste | Ticket |
|---|---|---|---|---|
| RIFE 4.26 TensorRT | 7,9 ms à 1280×768 (mesuré) | généraliste, le plus rapide à qualité égale | ×3 maintenant, ×4 après AH-376/372/373 | livré |
| RIFE 4.15-lite / 4.22-lite / 4.25 | 6,4 / 7,8 / 8,4 ms (mesurés) | qualité inférieure, gain négligeable | variante Fast seulement | AH-140 |
| RIFE 4.26-heavy | 34,3 ms (mesuré) | meilleure qualité RIFE | ×1,5 seulement | AH-140 |
| **DRBA / DistilDRBA** sur RIFE | ≈ RIFE + contrôle | conçu pour l'animation sur deux ou trois images : conserve le rythme des poses au lieu de tout lisser ; voie TensorRT documentée (vs-drba) | ×3, ×4 | **AH-143, AH-303 : priorité 1** |
| AMT-S | léger, pas de chiffre 1080p publié | à mesurer | ×2, peut-être ×3 | AH-144 |
| IFRNet-S | benchmarké à 720p sur V100 parmi les plus rapides | à mesurer | ×2, peut-être ×3 | AH-145 |
| EMA-VFI small | 25 ms contre 10 ms pour RIFE à 512² sur 2080 Ti, soit ≈ 2,5 × RIFE → ≈ 20 ms à 720p ici | à mesurer | ×2 | AH-158 |
| GMFSS Fortuna | 213 ms par image en eager FP32 à 720p (lot 38 : préparation 150 ms, synthèse 65 ms, softsplat 6 ms) | référence de qualité anime | ×1,5 après port TensorRT (GMFlow + softsplat en plugin), ×2 si ≤ 29 ms | AH-141, AH-165 |
| FrameFusion | 37 Mo, réutilisation multi-instant, pas de mesure publique | à mesurer | ×2 ? | AH-306 |
| BiM-VFI | 151 ms à 720p (article) | mouvement non uniforme | ×1,5 au mieux | AH-146 |
| SG-RIFE | 50 ms à 720×480 sur L4 | sémantique DINOv3 | hors temps réel | AH-305 |
| EISAI / SoftsplatLite | 0,45 s sans SGM | conservation des traits | préparation hors ligne | AH-304 |
| GIMM-VFI, SPEED, FILM, VFIMamba… | lourds ou lents dans les mesures publiées | généralistes | préparation hors ligne | AH-147, 148, 157… (Low) |
| Wan 2.2/2.7, Seedance 2.5, ToonCrafter, MiniMax H3, Trajectory-Guided | minutes par plan | création entre dessins clés, pas interpolation fidèle | hors ligne | AH-307 à AH-312 (`generatif`) |
| NVIDIA Smooth Motion, AMD AMF FRC, VideoToolbox | coût pilote | sans contrôle du rythme ni de la qualité | secours | réglage existant, AH-156, AH-150 |

Sources : comparatif du 16 octobre (dépôts officiels, SVP, SVFI, articles), [IFRNet](https://arxiv.org/pdf/2205.14620), [AMT](https://arxiv.org/pdf/2304.09790), [sparse global matching, tableau EMA-VFI/RIFE](https://arxiv.org/pdf/2404.06913), [BiM-VFI](https://arxiv.org/pdf/2412.11365), [vs-drba](https://pypi.org/project/vsdrba/), [DRBA](https://github.com/routineLife1/DRBA), rapport du lot 38 (archive). Les chiffres publiés viennent de GPU et de résolutions différents : ils classent la faisabilité, pas la qualité.

### 1.3 Ce qui manque pour offrir le choix

- La porte de faisabilité commune et le tableau comparatif : **AH-377**.
- Les facteurs fractionnaires ×1,5 et ×2,5 dans le pipeline ordonné, sans lesquels les méthodes lourdes n'ont pas de place : **AH-375**.
- Un harnais de parité qui compare chaque moteur à la même référence FP32 : **AH-378**.
- L'affichage du coût et du verdict dans le Manager, pour que le choix soit informé : **AH-380**.
- Le mode DRBA comme vrai réglage anime (« lisser tout » ou « conserver le rythme des poses ») : AH-143.

## 2. Programme par angle

### A. Moteur NVIDIA, budget Quality ×4

| # | Levier | Gain estimé | Ticket |
|---|---|---:|---|
| 1 | SPAN batch 4 | 2,5 à 5 ms | AH-376 (ex AH-358) |
| 2 | Encodeur RIFE partagé entre instants | 0,5 à 1,5 ms | AH-376 (ex AH-357), AH-73 |
| 3 | Padding RIFE 32 au lieu de 64 | ≈ 1 ms | AH-373 |
| 4 | Remise RGB FP16 directe RIFE → SPAN | 0,5 à 1 ms | AH-74 |
| 5 | TrueHDR sur le stream du pipeline | 0,5 à 1,5 ms | AH-372 |
| 6 | Deux tickets en vol | 0,5 à 2 ms de bulle | AH-374 |
| 7 | Préparation fusionnée Area + conversion + padding | ≈ 0,5 ms | AH-201, AH-388 |
| 8 | Suppression des attentes hôte restantes | 0,3 à 1 ms | AH-55 |

Prérequis : **AH-370** (critère d'équivalence FP32) et **AH-19** (trace Nsight). Total plausible 6 à 12 ms : la chaîne passe sous 41 ms. Parents : AH-329, AH-208.

### B. Fusion des maillons et refonte du pipeline

Déjà fusionné : bloc RIFE + SPAN par paire avec batch Quality, cache de paire et promotion B → A, graphes CUDA par réseau, décodage NVDEC sans copie. Pas encore : Area → préparation RIFE (intermédiaire YUV16), RIFE → SPAN (aller-retour YUV16), TrueHDR sur stream NULL avec douze attentes, un seul ticket en vol, seize synchronisations hôte par paire.

Architecture cible du pipeline ordonné : un stream par étage et des événements entre étages, deux paires en vol, une seule attente finale, puis **un graphe CUDA de paire entière** (3 RIFE + 4 SPAN + 4 HDR + copies, un seul lancement : AH-77) une fois les attentes supprimées. La sortie reste YUV444P16 importée par le rendu Vulkan de mpv (AH-83). Les étages gardent leur catégorie et leur ordre choisis par l'utilisateur ; la fusion est une décision d'exécution, jamais un changement de profil.

### C. Kernels CUDA, Triton et assembleur

Plan dans **AH-388** : trace Nsight d'abord (AH-19), puis préparation fusionnée (AH-201), remise directe (AH-74), warp + blend + post fusionnés pour Fast (AH-202), pack/unpack HDR vectorisés avec dither (AH-392), réductions en un passage. Triton pour prototyper (AH-209/210), CUDA C++ pour livrer, PTX inline seulement où la trace le justifie (AH-206), AVX2/F16C sur les chemins CPU du pont ORT (AH-203). Les réseaux restent ≈ 87 % du temps : les kernels maison valent 1 à 3 ms par paire, pas plus.

### D. Modèles

- **AH-389** : RIFE distillé et affiné pour l'anime (élève deux fois plus rapide à qualité égale ou supérieure ; coût accepté, plusieurs semaines, GPU d'entraînement).
- **AH-193** : INT8/FP8 calibré pour SPAN, variante Fast explicite seulement.
- AH-199 : variante entraînée pour haute cadence ; AH-212 : corpus anime versionné.

### E. Tous les GPU et tous les systèmes

Principe : un contrat commun (profils, catégories, critère d'équivalence, harnais) et une implémentation par moteur, sans convergence forcée. Objectifs mesurables : **AH-384 AMD** (MIGraphX/HIP natif plus rapide que DirectML sur RDNA3/4, chaîne résidente, VAAPI → HIP sous Linux), **AH-385 Intel** (OpenVINO natif résident, Arc/Xe, NPU pour SPAN), **AH-386 Apple** (RIFE natif Core ML/Metal, VideoToolbox → Metal), **AH-387 Vulkan/NCNN** (RIFE 4.26 mêmes poids, VkMat résident), **AH-82 Windows** (parité du pipeline ordonné sur TRT et DML). Outils transverses : **AH-378** harnais de parité RIFE, **AH-394** matrice de performance par matériel consommée par le Manager.

### F. Manager v2

**AH-379** avec AH-380 (résumé calculé et coût estimé par profil), AH-381 (trois états d'étape, cause lisible, action, création active), AH-382 (lexique unique, FR/EN), AH-383 (préréglages de facteur, liste fermée des modèles, page Moteurs simplifiée). Architecture d'information et captures de référence dans l'audit du soir, section 7.

### G. Qualité à faible coût

AH-371 matrice couleur réelle dans RIFE (sources 601), AH-392 dither avant TrueHDR, AH-393 downscale Descale pour les sources produites en 720–900p, AH-232 politique Fast v2 décidée par occlusion et cohérence du mouvement, AH-143 DRBA.

### H. Processus

AH-390 canaux stable/essai et une release par jour, AH-391 documentation (ce tri), AH-227 fork mpv avec les patches en commits, AH-228 binaires hors Git et moteur Linux construit en CI.

## 3. Ordre d'exécution proposé

| Étape | Contenu | Durée indicative |
|---|---|---|
| 1 | Fidélité : AH-330 sur l'installation réelle, AH-371, AH-370 avec son jeu de référence et son outil | une semaine |
| 2 | Budget Quality ×4 : AH-376, AH-372, AH-373, AH-374, AH-74, AH-55 ; une release vérifiée | deux semaines |
| 3 | Manager v2 (AH-379 à AH-383) et facteurs fractionnaires (AH-375) | deux à trois semaines |
| 4 | Programme VFI (AH-377) : DRBA, puis AMT-S / IFRNet-S / EMA-VFI, puis port GMFSS ; harnais AH-378 | un à deux mois |
| 5 | Objectifs matériels (AH-384 à AH-387, AH-82) au rythme des machines disponibles ; kernels (AH-388) après AH-19 ; distillation (AH-389) en tâche de fond | continu |

Le processus (AH-390, AH-391, AH-227, AH-228) avance en parallèle. Rien dans ce programme ne change un profil utilisateur ni un résultat Quality sans passer par le critère d'AH-370.
