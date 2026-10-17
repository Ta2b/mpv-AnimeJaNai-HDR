# État courant

Mis à jour le **17 octobre 2026, fin de soirée (lot A)**. Lire [AGENTS.md](../AGENTS.md), puis le ticket Jira choisi et les contrats qu'il cite. Jira AH : https://tatoub.atlassian.net/jira/software/projects/AH/boards/2 (connecteur Atlassian à charger en début de session ; sans lui, travailler depuis les exports archivés et le dire).

## Livré et vérifié

| Composant | Référence |
|---|---|
| Release | **3.8.0.107** en cours de publication (lot A) ; précédente **3.8.0.106**, source PLAYER `a688bef`, trois CI réussies, 17 assets |
| Manager | `714d48e` (ajout d'étapes corrigé, AH-369) |
| Bundle GPU | `fc9b430` (lot A) ; backend Linux `e70a044` (`impl/lot-fidelite-20261017`, base `118c272`), fatbins inchangés (TRT `.nv_fatbin` 23766330…, Area `3447cd8`) ; Windows DML/TRT `d5b3446` inchangé |
| Lecteur Windows | `32464bc` |
| Installation de l'utilisateur | 3.8.0.104 ; un `libaji_trt_rtx.so` régulier du 14 octobre (`200ea558…`) subsiste à côté des liens : AH-330 |

Mesure de référence (lot 62, RTX 4070 Ti) : Area 720 → RIFE 4.26 Quality ×4 → SPAN 1440 → TrueHDR = **46,4 ms par paire** (Area 0,8, RIFE+SPAN 37,9, HDR 6,9) pour un budget de 41,7 ms à 24 i/s.

## Lot A (17 octobre au soir) — fidélité et budget Quality ×4

Branche PLAYER `impl/lot-a-20261017` (base `c6fee61`), backend `impl/lot-fidelite-20261017` (`7477134`), bundle `binaries/lot-a-20261017` (`fc9b430`).

- **AH-370** : règle d'équivalence FP32 écrite dans [le contrat de précision](CONTRAT-PRECISION-MOTEURS.md), outils `tests/inference/fp32_reference.py`, `quality_equivalence.py`, `make_test_pattern.py`. Moteur livré contre FP32 sur la chaîne du lot 55 : PSNR Y/U/V 53,1 / 68,1 / 66,7 dB ; le moteur du lot A est bit à bit identique au moteur livré (13 sorties).
- **AH-55 / AH-372** : un seul stream prêté par le pipeline au moteur TensorRT (`aji_surface_set_stream_v1`), attentes hôte supprimées (`host_waits=0` dans la trace). Paire ×4 sans HDR : 36,1 ms au mieux contre 51,1 ms (banc hors ligne, GPU partagé avec le bureau, pas une cadence d'affichage). TrueHDR : le SDK reste sur le stream par défaut, ordonné par événements (`AJI_HDR_STREAM_MODE=null-async-events`) ; tout mode qui exécute le SDK sur le stream du pipeline rend des pixels faux et instables (matrice de 24 essais), gain HDR non concluant sous charge bureau.
- **AH-371** : RIFE convertit la paire avec sa vraie matrice et sa plage (709 inchangé) ; qualification 601 restant à faire. **AH-373** rejeté : RIFE 4.26 exige un padding multiple de 64. **AH-374** : deux paires en vol dans le filtre (`vf_animejanai-pipeline-inflight.patch`, compilation vérifiée, gain mesurable seulement en lecture). **AH-330** : migration des copies locales périmées dans `AppRun`, provenance du moteur chargé publiée par `linux-playback.lua`.

Reste pour ce lot : vérifier la release 3.8.0.107 (trois CI), qualifier AH-371 sur une source 601, mesurer AH-374 en lecture.

## Cinq lots ouverts (étiquettes Jira)

1. **lot-fidelite** : AH-330 (In Progress, Highest), AH-370 critère d'équivalence FP32, AH-371 matrice couleur RIFE, AH-15/275 couleur.
2. **lot-quality-x4** : AH-329/208/73/76 (In Progress, Highest), AH-376 rejuger SPAN B4 et encodeur partagé, AH-372 TrueHDR sur stream, AH-373 padding 32, AH-374 deux tickets en vol, AH-74 remise RGB directe, AH-19 trace Nsight, AH-388 kernels. Objectif : ≤ 41 ms par paire sur la chaîne de référence sans perte perceptible.
3. **lot-manager** : AH-379 Manager v2 et ses sous-tâches AH-380 à AH-383 (parent fonctionnel AH-224).
4. **vfi-temps-reel** : AH-377 programme VFI anime, AH-375 facteurs fractionnaires, AH-378 harnais de parité RIFE, AH-143 DRBA en priorité 1.
5. **processus** : AH-391 documentation (In Progress), AH-390 canaux de release, AH-227 fork mpv, AH-228 builds reproductibles et binaires hors Git, AH-394 matrice par matériel.

Objectifs matériels à long terme : AH-384 AMD, AH-385 Intel, AH-386 Apple, AH-387 Vulkan, AH-82 Windows.

## Règles courtes

- Un ticket est In Progress seulement s'il appartient à un lot réellement travaillé ; Done après périmètre complet, qualification adaptée et livraison vérifiée.
- Quality conserve les prédictions complètes et les modèles de référence ; dès l'adoption d'AH-370, « exact » signifie équivalence bornée contre FP32, pas identité avec un plan TensorRT.
- Toute approximation est une variante Fast explicite. Gain attendu, gain mesuré et coût supprimé par le code sont distingués.
- Préserver profils, médias, SDK, modèles et modifications utilisateur ; checkouts isolés ; aucun `git add -A`.

## Où lire

[Audit du matin](AUDIT-GLOBAL-2026-10-17.md) · [Audit du soir : performances, qualité, Manager](AUDIT-PERFORMANCE-QUALITE-MANAGER-2026-10-17.md) · [Programme d'amélioration et étude VFI](PROGRAMME-AMELIORATION-2026-10.md) · [Protocole de validation](PROTOCOLE-VALIDATION-FEATURES.md) · [Archives](ARCHIVES.md).
