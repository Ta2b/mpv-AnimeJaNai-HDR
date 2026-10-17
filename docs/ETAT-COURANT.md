# État courant — point d’entrée IA

Mis à jour le **17 octobre 2026**. Lire ce fichier et `../AGENTS.md`, puis uniquement le ticket et les contrats nécessaires. Les demandes actuelles de l’utilisateur et Jira réel priment sur les archives. Ne pas réimporter le backlog AH.

## Mission actuelle : reprise continue des tickets et débit Quality

**Reprise demandée par l’utilisateur après la pause.** Finir les tickets engagés et livrer les lots complets ; poursuivre les tâches indépendantes pendant les compilations. Dernière release vérifiée3.8.0.84.

**Release3.8.0.85 préparée, livraison à vérifier après les CI.** BundleGPU `0f43e8e7a3cf6781ff649969c0f9608bc3cb3dfe` : TRT Linux/Windows source `8ff36e8`, pipeline `8c67670` avec rafale expérimentale désactivée par défaut ; dispatcher Linux/AMD Windows inchangés et provenance conservée. AH345/346/347/355 qualifiés selon leur portée (code/build et essai court Quality exact), pas encore Done. AH338 : inventaire partagé des programmes, AppRun/updater/launcher macOS,19cas ciblés+32AppRun+9shellmac simulés, sources `c226388`. Aucun benchmark vidéo pour ce changement d'installation.

AH354 :13images/PTS/couleur exactes off/on, reset exact. Débit non concluant (fréquencesGPU1200/2385/2730MHz selon les passages), arrêt des essais. Reste ouvert ; `AJI_PIPELINE_QUALITY_BURST=1` pour étude seulement. [Reçu du lot Quality](qualification/lot59-quality-20261017/README.md), [qualification installation](qualification/lot60-managed-files-20261017/README.md).

AH344 : backendDML compile/link Windows39007945723 réussi ; lecteur apparié source `3ff8782d70f70dc0292c4365e0bf59535192b9bf`, run39006425781 en cours (compilation statique). **Aucun pin lecteur ni cacheDML actif annoncé dans .85.** Poursuivre une tâche indépendante, vérifier ce producteur en fin de tâche ; terminer son intégration/livraison dans le lot suivant.

Le manque de débit Quality4 reste ouvert : fusionactive, RIFE1280×720 et modules.84réellement chargés, pas un retour à une ancienne bibliothèque dans l'instance contrôlée. La chaîne native complète exige encore plus que le budget41,7ms dans la référence mesurée ; ne pas annoncer96FPS. Cas privés/références dans `artifacts/performance/lots-20261017/quality-live-20261017/`, profils installés non modifiés.

Les28guidesJira du relais restent disponibles dans [l’index](reprise/20261017/README.md), complétés parAH354/355. Reprendre seulement ticket/contrats utiles, ne pas réimporter ni refaire les travaux déjà livrés.

- Préserver profils, médias, SDK, modèles, modifications utilisateur et backend d’origine. Sources isolées, chemins explicites dans git add ; jamais git add -A, reset/clean global ou push vers un origin local du backend utilisateur.
- In Progress au début du travail effectif ; Done après périmètre entier et livraison vérifiée. Les parents partiels restent ouverts ; les reliquats ont leurs propres tickets.
- Précision utilisateur du17octobre : pas de benchmark systématique. Revue/compilation si l’effet est suffisamment établi ; essai court seulement pour une incertitude réelle ou une mesure revendiquée. Ne pas répéter un résultat concluant. Pour UI/docs/packaging, contrôles simples. Distinguer bénéfice statique, gain attendu et gain mesuré.
- Quality conserve les prédictions complètes et les frontières numériques de référence. Toute approximation reste Fast explicite. Ne pas forcer la convergence des backends quand leurs besoins diffèrent. Matériel absent : qualification partielle, jamais inventée.
- Lancer builds/releases puis avancer une tâche indépendante ; consulter leur résultat en fin de tâche. Pas d’attente active ni gh run watch. Strata facultatif, aucun concurrent GPU pendant une mesure.

## Dernière livraison vérifiée : 3.8.0.84

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

## Prochain lot : code préparé, pas livré

| Ticket | État exact et prochaine action |
|---|---|
| [AH-344](reprise/20261017/AH-344.md) | In Progress. DLL DML compilée ; producteur mpvWindows39006425781 en cours. Finaliser son pin et sa livraison appariée après succès ; cache non activé par .85 seule. |
| [AH-345](reprise/20261017/AH-345.md) | In Progress. Score Fast>3 inutile retiré, dépendance CUDA conservée, builds portables Linux/Windows intégrés au pin .85 ; vérifier livraison avant Done. Aucun nouveau FPS mesuré. |
| [AH-346](reprise/20261017/AH-346.md) | In Progress. Même3F copies finales, F attentes→1 ; compilation et chaîne complète13sorties exactes, TrueHDR conservé. Vérifier livraison .85 avant Done. |
| [AH-330](reprise/20261017/AH-330.md) | In Progress. Garantir Quality avec les bibliothèques réellement chargées, préserver overrides/fichiers utilisateur. Inventaire sur disque ≠ module déjà chargé. |
| [AH-347](reprise/20261017/AH-347.md) | In Progress. Pads a/b paresseux intégrés avec345/355, pad_o conservé ;11,25Mio évités à720p, pixels Quality exacts. Vérifier livraison .85 avant Done. |
| [AH-208](reprise/20261017/AH-208.md), [AH-329](reprise/20261017/AH-329.md) | In Progress. Parents fusion/Quality ; gardes, diagnostic, références effectives et optimisations exactes. Ne pas refaire les mesures lot55 concluantes. |

Patches et preuves portables : `docs/reprise/20261017/{patches,preuves}` avec manifest SHA. Les candidats temporaires peuvent disparaître ; les patches sont sauvegardés/versionnés. Binaires candidats Linux hors Git dans `/home/ta2b/.animejanai-tools/work/lot-58-engine-handoff-20261017/` avec SHA256.json. **Aucun candidat AH-344/345/346 n’est inclus dans .84.**

## Autres premières tranches explicites

Tous To Do, aucun code nouveau ni qualification matérielle prétendue :

- AH-348 sous AH-121 : diagnostic CoreML hors attente critique ; parent conserve la comparaison réelle GPU/ANE/CPU.
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
