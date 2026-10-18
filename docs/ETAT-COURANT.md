# État courant

Mis à jour le **17 octobre 2026, fin de soirée (lot A livré, tickets audités)**. Lire [AGENTS.md](../AGENTS.md), puis le ticket Jira choisi et les contrats qu'il cite. Jira AH : https://tatoub.atlassian.net/jira/software/projects/AH/boards/2 (connecteur Atlassian à charger en début de session ; sans lui, travailler depuis les exports archivés et le dire).

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

## Lot B en cours (18 octobre) — budget Quality ×4

Branches `impl/lot-b-20261018` (PLAYER et BACKEND). Livré en code : temps GPU par étage et par job (`AJI_PIPELINE_TIMING=1`), banc alterné `tools/bench/pipeline_bench.py`, attente de construction `tests/inference/pipeline_build_wait.py` (AH-396) ; SPAN à lot dynamique 1..4 avec remise directe RIFE → SPAN en RGB FP16, actifs par défaut sur le bloc Quality fusionné du pipeline ordonné (clé `chain_N_batch_upscale` écrite par le pipeline ; bascules `AJI_SPAN_BATCH=0`, `AJI_RIFE_DIRECT_HANDOFF=0`, `AJI_PIPELINE_QUALITY_BATCH=0`) (AH-376, AH-74) ; encodeur RIFE 4.26 partagé en opt-in (`AJI_RIFE_ENCODER_CACHE=1`) ; plans optionnels construits comme les plans de référence (une construction à la fois, attendue par le pipeline, GPU au repos), leur échec laisse la chaîne sur ses plans de référence ; le pipeline ordonné publie les journaux de ses étages dans le fichier de statistiques (`aji_pipeline_status_text_v1`, `vf_animejanai-pipeline-stats.patch`) : le moniteur narre et tient la lecture à la première lecture, ce qu'il ne faisait pas sur cette route ; règle d'équivalence v2 puis v3 (AH-399 : marge relative, percentile 99,9, la marge absolue de 16 était sous la variance de construction FP16). Mesures (banc long, médiane GPU par paire ×4, n = 124, GPU au repos) : référence 38,47 ms, lot + remise 38,03 ms, encodeur 37,64 ms, tout 37,81 ms ; tous ÉQUIVALENTS FP32 (v3). Constructions à la première lecture : plan SPAN à lot 77 s, encodeur + tête ≈ 60 s. Reste : contrôle final sur GPU au repos (adoption du plan par le pipeline, variance de construction du plan livré, banc de confirmation ; l'essai du 18/10 à 02:44 est invalide, `libnvinfer.so.11` manquait après la remise à zéro du dossier de données, voir `lotb-idle-queue.INVALID.txt`), revue adversariale, bundle et release 3.8.0.109. Les commits lecteur du lot B (outils, correctif de statistiques à symbole optionnel, règle v3) sont déjà dans la 3.8.0.108, avec les moteurs de la 3.8.0.107.

## Manager : reprise urgente (18 octobre) — priorité avant la release du lot B

Demande de l'auteur : Manager « moche, cassé, non intuitif », profils modulaires inopérants, RIFE qui « perd de la résolution », HDR appliqué sans étape HDR, TrueHDR « ne fonctionne pas ». Diagnostic et conception dans [MANAGER-V2.md](MANAGER-V2.md), contrat dans [CONTRAT-PROFILS-V2.md](CONTRAT-PROFILS-V2.md) : **les étapes sont la seule représentation d'un profil** (clés héritées régénérées depuis elles) et **le HDR est un réglage global** (désactivé / mpv / NVIDIA TrueHDR), appliqué après la dernière étape. Fichier de profils de l'auteur réparé le 18/10 (quatre profils vidés le 17/10 par un Manager de l'ancienne lignée). Tickets : AH-403 à AH-406, parapluie AH-379.

Fait (branche PLAYER `impl/manager-urgent-20261018`, WP1) : `interpolation-stages.lua` (normalisation, projection depuis les étapes, étapes HDR ignorées), `linux-playback.lua` (HDR global : sidecar sur la route héritée, étape TrueHDR injectée dans la copie d'exécution de la route ordonnée, sidecar supprimé sinon ; sélection après édition relue à la source), `linux-hdr.lua`, `pipeline-hdr.lua`, `gpu-policy.lua` (`conversion_in_profiles` ignoré), réglages livrés sans cette clé, `AppRun` exporte `ANIMEJANAI_IMAGE_DIR` ; suites Lua à jour (`tests/hdr/run.sh`, `tests/player/run.sh` ; seul `run_slot_tests` AMD AMF reste en échec, antérieur).

Fait ensuite (même branche, et Manager `impl/manager-v2-20261018`, interface en anglais à la demande de l'auteur ; français plus tard, AH-382) : Manager refait (pages Profils avec résultat calculé, trois états d'étape avec cause et action, trois catégories, modèles en liste fermée et noms courts, préréglages de facteur ; Réglages avec le choix global Off / Renderer / NVIDIA TrueHDR grisé avec sa cause ; Moteurs simplifiés, cache TensorRT, SDK). Les étapes suivent un changement de moteur (contrat §5 bis) ; les clés héritées sont de nouveau écrites par le Manager comme projection des étapes, car les lanceurs Windows et macOS les passent telles quelles aux moteurs (contrat §1) ; étapes HDR retirées à toute position ; fichier d'un Manager plus récent jamais réécrit. Banque `linux-nvidia` de départ en TensorRT (cinq profils, contrat §6 bis), noms anglais de la banque AMD, « Add recommended profiles » sur les mêmes définitions, lanceur `--all-slots` (TensorRT et RIFE téléchargés au premier lancement NVIDIA). Contrôles : les onze programmes de tests du Manager, `profile_components_check.py`, `package_check.py`, `PlatformTests`, `InterpolationContract` (assertion périmée corrigée), suites Lua. Limites : `libaji_rtx.so` n'est dans aucune release, TrueHDR reste grisé sur une installation neuve (AH-407) ; le premier lancement NVIDIA télécharge environ 1 Go sans progression visible (AH-408). Configuration de l'auteur remise à zéro pour l'essai « première installation » : `~/.local/share/AnimeJaNai-HDR-linux` déplacé en `AnimeJaNai-HDR-linux.avant-reset-20261018` (réversible).

Livraison : Manager `8b99001` (CI `build-hdr.yml`, branche `perf-specialized-manager-v2-20261018`, paquets `hdr-<sha>`), lecteur `hdr-3.8`, release 3.8.0.108 (moteurs de la 3.8.0.107). Ensuite : les moteurs du lot B après leur revue.

## Audit des tickets (17 octobre, fin de soirée)

283 tickets ouverts audités un par un : 203 clos (fusionnés dans leur ticket parapluie avec un commentaire qui le nomme, ou sans voie temps réel), 55 réécrits au format commun (verdict, périmètre, fichiers, étapes, preuve de clôture, gain attendu, modèle d'exécution recommandé), 25 créés le jour même conservés tels quels. Parapluies : AH-377 (programme VFI, catalogue des méthodes), AH-384/385/386/387/82 (objectifs AMD, Intel, Apple, Vulkan, Windows), AH-388 (kernels), AH-389 (modèles), AH-394 (matrice par matériel), AH-396 (banc), AH-329 (budget Quality ×4). Règle d'exécution : Opus 5.5 effort high pour moteur/filtre/interop, Fable 5.1 medium pour Lua/Manager/docs/scripts, Fable 5.1 max pour les études ; revue adversariale seulement avant une release moteur.

## Cinq lots ouverts (étiquettes Jira)

1. **lot-fidelite** (lot A livré en 3.8.0.107 : AH-330, 370, 371, 372, 373, 374, 55 Done) : restent AH-15 contrat couleur, AH-11 rapport de session, AH-12 profil verrouillé, AH-16 capacités, AH-397 qualification 601, AH-399 règle v2, AH-212 corpus.
2. **lot-quality-x4** (suivi AH-329) : AH-396 banc fiable, AH-376 SPAN B4 et encodeur partagé, AH-74 remise directe, AH-395 TrueHDR sans attente, AH-83 interop rendu, AH-77 graphe de paire, AH-201/202 kernels, AH-398 mesure en lecture. Objectif : ≤ 41,7 ms par paire avec HDR (36,1 ms sans HDR aujourd'hui).
3. **lot-manager** : AH-379 Manager v2 et AH-380 à AH-383, AH-297 validateur de chaînes, AH-140 registre RIFE, AH-37 états de lecture.
4. **vfi-temps-reel** : AH-377 (porte commune), AH-143 DRBA en priorité 1, AH-141 GMFSS, AH-144/145/158 candidats légers, AH-165 softsplat, AH-375 fractions, AH-378 harnais, AH-180 effets anime, AH-232 Fast v2, AH-193 INT8 Fast, AH-389 distillation.
5. **processus et robustesse** : AH-227 fork mpv, AH-225/226/336/337 registre et packs, AH-390 canaux, AH-21/23/39/42/43/45 compteurs, réserve, quotas, seek, cadence, erreurs, AH-218 longue durée, AH-28/32 caches, AH-231 découpage, AH-186 sous-titres HDR.

Objectifs matériels à long terme : AH-384 AMD, AH-385 Intel, AH-386 Apple, AH-387 Vulkan, AH-82 Windows.

## Règles courtes

- Un ticket est In Progress seulement s'il appartient à un lot réellement travaillé ; Done après périmètre complet, qualification adaptée et livraison vérifiée.
- Quality conserve les prédictions complètes et les modèles de référence ; dès l'adoption d'AH-370, « exact » signifie équivalence bornée contre FP32, pas identité avec un plan TensorRT.
- Toute approximation est une variante Fast explicite. Gain attendu, gain mesuré et coût supprimé par le code sont distingués.
- Préserver profils, médias, SDK, modèles et modifications utilisateur ; checkouts isolés ; aucun `git add -A`.

## Où lire

[Audit du matin](AUDIT-GLOBAL-2026-10-17.md) · [Audit du soir : performances, qualité, Manager](AUDIT-PERFORMANCE-QUALITE-MANAGER-2026-10-17.md) · [Programme d'amélioration et étude VFI](PROGRAMME-AMELIORATION-2026-10.md) · [Protocole de validation](PROTOCOLE-VALIDATION-FEATURES.md) · [Archives](ARCHIVES.md).
