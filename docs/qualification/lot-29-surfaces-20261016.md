# Lot 29 — surfaces versionnées et premier adaptateur CPU

AH-278 sous AH-49 ; intégrations natives dans AH-279. Base3.8.0.60 `afbd22a89ea3a7665cb8a3150699c3fa135bb465`, source d'implémentation `6fb3e49cc7ea587d801095a3677bf6a9927b93d2`. Worktree isolé ; fichiers utilisateur, modèles et référence Quality préservés.

## Interface livrée et limites négociées

[surface.h](../../native/common/surface.h) définit un contrat C en processus, indépendant de l'ABI1 RGB24 et de l'ABI9 CUDA/D3D11 : version/taille, ressource opaque et device/context/UUID/LUID, format, géométrie et vue recadrée, plans/strides/offsets/extents, matrice/primaires/transfert/plage/siting/profondeur/quantification/dither, orientation, PTS/durée/timebase, ID/génération et ownership. Le descripteur représente aussi CUDA/HIP/D3D11/D3D12/Metal/Vulkan/DMABUF et plusieurs formats entiers/flottants ; leur présence dans un enum ne vaut pas prise en charge.

Les deux symboles optionnels `aji_surface_query_v1`/`aji_surface_process_v1` sont intégrés au module partagé. Le premier adaptateur négocie seulement **Linux x86-64 CPU, ressource hôte, un plan RGB8 SDR, strides positifs, vues recadrées**. Query après configure réussi : masque ressource/format, dimensions maximales16384, ownership et complétion synchrones. Autre provider/OS/version/format refusé explicitement ; aucune conversion silencieuse enRGB24. ABI1/9 et tous les symboles précédents restent disponibles.

La vue active est lue/écrite directement dans le buffer et ses strides, sans copie de recadrage préalable. Ses dimensions doivent correspondre aux dimensions configurées et au plan de sortie. Les allocations/logical rows/offsets, bornes et adresses sont validées sans arithmétique débordante ; l'appelant reste responsable de fournir des adresses réellement valides. Les vues source/destination qui se recouvrent sont refusées.

L'encodage est explicite : RGB full-range8bits, transfert709/sRGB/1886, quantificationRGB8 de référence, pas de dither ajouté en sortie. PQ/HLG, linéaire non qualifié, haute profondeur et ressources natives restent refusés sur cet adaptateur. Primaires et orientation sont transportées et doivent être cohérentes dans la paire/sortie ; le moteur ne convertit ni gamut ni orientation. Les descripteurs, PTS/durée/timebase et tags sont conservés byte à byte. Le client fournit son PTS de sortie interpolé ; aucun timestamp inventé ou recalculé ici.

Avec callbacks, chaque descripteur fourni est retenu une fois puis libéré après tout le travail de pixels, y compris sur erreur moteur. Sans callbacks, le buffer est emprunté jusqu'au retour. Aucun pointeur/owner de descripteur retenu après l'appel ; les caches existants possèdent leurs pixels. Callbacks sans exception/échec/réentrée ; appels/configure sérialisés par contexte. Fences et Submit/Complete asynchrones restent AH-50. Les anciens hints de lookahead empruntés ne traversent pas ce contrat, qui ne dispose pas encore de descripteurs de sources futures.

Changement de couleur, vue, offset, stride ou génération : invalidation des résultats de sources/tuiles/décisions dérivées et des IDs de confiance. Des layouts différents entre les deux sources utilisent la comparaison exacte de pixels. Passer du nouveau chemin à l'ancienne ABI invalide une fois les résultats susceptibles d'être associés à une autre vue. Une tentative consomme également le hint d'identité legacy à usage unique ; pas de fuite vers l'appel suivant. Configure réinitialise le contrat.

## Client et qualification ciblée

Client C autonome réellement compilé et exécuté [surface_borrowed_check.c](../../tests/inference/surface_borrowed_check.c) : négociation puis buffers empruntés sur le nouveau module ; mêmes buffers sur un ancien module sans symboles surfaces, repli explicite ABI1. Deux copies exactes sans modèle. [surface_cpu_check.py](../../tests/inference/surface_cpu_check.py) consomme le même C ABI via ctypes ; contrôle indépendant du layout avec un programme C compilé depuis l'en-tête public : surface344octets, caps48, offsetscolor112/planes192/owner320/PTS144.

Contrôles courts sans modèle : copie exacte d'une ROI4×2 dans deux allocations plus grandes avec offsets/strides différents, bords/sentinelles intacts et descripteurs inchangés ; callbacks retain/release équilibrés. Versions/tailles/caps non supportées laissent la sortie de négociation intacte. Extent trop court, stride négatif, crop hors limites, adresse débordante, mauvais timing/callbacks, paire de couleurs/orientations/générations différentes, NaN et overlap refusés avant écriture/acquisition. RessourcesCUDA, formatF16, HDR ou dither ajouté refusés explicitement, sans les déréférencer/convertir.

| Chaîne réelle, mêmes entrées/modèles/options/machine | Référence valide réutilisée | Résultat |
|---|---|---|
| Quality CPU RIFE4.26+SPAN,128×72 | Lot24, `integrated-quality/after` | 8 sorties RGB24 exactes,0 octet différent |
| Fast CPU,256×72, SPAN tuilé2×1/deux exécuteurs | Lot25, `pruned-fast/after` | 8 sorties exactes,0 octet différent |

Pas de nouvel essai avant : les références déjà acquises sont réutilisées. Dans chaque contexte, trois contrôles supplémentaires portent précisément sur les nouvelles gardes : réutiliser les IDs de la dernière paire avec couleur/pixels changés doit reproduire l'autre paire de référence ; changer la ROI à mêmes ID/stride doit fournir la bonne source ; revenir à l'ancienne ABI avec ID recyclé doit aussi fournir la bonne source. Ces six sorties sont exactes. La reconfiguration comprise dans les huit sorties de base reste exacte.

Une erreur ORT injectée après acquisition des références mais avant calcul vérifie la libération de tous les owners et le statut d'erreur moteur ; aucune nouvelle inférence réussie répétée pour ce contrôle. Sur erreur moteur, le client doit écarter la destination ; la garantie «avant écriture» concerne les erreurs de validation, pas tout échec pouvant survenir au milieu d'une chaîne.

Dernière revue : des dimensions conservées après un configure échoué pouvaient donner une apparence de disponibilité. Ajout d'un état de configure réussi, requis pour les deux symboles. Contrôle ciblé sur binaire final : configure invalide désactive query/process sans écrire les buffers ; configure valide restaure les capacités. Ce changement ne modifie pas le traitement d'un configure réussi ; les essais neuronaux conclusifs ne sont pas rejoués.

Build CMake Release réussi ; en-tête/client C compilés, syntaxe Python et diff-check réussis. Ensembles d'exports comparés au lot28 : tous conservés, deux symboles optionnels ajoutés. Pas de gainFPS ou mémoire globale annoncé : le bénéfice est un contrat exploitable, une vue sans staging de recadrage et un premier consommateur sûr, prérequis des raccords natifs.

Artefacts locaux `artifacts/performance/lots-20261016/lot-29/` : `contract/summary.json`, `quality/summary.json`, `fast/summary.json`, sortiesNPZ, layoutC/JSON, `borrowed-modern.json`, `borrowed-legacy.json`, `failed-configure.json`, specs et logs. Commandes : compiler/exécuter `surface_layout_check.c`, `surface_borrowed_check.c MODULE [--failed-configure]`, puis `surface_cpu_check.py contract.spec.json|quality.spec.json|fast.spec.json` avec la sonde ORT test-only pour l'erreur injectée.

## Décision et livraison

Conserver comme contrat et premier adaptateur complet, avec ces limites explicites. Release **3.8.0.61**, pins GPU/Manager conservés depuis .60. AH-278 Done après publication vérifiée ; parent AH-49/AH-279 ouverts. Le lecteur mpv utilise encore son pont ABI1 : adoption par les clients et fidélité couleur complète dans AH-275, interop GPU dans AH-279, complétion asynchrone dans AH-50. Aucun de ces périmètres n'est fermé par cette première API.
