# Lot48 — étage TrueHDR réel, AH-317

17 octobre2026. Backend `9f2541e3dee1f159800b3a20c0e0729adc18491b`, Manager `f69589d7656ba5237cd29784e0c49f5106ff156b`, binaires `f638d0023d019efd2188cecb748238d4b00ef344`.
Cible exercée : Linux, RTX4070Ti, CUDA13.4/TensorRT11.3 pour RIFE, SDKMaxine
VideoFX1.3/TrueHDR1.2.3 installé dans/usr/local/VideoFX avec CUDA12.8/NPP/TRT10.
Les SDK/runtime propriétaires restent installés par l’utilisateur, sans redistribution.

## Changement et utilité

Avant : la catégorieHDR était grisée, conversion globale historique distincte,
aucun providerHDR dans les chaînes mixtes. Après : un étageHDR fixe NVIDIA
TrueHDR, activable avecSDK/provider présent, paramètres propres contraste,
saturation, gris moyen et pic400..2000nits. Limite d’unHDR sur tout le profil,
inactifs compris (garde déjà livrée.78/AH-323Done). HDR est obligatoirement le
dernier étage actif : RIFE/FRUC/upscalers actuels attendent duSDR. AjoutsSDR
insérés avant la queueHDR, aucun déplacement silencieux des étages existants.

La migration est explicite : ajouterHDR masque les anciens réglages globaux de
conversion et marque le profil `hdr_stage_controlled=yes`. RetirerHDR conserve
ce marqueur, donc ne réactive pas une conversion globale cachée. Un ancien
profil reste compatible tant qu’il n’adopte pasHDR. SDKabsent : bouton grisé ;
importSDKCore/feature demeure AH-318, distinct de la détection du SDKinstallé.

Le provider utilise un effet privé par pipeline/worker. CanoniqueYUV16SDR709→
RGBA8→SDKRGB10A2PQ2020→YUV444P16limité : SDK8bits en entrée,10bits effectifs en
sortie, compromis explicite ; ce n’est pas une conservationSDRbit-exact. Pixels
et métadonnées HDR ne sont libérés qu’après succèsSDK et clôtureGPU. Le pic est
une cible configurée, jamais un MaxCLLmesuré inventé. Les anciens lecteurs sont
refusés avant traitement si la négociation couleur est absente. UnHDRseul sur
sourcePQ/HLGBT2020 préserve pixels/couleur/métadonnées, sans seconde conversion.
Les buffersSDK comptent dans le budgetpixels ; workspace interneSDK exclu.

## Essais courts, références réutilisées

- Référence acquise avec adaptateurSDK indépendant : un gradient720p et patches
  primaires, contraste100/saturation100/gris50/pic1000 ; premier appel55.282ms
  incluantchargement. NoirRGB10[0,0,0], blanc[768,769,769]. Non rejouée.
- PackGPU exactement égal aux octetsRGBA8 de référence ; unpack contre
  arithmétique indépendante passe la tolérance fixée≤1codeYUV16 (maximum
  numérique non enregistré dans le premier log, donc non inventé).
- PipelineHDR : une imageEOF puis contrôle reset/nouvelle génération ; erreurs
  maximalesYUV16 [0,0] face à la référenceSDK convertie indépendamment.
  Tolérance préfixée1.05codeHDR10, flags[65,65], PTS/durée/owners/padding
  conservés, zéro copieCPU dans le provider. Appels59.405/52.095ms avecchargement,
  aucun gainFPS établi. Ancien lecteur refusé explicitement.
- Nouveau casHDRnatif seul : pixelsPQacquis réutilisés, sortiebit-exact,
  flagoriginal1 sansflagconversion, négociationPQ/HLGpréservée et pic0,
  PTS17/durée1/base1001/24000/owners exacts, zéro copieCPU. Pas de second essaiSDK.
- Lecteur réelNVDEC RIFEQuality×2→TrueHDR : trois sources720p→cinq sorties,
  PTS/durées/EOF exacts dans le log natif,1.666s ; flags[65,66,65,66,65].
- Nouveau cas coexistence RIFE×2→FRUC×2→TrueHDR : deux sources720p→cinq sorties,
  cadence×4,1.716s ; flags[65,68,66,68,65], PTS i×1001/96000 et dernière durée
  1001/24000 exacts à l’arrondi nanoseconde. ExportFFV1matroskaBT2020NC/PQ/
  BT2020/limité correct après correction du lecteur d’encodage qui omettait
  primaires/transfert. Le conteneur arrondit lesPTS à la milliseconde et ne
  conserve pas exactement la dernière durée : limite d’export explicitement
  distincte de la durée native vérifiée, aucun succès global d’export inventé.
- Manager :14 nouveaux contrôles ciblés disponibilité/catégorie/paramètres/
  migration/retrait/importexport/ordre/dernier fichier valide, tous réussis.
  Renduinspecté. Dernière compilation5.20s,0erreur. Anciennes suites non rejouées.
- ContrôleurLua/routage :9 nouveaux contrôles plus une garde de préchargement sans géométrie connue, requête seule ne retague pas,
  sortiePQeffective requise, aucune émulationSDRdouble, shaderutilisateur
  préservé, retrait/migrationHDRnatif corrects. Lanceurpipeline seul ajoute
  automatiquement les dépendances duSDKinstallé, vérificationmock sansvidéo.
- ConfigCPU : défauts, bornes inclusives,8 erreurs nouvelles, ordre actif,
  conservationinactif passent. Pile d’installation reconstruite depuis le
  mpvépinglé : filtre et encodeur obtenus exactement égaux aux sources compilées.

## Diagnostics exclus et limites

PremierpackSDK sur streamCUDA nondefault retournait succèsSDK mais noir ;
adaptateur de contrôle indépendant a isolé le stream requis. Correctiondefault
+fences, puis seulcandidat défaillant repris ; références conservées. SDK1.3
renvoieUNIMPLEMENTED pour ModelDirectory : ce seulparamètre optionnel ignore
ce statut, Load et les autres opérations restent obligatoires. Un lancement
sansNPP a échoué avanttraitement ; dépendances corrigées. Le cascoexistence
initial était refusé avantSDK carcadenceclipinconnue, puis option--fpsobsolète
refusée avantmédia ; seulcecas défaillant repris aveccontainer-fps-override.
HarnessLua corrigé pour notifier le cheminuser-data exact ; seuls contrôles
restants repris. CompatibilitéLua5.5 : variableforconst remplacée parlocal.

Conserver : utilité fonctionnelleHDR réel aprèsinterpolation et contrôle simple
parprofil ; aucun bénéficeFPS revendiqué. Qualification partielle matérielle :
affichageHDRphysique, autresGPU/API, Windows/macOSétageHDR non exercés, choix
indisponibles explicitementgrisés. DéfautsFRUCdéjàdiagnostiqués inchangés.
Artefacts : `artifacts/performance/lots-20261017/lot-48/`, scripts et logs
référencés dans le reçu `docs/jira/lot-48-hdr-stage-20261017.json`.
AH-317 reste In Progress jusqu’à publication vérifiée de.79.


Livraison vérifiée : 3.8.0.79, trois workflows success,17assets ; Manager EXE+DLL exacts, module/noyau HDR exacts dans l’overlayLinux, lecteur HDR réel présent dans le paquet Linux. AH-317 Done, commentaire10181. Reçu docs/jira/release-20261017-3.8.0.79.json.
