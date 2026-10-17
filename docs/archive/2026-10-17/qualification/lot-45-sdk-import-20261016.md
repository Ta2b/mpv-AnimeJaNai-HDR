# Lot45 — SDK FRUC et catégories fixes

AH-316 / AH-319. Référence Manager f5e2a0f ; candidat 98c8d27f0efcc7e8b2240ec1dd103457eb9d6b76.

L’éditeur propose quatre catégories fixes : Interpolation, Upscale, Downscale, HDR. Le choix de technologie est limité à sa catégorie ; un upscaler ne peut pas devenir RIFE/FRUC. FRUC est un choix d’Interpolation, grisé si son SDK/provider manque ou si son lecteur n’est pas livré sur la plateforme. Downscale/HDR restent désactivés jusqu’aux livrables distincts AH-315/317. Réglages avancés repliés, ajout en haut de la liste, état Ready compact. Les profils et options futures restent préservés.

Au premier lancement et ensuite dans Optional engines : lien NVIDIA et import du ZIP Optical Flow SDK. Installation locale atomique de libNvOFFRUC.so, CUDART11 et licences ; aucun chemin manuel ordinaire. Archives et anciens fichiers préservés ; versions gérées et chemins automatiques, bascule explicite des chemins personnalisés. NvTrueHDR est AH-318 ; l’import FRUC ne l’active pas.

Qualification strictement ciblée : vrai ZIP 5.0.7 SHA89b0923adc6f34fbe86e63cc17d5db452e34b945c03ba90d8e09bd1a0158e917, 16 contrôles import/UI/configuration/annulation/réparation, import 482,99 ms. Fichiers byte-exact (SDK04fcecca… / CUDART45da57e3…), licence conservée et source inchangée. Processus frais réel : provider FRUC create/query/destroy depuis les chemins gérés, 120,59 ms, succès. Aucun benchmark pixels répété : SDK/provider et calcul vidéo inchangés.

Catégories : 3 contrôles acquis avant un échec de sélection ; rebond de sélection corrigé par des objets de choix stables, puis reprise du seul cas échoué et des cas restants. Total 9 contrôles catégorie/UI/configuration, dont le véritable item popup grisé, plus 2 gardes SDK nouvelles (registre futur/symlink). Rendus assistant/éditeur compact inspectés. Compilation finale 0 erreur ; warnings préexistants. Logs/artefacts : artifacts/performance/lots-20261016/lot-45 ; fichiers lot-45-sdk-check.log, lot-45-category-check.log, lot-45-category-resume.log et lot-45-provider-setup.log.

Manager publié sur trois plateformes (workflow38971467600 success, 4 assets). Release lecteur 3.8.0.76 vérifiée : Windows/Linux/macOS success, 17 assets ; manifeste Windows/Linux pin98c8d27, EXE et trois DLL Windows byte-exact avec l’archive Manager immuable. AH-316 et AH-319 Done, commentaires10168/10169 ; reçu docs/jira/release-20261017-3.8.0.76.json. Diagnostic des artefacts FRUC distinct AH-320 ; choix des algorithmes de downscale AH-321. Aucun gain/qualité universel inventé.
