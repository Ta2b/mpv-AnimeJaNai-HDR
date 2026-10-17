# État courant — point d’entrée IA

Mis à jour le **17 octobre 2026**. Lire AGENTS.md, puis uniquement le ticket et ses contrats utiles. Demandes utilisateur et Jira réel priment sur les archives. Projet existant AH : https://tatoub.atlassian.net/jira/software/projects/AH/boards/2 ; connexion vérifiée, ne pas réimporter le backlog.

## Mission et dernière livraison vérifiée

Poursuivre les lots complets sans pause, sans attendre builds/releases. Vérifier à la fin d’une tâche indépendante ; aucun watch/poll/sommeil. Pas de nouveaux sous-agents, les anciens sont terminés. Source IDE ancienne/modifiée, relais documentaire seulement. Checkouts isolés, fichiers explicites dans git add, préserver installation/profils/médias/SDK/modèles ; aucun add-A/reset/clean global/push au backend utilisateur original.

**Dernière release vérifiée .101**, source5ff6137878cc4f3616ee9740fb7495fc9a2c46f0, [reçu](jira/release-20261017-3.8.0.101.json). TroisCI réussies, tag/17assets. Tar/manifeste/packs Linux digests conformes ;32programmes, sixmodulesCUDA/Vulkan inchangés .95, identité native recalculée égale au manifestec8a86a65…. Helper livré/trimmed exécute correctement une détection temporelle5D et l’ordre upscale→RIFE dans une fixture privée sans GPU. ManagerLinux est **recompilé** dans la CI PLAYER, donc son hash diffère du tagManager autonome : source embarquéeb69968a et codeStream vérifiés, blob partagé identique97e325e. AH366 complet, clôture Jira à consigner.

**.100 vérifiée**, source0d7f1f3537cdad4f2eac3b92b9f0ebc0fba2feb8, [reçu](jira/release-20261017-3.8.0.100.json). TroisCI/tag17assets, archiveMac digest conforme,17programmes, contrôleur/launcher exacts au source, helper avec nouvelle CLI et ManagerMac exact au tag37e7c1a ; dylib7816d2a5… inchangé .99. Une régression du hook asynchrone trouvée ensuite empêche AH353/AH339 Done avant .102 ; les publications restent vérifiées, ne pas prétendre ce défaut déjà livré corrigé.

Pins .101/.102 : Managerb69968a8a30cedc83b28820ca14d014abcb36928, source partagée97e325efb59e80d2eac7dfc685192052a01d7399 ; bundleCUDA6598d4fa1bf4d1b988576d56afa39c72437f35c7. Dispatcher source118c272, TRT/alias/pipeline9d2c717, fatbinArea3447cd8 ; GPU-SOURCE.module_sources fait autorité, ancien backend_source global historique.

## Travail actif — AH353/AH339, correction du préchargement

Checkout `/home/ta2b/.animejanai-tools/work/lot-81-macos-preload-gate-20261017`, branche fix/macos-preload-profile-gate-20261017, base7be107e (.101 + enregistrementworkflow seulement, **aucun code expérimental350**). Garder ces tickets In Progress jusqu’à .102 vérifiée.

Le raccord canonique macOS est livré .100 : helperbundle, modèles/runtimes exacts selon device, source privée/policy, rule0 sans modèles inactifs, HDR de profil indépendant, async/timeout5s/annulation. [Guide AH353](reprise/20261017/AH-353.md), [preuves lot78](qualification/lot78-macos-profile-plan-20261017/README.md). Les preuves Windows/Linux .84 d’AH339 restent valides, ne pas les rejouer.

Régression trouvée avant clôture : le hook on_preloaded rendait la main avant réponse du helper, première image éventuellement sans profil. Correctif lot81 : hook.defer, cont après succès/refus/délai/Off/shutdown, génération des callbacks inchangée. Vrai mpvLinux avec contrôleurMac et helper300ms : base première sortie slot0, candidat slot1, erreur→slot0/lecture débloquée ; source intacte. [Preuve](qualification/lot81-macos-preload-gate-20261017/README.md). Aucun code moteur changé ; sources C#/Manager restent celles de .101. .102 à pousser/vérifier puis AH353/AH339 Done ; AH224 UX global reste ouvert.

## Travail actif — AH350 / parent AH120, import VideoToolbox→Metal

Checkout `/home/ta2b/.animejanai-tools/work/lot-80-videotoolbox-metal-import-20261017`, branche tickets/videotoolbox-metal-import-20261017, candidate3f0477ceb29cedbd2ebb190e712db26dcc188858. **Runtime hors main/release** ; seul workflow enregistré7be107e est sur main. AH350 et AH120 In Progress.

Adaptateur privé typé CVPixelBuffer NV12 420v SDR709→texturesR8/RG8 du deviceconsommateur ; buffer/wrappers/cache retenus jusqu’à finGPU. ABI RGB24 et capacités publiques METAL inchangées. Filtre opt-in apple-import-probe=yes **slot0 uniquement, sans inférence** ; défautvideotoolbox-copy conservé. Formatsrefusés→downloadSW profondeur/couleur/crop/PTS conservés, vérification contre réduction de profondeur. Worker/drain/reset existants réutilisés, pas de thread parframe.

Source : native/apple/nv12_import_probe.h/.mm, CMake, vf_animejanai_vulkan.c/install-filter.py ; tests/apple/videotoolbox_import_probe.mm et videotoolbox_filter_probe.py. SyntaxeC Linux/Python/shell passée, compilation native .dylib/probe réussie. CI39027604395 **échoue avant tout cas concluant** : VTDecompressionSessionCreate=-12902 (paramètre), cases{} ; filtrejob non lancé. Artefact `lot-80-native-first-evidence-20261017` contient dylib/ORT/clips/logs. Diagnostiquer paramètres/format/codec/support réel, ne pas déclarer une API absente sans vérifier. Aucun import qualifié, aucun FPS, aucune release350 à annoncer.

Workflow qualify-videotoolbox-import.yml : native puis vraiMPV, troisclipsHEVC3frames (NV12SDR709,SDR601repli,HDRP010repli), exactitude plans/PTS/couleur/profondeur. Mode filter_only réutilise un artefact **natif concluant** via prior_native_run ; pas utilisable tant que native.passed=false. Ne pas refaire les cas déjà conclus après un futur échec partiel. Relever versions/device/codec réellement utilisés. ParentAH120 garde entrée moteur/rendu macvk ; un importprobe ne clôt pas ces frontières.

## Autre build actif — AH344 Windows DirectML

Producteur39019317771, source32464bc : dernière lecture toujours Build both static entry points. Checkout lot-71-windows-producer-20261017. Échecs antérieurs libassHEADdétachée puis c-aresdepth1/defaultcoverity_scan corrigés ; c-aresmain épinglé f4156c12 et clonepartiel sansdepth. Cache dépendances conservé. Consulter seulement après tâche indépendante.

À réussite : tag windows-mpv-SHAcomplet, troisPE/provenance/patch/source, puis pinwindows-mpv-source-ref et release de la paire. DLL DML seul n’est pas un cache actif livré/qualifié. [Guide](reprise/20261017/AH-344.md). Aucun support physique Windows/AMD déduit d’une compilation.

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
