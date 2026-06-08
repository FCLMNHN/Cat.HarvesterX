import xml.etree.ElementTree as ET
import requests
import os
import datetime
from urllib.parse import urlparse, parse_qs
import argparse

def download_metadata_from_oai_xml(input_filepath, base_output_dir_name="IRD_JSON"):
    """
    Lit un fichier XML OAI, extrait les URLs dans l'attribut directApiCall,
    télécharge les fichiers et les sauvegarde dans un répertoire horodaté.

    Args:
        input_filepath (str): Chemin vers le fichier XML OAI d'entrée.
        base_output_dir_name (str): Nom de base du répertoire de sortie (ex: INRAE_JSON).
    """
    
    # --- 1. Préparation du répertoire de sortie ---
    today_date = datetime.date.today().strftime("%Y-%m-%d")
    output_dir = f"{base_output_dir_name}_{today_date}"

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Répertoire créé : '{output_dir}'")
    else:
        print(f"Le répertoire '{output_dir}' existe déjà.")

    # --- 2. Parsing du XML OAI et extraction des URLs ---
    # Définition des namespaces pour le parsing
    OAI_NAMESPACE = "http://www.openarchives.org/OAI/2.0/"
    NAMESPACES = {'oai': OAI_NAMESPACE}
    
    urls_to_download = []
    
    try:
        # Charger et parser le fichier XML
        tree = ET.parse(input_filepath)
        root = tree.getroot()

        # XPath pour trouver tous les noeuds <oai:metadata>
        # Le chemin est construit pour fonctionner avec ElementTree et les namespaces
        metadata_elements = root.findall(f'.//{{{OAI_NAMESPACE}}}metadata')
        
        if not metadata_elements:
             print("AVERTISSEMENT : Aucune balise <metadata> trouvée avec le namespace OAI.")
             return

        # Extraire les URLs
        for element in metadata_elements:
            url = element.get('directApiCall')
            if url:
                urls_to_download.append(url)
        
        print(f"URLs extraites : {len(urls_to_download)}")

    except FileNotFoundError:
        print(f"Erreur : Le fichier d'entrée '{input_filepath}' n'a pas été trouvé.")
        return
    except ET.ParseError as e:
        print(f"Erreur de parsing XML : {e}")
        return
    
    # --- 3. Téléchargement des fichiers ---
    for i, url in enumerate(urls_to_download):
        try:
            print(f"Téléchargement du fichier {i+1}/{len(urls_to_download)} à partir de : {url}")
            
            # Faire la requête HTTP GET
            response = requests.get(url, timeout=30)
            response.raise_for_status()  # Lève une exception pour les codes d'erreur 4xx/5xx

            # Déterminer un nom de fichier unique basé sur le 'persistentId' de l'URL
            parsed_url = urlparse(url)
            query_params = parse_qs(parsed_url.query)
            
            # Le paramètre 'persistentId' contient l'identifiant unique (ex: doi:10.12763/EF4K3L)
            file_id = query_params.get('persistentId', ['unknown_id'])[0].replace(':', '_').replace('/', '_')
            
            output_filename = os.path.join(output_dir, f"{file_id}.json")

            # Sauvegarder le contenu JSON téléchargé
            # Le contenu est déjà décodé par requests si le header est correct.
            with open(output_filename, 'wb') as f:
                f.write(response.content)

            print(f"-> Succès : Sauvegardé sous '{output_filename}'")
            
        except requests.exceptions.HTTPError as errh:
            print(f"Erreur HTTP pour {url}: {errh}")
        except requests.exceptions.ConnectionError as errc:
            print(f"Erreur de connexion pour {url}: {errc}")
        except requests.exceptions.Timeout as errt:
            print(f"Timeout pour {url}: {errt}")
        except requests.exceptions.RequestException as err:
            print(f"Erreur inattendue lors du téléchargement pour {url}: {err}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extrait les URLs directApiCall d'un fichier XML OAI, télécharge les fichiers JSON et les enregistre dans un répertoire horodaté."
    )
    parser.add_argument(
        "input_file",
        help="Chemin vers le fichier XML OAI à analyser."
    )

    args = parser.parse_args()

    # Assurez-vous d'avoir installé 'requests' (pip install requests)
    download_metadata_from_oai_xml(args.input_file)