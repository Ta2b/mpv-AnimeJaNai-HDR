# Intégration GPU spécialisée AMD / NVIDIA

## Checkpoint de livraison en cours

**Les builds Windows complets ont réussi** pour AMD et NVIDIA : source backend
`1f3e8f204cdabfd22b6673116c0e5b341adb43d3`, source lecteur `6a53c39`, run privé
`38639699749`. Résultat et logs récupérés via la référence Git privée
`build-status/specialized-1f3e8f204cdabfd22b6673116c0e5b341adb43d3-1`.
Ce sont des compilations/liaisons MSVC et HIP/CUDA réelles, sans lecture GPU.
Les anciennes mentions « DLL Windows non liée » ci-dessous sont dépassées.

Depuis ce résultat, protections ajoutées pour RIFE ensemble (graphe RGB complet)
et RIFE seul (pas de placeholder différé sans chaîne d’upscale), parsing MIGraphX
des poids inline en mémoire et repli sur le graphe RGB si extraction impossible.
Leurs compilations Linux passent ; leur dernier build Windows reste à obtenir.
Le runtime AMD attend son scalaire par événement, sans drainer les upscales.
La capture CUDA complète évite les captures de réseaux redondantes.

Packaging en cours : `AJI_SPECIALIZED_LOCAL` remplace seulement les bibliothèques
après la base amont, exige provenance ABI 9 / TRT 11.3, et conserve les outils.
`gpu-binaries-source-ref.txt` devra pointer un commit immuable de petits binaires
du projet, sans runtime vendor ni modèles. Le script de staging est écrit.
Windows : runtime AMD séparé en composant, DLLs dans l’overlay ; le Manager
exige module + runtime avant de proposer MIGraphX. `AJI_AMD_CONSUME_LOCAL=1`
consomme le SDK temporaire CI pour éviter sa duplication. Les packs utilisent
un listfile UTF-8 et drainent les sorties 7z, pour les milliers de fichiers.

**Étapes restantes pour la livraison** : committer/pousser les protections et
hooks de packaging, obtenir leur résultat Windows, récupérer leurs DLLs via
la ref de build, y joindre les bibliothèques Linux compilées avec RPATH portable,
créer la référence binaire immuable et son pin, puis construire la release et
actualiser ici chaque SHA/statut. La préparation anticipée reste abandonnée.
Aucun test, benchmark ni inférence locale n’est autorisé par l’instruction actuelle.
Les modèles, GPU de référence et worktrees utilisateur restent à conserver.

## Mandat et statut — 14 octobre 2026, 23 h 08 (Paris)

L’utilisateur demande MIGraphX + HIP spécialisé sur Windows/Linux, cible
RX 9070 XT (`gfx1201`), et TensorRT + CUDA spécialisé. Conserver les modèles
actuels et la qualité de référence. **La préparation anticipée des moteurs est
abandonnée explicitement.** L’instruction antérieure d’arrêter les tests et
benchmarks reste applicable : compilation, liaison et lecture statique seulement.
Aucun gain mesuré, aucune parité numérique nouvelle ne sont annoncés.

**Travail en cours, non livré.** La release publiée reste 3.8.0.29 (`6fa85bb`).
Ce fichier est le point de reprise du chantier, distinct des anciens résultats.

## Code écrit

- `native/amd/exec_migraphx.cpp` : C API MIGraphX native, formes NCHW fixes,
  précision FP16/FP32 du modèle, fast-math désactivé, tuning exhaustif par défaut,
  allocations GPU persistantes pour entrée, sorties `main:#output_N` et scratch.
  Pas de partitionnement ORT ni de repli CPU pour l’inférence AMD native.
- Capture HIP des réseaux après une première exécution, adresses et formes des
  sorties contrôlées avant capture ; repli sur exécution ordinaire si capture ou
  replay indisponible. `AJI_MIGRAPHX_GRAPH=0` désactive la capture ;
  `AJI_MIGRAPHX_TUNE=0` désactive la recherche exhaustive des kernels.
- `native/amd/hip_kernels.hip` : préparation NCHW, padding/grille/timestep RIFE,
  crop flow/mask, réduction du mouvement (seulement 4 octets lus pour décider),
  warp RGB24 et warp flottant NCHW FP16/FP32. Pas de fast-math ni de nouvelle
  quantification. Cache exact des sources et promotion du dernier endpoint.
- `onnx_flow.cpp` partagé et privé : `aji_onnx_motion_outputs` conserve le graphe
  et les poids, expose uniquement flow et masque. Les compilateurs peuvent ainsi
  supprimer la production RGB finale inutilisée dans la chaîne warp. Le nom
  TensorRT comporte une empreinte des poids afin d’éviter un ancien moteur
  incompatible. MIGraphX transforme ce graphe uniquement en mémoire, sans écrire
  de copie des poids sur disque. L’ancien RIFE reste disponible.
- Linux : module séparé `libaji_migraphx_rgb.so`, sélectionné par
  `linux-playback.lua` pour MIGraphX. `libaji_ort.so` reste sans dépendance ROCm.
  La frontière existante RGB24 hôte reste présente entre les étapes ; ce chemin
  n’est pas un pipeline vidéo entièrement résident sur GPU.
- Windows : `device_model.h` et `windows_interop.h`, partagés avec le backend
  privé. Sélection HIP par LUID Direct3D, import des buffers D3D12, deux fences
  GPU pour les deux directions, entrée/sortie MIGraphX directement liées aux
  buffers partagés. Chemin vidéo haute profondeur existant conservé.
- Backend Windows privé : compilation conditionnelle de `aji_dml.cpp` en
  `aji_migraphx.dll`, ABI 9. Flow/mask et endpoints upscalés restent sur GPU,
  un upscale par source, warp flottant HIP. La chronologie des dessins tenus
  Windows n’est pas portée ; les modèles temporels rank-5 sont rejetés.
- TensorRT/CUDA privé : fusion de la branche CUDA Graph RIFE dans `warp-chain`,
  capture du RIFE classique ET du réseau motion, cache de timestep cohérent,
  capture par réseau SPAN/temporel lorsque la capture complète est impossible
  (warp/TrueHDR), nettoyage des captures avant contextes/buffers, invalidation
  des endpoints sur seek. `AJI_RIFE_CUDA_GRAPH=0`, `AJI_MODEL_CUDA_GRAPH=0`
  permettent de désactiver les captures concernées. Voir aussi les noms exacts
  des variables dans le code privé avant diagnostic.
- Dispatcher privé : choix MIGraphX et transmission des extensions optionnelles
  dessins aux backends qui les proposent. Pas de changement de l’ABI obligatoire.
- Manager : sélection « MIGraphX + HIP » Windows/Linux, conditionnée par GPU et
  présence de la bibliothèque native. Assemblage : `AJI_LOCAL_BUILD` Windows et
  Linux, bundle `AJI_AMD_LOCAL`, protection contre un remplacement contradictoire
  des bibliothèques ORT/DirectML/CUDA. Build AMD Linux séparé, appelé par la release
  Linux, sans inférence ni tests sur le runner.

## Dépôts et worktrees à conserver

| Dépôt | Chemin de travail | Branche / base |
|---|---|---|
| Lecteur | `/home/ta2b/Documents/mpv-AnimeJaNai-HDR` | `perf/specialized-gpu-20261014`, base `9a00a41`, code `b0a44ff261a7d385d8dedb284dd5cb50acf07c00`, poussé ; correction de liaison MSVC dans le commit suivant |
| Backend privé | `/home/ta2b/.animejanai-tools/work/gpu-specialized` | `perf-specialized-gpu-20261014`, base `warp-chain` / `3e30998`, cherry-pick `f4fcd17` résolu en `e5ec2b8`, intégration `94ee9a0c9ba10d6ccb3d32088bf0f58613376c1a` poussée ; suivi de builds Windows en cours |
| Manager | `/home/ta2b/.animejanai-tools/work/manager-specialized` | `perf-specialized-gpu-20261014`, commit `5abbc367f9584cd026ef04ada8ea3524fb3c76f6`, poussé ; builds Windows/Linux/macOS et release immuable réussis |

Ne pas toucher au worktree utilisateur voisin `Documents/animejanai-inference-rtx`
(fichiers RTX modifiés), ni à ses autres worktrees. Dans le lecteur, le PDF
`Avis sur mpv-AnimeJaNai-HDR.pdf` et le cache Core ML non suivis appartiennent à
l’utilisateur. Ne pas les ajouter aux commits. Ne pas modifier les modèles.

## Preuves de compilation locales

Artefacts ignorés : `artifacts/performance/amd-specialized/`.

| Cible | Résultat acquis | Limite |
|---|---|---|
| Linux MIGraphX/HIP | **Bibliothèque partagée compilée et liée**, SDK réel ROCm 7.2 / MIGraphX 2.15, LLVM 22, cible gfx1201 ; `amd-build.log`, `amd-sdk-build/libaji_migraphx_rgb.so` | Aucune inférence ni validation GPU/qualité |
| Linux TensorRT/CUDA | **Bibliothèque partagée compilée et liée**, TRT 11.3.0.99 / CUDA 13.4, architectures 75/80/86/89/90/100/120 ; `trt-build.log`, `trt-build/libaji_trt.so` | Même limite |
| Windows AMD | `aji_dml.cpp` et `exec_migraphx.cpp` compilés en objets PE/COFF MinGW avec vrais headers DML/ORT et SDK Windows ROCm 10.1 / MIGraphX 2.18 ; dispatcher et DirectML classique compilent aussi | Pas encore de DLL liée avec le SDK Windows ; pas de compilation MSVC ni de lecture Windows |
| ORT existant | Build Release `aji_ort` compilé et lié après le dernier ajout motion-only | Aucune exécution, syntaxe/liaison uniquement |
| Manager | Build Release réussi, 44 avertissements préexistants, zéro erreur | Aucun test/UI lancé |
| Assembleur | Build Release réussi après les dernières vérifications du bundle, zéro avertissement/erreur | Aucun assemblage complet ni test exécuté |
| Scripts | Lua `luac -p`, AppRun `bash -n` réussis | Syntaxe seulement |

Les premiers essais headers/LLVM IR sans SDK mentionnés auparavant sont dépassés
par les compilations liées Linux ci-dessus. Les compilations Windows en objets
ne doivent pas être présentées comme un build DLL complet.

## SDK et dépendances

- Linux : `fetch_rocm_sdk.py` extrait les paquets officiels sans installation
  système et contrôle leurs SHA-256. Le SDK compilateur extrait n’installe pas
  les dépendances runtime de MIGraphX (MIOpen/rocBLAS/etc.) sur le poste cible.
  La bibliothèque optionnelle exige un runtime ROCm compatible installé.
- Windows : HIP seul n’inclut pas forcément MIGraphX. Windows ML expose un EP
  MIGraphX mais son installation ne constitue pas un SDK C autonome. La voie
  directe native doit donc disposer de headers/import libs et DLL MIGraphX/HIP
  cohérents. `fetch_windows_sdk.py` extrait maintenant un SDK C/HIP cohérent et ses données
  gfx1201, contrôlés par SHA-256 ; extraction locale terminée.
- Une archive communautaire `lc700x/MIGraphX-Windows` a été téléchargée pour
  inspecter la distribution Windows, version `v10.1.0a20260822`, MIGraphX 2.18 ;
  le SDK est extrait et le workflow privé construit un bundle portable facultatif ;
  aucune DLL de cette archive n’est encore embarquée dans un paquet publié.
  Ses bibliothèques ne doivent pas être présentées comme un SDK officiel AMD.

## CI confirmée

- AMD Linux : [38637934496](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/actions/runs/38637934496),
  **succès**, code `b0a44ff`, bibliothèque gfx1201 compilée/liée, aucune inférence.
- Manager : [38637235847](https://github.com/Ta2b/AnimeJaNaiManager-HDR/actions/runs/38637235847),
  **succès** sur les trois plateformes et [quatre assets publiés](https://github.com/Ta2b/AnimeJaNaiManager-HDR/releases/tag/hdr-5abbc367f9584cd026ef04ada8ea3524fb3c76f6).
- Backend privé : push SSH confirmé ; l’API GitHub de cette session renvoie 404
  pour ce dépôt. Les résultats des builds Windows ne sont donc pas encore
  confirmés. Le workflow suivant enregistre logs/résultats et petites DLL du
  projet sur `build-status/specialized-<commit>-<attempt>`, lisible via Git SSH.
  Aucun runtime vendor ni modèle n’est ajouté à cette référence de build.

## Prochaines actions exactes

1. Terminer le build Windows : SDK/version C API cohérents, compilation HIP
   COFF et liaison MSVC, logs CI et dépendances runtime/distribution explicites.
2. Consommer les artefacts privés Windows dans un paquet complet une fois leur
   build réussi. Le code de packaging et le suivi manifest/packs sont écrits :
   alias TensorRT RTX dans l’overlay, runtime AMD dans le composant facultatif
   GPU engines (`onnxruntime`). Le pin Manager est `5abbc36`, poussé ; vérifier
   la disponibilité de sa release `hdr-<sha>` avant assemblage.
3. Recompiler les éléments modifiés depuis leur dernier build, contrôler les
   diffs ; **ne pas lancer de tests/benchmarks sans nouvelle instruction**.
4. Les trois dépôts sont committés/poussés ; finaliser le suivi Windows et ses corrections puis consigner les nouveaux SHAs et statuts CI.
   Ne pas publier comme stable une intégration Windows encore non liée.
5. Performance suivante : supprimer les transferts entre modèles du bridge Linux,
   porter la chronologie dessins Windows, puis validation réelle lorsque autorisée.

## Dépendances Windows et checksums

Le fetcher NVIDIA extrait les composants CUDA du manifeste officiel 13.4.1 et
les headers/import libs TensorRT correspondant aux pins de l’assembleur ;
extraction locale terminée. Le fetcher AMD fusionne les fichiers ordinaires des
wheels en un préfixe portable sans dépendre de droits de symlink Windows et
conserve les notices des composants statiques. Les headers C API 2.18 viennent
du commit AMD `95672916ed289d4be9d230a9be732e1bbad97e8c` ; les fichiers
consommateurs `config.h` et `api/export.h` sont générés explicitement (pas de
headers C++ MIGraphX exposés). Provenance des binaires communautaires indiquée.

`build-evidence.json`, dans le dossier d’artefacts ignoré, contient tailles et
SHA-256 des bibliothèques Linux et objets Windows à ce checkpoint. Les logs
`windows-nvidia-sdk-fetch.log`, `windows-sdk-fetch.log`, `windows-compile.log`,
`windows-executor-compile.log`, `windows-dml-compile.log`,
`windows-dispatch-compile.log`, `amd-build.log`, `trt-build.log`, `ort-build.log`,
`manager-build.log`, `assembler-build.log` distinguent les vérifications.
Une tentative de compilation HIP Windows via une cible GNU croisée a échoué
sur les hypothèses `long` des headers vendor : ce n’est pas une preuve de build
HIP Windows. La voie prévue utilise le compilateur Windows AMD et MSVC en CI.

La formule de mélange, le seuil de 15 px à 720p et la stratégie une médiane par
paire sont ceux de la 3.8.0.29. Ces approximations temporelles préexistantes ne
prouvent pas une identité numérique avec l’ancien pipeline : `rife_engine=old`
reste le chemin de comparaison. Le maintien des poids est établi par le code ;
la qualité et le débit de ces nouvelles implémentations restent non mesurés.
