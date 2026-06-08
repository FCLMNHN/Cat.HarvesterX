import requests
import xml.etree.ElementTree as ET
import os
import time
import argparse
import datetime
import re
import json
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any
import subprocess
import ftplib
import glob


ET.register_namespace('', "http://www.openarchives.org/OAI/2.0/")
ET.register_namespace('oai', "http://www.openarchives.org/OAI/2.0/")
ET.register_namespace('oai_dc', "http://www.openarchives.org/OAI/2.0/oai_dc/")
ET.register_namespace('dc', "http://purl.org/dc/elements/1.1/")
ET.register_namespace('xsi', "http://www.w3.org/2001/XMLSchema-instance")



def harvest_all_oai_records(base_url, metadata_prefix, set_spec, use_set, output_dir, output_filename="all_oai_records.xml"):
    """
    Moissonne l'ensemble des enregistrements d'un entrepôt OAI-PMH en gérant les jetons de reprise.
    """
    all_records_xml = ET.Element("{http://www.openarchives.org/OAI/2.0/}OAI-PMH")

    resumption_token = None
    records_count = 0
    request_number = 1

    print(f"\n{'='*60}")
    print(f"ÉTAPE 1 : Moissonnage OAI-PMH")
    print(f"{'='*60}")
    print(f"URL de base : {base_url}")
    print(f"Prefix      : {metadata_prefix}")
    if use_set:
        print(f"Set         : '{set_spec}'")
    else:
        print("Set         : (paramètre omis, tous les enregistrements)")

    while True:
        params = {"verb": "ListRecords"}

        if resumption_token:
            params["resumptionToken"] = resumption_token
            print(f"Requête {request_number}: Utilisation du jeton de reprise '{resumption_token}'")
        else:
            params["metadataPrefix"] = metadata_prefix
            if use_set and set_spec:
                params["set"] = set_spec
            print(f"Requête {request_number}: Première requête.")

        try:
            response = requests.get(base_url, params=params)
            response.raise_for_status()

            root = ET.fromstring(response.content)

            error_element = root.find(".//{http://www.openarchives.org/OAI/2.0/}error")
            if error_element is not None:
                print(f"Erreur OAI-PMH de l'entrepôt : {error_element.get('code')} - {error_element.text}")
                break

            records = root.findall(".//{http://www.openarchives.org/OAI/2.0/}record")
            for record in records:
                all_records_xml.append(record)
                records_count += 1

            print(f"   - Requête {request_number}: {len(records)} enregistrements récupérés (Total: {records_count})")

            resumption_token_element = root.find(".//{http://www.openarchives.org/OAI/2.0/}resumptionToken")

            if resumption_token_element is not None and resumption_token_element.text:
                resumption_token = resumption_token_element.text
                time.sleep(1)
                request_number += 1
            else:
                resumption_token = None
                print("   - Plus de jeton de reprise. Moissonnage terminé.")
                break

        except requests.exceptions.RequestException as e:
            print(f"Erreur réseau ou HTTP lors de la requête {request_number}: {e}")
            break
        except ET.ParseError as e:
            print(f"Erreur de parsing XML lors de la requête {request_number}: {e}")
            print(f"Contenu de la réponse problématique : {response.text[:500]}...")
            print("   - Fichier mal formé. Tentative de récupération de secours du jeton...")

            match = re.search(r'<resumptionToken[^>]*>([^<]+)</resumptionToken>', response.text)
            if match:
                resumption_token = match.group(1)
                print(f"   - Jeton de reprise récupéré : '{resumption_token}'. Continuation.")
                request_number += 1
            else:
                resumption_token = None
                print("   - Impossible de récupérer le jeton de reprise. Le moissonnage va s'arrêter.")
                break

        except Exception as e:
            print(f"Une erreur inattendue est survenue lors de la requête {request_number}: {e}")
            break

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, output_filename)

    if records_count == 0:
        print("\nAucun enregistrement moissonné. Le fichier XML ne sera pas créé.")
        return None

    try:
        tree = ET.ElementTree(all_records_xml)
        ET.indent(tree, space="  ", level=0)
        tree.write(output_path, encoding="utf-8", xml_declaration=True)
        print(f"\nMoissonnage terminé : {records_count} enregistrements sauvegardés dans '{output_path}'")
        return output_path
    except Exception as e:
        print(f"Erreur lors de la sauvegarde du fichier XML final : {e}")
        return None


def normalize_xml(input_filepath):
    """
    Applique les corrections du script Normalize_XML_OAI-PMH.py sur un fichier XML.
    """
    print(f"\n{'='*60}")
    print(f"ÉTAPE 2 : Normalisation du fichier XML")
    print(f"{'='*60}")
    print(f"Fichier à normaliser : {input_filepath}")

    namespaces = {
        '':       "http://www.openarchives.org/OAI/2.0/",
        'oai':    "http://www.openarchives.org/OAI/2.0/",
        'oai_dc': "http://www.openarchives.org/OAI/2.0/oai_dc/",
        'dc':     "http://purl.org/dc/elements/1.1/",
        'xsi':    "http://www.w3.org/2001/XMLSchema-instance"
    }
    for prefix, uri in namespaces.items():
        ET.register_namespace(prefix, uri)

    try:
        with open(input_filepath, 'r', encoding='utf-8') as f:
            raw_content = f.read()

        corrected_content = raw_content.replace("&amp;amp;", "&amp;")

        root = ET.fromstring(corrected_content)
        tree = ET.ElementTree(root)

        ET.indent(tree, space="  ", level=0)
        tree.write(input_filepath, encoding="utf-8", xml_declaration=True)

        print(f"Normalisation réussie : fichier réécrit dans '{input_filepath}'")
        return input_filepath

    except FileNotFoundError:
        print(f"Erreur : Le fichier '{input_filepath}' n'a pas été trouvé.")
        return None
    except ET.ParseError as e:
        print(f"Erreur de parsing XML lors de la normalisation : {e}")
        print("Le fichier XML est peut-être mal formé. La normalisation est ignorée.")
        return None
    except Exception as e:
        print(f"Erreur inattendue lors de la normalisation : {e}")
        return None


def download_metadata_from_oai_xml(input_filepath, output_directory, target_subject=None):
    """
    Télécharge les métadonnées. Supporte l'attribut 'directApiCall' (Dataverse) 
    OU la reconstruction d'URL via DOI (PANGAEA).
    """
    print(f"\n{'='*60}\nÉTAPE 3 : Téléchargement des JSONs\n{'='*60}")
    
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)

    OAI_NAMESPACE = "http://www.openarchives.org/OAI/2.0/"
    urls_to_download = [] 

    try:
        tree = ET.parse(input_filepath)
        root = tree.getroot()
        records = root.findall(f'.//{{{OAI_NAMESPACE}}}record')

        for record in records:
            metadata = record.find(f'{{{OAI_NAMESPACE}}}metadata')
            header = record.find(f'{{{OAI_NAMESPACE}}}header')
            
            if metadata is not None:
                # CAS 1 : OAI-PMH 
                url = metadata.get('directApiCall')
                if url:
                    parsed_url = urlparse(url)
                    file_id = parse_qs(parsed_url.query).get('persistentId', ['unknown'])[0]
                    urls_to_download.append((url, file_id))
                    continue

            # CAS 2 : directApiCall
            if header is not None:
                oai_id = header.find(f'{{{OAI_NAMESPACE}}}identifier').text
                if "pangaea.de" in oai_id:
                    doi = oai_id.replace('oai:pangaea.de:doi:', '')
                    url = f"https://doi.pangaea.de/{doi}?format=metadata_jsonld"
                    urls_to_download.append((url, doi))

        print(f"URLs prêtes pour téléchargement : {len(urls_to_download)}")

    except Exception as e:
        print(f"Erreur lors de la préparation des URLs : {e}")
        return

    success_count = 0
    for i, (url, file_id) in enumerate(urls_to_download):
        try:
            print(f"Téléchargement {i+1}/{len(urls_to_download)} : {url}")
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            # Note : PANGAEA renvoie du JSON-LD direct, pas la structure imbriquée de Dataverse
            json_data = response.json()
            
            # Filtrage par sujet (Uniquement si target_subject est défini)
            
            safe_id = file_id.replace(':', '_').replace('/', '_')
            output_filename = os.path.join(output_directory, f"{safe_id}.json")

            with open(output_filename, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, ensure_ascii=False, indent=2)
            success_count += 1
        except Exception as err:
            print(f"   -> Erreur : {err}")

    print(f"\nTerminé : {success_count} fichiers sauvegardés.")

def harvest_direct_search(base_url, question, subtree, output_dir, output_filename):
    """ÉTAPE 1 (Nouveau) : Moissonnage via l'API Search."""
    print(f"\n{'='*60}\nÉTAPE 1 : Moissonnage DIRECT (API Search)\n{'='*60}")
    
    search_api_url = base_url.replace('/oai', '/api/search')
    all_items = []
    start = 0
    per_page = 10 

    while True:
        params = {
            "q": question,
            "subtree": subtree,
            "type": "dataset",
            "start": start,
            "per_page": per_page
        }
        try:
            response = requests.get(search_api_url, params=params)
            response.raise_for_status()
            data = response.json()
            
            items = data.get('data', {}).get('items', [])
            all_items.extend(items)
            
            total_count = data.get('data', {}).get('total_count', 0)
            print(f"   - {len(items)} items récupérés (Total cumulé : {len(all_items)} / {total_count})")
            
            start += per_page
            if start >= total_count or not items:
                break
            time.sleep(0.5)
        except Exception as e:
            print(f"Erreur Moissonnage Direct : {e}")
            break

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, output_filename)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({"status": "OK", "data": {"items": all_items}}, f, ensure_ascii=False, indent=2)
    return output_path


def _process_downloads(urls_with_ids, output_directory, target_subject=None):
    """Logique de téléchargement et filtrage par sujet."""
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)

    target_keywords = [k.strip().lower() for k in target_subject.split(',')] if target_subject else []
    success_count = 0

    for i, (url, persistent_id) in enumerate(urls_with_ids):
        try:
            print(f"Téléchargement {i+1}/{len(urls_with_ids)} : {url}")
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            json_data = response.json()
            
            if target_keywords:
                fields = json_data.get('datasetVersion', {}).get('metadataBlocks', {}).get('citation', {}).get('fields', [])
                found_subjects = []
                for field in fields:
                    if field.get('typeName') == 'subject':
                        found_subjects = [str(v).lower() for v in field.get('value', [])]
                        break
                if not any(key in found_subjects for key in target_keywords):
                    continue

            filename = persistent_id.replace(':', '_').replace('/', '_') + ".json"
            with open(os.path.join(output_directory, filename), 'w', encoding='utf-8') as f:
                json.dump(json_data, f, ensure_ascii=False, indent=2)
            success_count += 1
        except Exception as e:
            print(f"   -> Erreur : {e}")
    print(f"\nTerminé : {success_count} fichiers sauvegardés.")


def download_metadata_from_direct_json(input_filepath, output_directory, base_url, target_subject=None):
    """ÉTAPE 3 (Nouveau) : Préparation des URLs depuis JSON Search."""
    print(f"\n{'='*60}\nÉTAPE 3 : Téléchargement (Source JSON Direct)\n{'='*60}")
    export_base_url = base_url.replace('/oai', '/api/datasets/export')
    urls_to_download = []
    try:
        with open(input_filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for item in data.get('data', {}).get('items', []):
            global_id = item.get('global_id')
            if global_id:
                url = f"{export_base_url}?exporter=dataverse_json&persistentId={global_id}"
                urls_to_download.append((url, global_id))
        _process_downloads(urls_to_download, output_directory, target_subject)
    except Exception as e:
        print(f"Erreur lecture JSON : {e}")

def rename_json_to_done(filepath):
    """Renomme le fichier de listing une fois terminé."""
    if filepath and os.path.exists(filepath):
        new_name = filepath + ".done"
        os.rename(filepath, new_name)
        print(f"\nFichier de listing renommé : {os.path.basename(new_name)}")

# Paramètres FTP
FTP_HOST = "node200-eu.n0c.com"
FTP_PORT = 21
FTP_USER = "francis.clement@pndb.worldlite.fr"
FTP_PASSWORD = "&I7bjy7p91978"
FTP_REMOTE_DIR = "ODS"

# Authentification API Huwise (commun à tous les entrepôts)
API_TOKEN = "Inscrire API-Key"


def run_transform_and_upload(repo_name: str, output_dir: str, harvester_uid: str):
    """
    Après moissonnage :
    1. Lance Transform_JSONToCSV.py situé dans le répertoire parent de output_dir.
    2. Surveille l'apparition d'un fichier output_mapping*.csv daté du jour dans ce répertoire.
    3. Transfère ce fichier vers le répertoire FTP /ODS/.
    4. Déclenche l'API harvester une fois le transfert effectué.
    """
    parent_dir = os.path.dirname(os.path.abspath(output_dir))
    transform_script = os.path.join(parent_dir, "Transform_JSONToCSV.py")

    # --- Étape 1 : lancement du script de transformation ---
    print(f"\n{'='*60}")
    print(f"POST-TRAITEMENT [{repo_name}] : Transformation JSON → CSV")
    print(f"{'='*60}")
    print(f"Script : {transform_script}")

    if not os.path.isfile(transform_script):
        print(f"  AVERTISSEMENT : Transform_JSONToCSV.py introuvable dans {parent_dir}. Étape ignorée.")
        return

    today_str = datetime.date.today().strftime("%Y%m%d")

    try:
        result = subprocess.run(
            ["python3", transform_script],
            cwd=parent_dir,
            capture_output=True,
            text=True,
            timeout=600
        )
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(f"  [stderr] {result.stderr}")
        if result.returncode != 0:
            print(f"  ERREUR : Transform_JSONToCSV.py s'est terminé avec le code {result.returncode}.")
            return
        print(f"  Transform_JSONToCSV.py terminé avec succès.")
    except subprocess.TimeoutExpired:
        print(f"  ERREUR : Transform_JSONToCSV.py a dépassé le délai d'attente (10 min).")
        return
    except Exception as e:
        print(f"  ERREUR lors de l'exécution de Transform_JSONToCSV.py : {e}")
        return

    # --- Étape 2 : recherche du fichier output_mapping*.csv du jour ---
    print(f"\nRecherche du fichier output_mapping*.csv du jour ({today_str}) dans : {parent_dir}")
    csv_files_found = []
    for filepath in glob.glob(os.path.join(parent_dir, "output_mapping*.csv")):
        mtime = datetime.date.fromtimestamp(os.path.getmtime(filepath))
        if mtime == datetime.date.today():
            csv_files_found.append(filepath)

    if not csv_files_found:
        print(f"  AVERTISSEMENT : Aucun fichier output_mapping*.csv du jour trouvé. FTP ignoré.")
        return

    for csv_path in csv_files_found:
        csv_filename = os.path.basename(csv_path)
        print(f"  Fichier CSV détecté : {csv_filename}")

        # --- Étape 3 : envoi FTP ---
        print(f"\nEnvoi FTP : {csv_filename} → {FTP_REMOTE_DIR}/")
        try:
            with ftplib.FTP() as ftp:
                ftp.connect(FTP_HOST, FTP_PORT)
                ftp.login(FTP_USER, FTP_PASSWORD)
                current_dir = ftp.pwd()
                if not current_dir.rstrip("/").endswith("ODS"):
                    ftp.cwd("ODS")
                    current_dir = ftp.pwd()
                print(f"  Répertoire FTP courant : {current_dir}")
                with open(csv_path, "rb") as f:
                    ftp.storbinary(f"STOR {csv_filename}", f)
            print(f"  Transfert FTP réussi : {csv_filename} envoyé dans {FTP_REMOTE_DIR}/")
        except ftplib.all_errors as e:
            print(f"  ERREUR FTP pour {csv_filename} : {e}")
            continue

        # --- Étape 4 : appel API harvester ---
        if not harvester_uid:
            print(f"  AVERTISSEMENT : harvester_uid non défini pour [{repo_name}]. Appel API ignoré.")
            continue

        api_url = f"https://www.pndb.fr/api/automation/v1.0/harvesters/{harvester_uid}/start/"
        headers = {
            "Authorization": f"apikey {API_TOKEN}",
            "Accept": "application/json"
        }
        print(f"\nAppel API harvester : {api_url}")
        try:
            api_response = requests.post(api_url, headers=headers, timeout=30)
            api_response.raise_for_status()
            print(f"  API harvester déclenchée avec succès (HTTP {api_response.status_code}).")
        except requests.exceptions.RequestException as e:
            print(f"  ERREUR lors de l'appel API harvester : {e}")


if __name__ == "__main__":
    available_repositories: Dict[str, Dict[str, Any]] = {
        "recherche_data_gouv": {
            "harvester_uid": "",
            "harvest": False,
            "Type_moissonnage": "OAI-PMH",
            "base_url": "https://entrepot.recherche.data.gouv.fr/oai",
            "metadata_prefix": "oai_dc",
            "set_spec": "ALL",
            "use_set": True,
            "question": "",
            "subtree": "",
            "description": "Entrepôt principal de recherche.data.gouv.fr (XML)",
            "subject": "",
            "output_dir": "OAI_Records/RechercheDataGouv_XML"
        },
        "inrae": {
            "harvester_uid": "moissonneur-rdg",
            "harvest": True,
            "Type_moissonnage": "OAI-PMH",
            "base_url": "https://entrepot.recherche.data.gouv.fr/oai",
            "metadata_prefix": "dataverse_json",
            "set_spec": "INRAE",
            "use_set": True,
            "question": "",
            "subtree": "",
            "description": "Entrepôt INRAE (JSON Dataverse)",
            "subject": "Agricultural Sciences, Earth and Environmental Sciences",
            "output_dir": "/Users/francisclement/Documents/PNDB/Cat.harvestX/Moissonnage RDG.INRAE/RDG.INRAE_JSONs"
        },
        "pangaea": {
            "harvester_uid": "moissonneur-pangaea",
            "harvest": False,
            "Type_moissonnage": "OAI-PMH",
            "base_url": "https://ws.pangaea.de/oai/provider",
            "metadata_prefix": "oai_dc",
            "set_spec": "NFDI4BioDiversity",
            "use_set": True,
            "question": "",
            "subtree": "",
            "description": "Entrepôt test PANGAEA (ISO 19139)",
            "subject": "",
            "output_dir": "/Users/francisclement/Documents/PNDB/Cat.harvestX/Moissonnage PANGAEA/PANGAEA_JSONs"
        },
        "datacite_ubfc": {
            "harvester_uid": "",
            "harvest": False,
            "Type_moissonnage": "OAI-PMH",
            "base_url": "https://search-data.ubfc.fr/ws/oai/oai.php",#To do : "https://oai.datacite.org/oai",
            "metadata_prefix": "oai_datacite",
            "set_spec": "inist.osutheta",
            "use_set": False,
            "question": "",
            "subtree": "",
            "description": "Entrepôt DAtaCite de l'UBFC",
            "subject": "",
            "output_dir": "/Users/francisclement/Documents/PNDB/Cat.harvestX/Moissonnage DataCite.UBFC/DataCite.UBFC_JSONs"
        },
        "uga": {
            "harvester_uid": "moissonneur-rdguga",
            "harvest": False,
            "Type_moissonnage": "OAI-PMH",
            "base_url": "https://entrepot.recherche.data.gouv.fr/oai",
            "metadata_prefix": "dataverse_json",
            "set_spec": "univ-grenoble-alpes",
            "use_set": True,
            "question": "",
            "subtree": "",
            "description": "Entrepôt Université Grenoble Alpes (JSON Dataverse)",
            "subject": "",
            "output_dir": "/Users/francisclement/Documents/PNDB/Cat.harvestX/Moissonnage RDG.UGA/RDG.UGA_JSONs"
        },
        "umontpellier": {
            "harvester_uid": "moissonneur-rdgdata_umontpellier",
            "harvest": False,
            "Type_moissonnage": "OAI-PMH",
            "base_url": "https://entrepot.recherche.data.gouv.fr/oai",
            "metadata_prefix": "dataverse_json",
            "set_spec": "umontpellier",
            "use_set": True,
            "question": "",
            "subtree": "",
            "description": "Entrepôt Université Montpellier (API Search)",
            "subject": "",
            "output_dir": "/Users/francisclement/Documents/PNDB/Cat.harvestX/Moissonnage RDG.Data_UMontpellier/RDG.Data_UMontpellier_JSONs"
        },
        "ulille": {
            "harvester_uid": "moissonneur-rdglillodata",
            "harvest": False,
            "Type_moissonnage": "OAI-PMH",
            "base_url": "https://entrepot.recherche.data.gouv.fr/oai",
            "metadata_prefix": "dataverse_json",
            "set_spec": "univ-lille",
            "use_set": True,
            "question": "",
            "subtree": "",
            "description": "Entrepôt Université Lille (JSON Dataverse)",
            "subject": "",
            "output_dir": "/Users/francisclement/Documents/PNDB/Cat.harvestX/Moissonnage RDG.Univ-Lille/RDG.Univ-Lille_JSONs"
        },
        "sorbonne-univ": {
            "harvester_uid": "moissonneur-rdgsu",
            "harvest": False,
            "Type_moissonnage": "OAI-PMH",
            "base_url": "https://entrepot.recherche.data.gouv.fr/oai",
            "metadata_prefix": "dataverse_json",
            "set_spec": "sorbonne-univ",
            "use_set": True,
            "question": "",
            "subtree": "",
            "description": "Entrepôt Université Sorbonne (JSON Dataverse)",
            "subject": "Earth and Environmental Sciences",
            "output_dir": "/Users/francisclement/Documents/PNDB/Cat.harvestX/Moissonnage RDG.SU/RDG.SU_JSONs"
        },
        "upoitiers": {
            "harvester_uid": "moissonneur-rdgdata_upoitiers",
            "harvest": False,
            "Type_moissonnage": "Direct",
            "base_url": "https://entrepot.recherche.data.gouv.fr/oai",
            "metadata_prefix": "dataverse_json",
            "set_spec": "",
            "use_set": False,
            "question": "*",
            "subtree": "univ-poitiers",
            "description": "Entrepôt Université Poitiers (JSON Dataverse)",
            "subject": "Earth and Environmental Sciences",
            "output_dir": "/Users/francisclement/Documents/PNDB/Cat.harvestX/Moissonnage RDG.UPoitiers/RDG.UPoitiers_JSONs"
        },
        "ird": {
            "harvester_uid": "moissonneur-datasudsird",
            "harvest": False,
            "Type_moissonnage": "OAI-PMH",
            "base_url": "https://dataverse.ird.fr/oai",
            "metadata_prefix": "dataverse_json",
            "set_spec": "",
            "use_set": False,
            "question": "",
            "subtree": "",
            "description": "Entrepôt IRD (JSON Dataverse)",
            "subject": "",
            "output_dir": "/Users/francisclement/Documents/PNDB/Cat.harvestX/Moissonnage DataSuds.IRD/DataSuds.IRD_JSONs"
        },
        "ird_geo": {
            "harvester_uid": "moissonneur-datasuds-geoird",
            "harvest": False,
            "Type_moissonnage": "OAI-PMH",
            "base_url": "https://datasuds-geo.ird.fr/geonetwork/srv/fre/oaipmh",
            "metadata_prefix": "dataverse_json",
            "set_spec": "",
            "use_set": False,
            "question": "",
            "subtree": "",
            "description": "Entrepôt GéoIRD (JSON Dataverse)",
            "subject": "",
            "output_dir": "/Users/francisclement/Documents/PNDB/Cat.harvestX/Moissonnage DataSuds_Geo.IRD/DataSuds_Geo.IRD_JSONs"
        },
        "cirad": {
            "harvester_uid": "moissonneur-cirad",
            "harvest": False,
            "Type_moissonnage": "OAI-PMH",
            "base_url": "https://dataverse.cirad.fr/oai",
            "metadata_prefix": "dataverse_json",
            "set_spec": "",
            "use_set": False,
            "question": "",
            "subtree": "",
            "description": "Entrepôt CIRAD (JSON Dataverse)",
            "subject": "",
            "output_dir": "/Users/francisclement/Documents/PNDB/Cat.harvestX/Moissonnage CIRAD/CIRAD_JSONs"
        },
        "ubfc": {
            "harvester_uid": "",
            "harvest": False,
            "Type_moissonnage": "OAI-PMH",
            "base_url": "https://search-data.ubfc.fr/ws/oai/oai.php",
            "metadata_prefix": "oai_dc",
            "set_spec": "",
            "use_set": False,
            "question": "",
            "subtree": "",
            "description": "Entrpôt Université Bourgogne Franche Comté",
            "subject": "",
            "output_dir": "/Users/francisclement/Documents/PNDB/Cat.harvestX/Moissonnage RDG.UBFC/RDG.UBFC_JSONs"
        },
        "univ-rennes": {
            "harvester_uid": "moissonneur-rdgurennes",
            "harvest": False,
            "Type_moissonnage": "Direct",
            "base_url": "https://entrepot.recherche.data.gouv.fr/oai",
            "metadata_prefix": "dataverse_json",
            "set_spec": "",
            "use_set": False,
            "question": "*",
            "subtree": "univ-rennes",
            "description": "Entrepôt Université de Rennes (API Search)",
            "subject": "",
            "output_dir": "/Users/francisclement/Documents/PNDB/Cat.harvestX/Moissonnage RDG.URennes/RDG.URennes_JSONs"
        },
        "cnrs": {
            "harvester_uid": "moissonneur-rdgcnrs",
            "harvest": False,
            "Type_moissonnage": "Direct",
            "base_url": "https://entrepot.recherche.data.gouv.fr/oai",
            "metadata_prefix": "dataverse_json",
            "set_spec": "",
            "use_set": False,
            "question": "*",
            "subtree": "cnrs",
            "description": "Entrepôt Université du CNRS (API Search)",
            "subject": "Earth and Environmental Sciences, Agricultural Sciences",
            "output_dir": "/Users/francisclement/Documents/PNDB/Cat.harvestX/Moissonnage RDG.CNRS/RDG.CNRS_JSONs"
        },
        "upsaclay": {
            "harvester_uid": "moissonneur-rdgupsaclay",
            "harvest": False,
            "Type_moissonnage": "Direct",
            "base_url": "https://entrepot.recherche.data.gouv.fr/oai",
            "metadata_prefix": "dataverse_json",
            "set_spec": "",
            "use_set": False,
            "question": "*",
            "subtree": "upsaclay",
            "description": "Entrepôt Université Paris-Saclay (API Search)",
            "subject": "Earth and Environmental Sciences, Agricultural Sciences",
            "output_dir": "/Users/francisclement/Documents/PNDB/Cat.harvestX/Moissonnage RDG.UPSaclay/RDG.UPSaclay_JSONs"
        },
        "data-bfc": {
            "harvester_uid": "moissonneur-rdgubfc",
            "harvest": False,
            "Type_moissonnage": "Direct",
            "base_url": "https://entrepot.recherche.data.gouv.fr/oai",
            "metadata_prefix": "dataverse_json",
            "set_spec": "",
            "use_set": False,
            "question": "*",
            "subtree": "data-bfc",
            "description": "Entrepôt Université Bourgogne Franche Comté (API Search)",
            "subject": "",
            "output_dir": "/Users/francisclement/Documents/PNDB/Cat.harvestX/Moissonnage RDG.UBFC/RDG.UBFC_JSONs"
        },
         "ubo": {
            "harvester_uid": "moissonneur-rdgubo",
            "harvest": False,
            "Type_moissonnage": "Direct",
            "base_url": "https://entrepot.recherche.data.gouv.fr/oai",
            "metadata_prefix": "dataverse_json",
            "set_spec": "",
            "use_set": False,
            "question": '"Université+de+Bretagne+Occidentale"',
            "subtree": "root",
            "description": "Entrepôt Université de Bretagne Occidentale (API Search)",
            "subject": "",
            "output_dir": "/Users/francisclement/Documents/PNDB/Cat.harvestX/Moissonnage RDG.UBO/RDG.UBO_JSONs"
        },
        "ephe-psl": {
            "harvester_uid": "moissonneur-rdgephe",
            "harvest": False,
            "Type_moissonnage": "Direct",
            "base_url": "https://entrepot.recherche.data.gouv.fr/oai",
            "metadata_prefix": "dataverse_json",
            "set_spec": "",
            "use_set": False,
            "question": "*",
            "subtree": "ephe-psl",
            "description": "Entrepôt EPHE (API Search)",
            "subject": "",
            "output_dir": "/Users/francisclement/Documents/PNDB/Cat.harvestX/Moissonnage RDG.EPHE/RDG.EPHE_JSONs"
        },
        "zenodo": {
            "harvester_uid": "",
            "harvest": False,
            "Type_moissonnage": "OAI-PMH",
            "base_url": "https://zenodo.org/oai2d",
            "metadata_prefix": "oai_dc",
            "set_spec": "",
            "use_set": False,
            "question": "",
            "subtree": "",
            "description": "Entrepôt Zenodo",
            "subject": "",
            "output_dir": "/Users/francisclement/Documents/PNDB/Cat.harvestX/Moissonnage ZENODO/DataSuds.CIRAD_JSONs"
        },
        "hal": {
            "harvester_uid": "",
            "harvest": False,
            "Type_moissonnage": "OAI-PMH",
            "base_url": "https://api.archives-ouvertes.fr/oai/hal",
            "metadata_prefix": "oai_dc",
            "set_spec": "",
            "use_set": False,
            "question": "",
            "subtree": "",
            "description": "Entrepôt HAL",
            "subject": "",
            "output_dir": "/Users/francisclement/Documents/PNDB/Cat.harvestX/Moissonnage ZENODO/HAL_JSONs"
        }
    }

    # Sélection des entrepôts à moissonner : uniquement ceux avec "harvest": True
    repositories_to_harvest = {
        name: info for name, info in available_repositories.items()
        if info.get("harvest", False)
    }

    if not repositories_to_harvest:
        print("Aucun entrepôt activé (harvest: True). Veuillez activer au moins un entrepôt dans available_repositories.")
        exit(0)

    print(f"\n{'='*60}")
    print(f"Entrepôts sélectionnés pour le moissonnage ({len(repositories_to_harvest)}) :")
    for name in repositories_to_harvest:
        print(f"  - {name} : {repositories_to_harvest[name].get('description', '')}")
    print(f"{'='*60}")

    # --- Nettoyage des répertoires de sortie avant moissonnage ---
    print(f"\n{'='*60}")
    print("Nettoyage des répertoires de sortie...")
    print(f"{'='*60}")
    for repo_name, repo_info in repositories_to_harvest.items():
        output_dir = repo_info.get('output_dir')
        if not output_dir:
            continue
        if not os.path.exists(output_dir):
            print(f"  [{repo_name}] Répertoire inexistant, ignoré : {output_dir}")
            continue
        deleted_count = 0
        for filename in os.listdir(output_dir):
            file_path = os.path.join(output_dir, filename)
            if os.path.isfile(file_path):
                try:
                    os.remove(file_path)
                    deleted_count += 1
                except Exception as e:
                    print(f"  [{repo_name}] Impossible de supprimer '{filename}' : {e}")
        print(f"  [{repo_name}] {deleted_count} fichier(s) supprimé(s) dans : {output_dir}")
    print("Nettoyage terminé.")

    for repo_name, repo_info in repositories_to_harvest.items():
        print(f"\n{'#'*60}")
        print(f"# TRAITEMENT : {repo_name}")
        print(f"# {repo_info.get('description', '')}")
        print(f"{'#'*60}")

        mode = repo_info.get("Type_moissonnage", "OAI-PMH")
        output_directory = repo_info.get('output_dir')
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        try:
            if mode == "Direct":
                filename = f"{repo_name}_{timestamp}.json"
                path = harvest_direct_search(repo_info["base_url"], repo_info["question"], repo_info["subtree"], output_directory, filename)
                if path:
                    download_metadata_from_direct_json(path, output_directory, repo_info["base_url"], repo_info.get("subject"))
                    rename_json_to_done(path)
            else:
                filename = f"{repo_name}_{timestamp}.xml"
                path = harvest_all_oai_records(repo_info["base_url"], repo_info["metadata_prefix"], repo_info["set_spec"], repo_info.get("use_set", True), output_directory, filename)
                if path:
                    norm_path = normalize_xml(path)
                    download_metadata_from_oai_xml(norm_path, output_directory, repo_info.get("subject"))

            print(f"\n{'='*60}\nPipeline terminé pour '{repo_name}' ({mode}).\n{'='*60}")

            # --- Post-traitement : transformation, FTP, API ---
            run_transform_and_upload(
                repo_name=repo_name,
                output_dir=output_directory,
                harvester_uid=repo_info.get("harvester_uid", "")
            )

        except Exception as e:
            print(f"\nErreur inattendue pour '{repo_name}' : {e}. Passage au suivant.")
            continue

    print(f"\n{'#'*60}\nTous les moissonnages activés sont terminés.\n{'#'*60}")