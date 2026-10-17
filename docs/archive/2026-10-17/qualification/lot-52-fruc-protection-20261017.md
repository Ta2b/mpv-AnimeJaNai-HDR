# Lot 52 — protection FRUC, AH-322 / AH-327

Le SDK FRUC produit directement les blocs sévères sur le faisceau signalé.
Le diagnostic RGBA/NV12 du lot46 est réutilisé, sans nouvel essai de format.
Une borne temporelle des pixels a été écartée : trous persistants et contours
altérés. Une fusion des sources supprime les trous mais crée des doubles
contours ; elle est également écartée. La solution conserve l’image précédente
quand la synthèse comporte un excès sévère de contours lumineux.

## Décision et compromis

Luma entière (54R+183G+19B+128)>>8 ; sommes des gradients horizontaux/verticaux
lorsque le maximum local des trois images dépasse96. Si l’énergie synthétique
est supérieure à2 fois le maximum des deux sources, répéter la source précédente.
Le calcul reste CUDA ; seuls24 octets de compteurs traversent vers le CPU.
Copie exacte dans le format natif quand les descripteurs correspondent, notamment
YUV16 du pipeline. Aucun mélange, modèle alternatif ou changement de PTS.

Une seule option FRUC « Protect against severe FRUC artifacts », activée par
défaut dans l’étage Fast, désactivable explicitement pour FRUC standard.
Le provider ancien ne peut pas activer silencieusement cette capacité ; la
protection peut être décochée pour rester en FRUC standard. Les originaux,
Quality/RIFE, modèles et noyaux Area/TrueHDR restent inchangés.
La fidélité spatiale du cas ciblé est restaurée au prix d’une perte locale de
fluidité ; ce n’est ni une réparation du SDK ni un détecteur universel.

## Essais strictement nécessaires

- Deux sorties SDK déjà acquises, aucun replay SDK : faisceau1920x1080, sommes
  [1246113,1433662,3952898], ratio2.757 : rejet. Mouvement ordinaire1280x720,
  [3312992,2896227,3462934], ratio1.045 : conservé. Oracle CPU indépendant
  exactement égal au GPU. Un intervalle GPU par cas :0.079872ms /0.032768ms.
  Coût isolé observé, aucune déduction de FPS ou accélération globale.
- Un nouveau couple faisceau protégé et EOF natifs : trois sorties flags1/140/1,
  originaux et synthèse remplacée bit-exacts aux sources YUV16. PTS0/20.5/41ms,
  durées20.5/20.5/41ms. Owners équilibrés, ROI/padding et descripteurs intacts,
  une prédiction SDK, une répétition de protection, zéro copie pixelCPU.
  Intervalle complet60.714ms à froid, EOF0.605ms : pas une comparaison FPS.
- Un passage réel NVDEC sur les deux mêmes sources acquises encodées sans perte :
  trois sorties FFV1, flags1/140/1, PTS et durées identiques. Première image et
  image protégée bit-exactes après décodage. Process0,1015.176ms wall incluant
  lancement et export. Aucune référence RIFE ni ancien essai concluant rejoué.
- ConfigCPU : yes/no acceptés, valeur inconnue refusée, cadence×2 inchangée.
  Six nouveaux contrôles Manager disponibilité/option/notice/persistance/ancien
  provider passent ; vrai rendu Avalonia inspecté. Le fixture initial oubliait
  deux fichiers requis : corrigé avant les succès, diagnostics conservés.

Les flags FRUC|REPEATED|PROTECTED=140 signalent la décision. Le compteur pipeline
fruc_repetitions comprend les répétitions SDK et de protection ; le provider
conserve ses compteurs SDK seuls et de protection distincts. Les constantes
exportées sont additives ; ABI9 et anciens createflags1 restent compatibles.

Artefacts : artifacts/performance/lots-20261017/lot-52-fruc-protection,
metric/native/player/ui/summary.json et logs. Sources média restent locales.
Backend4603933f, Manager2847c799, binaires92fb311a. Noyau pipeline byte-exact
1d9ca93c ; identités complètes dans le reçu Jira. Autres défauts, matériels/API
et présentation physique non qualifiés. Conserver pour l’utilité de fidélité
établie ; AH-322/AH-327 restent In Progress jusqu’à livraison vérifiée de.81.
