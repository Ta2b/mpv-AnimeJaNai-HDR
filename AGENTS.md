# Consignes de travail et de reprise

Lire [docs/ETAT-COURANT.md](docs/ETAT-COURANT.md), puis uniquement le ticket et les contrats nécessaires. Les demandes actuelles de l’utilisateur priment sur les archives. Projet Jira existant **AH** : https://tatoub.atlassian.net/jira/software/projects/AH/boards/2 ; vérifier la connexion au début de la session, ne pas réimporter le backlog.

- Préserver profils, médias, SDK, modèles et modifications utilisateur. Utiliser des checkouts isolés ; ne pas modifier le backend utilisateur d’origine. Aucun `git add -A`.
- Chaque ticket travaillé passe **In Progress** ; **Done** seulement après périmètre complet, qualification nécessaire et livraison vérifiée. Découper les reliquats en sous-tickets explicites, ne pas fermer un parent partiel.
- Validation proportionnée (précision utilisateur du 17 octobre) : ne pas imposer un test/benchmark à chaque optimisation. Revue ciblée et compilation peuvent suffire si le changement et son bénéfice sont établis par le code. Essai court avant/après seulement pour lever un doute réel sur rendu, stabilité ou performance ; mêmes entrées/réglages/machine. Arrêter dès conclusion suffisante, ne pas répéter un essai concluant.
- Pour documentation/UI/packaging sans changement moteur/vidéo : contrôles simples adaptés, sans mesures vidéo compliquées. Une compilation seule ne qualifie pas une optimisation moteur.
- Conserver la référence **Quality**. Toute approximation reste une variante **Fast** explicite. Distinguer bénéfice démontré par le code, gain attendu et gain mesuré ; un correctif de fidélité ou un prérequis peut avoir une utilité distincte des FPS. Matériel/API absents ou bruit : qualification partielle/non concluante, jamais validation inventée.
- Optimiser tous les OS/backends utiles sans forcer leur convergence : formats, précision, mémoire, kernels et langages peuvent différer selon les besoins matériels. Corriger les divergences utilisateur injustifiées ; garder les besoins propres à chaque moteur.
- Ne pas attendre les builds/releases : lancer, poursuivre une tâche indépendante, vérifier à sa fin. Strata optionnel s’il aide ; aucun travail concurrent GPU pendant une mesure.
- Consigner preuves courtes, limites, décision et reçus dans le ticket existant. Mettre à jour ETAT-COURANT en remplaçant les faits périmés ; ne pas empiler plusieurs « points courants ».

[Protocole](docs/PROTOCOLE-VALIDATION-FEATURES.md) · [Audit du matin](docs/AUDIT-GLOBAL-2026-10-17.md) · [Audit du soir](docs/AUDIT-PERFORMANCE-QUALITE-MANAGER-2026-10-17.md) · [Programme d’amélioration](docs/PROGRAMME-AMELIORATION-2026-10.md) · [Archives](docs/ARCHIVES.md). Les catalogues historiques sont des réservoirs de cas, jamais une batterie de tests obligatoire.
