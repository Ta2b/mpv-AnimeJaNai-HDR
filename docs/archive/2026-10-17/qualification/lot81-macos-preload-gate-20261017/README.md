# AH353 — Préchargement asynchrone sans première image hors profil

Régression trouvée après publication .100/.101, avant fermeture du ticket : le helper était asynchrone mais on_preloaded se poursuivait dès le retour Lua, donc la première image pouvait précéder l’application du profil. Le correctif conserve le hook avec defer(), puis cont() après application, refus ou délai borné ; Off/shutdown le libèrent aussi. Pas de nouvelle attente de build ou d’inférence, aucun modèle/SDK/profil utilisateur modifié.

[Reçu](receipt.json), vrai mpv Linux et contrôleur macOS, profil HDR seul (aucun moteur/GPU), helper privé volontairement retardé300ms. Première lecture réelle : base .101 slot0, candidat slot1, erreur du résolveur slot0/lecture normale débloquée. Les fichiers source sont inchangés. Un seul passage concluant avant/après/erreur ; ne pas le rejouer.

La première fixture ne trouvait pas hdr-tools avec --no-config, elle n’a jamais chargé les contrôleurs : aucun résultat de cette tentative n’a été utilisé. Fixture corrigée en exécutant dans son propre dossier privé, avec contrôle d’absence de Luaerror ; aucune configuration utilisateur lue.

La sémantique hook.defer/cont est documentée dans DOCS/man/lua.rst du mpv épinglé19c0fcf895. Ce test qualifie le raccord Lua/loader portable, pas les API vidéo macOS. Contrôles de syntaxe Lua/Python passés. Aucun benchmark vidéo, réglage numérique ou nouvelle qualification Metal/CoreML nécessaire ; les dylibs de .99 sont inchangés.

.102 doit livrer le contrôleur corrigé avant AH353/AH339 Done. Les publications .100/.101 et leurs contenus restent vérifiés, mais ne suffisent pas à clôturer ce défaut de préchargement.
