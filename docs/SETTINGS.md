# Simplification des réglages du Manager

## Demande du 12 octobre 2026

Regrouper les paramètres d'écran dans une seule section, indépendante du
constructeur du GPU, et retirer les valeurs personnelles des réglages par
défaut. Alléger la page Global Settings tout en conservant l'accès aux réglages
avancés. L'ajout de Vulkan sous Windows est reporté explicitement : les moteurs
existants ne changent pas pendant ce travail.

## Constats dans les sources

- `HdrSettings.cs` et `MainWindow.axaml` présentent deux écrans, NVIDIA et
  AMD/Intel, alors que luminosité, gamut et type de dalle décrivent l'écran.
- Le Manager et les options du lecteur imposent par défaut 1 000 nits, OLED
  et Display P3 sur NVIDIA. AMD impose aussi Display P3 et l'activation HDR
  Windows, contrairement au suivi de Windows choisi sur NVIDIA.
- Les profils Windows embarqués démarrent sur des slots personnels différents
  (4 sur NVIDIA, 3 sur AMD), avec les journaux activés.
- Le grading est activé avec des valeurs correspondant au préréglage Vivid.
  La conversion SDR vers HDR est activée par défaut.
- Le choix OLED actuel ne constitue pas une détection de la technologie de
  dalle. Aucun type d'écran ne doit être déduit du fabricant du GPU.

## Direction retenue

Une seule description d'écran ; luminosité et gamut automatiques, OLED décoché
par défaut en l'absence d'une détection fiable. Suivre l'état HDR Windows par
défaut ; la sortie Linux suit les préférences du compositeur. Les paramètres
du moteur d'inférence restent distincts des propriétés physiques de l'écran.
Les nouvelles valeurs par défaut concernent les installations neuves : les
réglages déjà enregistrés ne doivent pas être réinitialisés silencieusement.

La migration des anciennes clés par GPU conserve les valeurs explicites
et les commentaires. La page et le lecteur doivent adopter le même schéma et
les mêmes valeurs par défaut ; une modification uniquement visuelle ne suffit
pas. Les réglages détaillés sont repliés dans cette même page.

## Choix confirmés

- Conversion SDR vers HDR activée lorsque la sortie HDR du système est active.
- Grading activé dès le départ ; Natural sert de base modérée aux valeurs neuves.
- AnimeJaNai Performance actif sans RIFE au premier démarrage.

## Implémentation

Les options d'écran communes sont `windows_hdr`, `display_peak`, `display_gamut`
et `display_oled`. Les anciennes clés restent acceptées quand la clé commune
correspondante est absente. Le Manager importe la description de l'ancienne
banque active et conserve les anciennes lignes pour ne pas perdre l'autre
configuration. Les défauts de grading sont alignés entre Manager et lecteur.
Windows reçoit un profil Performance en slot 9 (base 720p), Linux conserve son
profil Vulkan 1 (base 360p). Les deux utilisent SPAN Performance Standard et
n'activent pas RIFE. La synchronisation des banques préservera les choix existants.

Sous Linux, `linux_hdr_output=auto` laisse mpv utiliser la description préférée
du compositeur Wayland. Le grading exige toujours une sortie PQ négociée et
le support strict du lecteur ; la source seule ne suffit jamais à activer HDR.
Les choix explicites SDR/PQ restent disponibles. Le HDR physique n'est pas
certifié par ces modifications.

## Validation automatisée et fonctionnelle

- LuaJIT : 239 assertions réussies, dont les 161 originales, 53 Linux et 25
  nouveaux cas de réglages communs. Les tests historiques gardent une fixture
  explicite de l’ancienne configuration ; les nouveaux défauts sont vérifiés
  séparément, y compris sans fichier et avec des clés invalides.
- Manager : 13 cas de persistance/migration réussis. Les anciens réglages et
  commentaires restent présents ; une édition manuelle survit à une détection
  GPU tardive. Les clés communes sont prioritaires, OLED décoché compris.
- Interface Avalonia/Skia : 13 vérifications réussies, liaisons et clavier,
  enregistrement/relecture et rendu en 1120 et 780 pixels de largeur.
  Captures : `artifacts/settings-manager-ui.png` et `.narrow.png`.
- Le Manager compile pour Linux et Windows. L’exécution Windows n’a pas été
  effectuée ici. Les mêmes tests sont ajoutés aux jobs indépendants de CI.
- Le portable `3.8.0.8-linux-test.3` démarre en Performance sans RIFE sur AMD,
  ouvre le Manager et sauvegarde/recharge ses réglages par socket. Les cinq
  clips, changements de profil, recherches et désactivation passent.
  Rapport : `artifacts/settings-linux-runtime.json`.
- Les 23 tests hors ligne de mise à jour AppRun passent : réglages et banques
  existants sont préservés. Aucun relevé sous la charge concurrente Twitch
  ne sert de référence de performance.

Les tests physiques NVIDIA et HDR sur écran compatible restent distincts.
Le backend natif n’est pas modifié par cette simplification. Aucun moteur
Vulkan Windows ni remplacement des fichiers de release Windows n’est ajouté.

## Paquets prêts à essayer

Le portable et l’AppImage `3.8.0.8-linux-test.3` passent les essais Wayland sur
RX 6500. L’AppImage confirme le démarrage en profil 1 sans RIFE et une sortie
`auto` négociée SDR, avec grading inactif dans cet état. Le Manager s’ouvre,
sauvegarde et recharge les réglages avec commentaires conservés ; les profils,
recherches, changements de résolution et nettoyage IPC passent dans les deux
formats. Rapport AppImage : `artifacts/settings-appimage-runtime.json`.

Le Manager Windows est également fourni en ZIP avec ses DLL natives. Il a été
compilé, mais pas exécuté sous Windows dans cette session. Les noms d’assets et
la publication Windows restent inchangés ; aucune release n’est publiée ici.
Les sources du Manager sont désormais publiées dans leur propre dépôt. Les
workflows utilisent des références immuables et ne rejouent plus de patch.
La publication Windows/Linux est décrite dans [RELEASE.md](RELEASE.md).

## Publication et nettoyage des workflows

La version suivante est 3.8.0.9. Windows et Linux utilisent le même numéro,
avec des fichiers propres à chaque plateforme dans une seule release.
Linux reste identifié comme expérimental dans les notes. Les tests sont
réutilisés avant publication, les builds ne publient pas individuellement et
l’assemblage du Manager télécharge le runtime HDR complet avec ses bibliothèques
natives. Les sources des deux dépôts sont liées par des références immuables.
Les anciens workflows amont inutilisés et le patch inter-dépôts sont supprimés.
