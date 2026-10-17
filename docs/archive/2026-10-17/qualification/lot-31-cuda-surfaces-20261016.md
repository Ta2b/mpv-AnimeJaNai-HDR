# Lot 31 — Surfaces CUDA natives typées

[AH-279](https://tatoub.atlassian.net/browse/AH-279), parent AH-49. Périmètre complet Linux x86-64 CUDA/TensorRT sur la machine disponible ; les autres API/OS et configurations spécialisées restent [AH-282](https://tatoub.atlassian.net/browse/AH-282). Submit/Complete et fences GPU restent AH-281. La release 3.8.0.62 / AH-280 a été terminée et vérifiée pendant ce lot, démarré immédiatement après son push.

## Route livrée et limites

Le module TensorRT implémente les deux symboles optionnels Surface v1 ; le dispatcher `libaji.so` les résout facultativement et transmet son contexte interne, jamais le wrapper public. Un ancien backend sans extension reste chargeable et renvoie Unsupported sans modifier la négociation. L'ABI9 reste disponible et les chemins par défaut ne changent pas.

Allocations CUDA natives NV12, P010 MSB et YUV444P16, planes/strides positifs, offsets et crop actif : aucune copie par le CPU ni réduction en RGB24. Les matrices 601/709/2020NC, plage et siting explicites vont aux conversions de référence ; primaires, transfert SDR, orientation, timing, IDs et génération restent dans les descripteurs immuables. Ils ne sont pas convertis silencieusement. La quantification `REFERENCE_NATIVE_YUV` désigne celle des kernels existants, sans dither ajouté. Les nouvelles valeurs d'enum/flags sont additives, sans changement de taille ABI.

La vue est validée contre la géométrie configurée, les extents déclarés et l'allocation CUDA réelle. Contexte, ordinal, UUID optionnel, type mémoire, alignement haute profondeur, crop chroma et non-recouvrement de sortie sont contrôlés avant acquisition/calcul. Ressources importées opaques, mémoire hôte, stride négatif, HDR PQ/HLG, politiques de dither différentes et configurations temporelles/préresize/RTX sont refusés explicitement. Ce lot ne démontre aucune fidélité HDR ni conversion de gamut.

Chaîne spatiale seule, RIFE avant/après upscale et RIFE seul : mêmes plans, kernels et décisions ABI9. Les intermédiaires sont des buffers YUV CUDA possédés par le contexte et réutilisés, bornés par ses dimensions/formats. Un changement de scène produit la duplication de la source gauche prévue par la référence ; après upscale, une copie CUDA du résultat gauche évite de recalculer le réseau.

Cette interface est synchrone : elle attend la fin réelle du stream avant de libérer les owners/retourner. Toute erreur après acquisition draine le GPU avant libération ; les sorties d'une erreur moteur sont à écarter. Aucun pointeur de descripteur/owner n'est conservé. Les adresses de vues empruntées de paire sont également effacées, après invalidation des caches de sources à l'entrée et à la sortie. Cette première route conserve les IDs dans le contrat mais ne fait pas confiance à une paire entre appels ; elle évite ainsi toute réutilisation dérivée erronée lors d'un changement de vue/couleur/génération ou d'un mélange avec ABI9. L'optimisation de leur réutilisation demeure un travail distinct.

## Qualification ciblée

Client C ABI réel [surface_cuda_check.py](../../tests/inference/surface_cuda_check.py), ctypes avec le layout C déjà qualifié au lot 29. Référence : backend livré `652fbc6bdd3a9d815367deeb2df65538636705dc`, pin binaire d00ed919. Machine RTX 4070 Ti / SM8.9, CUDA13.4 et TensorRT11.3.0.99 ; entrée128×72, SPANF3 Performance et RIFE4.26 existants. Même entrée, couleur, options et plans dans chaque comparaison.

| Cas sélectionné pour le nouveau raccord | Résultat |
|---|---|
| Spatial NV12 / 709 limited ; ROI, offset et stride avec sentinelles | Exact, zéro octet différent |
| Spatial P010 SDR / 2020 full | Exact, zéro octet différent |
| Spatial YUV444P16 / 601, chroma center | Exact, zéro octet différent |
| RIFE Quality avant upscale | Exact, zéro octet différent |
| RIFE Fast avant upscale | Exact, zéro octet différent |
| RIFE Quality après upscale | Exact, zéro octet différent |
| Changement de scène après upscale | Duplication gauche exacte |
| Dispatcher, spatial NV12 | Exact face à la référence acquise, sans rejouer son calcul |
| Dispatcher, RIFE seul | Exact, zéro octet différent |

Acquisitions/libérations équilibrées une fois par descripteur, descripteurs inchangés et aucune écriture hors ROI dans ces essais. Le modèle/RIFE déjà compilés sont réutilisés ; seule la résolution RIFE après upscale256×192 manquante a été construite une fois, puis le **même** plan a servi à la référence et au candidat. Aucune reconstruction indépendante ni comparaison de tactiques différente.

Refus avant acquisition/écriture : mauvais resource/device/contexte/UUID, extent court, stride négatif, crop mal aligné, pointeur non CUDA, HDR, dither ajouté, callbacks non appariés et timing invalide ; NaN et overlap de sortie refusés. Configure échoué désactive la négociation. L'ancien backend chargé par le nouveau dispatcher demeure opérationnel et refuse proprement les symboles optionnels manquants, sans calcul neuronal supplémentaire.

Erreur d'allocation CUDA injectée **après acquisition des trois owners et avant toute inférence** : EngineError/message d'allocation, références équilibrées, descripteurs et destination intacts. La sonde est test-only [cuda_surface_api_probe.c](../../tests/inference/cuda_surface_api_probe.c) ; son premier essai a révélé une résolution RTLD_NEXT inadaptée à libcudart chargé localement par ctypes. Le harness a été corrigé pour résoudre la vraie bibliothèque locale ; aucune correction du moteur nécessaire. Aucun reset/perte réelle de GPU provoqué.

Build Release Ubuntu de référence réussi, kernels multi-SM75/80/86/89/90/100/120 et PTX120. Exports historiques conservés, deux symboles optionnels ajoutés dans le backend et le dispatcher. En-tête public/backend identique. Le dernier effacement d'adresses empruntées ne change aucun calcul ; les sorties concluantes ne sont pas rejouées.

Artefacts locaux `artifacts/performance/lots-20261016/lot-31/` : specs, neuf sorties/références YUV sauvegardées, résumés, `qualification.json`, `dispatch-fallback.json`, `allocation-error/summary.json`, logs de build. Commande : `python3 tests/inference/surface_cuda_check.py SPEC.json` avec les bibliothèques CUDA/TensorRT du paquet dans LD_LIBRARY_PATH ; `trtexec=/bin/false` interdit un build inattendu, sauf la résolution nouvelle explicitement préparée. Les receipts concluants empêchent une répétition involontaire.

## Décision et livraison

Conserver comme contrat natif et raccord consommable : vues haute profondeur CUDA, capacités et lifetime sûrs, sans pont RGB24. Les durées ponctuelles de premier passage sont conservées dans les preuves mais **ne constituent pas un gain FPS** : warmup et allocations diffèrent. Aucune promesse sur tous les formats/couleurs/modèles/matériels ; les cas effectivement exécutés sont ceux ci-dessus.

Release prévue **3.8.0.63**. Binaires Linux nouveaux, bundle Windows précédemment livré conservé avec sa provenance propre ; Manager inchangé. Le client lecteur mpv n'adopte pas encore Surface v1, ce lot fournit le raccord natif et son consommateur direct/dispatcher. AH-279 reste In Progress jusqu'à publication vérifiée ; AH-49/AH-282/AH-281 restent ouverts.

Sources finales : backend `df7e02e7bd3f4d274986946d2e5a04e905d7a454`, qualification publique `a4e88c8c114385f41113e9ac047db3f894df3c87`, bundle Linux `8f7d7b8414c27157de91d54270cab78bb64e0e5e`. Le répertoire Windows de ce pin est inchangé depuis d00ed919 (backend652fbc6).
