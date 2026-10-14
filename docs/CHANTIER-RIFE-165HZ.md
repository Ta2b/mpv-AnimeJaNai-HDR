# Chantier RIFE fluide à 165 Hz, paquets allégés — 3.8.0.24 à 3.8.0.29

Suite publiée le 15 octobre : **3.8.0.30**, moteurs AMD/NVIDIA spécialisés,
19 assets sur Windows/Linux/macOS. Voir [le relais GPU](CHANTIER-GPU-SPECIALISE.md).
Le bilan 3.8.0.29 ci-dessous reste historique.

État au **14 octobre 2026**. Ce document prend la suite de
[ETAT-PROJET.md](ETAT-PROJET.md) (désormais consolidé jusqu’à la 3.8.0.29) : ce qui a été livré
depuis, les mesures, ce qui reste, les recommandations et une critique honnête
du code.

Publication confirmée : **3.8.0.29**, source `6fa85bb`, 16 assets GitHub et
builds Windows/Linux/macOS réussis. Les mesures ci-dessous proviennent de la
session d'implémentation CUDA ; elles n'ont pas été répétées dans la session
qui consolide les documents. Modèles conservés ne signifie pas rendu identique :
le warp médian et la chronologie des dessins changent la génération temporelle.
L'ancien moteur et le rythme original restent sélectionnables.

Machine de référence : Linux, RTX 4070 Ti, écran 4K 165 Hz HDR. Profil cible
(slot 3) : source 1080p réduite en 720p → RIFE 4.26 → SPAN V3.1 Sharp1
Performance ×2 (1440p) → TrueHDR. Choix validé par l'utilisateur : RIFE coûte
7,9 ms à 720p contre 26,6 ms à 1080p, et une image 1440p sur un écran 4K est
proche de l'invisible.

## 1. Ce qui a été livré

| Version | Contenu |
|---|---|
| 3.8.0.24–26 | Trois workflows de release indépendants (`release-windows.yml`, `release-linux.yml`, `release-macos.yml`), aucun job de test ; branches `try/**` = build sans publication. Choix « nouveau / ancien moteur RIFE » dans le Manager (`[global] rife_engine`). |
| 3.8.0.27 | Paquets allégés : TensorRT sorti de l'AppImage (586 → 239 Mo), updater et benchmark .NET trimmés (71 → 15–18 Mo). OpenVINO/ONNX Runtime Linux en pack. Manager et modèles en packs « core ». Mise à jour : seuls les packs dont la version de contenu change sont retéléchargés ; le lecteur annonce « Met aussi à jour : … ». Synchronisation d'affichage exacte (fractions continues, ex. 11011/1600 pour 23,976 i/s sur 165 Hz) et scaler final allégé au-delà de 100 i/s (`rife_light_scale`). |
| 3.8.0.28 | Linux CUDA : RIFE sur la chronologie des dessins (`rife_drawings`). |
| 3.8.0.29 | Moteur partagé (macOS, Linux ONNX Runtime) : nouvelle chaîne RIFE + chronologie des dessins. |

### Nouvelle chaîne RIFE (« warp »)

Pour les profils qui interpolent **avant** l'upscale :

1. Chaque image source est upscalée **une seule fois** (TrueHDR aussi, quand il
   garde la taille).
2. RIFE ne fournit plus l'image mais son **mouvement** (flux 4 plans + masque),
   via une copie du modèle ONNX à sorties supplémentaires (`onnx_flow.cpp`,
   éditeur protobuf sans dépendance).
3. Les images intermédiaires sont les deux images **upscalées** déformées et
   mélangées à la résolution de sortie (1,8 ms en TensorRT).
4. **Un seul RIFE par paire**, au milieu (t = 0,5) ; chaque instant en est
   dérivé avec la loi de mélange ajustée sur RIFE lui-même
   `logit(w) = 0,285·logit(masque) + 2,591·ln((1−t)/t) + 0,170`.
   Utilisé sous 15 px de mouvement (à l'échelle 720p) et toujours au-delà de ×3 ;
   sinon un RIFE par instant.

Le coût ne croît presque plus avec le facteur, ce qui rend ×7 à 165 Hz possible.

### Chronologie des dessins

Un dessin tenu 2 à 4 images (animation « en 2 », « en 3 ») : au lieu de tout le
mouvement sur un seul intervalle, il est réparti sur toute la tenue. Le filtre
Linux CUDA est patché (`native/linux-cuda/vf_animejanai-drawings.patch`,
4 images d'avance) ; le moteur partagé le fait via `aji_vk_upcoming`.
Mesuré sur une sortie réelle : images en mouvement 28,5 % → 79,9 %, plus gros
à-coup 9,7 → 5,3 niveaux. `rife_drawings=no` garde le rythme d'origine.

### Où se trouve la chaîne

| Moteur | Chaîne warp | Dessins |
|---|---|---|
| NVIDIA privé (`libaji_trt_rtx.so`, branche `warp-chain`) | oui | oui |
| Moteur partagé (`native/linux-ort` : Mac, Linux ORT) | oui (warp CPU) | oui |
| Filtre Linux CUDA | — | patch |
| NCNN/Vulkan | **non** | non |
| Binaires Windows amont | **non** (binaires the-database) | non |

## 2. Mesures (4070 Ti, TensorRT)

Coûts unitaires : SPAN Perf 4,1 ms ; SPAN Balanced 7,5 ms ; RIFE 4.26 360p 1,5 /
540p 3,7 / 720p 7,9 / 1080p 26,6 / 1440p 68,4 ms ; TrueHDR ≈ 0,9 ms ; warp 1,8 ms.

Banc d'essai (ms par image source, TrueHDR compris, budget 41,7 ms à 23,976 i/s) :

| Cas | Ancienne chaîne | Nouvelle |
|---|---|---|
| ×3 scène agitée | 27,6 | 19,0 |
| ×3 scène calme | 28,0 | 12,5 |
| ×6 | 60,3 / 62,6 | 15,1 / 13,6 |
| ×7 Performance | — | 14,2–15,6 |
| ×7 Balanced | — | 17,5–20,4 |

Lecture réelle profil 3 en ×4 : 56 % d'images perdues (nouvelle) contre 90 %
(ancienne) avant les réglages 165 Hz. **La lecture réelle à 165 Hz en ×7 n'a
pas été revérifiée** (l'utilisateur teste lui-même).

## 3. Reste à faire

- Porter la chaîne warp et les dessins sur NCNN/Vulkan (sert surtout aux AMD).
  NCNN permet d'extraire n'importe quel blob : le flux RIFE est lisible sans
  modifier le modèle ; il faut un shader de warp Vulkan.
- Windows : non porté et non livré. Les paquets consomment les binaires amont ;
  un build Windows du fork et son intégration avec une référence immuable seraient
  une autre voie à réaliser, sans attendre nécessairement une publication amont.
- Modèle ~165 i/s entraîné maison : reporté par l'utilisateur.

## 4. Recommandations

### 4.1 Préparer les moteurs TensorRT en arrière-plan — abandonné

**Décision utilisateur ultérieure, 14 octobre : ne pas réaliser cette proposition.**
Elle améliore le démarrage et pas le débit. La priorité active est
[MIGraphX/HIP et TensorRT/CUDA spécialisé](CHANTIER-GPU-SPECIALISE.md).
Le texte ci-dessous est conservé comme historique de la proposition initiale.

Problème : le premier film pour un couple modèle + résolution déclenche la
compilation `trtexec` (« pause de première lecture », parfois plusieurs minutes).
Aucune préparation anticipée des moteurs usuels après installation n’est
documentée ici ; la compilation déclenchée à la première utilisation est un autre mécanisme.

Distribuer des moteurs précompilés est une **mauvaise** piste : un moteur dépend
de la carte (SM), de la version exacte de TensorRT et de la forme d'entrée ; le
mode compatible entre architectures coûte des performances ; la matrice
modèles × résolutions × cartes × versions serait énorme.

Proposition :

1. Après l'installation du pack TensorRT (et après chaque mise à jour qui change
   `TrtVersion` ou les modèles), lancer en tâche de fond, à basse priorité, la
   compilation des moteurs **les plus probables** : modèles des slots par défaut
   et du `default_slot`, entrées 1280×720 et 1920×1080 (et 720p après réduction
   pour les profils qui réduisent), RIFE 720p si le profil l'utilise.
2. Réutiliser exactement le chemin et le nom de cache que le filtre calcule
   (CRC des réglages dans le nom), sinon le moteur sera recompilé : le plus sûr
   est d'exposer dans `aji` une entrée « prépare ce slot pour cette résolution »
   plutôt que de réimplémenter la ligne de commande `trtexec`.
3. Déclencheurs possibles : l'updater/AppRun après installation d'un pack, ou le
   Manager (« Préparer les moteurs maintenant »). Un verrou par fichier évite
   qu'une lecture et la préparation compilent le même moteur.
4. `animejanai_engine_monitor.lua` affiche « préparation en cours » si une lecture
   tombe sur un moteur en cours de compilation.

Coût estimé : moyen. Gain : supprime la pause du premier film pour la grande
majorité des usages.

### 4.2 Se dégrader proprement quand des images sont perdues (priorité 2)

Le signal n'est pas la charge GPU mais `frame-drop-count` / la durée des images.
Le bon levier est de **baisser le facteur RIFE** (ex. ×7 → ×5) dans
`rife-sync.lua`, pas de changer de modèle d'upscale en pleine lecture (deux
moteurs à compiler, saut de qualité visible). Utile surtout aux GPU modestes et
portables ; sur la 4070 Ti la marge est large.

### 4.3 Écarté après analyse (avis Gemini du 14 octobre)

Pré-passe GLSL deband + petit réseau (les modèles sont entraînés à nettoyer la
compression eux-mêmes ; l'upscale n'est plus le goulot) ; VkFFT / WebGPU (hors
sujet pour l'inférence native) ; lecteur complet réécrit (mpv.net + Manager
couvrent déjà le besoin) ; « ne pas interpoler les dessins répétés » (garde la
saccade ; le défaut réel est traité par la chronologie des dessins). Déjà fait :
upscale unique des plans fixes (réutilisation d'image dans le moteur NVIDIA, par
tuile et `engine_boost` dans le moteur partagé), RIFE une fois par paire.

## 5. Critique du code

- **Aucun test en CI** (choix de l'utilisateur) : une régression n'est vue qu'à la
  main. Les tests Lua `tests/hdr` existent et passent en local
  (`AJ_ROOT=…/portable_config`).
- **La chaîne RIFE existe en trois implémentations** (CUDA privé, CPU partagé,
  patch du filtre) : risque de divergence. Toute évolution de la loi de mélange
  ou du seuil 15 px doit être reportée partout.
- **Le patch du filtre** s'applique sur `vf_animejanai.c` de the-database/mpv
  (`19c0fcf895`) : un changement amont casse la compilation Linux. À proposer en
  amont ou à rebaser à chaque montée de version.
- **Windows, plateforme principale, n'a pas la nouvelle chaîne.**
- **Warp CPU du moteur partagé** : non mesuré à haute cadence en 1440p (bande
  passante mémoire) ; un warp GPU (Metal/CoreML) serait l'étape suivante sur Mac.
- **Fichiers monolithiques** : assembleur `Program.cs` 1 621 lignes (top-level
  statements), updater 2 049 lignes, `aji_ort.cpp` 1 231 lignes. À découper par
  responsabilité (téléchargements, packs, manifest) quand on y retouche.
- **Moteur NVIDIA privé installé à la main** hors release : son état réel sur une
  machine n'est pas traçable par le paquet.
