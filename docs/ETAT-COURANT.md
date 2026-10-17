# État courant — point d’entrée IA

Mis à jour le **17 octobre 2026**. Lire AGENTS.md, puis uniquement le ticket et ses contrats utiles. Demandes utilisateur et Jira réel priment sur les archives. Projet existant AH : https://tatoub.atlassian.net/jira/software/projects/AH/boards/2 ; connexion vérifiée, ne pas réimporter le backlog.

## Mission et dernière livraison vérifiée

Poursuivre les lots complets sans pause, sans attendre builds/releases. Vérifier à la fin d’une tâche indépendante ; aucun watch/poll/sommeil. Pas de nouveaux sous-agents, les anciens sont terminés. Source IDE ancienne/modifiée, relais documentaire seulement. Checkouts isolés, fichiers explicites dans git add, préserver installation/profils/médias/SDK/modèles ; aucun add-A/reset/clean global/push au backend utilisateur original.

**Dernière release vérifiée : 3.8.0.102**, source `714479b6de1e80499504fff019db390f90ebff96`, [reçu](jira/release-20261017-3.8.0.102.json). Trois CI réussies, tag exact,15assets. Archive Mac digest15a4457f…,17programmes gérés conformes, contrôleur93837a4a exact et hook différé présent ; launcher exact, helper et Managerb69968a présents, dylib7816d2a5 identique à .99. **AH353 Done10311, AH339 Done10312**. Qualification réelle du hook : première lecture slot0 avant, slot1 après, erreur helper libère la lecture ; aucun replay requis.

**.101 vérifiée**, [reçu](jira/release-20261017-3.8.0.101.json), **AH366 Done10309**. Lecture des formes ONNX sans charger les poids : dimensions/cache/fallback conservés, sparse128Mio134219232→5840octets alloués et90octets logiques lus. Helper réellement livré/trimmed : détection5D et ordre upscale→RIFE corrects. Le Manager Linux est recompilé par la CI PLAYER : son hash peut différer de l’archive autonome ; sourceb69968a et codeStream vérifiés, blob partagé identique97e325e. Aucun gainFPS d’inférence prétendu.

Pins .103 : Manager `b69968a8a30cedc83b28820ca14d014abcb36928`, source partagée `97e325efb59e80d2eac7dfc685192052a01d7399` ; bundle `dc53e6cacdff59c1f243226d9575b5079bae9c9e` (seule provenance Windows changée depuis6598d4f), lecteurWindows `32464bc13260918381537dbb73a5a2e7523c2477`. DispatcherLinux118c272, TRT/alias/pipeline9d2c717, fatbinArea3447cd8 ; GPU-SOURCE.module_sources fait autorité. WindowsDML/dispatcher/TRT source d5b34469, AMD source652fbc6 inchangée.

## Lots terminés — consommateurs canoniques

AH353 macOS et AH339 sont Done avec .102 ; [guideAH353](reprise/20261017/AH-353.md), [preuveslot78](qualification/lot78-macos-profile-plan-20261017/README.md), [preuvehooklot81](qualification/lot81-macos-preload-gate-20261017/README.md). Le helper bundle décide des modèles/runtimes exacts selon le device, garde source privée/policy, règle0 sans modèles inactifs et HDR de profil indépendant ; timeout5s, annulation et hook de préchargement sont couverts. Les preuves Windows/Linux .84 sont réutilisées. AH224 UX global et les moteurs restent ouverts.

## Travail actif — AH350 / parent AH120, import VideoToolbox→Metal

Checkout `/home/ta2b/.animejanai-tools/work/lot-80-videotoolbox-metal-import-20261017`, branche tickets/videotoolbox-metal-import-20261017, candidate3f0477ceb29cedbd2ebb190e712db26dcc188858. **Runtime hors main/release** ; seul workflow enregistré7be107e est sur main. AH350 et AH120 In Progress.

Adaptateur privé typé CVPixelBuffer NV12 420v SDR709→texturesR8/RG8 du deviceconsommateur ; buffer/wrappers/cache retenus jusqu’à finGPU. ABI RGB24 et capacités publiques METAL inchangées. Filtre opt-in apple-import-probe=yes **slot0 uniquement, sans inférence** ; défautvideotoolbox-copy conservé. Formatsrefusés→downloadSW profondeur/couleur/crop/PTS conservés, vérification contre réduction de profondeur. Worker/drain/reset existants réutilisés, pas de thread parframe.

Source : native/apple/nv12_import_probe.h/.mm, CMake, vf_animejanai_vulkan.c/install-filter.py ; tests/apple/videotoolbox_import_probe.mm et videotoolbox_filter_probe.py. **Natif39029415108 conclu**, candidate91632df : macOS15.7.9/24G830, AppleParavirtual, VTdécodeurHEVC actif. Plans55 296octets exacts, couleur/crop/PTS/padding conservés ; refusnonSDR/P010/bornes et reset passés, live0. Modulef13aafd1… ; [preuves](qualification/lot80-videotoolbox-metal-import-20261017/README.md). Ne pas refaire le natif ; jobfiltre du même run réussi : troisimages de chaquecasNV12SDR709/601/P010HDR exactes, imports3 oureplis3, live0,10bits/PQ conservés. Le lecteur d’échantillons ignore maintenant les marqueurs vides/avecformatnul ; les anciens échecs-12902 n’étaient pas une preuve d’API absente. Code qualifié identique après fusion .103 ; .104 poussée avec cet import opt-in. AH350 reste In Progress jusqu’à livraison vérifiée. Aucun FPS, aucun rendu macvk qualifié. FFmpeg9.0.1_1/libplacebo7.360.1/MoltenVK1.4.2.

Workflow qualify-videotoolbox-import.yml : native puis vraiMPV, troisclipsHEVC3frames (NV12SDR709,SDR601repli,HDRP010repli), exactitude plans/PTS/couleur/profondeur. Mode filter_only réutilise un artefact **natif concluant** via prior_native_run ; utiliser prior_native_run=39029415108 si seul le filtre doit être corrigé. Ne pas refaire les cas déjà conclus après un futur échec partiel. Relever versions/device/codec réellement utilisés. ParentAH120 garde entrée moteur/rendu macvk ; un importprobe ne clôt pas ces frontières.

## Livraison active — AH344, lecteur Windows apparié

Checkout `lot-82-windows-dml-delivery-20261017`, branche `tickets/windows-dml-paired-delivery-20261017`, depuis .102. Producteur39019317771 **réussi**, source32464bc : archive immuable62d5039e…, troisPE/provenance vérifiés contre le vrai assembleur. Nouveau pinWindows et provenanceGPUdc53e6c livrés avec .103 ; conserver AH344 In Progress tant que son paquet publié n’est pas vérifié.

[GuideAH344](reprise/20261017/AH-344.md), [preuveproducteur](qualification/lot82-windows-dml-pair-20261017/README.md). BackendDML déjà compilé/livré, seul lecteur manquait pour annoncer les IDs. Réutilisation A/B et SCD dans une paire, trois prédictionsQuality complètes conservées. **Pas de GPUWindows qualifié ni de gainFPS mesuré** : reliquat distinct [AH367](reprise/20261017/AH-367.md), To Do, sousAH93. AH93 reste In Progress pour qualification et autres sous-périmètres Fast/retiming.

## Lots récemment terminés — réutiliser les preuves

| Release | État et preuve |
| --- | --- |
| .99 | AH365 Done10304, [reçu](jira/release-20261017-3.8.0.99.json) : SPANCoreML résidents, RGB exact,1,5Mio RGB de conversions retirées, aucun gain tempsCPU établi (149,817→150,700ms/3appels). Dylib7816d2a5… exact au candidat natif. AH119 garde RIFE/rendu. |
| .98 | AH364 Done10303, [reçu](jira/release-20261017-3.8.0.98.json) : générationsCoreML/snapshot/lock, natif CPU exact, overlap1compile, kill/reprise/corruption/readonly. Anciennes générations conservées ; AH254/32 autresproviders ouverts. |
| .97 | AH335 Done10298, [reçu](jira/release-20261017-3.8.0.97.json) : configurations protégées sans manifeste valide, backups/liens/profils ; cinqcasCPU du vraiupdater. AH226 reste ouvert. |
| .96 | AH349 Done10297, [reçu](jira/release-20261017-3.8.0.96.json) : SPANMetal résidents, RGB exact et copies explicites retirées ; gainlocalVM court≈9,8%, pas de FPS720p/GPUApple physique. |
| .95/.94 | AH363/AH362 Done, [reçu .95](jira/release-20261017-3.8.0.95.json) : identité bundleLinux/routeQualityhistorique/snapshot. AH351 Done, [reçu .94](jira/release-20261017-3.8.0.94.json) : SPANVulkan résident exact, gainlocal≈27,3%, pas d’autresGPU qualifiés. AH330/131 ouverts. |
| .92/.91 | AH361 contratQualityCUDA Done10285 ; AH240 cléCoreMLp3 Done10282. Voir leurs guides ; ne pas refaire les qualifications inchangées. |
| .85–.90 | AH338/345/346/347/355,354/356,348,244/359/358/29,352/321,360 Done. Reçus/archives gardent les preuves ; pas de batterie à rejouer. |

## Débit Quality×4 — problème toujours ouvert

AH329/208/73/76 : chaîne Area720→RIFE426Quality4+SPAN1440→TrueHDR ≈46,4ms/intervalle, budget41,7ms source24fps. Fusion active et modules .84 réellement mappés dans l’instance contrôlée ; aucun ancienmoteur démontré dans cette instance. Les garde-fous et optimisations de métadonnées ne résolvent pas ce budget. AH357 ToDo : encodeur partagé exact aux troisphases, étude gainréseau local≈0,656ms/3,15%, pas de gainlecteur établi. SPANB4 modifie FP16, étude arrêtée, aucun Quality activé. Profils/médias privés artifacts/performance/lots-20261017/quality-live-20261017, installation inchangée.

## Contrats de reprise

In Progress au début ; Done après périmètre complet, qualification nécessaire et livraison vérifiée ; parents partiels ouverts. Essais courts mêmes entrées/modèles/réglages/machine, arrêt à conclusion ; réutiliser les preuves concluantes. UI/docs/packaging contrôles simples, source/compilation si l’effet est établi ; aucune validation matérielle inventée. Quality conserve sa référence, approximationsFast explicites, besoins propres aux moteurs respectés. Distinguer travail supprimé, gain attendu et FPS mesuré. Aucun GPU concurrent pendant une mesure. Strata facultatif, non utilisé.

[Guides](reprise/20261017/README.md) · [Protocole](PROTOCOLE-VALIDATION-FEATURES.md) · [Archives](ARCHIVES.md). AH334 audit/AH340 nettoyage clos, pas de réimport. HDRavantinterpolationAH333 demandé pour plus tard. RootIDE ETAT copié seulement si ses octets sont encore ceux de la dernière copie agent connue.
