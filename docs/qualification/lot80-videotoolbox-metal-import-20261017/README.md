# AH350 — première frontière VideoToolbox→Metal

## Contrôle natif conclu

[CI39029415108](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/actions/runs/39029415108), candidate91632df517c185caafc9ff663be71aea1c4b0d85. macOS15.7.9/24G830arm64, AppleParavirtual/unified. VideoToolbox annonce et utilise un décodeur matériel dans cette VM ; cela ne décrit pas un GPUApple physique de l’utilisateur.

HEVCMain hvc1,256×144SDR709limité, véritableCVPixelBuffer décodé→plansR8/RG8 Metal. Comparaison complète des55 296octets Y/UV exacte, paddingdestination intact ; couleur/crop/PTS conservés. Fin synchrone : live_images0. Refus nonSDR709 etP010, bornes invalides sans écriture partielle, reset/deuxièmeimage : deuximports au total, pic1owner,3octets de contrôle sur le second import, tous owners libérés. [Reçu natif](native-receipt.json).

Dylib candidat SHA256 `f13aafd1fa090d0ed0f2998569f60c9e30893894e762f0914edd0a8a1e566298` ; header privé `7fb530a52c7e84b65d7c59b1a42df45f5bebedb7902a32cd522881dcd3306719`.

Investigations antérieures :39027604395 puis39028979843 sessions refusées-12902 avant tout cas ; fluxinitialRExt remplacé parMain (insuffisant).39029226467 confirme le refus même avec paramètres minimaux ; aucune API absente déduite. La dernière fixture prend seulement les vrais échantillons comprimés non vides/avecformat (scan borné de marqueurs), puis création réussie dès les contraintes complètes. Le reçu final ne conserve que l’inspection du dernier échantillon : ne pas prétendre disposer du nombre exact de marqueurs du premier appel.39029122843 a échoué à compiler un diagnostic utilisant une fonction non publique, retirée ; aucun résultat d’import issu de ce run.

## Consommateur mpv encore à vérifier

Le jobfiltre du même run compile le vrai lecteur, puis compare troisimages par cas :NV12SDR709import, matrice601repli, P010HDRrepli sans troncature. À la fin d’une tâche indépendante vérifier ce job, sans attendre/relancer. Le modefilter_only réutilise le natif concluant39029415108 si le filtre seul doit être corrigé ; ne pas refaire les cas natifs conclus avec les mêmes octets.

Périmètre expérimental : apple-import-probe=yes, slot0 seulement, aucuneinférence. La voie normaleRGB24/videotoolbox-copy demeure en place, aucunEnumMETAL public activé. Une lecture GPU3octets/frame touche les plans, ce n’est pas une optimisationFPS ni un chemin complet sans copie. AH120 reste ouvert pour préparation fidèle et rendu macvk.
