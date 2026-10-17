# AH-354 — reprise exacte après pause

## État figé

- Checkout isolé : `/tmp/quality-pipeline-burst-20261017`.
- Branche : `perf-quality-pipeline-burst-20261017`.
- Base commune lot 58 : `61ba62753d0bbaa85734b19e7992be946ba92434`.
- Commit : **`b367479977202e971c3bdf803f24294967b2787e`**.
- Worktree propre, origin GitHub, aucun push. Aucun profil utilisateur modifié.
- Seulement trois fichiers committés : `src/aji_pipeline.cpp`, `src/pipeline_surface_burst.h`, `tests/pipeline_surface_burst_check.cpp`.
- Dossier de preuve : `/tmp/quality-pipeline-burst-artifacts-20261017/` : patch, logs configure/build, reçu JSON, résultat CPU, copie du `.so` et ce guide.
- Binaire candidat : `libaji_pipeline.so`, SHA256 **`2d0d107261f172cd34a8ab3b3adc2676e389b127ecd24f48c79b6a76bdef8d4d`**, 489720 octets.
- Fatbin inchangé : `1d9ca93cd2cc5e4ce5e944a5179d21687e7c9ab853f360f02bbfd96d19ca5b5d`.

**Statut : implémenté, compilé et contrôlé CPU ; ablation GPU et livraison encore nécessaires. Ne pas passer Done à la pause.** L'utilisateur a demandé de s'arrêter une fois le travail des agents figé ; aucun nouvel essai ou chantier n'est lancé ici.

## Ce que fait le patch

Pour un bloc **RIFE Quality + upscale fusionné** seulement, charge les extensions Surface async optionnelles, vérifie la capacité et crée une file persistante de 17 jobs (facteur cumulé maximal 16 plus endpoint droit). Soumet les phases/endpoints sans attente individuelle, puis attend la complétion terminale de tous les tickets avant le prochain étage ou les copies de sortie. Fast et le chemin synchrone public restent inchangés.

Le worker existant `src/surface_cuda_async.h:74–110` interroge les événements déjà en vol, puis prend un autre job queued même si les précédents sont encore Waiting. L'appel interne `cuda_surface_process(...,false)` supprime seulement l'attente finale par image ; les dépendances internes restent présentes. Ce n'est pas une boucle qui attend chaque image avant d'en lancer une autre.

`PipelineSurfaceBurst::finish` utilise Complete + callback terminal, sans Drain. **Le Drain du provider réinitialise son cache de paire** ; l'utiliser après chaque lot détruirait la promotion de l'endpoint droit. Drain est réservé à l'abandon/erreur, suivi de disable pour fermer une file potentiellement empoisonnée. Un reset désactive/joint d'abord le worker, appelle le reset historique, puis réactive la file. Détruire le helper avant le contexte garantit que son callback ne pointe plus vers un mutex/CV libéré.

Les Points sources restent dans le paramètre `points`; les sorties restent dans `out`, `right` ou `s.cached`, et toutes les allocations restent également dans le pool. Le garde d'erreur s'exécute avant la destruction des conteneurs sources/sorties. Si une allocation ou un push de vecteur lève une exception après Submit, le pool possède encore l'allocation et ne peut pas la réemployer avant le drainage. Le mode explicite BORROW_UNTIL_COMPLETE est donc tenu sans inventer des callbacks de ownership pour ces surfaces internes.

Les étages précédents ont terminé leur travail avant d'appeler ce bloc ; Complete FINISHED garantit l'achèvement de chaque sortie avant les consommateurs du stream pipeline/TrueHDR. Aucune barrière inter-stream n'est simplement supprimée.

## Vérifications terminées — ne pas répéter sans changement

1. `git diff --check` : passé.
2. Build de la seule cible `aji_pipeline`, **TrueHDR activé** avec `/usr/local/VideoFX` : exit 0, six étapes, logs joints.
3. Fixture CPU du vrai helper : **15 contrôles passés**, notamment soumissions multiples avant complétion, attente terminale, absence de drain normal, limite 17, erreur de soumission/complétion, fermeture et redémarrage, absence d'extension/wakeup et capacité insuffisante.
4. Revue de l'ownership, du worker réel, de la réutilisation de paire et du reset : décrite ci-dessus.

Aucun GPU, aucune mesure de FPS, aucun hash d'image prétendu. La file native peut attendre jusqu'à environ 1 ms avant de réinterroger ses événements lorsqu'elle n'a plus de job à soumettre. Ce délai préexistant de son reaper peut absorber une partie du gain ; ne pas annoncer de bénéfice mesuré avant ablation.

## Étapes restantes à la reprise

1. Préserver ces chemins avant nettoyage de `/tmp`. Récupérer le commit dans le checkout backend d'intégration. La branche du lot suivant peut déjà contenir d'autres changements de `aji_pipeline.cpp` (diagnostic/HDR) : **ne pas copier le fichier complet ancien**. Cherry-pick ce commit, puis résoudre seulement les zones concernées en conservant les autres travaux.
2. Reprendre le profil de diagnostic **isolé**, pas le profil utilisateur en place : Area 720p → RIFE426 vrai Quality ×4 → SPAN Sharp1 Performance 2× → TrueHDR 1440p. Même vidéo, même intervalle, mêmes modèles/engines, même machine et mode d'affichage. Root possède déjà le harnais et les entrées du diagnostic ; ce guide n'en invente pas un nouveau.
3. L'ablation utilise **le même binaire candidat ci-dessus** dans les deux branches, afin d'isoler AH-354 des optimisations déjà intégrées AH-346. Lancer exactement la même commande du harnais existant avec les seuls préfixes suivants :

```bash
# A : comportement synchrone, avec le même candidat
AJI_PIPELINE_QUALITY_BURST=0 AJI_PIPELINE_TRACE=1 <commande exacte du harnais déjà choisi par root>
# B : burst Quality, mêmes arguments/entrées
AJI_PIPELINE_QUALITY_BURST=1 AJI_PIPELINE_TRACE=1 <même commande exacte>
```

Les chevrons sont des emplacements documentaires, **pas des commandes à exécuter telles quelles**. Le chemin de bibliothèque doit être explicitement celui du candidat dans le harnais ; ne pas remplacer le `.so` installé pendant que le lecteur utilisateur est actif.

4. Dans B, vérifier la ligne `Quality surface burst enabled` puis le trace `quality_burst=1`. Les compteurs cumulés `burst_submitted` et `burst_finished` doivent progresser ensemble après chaque bloc. Le premier lot ×4 peut soumettre cinq images (A puis trois synthèses puis B), les suivants quatre grâce au cache d'endpoint. Pour l'EOF, un endpoint est possible ou déjà en cache.
5. Les compteurs de cache publics sont indisponibles tant que la file possède le contexte (`cache_status=-4`) ; **ne pas interpréter les zéros imprimés comme des cache misses**. Le patch évite précisément de désactiver/réactiver la file pour lire ces stats, ce qui réinitialiserait la paire. Le trace est explicite sur ce statut.
6. Vérifier les mêmes images/PTS en A/B, puis le temps du bloc sur le court échantillon utile. Ne pas comparer B à une ancienne DLL ou à un ancien « quality » qui projetait Fast. Arrêter lorsque le bénéfice et la fidélité sont établis ; approfondir seulement un échec ou résultat ambigu. Si aucun bénéfice utile n'est établi, ne pas activer par défaut : le coût du reaper asynchrone est un point ciblé à examiner.
7. Après résultat accepté, mettre à jour provenance/pin du bundle avec le **commit combiné réel**, publier et vérifier le hash du `.so` dans l'archive livrée. Consigner les résultats/limites dans AH-354, puis Done seulement après livraison vérifiée.

## Recompiler uniquement si l'intégration change les sources liées

Commandes utilisées, déjà concluantes sur le commit figé :

```bash
/home/ta2b/.animejanai-tools/work/rtx-build/cmake/bin/cmake \
  -S /tmp/quality-pipeline-burst-20261017 \
  -B /tmp/quality-pipeline-burst-build-20261017 -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_MAKE_PROGRAM=/home/ta2b/.animejanai-tools/venv/bin/ninja \
  -DCMAKE_CUDA_COMPILER=/opt/cuda/bin/nvcc \
  -DCMAKE_CUDA_ARCHITECTURES='75;80;86;89;90;100;120' \
  -DAJI_VFX_ROOT=/usr/local/VideoFX
/home/ta2b/.animejanai-tools/work/rtx-build/cmake/bin/cmake \
  --build /tmp/quality-pipeline-burst-build-20261017 --target aji_pipeline -j4
```

Ne pas omettre VideoFX pour obtenir artificiellement un build sans TrueHDR. Les builds doivent rester en fond pendant les tâches indépendantes, conformément au mandat utilisateur.
