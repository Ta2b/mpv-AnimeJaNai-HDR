# Lot 09 — identités et vues Fast CUDA

Backend de référence `d9d0a941d62f1dfcb3ed2f87018c4871aea12be7` (pin binaire `9eee3504d82387035e4908909ca9621733fed68c`), candidat `3f6f60fa58b5ed649bb94c11030d8e354a6d3fc0`. Base player `f05cf41c1448597a1929f7a8be318572a29c5ded` / 3.8.0.39. Travail effectué dans des worktrees isolés ; backend utilisateur d’origine intact.

## Changement et utilité

Les pointeurs décrivent le stockage, jamais l’identité des pixels. Les caches Fast (motion, endpoints et promotion B→A) exigent désormais des IDs explicites non nuls et la vue entière : dimensions, format, matrice, range, siting, trois plans, trois strides et stream CUDA. Sans extension ou avec IDs nuls, le backend recalcule. `AJI_RIFE_PAIR_CACHE=0` désactive aussi ces réutilisations Fast. Le caller doit garder les pixels immuables pour un ID donné.

Le reset invalide IDs/vues, préparations, endpoints et état de décision Fast. La reconfiguration détruit ces états avec les plans/engines auxquels ils appartiennent. La transmission de l’intermédiaire Fast est une réservation pour le prochain `aji_infer`, avec vue/stream identiques : elle est consommée même si la validation échoue. Une vue ou un stream changé est refusé, au lieu de lire le tampon intermédiaire non écrit. Les appels sérialisés changeant de stream ordonnent les buffers partagés par un événement ; le chemin habituel à stream constant n’enregistre pas d’événement supplémentaire. Les streams doivent rester vivants jusqu’à la fin de leur travail.

Aucun calcul Fast, modèle ou approximation Fast n’est changé. La référence Quality est conservée. Ce lot corrige la fidélité des réutilisations, sans promesse de FPS.

## Essais courts

Machine : Linux x86-64, RTX4070Ti, pilote 615.78.08, TensorRT 11.3.0.99 / CUDA 13.4. Entrées anime identiques 128×72 NV12, strides avec padding ; RIFE4.26 et SPAN Performance identiques, facteur Fast 4×, dessins désactivés, seuil scène 1. Les plans TensorRT sont les mêmes pour les deux bibliothèques et pour le recalcul frais : aucun écart de reconstruction indépendante ne brouille la comparaison. Le recalcul utilise `aji_temporal_reset` avant la même requête.

| Cas | Octets divergents avant / après, contre recalcul frais | Delta max avant |
|---|---:|---:|
| Paire inchangée | 0 / 0 | 0 |
| Range changé, mêmes adresses | 51 407 / 0 | 193 |
| Matrice changée, mêmes adresses | 41 544 / 0 | 7 |
| Promotion B→A avec range changé | 43 959 / 0 | 21 |
| Endpoint avec range changé | 52 279 / 0 | 22 |
| Pixels recyclés, ancien client sans IDs | 52 368 / 0 | 201 |
| Changement de stream | 0 / 0 | 0 |
| Reset puis stockage recyclé | 0 / 0 | 0 |
| Promotion B→A valide | 0 / 0 | 0 |
| Erreur de validation puis nouvel infer | 54 566 / 0 | 197 |
| Reconfigure puis stockage recyclé | 0 / 0 | 0 |

La vue changée de l’intermédiaire était acceptée silencieusement avant ; elle retourne désormais `AJI_ERR` avec diagnostic. Les sorties fraîches avant/après sont toutes identiques. La sortie Quality de contrôle est également identique entre références/candidat et calcul frais. Le contrat C++ portable vérifie l’invalidation sur chacun des 12 champs de vue, l’ID, le stream et l’état vidé. Les essais concluants ne sont pas rejoués.

Pilote : `tests/inference/fast_views_probe.py SPEC.json`. Contrat backend : `g++ -std=c++17 -I include -I src tests/frame_identity_check.cpp -o CHECK && CHECK`. Six specs/logs/JSON/NPZ dans `artifacts/performance/lots-20261016/lot-09/` : `before`, `after`, `before-quality`, `after-quality`, `before-remaining`, `after-remaining`. Le complément `remaining_only` a exercé seulement les questions restées ouvertes, sans rejouer les premiers cas.

La préparation des plans du témoin dure 18,4311 s (construction réelle RIFE full/motion, optimisation builder 0 et workspace 64 MiB via wrapper isolé), contre 0,5449 s au chargement du candidat : ce n’est pas une mesure de performance avant/après. Le premier groupe d’inférences dure environ 0,0481 / 0,0531 s, avec des recalculs nécessaires supplémentaires après correction ; **aucun gain FPS établi**. Les temps courts ne servent pas de seuil d’acceptation.

Client Linux réel : même mpv local, décodage NVDEC, entrée lossless de quatre sources, EOF drainé, Fast 4×, même configuration/plans. **13 hashes et PTS identiques** entre référence et candidat **multi-SM de livraison** ; aucun diagnostic de transmission invalide. Processus 1,0156 / 1,0153 s : pas de gain mesurable. Commandes exactes, environnements et temps dans `player-runs.json` ; sorties `*-player.framehash`, logs/stats conservés. Ce contrôle qualifie la compatibilité du client et le binaire final, sans répéter les cas adversariaux déjà concluants.

## Décision et limites

Conserver : six comportements incorrects reproduits avant sont supprimés, et les chemins valides/Quality restent identiques sur ces entrées. Les invalidations remplacent un résultat périmé par les calculs nécessaires. Aucune revendication de stabilité sur épisode, HDR physique, toutes résolutions ou tout matériel. Le cas multi-stream passe avant/après ; aucune course universelle de l’ancien code n’est déduite de cette sortie, l’ordre explicite protège le contrat.

Build Linux multi-SM 75/80/86/89/90/100/120 + PTX120 effectué dans l’image `aji-rtx-build`. Windows : NVIDIA et AMD success, build `38822986680`, compilation/linking seulement, sans qualification GPU Windows locale. Pin binaire `a2908cf4d3166011c9b853be9f480a52b7a7867f`, SHA-256 du backend Linux `142e6ea3245b797d38f90d698cfcc3488d53b5dae9625aeec640f63f57a65d95` ; 24 exports ABI inchangés. Les clients Windows et leur négociation restent un périmètre distinct. Publication : **3.8.0.40**, SHA source/pin et état des assets à consigner lors de la livraison.
