# Lot 02 — AH-11 / REF-01, 15 octobre 2026

Version prévue : **3.8.0.33** ; parent `454d034214ad7daf18c042dc8b0224d785f6d06a` (lot livraison .32). Implémentation dans le même worktree isolé. Pins modèles, backend et Manager inchangés. Nouveau helper macOS, export CLI partagé et entrée Lua à la demande. Documentation : [REFERENCE-EXPORT](../REFERENCE-EXPORT.md).

## Essais nécessaires

- Compilation .NET 10, publication Linux self-contained : succès sans avertissement.
- `tests/platform/reference_check.py` sur l’exécutable publié : IPC strictement en lecture ; empreinte modifiée après remplacement des poids sous le même nom, taille et mtime ; modification de filtre détectée ; package lié et cycle traités ; rapport existant préservé ; vidéo absente refusée. Tous concluants.
- `tests/platform/reference_real.py` : lecteur réel 3.8.0.31, même clip anime de 8 sources et même configuration Fast x5/2 que la qualification précédente, NVDEC/Vulkan. Un seul instant en pause : export CLI puis entrée Lua livrée. Avant/après, même PNG 16 bits SHA-256 `7de981b6b550dc724f14eafe82155e232efc5c475788d8f3de3d8a98ba586495`, PTS=0. 29 fichiers empreintés, chaque hash contrôlé indépendamment par Python. Temps CLI 1,6147 s ; coût ponctuel, pas une mesure de FPS. Source/sortie et paramètres du filtre réellement observés. Succès CLI et Lua, aucune perte pixel/PTS constatée.
- Syntaxes Lua/Bash valides, workflow macOS vérifié par actionlint (seule exclusion queue documentée au lot 01).

Artefacts locaux dans `artifacts/performance/lots-20261015/lot-02` du worktree utilisateur : `contract.json`, `real.json`, `reference.json`, captures avant/après, `runtime.stats`, commandes et log lecteur. Tests conclusifs non prolongés.

## Utilité et limites

Avant : les pièces étaient dispersées, sans export avec empreintes. Après : un rapport local rassemble un état de chaîne observable et l’identité des octets sur disque, sans déduire la fidélité d’un nom Quality. Aucun gain FPS attendu ; conservation justifiée par la reproductibilité des prochains essais. Aucun changement de calcul d’image, de modèle ou de profil.

Qualification **partielle de REF-01**, explicitement annoncée par le JSON : inventaire non assimilé aux modèles exécutés ; stats de fraîcheur inconnue ; poids déjà chargés, précision effective/placement et dimensions intermédiaires non prouvés ; média non empreinté ; état lu séquentiellement. Windows et macOS : compilation/publication CI à suivre, transport nommé et runtime Apple non testés sur cette machine. L’ajout du helper augmente le paquet macOS ; aucune activation de calcul périodique.

Jira AH-11 non clos. Commentaire préparé, non envoyé (connecteur absent). Le lot 03 poursuit CAC-02 pendant les builds, avec une identité de package comprenant les vrais poids.
