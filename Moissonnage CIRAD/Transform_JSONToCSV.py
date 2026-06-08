import os
import json
import glob
import pandas as pd
import csv
from typing import Any, Dict, List, Optional

# --- CONFIGURATION (À adapter si nécessaire) ---
# Nom du répertoire contenant les fichiers JSON source (doit exister)
INPUT_DIR = "CIRAD_JSONs" 
# Nom du fichier de mapping généré
MAPPING_FILE = "MappingCIRAD.json"
# Nom du fichier CSV de sortie
OUTPUT_CSV_FILE = "output_mapping_CIRAD.csv"
# Séparateur demandé (Conservé comme demandé)
CSV_SEPARATOR = "‡"
# Séparateur interne pour la colonne 'keyword'
KEYWORD_SEPARATOR = "; " # Utilisé pour joindre les mots-clés
# ----------------------------------------------

def clean_json_data(data: Any) -> Any:
    # Parcourt récursivement la structure de données JSON et remplace les caractères '\n' par un espace.
    if isinstance(data, dict):
        return {k: clean_json_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [clean_json_data(element) for element in data]
    elif isinstance(data, str):
        # Remplacement du caractère de saut de ligne par un espace simple
        return data.replace('\n', ' ').replace('\r', ' ')
    else:
        return data
    
def get_value_by_path(data: Dict[str, Any], path: str) -> Any:
    # Navigue dans une structure JSON (dictionnaire/liste) en utilisant un chemin de points.
    if not path or not data: return None
    
    # Remplacer les notations [index] par .index pour une gestion séquentielle
    path_normalized = path.replace('[', '.').replace(']', '')
    keys = path_normalized.split('.')
    current_data = data
    
    for key in keys:
        if isinstance(current_data, dict) and key in current_data:
            current_data = current_data[key]
        elif isinstance(current_data, list) and key.isdigit():
            # Tenter d'accéder à un index de liste
            try:
                index = int(key)
                if 0 <= index < len(current_data):
                    current_data = current_data[index]
                else:
                    return None # Index hors limites
            except ValueError:
                return None # La clé n'est pas un index numérique valide
        else:
            return None # Chemin interrompu ou clé non trouvée
            
    return current_data

def find_in_array(data: Dict[str, Any], config: Dict[str, Any]) -> str:
    # Implémente la logique robuste pour les champs composés Dataverse (keyword, topicClassification, etc.).
    # Recherche un objet dans une liste via lookup_key/value, puis extrait une valeur
    # simple ou gère une liste de champs composés ('value.champ').
    
    array_path = config.get('array_path')
    lookup_key = config.get('lookup_key')
    lookup_value = config.get('lookup_value')
    extraction_key = config.get('extraction_key')
    csv_column_name = config.get('csv_column_name', 'UnknownColumn')
    
    # Vérification initiale de la configuration
    if not all([array_path, lookup_key, lookup_value, extraction_key]): 
        # print(f"    AVERTISSEMENT: Configuration 'find_in_array' incomplète pour {csv_column_name}")
        return ""
    
    # 1. Récupérer le tableau (liste d'objets)
    array_data = get_value_by_path(data, array_path)
    if not isinstance(array_data, list): 
        return ""
    
    results: List[str] = []
    
    # 2. Trouver l'objet cible dans le tableau (ex: l'objet dont 'typeName' = 'keyword')
    target_field = next(
        (item for item in array_data if isinstance(item, dict) and item.get(lookup_key) == lookup_value), 
        None
    )
    if not target_field: 
        return ""

    # 3. LOGIQUE ROBUSTE POUR CHAMPS COMPOSÉS (keyword, topicClassification, etc.)
    if extraction_key.startswith('value.'):
        internal_path = extraction_key[6:]
        compound_list = target_field.get('value', [])
        
        # Gérer le cas où 'value' n'est pas une liste (si c'est un seul élément)
        if not isinstance(compound_list, list):
            compound_list = [compound_list] if compound_list is not None else []
            
        # Parcourir les éléments composés (les dictionnaires de mots-clés)
        for compound_element in compound_list:
            if not isinstance(compound_element, dict): continue
                
            # Extraire la valeur finale (ex: 'keywordValue' dans 'value.keywordValue')
            final_value = get_value_by_path(compound_element, internal_path)
            
            if final_value is not None:
                results.append(str(final_value))
        
    # 4. LOGIQUE POUR LES CHAMPS SIMPLES (Non composés sous 'value')
    else:
        value_to_extract = get_value_by_path(target_field, extraction_key)
        if value_to_extract is not None:
            if isinstance(value_to_extract, list):
                results.extend([str(v) for v in value_to_extract])
            else:
                results.append(str(value_to_extract))

    # 5. Joindre tous les résultats
    if not results:
        return ""

    return KEYWORD_SEPARATOR.join([str(r).strip() for r in results if str(r).strip()]).strip()

def join_html_links_transformation(data: Dict[str, Any], config: Dict[str, Any]) -> str:
    
    # Crée une chaîne de liens HTML formatés pour chaque fichier dans le tableau spécifié,
    # en utilisant le point d'accès API pour le téléchargement.
    
    list_path = config.get('list_path')
    link_template = config.get('link_template', {})
    
    if not list_path or not link_template:
        return ""

    # 1. Récupérer le tableau (liste d'objets fichier)
    file_list = get_value_by_path(data, list_path)
    
    if not isinstance(file_list, list):
        return ""

    links: List[str] = []
    
    # Extraction des chemins pour la construction de l'URL
    base_url = link_template.get('base_url', '')
    # 'file_id_path' pointe vers 'datasetVersion.files.dataFile.id'
    file_id_path = link_template.get('file_id_path', '')
    # 'label_path' pointe vers 'datasetVersion.files.dataFile.filename'
    label_path = link_template.get('label_path', '') 

    for file_item in file_list:
        if not isinstance(file_item, dict):
            continue

        # Récupération des valeurs nécessaires via les chemins
        file_id = get_value_by_path(file_item, file_id_path)
        label = get_value_by_path(file_item, label_path)

        # On s'assure que l'ID et le label sont présents
        if file_id is not None and label:
            # Construction de l'URL spécifique Dataverse pour l'accès API (téléchargement)
            # Format demandé: BASE_URL/api/access/datafile/FILE_ID?gbrecs=true
            url = f"{base_url.rstrip('/')}/api/access/datafile/{file_id}?gbrecs=true"
            
            # Construction du lien HTML: <a href="URL" target="_blank">Label</a>
            html_link = f'<a href="{url}" target="_blank">{label}</a>'
            links.append(html_link)

    # Joindre tous les liens HTML avec un point-virgule et un espace
    return KEYWORD_SEPARATOR.join(links)

def join_compound_period_transformation(data: Dict[str, Any], mapping: Dict[str, Any]) -> str:
    """ Extrait les paires de dates (Début/Fin) d'un champ composé multiple. """
    array_path = mapping.get('array_path')
    lookup_key = mapping.get('lookup_key')
    lookup_value = mapping.get('lookup_value')
    if not all([array_path, lookup_key, lookup_value]): return ""
    array_data = get_value_by_path(data, array_path)
    if not isinstance(array_data, list): return ""
    periods = []
    for item in array_data:
        if isinstance(item, dict) and item.get(lookup_key) == lookup_value:
            raw_value = item.get('value')
            if isinstance(raw_value, list): periods = raw_value
            elif isinstance(raw_value, dict): periods = [raw_value]
            break
    if not periods: return ""
    formatted_periods = []
    for period in periods:
        if not isinstance(period, dict): continue 
        start_date_obj = period.get('timePeriodCoveredStart', {})
        start_date = start_date_obj.get('value')
        end_date_obj = period.get('timePeriodCoveredEnd', {})
        end_date = end_date_obj.get('value')
        if start_date and end_date:
            line = f"Start Date: {start_date} ; End Date: {end_date}"
            formatted_periods.append(line)
    return " - ".join(formatted_periods).strip()

def prepend_persistent_link(data: Dict[str, Any], extracted_value: str, csv_column_name: str) -> str:
    """ Construit le lien permanent (persistentUrl) et le préfixe au contenu extrait. """
    persistent_url = get_value_by_path(data, "persistentUrl")
    if not persistent_url: return extracted_value
    link_html = f'<a href="{persistent_url}" target="_blank">Lien vers les données</a>'
    # La colonne 'description' doit utiliser le séparateur <br>
    if csv_column_name in ['description', 'metas.liens.donnees']: separator = '<br>'
    else: return extracted_value
    if extracted_value:
        return f"{link_html}{separator}{extracted_value}"
    else:
        return link_html


def process_mapping(data: Dict[str, Any], mapping_config: List[Dict[str, str]]) -> Dict[str, Any]:
    # Applique la configuration de mapping à un seul objet JSON.
    # Gère l'accumulation de résultats pour les mêmes colonnes CSV (comme 'keyword').
    # Ajoute le préfixe 'CIRAD' à la colonne 'keyword'.
    
    mapped_data = {}
    
    for config in mapping_config:
        csv_column_name = config.get('csv_column_name')
        transformation = config.get('transformation')
        json_path = config.get('json_path')
        
        if not csv_column_name:
            continue

        value = None
        extracted_value = None 

        if transformation == 'find_in_array':
            # find_in_array retourne déjà une chaîne de caractères (str) jointe.
            value = find_in_array(data, config)
            # FIX pour le lien permanent : Assigner la valeur extraite à extracted_value
            extracted_value = value
        
        elif transformation == 'join_compound_period':
            value = join_compound_period_transformation(data, config)
            extracted_value = value
            
        elif transformation == 'join_html_links':
            # join_html_links_transformation retourne déjà une chaîne de caractères (str) jointe.
            value = join_html_links_transformation(data, config)

        elif transformation == 'constant':
            value = config.get('constant_value')
            extracted_value = value
            
        elif json_path:
            # Utilise le chemin direct
            value = get_value_by_path(data, json_path)
            if value is not None:
                if isinstance(value, list):
                    extracted_value = KEYWORD_SEPARATOR.join([str(v) for v in value])
                else:
                    extracted_value = str(value)
            
        
        # --- Traitement spécifique pour le lien permanent ---
        if extracted_value is not None:
            final_value_for_column = prepend_persistent_link(data, extracted_value, csv_column_name)
        else:
            final_value_for_column = value

        # --- Post-traitement et Accumulation (Fusion) des résultats ---
        
        current_value = ""
        
        if final_value_for_column is not None:
            if isinstance(final_value_for_column, list):
                current_value = KEYWORD_SEPARATOR.join([str(v) for v in final_value_for_column])
            else:
                current_value = str(final_value_for_column)
        
        current_value = current_value.strip()

        # Si la colonne existe déjà (accumulation), on concatène.
        if csv_column_name in mapped_data and mapped_data[csv_column_name]:
            if current_value:
                mapped_data[csv_column_name] = KEYWORD_SEPARATOR.join(
                    [mapped_data[csv_column_name], current_value]
                )
        else:
            # Première valeur trouvée
            mapped_data[csv_column_name] = current_value
            
            
    # --- LOGIQUE D'AJOUT DU PRÉFIXE 'CIRAD' APRÈS TOUTES LES FUSIONS ---
    
    for column_name, value in mapped_data.items():
        if column_name == "keyword":
            # Si la valeur est vide, on ajoute juste "CIRAD"
            if not value.strip():
                mapped_data[column_name] = "CIRAD"
            # Si la valeur contient déjà des mots-clés, on ajoute "CIRAD" suivi du séparateur
            else:
                prefix = "CIRAD" + KEYWORD_SEPARATOR
                # Vérifier si "CIRAD" est déjà présent au début pour éviter la duplication
                if not value.startswith("CIRAD"):
                    mapped_data[column_name] = prefix + value.strip()
                
    return mapped_data

def main():
    # Fonction principale pour lire les JSON, appliquer le mapping et générer le CSV.
    print("--- Démarrage de l'extraction JSON vers CSV ---")
    
    # 1. Lire la configuration de mapping
    try:
        with open(MAPPING_FILE, 'r', encoding='utf-8') as f:
            mapping_config = json.load(f)
        
        # --- CORRECTION DE L'ORDRE DES COLONNES (Garantir l'unicité de 'keyword') ---
        # Crée une liste de colonnes unique et ordonnée selon leur première apparition dans le mapping.
        
        df_columns_order_unique = []
        seen_columns = set()
        
        for item in mapping_config:
            col_name = item['csv_column_name']
            if col_name not in seen_columns:
                df_columns_order_unique.append(col_name)
                seen_columns.add(col_name)
                
        # La liste finale des colonnes à utiliser pour l'en-tête du CSV
        df_columns_order = df_columns_order_unique 
        # ----------------------------------------------------------------------------
        
        print(f"Mapping lu : {len(df_columns_order)} colonnes uniques à extraire.")

    except FileNotFoundError:
        print(f"ERREUR : Le fichier de mapping '{MAPPING_FILE}' est introuvable.")
        return
    except json.JSONDecodeError:
        print(f"ERREUR : Le fichier de mapping '{MAPPING_FILE}' n'est pas un JSON valide.")
        return

    # 2. Vérifier le répertoire source et trouver les fichiers
    if not os.path.isdir(INPUT_DIR):
        print(f"ERREUR : Le répertoire source '{INPUT_DIR}' est introuvable. Veuillez le créer et y placer les fichiers JSON.")
        return

    json_files = glob.glob(os.path.join(INPUT_DIR, '*.json'))
    if not json_files:
        print(f"AVERTISSEMENT : Aucun fichier JSON trouvé dans '{INPUT_DIR}'.")
        return

    print(f"{len(json_files)} fichiers JSON trouvés. Début du traitement...")
    all_data: List[Dict[str, str]] = []

    # 3. Parcourir et traiter chaque fichier JSON
    for i, file_path in enumerate(json_files):
        file_name = os.path.basename(file_path)
        # print(f"  [{i+1}/{len(json_files)}] Traitement : {file_name}")

        try:
            # 4. Charger, nettoyer et mapper les données
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Nettoyage des sauts de ligne, etc.
                data = clean_json_data(data)
            
            # Appliquer le mapping
            mapped_data = process_mapping(data, mapping_config)
            
            all_data.append(mapped_data)

        except json.JSONDecodeError:
            print(f"    AVERTISSEMENT : Le fichier '{file_name}' n'est pas un JSON valide et est ignoré.")
        except Exception as e:
            print(f"    ERREUR lors du traitement de '{file_name}' : {e}")


    if not all_data:
        print("Aucune donnée n'a pu être extraite. Sortie.")
        return

    # 5. ÉCRIRE le fichier CSV (avec le module natif)
    try:
        
        # --- Utilisation du module CSV natif pour un contrôle maximal ---
        with open(OUTPUT_CSV_FILE, 'w', newline='', encoding='utf-8') as csvfile:
            
            writer = csv.writer(
                csvfile, 
                delimiter=CSV_SEPARATOR,
                quotechar='\"',       
                quoting=csv.QUOTE_MINIMAL 
            )

            # Écrire l'en-tête (colonnes uniques et ordonnées)
            writer.writerow(df_columns_order)
            
            # Écrire les lignes de données
            for data_row in all_data:
                 # Construire la ligne en utilisant les clés uniques de df_columns_order
                 row_to_write = [data_row.get(col, '') for col in df_columns_order]
                 writer.writerow(row_to_write)
        
        # --- Fin de l'utilisation du module CSV natif ---

        print(f"\n--- ✅ Succès ---")
        print(f"Extraction terminée et fichier CSV généré : {os.path.abspath(OUTPUT_CSV_FILE)}")
        print(f"Séparateur utilisé : '{CSV_SEPARATOR}'")
        print(f"La colonne 'keyword' est unique et contient toutes les données fusionnées.")

    except Exception as e:
        print(f"ERREUR lors de l'écriture du fichier CSV : {e}")
        
if __name__ == "__main__":
    main()