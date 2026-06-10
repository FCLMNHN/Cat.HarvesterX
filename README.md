# OAI-PMH & Dataverse Harvester Pipeline

Ce script Python (`Extract_JSONs_Sequence.py`) est un outil complet de moissonnage de métadonnées conçu pour interagir avec des entrepôts de données comme **Recherche Data Gouv** ou **PANGAEA**. Il automatise l'ensemble du workflow, de la récupération initiale jusqu'au déclenchement du moissonneur distant "CSV par FTP" de la plateforme Huwise via l'API Automation.
V 5.0
---

## V 5.0

## Fonctionnalités Principales

* **Multi-Protocole** : Supporte le moissonnage via le protocole **OAI-PMH** (XML) et l'API **Search de Dataverse** (JSON Direct).
* **Normalisation XML** : Nettoyage automatique des fichiers XML pour corriger les erreurs d'encodage (ex: `&amp;amp;`).
* **Extraction Intelligente** : Téléchargement des métadonnées JSON à partir de l'attribut `directApiCall` ou par reconstruction d'URL via DOI (pour PANGAEA).
* **Filtrage des jeux de données moissonnées** : Possibilité de filtrer les jeux de données par :
    - Set ;
    - Paramètre de requête de type q= dans l'URL ;
    - Subtree ;
    - Subject.
* **Pipeline de Post-traitement** :
    1. Nettoyage automatique des anciens fichiers dans les répertoires des entrepôts moissonnés.
    2. Exécution d'un script de transformation externe `Transform_JSONToCSV.py`.
    3. Transfert des résultats vers un serveur **FTP** sécurisé.
    4. Lancement du moissonneur "CSV via FTP" de la plateforme Huwise via l'API Automation.

---

## Configuration

Le script gère une liste préconfigurée d'entrepôts dans le dictionnaire `available_repositories`.

### Paramètres de connexion
Les variables suivantes doivent être configurées dans le script pour assurer le fonctionnement du pipeline complet :

* **FTP** : `FTP_HOST`, `FTP_USER`, `FTP_PASSWORD`.
* **API Automation PNDB** : `API_TOKEN` (nécessaire pour l'étape finale de notification).

### Dépendances Python
Le script utilise principalement des bibliothèques standards, à l'exception de `requests` :
```bash
pip install requests
