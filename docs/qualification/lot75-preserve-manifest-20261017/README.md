# AH-335 — profils conservés même sans manifeste local valide

Le17octobre2026. Lot updater/packaging, aucun moteur ou calcul vidéo modifié. [Reçu CPU](receipt.json) ; [défaut avant déjà établi par l’audit](before-audit.json), réutilisé sans rejouer la panne.

## Avant / après

Avant : ReadUserPreserve renvoyait un ensemble vide sans manifest.json valide. Lors d’une copie complète, une banque existante pouvait être remplacée par un défaut livré. Le témoin avec manifeste valide était conservé.

Après : un socle de réglages, banques, raccourcis et script-opts est toujours protégé ; un manifeste valide peut ajouter des chemins, sans retirer ce socle. Les scripts/shaders de l’application restent traités par leur inventaire de propriété distinct et peuvent être mis à jour. Les profils existants ne sont jamais remplacés ; les banques manquantes sont amorcées. Les dossiers de réglages absents sont aussi initialisés, ceux déjà présents restent en place.

Les liens utilisateur protégés, y compris une config pointant vers une cible absente, restent des liens. Le copiage de banques ne suit pas un lien de dossier vers des données externes. Un fichier utilisateur à amorcer utilise une copie sans overwrite : si une sauvegarde apparaît entre vérification et copie, l’update échoue sans la remplacer. Aucune nouvelle option UI.

## Contrôles suffisants

Vraies méthodes ApplyOver/CopyTree/ReadUserPreserve et inventaire ManagedProgramFiles exécutés dans de nouveaux dossiers :

- manifeste absent et JSON corrompu : sept configurations/banques conservent leurs octets ; nouveau profil manquant créé ; programme possédé actualisé, override Lua local conservé ;
- manifeste valide enrichi (casse/backslashes) : chemin supplémentaire conservé ;
- création initiale : valeurs par défaut et script-opts correctement amorcés ;
- Linux : lien de banque et lien de config cassé préservés, aucun fichier ajouté dans la cible externe ;
- SDK et modèle inconnus conservés ; sauvegarde d’input et copie brute du manifeste corrompu conservées par le code existant.

La première fixture avait mal échappé son JSON du cas valide personnalisé ; correction de la fixture, sans correction produit supplémentaire. Seuls ce cas et ceux restant à faire ont été exécutés ensuite ; états des cas déjà conclus relus sans répéter ApplyOver. L’ancien générateur de régressions était devenu non compilable (signature CopyTree/dépendances extraites) : raccord réparé et compilation passée, sans rejouer ses autres scénarios conclus.

Build updater Release .NET10/Linux passé, deux avertissements CA1416 préexistants dans les helpers AppImage, zéro erreur. Aucun test GPU/vidéo ou mesure FPS requis. Les sémantiques de locks/liens Windows ne sont pas présentées comme exécutées sur Linux.

## Sauvegarde et livraison

Ne pas créer un deuxième système de backup : ApplyAsync appelle déjà BackupInputConf et copie le manifeste brut vers manifest.prev.json avant ApplyOver. Ces appels inchangés sont extraits aussi dans la fixture. Les réglages et profils protégés restent à leur emplacement ; aucune migration de format n’est faite ici.

Livraison prévue .97 : vérifier CI/tag et nouveaux binaires updater dans les assets concernés. Les moteurs et programmes inchangés réutilisent .95/.96 ; aucune comparaison vidéo répétée. AH335 Done seulement après livraison vérifiée ; parentAH226 reste ouvert pour ses autres critères.
