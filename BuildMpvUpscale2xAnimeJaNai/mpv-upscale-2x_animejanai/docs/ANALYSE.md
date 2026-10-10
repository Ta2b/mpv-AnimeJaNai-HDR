# Rendu HDR — fonctionnement et réglages (10 octobre 2026)

## Objectif

Anime en HDR qui ressort sur le MSI MAG 272UP QD-OLED (Peak 1000 / EOTF Boost) : noirs profonds, éclats lumineux qui montent vers 1000 nits, couleurs vives, sans voile ni contours éclaircis. Le même dossier doit fonctionner sur le PC AMD (RX 9070 XT) en s’adaptant à la carte et à son écran.

## Chaîne complète

1. **Démarrage.** `mpv.conf` charge `hdr-tools/user-script-loader.lua`. Le chargeur détecte le GPU **une seule fois** (`gpu-policy.lua` + `detect-gpu.ps1`), active la banque de profils correspondante (`select-profile-bank.ps1`), puis lance les scripts personnels et officiels. Les scripts lisent ensuite la détection mise en cache.
2. **AnimeJaNai.** NVIDIA : TensorRT + NVDEC, avec RIFE selon le profil. AMD/Intel : DirectML + D3D11VA (`hardware_auto.lua`), sans RIFE, AMF ×2 en option (Ctrl+4).
3. **Fin de chaîne vidéo** (`animejanai_hdr_auto.lua`) :
   - NVIDIA, source SDR, HDR Windows actif : `format=p010` puis `d3d11vpp` avec **RTX TrueHDR** et **RTX VSR** dans le même filtre, jusqu’à la résolution de l’écran ;
   - AMD : AMD VideoSR 1.0 (`sr_amf`), avec repli D3D11 classique ;
   - sans HDR ou sur source HDR native : seulement la mise à l’échelle.
4. **Description de l’écran**, appliquée par le contrôleur dès que le HDR Windows est confirmé, à partir des réglages du GPU courant : `target-peak`, `target-contrast` (`inf` sur OLED) et `target-gamut`. Ces valeurs sont restaurées à la fin de la lecture.
5. **Conversion SDR → HDR :**
   - **RTX** (défaut NVIDIA) : TrueHDR produit du PQ marqué à 1000 nits. Avec `target-peak=1000`, libplacebo ne fait **aucun tone mapping** : les valeurs passent telles quelles. Vérifié dans le code de mpv/libplacebo et dans `libmpv-2.dll`.
   - **MPV** (défaut AMD/Intel) : pas d’inverse tone mapping global. Le blanc SDR est placé à `paper_white` (203 nits) via `hdr-reference-white`, le noir est ramené à 0, et c’est le shader qui crée les éclats.
6. **Grading** `user-shaders/anime-hdr-grade.hook`, sur l’image finale en PQ, identique pour tous les GPU. Seuls ses paramètres changent selon le moteur.
7. Sous-titres composés après le grading (`blend-subtitles=no`), blancs à 200 nits.

## Le shader de grading

Cinq passes sur `OUTPUT`. Les quatre premières construisent, en basse résolution, une carte de la luminance locale (1/8) et de la luminance de zone (1/32, flou gaussien d’environ 2,5 % de l’image). La dernière traite chaque pixel en lumière linéaire absolue :

| Étape | Effet | Détail |
|---|---|---|
| Noirs | Plus profonds | Pied de courbe sous ~50 nits, appliqué au maximum RGB. Le noir reste à 0, pente 1 au genou, pas de cassure. |
| Éclats | Pics lumineux | Gain sur la luminance au-dessus de 0,5 × blanc papier (mode MPV) ou de 250 nits (mode RTX). Il est fort quand la zone est nettement plus lumineuse que son voisinage (reflets, étincelles, magie, néons, lampes) et faible pour les grands aplats clairs (ciel, murs). **Jamais modulé sur la peau.** |
| Épaule | Pas d’écrêtage | Courbe rationnelle qui amène le maximum possible exactement au pic, avec une pente 1 au genou (65 % du pic). Elle reste neutre quand aucun gain ne peut dépasser le pic. |
| Vibrance | Couleurs vives | Chroma ICtCp (BT.2100) renforcé à intensité constante. Couleurs moyennes favorisées ; **peau exclue** (teinte ICtCp 105–135°, chroma < 0,1), primaires déjà saturées et ombres ménagées. |
| Gamut | Sans écrêtage | Limite douce au gamut Display P3 de l’écran et au pic : le renforcement ralentit avant le bord. |

Les canaux RGB sont multipliés ensemble pour les noirs, les éclats et l’épaule, donc la teinte ne bouge pas. La courbe est monotone pour un isolement donné (1152 combinaisons pic × blanc × moteur × réglages vérifiées).

**Mesures dans libplacebo** (mpv 0.37, Vulkan logiciel, sortie PQ 1000 nits) :

| Entrée | Mode MPV (SDR) | Mode RTX (sur TrueHDR) |
|---|---|---|
| Noir proche 2,75 nits | 2,0 | — |
| Gris 9,8 nits | 8,0 | — |
| Tons moyens ~106 nits | inchangés | inchangés |
| Grand aplat blanc 203 nits | ~294 | inchangé |
| Petit éclat blanc 203 nits | ~875 | — |
| Petit éclat 300 / 600 nits | — | 473 / 844 |
| Primaires saturées | inchangées | inchangées |
| Bleu ciel moyen (B 110 nits) | B 128 | — |

Coût : cinq passes légères, dont quatre en 1/64e de résolution ou moins. C’est négligeable sur RTX 4070 Ti et RX 9070 XT ; la mesure réelle reste à faire sur les deux PC.

## Correctif du 11 octobre : peau trop claire et scintillante en RTX

Symptôme : teint trop poussé, avec des taches blanches légèrement clignotantes sur les visages.

Cause : avec le réglage RTX *Middle grey* à 100 nits, TrueHDR place la peau entre 250 et 400 nits, au-dessus du pivot de 203 nits. La première version la traitait comme un éclat. Le gain dépendait de l'isolement (visage clair sur cheveux sombres), donc il variait entre le centre et les bords du visage, et d'une image à l'autre avec le grain et l'interpolation RIFE. Mesure dans libplacebo : peau 218 → 340 nits au centre, 424 sur les bords.

Correctif :
- en mode RTX, les éclats démarrent à 250 nits (la moitié du pic) ;
- les tons chair sont détectés (teinte ICtCp) et ne reçoivent ni gain d'isolement ni vibrance ;
- l'isolement se mesure sur des moyennes stables : un pixel ne compte seul que s'il dépasse sa zone de plus de 0,08 PQ (étincelle) ;
- la transition de l'isolement est plus progressive.

Résultat : peau à 250, 330 et 400 nits inchangée ; un reflet blanc sur la peau passe toujours de 409 à 547 nits ; orange et ciel restent renforcés. La capture 8 bits du test ne mesure pas d'écart sous ~3,7 % entre images, mais la peau ne reçoit plus aucun gain variable, ce qui supprime la cause du scintillement.

Réglages NVIDIA (RTX Video HDR) : les quatre curseurs sont en butée. *Middle grey* à 100 nits éclaircit fortement les tons moyens, dont la peau, et l'EOTF Boost de l'écran les éclaircit encore. Contraste et saturation au maximum poussent aussi les teints et écrêtent les hautes lumières de la peau. Conseillé : *Middle grey* vers 50, contraste et saturation baissés, en comparant TrueHDR seul avec Ctrl+G.

## Base AnimeJaNai 3.8.0 et génération d'images (11 octobre)

- Le fork suit maintenant **AnimeJaNai 3.8.0** et le **Manager 0.8.0**. Il récupère ainsi le choix automatique de la fréquence d'écran (*Automatic Display Refresh Rate*, Global Settings) : une fréquence multiple de la cadence vidéo pour tout l'épisode, par exemple 144 Hz pour du RIFE ×2 à 47,952 i/s, ce qui règle la saccade à 165 Hz. Il faut le lecteur mpv de la 3.7.0 ou plus récent ; celui de la 3.6.3 n'a pas `display-rate-match`.
- **AMD AMF x2** n'est plus lié au profil 4 : c'est une option globale (*Extra Frame Generation*) appliquée à tous les profils sur AMD. Le profil AMD 4 devient une variante libre du 2K. Ctrl+1…4 refusent un profil vide au lieu de sélectionner un slot sans chaîne.
- NVIDIA Smooth Motion et AMD Fluid Motion Frames sont des fonctions du pilote : le Manager indique où les activer.

## Ce qui a été retiré

- `rtx-hdr-peps.hook` : courbe en S centrée sur 500 nits en lumière linéaire, qui **assombrissait les tons moyens de 10 à 17 %** et n’ajoutait que +2 % aux hautes lumières.
- `mpv-hdr-peps.hook` et son style (`mpv_*`), remplacés par le shader commun. L’inverse tone mapping `spline` envoyait tous les blancs SDR vers le pic : grands aplats éblouissants, limitateur de luminosité (ABL) de l’OLED sollicité, aucune distinction avec les vrais éclats.
- Profils `[anime-rtx-hdr]` et `[msi-peak-1000]` : remplacés par le contrôleur. `hdr-contrast-recovery=0.30`, `hdr-compute-peak=no` et `tone-mapping` n’avaient aucun effet sur la sortie TrueHDR, puisque libplacebo n’y fait aucun tone mapping.
- `saturation=22` (saturation YUV globale), remplacée par la vibrance ICtCp limitée au gamut.
- Profils de comparaison `[anime-couleurs-vives]`, `[anime-couleurs-neutres]`, `[anime-hdr-contraste]`, `[anime-hdr-fidele]` : remplacés par **Ctrl+G**.
- Réglages neutres redondants (`gamma/contrast/saturation/brightness/hue=0`), commentaires dupliqués, variable `vsr_scale` jamais lue, `policy.hdr_conversion`.
- Détection GPU lancée en parallèle par plusieurs scripts : elle est maintenant faite une fois par le chargeur.
- `resize_factor_before_upscale=NaN` du profil NVIDIA 3 : remplacé par 100. La hauteur 720 reste prioritaire, comme le confirmait déjà le journal du filtre.

## Vérifications

- Shader compilé et exécuté par libplacebo réel (mpv 0.37, Vulkan logiciel) en mode MPV et en mode RTX, avec mesures sur mires synthétiques. La compilation D3D11 (HLSL via SPIR-V) se fait au premier lancement sous Windows.
- Contrôleur exécuté avec un mpv simulé (LuaJIT et Lua 5.1), 51 cas : NVIDIA RTX SDR, HDR natif, HDR Windows coupé, AMD MPV, écran AMD de 600 et 250 nits, bascule Ctrl+G, diagnostic, restauration en fin de fichier, conservation des autres shaders et de leurs options, absence de réécriture de propriétés en régime établi, détection GPU unique.
- Non vérifié ici : le rendu réel sur les deux écrans, la lecture sur RX 9070 XT (DirectML, VideoSR, AMF) et le pic que le pilote NVIDIA donne réellement à TrueHDR.

## Suggestions pour aller plus loin

| Priorité | Action | Pourquoi |
|---|---|---|
| Haute | Étalonnage HDR Windows dans le mode d’écran utilisé (EOTF Boost), pic réglé à 1000 | Le pilote NVIDIA choisit le pic de TrueHDR d’après les informations de l’écran dans Windows ; mpv suppose 1000 nits. |
| Haute | Windows à **144 Hz** + `--profile=anime-cadence-ecran` | RIFE ×2 donne 47,952 i/s. 144 Hz = 3 × 48 : cadence parfaite. À 165 Hz, chaque image dure 3 ou 4 rafraîchissements, d’où une saccade. |
| Moyenne | Comparer Ctrl+2 (1080p natif → 4K, sans RIFE) et Ctrl+3 (720p → RIFE → 1440p → VSR) | Ctrl+3 jette du détail source en descendant à 720p. Si la fluidité RIFE compte moins que la netteté, Ctrl+2 est plus fidèle. |
| Haute | NVIDIA App > RTX Video HDR : *Middle grey* vers 50, contraste et saturation baissés | Ces curseurs sont en butée : tons moyens et peau trop clairs, teints trop saturés, hautes lumières écrêtées. |
| Moyenne | Régler `shadows`, `highlights`, `vibrance` sur 2–3 épisodes de référence, avec Ctrl+G pour comparer | L’EOTF Boost éclaircit déjà les tons moyens côté écran. |
| Basse | Remplir `peak_amd` et `oled_amd` selon l’écran du PC AMD | `auto` suit Windows, souvent approximatif. |
| Performance | NVIDIA : le passage CUDA → D3D11 (`format=p010`) transite par la RAM | Inévitable tant que TrueHDR/VSR n’existent qu’en D3D11 et TensorRT qu’en CUDA. |
