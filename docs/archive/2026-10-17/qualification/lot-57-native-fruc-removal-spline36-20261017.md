# Lot 57 — retrait FRUC et Downscale Spline36 indépendant

État : implémentation et qualification native ciblée terminées, release en
préparation. AH-328 porte le retrait FRUC ; AH-321 porte la dissociation réelle
du Downscale. La qualification du Manager, du routage Lua et du paquet complet
est distincte et doit être jointe avant de déclarer tout le lot livré.

## Changement utile

Le fournisseur FRUC, ses kernels, son en-tête, ses options mpv et ses cibles CMake
sont retirés. La cible Linux `aji_pipeline` ne dépend plus de `AJI_FRUC_ROOT`.
Le paquet retire `libaji_fruc.so`, `aji_fruc.fatbin` et `FRUC-README.md` ;
les fichiers SDK personnels restent intacts. Un étage historique FRUC activé
est explicitement incompatible, sans remplacement. Désactivé, il conserve ses
données. Les emplacements ABI v1 sont réservés plutôt que supprimés : taille et
offsets restent compatibles, compteurs retirés à zéro.

L’étage `resize/spline36/tensorrt` (ou runtime `cuda`) réutilise le
redimensionneur natif dans une chaîne sans modèle. Il s’exécute à sa position,
sans regroupement ni déplacement à travers RIFE. Une hauteur est un plafond,
traduit en pourcentage double précis pour préserver l’aspect ; la boîte16:9
historique n’est pas utilisée. Les dimensions réduites suivent l’arrondi pair
natif. Le pourcentage explicite vaut 1..100. Area reste une autre méthode. Le bit de capacité
Spline36 vaut 4 ; aucun alias bilinear trompeur n’est ajouté.

L’utilité est la simplification demandée et le choix d’un Downscale explicite,
pas une optimisation FPS. Les calculs TRT, modèles et kernels existants restent
inchangés. Lanczos3 et d’autres algorithmes sont des explorations distinctes :
aucune disponibilité supplémentaire n’est revendiquée.

## Essais strictement ciblés

| Contrôle | Résultat |
| --- | --- |
| Quatre exécutables CPU configuration/ordonnancement/Downscale/retrait | PASS : schéma, limites, ordre/groupes, fractions historiques, rejet FRUC actif, préservation inactive, ABI64bits et traduction Spline36 sans modèle |
| Build Linux portable pipeline, sans variable ni en-tête FRUC | PASS, TrueHDR optionnel conservé ; fatbin exactement identique à la référence |
| Application des huit patches natifs mpv sur la base épinglée | PASS sans fuzz ; en-tête et option FRUC absents du filtre assemblé |
| RIFE Fast ×4 + SPAN, avant/après retrait | PASS : les 5 sorties, PTS/durées, flags, dimensions, couleur et compteurs sont identiques |
| Spline36 seul 128×72 → 64×36, oracle ABI9 4:4:4 | PASS : pixels exacts, cadence/descripteurs/padding/propriétaires préservés, zéro construction de modèle |
| Configuration Spline36 large puis identité | PASS : 128×54→84×36 et64×32→64×32 avec plafond36, sans inférence ni construction |

Le cas RIFE utilise deux sources720p, Area identité → RIFE Fast×4 → SPAN1440p,
puis EOF. Les deux traces prouvent la même fusion native : 2 sources agrandies,
3 images synthétisées par warp, 1 préparation. Les compteurs restent à
3 requêtes RIFE, 5 spatiales, 2 conversions, 121651200 octets de pixels possédés
et zéro copie pixels CPU. Le contrôle concluant de fidélité n’a pas été répété.

Les premières observations d’intervalle ont donné 49,869 ms avant et 68,907 ms
après, après environ1,93s d’initialisation. Ce premier intervalle ne suffit pas
à conclure sur la performance. Une seule vérification temporelle complémentaire
a donc été demandée : même processus et mêmes sources, deux intervalles de
chauffe puis trois mesurés, sans nouvelles captures ni comparaison de qualité.
Résultat : médiane18,852ms avant et17,402ms après, compteurs identiques. Le
ralentissement du premier intervalle ne persiste pas dans ce contrôle. Les
fréquences SM variaient1080→1845MHz puis1845→2100MHz : aucun gain attribuable
au retrait n’est établi. Les preuves figurent dans `fusion-warm-summary.json`.
Arrêt après cette clarification, sans répétition des pixels déjà concluants.

L’oracle Spline36 compare la nouvelle étape au resize ABI9 inchangé sur la même
entrée YUV444P16 pleine plage BT.709. SHA256 sortie :
`38d44d4748284fe69612466ce4a8f0f0264049a518f9b7b0bbde0b96d0a6e6ed`.
Il vérifie l’algorithme natif et le raccord, pas une ancienne conversion420.
La migration fidèle des cas historiquement représentables doit conserver la
route native historique ; le nouveau pont444 ne promet pas des pixels identiques
à un aller-retour NV12/P010. L’affichage HDR physique, Windows/macOS et les autres
GPU n’ont pas été requalifiés. Les tests historiques FRUC restent des preuves,
pas une capacité active.

Une revue a repéré que la première traduction de hauteur Spline36 réutilisait
la boîte16:9 historique, incorrecte pour une nouvelle hauteur plafond sur une
vidéo large. La correction finale change uniquement la configuration de cet
étage : hauteur→pourcentage précis, ancienne hauteur supprimée. Le cas16:9
concluant produit la même géométrie et le chemin RIFE testé n’exécute pas cette
branche ; leurs pixels/timings ne sont pas répétés. Un contrôle de configuration
sans inférence a validé128×54→84×36 (l’ancien fit-box donnait64×26). Une
fixture64×24 était hors limiteAPI minimale32 : corrigée à64×32, elle contrôle
64×32→64×32 pour une hauteur plafond36, sans répéter le premier cas. L’identité
native retourne0 et n’expose pas Surface ; ce retour est accepté uniquement
pour le resize sans changement, déjà passé sans traitement dans apply. Résultat final PASS consigné dans
`spline36-geometry/summary.json`, avec le premier cas conservé dans
`spline36-geometry.log`.

## Sources et reproductibilité

Backend de départ : `463a0c73b6f2e77df09f908a3fef2bf5898cb5a1`.
Bundle de référence : `5217111b754412338fe94d236d80f39dcd42b957`.
Le SHA du nouveau backend est fixé après commit dans
`GPU-SOURCE.json/ordered_pipeline/backend_source`, sans numéro anticipé.
Les bibliothèques TRT/RTX et le bundle Windows ne changent pas.

| Objet | SHA256 |
| --- | --- |
| pipeline avant | `04733106673129bd508acee4f4068323cc63609aaffb35e331844b0b39140c28` |
| pipeline des contrôles pixels/timing | `b6045320cfaa6e7ccb9d41f27963e321a69b343ac4d2b34aedeb697d4313de79` |
| pipeline final, correction hauteur isolée | `f3157d0589279131e6952b2f251d1e46a74d0d550db3962f5a80f4705a363801` |
| fatbin inchangé | `1d9ca93cd2cc5e4ce5e944a5179d21687e7c9ab853f360f02bbfd96d19ca5b5d` |
| TRT inchangé | `c6f2fce428e2b3b931c7c4ffb7b589513ba9653fc6693ee20d1eeed5c21fa713` |
| entrée RGB | `ff88858e1830323b9a85de0719477f9a7fed36385ef4f32670122322388bc6fb` |
| configuration RIFE | `e451daaf39ef527737092bb207f19e09e0283c6071a3e0255dfe23f9142ac2eb` |

Preuves locales sous
`artifacts/performance/lots-20261017/lot-57-native/` :
`native-qualification.json`, `config-tests.log`, `configure.log`,
`build.log`, `fusion-before/summary.json`, `fusion-after/summary.json`,
traces associées, `spline36/summary.json`, `spline36-geometry/summary.json`,
configurations et scripts. Le premier binaire qualifié est conservé dans
`libaji_pipeline-pixels-timing-qualified.so` pour identifier les preuves
antérieures à la correction de géométrie. Le binaire du premier contrôle large
est conservé dans `libaji_pipeline-wide-geometry-qualified.so` ; la dernière
retouche concerne uniquement la configuration resize identité.
Les chemins absolus des entrées/bibliothèques sont enregistrés dans les JSON.
Les sorties GPU du retrait ont été exécutées par l’agent principal, dont
l’environnement donne accès au GPU ; le sous-agent a préparé les essais.

Le build utilise CMake/Ninja, CUDA13, architectures75/80/86/89/90/100/120 et
`AJI_VFX_ROOT=/usr/local/VideoFX`, cible `aji_pipeline` seule.
Le binaire garde le plancher glibc2.38/GLIBCXX3.4.30, sans RPATH local ni dépendance
FRUC. Le script `finalize_bundle.py` compare les sources committées aux sources
compilées avant d’inscrire le SHA exact et les hashes du paquet. Compiler les
autres architectures ne constitue pas une validation sur ces matériels.
