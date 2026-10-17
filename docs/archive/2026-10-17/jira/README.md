# Suivi Jira et reçus

Projet existant **AH**, tableau2 : https://tatoub.atlassian.net/jira/software/projects/AH/boards/2 . Connexion Atlassian à vérifier une fois au début de session. [Index](INDEX-JIRA.md), [état courant](../ETAT-COURANT.md), [audit](../AUDIT-GLOBAL-2026-10-17.md).

L’import initial est terminé. **Ne pas réimporter, recréer les clés ni rejouer les reçus historiques**, même si leur nom contient `pending`. Lire `sync_status` et vérifier l’état distant. `import-state.json` reste la correspondance initiale ; les issues et dépendances Jira sont la source vivante.

Au début d’un travail, In Progress. À la fin : résultat, commandes/empreintes utiles, limites et décision dans le ticket ; Done seulement pour un périmètre achevé et livré. Conserver les parents ouverts quand il reste des critères. Pas de tests vidéo pour une modification qui ne touche ni moteur ni flux.

Conserver ici les reçus JSON immuables `release-*`, `lot-*`, `manager-release-*`, commentaires/transitions et qualifications. Ne pas les réécrire pour refléter une livraison ultérieure. Les gros exports d’import redondants ont été archivés avec empreintes ; [récupération](../ARCHIVES.md).

`tools/export-jira-backlog.py` est un outil historique local, sans réseau, pas une procédure de reprise. Pour reproduire l’import ancien, extraire la TODO originale dans un répertoire séparé et fournir `--source` et `--output` vers un répertoire temporaire. Ne pas l’exécuter pour remplacer le backlog courant ou ses reçus.
