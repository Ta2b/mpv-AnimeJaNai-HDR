# AH-359 / AH-244 — manifestes stables et cycle natif Core ML

Les modèles Apple de .86 et .87 contenaient les mêmes programmes, poids et tables. Seuls les UUID aléatoires des quatre `Manifest.json` changeaient parmi les 32 ressources. L'identité V2 inclut correctement ces octets : leur renouvellement invalidait donc inutilement les modèles compilés.

Le convertisseur normalise désormais les seuls packages qu'il vient de générer, après sérialisation déterministe du programme. Recette `animejanai-coreml-manifest-v1` : digest SHA-256 de toutes les ressources hors manifeste, chemins et longueurs inclus ; UUIDv5 dérivés de ce digest et de chaque entrée sémantique. Références et racine sont modifiées ensemble. Schéma inconnu, références absentes, chemins ambigus/sortants et liens sont refusés avant écriture atomique. Aucun poids, programme, table ni modèle installé n'est modifié. Le tag V2 continue d'inclure le manifeste et tous les poids. Une migration de tag est nécessaire ; les anciennes entrées restent conservées.

Contrôle portable unique sur copies des vrais paquets .86/.87 : les 32 ressources deviennent identiques après normalisation, les huit tags convergent par modèle, tous les octets hors manifeste restent inchangés. Idempotence et refus conservateurs contrôlés. Remplacer les seuls poids par ceux d'un modèle valide change le tag même avant normalisation, puis les nouveaux IDs et le tag changent après normalisation. [Reçu portable](portable-receipt.json).

[Exécution native 39013648864](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/actions/runs/39013648864), source `50c3fd7215b317b983d3f73c5696dee5dd9d90f6`, macOS 15.7.9 / 24G830, arm64, Apple M1 virtualisé. Core ML CPU, SPAN Sharp1 Performance, entrée synthétique RGB 256×256, sortie 512×512 ; diagnostic de placement désactivé, déjà qualifié par AH-348. [Reçu natif](native-receipt.json), [machine](machine.txt).

| Cas distinct | Conclusion |
| --- | --- |
| Compilation froide puis hit original | Une compilation ; hit sans branche de reconstruction, même répertoire compilé et RGB exact. |
| Manifeste normalisé | Accepté par Core ML ; RGB exact avec l'original. |
| Copie réexportée, normalisée identiquement | Même tag, hit du même répertoire compilé, RGB exact. |
| Remplacement des seuls poids, manifeste conservé | Nouvelle clé et reconstruction. Programme et table identiques au donneur Performance ; sortie exacte au donneur et différente de Sharp1. |
| Répertoire `.mlmodelc` présent mais invalide | Erreur explicite « cache cleared, try again », seule entrée courante retirée. La tentative suivante reconstruit et produit exactement la sortie précédente. Autres anciennes entrées conservées. |

SHA-256 RGB original/normalisé : `18dfcc6c44d5a6abeeeb97c2c9e393c9126762ddc34e9da1e72fd806f8843f63`. Avec les poids Performance : `6edc44a92d81afdd1b88677453617452d4bcc3b324efbdca189be373e7b2b4b2`. Aucun benchmark ni gain FPS revendiqué ; bénéfice établi : réutilisation entre exports identiques, sans masquer un changement de poids. L'essai s'arrête après ces conclusions.

Reproduction : compiler `tests/cache/coreml_identity_cli.cpp` avec `native/linux-ort/mlpatch.cpp`. `tests/apple/coreml_manifest_release_check.py --previous-zip … --current-zip … --identity … --work NOUVEAU_DOSSIER` reproduit la comparaison portable. `.github/workflows/qualify-coreml-cache.yml` réutilise les modèles préconvertis de .87 et le probe natif AH-348 ; aucune reconversion ni répétition des comparaisons ONNX/CoreML antérieures.

AH-244 qualifie le cycle existant, dont le retry est une nouvelle tentative du client, sans réparation automatique cachée. AH-240 (clé complète options/runtime), AH-254 (transactions multi-provider) et le parent AH-29 restent distincts et ouverts. GPU/ANE, ORT/CoreML, concurrence de compilation et autres versions d'OS ne sont pas qualifiés ici. Livraison à constater dans le reçu de release avant Done.
