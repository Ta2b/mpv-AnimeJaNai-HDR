# AH350 — première frontière VideoToolbox→Metal

## Contrôle natif conclu

[CI39029415108](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/actions/runs/39029415108), candidate91632df517c185caafc9ff663be71aea1c4b0d85. macOS15.7.9/24G830arm64, AppleParavirtual/unified. VideoToolbox annonce et utilise un décodeur matériel dans cette VM ; cela ne décrit pas un GPUApple physique de l’utilisateur.

HEVCMain hvc1,256×144SDR709limité, véritableCVPixelBuffer décodé→plansR8/RG8 Metal. Comparaison complète des55 296octets Y/UV exacte, paddingdestination intact ; couleur/crop/PTS conservés. Fin synchrone : live_images0. Refus nonSDR709 etP010, bornes invalides sans écriture partielle, reset/deuxièmeimage : deuximports au total, pic1owner,3octets de contrôle sur le second import, tous owners libérés. [Reçu natif](native-receipt.json).

Dylib candidat SHA256 `f13aafd1fa090d0ed0f2998569f60c9e30893894e762f0914edd0a8a1e566298` ; header privé `7fb530a52c7e84b65d7c59b1a42df45f5bebedb7902a32cd522881dcd3306719`.

Investigations antérieures :39027604395 puis39028979843 sessions refusées-12902 avant tout cas ; fluxinitialRExt remplacé parMain (insuffisant).39029226467 confirme le refus même avec paramètres minimaux ; aucune API absente déduite. La dernière fixture prend seulement les vrais échantillons comprimés non vides/avecformat (scan borné de marqueurs), puis création réussie dès les contraintes complètes. Le reçu final ne conserve que l’inspection du dernier échantillon : ne pas prétendre disposer du nombre exact de marqueurs du premier appel.39029122843 a échoué à compiler un diagnostic utilisant une fonction non publique, retirée ; aucun résultat d’import issu de ce run.

## Vrai filtre mpv conclu

Le second job du même run39029415108 a compilé le vrai lecteur mpv19c0fcf89595e6ab33908299207c555b67e81558 avec le filtre candidat. FFmpeg9.0.1_1, libplacebo7.360.1, MoltenVK1.4.2 ; rendu de contrôlevo=null, décodageVideoToolbox réellement actif dans les sixprocessus référence/probe.

Troiscas distincts, troisimages chacun : NV12SDR709→3imports/0repli/9octets de contrôle ; matrice601→0import/3replis ; P010HDR→0import/3replis. Plans, PTS, format, dimensions et couleurs byte-référence exacts dans les troiscas. Le troisième resteyuv420p10le/PQBT2020, aucune troncature. Deuxresets parprocessus et liveowners0 àfermeture. [Reçu filtre](filter-receipt.json). Aucun cas concluant à répéter ; code natif et build-mpv identiques au candidat91632df après fusion .103.

Périmètre expérimental : apple-import-probe=yes, slot0 seulement, aucuneinférence. La voie normaleRGB24/videotoolbox-copy demeure en place, aucunEnumMETAL public activé. Une lecture GPU3octets/frame touche les plans, ce n’est pas une optimisationFPS ni un chemin complet sans copie. AH120 reste ouvert pour préparation fidèle et rendu macvk.

## Livraison vérifiée

[.104](../../jira/release-20261017-3.8.0.104.json) : modulef13aafd1 exact à la qualification, archiveMac80ab0fc3…,17programmes gérés conformes, consommateur présent dans le vrai mpv ; les troisCI release sont réussies. Aucun essai natif concluant rejoué.
