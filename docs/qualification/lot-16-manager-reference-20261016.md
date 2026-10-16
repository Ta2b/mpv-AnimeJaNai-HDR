# Lot 16 — export de référence depuis le Manager

AH-236, sous-ticket de AH-11. Base player `2943d34bf423894278bede36391a7376324de22a` / 3.8.0.45 ; Manager de référence `132dab9525b5eab87e149f3d043b572b5f2d258a`. Aucun changement de bibliothèque d’inférence, modèle, shader ou référence Quality. Le lot 14 non qualifié n’est pas inclus.

## Fonction et utilité

Avant : export CLI/Lua disponible, aucune action Manager. Après : onglet Reference, découverte des sessions des lanceurs, choix explicite entre plusieurs vidéos, export vers un nouveau JSON par le sélecteur local de fichiers. L’action réutilise `ReferenceExporter` partagé ; elle capture la chaîne de la session choisie, jamais le profil non enregistré de l’éditeur. Média/filtre/slot sélectionnés sont recontrôlés dans le rapport ; une modification refuse l’export et demande de rafraîchir. Destination existante et connexion perdue donnent des erreurs, sans rapport trompeur ni écrasement.

Utilité : accès direct à la référence observable pour reproduire les prochains essais. Aucun gain FPS attendu ou revendiqué ; lecture de fichiers à la demande, aucun travail périodique.

## Essai ciblé réel

`tests/manager-reference/ReferenceProbe.csproj` référence le projet Manager réel ; le probe appelle exactement les méthodes du ViewModel utilisées par l’onglet. `real_sessions_check.py SPEC` ouvre deux lecteurs mpv privés (bridge compilé du lot 08), deux copies du même clip 128×72 et deux slots du même modèle SPAN ; ONNX Runtime **CPU forcé**, décodage CPU, sortie null. Les sockets et processus appartiennent à cet essai. Le proxy IPC observe les commandes Manager, sans simuler les réponses mpv.

- Découverte de deux vidéos : aucune sélection implicite ; choix de session 2, rapport associé à `session-2.mp4`, slot 2 et paramètres réels du filtre. Quatre empreintes vérifiées indépendamment. Export **0,0671 s**, coût ponctuel unique.
- Avant/après export : mêmes média, filtre, pause, PTS et paramètres de sortie sur les deux lecteurs. Les **180 commandes** de découverte/capture (positive et refus de sélection périmée) sont exclusivement `get_property`/`expand-path` ; aucune mutation du lecteur par le Manager. La preuve PNG16/PTS du moteur d’export existant reste celle du lot 02, sans rejouer ce cas conclusif ni revendiquer ici une nouvelle qualification HDR.
- Même destination : refus explicite, contenu préservé, aucune nouvelle commande IPC.
- Profil changé après sélection : refus explicite, aucun JSON créé.
- Lecteur choisi fermé : erreur explicite, aucun JSON créé.

Build Manager et bindings Avalonia réels : **0 erreur, 44 avertissements existants**, après retrait d’un avertissement nullable introduit dans le nouveau handler. La première invocation du lecteur extrait ancien a refusé l’option `ahead` avant tout décodage ; ce diagnostic est conservé (`*.invalid-ahead`). Le test a utilisé ensuite le lecteur du lot 08 qui possède cette option. Le refus de connexion du dernier cas a aussi provoqué une traceback dans le proxy de test ; résultat attendu et correctement traité par le Manager, puis nettoyage du proxy sans nouvelle exécution du cas conclusif.

Artefacts : `artifacts/performance/lots-20261016/lot-16/` (spec, commandes exactes, transcript, rapport, logs et reçu `summary.json`). Pas de répétition après conclusion.

## Limites et livraison

Observation séquentielle, pas capture atomique ; changement aller-retour potentiellement indétectable. Les empreintes identifient les fichiers sur disque ; modèles déjà chargés, dimensions de chaque étage, précision/placement effectifs et fraîcheur des stats restent explicitement inconnus ou non prouvés, dans AH-234/AH-235. Le JSON conserve `qualification: partial` pour ces limites du format ; la fonction Manager AH-236 est qualifiée dans son périmètre Linux. Transport et sélection native du fichier sur Windows/macOS restent AH-237 ; compilation CI ne remplace pas ces essais matériels.

Manager `4c4af97f322706682c38ff4d630f4156b50999ef`, source player partagée `36ba0ee958837d3c9180904b197d50dac6a04a62`. Workflow **38846697494 success**, release immuable `hdr-4c4af97f322706682c38ff4d630f4156b50999ef` vérifiée avec quatre assets uploaded. Player **3.8.0.46** publié avec ce pin ; AH-236 reste In Progress jusqu’à vérification des trois workflows/assets de cette livraison. Le lot 17 démarre pendant la publication, sans attente.
