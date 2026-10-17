# État courant — reprise du travail

Mis à jour le **17 octobre 2026**. Lire AGENTS.md, puis seulement le ticket et les contrats utiles. Les demandes actuelles priment sur les archives. Jira existant **AH** : https://tatoub.atlassian.net/jira/software/projects/AH/boards/2 ; connexion en lecture/écriture vérifiée, ne pas réimporter le backlog.

## Mission

Continuer les tickets par lots complets, sans pause. Après chaque push, avancer sur une tâche indépendante et vérifier les builds à sa fin ; aucun watch/poll/sommeil d’attente. Pas de nouveaux agents. Conserver profils, médias, SDK, modèles et modifications utilisateur ; checkouts isolés, git add explicite, jamais add-A/reset/clean global ni push au backend utilisateur original. Le checkout IDE est ancien et modifié : relais documentaire seulement.

## Livraison courante vérifiée : 3.8.0.105

Source `b82f358540dfadca2f3857e604e2745fcc6d07fe`, [reçu .105](jira/release-20261017-3.8.0.105.json). Trois CI réussies, tag exact, 15 assets et digests des manifestes téléchargés vérifiés. **AH357 Done pour décision de rejet complète**, aucun candidat moteur activé. Code runtime et pins strictement identiques à .104.

### .104 et livraisons précédentes

Source `26dea3562f7d9260b0c935d6e25bfb562a152eff`, [reçu .104](jira/release-20261017-3.8.0.104.json). Trois CI release réussies, tag exact et assets vérifiés. Archive Mac SHA25680ab0fc3…,17programmes gérés conformes. Dylibf13aafd1… **identique au module natif et au consommateur mpv qualifiés**, option/lifecycle du filtre présents dans le vrai mpv livré ; défautvideotoolbox-copy conservé.

**AH350 Done**, commentaire10316 : import expérimental NV12SDR709 vers textures Metal possédées, natif et vrai filtre39029415108 conclus. Plans/PTS/couleur exacts ; replis601/P010HDR exacts avec10bits/PQ, owners0 et reset. [Preuve](qualification/lot80-videotoolbox-metal-import-20261017/README.md), [guide](reprise/20261017/AH-350.md). Ne pas rejouer. AppleParavirtual/macOS15.7.9, FFmpeg9.0.1_1/libplacebo7.360.1/MoltenVK1.4.2 ; aucun FPS/GPUApple physique ni rendu macvk qualifié. Option apple-import-probe=yes/slot0 sans inférence ; **AH120 reste In Progress** pour entrée moteur fidèle et sortie rendu.

**.103 vérifiée**, [reçu](jira/release-20261017-3.8.0.103.json). **AH344 Done10315 pour implémentation/compilation/livraison** : producteurWindows39019317771/source32464bc…, troisPE x64 appariés et provenance exacts ; paquet réel,36programmes gérés et cinqDLLGPU vérifiés. DML et dispatcher sont inclus dans le core. **Qualification GPUWindows non faite : AH367 To Do**, étapes détaillées dans [son guide](reprise/20261017/AH-367.md). ParentAH93 reste ouvert. Ne pas recompiler deux heures le producteur déjà publié ni assimiler compilation et FPS.

**.102 vérifiée**, [reçu](jira/release-20261017-3.8.0.102.json), **AH353 Done10311 et AH339 Done10312**. Plan canonique macOS et hook de préchargement corrigés : vrai mpv, première sortie slot0 avant/slot1 après, erreur helper libère la lecture. [Guide](reprise/20261017/AH-353.md), [preuve](qualification/lot81-macos-preload-gate-20261017/README.md). Sources et preuves Windows/Linux .84 réutilisées. Dylib7816d2a5… inchangée .99 pour ce lot.

**.101 vérifiée**, [reçu](jira/release-20261017-3.8.0.101.json), **AH366 Done10309** : formes ONNX en streaming, dimensions/cache/fallback conservés ; sparse128Mio,134219232→5840octets alloués et90octets logiques lus. Helper livré détecte5D correctement. Manager Linux recompilé par la CI PLAYER : son hash diffère légitimement du tag autonome ; sourceb69968a/codeStream et blob partagé97e325e vérifiés. Aucun gainFPS d’inférence revendiqué.

Pins conservés en .105 : Manager `b69968a8a30cedc83b28820ca14d014abcb36928`, source partagée `97e325efb59e80d2eac7dfc685192052a01d7399`, bundleGPU `dc53e6cacdff59c1f243226d9575b5079bae9c9e`, lecteurWindows `32464bc13260918381537dbb73a5a2e7523c2477`. Module_sources de GPU-SOURCE fait autorité : dispatcherLinux118c272, TRT/alias/pipeline9d2c717, fatbinArea3447cd8 ; WindowsDML/dispatcher/TRTd5b34469 et AMD652fbc6. Ne pas attribuer un SHAglobal à tous les modules.

## AH357 conclu — encodeur RIFE partagé rejeté

PLAYER `/home/ta2b/.animejanai-tools/work/lot-83-rife-shared-encoder-player-20261017`, branche tickets/rife426-shared-encoder-runtime-20261017. Backend isolé lot-83-rife-shared-encoder-backend-20261017, candidatlocal82c82959b187288432d3b84b70b8c6a44e7ea0cc depuis118c272. **Candidat rejeté, aucun nouveau binaire moteur à livrer**. .105 contient seulement outils/preuves/documentation, livraison vérifiée et décision de rejet complète. [Guide précis](reprise/20261017/AH-357.md), [reçu de rejet](qualification/lot83-rife-encoder-runtime-20261017/native-rejected.json).

Dérivation C++ sans Python, snapshots encoder/head et deuxbindings contrôlés ; opérateurs/poids/IO exacts à l’outilPython étudié. Compilation native et troisplans TRT terminées. Nouveau contrôle ABI9 sur mêmes sources privées720p, mêmes plans et machineRTX4070Ti/TRT11.3 : candidat off exact aux troisphases ; candidaton échoue dès.25,1 053 807/2 764 800valeursuint16 différentes, max88. Arrêt immédiat avant timing, phaseson suivantes/reset/cache/legacy non exécutés. Les graphes séparés/tactiques sont une hypothèse de cause, pas une conclusion vérifiée. Les anciennes preuves réseauAH356 ne qualifient pas ce raccord natif.

Le patch rejeté et son protocole sont versionnés comme recherche, jamais à appliquer en production. Plans/binaires/entrées restent dans lot-83-rife-encoder-proof-20261017. Une reprise éventuelle doit viser seulement le cas.25 échoué après hypothèse concrète ; aucun replayoff/AH356 ni benchmark avant exactitude. La référence livrée4c1074ed… demeure intacte.

## Lot actif prioritaire — AH369, ajout d’étapes dans le Manager

Régression utilisateur reproduite via les vrais boutons Avalonia Headless : menu ouvert, contexte et commande valides, clic Interpolation n’ajoute rien. Le Click ferme le Flyout avant l’exécution de la commande, ce qui détache son binding. Correctif : fermeture différée sur le dispatcher UI.

Manager isolé `/home/ta2b/.animejanai-tools/work/lot-85-manager-add-step-20261017`, branche perf-specialized-manager-add-step-20261017 ; test `tests/AddStepUi` : échec avant, quatre catégories/sélection inactive/fermeture/sauvegarde-rechargement puis gardes HDR unique/plafond16/schéma futur passés après, sans replay. Aucun moteur/vidéo changé. Producteur trois OS lancé ; livraison PLAYER .106 à faire après disponibilité des assets. AH369 In Progress, parent AH224 reste ouvert. PLAYER isolé `lot-85-manager-add-step-player-20261017`.

AH368 In Progress : étude bornée d’ordonnancement Quality RIFE→SPAN, **aucun code ni gain encore**. Checkouts propres lot-84-quality-stage-major-{player,backend}-20261017, backend base118c272 (jamais candidat rejeté82c8). Reprendre après correctif Manager ; lire ticket détaillé. Corriger son chemin de fichier en `include/surface_cuda_state.h` avant implémentation.

## Problème Quality×4 toujours ouvert

AH329/208/73/76 : chaîne Area720→RIFE426Quality4+SPAN1440→TrueHDR ≈46,4ms/intervalle, budget41,7ms à24fps. Fusion et modules .84 étaient réellement actifs ; aucun ancien moteur démontré dans l’instance contrôlée. Les optimisations de métadonnées et garde-fous ne résolvent pas ce budget. SPANbatch4 modifieFP16 (AH358 rejeté), encodeur partagé natif actuel rejeté (AH357). Étudier une autre piste bornée avant nouveau ticket, notamment ordonnancement/fusion réelle si pas déjà fait. Profils/médias de référence privés : artifacts/performance/lots-20261017/quality-live-20261017 ; installation utilisateur inchangée.

## Autres lots conclus : réutiliser les preuves

| Release | Conclusion et limites |
| --- | --- |
| .99 | AH365 Done10304 : SPANCoreML résident, RGB exact,1,5Mio de conversionsRGB retirées ; aucun gain tempsCPU établi. Dylib7816d2a5… exact. AH119 conserve RIFE/rendu. |
| .98 | AH364 Done10303 : générationsCoreML, snapshot/lock, natifCPU exact, overlap/kill/reprise/corruption/readonly ; anciennes générations conservées. AH254/32 autresproviders ouverts. |
| .97 | AH335 Done10298 : configurations protégées sans manifeste valide, sauvegardes/liens ; cinqcas du vraiupdater. AH226 reste ouvert. |
| .96 | AH349 Done10297 : SPANMetal résident exact, copies retirées, gain courtlocalVM≈9,8% ; pas de FPS720p/GPUApple physique. |
| .95/.94 | AH363/AH362 identitébundleLinux/routeQuality historique Done ; AH351 SPANVulkan résident exact, gainlocal≈27,3%. AH330/131 ouverts. |
| .92/.91 | AH361 contratQualityCUDA et AH240 cléCoreMLp3 Done. Guides/reçus conservés. |
| .85–.90 | AH338/345/346/347/355,354/356,348,244/359/358/29,352/321,360 Done. Ne pas rejouer les catalogues historiques. |

## Contrats de reprise

Chaque ticket travaillé In Progress ; Done après périmètre complet, qualification nécessaire et livraison vérifiée, parents partiels ouverts. Découper les reliquats explicites comme AH367. Essais moteur courts, mêmes entrées/modèles/réglages/machine, arrêt dès conclusion ; absence matériel/bruit = qualification partielle, jamais résultat inventé. UI/docs/packaging : contrôles simples adaptés. Quality conserve sa référence ; approximationFast explicite. Distinguer travail supprimé, gain attendu et FPS mesuré. Aucun build ou travailGPU concurrent pendant une mesure. Strata facultatif, inutilisé.

[Guides](reprise/20261017/README.md) · [Protocole](PROTOCOLE-VALIDATION-FEATURES.md) · [Archives](ARCHIVES.md). AH334 audit/AH340 nettoyage sont clos. HDRavantinterpolationAH333 demandé pour plus tard.
