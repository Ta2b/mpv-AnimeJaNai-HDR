# Lot 25 — RIFE Fast CPU limité aux calculs de mouvement utiles

AH-272 sous AH-66 ; autres graphes/providers/OS dans AH-273. Base .56 `4d7ff64d667d6204bf4acb6fd52a50c7c1310920`, moteur `4488fd442e3373a62886b12688478aff5ead45d0`. Worktree isolé ; sources utilisateur et modèles installés préservés.

## Changement et périmètre

Fast CPU utilise flow/mask pour interpoler les images agrandies. Le graphe chargé exposait aussi une image RGB que ce chemin ne consomme pas. Une demande motion-only explicite prépare en mémoire les deux sorties utiles, puis conserve exactement les nœuds dans leur fermeture de dépendances. Poids, nœuds conservés, entrées et métadonnées non concernées restent identiques. Aucune approximation ni changement de convolution, activation, couleurs ou loi de mélange. Le convertisseur flow générique et ses identités/caches TensorRT restent inchangés.

Activation par défaut limitée à Linux x86-64, provider CPU, ORT1.24.1, optimiseur ALL3 et contenu exact RIFE4.26 déjà qualifié : image SHA256 `fd6b06538898c9a94d20f0fe55febceadbcde5ad64952240733b7275ef4c9d59`, export flow v2 `4d93a8a394cc1a1dd20d7efc2fcbace769f289dd655d0f76f941f533ffbbc216`. La préparation vérifie le contenu complet avant toute modification ; l'élagage est privé à ces graphes plats déterministes. Les autres chemins conservent le graphe complet. `AJI_ORT_CPU_MOTION_ONLY=0` désactive la spécialisation ; indépendant de `AJI_ORT_CPU_ACTIVATIONS=0`.

L'interpolateur utilise les noms/types réels des deux sorties et ne crée plus de binding ni buffer RGB. Une demande RGB sur cette session est rejetée avant préparation/écriture. Une erreur de compilation restaure le graphe original complet ; le mode réel est activé seulement après compilation réussie. Les fichiers des modèles et caches flow ne sont pas réécrits ; aucun cache compilé CPU persistant ajouté.

## Preuves courtes

Première tentative : ne retirer que la sortie RGB a conservé les378 kernels effectivement exécutés, dont5 GridSample. Flow/mask et huit sorties RGB exacts, mais aucun gain de calcul établi : variante insuffisante écartée. Ce résultat a motivé l'élagage explicite, sans prolonger une mesure de temps ambiguë.

| Comparaison finale, même runtime/machine/modèle/options/entrées | Avant→après | Résultat |
|---|---|---|
| Flow/mask bruts, activations natives,128×72 puis nouveau contexte160×80 | 3→2 sorties,378→362 kernels réellement exécutés | Tous les bits identiques ; appel RGB refusé, destination sentinelle intacte |
| Activations natives désactivées,128×72 | 484→468 kernels exécutés | Flow/mask bit à bit identiques ; indépendance du flag établie |
| Fast complet SPAN tuilé2×1/deux exécuteurs CPU,256×72 | RIFE378→362 ; SPAN47 inchangé | 8 sorties RGB24 exactes,0 octet différent, strides et reconfiguration inclus |

Le profiling C API confirme un run par session et des kernels correspondant aux nœuds compilés, sans se fonder sur un compteur produit. **16 kernels et leurs matérialisations inutiles disparaissent**, dont GridSample5→4, Cast42→36, Add50→48, Mul14→11, Split/Reshape/Transpose chacun−1 et Sub1→0. Conv53, ConvTranspose6, ReorderInput51/Output52 et les53 activations natives restent identiques. La fermeture de dépendances a été calculée indépendamment ; restaurer les nœuds et la sortie supprimés restitue le modèle complet, poids compris.

Le buffer RGB applicatif retiré représente `3×PW×PH×2` octets FP16 par interpolateur :196608 octets pour le cas256×72 paddé256×128. Cette borne explicite ne mesure pas la RSS totale ni la mémoire interne ORT. Créations applicatives de MemoryInfo/tenseurs/handles de forme possédés et demandes de sortie non préallouée toujours0 dans la fenêtre chaude ;6 runs et114 lectures de forme empruntée inchangés.

Référence Fast valide du lot24 réutilisée sans refaire un essai concluant, profiling désactivé dans les deux branches : chaîne de deux nouvelles paires122,6149→98,8690ms. **Gain temporel soutenu/FPS non concluant**, observation courte et état bureau/alimentation non mesuré. Le bénéfice retenu est la suppression démontrée de calculs et du buffer inutiles, avec sortie exacte ; aucune extrapolation universelle.

Deux contrôles configure-only, sans nouvelle comparaison de frames : flag0 restaure exactement le modèle complet avec activations natives,378 nœuds/3 sorties ; échec injecté de compilation motion-only restaure exactement le modèle original,484 nœuds/3 sorties. Fast/motion et facteur2 restent actifs dans les deux cas. ABI publique9 symboles `aji_vk_*` conservée, build CMake Release réussi, syntaxe Python et `git diff --check` réussis.

Artefacts locaux : `artifacts/performance/lots-20261016/lot-25/`, `pruned-raw-capture/verified-summary.json`, `activation-off-raw-capture/verified-summary.json`, `pruned-fast/summary.json`, `fallback/summary.json`, specs/logs/NPZ/profils. Commandes ciblées : `cpu_motion_only_check`, `cpu_motion_graph_check.py CAPTURE`, `ort_motion_only_check.py pruned-fast.spec.json`, `cpu_motion_fallback_check.py fallback.spec.json`. La variante initiale sans élagage et ses résultats sont conservés comme diagnostic.

## Décision

Conserver pour la réduction utile de calculs/matérialisations et la fidélité établie dans ce périmètre. Release **3.8.0.57**, pins GPU et Manager inchangés. AH-272 Done après publication vérifiée ; AH-66/AH-273 restent ouverts. Aucune qualification matérielle/API supplémentaire inventée.
