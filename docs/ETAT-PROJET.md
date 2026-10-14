# État du projet et du chantier performances

## État courant — 14/10/2026 à 20 h 45 (Paris)

**[3.8.0.29 publiée sur Windows, Linux et macOS](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/releases/tag/3.8.0.29)**,
16 assets `uploaded`, source **`6fa85bbe932cbcd5725f26b0107c9142b4c7388a`**.
Les workflows indépendants ont réussi :
[Windows 38570902971](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/actions/runs/38570902971),
[Linux 38570902856](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/actions/runs/38570902856),
[macOS 38570902519](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/actions/runs/38570902519).
Depuis `6eb4971`, les releases sont construites par trois workflows distincts,
**sans jobs de tests** ; `try/**` construit sans publier. Les succès CI de
`30a3e83` cités dans l'historique appartiennent à l'ancienne organisation.

Le moteur partagé de la 3.8.0.29 inclut désormais `d639dc1` et `b3f9d5d` :
**un upscale par source, extraction du mouvement RIFE, warp des images upscalées,
réutilisation d'un RIFE médian par paire et chronologie des dessins tenus**.
Le calcul partagé du warp reste sur CPU. La branche NVIDIA privée `warp-chain`
possède cette chaîne sur CUDA ; son binaire reste installé séparément du paquet.
**NCNN/Vulkan et les binaires Windows amont n'ont pas cette nouvelle chaîne.**
La branche CUDA Graph de cette session (`f4fcd17`, documentation `0dba21a`) est
une branche différente, non fusionnée dans `warp-chain` et non livrée par le paquet.

Les modèles entraînés sont conservés, mais la nouvelle chaîne warp et la
chronologie des dessins **modifient la méthode de génération et le rythme des
images** : elles ne sont pas démontrées équivalentes pixel à pixel à l'ancienne
chaîne. Le choix `rife_engine=old` et `rife_drawings=no` reste disponible sur les
moteurs concernés. L'objectif de qualité ne doit pas être confondu avec une
preuve d'identité numérique de ces nouvelles stratégies.

Mesures consignées par l'autre session sur RTX 4070 Ti : RIFE 4.26 720p 7,9 ms
contre 1080p 26,6 ms ; ×6 ancien 60–63 ms/source, nouveau 14–15 ms/source ; ×7
Performance 14,2–15,6 ms/source. Ce sont les mesures de
[CHANTIER-RIFE-165HZ.md](CHANTIER-RIFE-165HZ.md), **pas de nouvelles mesures de
cette session ni des résultats Mac**. La lecture réelle ×7 à 165 Hz reste
non revérifiée dans ce document ; l'acceptabilité visuelle des approximations
et le coût du warp CPU sur Mac restent à établir.

Paquets actuels : TensorRT retiré de l'AppImage, outils .NET réduits, OpenVINO/ORT
Linux et composants « core » en packs, mise à jour des seuls contenus changés.
L'AppImage publiée est passée de **615 Mo en 3.8.0.23 à 206 Mo en 3.8.0.29**
(tailles décimales des assets GitHub, pas tailles d'installation).
Synchronisation d'affichage par ratio rationnel exact et scaler final allégé
au-delà de 100 i/s sont également implémentés.

Prochaines étapes documentées : warp GPU sur Mac, portage NCNN/Vulkan et Windows,
préparation anticipée des moteurs TensorRT et gestion de surcharge à haute cadence.
Aucun nouveau modèle entraîné ni remplacement du lecteur complet n'est nécessaire
pour reprendre ces chantiers. Les détails, réglages et critiques de l'autre
session sont dans [CHANTIER-RIFE-165HZ.md](CHANTIER-RIFE-165HZ.md) ; les références
immutables des premiers lots restent dans [le relais](CHANTIER-PERFORMANCE-RELAIS.md).

## Archive — checkpoint des premiers lots à la 3.8.0.23

Les sections suivantes décrivent le snapshot vérifié à 01 h 14, antérieur aux
releases 3.8.0.24–29. Leurs mentions « non livré » concernent cette époque.

État vérifié le **14 octobre 2026, 01 h 14 à Paris (13 octobre, 23 h 14 UTC)**. Ce document résume la situation
courante ; [le relais détaillé](CHANTIER-PERFORMANCE-RELAIS.md) conserve les
commandes, références, preuves et étapes historiques.

## Livré : 3.8.0.23 sur les trois plateformes

La [release 3.8.0.23](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/releases/tag/3.8.0.23)
contient **15 assets au statut `uploaded`** : Setup, archive complète et overlay
Windows ; portable, AppImage et overlay Linux ; application, SHA-256, notice et
benchmark Mac ; deux manifests, deux index de packs et SHA256SUMS.
Source de livraison : **`aab89ba7ded15d81dc279a83cea2cb39440f6e90`** sur `release`.
[Deploy 38479416318](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/actions/runs/38479416318)
et [macOS 38479416046](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/actions/runs/38479416046)
sont terminés avec succès, publication comprise.

Les composants lourds sont réutilisés : les **10 entrées de chacun des deux
index `packs*.json`** possèdent une URL vers leurs assets antérieurs, notamment
la 3.8.0.9. Leur absence dans les 15 assets de la nouvelle release est normale.
Ces anciennes releases doivent être conservées. Le téléchargement/installation
physique de chaque composant sur une installation neuve n'a pas été répété ici.

## Ce qui a été fait et où le trouver

| Lot | Code et statut | Preuves et limites |
|---|---|---|
| NCNN/Vulkan | Inclus dans la 3.8.0.23 : exact par défaut, similarité explicite, parcours de coupe évités lorsque inutiles, dépendances de cache CI corrigées | Parité locale et lecture mpv vérifiées avant l'arrêt des tests ; CI Vulkan logiciel réussie. Gain ×1,142 limité au cas RIFE après ×4, coupes désactivées, RTX 4070 Ti ; aucun gain universel annoncé. |
| Préparation CPU RIFE / workers | Commit `089b6b5`, inclus dans la 3.8.0.23 : workers persistants, entrée ORT et timestep réutilisés, scratch FP16 conservé, table FP16 sûre entre threads | 17 cas / 516 images par variante, quatre variantes, identiques à l'octet sur provider CPU avant l'arrêt des tests. Aucun gain chiffré pour ce lot. |
| Mesure Mac | Inclus dans la 3.8.0.23 : mesures par intervalle source, échauffement, médiane/p95/max, phases RIFE, classement indépendant de la locale, protection temporaire contre la veille | Le benchmark utilisateur 3.8.0.21 a été perturbé par un verrouillage ; ses classements restent provisoires. Les mesures du runner virtuel ne prédisent pas le débit d'un vrai Mac. |
| Suite SVP, moteur partagé | **`30a3e83dfd3c7c30dd4874f01d71509023acf1a5` sur `hdr-3.8`, pas dans la release** : décision par paire et sortie RIFE préallouée | Compilation Release locale et CI Mac/Linux/Windows réussies. Suite locale complète de parité non répétée et aucun gain mesuré pour ces nouvelles modifications. |
| Suite SVP, NVIDIA | **`f4fcd17df4686c9978e49359a12a5c6d53128f72`**, branche isolée `perf-rife-cuda-graphs-20261014` du dépôt `Ta2b/animejanai-inference-rtx` : CUDA Graph RIFE, timestep réutilisé, score de coupe épinglé | Unité C++ compilée localement avec headers TensorRT 10.9 et 11.3.0.99 / CUDA 12.8. Build CUDA complet configuré en CI, résultat non confirmé : API du dépôt non accessible. Bibliothèque non intégrée au paquet, compilation Windows et validation GPU restantes. |

CI du moteur partagé à `30a3e83` :
[macOS 38481912353](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/actions/runs/38481912353)
et [Platform checks 38481912257](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/actions/runs/38481912257)
**terminés avec succès**, incluant moteur/application Mac et tous les jobs
plateforme/ORT/Vulkan. Ces contrôles existants de CI ne constituent pas une
mesure de gain ni une validation de tous les GPU physiques.

## Évolution constatée dans les documents

- **12 octobre : rendre le projet portable et publiable.** Banques Linux,
  lecteur Wayland, NCNN/Vulkan SPAN + RIFE, Manager et paquets Windows/Linux.
  Les premiers blocages portent sur les dépendances, l'AppImage et la conservation
  des réglages ; la 3.8.0.9 est le jalon commun documenté.
- **13 octobre : élargir et exploiter les moteurs Apple.** Premier retour réel
  du M4 Pro, puis Core ML natif et Metal, partage de tuiles GPU/NPU/CPU, caches
  d'images et traitement en avance. Le chantier devient celui de l'orchestration
  des mêmes modèles, avec un retour utilisateur favorable aux cibles GPU+NPU.
- **13–14 octobre : fiabiliser les optimisations et les mesures.** Caches RIFE,
  reprise exacte NCNN, preuves de pixels/PTS, workers CPU persistants et préparation
  réutilisée. Les longues pauses liées possiblement au verrouillage et les
  colonnes de mesure ambiguës sont identifiées ; la 3.8.0.23 livre ce jalon.
- **14 octobre, après la release : réduire le coût de chaque inférence.** Décision
  par paire et sortie ORT préallouée, puis réseau TensorRT capturé et timestep
  conservé sur une branche isolée. Le partage de tensors GPU et les contextes
  concurrents sont encore des prochains chantiers, pas des fonctions livrées.

La documentation a ainsi évolué d'un journal de portage vers un relais de
performance avec commits, binaires de référence, empreintes, conditions de mesure
et limites de validation. Le point de maturité à conserver est cette séparation :
compilation, bon fonctionnement en CI, fidélité numérique, performance mesurée
et publication sont cinq preuves différentes. Les résultats d'un ancien lot ou
le débit d'un autre GPU ne valident pas automatiquement le code suivant.

## Contraintes et constat SVP

L'utilisateur a demandé de **garder les modèles et la qualité**, puis
**d'arrêter les tests locaux et de coder/committer/pousser**. Aucun nouveau
benchmark, test de parité ou essai de lecture local après cette consigne.
Les compilations et les contrôles habituels de CI ont continué. Les poids,
types de calcul et règles sensibles ne sont pas modifiés par les derniers lots.
Une compilation seule ne démontre pas la fidélité d'une nouvelle exécution.

Son ancien cas : RTX 2070 Super, **RIFE 4.26 / TensorRT dans SVP**, source 1080p,
AnimeJaNai ×2, écran 1080p. La résolution effectivement reçue par RIFE et l'ordre
des filtres restent inconnus. Une réduction à l'écran avant RIFE est plausible,
mais non confirmée. Aucun changement automatique de résolution ou d'ordre adopté.

Sur Mac, les trois moteurs d'upscale sont Core ML natif, Metal et ORT/Core ML ;
**RIFE passe toujours par ORT/Core ML**. RIFE natif Apple, chaîne SPAN/RIFE
résidente sur GPU et contextes GPU concurrents restent des chantiers à faire.
Sur NVIDIA, la nouvelle capture couvre le réseau RIFE, **pas la décision de
coupe CPU**, dont la synchronisation reste présente. Le paquet Windows/Linux
consomme toujours la bibliothèque amont `AjiVersion=v0.11.1` ; le fork NVIDIA
expérimental ne remplace pas cette dépendance livrée.

## Pour reprendre sans perdre les preuves

1. Lire [le relais](CHANTIER-PERFORMANCE-RELAIS.md), puis [les pistes classées](OPTIMISATIONS-MOTEURS.md).
2. Distinguer le commit publié `aab89ba` et le moteur partagé suivant `30a3e83`.
   Les prochains commits documentaires ne changent pas les binaires publiés.
3. Conserver `artifacts/performance/phase-*`, `resume-ncnn`, `rife-cpu-prep`,
   `svp-rife-shared` et `svp-rife-trt`. Les références historiques sont immuables.
   Les checkpoints locaux sont utiles au relais, mais ignorés par Git ; les
   commits source et rapports décrits dans le relais permettent la reconstruction.
4. Reprendre le backend dans son worktree `artifacts/performance/svp-rife-trt/source`
   ou depuis sa branche distante. L'arbre original du dépôt voisin contient les
   modifications d'une autre session et n'a pas été écrasé.
5. Confirmer le build complet NVIDIA et intégrer ses binaires avec une référence
   immuable avant une future publication. Préparer ensuite l'API par paire et
   les buffers GPU partagés. Toute nouvelle mesure locale doit respecter la
   consigne d'arrêt encore active.
