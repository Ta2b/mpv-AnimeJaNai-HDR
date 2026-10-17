# AH-349 — deux SPAN Metal sans retour RGB hôte intermédiaire

Qualification native le17octobre2026, macOS15.7.9 / build24G830 / arm64, **Apple Paravirtual device**, mémoire unifiée. Deux vrais SPAN Performance128→256→512, modèles .91 déjà livrés et mêmes graphes/précision/options. Pas de résultat sur un GPU Apple physique ou à720p extrapolé.

## Conclusion suffisante

- Ancien binaire de référence, candidat ablation off et candidat on : **RGB8 exact**, SHA256 `2aa215074dc7823a63043c1241bba5b3ec5df48fdd7478e8f02a818bbdc12a45`. Padding destination intact.
- Staging hôte explicite **245760→49152octets**, `readBytes` explicite **983040→786432octets** par sortie : le256×256×3 intermédiaire n’est plus lu ni recopier dans l’entrée suivante. Entrée/sortie finales restent hôtes.
- Une observation chaude de trois appels complets par voie, après première sortie : médiane **17.178→15.497ms** (environ9.8% local). Aucun replay après cette conclusion, aucun FPS720p/GPU physique annoncé.
- Resize50% intermédiaire : repli hôte conservé, RGB exact à la référence. Configure détruit/recrée les graphes et retrouve exactement la référence.
- Contrôle restant seul, dans une secondeCI **error-only** : sortie du second graphe volontairement invalide dans une copie privée .ajm, refus `Metal: invalid graph output`, destination intacte ; modèle restauré, reconfigure et RGB exact. Graphe synchrone terminé avant l’erreur ; aucune perte physique du GPU ou exécution asynchrone simulée.

[Reçu principal](receipt.json), [erreur/reprise](error-receipt.json), [machine](device.txt), [modèles](models.sha256). Utilité établie : passage hôte intermédiaire supprimé et gain local observé, référence numérique conservée.

## Contrat et sélection

`engine.h:ResidentImage` interne décrit RGB8NHWC, mémoire MetalGraph, géométrie et device. Son owner C++ retient fortement le MPSGraphTensorData ; les appels sont synchrones. Le consommateur Metal valide type, forme et registryID. Aucun pointeur Metal dans Job::in ou dans le CABI RGB.

`MetalExecutor::run_resident` réemploie les mêmes graphes : premier réseau après clamp/×255/round/castUInt8, puis castFP16/×1/255 du suivant. Les graphes ne sont pas fusionnés ; readBytes seulement au dernier étage. `run(Job)` reste adaptateur hôte. Les options MPSGraph de synchronisation par défaut sont **inchangées** ; les compteurs portent sur nos copies/API, pas les copies internes/éventuels blits du framework ou du driver.

Le core choisit cette voie seulement pour plusieurs SPAN à fenêtre entière, un worker par étage, même device, sans reuse/boost/areas/padding/resize intermédiaire/RIFE. Un premier resize reste dans le chemin hôte de référence. Cas exclus : ancien plan conservé, aucun réglage utilisateur ignoré. `AJI_METAL_RESIDENT_SPAN=0` est l’ablation interne. Compteurs atomiques dans l’exécuteur, statut de segment dans le snapshot existant.

La sortie du premier graphe reste possédée pendant tout le run synchrone du second ; aucune nouvelle queue asynchrone, thread ou fence. Les autres exécuteurs renvoient can_take_resident=false ; leurs mathématiques et formats ne convergent pas avec Metal.

API Apple vérifiées dans la documentation officielle : [run synchrone](https://developer.apple.com/documentation/metalperformanceshadersgraph/mpsgraphexecutable/run(with:inputs:results:executiondescriptor:)), [TensorData consommable comme feed](https://developer.apple.com/documentation/metalperformanceshadersgraph/mpsgraphtensordata), [synchronisation des résultats](https://developer.apple.com/documentation/metalperformanceshadersgraph/mpsgraphoptions/synchronizeresults). La documentation confirme le contrat d’appel ; la CI fournit la preuve native.

## Sources et livraison

CI39021246527, runtime source `1b2d967e28912a961cf18e117fcd0946e36518ad` ; CI erreur39021459624 source `b1602fdf8f8a6ddcf767d7b735dd39c3c7054dc0`, runtime inchangé. Dylib **byte-identique entre les deux builds**, SHA256 `67805bd1a0c6dea078fd0a14c26467cf7e81a9d207c4b14da69f4483b9dda190` ; référence `ab9e1281…` identique à .91 livrée. Vraie source core C++ syntax-check Linux passée ; tous les fichiers ObjC++/core compilés et CABI exécuté sur Mac. Aucune recompilation de modèle pour ce lot.

Livraison .96 à vérifier : troisCI/tag, dylib Mac réellement extrait contre ce hash, modèles et17programmes gérés. Si les octets concordent, ne pas rejouer les essais natifs concluants. Autres moteurs/mathématiques inchangés ; revue/compilation et qualifications antérieures réutilisées. AH349 Done seulement après livraison vérifiée. AH119 reste ouvert pour CoreML→CoreML, RIFE→SPAN et rendu ; ce lot ne promet pas une chaîne vidéo sans aucune copie hôte.
