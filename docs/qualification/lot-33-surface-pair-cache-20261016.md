# Lot 33 — Réutiliser la préparation exacte des paires Surface CUDA

[AH-284](https://tatoub.atlassian.net/browse/AH-284), exploration issue de AH-279/AH-281, sous AH-33. Base3.8.0.64/backend3fcb6e4. Le cache exact ABI9 existait, mais les resets de chaque job Surface neutralisaient sa préparation RIFE et les endpoints Fast. Ce lot raccorde cette réutilisation à la nouvelle interface ; le lecteur mpv conserve encore son chemin ABI9 actuel.

## Implémentation et invariants

Une seule paire est conservée dans les buffers GPU déjà possédés par le contexte. Deux clés numériques fixes couvrent les IDs/générations non nuls, contexte/device/UUID, ressource, format, plans, extents/offsets/strides, géométrie/crop/orientation et huit champs couleur. Une politique de sortie distincte couvre format/couleur/orientation ; les adresses et PTS des destinations ne limitent pas la réutilisation de sources. Pas de comparaison de padding de struct ni de pointeur seul comme identité.

Seules les phases intérieures d'une paire RIFE avec même génération non nulle sont éligibles. Même clé : réutilisation des préparations/décision de scène et des endpoints Fast existants. Paire, vue ou politique différente, ID/génération zéro, appels legacy, configure/reset/drain/disable et erreur invalident la confiance. Les appels internes à ABI9 sont distingués par un état de dispatch, pour ne pas invalider la préparation qu'ils utilisent. L'erreur d'événement invalide après drainage du contexte, avant libération des références.

Aucun owner/descripteur client n'est conservé après complétion. Les buffers préparés sont possédés par le contexte ; les anciennes adresses ne restent que comme valeurs numériques de clés/vues, sans lecture de ressources libérées. Les IDs non nuls promettent des pixels immuables pour la vue/génération ; les pointeurs recyclés requièrent un nouvel ID/génération ou le repli sans confiance. Source et résultat gardent l'ownership qualifié au lot32.

Capacité facultative `EXACT_SOURCE_CACHE`, annoncée seulement sur une configuration RIFE CUDA admissible. `AJI_SURFACE_PAIR_CACHE=0` garde l'ablation sans réutilisation. Un symbole facultatif `aji_surface_cache_stats_v1`, aussi transmis par le dispatcher, expose les compteurs Surface et réels RIFE/Fast. Lecture uniquement contexte inactif, queue asynchrone désactivée ; Busy sinon, sorties courtes/versions non supportées intactes. Modèles, plans TensorRT, précision, conversions et prédictions Quality/Fast conservés.

## Ablation courte, mêmes entrées/options/plans/machine

RTX4070Ti/SM8.9, CUDA13.4, TensorRT11.3.0.99 ; RIFE4.26 et SPANF3 Performance, entrée NV12 128×72, sortie256×144. Un warmup nécessaire par processus initialise formes, allocations et graphes ; une seule rafale mesurée de trois phases0.25/0.5/0.75, dans des processus cache off/on séparés. Le worker reste vivant entre warmup et mesure. Aucun nouveau plan TensorRT, `trtexec=/bin/false`.

| Mesure de la rafale | Cache off | Cache on | Conclusion |
|---|---:|---:|---|
| Préparations réelles RIFE, hors warmup | 3 | 1 | Deux préparations/décisions scalaires évitées |
| Upscales des sources Fast, hors warmup | 6 | 2 | Quatre calculs d'endpoints évités |
| Intervalle GPU Fast | 19.761ms | 6.873ms | Gain net établi sur ce cas |
| Temps mural Fast | 20.486ms | 7.362ms | Même conclusion sur la rafale |
| Intervalle GPU Quality | 22.943ms | 22.754ms | **Non concluant pour les FPS**, variation inférieure à1% |

Les six sorties mesurées Quality/Fast sont exactes, zéro octet différent ; ROI/padding et descripteurs intacts, owners acquis une fois par rôle/job puis équilibrés. Trois prédictions Quality complètes restent calculées ; le compromis Fast existant est conservé.

L'ambiguïté Quality a justifié **un complément court portant sur une autre mesure**, sans prolonger le test FPS ni répéter Fast : moment où la dernière fence de la rafale est enregistrée/exportable. Cache off15.431ms, cache on0.915ms. Le GPU Quality termine toujours vers23ms : cette avance concerne la soumission sur le worker et le chaînage du consommateur GPU, **pas des pixels déjà terminés**. Les deux attentes scalaires intermédiaires supprimées expliquent l'avance. Les mêmes trois prédictions sont préservées, les résultats CPU n'étant disponibles qu'après leur vraie complétion.

Les intervalles CUDA incluent les trous d'enqueue CPU ; ils ne sont pas une somme de temps de kernels ni une promesse FPS générale. Aucun autre essai de performance lancé après cette conclusion suffisante.

## Gardes ciblées

[Client C ABI réel](../../tests/inference/surface_pair_cache_check.py). Références cache off nouvelles seulement pour les jeux de pixels modifiés ; sortie centrale de la rafale déjà acquise réutilisée pour amorcer le cache du candidat. Les compteurs de préparation proviennent des champs réels du backend, indépendamment du compteur d'éligibilité.

Quality : mêmes allocations/IDs recyclés avec nouveaux pixels et génération, transfert/primaires modifiés, ROI déplacée à pointeurs de base/strides identiques ; chacun force une préparation nouvelle et produit la bonne référence. Les métadonnées couleur transportées ne changent pas ici la conversion ABI9 de référence ; cela ne démontre aucune conversion de gamut/HDR.

Mixing legacy : mêmes allocations/IDs/génération/vues réécrits, sans hint d'identité ABI9. L'appel direct RIFE→SPAN et le retour à Surface donnent tous deux les nouveaux pixels de la référence cache off, sans préparation/endpoints périmés. Ce contrôle et celui de génération sont exécutés aussi en Fast, où les endpoints constituent un dérivé supplémentaire.

Drain vide après une paire synchrone, puis job de même identité : préparation nouvelle. Disable après complétion sans drainage public préalable, puis même paire : nouvelle préparation. IDs zéro sur deux appels successifs et génération zéro avec IDs non nuls : repli sans confiance, sorties exactes. Une erreur de consultation d'événement injectée après vraie fin GPU est signalée Failed ; après désactivation et réécriture des mêmes ressources/IDs, la récupération donne les bons nouveaux pixels. Sortie d'erreur écartée ; aucune perte matérielle/reset GPU provoqué.

Callbacks équilibrés, descripteurs/sentinelles conservés ; versions/tailles des statistiques refusées sans écriture. Les suites de contrat/vidéo déjà concluantes des lots précédents ne sont pas rejouées.

## Décision, preuves et limites

**Conserver activé sur la route Surface RIFE CUDA négociée** : bénéfice Fast établi et avance de soumission Quality mesurée, sans perte de qualité observée. Aucun gain FPS Quality revendiqué. Paires adjacentes, formats/modèles/couleurs et matériels non exécutés ne sont pas présentés comme qualifiés ; les autres API/OS restent ouverts. Le cache n'ajoute aucun buffer modèle/GPU et garde une paire de clés bornée.

Build Release multi-SM75/80/86/89/90/100/120+PTX120 réussi ; en-tête C public/backend identique, struct de statistiques72octets vérifiée. Exports précédents conservés, une extension facultative ajoutée au backend et au dispatcher. Artefacts `artifacts/performance/lots-20261016/lot-33/` : specs, sortiesNPZ, `ablation-summary.json`, `qualification.json`, sous-dossiers `quality-*`/`fast-*`, journaux de build. Les receipts concluants empêchent une répétition involontaire.

Commande : `python3 tests/inference/surface_pair_cache_check.py SPEC.json`, avec bibliothèques CUDA/TensorRT du paquet dans LD_LIBRARY_PATH. `cache=0|1` sélectionne l'ablation ; `phase=guards-ref|guards-on` les gardes. La sonde test-only du lot32 est chargée par LD_PRELOAD pour l'erreur native.

Sources : backend `7e9c87137e77046e5c521e635634bfdef751a277`, qualification publique `afe9136bf25173bd8db4899bbc66a4e703a14ba8`. Release prévue **3.8.0.65**, binaires Linux nouveaux ; Windows et Manager conservés. AH-284 reste In Progress jusqu'à publication vérifiée ; parent AH-33 et qualifications restantes ouverts.

Bundle Linux livré : `3d434bd856afed2f63f51e117c96d4b259cd8083` ; sections .text/fatbin inchangées après RPATH.
