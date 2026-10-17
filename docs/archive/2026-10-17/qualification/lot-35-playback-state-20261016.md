# Lot 35 — États de lecture et priorité de la pause utilisateur

[AH-285](https://tatoub.atlassian.net/browse/AH-285), sous [AH-37](https://tatoub.atlassian.net/browse/AH-37) ; intégration/qualification natives restantes [AH-286](https://tatoub.atlassian.net/browse/AH-286). Base3.8.0.66 `ac407bca07771db0bf9da0b4e37ce245fea895cd`. Aucun calcul moteur ni pixel n'est modifié : contrôles du comportement de lecture, sans mesure GPU ni batterie vidéo.

## Problème et résultat

Le moniteur possédait un booléen `we_paused`, vérifié seulement au poll de sa lecture du log. Une reprise puis une nouvelle pause entre deux polls laissaient ce booléen actif ; la complétion réécrivait `pause=false`, annulant la pause demandée. Le témoin réel reproduit ce défaut.

Un contrôleur commun sépare désormais l'intention utilisateur des demandes automatiques possédées par leurs émetteurs. La fin d'une demande libère uniquement celle-ci ; elle ne réécrit pas l'intention utilisateur. Une reprise manuelle pendant une demande est respectée. Plusieurs émetteurs peuvent demander une préparation ou un remplissage sans se libérer mutuellement. Chaque demande/complétion appartient à la génération du média ; les générations précédentes sont refusées.

Réducteur portable `portable_config/hdr-tools/playback-state.lua`, chargé par `scripts/animejanai_playback.lua`. Moniteur de build raccordé ; observation `pause`/`seeking`, événements de fichier, messages d'intention et état `user-data/animejanai-playback`. Les bindings gérés portés vers Linux passent par l'intention explicite. Windows conserve ses bindings natifs en attendant AH-286 ; macOS embarque le contrôleur/module, sa qualification native restant ouverte.

| État | Raison et comportement |
|---|---|
| SEEK | Seek mpv en cours ; l'intention utilisateur est conservée. |
| ERREUR | Cause explicite du lecteur/préparateur ; une pause utilisateur reste effective. |
| PAUSE_UTILISATEUR | Intention utilisateur active, indépendante des demandes automatiques. |
| PREPARATION | Préparation active ou attente de fichier. Une demande peut être observée sans pause avec `auto_pause=no`. |
| REMPLISSAGE | Demande de remplissage active ; aucun seuil ni politique mémoire implicite. |
| LECTURE | Fichier chargé, sans cause précédente. |

Ordre de présentation du diagnostic : SEEK, ERREUR, PAUSE_UTILISATEUR, préparation, remplissage, lecture. L'intention utilisateur reste un champ indépendant même lorsqu'un seek/une erreur est l'état visible. Aucun tick périodique ni scan vidéo ajouté au contrôleur ; le moniteur conserve son poll existant.

## Contrat de contrôle

Messages mpv : `aji-playback-hold OWNER preparation|refill GENERATION [yes|no]`, `aji-playback-release OWNER GENERATION`, `aji-playback-error OWNER REASON GENERATION`, `aji-playback-user-pause yes|no|toggle`. `no` en dernier argument de hold enregistre une préparation sans pause automatique. Owner identifie une demande possédée ; les émetteurs réutilisant un owner dans une génération doivent sérialiser ses renouvellements/complétions. Une génération explicite invalide est refusée ; omettre celle-ci désigne volontairement le média courant. Le moniteur utilise toujours une génération explicite.

État version1 : état/raison, génération, intention utilisateur, pause automatique/effective, reprise manuelle, owners triés et compteur de transitions. Start/end-file libèrent les demandes de l'ancien média ; le moniteur ignore son ancien snapshot disque jusqu'à changement ou preuve fraîche de configure. Les logs de configure permettent aussi une nouvelle publication au contenu identique. Le module est dans les dossiers déjà gérés par l'overlay, avec copie explicite pour macOS.

Une écriture externe idempotente `set pause=yes` alors que le lecteur est déjà automatiquement en pause ne porte pas d'événement d'intention distinct. Pour exprimer cette intention, employer le message `aji-playback-user-pause yes`. Les bindings Linux gérés le font ; l'intégration des clients natifs et de leurs intentions reste AH-286. Les changements externes effectifs de propriété sont aussi observés. Aucun protocole ne prétend deviner une intention sans événement.

## Vérifications courtes et conclusion

- Réducteur Lua : préparation/release, pause explicite pendant pause automatique, reprise puis pause entre deux polls, reprise manuelle, owners indépendants, remplissage, seek, erreur, changement de génération, rejet d'une ancienne complétion et préparation non bloquante. PASS.
- Contrat du moniteur existant adapté : lecture absente/vide ne signifie pas fin de build ; erreur immédiate et complétion libèrent leur demande. PASS.
- **Session mpv Linux réelle**, entrée identique H264128×72/12images, sans filtre d'inférence ni GPU, poll0.2s. Témoin .66 : après reprise puis pause et complétion, `pause=false` (défaut). Candidat : `pause=true`, état `PAUSE_UTILISATEUR`, aucun owner restant. Contrôle principal0.460s/0.463s : durées descriptives, aucun gain FPS recherché. Puis API réelle remplissage → pause explicite → release, ancienne génération et erreur : pause maintenue, état final ERREUR/cause targeted-error, exit0.
- Chargement automatique depuis une configuration temporaire contenant les deux scripts et le module, sans réglages utilisateur. Shell macOS syntaxiquement valide ; chemins d'overlay/module contrôlés. La première tentative utilisait `get_script_directory` sur un script simple (nil) ; correction vers `~~/hdr-tools`. La suivante utilisait `--no-config`, qui supprime la résolution `~~` : setup corrigé en configuration temporaire normale. Ces essais invalides ne qualifient rien ; le témoin concluant a été réutilisé et seul le candidat repris.

**Conserver** : correction fonctionnelle établie et contrat d'états utilisé par un préparateur existant. Aucun rendu, poids, Quality/Fast ni moteur modifié ; aucun benchmark GPU justifié. Les seuils/plafonds et la synchronisation A/V/sous-titres restent AH-39/40/41, sans les déclarer implémentés par une simple pause. Windows/macOS ne sont pas qualifiés nativement ici : AH-286 et parent AH-37 restent ouverts.

Commandes : `lua tests/player/playback_state_check.lua "$PWD"`, `lua tests/observability/stats_lua_check.lua "$PWD"` ; [session réelle](../../tests/player/playback_state_runtime_check.py), `python3 tests/player/playback_state_runtime_check.py SPEC.json` avec `mpv,input,out`, référence .66 fixée, receipts protégeant les essais concluants. Artefacts `artifacts/performance/lots-20261016/lot-35/`, `before-result.json`, `on-result.json`, `runtime-summary.json`, journaux et configuration temporaire. Aucun service Strata modifié ; aucune inférence déléguée.

**3.8.0.67 publiée**, source `3f09cd036a218d600fd285c74924d9e8a069d530` ; trois workflows success,15assets uploaded et versions vérifiées. Overlay/digest et sources livrées identiques au contrôle Linux ; bindings d’intention présents. AH-285 **Done**, clôture10124 ; parent AH-37/AH-286 ouverts.
