# État courant — point d’entrée IA

Mis à jour le **17 octobre 2026**. Lire `../AGENTS.md`, puis uniquement le ticket et ses contrats utiles. Demandes utilisateur et Jira réel priment sur les archives. Projet **AH** : https://tatoub.atlassian.net/jira/software/projects/AH/boards/2 ; connexion vérifiée, ne pas réimporter le backlog.

## Mission et livraison vérifiée

Poursuivre les tickets par lots complets, sans attendre builds/releases. Aucune pause active. Pas de nouveaux sous-agents ; les précédents ont terminé. Checkout IDE ancien/modifié : relais documentaire seulement, jamais source de release. Préserver installation, profils, médias, SDK, modèles et modifications inconnues ; checkouts isolés, fichiers explicites dans git add, aucun add-A/reset/clean global/push au backend utilisateur original.

Dernière release vérifiée **3.8.0.99**, source `2582f2c6ccfbc911dfadd0152393a53318add8f5`, [reçu .99](jira/release-20261017-3.8.0.99.json). TroisCI/tag16assets vérifiés, archiveMac digest conforme, dylib7816d2a5… exact au candidat natif qualifié,17programmes/32ressourcesmodèles conformes ; AH365 Done, commentaire10304. Aucun replay.

Release précédente **3.8.0.98**, source `18013889f61234facfa53b997d5aeebea2cdc307`, [reçu .98](jira/release-20261017-3.8.0.98.json). Trois CI/tag16assets vérifiés ; archiveMac digest conforme, dylib61b30d43… EXACT au module complet .98 qualifié en base d’AH365,17programmes/32ressourcesmodèles conformes. AH364 Done, commentaire10303.

Release précédente **3.8.0.97**, source `7796cfc13f7a0d1557238149bffaf22b09bb27dd`, [reçu .97](jira/release-20261017-3.8.0.97.json). Trois CI réussies, tag et16assets vérifiés. Tar Linux/manifeste/packs digests conformes ; vrai updater ELF changé, hash2ee7ddc5…,32programmes gérés conformes, sixmodulesCUDA et Vulkan inchangés .95. Identité du dossier mpv recalculée égale au manifeste (`91db1a94…`). **AH335 Done**, commentaire10298 ; parentAH226 conserve ses reliquats.

**3.8.0.96 vérifiée**, source `f71a17bac81d8f87af1ffeeda43ab4a4066464a8`, [reçu .96](jira/release-20261017-3.8.0.96.json). TroisCI réussies/tag16assets ; archive Mac digest conforme, dylib **67805bd1a0c6dea078fd0a14c26467cf7e81a9d207c4b14da69f4483b9dda190**, byte-identique aux deux qualifications natives,17programmes et32ressourcesmodèles vérifiés. **AH349 Done**, commentaire10297 ; AH119 garde CoreML/RIFE/rendu. Aucun replay natif si mêmes octets.

Pins actuels : Manager `f1f85962f8e86e5f37d84501f37f72b6d1780828`, bundle `6598d4fa1bf4d1b988576d56afa39c72437f35c7`. Dispatcher Linux source118c272, TRT/alias/pipeline source9d2c717, fatbinArea source3447cd8 ; GPU-SOURCE.json module_sources fait autorité, ancien backend_source global historique. Ne pas attribuer le SHA dispatcher aux autres modules.

## Lot terminé — AH364 : transaction CoreML

Checkout `/home/ta2b/.animejanai-tools/work/lot-76-coreml-transactions-20261017`, branche `tickets/coreml-transaction-generations-20261017`, base .97. AH364 et AH254 In Progress ; sous-ticket explicite sousAH32, car AH254 est déjà un sous-ticket. Périmètre .mlmodelc natif macOS uniquement, autresproviders/Windows restent ouverts dansAH254.

Implémentation candidate : namespace coreml-tx1/hash, clé de programme p3 inchangée ; snapshots privés dont le tagV2 doit égaler le tag initial avant patch/compile ; chemins AJP relatifs bornés au package ; verrou commun stable parclé, doublelecture, staging possédé récupérable. Validation CoreMLCPU avant publication, génération conservée et pointeur atomique, aucune suppression de génération après loadfailed. Erreur spécifique device/hints distinguée d’un artefact invalide par chargementCPU indépendant ; retrait uniquement du commit qui vise encore la génération invalide. Hits sans écriture/verrou, anciennes générations conservées (pas de GC sans leases).

Fixture du vrai protocole POSIX passée : commit/record strict, mauvaispointeurs/liens refusés, reprise après kill réel, préservation inconnus/autreskeys/anciennes générations, stale-retire et hit readonly. Snapshot neutre d’un vrai modèle a le même tag ; trois chemins AJP absolus/parents refusés avant écriture. Qualification native39023454995 réussie via qualify-coreml-transactions.yml : macOS15.7.9/24G830/arm64, CPU256 vrai modèle déjà livré .88, référence18df… exacte, demandes chevauchées/unecompile, kill/reprise, artefactinvalide/réparation/anciennegénération conservée, readonly. .98 vérifiée sur troisCI/tag16assets et vrai moduleMac, [reçu](jira/release-20261017-3.8.0.98.json) ; Done10303 ; [guide](reprise/20261017/AH-364.md), [preuves](qualification/lot76-coreml-transactions-20261017/README.md). Aucun benchmarkFPS, aucune nouvelle conversionmodèle. Ne pas répéter les preuves AH244/AH240.

## Lot terminé — AH365 : SPAN CoreML résident

Checkout `/home/ta2b/.animejanai-tools/work/lot-77-coreml-resident-span-20261017`, branche `tickets/coreml-resident-span-20261017`. Sous-ticket réel d’AH119, In Progress. Candidate9e03e0c559af3b212382a439224a58d3368fa717, hors release avant qualification. Résultat CVPixelBuffer réel retenu, backing renouvelé seulement si sortie encore possédée, suppression des conversions RGB intermédiaires sans changement des modèles/options. AblationCoreML distincte de Metal, compteurs de conversions hôte distincts des transferts GPU. Core syntax-check passé ; nativeCI39023928908 réussie sur deux vrais modèlesCPU256→512→1024 : base/off/on exacts3f38af37, deux conversions supprimées (1,5Mio RGB), resize/reconfigure/ownership/format invalide passés. Dylib candidat7816d2a5…, médianes troisappels149,817→150,700ms : aucun gain tempsCPU établi, utilité = travail hôte supprimé. .99 vérifiée sur les troisCI/tag16assets/dylib exact, Done10303. [Guide](reprise/20261017/AH-365.md), [preuves](qualification/lot77-coreml-resident-span-20261017/README.md). [Guide parent actualisé](reprise/20261017/AH-119.md). Aucun replay des transactions AH364 ni prétention FPS720p/GPU/ANE.

## Livraisons récemment terminées — réutiliser les preuves

| Release | Tickets et preuves |
| --- | --- |
| .95 | AH363/AH362 Done10292/10293, [reçu](jira/release-20261017-3.8.0.95.json). Identité native calculée et build-info livré ; force package complet si lecteur changé. RouteQuality historique Linux et snapshot immuable, pas de calculpixel changé. ParentAH330 ouvert. |
| .94 | AH351 Done10290, [reçu](jira/release-20261017-3.8.0.94.json). DeuxSPAN Vulkan résidents, frontière F32 conservée, RGB exact, médiane locale3,214→2,337ms ; pas de FPS720p/autresGPU prétendus. ParentAH131 ouvert. |
| .92 | AH361 Done10285, [guide](reprise/20261017/AH-361.md). ContratQualityCABI du pipelineCUDA, contrôle vraie image/module et flags ; anciensQuality inconnus refusés, Fast explicite inconnu conservé. Fatbins byte-identiques, aucun replaynumérique nécessaire. |
| .91 | AH240 Done10282, [guide](reprise/20261017/AH-240.md). IdentitéCoreMLp3 : poids/formes/recette/framework/OS/ISA ; CPU256 natif exact18df…/hit. AH254 transaction distinct. |
| .90 | AH360 Done10279, Area3:2 entier,2 764 800valeurs exactes, pas de gainFPS mesuré. |
| .89 | AH352/AH321 Done10276/10277, choixArea/Spline36 ; compromis qualité, pas de meilleur universel ni gainFPS prétendu. |
| .88 | AH244/AH359/AH358/AH29 Done : manifestesCoreML stables/cyclecache natif ; SPANB4 FP16 change la première sortie, étude arrêtée, aucun Quality activé. |
| .87 | AH348 Done10267 : diagnosticCoreML asynchrone, premièreimageCPU pendant pending, référenceRGB exacte, pas de traceGPU réelle. |
| .86 | AH354/AH356 Done : batchQuality natif ; étudeencodeurRIFE exacte mais raccordruntimeAH357 reste ToDo. |
| .85 | AH338/AH345/AH346/AH347/AH355 Done : programmes gérés et copies/attentes supprimées. |

[Guide AH349](reprise/20261017/AH-349.md), [preuve Metal](qualification/lot73-metal-resident-span-20261017/README.md) : Apple Paravirtual/unified/macOS15.7.9arm64, deuxSPAN128→256→512, RGB exact2aa21507, staging245760→49152/readBytes983040→786432, médiane courte17,178→15,497ms. Resize/reconfigure et seul défautsecondgraphe/reconfigure exact passés. Pas de GPUApplephysique, FPS720p ou copiesinternesdriver revendiqués.

[Guide AH335](reprise/20261017/AH-335.md), [preuve updater](qualification/lot75-preserve-manifest-20261017/README.md) : socleconfigs conservé même sans manifeste valide, cinqcasCPU du vrai ApplyOver/inventaire conclus, sauvegardesexistantes réutilisées. Liensprofils non suivis, valeursmanquantes amorcées. Build updaterRelease passé, deuxCA1416 préexistants. Aucun testvidéo requis.

## Autre livraison en cours — AH344 Windows DirectML

Producteur run **39019317771**, source32464bc, toujours actif à la dernière vérification (« Build both static entry points »). Deux échecs précédents résolus : libassHEADdétachée (aa49479), puis c-ares clone depth1/defaultcoverity_scan au lieu de main ; maintenant main épinglé f4156c12 et clonepartiel sansdepth. Cache des dépendances conservé. Vérifier seulement en fin de tâche ; aucun watch/poll/sommeil d’attente.

Checkout producteur `lot-71-windows-producer-20261017`. À réussite : vérifier tag windows-mpv-SHAcomplet, troisPE/provenance/patch/source ; ensuite seulement créer windows-mpv-source-ref.txt et livrer la paire. Aucun cacheDML actif annoncé tant que lecteur apparié absent. [Guide AH344](reprise/20261017/AH-344.md). Le DLL seul n’est pas une qualification Windows matérielle.

## Problème de débit Quality×4 — toujours ouvert

AH329/208/73/76 : chaîne complète Area720→RIFE426Quality4+SPAN1440→TrueHDR ≈46,4ms/intervalle contre budget41,7ms source24fps. Fusion active et modules .84 réellement mappés dans l’instance contrôlée ; aucun ancienmoteur démontré dans cette instance. Les garde-fousQuality ne résolvent pas ce budget. AH357 ToDo : encodeur partagé exact aux troisphases, étude gainréseau local≈0,656ms/3,15%, pas de gainlecteur établi. SPANB4 n’est pas Quality exacte. Profil/médias privés dans artifacts/performance/lots-20261017/quality-live-20261017 ; installation utilisateur inchangée.

## Contrats de reprise

In Progress au début ; Done après périmètre complet, qualification nécessaire et livraison vérifiée ; parents partiels ouverts. Essais courts ciblés mêmes entrées/modèles/réglages/machine. Réutiliser preuves concluantes ; UI/docs/packaging contrôles simples. Distinguer gain attendu, travail supprimé et FPS mesuré. RéférenceQuality conservée ; approximationFast explicite, besoins propres aux moteurs respectés. API/matériel absents = qualification partielle, jamais fauxDone. Lancer builds/releases puis avancer, consulter en fin de tâche ; aucun travail concurrentGPU pendant mesure. Strata facultatif, non utilisé.

[Guides](reprise/20261017/README.md) · [Protocole](PROTOCOLE-VALIDATION-FEATURES.md) · [Archives](ARCHIVES.md). AH334 audit/AH340 nettoyage déjà clos : ne pas réimporter ni rejouer leurs inventaires. HDRavantinterpolationAH333 demandé pour plus tard.

## Travail actif — AH353 : plan canonique du lanceur macOS

Checkout PLAYER lot-78-macos-profile-plan-20261017, branche tickets/macos-canonical-profile-plan-20261017 ; source044c53a80c00b6fa88d25f45806af30a5d1d9e8c poussée sur branche seulement. Manager isolé lot-78-canonical-manager-20261017 depuisf1f8596, source37e7c1ad2ad12982d2b8197824f7c15c28e00958 publiée sur les troisOS (CI39025011499), player-source-ref044c53a. .100 épingle ce Manager ; à publier/vérifier avant Done AH353/AH339. Lanceur async/timeout5s/cancellation, snapshot et policy privée conservés, modèle/runtime exacts via helperbundle. CLI --models-dir/--rife-dir, ContextAppleDevice ; ProfileHdr macOS indépendant de la règle, rule0 n’exige aucun modèle des règles inactives. TestsCLI10cas +4HDR et vraiefixtureLua gardes/snapshot/timeout/stale/off concluants ; aucun testvidéo nécessaire. Buildhelper0erreur/0warning ; Manager sourcepartagée initiale compilée0erreur/43warnings préexistants, production finale troisOS et tag immuable vérifiés ; présence dans le paquet .100 à vérifier. AH339 reste ouvert jusqu’à la livraison complète de ce reliquat.
