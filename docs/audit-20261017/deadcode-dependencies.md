# Audit code mort, dépendances et travail inutile — 17 octobre 2026

Référence inspectée : player **3.8.0.82**, commit `0f3f6bfb7e76ca15647d74fc5a91405d3072be69`, et backend `463a0c73b6f2e77df09f908a3fef2bf5898cb5a1`. Bundle GPU `5217111b754412338fe94d236d80f39dcd42b957`. Les chemins exacts, preuves et contrôles proposés figurent dans [deadcode-candidates.json](deadcode-candidates.json). Les lignes ci-dessous désignent ces refs, avant nettoyage.

Deux petits retraits ont une preuve suffisante et sont appliqués dans le checkout isolé `/tmp/animejanai-audit-cleanup-20261017`, sans commit ni publication par cet audit. Les autres conclusions sont des propositions ou des éléments à conserver. Aucun benchmark GPU nouveau, aucune extrapolation de gain FPS.

## Retraits ciblés réalisés

- **DD01 — fonction Lua `bridged()`** : `portable_config/hdr-tools/linux-playback.lua:82`, définition locale sans référence, export ni callback. Une ligne retirée. Le script lui-même reste chargé par `user-scripts/hardware_auto.lua:9`. La recherche ne justifie aucune suppression de ce script.
- **DD02 — deux copies de répertoires AppImage** : `installer/linux/AppRun:125–126` recopiait `scripts` et `shaders`, déjà copiés par la boucle à la ligne 103. Deux commandes retirées, boucle globale conservée. Cela évite deux appels `cp` et la recopie des fichiers correspondants à chaque lancement normal. Aucun gain de fluidité vidéo revendiqué.

Qualification minimale : `luac -p`, `sh -n`, `git diff --check` réussis. Une fixture CPU utilisant les blocs extraits des sources avant/après donne **31 entrées identiques** (contenu, permissions, symlinks, fichiers personnalisés conservés), avec **7 → 5 appels `cp`**. Voir [script reproductible](deadcode-validation/check_apprun_copy.py) et [résultat](deadcode-validation/apprun-copy-result.json). Ce contrôle porte sur la copie ; il ne constitue pas un lancement complet AppImage. Le premier `cp` échouait déjà sous `set -e`, donc les copies suivantes ne servaient pas à récupérer son échec.

Diff livré à l’agent principal : uniquement ces deux fichiers, trois lignes supprimées. Les modifications existantes de `Program.cs`, appartenant à l’agent principal, n’ont pas été touchées.

## Dépendances à simplifier sans supprimer leurs fonctionnalités

| ID | Constat et preuve | Meilleure suite |
| --- | --- | --- |
| DD03 | Backend `src/pipeline_config.cpp:6` conserve `<cstdlib>` sans utilisation détectée. | Retrait cosmétique lors d’un prochain changement, avec compilation de cette unité. Aucun gain runtime. |
| DD04 | `native/linux-ort/CMakeLists.txt:62–65` ajoute deux tests CPU aux cibles ALL. Les releases Linux `release-linux.yml:93–95` et macOS `release-macos.yml:71–77` construisent ALL mais ne livrent que `aji_ort` et `animejanai-ort-test`. | Cibler explicitement les exécutables livrés ou utiliser `EXCLUDE_FROM_ALL`/`BUILD_TESTING`. Garder les tests et leur exécution explicite de qualification. |
| DD08 | Le parser ORT/Apple/AMD vient encore d’un clone externe `v0.11.1`, alors que le pipeline CUDA utilise son parser local. CMake ORT ligne 13 et workflows Linux ligne 89, macOS ligne 42, AMD ligne 33. | Définir un contrat de configuration commun et comparer les champs réellement lus avant consolidation. Divergence de sources prouvée ; bug de parsing actuel non démontré. |
| DD11 | Le dispatcher est annoncé sans CUDA à `backend/CMakeLists.txt:86`, mais `project(... CUDA)` ligne 14 et `find_package(CUDAToolkit REQUIRED)` ligne 38 rendent le SDK obligatoire au configure. | Options de fournisseurs et activation conditionnelle des SDK ; vérifier un build dispatcher seul, puis les cibles de release inchangées. |
| DD13 | `aji_encode` est un CLI hors ligne optionnel, et `aji_msb444_test` un test de développement. Ils ne sont pas nécessairement livrés ; `aji_harness` et `aji_kernel_test` le sont. | Séparer explicitement les cibles dev et produit, préserver les outils. Absence d’un paquet ne signifie pas inutilité. |

Le moteur AMD natif réutilise encore les sources ORT et lie `onnxruntime` (`native/linux-ort/CMakeLists.txt:30–35`). Ce lien est actuel et ne peut pas être retiré simplement parce que MIGraphX exécute une partie du calcul.

## Retraits structurels nécessitant un lot complet

**DD05 / AH-328 — FRUC est actif et doit être retiré selon le mandat utilisateur.** Ce n’est pas du code sans références. Le parser accepte FRUC (`pipeline_config.cpp:121`), le pipeline charge son API dynamiquement, Lua configure `fruc-lib` et le packaging copie ses fichiers (`Program.cs:798`, `:1062`). Surtout, `CMakeLists.txt:44–83` place **la construction du pipeline et TrueHDR dans le bloc conditionné par le SDK FRUC**. Supprimer d’abord le SDK ou le bloc entier casserait des fonctionnalités conservées. Ordre recommandé : rendre le pipeline autonome au build, puis retirer FRUC des fournisseurs, filtres, schémas, UI, installateurs et assets avec migration explicite des profils. Préserver le SDK utilisateur non suivi et les preuves historiques.

**DD06 / AH-325 — ancienne interface et compatibilité backend sont deux chantiers distincts.** `legacy_equivalent()` puis le retour `AJI_PIPELINE_LEGACY` restent consommés par le patch mpv. Les facteurs rationnels restent explicitement disponibles via ABI9 (`pipeline_config.cpp:116`). La suppression de l’ancien éditeur ne justifie pas la suppression des voies backend encore nécessaires. Le retrait complet requiert une parité documentée et une migration versionnée.

**DD07 / AH-326, AH-330 — l’alias TRT/RTX identique reste utilisé.** Le backend copie `aji_trt` vers `aji_trt_rtx` (`CMakeLists.txt:110`), mais Lua teste cet alias et le sélectionne encore (`linux-playback.lua:37`, `:170`). Garder le nom tant que la route HDR existe. Une consolidation future concerne aussi les anciennes bibliothèques installées et les règles de remplacement ; elle ne promet pas un gain FPS. Des liens de fichiers ne sont envisageables qu’après vérification du comportement des archives et installateurs.

## Deux optimisations exactes candidates, encore non qualifiées

**DD09 — éviter la préparation motion lorsque le plan ne peut jamais l’utiliser.** `aji_trt.cpp:1345` appelle `setup_warp()` sur un RIFE avant upscale sans ensemble ; les lignes 1245–1250 peuvent construire/charger le moteur motion. Pourtant un bloc RIFE seul retourne avant activation spatiale à la ligne 2036, et `warp_ready()` refuse `!active` à la ligne 2576. C’est notamment pertinent pour le Fast ×2 conservé en bloc séparé. Décider l’éligibilité à partir du plan final avant cette préparation pourrait économiser démarrage et VRAM sans modifier les images. Le coût effectif dépend du profil et n’a pas été mesuré. Essai suffisant : RIFE-only avec sorties identiques et absence de préparation motion, puis un cas fusion Fast ×4 qui confirme que motion reste disponible.

**DD10 — une fence finale par burst au lieu d’une par image.** `aji_pipeline.cpp:311–318` soumet trois copies asynchrones puis synchronise, et la boucle 434–437 répète cette séquence pour chaque sortie. Le résultat et les owners ne sont publiés/libérés qu’après `run()` (506–513). Une seule fence après toutes les copies sur le même stream paraît compatible avec ce contrat, si les surfaces sources restent vivantes et si l’unwind conserve sa synchronisation. Ce n’est pas une autorisation de supprimer les barrières entre SDK. Validation si implémentation : un burst ×4 et EOF, égalité des pixels, durée de vie des owners et reset ; timing bref pour décider si le gain est utile.

Ces propositions prolongent [moteurs-pipeline.md](moteurs-pipeline.md), notamment MP05/MP06. Elles sont **non mesurées**, et non présentées comme des optimisations déjà validées ou livrées. Les timings hybrides lot 55 restent instables, dont la comparaison burst avant `40.385/38.672 ms`, après `58.263/38.347 ms` : aucune conclusion générale de gain ou régression persistante n’en découle.

## Faux positifs exclus et limites

- `InferOutputShape` dans `cpu_activations.cpp:44` est un callback du template ORT `CustomOpBase`, malgré une seule occurrence littérale.
- `exec_ref.cpp` est compilé et sélectionné par `provider == "reference"` (`aji_ort.cpp:285`). C’est une référence de test exploitable.
- L’ancienne voie de threads CPU est sélectionnable avec `AJI_PIXEL_POOL=0` pour ablation (`engine.h:30–52`). Elle n’est pas inaccessible.
- Les exports `aji_*`, les champs de configuration, les shaders, les patches mpv et les noms de bibliothèques ont des consommateurs dynamiques ou externes. `rg` seul ne prouve pas qu’ils sont morts.
- Le checkout utilisateur est à `55bbc850...`, distinct de `.82`, avec des docs, le SDK `NvOFFRUC/` et un cache CoreML modifiés ou non suivis. Ils ne doivent pas être nettoyés comme des résidus de la release. La préparation GMFSS est sur une autre branche ; son absence de `.82` ne signifie pas abandon.

La revue couvre les chemins cités et leurs dépendances directes dans les refs livrées. Elle n’affirme pas l’absence globale de code mort, ni un audit détaillé de tout le code upstream des SDK. Aucun fichier utilisateur, dépendance tierce, ABI ou fonctionnalité active n’a été supprimé par cet audit.
