# Quality / Fast et optimisation TensorRT-CUDA — 15 octobre 2026

## Mandat et règles

Renommer Original en Quality et New en Fast. Conserver les modèles actuels.
Quality conserve chaque prédiction complète RIFE et l'upscale de chaque image ;
aucune extrapolation de mouvement, réutilisation approximative ou modification
des dessins tenus. Fast bénéficie des mêmes optimisations d'exécution et garde
les raccourcis de reconstruction/réutilisation temporelle. La conservation de
l'algorithme est une exigence théorique, pas une preuve d'identité numérique.
Aucun test, benchmark ni inférence locale : instruction utilisateur toujours
active. Seuls compilation/liaison et contrôles statiques sont autorisés.

## Dépôts à reprendre

- Lecteur : `/home/ta2b/Documents/mpv-AnimeJaNai-HDR`, branche
  `perf/specialized-gpu-20261014`, base `5933526` après release 3.8.0.30.
- Backend : `/home/ta2b/.animejanai-tools/work/gpu-specialized`, branche
  `perf-specialized-gpu-20261014`, base `c7bdb1a`.
- Manager : `/home/ta2b/.animejanai-tools/work/manager-specialized`, même branche,
  base `fade3c7`. Ne pas modifier le worktree backend utilisateur d'origine.
- Dernière release livrée : 3.8.0.30. Les modifications de ce document ne sont
  pas encore intégrées dans ses binaires.

## Avancement exact — premier lot codé

- Manager : Quality/Fast et valeurs `quality`/`fast`, lecture des aliases old/new
  et des sauvegardes sérialisées ; Fast reste le défaut antérieur. Retiming
  grisé en Quality, ses valeurs préexistantes sont ignorées par les moteurs.
- Quality CUDA : graphe RGB complet par instant, pas de warp des sources ni de
  skip de dessins ressemblants, même si le sidecar RTX demandait ce skip.
- Quality partagé Apple/ORT/AMD : pas de warp, retiming, reuse approximatif ni
  boost adaptatif ; chaque intermédiaire conserve son passage RIFE complet.
- CUDA commun : score de coupe lu en mémoire pinned et attendu par événement,
  préparation des sources soumise avant l'attente ; formule/seuil conservés.
- Cache exact : nouvelle extension optionnelle `aji_rife_begin_pair(c,a_id,b_id)`.
  Le lecteur fournit des IDs uniques non réinitialisés sur seek, y compris
  pour les images détenues dans le cache des dessins tenus. Métadonnées/strides/stream vérifiés. Même paire : on garde
  préparation et décision de coupe ; B devient A : copie RGB FP16 déjà convertie.
  Ancien lecteur : cache désactivé, exécution classique maintenue.
- Filtre Linux : dépendance NVDEC explicite avant RIFE sans pre-resize.
  Intermédiaires/upscales soumis en rafale bornée à huit sorties,
  attente du dernier ticket avant présentation ; références d'entrée conservées
  jusqu'à complétion, drainage des chemins d'erreur. Plus d'attente entre un
  intermédiaire RIFE et son upscale consommateur sur le même stream.
- CUDA classique : capture prédiction RGB + post-conversion existante ; cropping
  vers la sortie courante reste vivant. Première sortie de warmup utilisée,
  pas d'inférence doublée. Repli sur réseau complet si capture impossible.
- Kernels RIFE 4:4:4, NV12 et P010 : padding virtuel studio-black et conversion
  RGB FP16 sans copie préalable de l'image paddée. En 4:2:0 les deux passes
  chroma, poids, ordre d'accumulation et matrice sont conservés ; géométrie
  impaire = repli historique. Moins de copies et de lectures de tampons paddés.
- Fast : scalaire de mouvement lu avant les upscales, et réseau de mouvement
  dans un stream non bloquant indépendant ; événement d'entrée et attente CPU
  de fin protègent le partage. Upscale et mouvement peuvent se chevaucher.
  Les approximations médianes, masques et retiming restent réservés à Fast.
- DML/AMD Windows gardent leur exécution et un stub de l'extension optionnelle.
- Le cache Fast utilise aussi les IDs explicites, évite la réutilisation d'un
  pointeur recyclé, et promeut B même si un facteur fractionnaire ne l'a pas émis.

## Publication 3.8.0.31 en cours

Le commit de livraison est `bf4dc2b` (attente NVDEC avant lecture RIFE directe).
Premier lancement `58f2e3d` remplacé avant publication pour inclure ce correctif.
Windows et macOS ont terminé avec succès, leurs dix assets sont `uploaded`.
Linux : moteurs réussis, compilation du lecteur natif en cours ; pas encore
publié. Ne pas annoncer la livraison Linux avant les résultats et les assets :

- [Windows 38670981195](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/actions/runs/38670981195).
- [Linux 38670981419](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/actions/runs/38670981419).
- [macOS 38670981300](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/actions/runs/38670981300).
 Binaires immuables :
`7c4ab72707fab87e77aa4778514f5aa723721015`, pin `gpu-binaries-source-ref.txt`.
Référence privée de résultat Windows :
`build-status/specialized-1468be6f24cac537407283d434bd5d542d642cf3-1`.

## Références du lot en cours

- Lecteur / filtre / packaging : `2600de1`, puis identités des dessins `8e7d767`, drainage borné `04d2a78`.
- Backend : branche `perf-specialized-gpu-20261014`, HEAD `1468be6f24cac537407283d434bd5d542d642cf3` ; CI Windows `38670166267`, AMD/NVIDIA **success**.
- Manager : `b3a8c1fcfd7b5acc846c0fb6ecba2fea793ef740`, paquets immuables publiés.
- Build AMD Linux : `38669623563`, succès.
- Le suffixe de dépendance du lecteur Linux est incrémenté en `quality-fast1`
  pour que la mise à jour livre le filtre avec le cache/rafale, pas seulement la .so.

## Compilations et limites

Logs ignorés dans `artifacts/performance/amd-specialized/quality-fast-*.log` :
Manager Release (44 avertissements préexistants, zéro erreur ; CI `38669549109` réussie), backend CUDA/TRT
Linux complet, modules ORT/AMD Linux et objet C du filtre mpv compilés. Le dernier
build Windows complet est réussi ; les modules Linux sont recompilés.
Aucune inférence, mesure de gain ou comparaison numérique exécutée. Ne pas
présenter les optimisations comme garantissant des pixels identiques ni un gain
sur toutes les cartes. Les ordres/formules et paramètres de modèle sont gardés.

## Commandes de comparaison (ne pas exécuter sans nouvelle autorisation)

- `AJI_RIFE_BURST=0` : attentes synchrones historiques entre RIFE et upscale.
- `AJI_RIFE_PAIR_CACHE=0` : pas de cache exact des entrées/paires.
- `AJI_RIFE_PICTURE_GRAPH=0` : pas de capture RGB + post ; réseau complet gardé.
- `AJI_RIFE_FUSED_PRE=0` : staging/conversion historiques, tous formats.
- `AJI_RIFE_OVERLAP=0` : mouvement Fast et upscale sur le stream initial.
- `AJI_RIFE_CUDA_GRAPH=0` : captures RIFE désactivées.

## Liste du chantier restant

| Lot | Statut |
|---|---|
| Quality/Fast, compatibilité et garde des raccourcis | Codé ; compilations Linux/Windows/Manager réussies |
| Attentes CUDA limitées à l'événement utile | Codé |
| Cache exact de paire et promotion des RGB préparés | Codé ; activation par filtre Linux mis à jour |
| Capture RIFE plus large et fusion padding/conversion 4:4:4 / 4:2:0 | Codé |
| Recouvrement GPU RIFE/upscale, soumission groupée au lecteur | Codé ; pas de mesure |
| Préparation des prochaines paires hors de la paire courante | Non implémentée ; ownership/contextes à étendre |
| Fusion des conversions RIFE→upscale, plugins d'opérateurs neuronaux | Non implémentés ; conserver chroma et arrondis |
| Batching neuronal et contextes concurrents par modèle | Non implémentés ; distinct de la rafale de soumissions |
| Choix empirique des tactiques/streams TensorRT | Pas effectué ; builder niveau 5 déjà actif, profilage interdit |
| Publication des binaires et pin Manager | 3.8.0.31 déclenchée ; résultats des trois workflows à confirmer |

Ne pas confondre ces pistes avec les lots déjà codés. Les anciens worktrees
utilisateur et fichiers non suivis restent à préserver.
