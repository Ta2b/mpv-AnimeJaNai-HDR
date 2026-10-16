# Lot 18 — distinguer les choix Quality

AH-13 / REF-03. Base player .48 `aa2afa039a36b46bc54ab75e7061fa45e56f1422`, Manager de référence `4c4af97f322706682c38ff4d630f4156b50999ef`. GPU pin `a1998637f2c3c243da8b7b9847f66eaaad1958ca` conservé. Aucune modification native, modèle, shader ou politique d’inférence.

## Fonction et utilité

Avant : bouton « Quality » sous « RIFE interpolation engine », sans distinction locale du preset spatial homonyme ou du verrouillage global. Après : « Temporal RIFE policy », « Full RIFE (Quality) » et « Fast (shortcuts) », notice du preset spatial, absence explicite du verrou global (AH-12), retiming/ensemble/précision distingués. Descriptions partagées `QualitySemantics`, consommées par le Manager et le catalogue de capacités. Documentation [QUALITE-MODES](../QUALITE-MODES.md).

La canonicalisation existante old→quality et new→fast est conservée dans cette même source partagée. Aucun changement silencieux de profil ou effacement du retiming configuré lorsque Quality l’ignore. Utilité : choix compréhensible et conforme au fichier/à la politique exécutée, pas d’accélération FPS.

## Essai court ciblé

`tests/quality-meaning/QualityProbe.csproj` référence chaque véritable projet Manager avant/après ; même probe, deux processus, mêmes fichiers de configuration privés. Le probe lit/sauvegarde les alias **old, quality, new, fast** par les méthodes de production et actionne les mêmes propriétés que les boutons UI. `meaning_check.py SPEC` contrôle les résultats par un exécutable compilant le **parser natif réel** `src/aji_conf.cpp` du backend livré, sans reproduire ce parser en Python.

Résultats : UI booléenne, valeur canonique sauvegardée et politique native correspondent dans les quatre cas ; les toggles sauvegardent aussi quality/fast correctement. Modèle spatial, preset Sharp, ensemble, facteur rationnel 5/2, ordre RIFE et retiming restent identiques avant/après. Le parser voit les mêmes choix depuis les fichiers initiaux et sauvegardés ; Quality garde le retiming configuré sans l’activer dans sa politique. Cinq descriptions nouvelles distinguent explicitement les trois sens, les approximations et la précision. Les bindings réels Avalonia compilent : **0 erreur, 44 avertissements existants**. La configuration de test est une fixture UI/config ; elle ne prétend pas exécuter le modèle `2x_fixture_fp16`.

Le code natif de choix/inférence est inchangé. Les preuves déjà exécutées du **lot 09** sont réutilisées : log `after.log` avec « Motion applied to the upscaled pictures » pour Fast, `after-quality.log` avec RIFE complet suivi de SPAN pour Quality ; cas Quality à plan identique exacts, sans retiming. Le nouveau test rattache les valeurs sauvegardées à ce même parser de production. Aucun essai d’inférence conclusif rejoué pour une modification de texte/canonicalisation équivalente ; aucune nouvelle qualification de moteur/OS déduite d’une compilation.

Artefacts : `artifacts/performance/lots-20261016/lot-18/` : sources de probe isolées, builds/logs, `meaning/summary.json`, fichiers initiaux/sauvegardés, valeurs du ViewModel et sorties du parser. Coûts ponctuels des deux processus dans le reçu ; aucun benchmark FPS. Aucun changement du calcul d’image introduit.

## Livraison

Source player partagée `c1217ca`, Manager `50ff160f534699015f01d4fd8beb8c3f53464a58` : workflow **38848948867 success**, quatre assets uploaded dans la release immuable `hdr-50ff160f534699015f01d4fd8beb8c3f53464a58`. Livraison player **3.8.0.49** poussée avec ce pin ; AH-13 reste In Progress jusqu’à vérification des trois plateformes/assets. AH-12/AH-14 restent ouverts pour le verrouillage global et le contrat de précision ; ces travaux distincts ne sont pas déclarés implémentés par la clarification. Le travail reprend sur la décision de migration AH-242 après le push, sans attendre la release.
