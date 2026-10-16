# Manager : étages ordonnés — 16 octobre 2026

[AH-302](https://tatoub.atlassian.net/browse/AH-302), parentAH-297.
Source Manager e278b865df0db87ce61cb5a8b02dd20ac989825d, base50ff160 ; contrat partagé et readerAH-301
livrés dans3.8.0.72/c40496d. User worktrees backend/Manager d’origine préservés.

## Livraison et utilité

Éditeur réel dans les chaînes des profils personnalisés : ajouter/supprimer,
monter/descendre, activer/désactiver ; ID stable par étage, méthode/modèle,
runtime adapté à la méthode, facteur rationnel, politique, ensemble/SCD,
pré-resize spatial et chemins SDK FRUC. Affichage24→48→96 pour RIFE×2→FRUC×2.
Les nouveaux étages sont inactifs jusqu’au choix explicite ; les fichiers
manquants/paramètres incompatibles empêchent leur activation dans l’UI.

Choix raccordés : RIFE TensorRT, FRUC CUDA Fast×2 SDR8bits, ONNX TensorRT
spatial. Les autres méthodes du comparatif sont signalées comme intégrations
séparées ; aucun faux provider disponible. La présence des fichiers est un
état de préparation sur disque, pas une validation GPU/driver/couleur ; le
lecteur négocie les capacités effectives et refuse l’incompatible.

Les profils anciens gardent leurs commandes et arithmétiques. Conversion
lossless vers étages, projection des clés historiques seulement lorsque
possible sans perte : RIFE unique avant/après SR, mêmes options/politique.
Un mixte ne se réduit jamais silencieusement au toggle RIFE. Les versions
inconnues restent en lecture seule avec clés originales ; options inconnues
attachées à l’ID et conservées lors du déplacement. Commentaires/globals
personnels préservés. L’autosave est suspendue pendant une lecture/import,
puis le profil complet est écrit ; saisie invalide laisse le fichier valide.

L’utilité est le choix et l’édition du traitement cumulable auparavant absent.
Aucun code moteur/pixel ne change dans ce lot ; aucune mesure FPS ou qualité
complexe requise. Qualification moteur et compromis acquis dans les lots39/40.

## Contrôles strictement ciblés

- Contrôle headless du **vrai UserControl Avalonia** :16assertions réussies,
  migration5/2+SPAN, retour legacy, notification de facteur, addFRUC/inactivité,
  fichiers SDK requis, activation, déplacement/ID, cadence cumulée, export
  complet et profil/reload, option inconnue déplacée, version9 préservée,
  désactivation conservée, suppression et commentaires. Rendu PNG inspecté :
  textes, commandes, chemins, ordre et cadence lisibles. Les fichiers de cette
  fixture sont des stubs disque ; jamais chargés comme SDK/modèle/GPU.
- Persistance finale : constructeur et lecture autoSave ne modifient pas le
  profil actif pendant le chargement ; add4/remove3 supprime les anciennes clés ;
  import valide nom et trois étages complets ; vrais chemins SDK sérialisés.
  Ces six cas acquis ne sont pas rejoués après la dernière correction.
- Saisie vide d’un facteur : premier contrôle a révélé InvalidDataException
  non interceptée (ne dérive pas de IOException). Correction du handler
  autosave/export. Seul le cas invalide a été repris : aucun écrasement du
  facteur2 enregistré, erreur inline conservée, aucune exception non traitée.
  Un contrôle intermédiaire de notice globale a échoué : la détection des
  composants la rafraîchit, alors que le diagnostic de l’étage reste stable.
  Assertion ciblée sur ce diagnostic propre ; anciens logs conservés.
- Profil généré **par le Manager** avec propriétés éditables et vrais chemins
  SDK, options builder privées identiques aux plans qualifiés ; consommé par
  mpv/NVDEC réel : RIFE×2→FRUC×2→mêmeSPAN,2560×1440, limite4sorties encodées
  par framemd5, bons PTS/durées/provenances17/20/18/20. Le lecteur a préparé
  la rafale suivante avant la limite :8sorties natives/2intervalles,12retains/
  12releases/live0 à l’arrêt. Qualification de consommation, pas de vitesse.
- Premier client : tronquer des packets du mini-H264 a retiré la cadence connue,
  explicitement refusée par le lecteur. Source complète connue réutilisée,
  sortie bornée4. Deuxième assertion attendait exactement4sorties natives,
  mais mpv précharge une rafale ; **inspection offline du même run**, sans
  rejouer le GPU, a validé les8natives et4encodées. Aucun résultat moteur
  concluant n’a été rejoué pour adapter un harness.

## Preuves et limites

Artefacts privés sous artifacts/performance/lots-20261016/lot-41 :
ui/summary.json et stages.png ; persistence-check.log (six réussites avant le
cas invalide), invalid-edit-final.log/invalid-edit.json ; generation.log et
persistence/manager-generated.conf ; player/summary.json/mpv.log/frames.md5,
player-verify.log. Identité du profil généréSHA
 d1891130bf2dacd4175c75a105898d08997b62c193007235466fbf76b9914c7f.
Module pipeline321e52…/TRT953c8f…/FRUCf320f5… identiques aux livrés. Aucun
plan/poids utilisateur modifié. Tests publics dans le dépôt Manager :
tests/InterpolationStages et tests/InterpolationPersistence ; client lecteur
[manager_pipeline_player_check.py](../../tests/inference/manager_pipeline_player_check.py).

Qualification UI Linux headless ; Windows/macOS : compilation CI, pas de
qualification interactive/physique. Lecture mixte disponible seulement Linux
CUDA, limites SDR/Fast/méthodes/facteurs du reader inchangées. Aucun gain FPS,
aucune équivalence Quality FRUC, aucune garantie universelle annoncés.
Release3.8.0.73 en préparation ; AH-302 In Progress jusqu’à publication vérifiée.

Correctif de livraison :.73 Linux success, Windows404 car la branche source ne
déclenchait pas la publication Manager et le pin partagé restait ancien.
Manager2cc424c corrige uniquement player-source-ref versc40496d ; workflow
38962517292 success et quatre assets Win/Linux/Mac effectivement publiés.
UI/calculs inchangés. Release corrective3.8.0.74 référence ces binaires ;
AH-302 reste In Progress jusqu’à vérification complète. Aucun essai GPU répété.
