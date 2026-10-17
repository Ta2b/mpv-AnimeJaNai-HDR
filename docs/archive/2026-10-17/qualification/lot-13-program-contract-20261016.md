# Lot 13 — contrat commun des clés de programmes

Base player `267a004fbe5f22f0835d733a72fe64ca813de45b` / 3.8.0.43 ; backend référence `650c2a71f5c8bca8cfa52805e0db1c17dad8aa67`, candidat `df489209a9758149f0e8e580539ebdc50c2ae577`. AH-239 : contrat commun tous formats et application aux consommateurs existants TRT ordinaire / export flow ; adoption native des autres formats AH-240/AH-241, audit complet TRT dérivé/temporel AH-242. Frontière définie avant implémentation.

## Changement et utilité

Header C++17 identique player/backend : formats ONNX export, TensorRT, Core ML, ORT-provider, MIGraphX ; source graphe/tous poids avec schéma et SHA-256, convertisseur/version sémantique, options/environnement builder, formes/types par contenu/options ou bindings spécialisés nommés, compilateur/runtime/device selon format. Champs encadrés, bindings triés, contrats incomplets/ambiguës refusés. Voir [le contrat](../program-cache-contract.md).

Les profils min/opt/max et les types sont déjà liés par le graphe ONNX + les options complètes TRT ; une résolution de lecture compatible avec un profil dynamique ne crée pas un autre programme. L’environnement explicite du builder entre désormais dans la clé. Le convertisseur a une version sémantique explicite. Un changement de contrat utilise le schéma v3, sans supprimer/importer les caches v2. Le premier appel reconstruit/réexporte, les suivants réutilisent. Pas de modification d’arithmétique, de poids ou de précision.

## Essais ciblés arrêtés après conclusion

Même Linux RTX4070Ti, pilote 615.78.08, TensorRT11.3.0.99, SPAN/RIFE4.26 inchangés et NV12 anime 128×72. Source SPAN SHA `72246eded3aab52f8d1a71613c0a1d900734b358d1820b62eb36f1ed376e1cf4`, RIFE SHA `fd6b06538898c9a94d20f0fe55febceadbcde5ad64952240733b7275ef4c9d59`. Options builder identiques, optimisation 0/workspace 64 MiB. Aucune délégation GPU concurrente.

- Contrat portable : **16 mutations pertinentes → clés distinctes**, **11 contrats invalides → refus** ; ordre de bindings stable et séparation de champs protégée. Les politiques autres formats sont des contrôles de métadonnées, pas une qualification native de ces API.
- Flow réel : export v2 puis v3 dans le même cache, **0 octet différent** dans le graphe ; ancienne entrée intacte. Hit v3 suivant : inode/mtime inchangés, aucune réécriture. Les poids sont inchangés ; la parité d’inférence CPU de cette transformation sémantique v2 était déjà établie au lot 04 et n’est pas répétée.
- TRT réel : référence v2 active ; première demande v3 : **1 vrai builder**, ancien plan SHA intact ; demande chaude suivante : **0 builder**, inode/mtime intact, sortie exacte avec le plan reconstruit. Configure : référence chaude **0,0491 s**, migration froide **3,5290 s**, hit v3 **0,0468 s**. Mesures uniques, pas un gain FPS établi.
- Qualité : reconstructions indépendantes v2/v3, **3722 octets différents, delta max 1/255** (sélection de tactiques, déjà observée lors du lot 05). Contrôle isolant la nouvelle logique avec **les mêmes octets de plan** : **0 octet de sortie différent**, configure 0,0576 s. La copie de plan est une ablation explicite de fixture ; le produit n’importe pas automatiquement les v2.

Le candidat est directement le binaire de livraison Linux multi-SM (`75/80/86/89/90/100/120 + PTX120`), SHA `9d9e87d50753613acb6e6b2e3bb0202ad3b2283728797c8f1511a414f3e33868`. Une première compilation a précédé l’ajustement de portée des formes ; les deux unités touchées ont été recompilées avant les essais, aucune conclusion de test à reprendre.

Reproduction : `g++ -std=c++17 -O2 -Wall -Wextra -Werror tests/cache/program_identity_check.cpp -o CHECK && CHECK` ; `program_consumers_check.py SPEC --phase flow|gpu`. Specs, commandes, journaux et reçus par invocation dans `artifacts/performance/lots-20261016/lot-13/`. Pilotes à checkpoints, pas de répétition des cas concluants ; anciens contrôles de corruption/concurrence/ENOSPC inchangés réutilisés.

## Décision et livraison

Conserver comme prérequis d’intégrité et de maintenance : contrat explicite partagé, invalidation de champs pertinents et migration sûre. Coût initial de rebuild déclaré ; aucun gain FPS revendiqué. Modèles/Quality et worktrees utilisateur préservés. Compilations et publication suivies en fin de tâche sans attente inactive. Livraison **3.8.0.44**, pin `9bcc7d476e59f1bf87ed0af6c3c5a65ac420c76f`. Windows NVIDIA/AMD compile/link successful, run `38839055041`, source exacte `df489209a9758149f0e8e580539ebdc50c2ae577`. Player SDK utilisé par ce workflow `f05cf41`, qualification player/tests `8596191` ; provenance distincte. ABI9 / 24 exports préservés. Le binaire livré est exactement celui qualifié ci-dessus, aucun nouveau replay nécessaire. Core ML/ORT-provider/MIGraphX et audit global TRT restent dans leurs sous-tickets ouverts.
