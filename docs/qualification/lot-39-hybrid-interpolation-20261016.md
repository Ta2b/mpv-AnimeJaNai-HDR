# Chaîne RIFE×2 → FRUC×2 : première comparaison

[AH-300](https://tatoub.atlassian.net/browse/AH-300), sous
[AH-297](https://tatoub.atlassian.net/browse/AH-297). Demande utilisateur :
cumuler et choisir les technologies d'interpolation dans le Manager ; comparer
l'usage d'un deuxième étage rapide après un modèle plus lourd.

FRUC utilise déjà NVOFA et ajoute la reconstruction CUDA :
[guide NVIDIA](https://docs.nvidia.com/video-technologies/optical-flow-sdk/nvfruc-programming-guide/index.html).
Un champ Optical Flow seul demande un synthétiseur supplémentaire. Cet essai
compare deux chaînes de synthèse ; il ne mesure pas une reconstruction maison
alimentée par le flow matériel brut.

## Essai ciblé acquis

Mêmes six sources720p, machine, poids RIFE4.26 et plan9c85de76 du lot38.
Les cinq médianes RIFE Quality déjà concluantes sont **réutilisées**, sans
nouvelle inférence. Elles donnent onze sources pour FRUC à47.95204795fps.
Dix nouveaux quarts de phase FRUC sont comparés à dix prédictions RIFE direct
t=0.25/0.75. Pas de compilation concurrente ni autre ablation rejouée.

| Couple | Deux quarts RIFE direct, ms | Deux quarts FRUC après RIFE, ms |
|---|---:|---:|
| 0, avec premier appel froid | 108.043 | 20.808 |
| 1 | 47.937 | 15.806 |
| 2 | 44.141 | 15.810 |
| 3, déplacement inspecté | 48.574 | 19.066 |
| 4 | 44.267 | 14.668 |

Le couple3 montre une économie locale d'environ29.5ms pour les deux images
supplémentaires. Le médian RIFE est commun et ne doit pas être compté deux fois.
Les coûts FRUC de ce nouvel essai (6.72–10.83ms/appel) diffèrent du cas standalone
du lot38 ; ne pas lui substituer ses anciens2–5.6ms. Ces temps par étage ne
prouvent ni une cadence du lecteur ni un coût complet NVDEC→rendu. Staging
CPU/RGBA du prototype, ressources, mémoire et futures conversions GPU restent
à remplacer/qualifier dans AH-296/AH-301. Le client natif signale aussi le coût
potentiel de son stream CUDA par défaut ; aucune latence universelle revendiquée.

FRUC : dix intermédiaires, zéro répétition signalée, cleanup réussi. Les crops
aux quarts des deux déplacements montrent encore des dentelures et défauts de
bouche/occultation dans l'hybride face au RIFE direct. **Conserver cette voie
comme Fast expérimentale avec compromis explicite ; garder la référence
Quality.** Aucun jugement perceptuel universel ni validation humaine en lecture
fluide. Ce résultat suffit à engager l'intégration cumulable ; pas de nouvelle
mesure de ces cas sans changement affectant leur résultat.

## Cadence, provenance et EOF

Planning rationnel validé : source24000/1001fps, deux facteurs2, sortie nominale
96000/1001fps, timebase1001/96000. Vingt-et-une images sur cinq intervalles :
sources aux PTS0,4,…20 ; médianes RIFE aux PTS2mod4 ; quarts FRUC aux PTSimpairs.
Sources/médianes **exactement identiques** dans les deux séquences composées.
La dernière source garde4ticks de durée : durée totale exactement6/(24000/1001).
Aucun futur fictif n'est interpolé pour remplir la fin. Les timestamps flottants
du SDK ont un décalage d'époque constant ; les PTS média viennent du planning
rationnel, pas d'un arrondi du JSON de diagnostic du SDK.

Deux raws RGB24 de comparaison, chacun21images, avec durée définie par le
manifest de planning (ce ne sont pas des vidéos CFR autonomes) :

- RIFE×4 : SHA256 `4908c02dbd63f0b802336049d0202731d07b3d59450531bd5a86c7cf258e0731`.
- Hybride : SHA256 `1fc6dc62b22f2ea7e01d9e1c0b1f7e945d1f4b266c41a63ea6fcf6694a59d3b0`.

## Reproduction et suite

[Client de composition](../../tests/inference/vfi_cascade_check.py),
[client natif RIFE](../../tests/inference/vfi_candidate_probe.py),
[client FRUC](../../tests/inference/fruc_probe.cpp).
Spec de composition : `rife_spec,median_dir,output,source_fps:[24000,1001]`.
`python vfi_cascade_check.py SPEC prepare` réutilise les médianes et écrit les
sourcesRGBA et la spec RIFE de quarts ; exécuter les deux clients d'inférence
sur ces nouvelles entrées, puis `python vfi_cascade_check.py SPEC verify`.
Le dernier contrôle lit les reçus et compose les artefacts sans rejouer le GPU.

Artefacts privés `artifacts/performance/lots-20261016/lot-39/hybrid/` :
specs/reçus, timeline, raws, crops et logs. Le reçu de composition confirme
provenance partagée, comptes et durée exacte. Le champ temps global du client
RIFE donne2.432s pour sa nouvelle exécution, distinct du coût de ses prédictions.

Raccord GPU borné AH-296 et runtime ordonné AH-301 restent à implémenter ;
éditeur Manager AH-302 préparé en worktree isolé, interface non encore livrée.
AH-300 reste In Progress jusqu'à rapport/client livrés par release vérifiée.
