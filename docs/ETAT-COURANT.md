# État courant — point d’entrée IA

Mis à jour le **17 octobre 2026**. Lire ce fichier et `../AGENTS.md`, puis uniquement le ticket et les contrats nécessaires. Les demandes actuelles de l’utilisateur et Jira réel priment sur les archives. Ne pas réimporter le backlog AH.

## Mission actuelle : lots complets, cache CoreML et débit Quality

Reprise continue demandée par l'utilisateur. Dernière release vérifiée **3.8.0.88**, source `4b73312b8dddbf1902e1b8e6a8a6c2724ed71fb6` ; [reçu](jira/release-20261017-3.8.0.88.json). Trois CI réussies, tag exact et15assetsuploaded ; paquet macOS modifié téléchargé/digest vérifié,32ressources modèles identiques aux copies .86/.87 normalisées et17programmes vérifiés. Windows/Linux : métadonnées etCI vérifiées, qualification des payloads inchangés réutilisée de .87 ; pas de téléchargement répété. CoreML natif CPU sur Apple M1 virtualisé/macOS15.7.9 : cache et manifeste qualifiés, pas de GPU/ANE/ORT ou FPS général annoncé.

**Done après livraison : AH338/345/346/347/355 (.85), AH354/356 (.86), AH348 (.87).** [Reçu.85](jira/release-20261017-3.8.0.85.json), [reçu.86](jira/release-20261017-3.8.0.86.json). Parents AH329/73/76/121/29/330 conservent leur portée restante. Le manager reste `f1f85962f8e86e5f37d84501f37f72b6d1780828`, bundleGPU `ff27fba988b75e00c1348195266455ce0992428a`, backendNVIDIA `d5b34469a3aa1cc30f107ba3122699d713de1dca`. Ne pas annoncer le cache exact DML actif : son lecteur apparié reste à livrer.

**Lot .88 vérifié — AH359 / AH244 / AH358** : checkout isolé `lot-65-coreml-cache-20261017`. Manifestes déterministes uniquement à la génération, tous les programmes/poids toujours inclus dans le tag V2 ; 32 ressources .86/.87 identiques après normalisation. Qualification native réussie run39013648864, source50c3fd7 : macOS15.7.9 arm64 / Apple M1 virtualisé, CoreML CPU256×256 ; hit réel, normalisation RGB exacte, réexport identique/hit, poids seuls remplacés/rebuild exact au donneur, cache corrompu diagnostiqué puis retry exact, anciennes entrées conservées. [Preuves](qualification/lot65-coreml-cache-20261017/README.md). Pas de FPS ni GPU/ANE qualifiés. Livraison .88 vérifiée ; AH359/244/358 prêts Done et AH29 peut être clos après ses enfants. AH240/254 restent distincts et ouverts.

AH358 sousAH76, étude livrée .88 : étude neuronaleSPANB4 intégrée au lot .88, source initiale `b46672b`. Premier comparatifFP16 non exact (8 063 623/11 059 200valeurs, maxabs0,0107422, MSE1,43062e-7) ; direction perceptuelle inconnue, arrêt avant autresimages/benchmark, aucun runtimeB4 activé. AH76 reste ouvert ; poolsAH53/contextesB1concurrents non faits. [Preuve](qualification/lot64-span-batch-20261017/README.md). Livraison du lot vérifiée ; parent AH76 conserve ses autres critères.

AH344 : backend DML compilé ; premier producteur Windowsmpv39006425781 échoué au nettoyage de libass sur HEAD détachée. Correctif `aa49479` dans `lot-66-windows-producer-20261017` : SHA40 préservés, contrôle CMake/Git court passé, dépendances sauvées même en échec. Nouveau producteur39013899609 en cours, ne pas attendre. Aucun pin lecteur ni cacheDML actif annoncé dans .85 à .89 ; finir le lot apparié après succès et vérification.

Le manque de débit Quality4 reste ouvert : fusionactive, RIFE1280×720 et modules.84 réellement mappés dans l'instance contrôlée ; ce n'était pas un retour à l'ancien moteur. AH354 livré : batch natif direct,4→1attentes finales sans second worker/reaper,13sorties/PTS/couleurs exacts et reset/fallback/erreur qualifiés ; observation complète46,4ms encore au-dessus du budget41,7ms. AH356 : encodeur partagé viable sur un modèle/forme (RGBFP16 exact), gain réseau local≈0,656ms/3,15%, aucun raccordruntime ; suite explicite AH357 ToDo. Ne pas annoncer96FPS. Médias/profils privés conservés dans `artifacts/performance/lots-20261017/quality-live-20261017/`, installation utilisateur inchangée.

Les28guidesJira du relais restent disponibles dans [l’index](reprise/20261017/README.md), complétés parAH354/355. Reprendre seulement ticket/contrats utiles, ne pas réimporter ni refaire les travaux déjà livrés.

- Préserver profils, médias, SDK, modèles, modifications utilisateur et backend d’origine. Sources isolées, chemins explicites dans git add ; jamais git add -A, reset/clean global ou push vers un origin local du backend utilisateur.
- In Progress au début du travail effectif ; Done après périmètre entier et livraison vérifiée. Les parents partiels restent ouverts ; les reliquats ont leurs propres tickets.
- Précision utilisateur du17octobre : pas de benchmark systématique. Revue/compilation si l’effet est suffisamment établi ; essai court seulement pour une incertitude réelle ou une mesure revendiquée. Ne pas répéter un résultat concluant. Pour UI/docs/packaging, contrôles simples. Distinguer bénéfice statique, gain attendu et gain mesuré.
- Quality conserve les prédictions complètes et les frontières numériques de référence. Toute approximation reste Fast explicite. Ne pas forcer la convergence des backends quand leurs besoins diffèrent. Matériel absent : qualification partielle, jamais inventée.
- Lancer builds/releases puis avancer une tâche indépendante ; consulter leur résultat en fin de tâche. Pas d’attente active ni gh run watch. Strata facultatif, aucun concurrent GPU pendant une mesure.

**Travail suivant AH360** : checkout backend `lot-68-area-three-halves-20261017`, source3447cd8 ; PLAYER `lot-68-area-player-20261017`. Area3:2 exact par poids entiers (1080→720), compilation portable terminée ; contrôle natif ancien/candidat restant, aucun FPS revendiqué. Ne pas publier avant fidélité et provenance du bundle.

**Lot .89 en publication — AH352** : comparaison Area/Spline36 conclue, [preuve unique lot67](qualification/lot67-downscale-comparison-20261017/README.md). Guides/reçus/probe uniquement, moteurs et profils inchangés. Spline36 filtre davantage le damier mais crée des halos, Area sans dépassement ; aucun FPS mesuré. Vérifier la livraison documentaire avant Done puis relire AH321 entier. Le lot comprend aussi le correctif du producteur Windows, sans activer son lecteur encore absent.

## Référence précédente : 3.8.0.84

[Release publique](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/releases/tag/3.8.0.84), [reçu principal](jira/release-20261017-3.8.0.84.json), [Linux](jira/release-20261017-3.8.0.84-linux.json), [Windows/macOS](jira/release-20261017-3.8.0.84-windows-macos.json), [qualification Manager](qualification/lot-57-manager-20261017.md), [qualification native](qualification/lot-57-native-fruc-removal-spline36-20261017.md).

Trois workflows réussis au SHA exact, **17 assets publiés**. CI Linux39004574426, Windows39004574310, macOS39004574453. Vérification des digests, contenus modifiés, pins, pipeline Linux, AppRun et Manager. Windows overlay/composant Manager et archive macOS complète vérifiés ; installateur Windows complet non téléchargé. Aucun test vidéo répété lors de ce contrôle de livraison.

| Composant | Référence immuable |
|---|---|
| PLAYER/assemblage | `f626ceb2154f1b90ff5c4e275e8bb31a969f1bc6` |
| Manager | `f1f85962f8e86e5f37d84501f37f72b6d1780828` |
| Source partagée du producteur Manager | `69aca0b866a8625bb53bc265d308743cd1314269` |
| Backend NVIDIA Linux | `36f3d94491b51d334dc9420ce6d5192b086b0a8f` |
| Bundle GPU | `e48fb15b048db5ea39d3becbe9fdede6764f1941` |

Manager Windows/macOS identique aux assets du producteur épinglé. Manager Linux reconstruit depuis ce pin avec les sources partagées PLAYER (contenu identique entre69aca etf626), identique entre composant et AppImage ; ne pas prétendre identité binaire avec l’archive Manager autonome. Installation/profils utilisateur non modifiés. Une release sur trois OS ne qualifie pas tous les GPUs.

Livré : navigation Profils/Préparer/Moteurs et composants/Paramètres ; profils libres, quatre catégories fixes interpolation/upscale/downscale/HDR ; HDRmpv ou TrueHDR, une conversion par profil ; ancien éditeur, trois profils intégrés1001..1003 et doublons retirés ; FRUC retiré avec anciens profils conservés/incompatibilité explicite ; Area/Spline36 indépendant LinuxNVIDIA ; plan partagé et dépendances exactes ; policy RIFE du maillon appliquée via configuration privée ; préparation GMFSS CFR SDR8 CUDA/CuPy. Les six profils de départ propres à macOS ne sont pas annoncés retirés. L’ordre arbitraire reste propre au lecteur LinuxNVIDIA ; les autres moteurs gardent leurs chemins compatibles.

**Done après vérification : AH-313, AH-325, AH-326, AH-328, AH-341, AH-342, AH-343.** Commentaires de preuve10224..10230. AH-224 reste ouvert avec AH-339/AH-353 ; AH-321 reste ouvert avec son reliquat AH-352 (rattaché à AH-297, car Jira ne permet pas de sous-ticket sous un sous-ticket).

Les sources livrées sont dans `/home/ta2b/.animejanai-tools/work/lot-57-manager-ux-20261017` et `manager-ux-20261017`. La copie documentaire racine peut être ancienne et modifiée par l’utilisateur : vérifier pins/status ; ne pas publier son ancien code.

## Tickets restants et livraisons

| Ticket | État exact et prochaine action |
|---|---|
| [AH-344](reprise/20261017/AH-344.md) | In Progress. DLL DML compilée ; producteur mpvWindows39006425781 en cours. Finaliser son pin et sa livraison appariée après succès ; cache non activé par .85 seule. |
| [AH-345](reprise/20261017/AH-345.md) | Done, livré .85. Score Fast>3 inutile retiré, dépendance CUDA conservée ; Aucun nouveau FPS mesuré. |
| [AH-346](reprise/20261017/AH-346.md) | Done, livré .85. Même3F copies finales, F attentes→1 ; chaîne complète13sorties exactes, TrueHDR conservé. |
| [AH-330](reprise/20261017/AH-330.md) | In Progress. Garantir Quality avec les bibliothèques réellement chargées, préserver overrides/fichiers utilisateur. Inventaire sur disque ≠ module déjà chargé. |
| [AH-347](reprise/20261017/AH-347.md) | Done, livré .85. Pads a/b paresseux, pad_o conservé ;11,25Mio évités à720p, pixels Quality exacts. |
| [AH-208](reprise/20261017/AH-208.md), [AH-329](reprise/20261017/AH-329.md) | In Progress. Parents fusion/Quality ; gardes, diagnostic, références effectives et optimisations exactes. Ne pas refaire les mesures lot55 concluantes. |

Patches et preuves portables : `docs/reprise/20261017/{patches,preuves}` avec manifest SHA. Les candidats temporaires peuvent disparaître ; les patches sont sauvegardés/versionnés. Binaires candidats Linux hors Git dans `/home/ta2b/.animejanai-tools/work/lot-58-engine-handoff-20261017/` avec SHA256.json. **Aucun candidat AH-344/345/346 n’est inclus dans .84.**

## Autres premières tranches explicites

États propres aux premières tranches (ne pas confondre livraison et présence du code) :

- AH-348 sous AH-121 : **Done .87**, diagnostic hors attente critique, qualifié CoreMLCPU ; parent conserve la comparaison GPU/ANE/CPU et autres modèles.
- AH-349 sous AH-119 : deux SPAN Metal sans retour RGB hôte intermédiaire, frontière RGB8 conservée.
- AH-350 sous AH-120 : import VideoToolboxNV12SDR709 et ownership Metal ; préparation/rendu restent des tranches séparées.
- AH-351 sous AH-131 : SPAN→SPAN Vulkan résident, conversions et multiplications de frontière conservées ; RIFE→SPAN distinct.
- AH-352 sous AH-297 : conclusion sur les compromis Area/Spline36 restant d’AH-321, réutiliser les preuves et ne tester qu’un doute réel.
- AH-353 sous AH-224 : reliquat macOS du plan canonique AH-339, contrôles CPU/routage proportionnés.

AH-324 (archive TrueHDR originale) reste distinct. AH-333 (HDR avant interpolation) est toujours demandé **pour plus tard** : aucun déplacement sans contrat couleur.

## Repères historiques utiles seulement si nécessaires

Audit global AH-334 clos :333 tickets examinés,171 descriptions révisées, documents condensés ; nettoyage AH-340 livré .83. Voir [audit Jira AH-334](https://tatoub.atlassian.net/browse/AH-334). Les rapports historiques locaux `docs/AUDIT-GLOBAL-2026-10-17.md`, `docs/audit-20261017/repositories.md` et `docs/ARCHIVES.md` restent disponibles dans le workspace initial ; ils ne sont pas nécessaires à ces guides autonomes.

Lot55/.82 AH-331/332 Done : Fast×4→SPAN58,8–60,5→18,3–18,4ms sur LinuxRTX4070Ti sansHDR ; Qualityexact. Hybride Quality×2→Fast×2 et chaîneHDR : pas de gain global établi. Fast×2 conserve sa voie séparée. Ces chiffres ne mesurent ni .84 ni les nouveaux candidats.

Après chaque lot, remplacer les faits périmés ici ; garder les détails dans le ticket et ses reçus. Ne pas empiler plusieurs états courants contradictoires.
