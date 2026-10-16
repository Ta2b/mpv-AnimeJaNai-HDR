# Rapports de mesures comparables — AH-25

Outil de développement à la demande, Python 3.10+ sans dépendance externe :

```sh
python3 tools/performance-report.py avant.json apres.json --output comparaison.json
python3 tools/performance-report.py mesure.json --output rapport.json
```

Les traces sont les **mesures brutes du collecteur**, pas des logs contenant seulement une moyenne. L’outil ne lance pas d’inférence ni de capteur et ne modifie aucun profil. Un fichier existant n’est pas remplacé. Le rapport conserve SHA-256 du collecteur fourni et du script exporteur ; il est local, sans envoi automatique. Les mesures/identités sont déclarées par le collecteur et doivent être contrôlées pendant la qualification de la feature.

## Périmètres distincts

| `scope` | Mesure | Ce qu’elle ne démontre pas |
|---|---|---|
| `network_resident` | Réseau avec tenseurs déjà résidents | Coût decode/conversions/chaîne/affichage |
| `chain_offscreen` | Chaîne complète sans présentation | Rafraîchissements physiques, compositeur et VRR |
| `playback_presented` | Lecture avec présentation observée par le collecteur | Une complétion filtre seule ne constitue pas une observation de l’écran |

Le couple avant/après doit avoir même scope, unité d’échantillon, source d’horloge, politique de warm-up, média, modèles, réglages de base, contrat de sortie, machine/runtime/pilote et état de session/charge du bureau/alimentation. Les versions de code sont distinctes dans la provenance. Pour une ablation, identifier séparément le seul traitement off/on et empreinter les autres réglages inchangés ; ne pas masquer un changement de modèle/précision/scaler dans cette ablation. Un contexte absent ou inconnu, même imbriqué dans la liste des modèles, interdit la comparaison ; le rapport d’une seule trace reste exportable avec cette limite explicite.

## Contrat de trace v1

Champs requis : `schema: animejanai.measurements.v1`, `data_origin: measurement|fixture`, scope ci-dessus, `sample_unit`, `timing_source`, `warmup_policy`, `provenance` (versions/SHA du code réellement mesuré). `identity` contient `media_sha256`, `models_sha256`, `settings_sha256`, `machine_id`, `runtime`, `driver`, `output_contract` ; `session` contient `desktop_load`, `player_state`, `power_mode`. Les inconnues sont null/`unknown` et restent signalées.

`window` fournit **wall_seconds et media_seconds du seul intervalle mesuré**, avec `excludes_compile_warmup: true`. Les durées média doivent tenir compte des PTS/durées réelles et de la vitesse choisie ; elles ne se déduisent pas d’un nombre de frames en VFR. Le débit est `media_seconds / wall_seconds`, sans sommer des durées GPU qui peuvent se chevaucher.

`samples` fournit les observations individuelles `{phase: measure|compile|warmup, completed: true|false, duration_ms: N}`. Compilation/warm-up et sorties non terminées sont comptés séparément et exclus des percentiles. Médiane/P95/P99/max/moyenne utilisent l’interpolation linéaire R7, avec le nombre d’observations. Un seul échantillon ne certifie pas une distribution stable. Une trace sans mesure terminée est refusée.

`pairs`, facultatif, contient des coûts par paire **réellement mesurés** `{phase, completed, cost_ms}` et reçoit sa distribution séparée. Ne pas reconstruire un coût de paire en sommant des latences concurrentes. En particulier, le `Recent ms` natif partagé multiplie déjà la moyenne par le facteur RIFE : ne pas appliquer ce facteur une seconde fois. Ce champ moyen seul ne permet pas de fabriquer P95/P99.

`resources`, facultatif : `allocations_count`, `peak_ram_bytes`, `peak_vram_bytes`, `energy_joules`, chacun `{value, source}`. Compteurs/bytes entiers non négatifs ; énergie = delta de compteur sur le même intervalle, puissance moyenne = énergie / temps mural. Une absence devient `not_measured`, jamais zéro. `temperatures_celsius` contient `{wall_seconds, value, source}` croissants dans la fenêtre : min/max/delta/pente et durée couverte sont descriptifs. L’exporteur ne déduit **jamais** une stabilité thermique soutenue d’un bref relevé.

`quality`, facultatif, conserve le constat documenté du collecteur ; aucune conclusion d’image ne provient des temps. La comparaison fournit des écarts descriptifs et garde `gain_established: false` : conclusion sur bruit, qualité et utilité à consigner dans le ticket de la feature après l’essai ciblé. Cet outil n’autorise pas à refaire une série concluante ni à prolonger automatiquement un essai bruité.

Exemples exécutables : les JSON produits par `tests/performance/report_check.py` sont explicitement des **fixtures**, avec statistiques et unités vérifiables à la main. Ne pas les citer comme performances du lecteur ou de la machine.
