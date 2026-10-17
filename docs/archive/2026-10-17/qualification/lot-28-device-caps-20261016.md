# Lot28 — compatibilité CPU/CUDA vérifiée par les modules

AH-276 sous AH-16 ; autres providers/OS et politiques automatiques AH-277. Base lecteur3.8.0.59 `d8c908804c019f9e66ddf6be7dc3b5bbb78cc05e` ; backend `652fbc6bdd3a9d815367deeb2df65538636705dc` depuis66fcd9d. Worktrees isolés, backend utilisateur d'origine préservé.

## Livrable

`AnimeJaNaiPlatform --device-capabilities --root DIR [--cuda-device ORDINAL]` charge les modulesCPU/CUDA surLinux et appelle des extensions optionnelles versionnées. La présence d'un fichier ou le nom du fabricant ne vaut plus preuve dans ce diagnostic : absence, échec de chargement/dépendance, sonde absente/ancienne, signature incompatible et erreur d'exécution sont distincts. L'identité du fichier sur disque est rapportée séparément ; elle ne décrit pas une bibliothèque déjà chargée dans un autre processus.

CPU : sonde `aji_ort_probe_v1`, signature figée180octets/version1/bridgeABI1, exigencesAVX/F16C x86, versionORT réellement liée et conversionFLOAT→HALF du module. Entréevolatile0,5 pour empêcher une réponse constante du compilateur. Le CLI vérifie AVX activé par l'OS et le bitCPUIDF16C avant de charger/appeler le code x86. Aucun modèle/sessionORT créé.

CUDA : sonde backend `aji_trt_probe_v1`, signature figée468octets/version1/ABI9. CUDAordinal demandé, PCI, nom, SM, attributintegrated, versionsdriverCUDA/runtimeCUDA/TensorRT et codes d'erreur réellement relevés. Elle retient sa propre référence de contexte primaire, pousse/restaure le contexte courant, utilise son stream non bloquant, exécute `aji_fill_f16` du module et vérifie le résultatHALF0x3800, puis libère ses ressources/référence. Aucun reset du device ni compilation de plan, réseau ou changement de pixels. Un champ matériel non interrogé reste−1/null, une version inconnue0/null.

Les extensions s'ajoutent aux ABI1/9 ; aucun symbole existant retiré/changé. Short/nulloutput refusé avant écriture. Moduleancien sans symbole = «probe-unavailable», jamais compatible par défaut. La compatibilité d'un kernel/conversion reste distincte de la prise en charge d'un modèle/plan, de sa qualité ou des surfaces importables. Diagnostic ponctuel, à utiliser hors mesureGPU/lecture ; il peut initialiser temporairement CUDA.

## Capacités déclarées et limites de cette preuve

| Route actuelle / sources | Implémentation visible | Ce que la sonde établit |
|---|---|---|
| ORT partagéCPU, `aji_ort.cpp`/`exec_ort.cpp` | SpatialONNX batch1/3couleurs, RIFE4.x export11plans, modèleensemble séparé ; Fastflow/mask seulement horsensemble, dessins/raccourcis réservésFast ; modèles temporels `frames>1` explicitement refusés ; I/ORGB24SDR hôte | Chargementmodule, exigencesCPU, runtimeORT, conversion compilée. Aucun modèle/provider/rank5/importGPU qualifié |
| TensorRT/CUDA, backend `aji_trt.cpp`/`onnx_shape.cpp` | SpatialONNX, RIFEexport/ensemble selon modèles, Fast sansensemble ; temporelrank4 empaqueté/rank5 adapté, une étape temporelle, fenêtre impaire≤15 etI/OFP16 ; formatsCUDA NV12/P010/44416/44410-12MSB et référencesdeCUcontext/CUdeviceptr | Module chargé et un kernel embarqué exécuté sur device/SM réel, versions liées et cycle de contexte sûr. Pas de certification des opérateurs/modèles/plans/tactiques ni d'import Vulkan/D3D12 générique |
| AMD/Intel/NPU/Apple/Windows | Notices d'implémentation séparées dans le catalogue ; gfx1201/gfx1152/XMX/LUID/NPUnécessitent leurs API natives | Pas sondés par ce lot ; ni «AMD» ni présenceDLL ne valide ces capacités |

Le catalogue d'implémentation intégré auJSON est une déclaration de la révision de l'outil, distincte du résultat de la sonde du module. La sélection automatique historique reste dansAH-277 ; ce lot ne prétend pas avoir remplacé toutes les heuristiques de fabricant. Les métadonnées de surfaces/couleur restentAH-49/AH-275. Respecter [précision](../CONTRAT-PRECISION-MOTEURS.md) et [couleur/profondeur](../CONTRAT-COULEUR-PROFONDEUR.md).

## Qualification ciblée, arrêt après conclusion

MachineLinuxCachyOS, CPUx86-64 AVX/F16C, RTX4070Ti PCI0000:01:00.0/SM8.9. VraiCLI + vraiesbibliothèques : conversionCPU réussie/ORT1.24.1, kernelCUDA réussi, integratedfalse, driver/runtimeCUDA13040 et TensorRT110300 (encodages entiers retournés parAPI). N'inférer ni version de pilote marketing ni buildpatchTensorRT depuis ces seuls entiers.

Contrôles courts `tests/platform/device_capabilities_check.py SPEC` : anciens modules réels du lot25/14 = sondeinconnue ; absence explicite ; fauxfichierELF = chargementéchoué ; ordinal65535 = échecpilote et SM/integratedinconnus ; sortiescourtes/nulles refusées/sentinelle intacte pour les deuxAPI. Cas de durée de vie distinct : appeler la sondeCUDA avec un contexte privé du caller courant ; contexte du caller restauré et encore valide, puis contexte précédent restauré à sa destruction. Le casGPU par défaut déjà concluant n'est pas rejoué.

Le premier rapport positif est acquis avant la correction des valeurs inconnues par défaut ; cette correction ne change pas les champs réécrits lors d'un succès. Le contrôle de contexteGPU et l'ordinal invalide portent sur le binaire final. La sortieCPU est inchangée après sa qualification initiale. Aucun réseau/plan/inférence exécuté ; aucun gainFPS/qualité extrapolé. Le bénéfice est une preuve réelle et un diagnostic exploitable au-delà de «DLLprésente».

BuildsCPURelease/.NETRelease réussis, .NET0warning/0error ; backendCUDA toutesarchitectureslivrées75/80/86/89/90/100/120 +PTX120, build réussi (warningsSDKpréexistants). Ensembles des exportsC comparés : seul `aji_ort_probe_v1` ajouté côtéORT et `aji_trt_probe_v1` côtéCUDA. SyntaxePython/diff-check réussis. Les corps d'inférence/rendu et poids ne sont pas modifiés ; aucune répétition vidéo nécessaire pour l'extensiondiagnostic.

Artefacts `artifacts/performance/lots-20261016/lot-28/` : `actual-capabilities.json`/`.log`, `checks/summary.json` et casJSON/logs, `check.spec.json`, buildmulti-SM, CPU, CLI. RéférencesmodelQuality/Fast des lots précédents conservées, non rejouées.

## Livraison

Backend652fbc6 poussé sur `perf-specialized-capabilities-20261016`, compilationWindows/Linux lancée. SourceCLI/CPU et qualification prêtes ; assembler le prochain lot/release avec le nouveau pin de binaires après disponibilité, sans attendre pour entreprendre une tâche indépendante. AH-276 reste In Progress jusqu'à publication vérifiée du livrable complet. ParentAH-16/AH-277 restent ouverts ; aucune qualificationWindows/AMD/Intel/Apple inventée.

Livraison préparée3.8.0.60, pinbinaires `d00ed919d8337a89b68f519f1ab1ce71e68a8628` ; compilationWindows AMD/NVIDIA38874628974 success. Hashes etsymboleoptionnel/RPATH du staging vérifiés, patchRPATH préserve `.text`. Manager inchangé.
