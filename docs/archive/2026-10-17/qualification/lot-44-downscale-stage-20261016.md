# Lot44 — downscale indépendant, AH-315 In Progress

Backend624ff49, Managerd5e7cc4. Nouveau resize/area/CUDA avec target_height explicite, plafond720p par défaut, jamais activé automatiquement. Réduction seulement ; aspect arrondi au pixel le plus proche. Chaque point reste YUV444P16 sur GPU ; aucune conversionRGB8 ni modification de cadence. Sources plus petites inchangées. Éditeur déplacer/activer/hauteur, sans modèle ni faux mode ; anciens resize attachés préservés dans un expander de compatibilité.

Qualification acquise : CPU schéma/limites/facteur/options inconnues ; GPU1080→720 sur gradients/motifs fins/chroma, paire+EOF : référence indépendante3:2 max0code/2sources, tolérance préfixée1code16bit. PTS/EOF/ROI/padding/descripteurs/owners préservés,0copieCPU dans le provider,pool35,94Mo. Temps10,177ms premier intervalle/1,235ms EOF, sans portéeFPSRIFE. Lecteur réelNVDEC720p/plafond720 :3sources→3sorties, durée source et PTS exacts,0,805s. Le lancement initial sanslibnvinfer.so.11 est exclu, environnement corrigé. Manager9assertionsUI/configuration +1garde nouvelleautosa veheight invalide ; compilation3,57s,0erreur ; rendu inspecté.

Reste comparaison downscale→RIFE contreRIFE→downscale, contrôle de perte spatiale sur contenu animé, publication des binaires et release. ActivitéGPU concurrente/VRAM libre environ1Go : aucune mesureRIFE lancée ni gain inventé. Conserver ce ticket In Progress. Artefacts rootartifacts/performance/lots-20261016/lot-44, commentaireJira10161.


## Séparation complète dans le Manager courant —17octobre

Backend8d4ea4e, modulefinal7d168927… / kernel8a8a3f69… ; binaires2968000.
L’éditeur courant conserve SDK/import/catégories de.76 et l’avertissementFRUC.
Downscale a son bouton, une catégorie fixe et le filtreArea ; hauteur maximale
ou pourcentage exclusifs. Aucun réglage de réduction n’apparaît dans Upscale.
Les anciens resize restent actifs à l’identique tant que l’utilisateur ne
clique pas «Move imported resize into Downscale» ; cette action explicite garde
la position et annonce le passage au rééchantillonnageArea. L’ancienne réduction
peut donc être déplacée avant RIFE après conversion. Les pré-resize historiques
qui agrandissent ne sont pas convertis silencieusement en réduction.

Nouveaux contrôles intégrés :11 assertionsUI/configuration/migration et gardeHDR,
rendu inspecté ; pourcentage50%1080→540 contre moyenne indépendante2×2 : max0code
sur paire+EOF, tolérance1code16bit. PTS/ROI/padding/owners conservés, zéro copieCPU.
Nouvelles gardes natives : pourcentage0/101 et doublecible refusés, unHDR même
inactif réservé à tout le profil, deuxchaînes refusées, profils distincts indépendants.
Les cas du premier lot44 acquis ne sont pas répétés.

ComparaisonRIFEQuality426 sur trois mêmes sources1080p, trois sorties originales
et deux synthèses : RIFE1080→Area720 / Area720→RIFE720. Originaux+EOF bit-exact
entre ordres, durée6ticks/48000×1001 conservée, zéro copieCPU. Les synthèses ont
un écart moyen97.34codesYUV16 et max25373 localisé aux contours ; planche inspectée,
légères différences de contours/détails, aucune équivalence complète annoncée.
Le downscale est un choix utilisateur qui réduit le détail spatial et n’est
jamais ajouté/activé automatiquement. Temps valide d’un intervalle chaud :
43.83ms avant /23.07ms après ; un candidat initial8.85ms avait échoué sur une
attente de flags de provenance incorrecte. Cette variabilité et l’échantillon
court rendent le gainFPS non concluant ; l’utilité retenue est le contrôle réel
de la résolution avant interpolation. Référence acquise non rejouée ; seul
candidat repris après correction de l’oracle de provenance.

Lecteur réelNVDEC : trois sources1080p→Area720→RIFE720, cinq sorties720pYUV444P16,
PTS/durées/EOF corrects et flags[33,2,33,2,33]. Capture unique réanalysée sur disque
après correction de l’oracle qui oubliait la normalisation du start_ptsNUT
(aucun deuxième passage vidéo). Aucune durée globale de ce passage inventée.
Modulefinal ajoute seulement des gardes de configuration aux pixels qualifiés ;
kernel et TensorRT identiques aux comparaisons. Autres matériels/API et sortieHDR
physique non qualifiés. AH-315 et AH-323 restent In Progress jusqu’à livraison
vérifiée de.78 ; conversionHDR réelle reste AH-317, installationNvTrueHDR AH-318.


Quatre gardes d’import/contrat supplémentaires passent : deuxHDR dans une chaîne,
deuxchaînesHDR dans un profil, import dupliqué conservé et sauvegarde refusée,
unHDR dans chacun de deuxprofils distincts accepté. Aucun ancien contrôleUI rejoué.
Managerdf4e7f3 publié (workflow38976374521 success, quatreassets immuables).


Livraison17octobre : .78 vérifiée, trois workflows success,17assets ; Manager exact et module/fatbin dans l’overlayLinux identiques aux SHA qualifiés. AH-315 et AH-323 Done, commentaires10176/10177. HDR réel reste AH-317.
