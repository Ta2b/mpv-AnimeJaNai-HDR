# Archives documentaires

Tri du 17 octobre 2026 au soir (ticket « Documentation : un état d'une page pour humains »). Le jeu vivant de `docs/` est réduit aux contrats, procédures, audits et au programme d'amélioration. Tout le reste est déplacé sous `docs/archive/2026-10-17/` et reste dans l'historique Git ; le dernier commit qui contenait ces fichiers à leur emplacement d'origine est `95b1735c054f66233f0bdf124af704d4465dd463` (3.8.0.106).

| Déplacé vers `docs/archive/2026-10-17/` | Contenu | Usage |
|---|---|---|
| `qualification/` | 158 fichiers : rapports de lot, reçus natifs, patches de recherche (lot 58 à 83) | Preuves datées citées par les tickets Jira Done ; ne pas rejouer |
| `jira/` | Reçus de release 3.8.0.72 à .106, exports et vérifications d'import du backlog, snapshot de l'audit du matin (`audit-reworked`, `coverage-check`, `handoff`) | Traçabilité des livraisons ; les statuts vivants sont dans Jira |
| `reprise/20261017/` | 30 guides de reprise par ticket, patches AH-344 à AH-346 et preuves | Le texte des guides est aussi dans les descriptions Jira ; les liens `blob/hdr-3.8/docs/reprise/...` des tickets pointent désormais ici |
| `chantiers/` | CHANTIER-GPU-SPECIALISE, CHANTIER-PERFORMANCE-RELAIS, CHANTIER-RIFE-165HZ, ETAT-PROJET, OPTIMISATIONS-MOTEURS, REPRISE, AMD-PERFORMANCE | Récits historiques du 13 au 15 octobre, remplacés par ETAT-COURANT, les audits et le programme |

Retrouver un fichier à son ancien chemin :

```sh
git show 95b1735:docs/qualification/lot-55-rife-fusion-20261017.md
```

Le dossier `docs/archive/` peut être supprimé entièrement (`git rm -r docs/archive`) sans perte : décision du propriétaire du dépôt. Les notes de release historiques de `.github/release-notes/` pointent encore vers les anciens chemins ; elles décrivent des releases déjà publiées et ne sont pas modifiées.

Le checkout de travail de l'IDE (`~/Documents/mpv-AnimeJaNai-HDR`, branche `perf/specialized-gpu-20261014`) contient d'anciennes copies non suivies de ces documents ainsi que `comparatif_interpolation_anime_2026-10-16.md`, dont le contenu est repris dans `PROGRAMME-AMELIORATION-2026-10.md`.
