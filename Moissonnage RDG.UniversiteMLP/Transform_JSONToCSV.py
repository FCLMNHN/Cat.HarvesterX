import os
import json
import glob
import pandas as pd
import csv
from typing import Any, Dict, List, Optional

# Nom du répertoire contenant les fichiers JSON source (doit exister)
INPUT_DIR = "INRAE_XML_2025-11-14" 
# Nom du fichier de mapping généré
MAPPING_FILE = "INRAE171120251533.json"
# Nom du fichier CSV de sortie
OUTPUT_CSV_FILE = "output_mapping_inrae.csv"
# Séparateur du fichier CSV généré
CSV_SEPARATOR = "‡"
# Séparateur interne pour la colonne 'keyword'
KEYWORD_SEPARATOR = "; " # Utilisé pour joindre les mots-clés
# ----------------------------------------------

def clean_json_data(data: Any) -> Any:
    """ Parcourt récursivement la structure de données JSON et remplace les caractères '\n' par un espace. """
    if isinstance(data, dict):
        return {k: clean_json_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [clean_json_data(element) for element in data]
    elif isinstance(data, str):
        return data.replace('\n', ' ').replace('\r', ' ')
    else:
        return data
    
def get_value_by_path(data: Dict[str, Any], path: str) -> Any:
    """ Navigue dans une structure JSON (dictionnaire/liste) en utilisant un chemin de points. """
    if not path or not data: return None
    current_data = data
    parts = path.split('.')
    for part in parts:
        if not current_data: return None
        if '[' in part and ']' in part:
            key, index_str = part.split('[')
            index = int(index_str.split(']')[0])
            if key:
                if isinstance(current_data, dict) and key in current_data: current_data = current_data[key]
                else: return None
            if isinstance(current_data, list) and len(current_data) > index: current_data = current_data[index]
            else: return None
        elif isinstance(current_data, dict) and part in current_data:
            current_data = current_data[part]
        elif isinstance(current_data, list):
            if current_data and isinstance(current_data[0], dict) and part in current_data[0]:
                 return [get_value_by_path(item, part) for item in current_data if isinstance(item, dict) and part in item]
            else: return None
        else: return None
    return current_data


def find_in_array_transformation(data: Dict[str, Any], mapping: Dict[str, Any]) -> str:
    """ Implémente la logique robuste pour les champs composés Dataverse (keyword, topicClassification). """
    array_path = mapping.get('array_path')
    lookup_key = mapping.get('lookup_key')
    lookup_value = mapping.get('lookup_value')
    extraction_key = mapping.get('extraction_key')
    if not all([array_path, lookup_key, lookup_value, extraction_key]): return ""
    array_data = get_value_by_path(data, array_path)
    if not isinstance(array_data, list): return ""
    results = []
    target_field = next((item for item in array_data if isinstance(item, dict) and item.get(lookup_key) == lookup_value), None)
    if not target_field: return ""

    # Logique pour champs composés (keyword, topicClassification)
    if extraction_key.startswith('value.'):
        internal_path = extraction_key[6:]
        compound_list = target_field.get('value', [])
        if not isinstance(compound_list, list):
            compound_list = [compound_list] if compound_list is not None else []
            
        for compound_element in compound_list:
            if not isinstance(compound_element, dict): continue
            final_value = get_value_by_path(compound_element, internal_path)
            if final_value is not None:
                results.append(str(final_value))
        
        return KEYWORD_SEPARATOR.join([str(r).strip() for r in results if str(r).strip()]).strip()

    # Logique pour les autres champs 'find_in_array'
    else:
        value_to_extract = get_value_by_path(target_field, extraction_key)
        if value_to_extract is not None:
            if isinstance(value_to_extract, list):
                results.extend([str(v) for v in value_to_extract])
            else:
                results.append(str(value_to_extract))

    return KEYWORD_SEPARATOR.join([str(r).strip() for r in results if str(r).strip()]).strip()


def join_html_links_transformation(data: Dict[str, Any], mapping: Dict[str, Any]) -> str:
    """ Extrait les liens (URL et label) et les formate en liens HTML. """
    list_path = mapping.get('list_path')
    link_template = mapping.get('link_template', {})
    list_data = get_value_by_path(data, list_path)
    if not list_data or not isinstance(list_data, list): return ""
    base_url = link_template.get('base_url', '')
    url_path = link_template.get('url_path', '')
    label_path = link_template.get('label_path', '')
    links: List[str] = []
    for item in list_data:
        if isinstance(item, dict):
            url_suffix = get_value_by_path(item, url_path)
            label = get_value_by_path(item, label_path)
            if url_suffix and label:
                full_url = f"{base_url}{url_suffix}" if base_url else url_suffix
                html_link = f'<a href="{full_url}" target="_blank">{label}</a>'
                links.append(html_link)
    return "<br>".join(links).strip()

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
    if csv_column_name in ['description', 'metas.liens.donnees']: separator = '<br>'
    else: return extracted_value
    if extracted_value:
        return f"{link_html}{separator}{extracted_value}"
    else:
        return link_html

def process_mapping(data: Dict[str, Any], mapping_config: List[Dict[str, Any]]) -> Dict[str, str]:
    """ Applique tous les mappings pour un seul fichier JSON, gère la déduplication et la priorité INRAE. """
    result = {}
    all_extracted_keywords: List[str] = []
    
    for mapping in mapping_config:
        csv_column_name = mapping.get('csv_column_name')
        if csv_column_name:
            csv_column_name = csv_column_name.strip()
        
        if not csv_column_name: continue
        
        transformation = mapping.get('transformation', 'simple')
        extracted_value = ""

        # Logique d'extraction
        if transformation == 'simple':
            json_path = mapping.get('json_path')
            value = get_value_by_path(data, json_path)
            extracted_value = str(value).strip() if value is not None else ""
        elif transformation in ['find_in_array', 'find_in_composite_array']:
            extracted_value = find_in_array_transformation(data, mapping)
        elif transformation == 'join_html_links':
            extracted_value = join_html_links_transformation(data, mapping)
        elif transformation == 'join_compound_period':
            extracted_value = join_compound_period_transformation(data, mapping)
        elif transformation == 'join_list_with_comma':
             json_path = mapping.get('json_path')
             list_data = get_value_by_path(data, json_path)
             if isinstance(list_data, list):
                 extracted_value = KEYWORD_SEPARATOR.join([str(item) for item in list_data if item is not None])
             else:
                 extracted_value = str(list_data).strip() if list_data is not None else ""
        elif transformation == 'constant':
            extracted_value = mapping.get('constant_value', '')

        # Etape 1: Accumulation des mots-clés
        if csv_column_name == 'keyword':
            if extracted_value:
                # Sépare les mots-clés si la valeur extraite en contient plusieurs 
                keywords_from_mapping = [kw.strip() for kw in extracted_value.split(KEYWORD_SEPARATOR.strip()) if kw.strip()]
                all_extracted_keywords.extend(keywords_from_mapping)
            continue
        
        if extracted_value is not None:
            if csv_column_name in ['description', 'metas.liens.donnees']:
                extracted_value = prepend_persistent_link(data, extracted_value, csv_column_name)
      
        result[csv_column_name] = extracted_value

    # Etape 2: POST-PROCESSING FINAL pour 'keyword' (Priorisation et Déduplication) ---
    
    MOT_CLE_PRIORITAIRE = "INRAE" 

    final_keywords_list = []
    other_keywords = []
    seen_upper = set() 
    mot_cle_prioritaire_trouve = None 

    for kw in all_extracted_keywords:
        kw_upper = kw.upper()
        
        if kw_upper not in seen_upper:
            # 1. Identifier et stocker le mot-clé prioritaire (en conservant sa casse originale)
            if kw_upper == MOT_CLE_PRIORITAIRE.upper():
                mot_cle_prioritaire_trouve = kw
            else:
                other_keywords.append(kw)
            seen_upper.add(kw_upper) # Ajout ici pour éviter la déduplication du mot-clé prioritaire s'il apparaît en minuscules

    # 2. Trier les autres mots-clés par ordre alphabétique
    other_keywords.sort()

    # 3. Construire la liste finale en plaçant le mot-clé prioritaire en premier
    if mot_cle_prioritaire_trouve:
        final_keywords_list.append(mot_cle_prioritaire_trouve)
    
    # 4. Ajouter les autres mots-clés triés
    final_keywords_list.extend(other_keywords)
            
    # Construction de la chaîne finale
    final_keyword_value = KEYWORD_SEPARATOR.join(final_keywords_list)
        
    result['keyword'] = final_keyword_value.strip()
    
    # Log de debug
    print(f"    -> [DEBUG] Valeur 'keyword' générée : {result['keyword']}")

    return result


def main():
    """ Fonction principale pour charger le mapping, traiter les fichiers et générer le CSV. """
    print(f"--- Démarrage de l'extracteur JSON vers CSV ---")

    # 1. Charger le fichier de mapping
    try:
        with open(MAPPING_FILE, 'r', encoding='utf-8') as f:
            mapping_config = json.load(f)
    except FileNotFoundError:
        print(f"ERREUR : Le fichier de mapping '{MAPPING_FILE}' est introuvable.")
        return
    except json.JSONDecodeError:
        print(f"ERREUR : Le fichier de mapping '{MAPPING_FILE}' n'est pas un JSON valide.")
        return

    # 2. Déterminer les colonnes du CSV à partir du mapping
    csv_columns = []
    seen_columns = set()
    for m in mapping_config:
        col_name = m.get('csv_column_name')
        if col_name:
            col_name_stripped = col_name.strip() 
            if col_name_stripped not in seen_columns:
                 csv_columns.append(col_name_stripped)
                 seen_columns.add(col_name_stripped)
             
    keyword_column_name = 'keyword'
    if keyword_column_name not in seen_columns:
        csv_columns.append(keyword_column_name)
    else:
        csv_columns = list(dict.fromkeys(csv_columns)) 

    if not csv_columns:
        print("AVERTISSEMENT : Aucune colonne CSV valide trouvée.")
        return

    # 3. Trouver les fichiers JSON source
    search_path = os.path.join(INPUT_DIR, '*.json')
    json_files = glob.glob(search_path)
    
    if not json_files:
        print(f"ERREUR : Aucun fichier JSON trouvé dans le répertoire '{INPUT_DIR}'.")
        return

    print(f"Fichiers JSON trouvés : {len(json_files)}")
    all_data = []

    # 4. Traiter chaque fichier JSON
    for i, file_path in enumerate(json_files):
        file_name = os.path.basename(file_path)
        print(f"  Traitement {i+1}/{len(json_files)} : {file_name}")

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                data = clean_json_data(data)
            
            # Correction de l'erreur de syntaxe précédente
            mapped_data = process_mapping(data, mapping_config) 
            all_data.append(mapped_data)

        except json.JSONDecodeError:
            print(f"    AVERTISSEMENT : Le fichier '{file_name}' n'est pas un JSON valide et est ignoré.")
        except Exception as e:
            print(f"    ERREUR lors du traitement de '{file_name}' : {e}")

    if not all_data:
        print("Aucune donnée n'a pu être extraite. Sortie.")
        return

    # 5. Créer le DataFrame et écrire le fichier CSV
    try:
        df = pd.DataFrame(all_data, columns=csv_columns)
        
        # Écriture du CSV avec le module natif
        with open(OUTPUT_CSV_FILE, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(
                csvfile, 
                delimiter=CSV_SEPARATOR,
                quotechar='"',       
                quoting=csv.QUOTE_MINIMAL 
            )

            writer.writerow(csv_columns)
            
            for row in df.itertuples(index=False):
                writer.writerow(list(row)) 
        
        print(f"\n--- ✅ Succès ---")
        print(f"Extraction terminée et fichier CSV généré : {os.path.abspath(OUTPUT_CSV_FILE)}")
        print(f"Séparateur utilisé : '{CSV_SEPARATOR}'")
        print(f"Veuillez vérifier la colonne 'keyword' dans {OUTPUT_CSV_FILE}.")

    except Exception as e:
        print(f"ERREUR lors de l'écriture du fichier CSV : {e}")


if __name__ == "__main__":
    main()