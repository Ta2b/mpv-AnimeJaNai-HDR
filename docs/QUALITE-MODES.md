# Trois sens de « Quality »

Le **preset spatial Quality** choisit une chaîne et des modèles d’upscale. Son nom ne sélectionne pas la politique d’interpolation ni un verrouillage global de fidélité. Standard/Sharp sont des choix de modèles spatiaux distincts.

La **politique temporelle Full RIFE (Quality)** (`rife_engine=quality`, ancien alias `old`) conserve les prédictions RIFE complètes pour les instants intermédiaires, avec l’upscale et les règles de coupe configurés. **Fast (shortcuts)** (`rife_engine=fast`, ancien alias `new`) permet les raccourcis disponibles sur le backend : réutilisation des sources upscalées/mouvement et approximations déclarées. Ils peuvent modifier contours ou temporalité. Les deux gardent les optimisations d’exécution applicables. Une option Fast ne prouve pas que tous les raccourcis sont disponibles sur chaque moteur ; consulter la chaîne effectivement activée.

Le **verrouillage global de fidélité** n’est pas encore disponible (AH-12). Le mode temporel Quality ne fige donc pas à lui seul le modèle, la résolution, le scaler final, le facteur RIFE, les traitements HDR ou la génération externe de frames. Le libellé de l’interface signale cette limite ; aucun profil existant n’est transformé silencieusement.

Le **retiming des dessins tenus** répartit le mouvement sur la durée d’un dessin répété. Ce choix change le rendu temporel, reste distinct de l’ensemble et est ignoré par la politique temporelle Quality. L’option enregistrée n’est pas effacée lors d’un passage en Quality, pour préserver le choix lors du retour en Fast ; son activation effective dépend du backend. Redémarrer la lecture après modification.

**Ensemble** sélectionne un autre modèle RIFE lorsque le moteur le supporte. Il est indépendant du choix temporel Quality/Fast. Des poids FP16 ne prouvent ni la précision de tous les opérateurs/accumulateurs, ni une équivalence numérique entre moteurs. Choisir Quality ne change pas la politique de précision du modèle. Le contrat détaillé par opérateur reste AH-14.

La source des descriptions est `QualitySemantics` dans `AnimeJaNaiPlatform/PlatformServices.cs`, partagée avec le Manager et le catalogue CLI `--capabilities`. Les alias sont lus, puis sauvegardés sous les valeurs canoniques `quality`/`fast`, comme avant ce changement. Les prédictions, modèles, options de précision, ensemble, facteur et règles de coupe ne sont pas modifiés par cette clarification.
