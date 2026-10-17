# État courant — point d’entrée IA

Mis à jour le **17 octobre 2026**. Lire `../AGENTS.md`, puis seulement le ticket et ses contrats utiles. Les demandes récentes et Jira réel priment sur les archives. Projet existant **AH** : https://tatoub.atlassian.net/jira/software/projects/AH/boards/2 ; connexion vérifiée, ne pas réimporter le backlog.

## Mission et dernière livraison vérifiée

L'utilisateur demande de poursuivre les tickets par lots complets, sans attendre les builds/releases. Aucune pause active. Pas de nouveaux sous-agents ; les précédents ont terminé.

Dernière release vérifiée **3.8.0.94**, source `856f2c17e2276f46546a2d85519844d87acc80a6`, [reçu](jira/release-20261017-3.8.0.94.json). Trois CI réussies,15assets et tag vérifiés ; overlay Linux/digests/6modules/32programmes conformes, marqueur Vulkan résident. Une sortie du vrai module Ubuntu livré (hash031dc1f8) identique à la référence2a83161a,2inférences/1upload/1download. AH351 Done, commentaire10290. Pas de timing/erreur/domaineFP16 rejoué ; autres payloads inchangés réutilisés (.93lecteur, .91Mac, .87Windows). .95 packaging en publication ; AH362/AH363 attendent ce couplage d’upgrade, pas de fauxDone.

Manager toujours `f1f85962f8e86e5f37d84501f37f72b6d1780828`. Bundle .92 `71f271a6c94f2693e8a1a8b550e2f72fd1137f9e` : TRT/alias et pipeline source9d2c717, fatbin Area3:2 source3447cd8. Sources exactes par module dans GPU-SOURCE.json ; son ancien champ backend_source global est historique.

## Lot vérifié : AH-361, release .92

Tranche explicite sous **AH330** : garantir Quality dans le pipeline CUDA ordonné et exposer le module réellement chargé. Le parent conserve routes ABI9 historiques, alias TrueHDR, dispatcher/résolveur et autresOS ; ne pas le fermer avec cette tranche.

- PLAYER : `/home/ta2b/.animejanai-tools/work/lot-70-quality-contract-player-20261017`, branche `tickets/pipeline-quality-contract-20261017`.
- Backend : `/home/ta2b/.animejanai-tools/work/lot-70-quality-contract-backend-20261017`, source `9d2c717f756c632c9c2d0acc53479fd8690586cb`, remote GitHub Ta2b/animejanai-inference-rtx. Backend utilisateur original intact.
- Bundle préparé : `/home/ta2b/.animejanai-tools/work/lot-70-quality-binaries-20261017`, pin 71f271a6c94f2693e8a1a8b550e2f72fd1137f9e. Linux TRT/alias `4c1074ed7cd31361c99e991966e86a45e3092fb13531fe6a773c73cc9cdf302e`, pipeline `834ca0a740b92e632b5ea63b07f5da28326d6bd2cc72f67b08ed6a8f6b9b39bc`. Windows/dispatcher/fatbin Area conservés avec leurs propres sources.

[Guide AH361](reprise/20261017/AH-361.md), [preuves lot70](qualification/lot70-quality-contract-20261017/README.md). CABI optionnel configuré, même image ELF pour create/configure/process/contrat ; un symbole emprunté à une dépendance ne certifie pas le moteur. Quality inconnu refusé avant create/configure ; après configure, policy/flags réels contrôlés. Fast ancien reste accepté avec effectiveunknown. Une ligne par activation, aucun query par image. Source déclarée du binaire unknown (Git absent du build portable), distincte de la provenance et du hash fichier.

Qualification complète : fixtureCPU avec vrais DSOs passée ; native RTX4070Ti : ancienQuality seul refusé, actuelQuality fusionné/flags1, actuelFast/flags2, ancienFast accepté/inconnu ; erreurs CABI sans écriture du buffer. Zéro image vidéo traitée, aucun calculpixel changé ; section deviceTRT byte-identique à .86 et fatbin pipeline identique à .90. Réutiliser les preuves numériques acquises, pas de replay13images/FPS. Build portable sans RPATH local ; pas de nouvelle qualification Windows/AMD/Intel/macOS.

**Livraison .92 vérifiée : AH361 Done (commentaire10285).** Ne pas répéter les configurations concluantes sur ces mêmes hashes. AH330 reste ouvert.

## Travail actif : AH-362, route historique et snapshot Linux

PLAYER `lot-71-legacy-quality-player-20261017`, backend `lot-71-legacy-quality-backend-20261017`, MPV `lot-71-mpv-legacy-quality-20261017`. Dispatcher source118c272 : transfert sur innerhandle et garde de même image ; fixtures DSO API présente/absente/dépendance seule passées. Neuvième patch Linux : rife-policy auto/quality/fast, garde après configure/avant pixels, GET_META ; source C compilée/liée, patch exact sans fuzz. Snapshot immuable : banque, helper, contexte et diagnostic décrivent la même version. Fixture Lua passée ; Manager reload-options recréait déjà le filtre, ne pas prétendre une panne UI générale.

Contrôle natif conclu : dispatcher actuel Quality verified/flags1 et vrai chemin innerTRT ; ancien Quality failed, zéro inférence RIFE et repli MPV original ; ancien Fast explicite accepted/unknown. Aucun calcul vidéo changé ni FPS revendiqué. [Guide](reprise/20261017/AH-362.md), [preuves lot71](qualification/lot71-legacy-quality-20261017/README.md). Bundle6598d4fa1bf4d1b988576d56afa39c72437f35c7 ne change que le dispatcher Linux (hash592a8289) ; TRT/pipeline/kernels/Windows préservés avec leurs sources. .93 poussée source04b3cb524a85fc54f6c05abc4441fef79682e98d, CI Windows39019535179/macOS39019535194 réussies, Linux39019535185 construit encore le lecteur. Vérifier lecteur Linux complet/libmpv, marqueur legacy_rife_contract=1, dispatcher et Lua avant Done. AH330 reste ouvert.

## Travail actif : AH-351, SPAN Vulkan résident

Checkout `lot-72-vulkan-resident-span-20261017`, branche tickets/vulkan-resident-span-20261017. Base .93 source04b3cb524a85fc54f6c05abc4441fef79682e98d. Deux vrais SPAN128→256→512 sans download/upload intermédiaire ; frontière F32×255 puis×1/255 et stockage NCNN conservés. GPU RTX4070Ti : pixels exacts à base/off/on, domaineFP16 fini exact aux deux stockages, resize/repli et erreur/reconfigure passés ; médiane courte3,214→2,337ms, pas de FPS720p/autresGPU revendiqués. [Guide AH351](reprise/20261017/AH-351.md), [preuves lot72](qualification/lot72-vulkan-resident-span-20261017/README.md). Livraison .94 vérifiée, AH351 Done ; réutiliser ses preuves, aucun replay. Parent AH131 In Progress reste ouvert.

## Livraison en correction : AH-363, identité native Linux

Checkout `lot-74-native-bundle-identity-20261017`, branche fix/linux-native-bundle-identity-20261017. .93 : trois CI réussies,15assets, AppImage/overlay/manifeste téléchargés et digests vérifiés ;6modules/32programmes dans chacun, quatre binaires/libmpv portent la garde, interface rife-policy du vrai lecteur livrée vérifiée. [Reçu .93](jira/release-20261017-3.8.0.93.json). AH362 reste In Progress car le deps.mpvfork manuel inchangé permettait un overlay de dossier sans le lecteur neuf. AppImage fraîche/complète correcte.

AH363 calcule maintenant l’identité du bundle mpv assemblé depuis ses fichiers, copie son build-info et force le package complet si le natif change. Fixture CPU du vrai calcul/décision d’overlay passée ; assembleur .NET10 compilé sans erreur/avertissement. [Guide](reprise/20261017/AH-363.md), [preuve lot74](qualification/lot74-native-bundle-identity-20261017/README.md). Livrer .95 puis vérifier identité sur tar/build-info avant Done AH363/AH362. Pas de changement vidéo. AH335 reste distinct.

AH349 / parent AH119 In Progress : checkout `lot-73-metal-resident-span-20261017`, candidat1b2d967 sur sa branche seulement, **hors release/main**. Interface ResidentImage interne typée RGB8NHWC/MetalGraph/device/owner, exécutions synchrones ; deux SPAN GPU reliés à frontière UInt8 conservée, repli géométrie/reuse/boost/tiles/RIFE. Syntaxe du core C++ passée ; ObjC++/pixels/utilité attendent le workflow qualify-metal-resident-span.yml, source de workflowf0d971a enregistrée sur hdr-3.8. Modèles réutilisés .91, aucun nouveau modèle converti. Documentation Apple officielle confirme run synchrone ; options graphes par défaut conservées, ne pas prétendre suppression des copies internes du driver. Reprendre qualifications, pas de performance/Metal opérationnel annoncé sans preuve native.

## Autre livraison en cours : AH-344 Windows DirectML

Backend DML exact-pair compilé ; lecteur apparié non livré. Premier producteur39006425781 échoué au nettoyage libass sur HEAD détachée. Correctif `aa49479` : SHA40 préservés, contrôle CMake/Git passé, sauvegarde explicite des dépendances même en échec. Run39013899609 a passé libass mais échoué au clone c-ares : branche par défaut coverity_scan, clone manuel depth1 puis checkout main absent. Correctif32464bc : main épinglé f4156c12 et clone partiel sans depth ; clone/checkout réel passé. **Run39019317771** relancé avec dépendances en cache ; vérifier seulement en fin de tâche, jamais watch/poll/sommeil d’attente.

Producteur : `/home/ta2b/.animejanai-tools/work/lot-66-windows-producer-20261017`. À réussite, vérifier tag `windows-mpv-<SHA complet>`, trois PE/provenance/patch/source, puis créer le pin `windows-mpv-source-ref.txt` et livrer le lot apparié. Les fixtures de collecte/assembleur sont déjà concluantes. Aucun cache DML actif annoncé dans .85 à .92 tant que ce lecteur manque. [Guide AH344](reprise/20261017/AH-344.md).

## Tickets terminés récemment et limites

| Livraison vérifiée | Tickets Done et preuve |
| --- | --- |
| .85 | AH338/345/346/347/355, [reçu](jira/release-20261017-3.8.0.85.json) : fichiers gérés préservés et suppressions de copies/attentes inutiles. |
| .86 | AH354/356, [reçu](jira/release-20261017-3.8.0.86.json) : batch Quality natif direct ; étude encodeur RIFE partagée, sans raccord runtime. |
| .87 | AH348, [reçu](jira/release-20261017-3.8.0.87.json) : diagnostic CoreML asynchrone, première image pendant pending, RGB exact sur CPU. |
| .88 | AH244/359/358 et parentAH29, [reçu](jira/release-20261017-3.8.0.88.json) : manifestes stables/cycle natif cache ; étude SPANB4 rejetée pour Quality exacte, pas d'activation. |
| .89 | AH352/321, [reçu](jira/release-20261017-3.8.0.89.json) : compromis Area/Spline36 conclus, deux choix conservés, aucun meilleur universel/FPS inventé. |
| .90 | AH360, [reçu](jira/release-20261017-3.8.0.90.json) : Area3:2 entier,2 764 800valeurs exactes, pas de gainFPS mesuré. |
| .91 | AH240, [guide](reprise/20261017/AH-240.md) : identité compilée p3 (poids, formes, recette, framework/OS/ISA), CPU natif exact/hit. AH254 transactions reste distinct. |

**Manque de débit Quality×4 toujours ouvert** (AH329/208/73/76). Dernière chaîne native complète Area720→RIFE426Quality4+SPAN1440→TrueHDR : environ46,4ms par intervalle, budget41,7ms pour une source24fps. Fusion active et modules .84 réellement mappés dans l'instance contrôlée ; aucun ancien moteur démontré dans cette instance. Ne pas annoncer96FPS ou prétendre que les garde-fous résolvent ce budget. AH357 ToDo : raccord runtime de l'encodeur partagé (étude exacte, gain réseau local≈0,656ms/3,15%, pas de gain lecteur établi). SPANB4 change la première sortie FP16 : étude arrêtée, aucune activation Quality.

Profils/médias de référence privés dans `artifacts/performance/lots-20261017/quality-live-20261017/`, installation utilisateur inchangée. Le checkout IDE racine est ancien et modifié ; il sert de relais documentaire, jamais de source de release. Copier seulement l'ETAT agent si son contenu correspond à la précédente copie agent ; préserver toute modification utilisateur.

## Contrats de reprise

- Checkouts isolés, fichiers explicites dans git add ; jamais git add -A, reset/clean global ou push au backend utilisateur d'origine. Préserver profils, médias, SDK, modèles et modifications inconnues.
- In Progress au début ; Done après périmètre complet et livraison vérifiée. Reliquats en sous-tickets explicites ; parents partiels ouverts.
- Tests courts uniquement pour une incertitude réelle. Réutiliser les preuves concluantes. UI/docs/packaging : contrôles simples ; source/compilation suffit quand l'effet statique est établi. Distinguer suppression de travail, gain attendu et FPS mesuré. Aucune validation matérielle inventée.
- Quality conserve sa référence ; approximations Fast explicites. Besoins propres à chaque moteur respectés. Matériel/API absent ou bruit : qualification partielle, pas de fauxDone.
- Lancer builds/releases puis avancer ; consulter à la fin de la tâche. Aucun travail concurrent GPU pendant une mesure. Strata facultatif s'il aide ; non utilisé dans ces lots.

[Guides détaillés](reprise/20261017/README.md) · [Protocole](PROTOCOLE-VALIDATION-FEATURES.md) · [Archives](ARCHIVES.md). Audit global AH334 et nettoyage AH340 déjà clos ; ne pas réimporter/rejouer leurs inventaires. Les catalogues historiques ne sont pas une batterie obligatoire. HDR avant interpolation AH333 reste demandé pour plus tard, sans déplacement implicite.
