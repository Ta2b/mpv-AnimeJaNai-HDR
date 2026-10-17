# Lot 32 — Submit/Complete CUDA et fences natives

[AH-281](https://tatoub.atlassian.net/browse/AH-281), parent AH-50. Périmètre Linux x86-64 CUDA/TensorRT ; les autres API/OS restent [AH-283](https://tatoub.atlassian.net/browse/AH-283). Base joueur3.8.0.63 et backend `df7e02e7bd3f4d274986946d2e5a04e905d7a454`. AH-279 a été terminé et sa publication vérifiée pendant ce lot, commencé immédiatement après son push.

## Comportement livré

Les six opérations Submit/Complete CPU du lot30 sont maintenant implémentées aussi sur les surfaces CUDA natives du lot31, avec un septième symbole facultatif `aji_surface_output_fence_v1`. Le dispatcher les négocie et transmet son contexte interne. Les anciennes interfaces et Surface synchrone restent disponibles ; sans Enable, aucun worker ni événement de cette file n'est créé et les chemins historiques restent actifs.

Enable réserve 1..64 emplacements et événements CUDA, puis un worker persistant prend exclusivement le contexte. Submit valide la requête et les vues natives, copie les descripteurs et jusqu'à trois dépendances, retient les owners une fois et réserve un ticket monotone. Il n'attend ni le calcul ni une place libre. Saturation : Busy, ticket zéro, aucune acquisition ; résultats terminés non consommés toujours comptés dans la borne. Les appels historiques mutables sont refusés pendant cette ownership ; les erreurs se lisent par ticket plutôt que dans un buffer d'erreur partagé avec le worker.

Les événements d'entrée CUDA doivent déjà avoir été enregistrés ; le producteur peut encore finir le travail placé avant ces événements. Le worker place `cudaStreamWaitEvent` sur son stream, puis exécute la chaîne de référence sans la synchronisation finale du mode Surface synchrone. Les attentes scalaires préexistantes du backend, notamment la décision RIFE, restent sur le worker ; elles ne sont pas présentées comme supprimées. Aucun nouvel intermédiaire CPU ni attente GPU par image sur le thread Submit. Les queues externes, fences d'autres API et champs non supportés sont refusés explicitement.

Après enregistrement de l'événement de sortie, le client peut emprunter sa fence et chaîner un consommateur GPU sans attendre le résultat CPU terminal. Cette disponibilité ne garantit pas encore les pixels ni un succès final : le consommateur doit placer son attente GPU avant de consommer/retirer le ticket et conserver ses propres références aux buffers. La fence n'est plus valable après Consume, DropResults ou Disable ; un événement d'entrée non enregistré ne constitue pas une dépendance valide. Ces obligations sont écrites dans l'en-tête public.

Le worker consulte les événements natifs ; le résultat ne devient Finished qu'après la fin GPU **et** la libération des owners. Complete est une consultation sans attente et ne consomme jamais un ticket Pending. Le worker attend sans réveil périodique lorsque la file est vide ; pendant une fin GPU en attente, il consulte avec une attente de condition de1ms entre passages. La fence permet au consommateur GPU d'éviter cette latence de publication CPU.

Une erreur de calcul/événement draine le contexte CUDA avant libération, publie Failed/message et verrouille la file contre de nouvelles requêtes ; elle n'est jamais assimilée à une fence réussie. Drain annule seulement les travaux non démarrés, laisse finir les autres et peut retirer les anciens résultats pour un seek. Disable et destruction drainent/annulent avant de libérer événements/modèles. Les tickets ne sont pas recyclés dans le même contexte, y compris après Disable/Enable. L'invalidation interne a été séparée de l'entrée ABI historique afin que les gardes d'ownership ne bloquent pas le reset du drainage.

## Qualification courte

Machine RTX4070Ti/SM8.9, CUDA13.4 et TensorRT11.3.0.99 ; mêmes modèles/plans/configurations que le lot31. Client C ABI réel [surface_cuda_async_check.cpp](../../tests/inference/surface_cuda_async_check.cpp), compilé avec les en-têtes ABI9 et CUDA du SDK, sans NDEBUG. Configuration RIFE seule chargée depuis le cache, mais les contrôles de contrat utilisent uniquement ses endpoints de copie CUDA : **aucune inférence neuronale** pour cette partie.

Un événement producteur enregistré derrière un callback contrôlé retarde des écritures CUDA connues. Submit rend la main alors que cette dépendance est encore Pending ; la fence de sortie est déjà exportable mais reste NotReady. Un consommateur sur un autre stream attend cette fence et copie exactement les nouveaux pixels. Aucun seuil temporel arbitraire n'est utilisé pour conclure : le producteur n'est libéré que par le client après ces assertions.

Un second contrôle retarde le callback release de sortie : Complete reste Pending avec les références encore détenues, alors que le consommateur GPU peut déjà obtenir sa sortie correcte par la fence. Saturation/ticket zéro sans acquisition, résultats non consommés bornés, consommation/drop, tickets monotones, emprunt explicite, refus d'accès legacy, annulation et destruction sûres vérifiés. Les destinations des travaux annulés restent intactes et tous les owners sont équilibrés.

Le premier contrôle de snapshot pouvait avoir laissé le worker lire la requête avant sa mutation. Un contrôle supplémentaire **ciblé**, `--snapshot`, bloque donc le worker avant qu'une nouvelle requête puisse démarrer. Muter ensuite le descripteur original, le timestep et le type de dépendance conserve la bonne sortie CUDA : copies effectivement consommées depuis la file, owners acquis une fois. Aucun autre essai concluant n'est rejoué pour ce contrôle.

Une erreur d'événement est injectée par la sonde test-only [cuda_surface_api_probe.c](../../tests/inference/cuda_surface_api_probe.c), après que la vraie consultation CUDA a constaté la fin du travail. Failed/message, références libérées et refus de nouvelles requêtes sans acquisition vérifiés. Cela qualifie la remontée/drainage d'erreur native ; **aucune perte matérielle réelle ni reset GPU n'a été provoqué**. Les pannes de pilote/matériel restent une limite explicite, sans validation universelle inventée.

Un échec initial du harness venait de la valeur numérique historique de NotReady ; CUDA13.4 utilise une autre valeur. Le client a été corrigé pour utiliser `cudaErrorNotReady` depuis le SDK, puis le contrôle interrompu a passé. Aucune correction du moteur n'a été nécessaire pour cet échec. Le premier build avait aussi un nom de type non qualifié dans un catch ; corrigé avant les essais runtime.

| Calcul réel sur le worker | Référence acquise réutilisée | Résultat |
|---|---|---|
| RIFE4.26 Quality avant upscale + SPAN, NV12, entrée128×72 | Lot31 `quality-before/pixels.npz` | Une sortie exacte, zéro octet différent |
| RIFE Fast avant upscale + SPAN, mêmes géométries/modèles/options | Lot31 `fast-before/pixels.npz` | Une sortie exacte, zéro octet différent |

ROI/padding et descripteurs intacts, acquisitions/libérations une fois par rôle. Les références sont lues depuis les fichiers ; aucun calcul avant ni suite synchrone concluante répété. Les formats P010/444 et autres routes synchrones conservent leurs preuves lot31 ; leurs combinaisons asynchrones n'ont pas été toutes exécutées.

Submit observé à0.01296ms /0.01266ms ; Submit+drain de premier passage17.97ms /20.37ms. Ces durées incluent initialisations/allocations et ne constituent pas un gain FPS avant/après. Le bénéfice établi est fonctionnel : l'appelant progresse pendant une dépendance GPU bloquée et le consommateur GPU se chaîne sans attendre la libération CPU. Les plans et sorties Quality restent inchangés.

Build Release multi-SM75/80/86/89/90/100/120+PTX120 réussi, en-tête C valide et public/backend identique. Tous les exports précédents conservés, sept facultatifs ajoutés au backend et au dispatcher. Artefacts `artifacts/performance/lots-20261016/lot-32/` : `contract.log`, `snapshot.log`, `quality-before/summary.json`, `fast-before/summary.json`, sortiesNPZ, specs, `qualification.json` et logs de build.

Commandes : compiler le client avec `c++ -std=c++17 -O2 -pthread tests/inference/surface_cuda_async_check.cpp -I native/common -I AJI_HEADERS -I CUDA_INCLUDE -ldl` ; exécuter `CLIENT MODULE CONF_RIFE_SEUL MODELS RIFE` avec la sonde CUDA test-only en LD_PRELOAD, ou ajouter `--snapshot` pour le contrôle isolé sans injection. Comparaison neuronale : `python3 tests/inference/surface_cuda_check.py SPEC.json` avec `async_mode=true` et `reference_output` déjà acquis ; `trtexec=/bin/false` interdit un build inattendu.

## Décision et livraison

Conserver ce raccord asynchrone et son contrat borné/interopérable. Aucun gain FPS ni fidélité HDR/tout matériel revendiqué. Release prévue **3.8.0.64**, binaires Linux nouveaux, répertoire Windows et Manager précédemment livrés conservés. AH-281 reste In Progress jusqu'à publication vérifiée ; parents AH-49/AH-50 et AH-282/AH-283 ouverts. Le lecteur mpv n'adopte pas encore cette nouvelle interface, son intégration reste dans le chantier producteur/consommateur.

Sources : backend `3fcb6e4de075907388e44d6e46096290082770ec`, qualification publique `60e480bfdf07f2e2c022e079be3ea8c716dd4c0a`.

Bundle Linux : `cabec957531fa0c812f40c2e420e11f9d6e9c07c`. Les sections .text et fatbin sont identiques après adaptation du RPATH ; le répertoire Windows reste inchangé depuis d00ed919/backend652fbc6.
