# Lot 49 — import du SDK TrueHDR, AH-318

L’assistant « Optional engines » accepte les archives ZIP, TGZ et tar.gz de
Maxine Core et de la feature TrueHDR, dans les deux ordres. Il installe les
bibliothèques Linux x64, dépendances et licences dans des composants privés
versionnés. Le SDK complet est assemblé par des liens contrôlés, sans recopier
Core à chaque ajout de feature. La sélection est atomique ; annuler ou refuser
une archive laisse la sélection précédente. Les archives et le SDK système
restent inchangés. Aucune bibliothèque NVIDIA n’est redistribuée.

Core seul ou feature seule restent incomplets. Le lecteur compatible est
également requis. Les chemins sont automatiques ; un profil ayant un ancien
chemin personnalisé le conserve jusqu’au bouton « Use installed TrueHDR SDK ».
Un override ANIMEJANAI_VFX_SDK reste prioritaire. Après import, rouvrir le
lecteur pour charger les nouveaux chemins de dépendances. Windows conserve
son runtime RTX Video et ne demande pas ce SDK Linux.

## Qualification courte

- Archive officielle Core Linux 1.3.0.0 de Downloads : SHA
  6fb57ff447203910f4e9ca4ede8ddb465921978b0b64fea591ec59c0f951ff05,
  import 24,630 s, environ 4,1 Gio de runtimes. ELF x64, alias internes requis,
  licences et état incomplet vérifiés ; aucune sélection HDR avec Core seul.
- Fichiers réels de la feature déjà installée dans /usr/local/VideoFX,
  réempaquetés dans un TGZ contrôlé : import 62,67 ms et assemblage complet.
  Ce fixture n’est pas l’archive NGC originale, absente localement.
- Quatorze nouvelles gardes : ordre feature puis Core, chemins dangereux,
  architecture ARM, NGX absent, licence seule, alias externes et cycles,
  CRC ZIP, annulation, fichier modifié, réparation dans une nouvelle version,
  registre futur et nettoyage des imports temporaires. Six succès initiaux
  réutilisés ; seulement les huit cas restants exécutés après correction du
  fixture d’alias qui visait à tort une bibliothèque non sélectionnée.
- Sept contrôles UI cumulés : bouton d’import, progression HDR seule et verrou
  d’import, Core incomplet, disponibilité et racine automatiques après les deux
  composants, ancien profil préservé, adoption en un clic, fin de progression.
  Rendu inspecté. Le harness headless async bloquait sa propre continuation ;
  corrigé avec pompe d’événements bornée, puis seuls les cinq cas restants repris.
- Lanceur simulé : SDK géré complet et dépendances trouvés automatiquement ;
  override utilisateur préservé. Aucun moteur ni flux vidéo modifié, donc aucun
  essai vidéo/GPU ni mesure FPS. Dernière compilation locale 3,22 s, zéro erreur.

La première sélection Core était trop large : alias inutiles hors runtime,
puis copies dans des sous-dossiers. Sélection resserrée sur les dossiers de
runtime ; seuls les imports Core défaillants repris. Les diagnostics restent
conservés. Un build --no-restore utilisait le graphe du projet de test ; restore
ciblé corrigé, sans relancer de contrôles concluants.

Manager b6ebb1a696d8e8bc04a960651784d3e4c662b1b2, workflow 38984776150 success,
quatre assets immuables vérifiés. Rapport/reçus dans
artifacts/performance/lots-20261017/lot-49 et docs/jira/lot-49-truehdr-import-20261017.json.
3.8.0.80 livrée et vérifiée : trois workflows success,17 assets non vides, deux
manifestes et EXE/DLL du Manager exacts. AH-318 Done, commentaire10183 ; reçu
docs/jira/release-20261017-3.8.0.80.json.

Le contrôle du layout de l’archive NGC originale est explicitement isolé dans
AH-324, To Do. Aucun compte, clé ou téléchargement authentifié automatique.
Les autres matériels/API et l’affichage HDR physique gardent leurs tickets.
