# AH-329 — coût du chemin Quality ×4 fusionné, revue source ciblée

## Conclusion

Le code livré .84 conserve le vrai RIFE Quality complet, son cache exact de paire, sa préparation fusionnée et son graph CUDA de prédiction RGB. Pour le profil 3 observé, le plan attendu est bien **Area 1920×1080 → 1280×720**, **bloc fusionné RIFE426 Quality ×4 → SPAN Performance 2× → 2560×1440**, puis **TrueHDR à 1440p**. Aucun argument source ne permet d'accuser un retour automatique à un ancien moteur ou une interpolation à 1440p dans ce profil.

Il existe néanmoins un écart concret avec le traitement historique par lot : l'API surface appelée par la pipeline impose une attente hôte à chaque sortie fusionnée. Un second coût évitable est la succession de deux copies du même intermédiaire YUV entre RIFE et le graph d'upscale. Ces constats sont établis dans le code ; **leur contribution à la baisse de FPS n'est pas mesurée**. Ils ne démontrent pas à eux seuls la cause dominante.

Aucun code, profil, ticket, backend lot 58/59 ou processus utilisateur modifié. Aucun essai GPU lancé.

## Sources et portée

- Backend inspecté : `/tmp/animejanai-backend-remove-fruc-20261017`, base `36f3d94491b51d334dc9420ce6d5192b086b0a8f`, source livrée lot 57/.84. Les numéros de lignes ci-dessous désignent cette version, pas le cumul lot 58.
- Filtre historique inspecté : `/tmp/animejanai-mpv-fruc-removal-20261017/video/filter/vf_animejanai.c`, base mpv `19c0fcf89595e6ab33908299207c555b67e81558` avec patches lecteur déjà présents dans ce checkout. Ce fichier sert à comparer le code du burst, pas à prétendre qu'une ancienne vidéo ou un ancien profil a été rejoué.
- Snapshot root : `artifacts/performance/lots-20261017/quality-live-20261017/live-snapshot.json`, 05:28:37 UTC, PID 66579 pausé, profil 3, entrée NV12 1080p/23.976 FPS, sortie YUV444P16/PQ 1440p, bibliothèques réellement mappées .84 (TRT `c6f2fce4…`, pipeline `f3157d05…`). Le log de stats historique indiqué par le filtre ne démontre pas les réglages de cette instance.
- Configuration utilisateur lue seulement : `/home/ta2b/.local/share/AnimeJaNai-HDR-linux/animejanai/animejanai.conf:98–162`. Les clés orphelines `chain__*` ne constituent pas les étapes de `chain_1`.
- Le PID n'existait plus dans `/proc` de cet agent lors de la tentative de lecture des seuls flags `AJI_*` pertinents. Les variables d'environnement de cette instance ne sont donc pas confirmées ici. La fusion est prouvée **éligible par le code**, mais son activation effective doit être corroborée par la ligne de bloc ou les compteurs du processus testé ; `AJI_PIPELINE_FUSION=0` pourrait la désactiver.

## Ce qui reste correct

1. `pipeline_config.cpp:179–208` groupe les étapes interpolate/upscale et autorise Quality ×4 suivi d'un upscaler TensorRT. L'exception Fast ×2 ne s'applique pas. `aji_pipeline.cpp:196–214` ne casse le bloc que pour un pré-resize spatial non identique ; cette option n'est pas présente sur le SPAN de ce profil.
2. Area fixe les dimensions avant la création du contexte TRT (`aji_pipeline.cpp:222–236,259–265`). Le SPAN est spatial (`frames=0`), donc `aji_trt.cpp:1796–1810` conserve RIFE-before-upscale. RIFE calcule à 1280×720, avec padding 1280×768 (`aji_trt.cpp:1290–1306`), pas à 2560×1440.
3. La configuration générée transmet `rife_engine=quality` (`pipeline_config.cpp:149–163`). Le parseur désactive `rife_warp` pour quality (`aji_conf.cpp:354–356`), donc le résultat RIFE complet passe par `enqueue_rife_picture` (`aji_trt.cpp:4078`), pas par une reconstruction flow-only.
4. Les phases .25/.50/.75 utilisent le même couple stable. L'adaptateur surface préserve les identités et promeut l'ancienne droite (`surface_cuda_impl.h:186–205`), appelle `aji_rife_begin_pair` (`:211`), puis `aji_trt.cpp:3936–3950` réutilise la préparation/SCD. La préparation fusionnée YUV→RGB est active par défaut (`:3701–3754`). Le graph RGB complet rejoue sans attente par image (`:3822–3825`) ; l'attente `:3842` n'est que le warmup de capture. Un reset de paire n'efface pas ce graph (`:3005–3019`).
5. L'endpoint B est calculé et gardé pour devenir A au job suivant (`aji_pipeline.cpp:316–336`). Le premier lot peut faire cinq upscales, puis quatre par paire en régime établi. Ce B anticipé n'est pas un cinquième upscale inutile à chaque paire. Le cache de resize et de HDR fonctionne sur le même principe.

## Priorité 1 — retrouver une soumission par lot sans attente après chaque sortie

**Coût actuel prouvé.** `aji_pipeline.cpp:319,330,334` appelle `trt.process` pour chaque sortie. Cette fonction résout `aji_surface_process_v1`, dont `surface_cuda_impl.h:261` passe `wait=true`, puis `:247` fait `cudaStreamSynchronize(stream)`. À ×4 en régime établi, trois synthèses RIFE+SPAN et l'endpoint droit SPAN font **quatre attentes hôte**, hors attente de score SCD et hors les autres étages. Au tout premier lot, l'endpoint gauche n'est pas encore en cache : cinq appels.

**Écart historique.** Le filtre `vf_animejanai.c:1900–1926` active `cuda_burst` pour RIFE-first CUDA et attend le dernier ticket seulement. `interp_source:1977` et `upscale_image:1998–2003` retournent sans attente intermédiaire en gardant les owners ; la boucle `:2538–2566` soumet les phases puis draine le burst. Le nouvel adaptateur a donc réintroduit une synchronisation par sortie même si le réseau et les caches sont les mêmes.

**Approche retenue à étudier en premier.** Un chemin interne de bloc surface avec soumission ordonnée et un événement/une attente de fin de bloc. Conserver le caractère synchrone de l'API publique actuelle. Le backend a déjà un chemin `cuda_surface_process(...,false)` utilisé par sa file asynchrone (`surface_cuda_async.h:100–110`) : réutiliser son contrat ou ajouter une API bornée de lot ; ne pas appeler naïvement une méthode interne non exportée. La pipeline possède déjà un worker unique, donc éviter de créer une file et un thread par image.

**Invariants indispensables.** Sources, sorties et temporaires retenus jusqu'à l'événement de fin ; ordre sur le même stream TRT ; entrée/sortie vers le stream de la pipeline ordonnée par événement ; erreurs drainées avant réemploi ; reset/seek/reconfiguration attendent le lot. Ne pas retirer l'attente publique existante sans contrat de complétion : les copies et HDR utilisent un autre stream. Ne pas dépasser la capacité d'une file par défaut si la solution réemploie l'API asynchrone.

**Bénéfice statique attendu.** Quatre attentes de fin d'image peuvent devenir une barrière de fin de bloc pour ×4, avec les mêmes trois inférences RIFE et quatre SPAN. Le temps GPU réseau ne diminue pas automatiquement ; le gain est l'absence de trous de soumission/retours CPU entre phases. La taille de ces trous doit être observée avant toute promesse de FPS.

AH-346 retire déjà les attentes répétées des copies finales de la pipeline. Ce sont **d'autres** attentes (`aji_pipeline.cpp:311`) ; sa livraison ne règle pas celles de `surface_cuda_impl.h:247`.

## Priorité 2 — supprimer une copie YUV intermédiaire, conserver la quantification

**Chaîne réelle Quality fusionnée.** `surface_cuda_impl.h:241–245` alloue un `middle`, y appelle RIFE, puis le passe à `aji_infer`. RIFE fait RGB fp16 → YUV dans `R.pad_o` (`aji_trt.cpp:3782–3806`) puis crop/copie des trois plans vers `middle` (`:4081–4086`). Le graph spatial recopie immédiatement les trois plans de `middle` vers ses adresses stables `stage_in` (`:2475–2500`) avant le pré-traitement et SPAN. Il y a donc deux copies device-to-device successives de la même image 720p, sans calcul entre les deux.

**Approche minimale.** Dans un chemin interne explicitement Quality-before-upscale, utiliser directement une vue crop du tampon YUV RIFE pour remplir le staging spatial, ou cibler ce staging depuis la copie de crop, avec vérification d'identité/adresses et sérialisation. Garder la voie publique/générique existante en fallback. Réduire deux copies à une est plus simple et plus sûr que réécrire le réseau ou l'ensemble des graphs. Une copie de trois plans 1280×720×16 bits représente 5 529 600 octets ; pour trois synthèses, une couche retirée évite 16 588 800 octets de charge utile copiée par paire (ce chiffre n'est pas un débit ou une mesure de bus).

**Fidélité.** Ne pas brancher directement `R.out_tensor` RGB fp16 sur SPAN comme si c'était une optimisation équivalente. Le parcours actuel applique la conversion RGB→YUV, sa quantification, puis YUV→RGB ; les supprimer change les valeurs et constitue un nouveau contrat Quality à qualifier. Conserver aussi padding/crop, plage et matrice. Les deux copies existent également dans le legacy qui utilise ces mêmes fonctions : leur suppression optimise Quality, mais leur existence seule ne démontre pas la régression récente.

## Éléments à mesurer sans fausse comparaison

- `AJI_PIPELINE_TRACE=1` fournit déjà la durée CPU/GPU synchronisée par bloc et `fused`, `preparations`, `promoted` (`aji_pipeline.cpp:402–410`). À partir des deltas, une paire Quality ×4 normale attend une préparation RIFE, deux hits sur les phases suivantes, puis une promotion au couple suivant. Les compteurs publics complets existent dans `surface_cuda_impl.h:267–275` ; le trace actuel n'affiche pas tous les hits/uncached.
- La capture/graphe de prédiction n'a pas de compteur public dans cette API ; des logs de capture ou une exposition ponctuelle des compteurs internes `picture_replays` aideraient à distinguer graph désactivé/échec de capture d'un défaut de fusion.
- Isoler le temps Area, bloc RIFE+SPAN et HDR avant de conclure que RIFE est le seul responsable. TrueHDR est réellement appliqué sur les quatre nouvelles sorties 1440p en régime établi. Le code .84 impose pack/attente, appel SDK, attente contexte, unpack/attente (`aji_pipeline.cpp:350–360`). L'adaptateur force actuellement le stream par défaut du SDK (`pipeline_hdr.c:69–71`) ; enlever ces barrières sans changer/établir le contrat de stream est dangereux. Cette observation ne requiert pas de refaire le chantier HDR déjà attribué.
- La pipeline normalise les surfaces en YUV444P16 (`aji_pipeline.cpp:163–165`) et réalise Area sur cette représentation ; un ancien profil NV12/Spline36 n'a pas exactement les mêmes conversions ni qualité. Comparer des pixels/temps entre ces profils sans alignement du downscale et des formats ne mesure pas uniquement la fusion.
- Ne pas comparer au vieil affichage « quality » si celui-ci activait en réalité une stratégie Fast. Garder le modèle 426, le vrai Quality, les trois instants, le downscale et l'upscaler identiques.

La courte observabilité préparée par root suffit comme prochaine étape. Aucun élargissement de batterie de tests, aucune réécriture de RIFE et aucune désactivation d'option utilisateur ne sont nécessaires pour terminer ce diagnostic source.
