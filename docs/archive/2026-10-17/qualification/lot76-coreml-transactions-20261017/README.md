# AH364 — preuves ciblées du cache CoreML

Candidate runtime ab2d0ea1b60bf165a370293da38461c461b9218f. Qualification native macOS **réussie** : run39023454995, macOS15.7.9/24G830/arm64, vrai CoreMLCPU256. Livraison .98 à vérifier avant Done ; aucun FPS/GPU/ANE ou port des autres providers revendiqué.

- Linux : compilation C++17 O2 Wall/Wextra/Werror du vrai protocole ; PASS commit/record strict, recovery SIGKILL réel, marqueurs possédés, inconnus/autreskeys/générations conservés, stale-retire et readonly. Fixture privée `lot-76-coreml-protocol-proof-20261017` ; aucune écriture dans le cache utilisateur.
- Snapshot neutre d’un vrai modèle Sharp1 Performance livré : tag identique `v2-694905b1555494bdf5ff59e357b54bb05ce53d7800d8ac44ebff0b43965f63b7`. Refus avant écriture de `../outside`, `/tmp/outside`, `Data/../outside`. Fixture `lot-76-coreml-snapshot-proof-20261017`.
- AH244 poids/manifeste et AH240 clé de programme déjà concluants, réutilisés. Aucun replay ni nouvelle conversion. Configuration CoreML et calcul d’image inchangés ; la qualification native vérifie la référence RGB18df… et les nouvelles propriétés de publication.

Tests : `tests/cache/coreml_transaction_check.cpp`, `tests/apple/coreml_transaction_native.py`. Voir le [guide précis](../../reprise/20261017/AH-364.md).

Native : demandes réellement chevauchées→une compilation, deux sorties exactes à18df… ; SIGKILL après marquage du staging puis reprise exacte ; artefact compilé vide→erreur native, seul commit retiré, génération conservée, reconstruction exacte ; hit complet readonly exact sans compilation. [Reçu](receipt.json), [machine](machine.txt), [protocole natif](protocol.log), [erreur contrôlée](invalid-artifact.log). Le key p3 reste73d559a2…, identique AH240. Aucun autre essai nécessaire sur ces sources.

Deux anciens utilitaires de qualification ont été adaptés à la découverte des générations et au diagnostic de retrait (sans replay de leurs anciens cas). Leur validation de syntaxe et revue de chemins suffisent pour ce raccord de fixtures ; les nouveaux cas natifs utilisent le protocole réel.
