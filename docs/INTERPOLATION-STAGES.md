# Étages d’interpolation ordonnés — Linux NVIDIA

Le lecteur Linux de 3.8.0.72 accepte des étages ordonnés explicites dans
`animejanai.conf`. L’éditeur Manager est le lot suivant AH-302 ; cette release
livre le raccord natif AH-301. Les profils existants conservent leur chemin,
Quality et les fractions RIFE (dont5/2). Un schéma strictement équivalent à
ces réglages emprunte également ce chemin inchangé.

## Capacités livrées

- Interpolation `rife` / `tensorrt` : facteur entier2..8 par étage mixte,
  modèle RIFE disponible, ensemble, seuil de scène, politique Quality ou Fast.
- Interpolation `nvidia-fruc` / `cuda` : Fast explicite×2, SDK NVIDIA installé
  séparément, SDR8bits interne même dans un conteneur16bits. Ses défauts de
  contours/bouche/occultation excluent une équivalence Quality.
- Upscaling `onnx` / `tensorrt` spatial, entre ou après les interpolateurs.
  Les upscalers contigus restent regroupés pour conserver leurs calculs.

Les facteurs temporels se multiplient : RIFE×2 puis FRUC×2 =×4.
Limites initiales :16étages, facteur cumulé≤16, pool pixels possédés512MiB
(hors espace de travail interne TRT/SDK). Un étage désactivé est conservé.
Méthode/runtime/option non implémentés, SR temporel, HDR PQ/HLG et fractions
mixtes sont refusés explicitement. Ces limites n’en font pas des choix disponibles.
Les autres moteurs du comparatif restent des travaux distincts du backlog.

## Exemple : RIFE×2 → FRUC×2 → SPAN

Conserver la section `[global]` de son profil avec `backend=TensorRT`, et ses
options de construction. Dans le slot/règle choisi, garder les limites de
résolution/FPS, puis ajouter les clés suivantes. Remplacer les trois chemins
absolus FRUC par ses fichiers réels ; aucun SDK/runtime propriétaire n’est
livré. Le modèle RIFE426 et le SPAN doivent être présents dans le paquet/cache.

```ini
[slot_1]
chain_1_pipeline_version=1
chain_1_stage_count=3
chain_1_stage_1_id=rife-first
chain_1_stage_1_kind=interpolate
chain_1_stage_1_method=rife
chain_1_stage_1_runtime=tensorrt
chain_1_stage_1_enabled=yes
chain_1_stage_1_model=426
chain_1_stage_1_factor_numerator=2
chain_1_stage_1_factor_denominator=1
chain_1_stage_1_policy=quality
chain_1_stage_1_ensemble=no
chain_1_stage_1_scene_detect_threshold=0.150
chain_1_stage_2_id=fruc-second
chain_1_stage_2_kind=interpolate
chain_1_stage_2_method=nvidia-fruc
chain_1_stage_2_runtime=cuda
chain_1_stage_2_enabled=yes
chain_1_stage_2_factor_numerator=2
chain_1_stage_2_factor_denominator=1
chain_1_stage_2_policy=fast
chain_1_stage_2_sdk_library=/chemin/SDK/libNvOFFRUC.so
chain_1_stage_2_sdk_runtime=/chemin/SDK/libcudart.so.11.6.55
chain_1_stage_2_kernel_fatbin=/chemin/paquet/animejanai/inference/aji_fruc.fatbin
chain_1_stage_3_id=span-last
chain_1_stage_3_kind=upscale
chain_1_stage_3_method=onnx
chain_1_stage_3_runtime=tensorrt
chain_1_stage_3_enabled=yes
chain_1_stage_3_model=2x_AnimeJaNai_HD_V3.1Sharp1_Performance_SPANF3_b5f48_unshuffle_fp16
chain_1_stage_3_policy=quality
```

Un ID reste attaché à son étage quand l’ordre change. Les facteurs absents
valent1 ; renseigner les facteurs des interpolateurs. Les clés historiques
restent utiles à la compatibilité des profils équivalents ; elles ne remplacent
jamais silencieusement une chaîne mixte. Utiliser ce schéma avec le nouveau
lecteur Linux ; le Manager antérieur à AH-302 ne doit pas réenregistrer ces
profils manuels. Il ne connaît pas encore les étages.

Le lanceur fournit les chemins des modules propres au lecteur. FRUC exige un
`kernel_fatbin` explicite et son CUDART11 compatible : ne jamais renommer
CUDART13 en11. SDK et pilotes suivent leurs propres conditions et compatibilités.
La chaîne mixte conserve sa cadence déclarée ; la synchronisation écran
continue pour les anciens profils/étages équivalents. Le marquage TrueHDR du
chemin historique est réservé à ce dernier, pas à la synthèse mixte SDR.

## Qualification et diagnostic

Sur RTX4070Ti/Linux : neuf sorties réelles pour trois sources, cadence×4,
EOF sans futur fictif, médiane commune RIFE→SPAN exacte, seek/pause/changement
de slot, owners équilibrés et erreurs remontées. Aucune copie pixels CPU dans
le moteur. La file et l’initialisation des modèles sont asynchrones ; une
compilation peut être annulée à la destruction du lecteur.

Les métadonnées `pipeline-active`, `pipeline-factor`, `pipeline-*-requests`,
`pipeline-fruc-repetitions`, `pipeline-peak-pixel-bytes` et
`pipeline-cpu-pixel-copies` décrivent l’exécution. Les requêtes ne prouvent pas
le nombre de kernels lancés ; une coupure de scène peut copier une source.
Aucune garantie FPS tous matériels, HDR physique ou autre API n’est établie.
Le SDK FRUC n’a pas montré une reproductibilité exacte bit à bit.
Voir le rapport `docs/qualification/lot-40-ordered-interpolation-20261016.md`
dans les sources du projet pour les preuves et diagnostics exclus.
