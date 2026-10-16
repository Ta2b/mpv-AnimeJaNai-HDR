# Lot 20 — workers persistants de soumission du moteur partagé

AH-262 sous AH-59 ; qualification/intégration native restante AH-263. Base .51 `51ce932230cf2a2f70ab3ba27f0f0a2c92facd98`. Référence native dans un worktree immuable distinct, candidat dans `lot-20-submission-workers-20261016`. Même compilateur/ORT1.24.1, modèles RIFE4.26/SPAN, machine, entrées, options et plans de tuiles pour chaque comparaison. Aucun backend utilisateur d’origine modifié.

## Changement et utilité

Les trois créations de `std::thread` par appel disparaissent : partage de tuiles, recouvrement motion/upscale et recouvrement RIFE complet/upscale. Une lane persistante par helper de modèle, créée à la demande, reçoit au plus un travail en attente en plus du travail courant. Le producteur de source suivant possède sa propre lane ; les lanes de tuiles et le pool pixels existant ont des files distinctes. Une soumission imbriquée sur sa propre lane s’exécute immédiatement, empêchant l’attente sur sa propre file.

Toutes les tâches de tuiles terminent avant la sortie du groupe, y compris en cas d’exception de création/soumission/caller ; les erreurs des helpers remontent après le drain. Les deux recouvrements attendent leur tâche même si RIFE échoue. Destruction : drain de la tâche en attente et join. La reconfiguration détruit les lanes des anciens modèles ; la lane de producteur du contexte peut rester inactive pour être réutilisée. Appels de l’ABI toujours sériels ; aucun nouveau contrat d’appel concurrent.

**Bénéfice établi : suppression des créations OS de threads à chaque paire**, avec files bornées et réutilisation. Utilité de gestion de ressources/prérequis de production, sans promesse de gain FPS. Les threads persistants conservent leur stack et éventuel état local jusqu’à destruction ; ils ne donnent pas une garantie de baisse de RAM. La politique Quality, les opérations numériques, modèles, retiming et tuilage ne changent pas.

## Essais courts ciblés

`submission_worker_check.cpp`, compilé avec le pool pixels de production : même thread sur deux soumissions, FIFO, soumission imbriquée immédiate, exception transmise puis lane réutilisable, producteur→tuile→pool pixels sans blocage, destruction qui termine la tâche. Exécution bornée par timeout10s, succès immédiat ; aucun essai répété.

`submission_workers_check.py SPEC` avec `submission_workers_probe.py` : **vrais RIFE et SPAN via ORT CPU**, sources RGB24 synthétiques avec strides/padding, premier intervalle exclu pour warm-up puis seulement deux nouvelles paires. Interposition `pthread_create` compte les créations réellement réussies après warm-up ; elle est identique avant/après. Toutes les sorties, y compris warm-up/endpoints et une source après reconfiguration, sont comparées byte à byte.

| Chemin nécessaire | Créations de thread avant→après pendant les paires mesurées | Sorties / différences |
|---|---:|---:|
| Quality RIFE complet, 128×72, un executor CPU | 2→0 | 8 / 0 octet |
| Fast motion, 128×72, source pré-upscalée | 2→0 | 8 / 0 octet |
| Fast motion + tuiles2×1, 256×72, deux executors CPU | 4→0 | 8 / 0 octet |

Le premier essai demandé tuilé à128×72 a révélé que le plan conservait une seule tuile, conformément à son halo56 : test de compteur mal anticipé, diagnostic conservé. Ses résultats réels Fast sont conclusifs et réutilisés, sans relancer le modèle. Seul le chemin de tuiles non encore exercé est testé à256×72 : stats confirment **deux executors et Tiles2×1 de184×72**, avec producteur imbriquant effectivement les travaux de tuiles. Aucun nouvel essai après ces conclusions.

Coûts muraux uniques des deux paires : Quality65,32→41,78 ms ; Fast1tuile44,92→41,99 ms ; Fast2tuiles143,59→139,12 ms. **Gain temporel/FPS non concluant** : séries courtes, charge du bureau/alimentation non mesurées ; aucun prolongement. Le bénéfice retenu est le compteur OS exact, pas un pourcentage de vitesse extrapolé. Les deux rapports individuels Quality exportés par l’outil du lot19 gardent ce contexte incomplet ; aucune paire déclarée comparable à tort.

RSS `getrusage` observé sur la vie du processus (configure/warm-up/reconfigure inclus) : Quality134873088→135249920 bytes, Fast1tuile145551360→141955072, Fast2tuiles192221184→176652288. **Ces valeurs ne sont pas des pics de la fenêtre mesurée** : elles sont reclassées dans `auxiliary_observations`, valeurs originales préservées dans `*.trace-original.json`. RAM/VRAM/énergie/température de la seule fenêtre restent non mesurées ; aucune baisse de mémoire soutenue revendiquée.

Artefacts : `artifacts/performance/lots-20261016/lot-20/` : builds séparés, unit, interposeur, trois comparaisons CPU, stats/NPZ/traces/rapports et reçus. Première commande CMake système indisponible, corrigée vers le CMake installé avant toute exécution de test. Source/ABI inchangées hors ordonnancement ; Quality reste exacte sur cette comparaison.

## Livraison et reste explicite

Source commun livré Linux/macOS avec la prochaine release .52 ; compilation CI des autres moteurs/OS ne constitue pas leur qualification matérielle. Le pin GPU spécialisé et ses DLL Windows restent ceux de .50 : la DLL AMD/Windows consomme encore le player source épinglé de son workflow backend. Son intégration des nouveaux workers puis sa qualification, ainsi que GPU/ANE/AMD natifs, sont **AH-263**, qui reste To Do. Le parent AH-59 demeure In Progress.

AH-262 clôt seulement l’intégration source partagée et sa qualification réelle Linux CPU, après publication vérifiée. Aucun essai Apple/AMD/Windows ni bénéfice sur ces matériels inventé. La source partagée compilée macOS apporte le changement, mais son essai natif reste ouvert. Aucun nouveau modèle ni accélération sans bénéfice établi ajouté.
