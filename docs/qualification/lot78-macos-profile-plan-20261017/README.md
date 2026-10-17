# AH353 — Lanceur macOS et plan canonique

PLAYER044c53a80c00b6fa88d25f45806af30a5d1d9e8c : contrat C#/CLI et contrôleur ; complément de lanceur8f2b5d6 pour transmettre le répertoire inference réel au Manager. Manager37e7c1ad2ad12982d2b8197824f7c15c28e00958, source partagée044c53a. Aucun code moteur, modèle ou calcul vidéo changé.

Avant : le contrôleur macOS ne consultait pas le JSON canonique ; présence de libaji_ort seulement, sources/règles/policy projetées localement. Le plan C# ne vérifiait que .mlpatch pour CoreMLNative et .ajm pour Metal, sans package/poids ni différence CPU/NPU/GPU de Metal ; le Manager pouvait chercher inference dans les données utilisateur plutôt que le bundle.

Après : helper du bundle, chemins modèles/RIFE/modules exacts ; snapshot privé avant résolution, même version utilisée par le filtre. Async avec timeout5s, annulation par génération, schéma/slot/règle/issues/capacité validés. Une erreur laisse le filtre actif et les fichiers utilisateur intacts. Off n’appelle pas le helper ; rule0 ne réclame pas les modèles des règles inactives ; le HDR du profil est résolu indépendamment. La copie privée de policy Quality est conservée pour le lecteur historique.

[CLI réel](cli-receipt.json) : dix cas, macOS simulé sur Linux avec fichiers privés. Modèle exact absent malgré autre ONNX, table sans package, CoreML sans ONNX inutile, MetalCPU/NPU→template, MetalGPU→AJM+AJW, runtime lié absent, HDRmpv sans SDK, import désactivé, RIFE alternatif et policy maillon. Une seule exécution concluante.

[Complément HDR/rule0](hdr-receipt.json) : quatre cas distincts découverts pendant revue, sans répéter les dix précédents. ProfileHDRmpv disponible même sans règle d’inférence ; TrueHDR refusé macOS, futureversion refusée ; pas de modèles des règles inactives.

Vrai contrôleur `tests/player/macos_profile_plan_check.lua` avec mock des APIs mpv : PASS sélection async/chemins exacts, snapshot immuable quand le fichier change pendant la requête, Quality privée malgré globalFast, modèle manquant/schéma/JSON refusés, timeout→abort, callbacktardif ignoré, Off sans helper, helper absent, nettoyage limité aux copies privées. Puis mode `hdr-only` : seul cas nouveau rule0/HDR conservé sans filtre d’inférence ; pas de replay du premier passage.

Build helperRelease0warning/0error ; Manager compilation0error,43warnings dans les fichiers existants non modifiés. Syntaxes Lua et shell vérifiées. Tests CPU/routage suffisants ; aucune nouvelle qualification GPU/vidéo ni mesureFPS. Les anciennes preuves Windows/Linux .84 d’AH339 restent valides et ne sont pas rejouées.

Production Manager39025011499 réussie sur les troisOS, tag immuable hdr-37e7c1ad2ad12982d2b8197824f7c15c28e00958 vérifié (quatreassets dont archivesdes troisOS). .100 épingle ce Manager et doit être vérifiée après publication. Vérifier ensuite helper/contrôleur/launcher/Manager réellement livrés avant AH353/AH339 Done.
