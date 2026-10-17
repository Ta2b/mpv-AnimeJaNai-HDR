# Lot 17 — identité des sources et fenêtres temporelles TensorRT

AH-261, sous-ticket de AH-33. Backend de référence livré .44 `df489209a9758149f0e8e580539ebdc50c2ae577` ; candidat initial `77bce826327e51699c592f8821f703539ccf5e21`, correction du seul accumulateur adjacent `635424ef27356fac94745419e46da48978804702`. Le lot 14 motion/identité de programmes reste isolé et non livré. Référence de paquet au démarrage : .45 ; base de publication à jour .47.

## Correction et périmètre

L’anneau réutilisait une préparation sur le seul numéro de séquence. Il vérifie maintenant la vue complète et le flux CUDA avant réutilisation : dimensions, format, matrice/plage/siting, trois adresses et strides. Les numéros invalidés au reset constituent une nouvelle génération ; une reconfiguration remplace tout l’anneau et les modèles de la chaîne. Les pixels d’une identité/vue inchangée doivent rester immuables, conformément au contrat d’appel.

Chaque inférence rassemble de nouveau **toute la fenêtre dans l’ordre**, sans cache de sortie indexé par le seul centre. Un voisin remplacé est donc pris en compte. Ses deux métriques de coupe adjacentes sont recalculées, y compris pour le frame suivant déjà ingéré. La barrière de dépendance CUDA existante couvre ingest et infer_seq, et la fenêtre droite à INT64_MAX est bornée sans overflow signé. DirectML conserve son contrat existant ; aucune qualification native Windows n’est déduite de ce changement CUDA.

Utilité : fidélité des tenseurs préparés et suppression de lectures périmées/races entre appels sériels sur deux streams. Aucun gain FPS revendiqué, aucun nouveau cache de sortie, changement de modèle ou compromis Quality.

## Essai court et réel

`tests/inference/temporal_views_check.py SPEC`, avec `temporal_views_probe.py`, exécute un véritable réseau **rank-5 fp16 dynamique TensorRT**, fenêtre T=3 pondérée asymétriquement. Modèle synthétique explicitement déclaré : il rend l’ordre observable, sans prétendre qualifier visuellement un modèle anime temporel. Même entrée NV12 128×72, réglages, machine RTX 4070 Ti et **même plan**, construit une seule fois par la référence ; candidat utilise `/bin/false` comme builder. Aucun rebuild ni variante de plan dans la comparaison.

| Cas | Référence vs calcul frais : octets différents / max | Candidat vs calcul frais |
|---|---:|---:|
| Fenêtre inchangée | 0 / 0 | 0 / 0 |
| Voisin même séquence, couleur différente | 6 716 / 2 | 0 / 0 |
| Voisin même séquence, autre vue | 12 489 / 21 | 0 / 0 |
| Ordre des voisins inversé, même centre | 13 517 / 104 | 0 / 0 |
| Numéros recyclés après reset | 0 / 0 | 0 / 0 |
| Ingest puis inférence sur deux streams, sans attente hôte intermédiaire | 13 564 / 125 | 0 / 0 |
| Remplacement du prédécesseur, coupe vers le suivant | 9 216 / 1 | 0 / 0 après correctif |
| Fenêtre en fin de domaine des séquences | 0 / 0 | 0 / 0 |

Les fenêtres fraîchement inversées diffèrent de l’originale sur 13 517 octets : le réseau distingue bien l’ordre. Le reset refuse d’abord l’inférence de l’ancien centre non réingéré. La sortie de fenêtre inchangée est aussi identique avant/après bibliothèque : **0 octet différent**.

Le candidat initial corrige tous les cas sauf la coupe adjacente : le kernel additionne atomiquement, et le nouveau recalcul avait omis de remettre son accumulateur à zéro. Après correction, **seul ce cas en échec** est rejoué (`--cut-fix`) avec le plan préservé ; résultat exact. Les autres reçus conclusifs sont réutilisés : ces quatre lignes ne changent que la branche de métrique adjacente, et les cas de vues/ordre concernés utilisent une coupe désactivée. Pas de nouvelle série ni de répétition des réussites.

Artefacts locaux : `artifacts/performance/lots-20261016/lot-17/` : sources/spec, builds multi-SM avant/après correctif, logs, `views/before.json`, `views/after.json`, `views/after-cut-fix.json`, tableaux NV12 `.npz`, un seul plan et reçu `views/summary.json`. Aucun benchmark FPS, ni assertion sur la qualité d’un réseau temporel anime non disponible. Le résultat est un correctif de fidélité mesuré sur ce chemin rank-5 réellement exécuté.

## Livraison

Linux : bibliothèque de production multi-SM finale qualifiée, source `635424e`, SHA `744300945d8adfc72faf13134180dbdbc50b1de59c9b78e01b9d3d4b9e1f9d14`. Windows compile/link AMD/NVIDIA success **38847445122**, même source `635424e`, SDK/player source `f05cf41` ; ce n’est pas un essai matériel. **24 exports ABI identiques**. Pin binaire `a1998637f2c3c243da8b7b9847f66eaaad1958ca`, source player de qualification `0cb5d2b0f6020ad620cf3250796babc7b98fff0e` distincte du source SDK. Paquet **3.8.0.48** poussé ; AH-261 reste In Progress jusqu’à publication vérifiée. AH-13 / lot 18 progresse pendant cette publication, sans attente.
