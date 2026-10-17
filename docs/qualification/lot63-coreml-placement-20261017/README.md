# AH-348 — Diagnostic CoreML hors du démarrage critique

L'ancienne collecte attendait un sémaphore jusqu'à20secondes dans le constructeur. Elle est remplacée par une demande GCD utilitaire, avec URL/configuration et état partagé possédés jusqu'au callback. Le callback ne capture pas Executor/Context, ne touche pas `note` ni les buffers ; aucun join dans le destructeur. Les statistiques prennent une copie synchronisée une seule fois par worker. Les autres exécuteurs gardent leur note immuable.

Cache en mémoire de16requêtes : identité complète du template/ressources, modèle/taille réelle, unités, permission de précision, hints effectivement choisis et OS/build. Les requêtes identiques pending sont partagées. Une entrée pending n'est jamais évincée pour lancer un nombre illimité de demandes ; à saturation le diagnostic est explicitement indisponible. Callback sûr après destruction d'un abonné/cache, erreur diagnostique non fatale, NO_PLAN conservé. Aucun changement aux poids, computeUnits, hints, précision, conversions ou `run()`.

Qualification native unique : [CI39011223631](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/actions/runs/39011223631), source73d9d8f, macOS15.7.9/build24G830 arm64, CoreML natif CPU, SPAN Sharp1Performance256×256→512×512. Même modèle converti repris de la release.86, cache compilé réchauffé une fois, aucune reconversion/validation redondante. [Reçu](native-receipt.json), [modèle](model-sha256.txt), [machine](machine.txt).

- Référence synchrone : construction exécuteur110,132ms, première prédiction34,399ms.
- Candidat : construction79,418ms, première prédiction45,507ms ; diagnostic pending à la sortie du constructeur **et après la première image**, puis plan valide56opérations CPU préférées.
- Collecte désactivée : construction43,893ms, première prédiction34,104ms, état disabled explicite.
- Sorties RGB8 strictement identiques dans les trois cas ; hash18dfcc6c44d5a6abeeeb97c2c9e393c9126762ddc34e9da1e72fd806f8843f63. Fixture CPU d'état acquise : déduplication, borne, clé, erreur, callback tardif et lecture concurrente.

Interprétation : le diagnostic ne bloque plus la première image. L'observation de construction baisse d'environ30,7ms, mais son travail concurrent peut influencer la première prédiction ; aucun gainFPS ou pourcentage universel revendiqué. Le test mesure la construction de l'exécuteur natif, pas l'ouverture totale du lecteur. `ort_test` rapporte désormais configure et first_process séparément pour les contrôles futurs ; son ancien chronomètre ne mesurait pas configure.

Limites : un seul modèle/taille et CPU natif, SoC exact non relevé, aucune qualification GPU/ANE/ORT ni campagne multi-placement. Le plan indique des préférences d'opérations, pas une trace matérielle par frame. AH121 parent reste ouvert. API callback vérifiée dans la [documentation Apple](https://developer.apple.com/documentation/coreml/mlcomputeplan-85vdw/loadcontentsofurl:configuration:completionhandler:), disponible macOS14.4 ; OS plus ancien indisponible explicite. Build macOS de la release et extraction du module restent à confirmer avant Done.
