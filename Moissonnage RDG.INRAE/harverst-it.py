import requests
import xml.etree.ElementTree as ET
import os
import time
import argparse
import datetime
import re

# --- Déclaration des espaces de noms globalement pour ElementTree ---
# Ceci aide ElementTree à mapper les URI d'espaces de noms à des préfixes
# préférés lors de la sérialisation, au lieu de générer ns0, ns1, etc.
ET.register_namespace('', "http://www.openarchives.org/OAI/2.0/")
ET.register_namespace('oai', "http://www.openarchives.org/OAI/2.0/") # Redondant si le défaut est OAI, mais peut aider
ET.register_namespace('oai_dc', "http://www.openarchives.org/OAI/2.0/oai_dc/")
ET.register_namespace('dc', "http://purl.org/dc/elements/1.1/")
ET.register_namespace('xsi', "http://www.w3.org/2001/XMLSchema-instance")
# ------------------------------------------------------------------

def harvest_all_oai_records(base_url, metadata_prefix, set_spec, output_filename="all_oai_records.xml"):
    """
    Moissonne l'ensemble des enregistrements d'un entrepôt OAI-PMH en gérant les jetons de reprise.

    Args:
        base_url (str): L'URL de base de l'entrepôt OAI-PMH.
        metadata_prefix (str): Le format de métadonnées souhaité (ex: "oai_dc").
        set_spec (str): L'ensemble à moissonner (ex: "ALL" pour tous).
        output_filename (str): Le nom du fichier XML où tous les enregistrements seront sauvegardés.
    """
    
    # MODIFICATION : Création de l'élément racine avec les attributs OAI-PMH
    all_records_xml = ET.Element(
        "{http://www.openarchives.org/OAI/2.0/}OAI-PMH", # Utiliser l'URI complète pour l'élément racine
      
    )
    # L'espace de noms "xmlns:dc" n'est pas nécessaire sur l'élément racine OAI-PMH pour la conformité.
    # Il est déclaré sur la balise <oai_dc:dc> elle-même par le serveur.

    resumption_token = None
    records_count = 0
    request_number = 1

    print(f"Démarrage du moissonnage de {base_url} avec prefix={metadata_prefix}, set={set_spec}")

    while True:
        params = {"verb": "ListRecords"}
        if resumption_token:
            params["resumptionToken"] = resumption_token
            print(f"Requête {request_number}: Utilisation du jeton de reprise '{resumption_token}'")
        else:
            params["metadataPrefix"] = metadata_prefix
            params["set"] = set_spec
            print(f"Requête {request_number}: Première requête.")

        try:
            response = requests.get(base_url, params=params)
            response.raise_for_status()

            # Parse le XML de la réponse
            root = ET.fromstring(response.content)

            # Vérifier s'il y a des erreurs OAI-PMH
            error_element = root.find(".//{http://www.openarchives.org/OAI/2.0/}error") # Utiliser l'URI complète
            if error_element is not None:
                print(f"Erreur OAI-PMH de l'entrepôt : {error_element.get('code')} - {error_element.text}")
                break
            
            # Ajouter les enregistrements au fichier XML principal
            records = root.findall(".//{http://www.openarchives.org/OAI/2.0/}record") # Utiliser l'URI complète
            for record in records:
                # IMPORTANT : S'assurer que les espaces de noms sont correctement gérés lors de l'ajout
                # ElementTree gère généralement cela si les namespaces sont enregistrés.
                all_records_xml.append(record)
                records_count += 1

            print(f"   - Requête {request_number}: {len(records)} enregistrements récupérés (Total: {records_count})")

            # Récupérer le jeton de reprise pour la prochaine requête
            resumption_token_element = root.find(".//{http://www.openarchives.org/OAI/2.0/}resumptionToken") # Utiliser l'URI complète
            
            if resumption_token_element is not None and resumption_token_element.text:
                resumption_token = resumption_token_element.text
                time.sleep(1) # Pause d'une seconde
                request_number += 1
            else:
                resumption_token = None
                print("   - Plus de jeton de reprise. Moissonnage terminé.")
                break

        except requests.exceptions.RequestException as e:
            print(f"Erreur réseau ou HTTP lors de la requête {request_number}: {e}")
            break
        except ET.ParseError as e:
            # Gère spécifiquement l'erreur de parsing XML
            print(f"Erreur de parsing XML lors de la requête {request_number}: {e}")
            print(f"Contenu de la réponse problématique : {response.text[:500]}...")
            print("   - Fichier mal formé. Tentative de récupération du prochain jeton...")
            
            # --- Logique de récupération de secours du jeton ---
            match = re.search(r'<resumptionToken[^>]*>([^<]+)</resumptionToken>', response.text)
            if match:
                resumption_token = match.group(1)
                print(f"   - Jeton de reprise récupéré : '{resumption_token}'. Continuation.")
                # On ne met pas de "continue" ici car la boucle de contrôle se trouve après le bloc try/except
            else:
                resumption_token = None
                print("   - Impossible de récupérer le jeton de reprise. Le moissonnage va s'arrêter.")
                break # On s'arrête si on ne peut pas continuer
                
        except Exception as e:
            print(f"Une erreur inattendue est survenue lors de la requête {request_number}: {e}")
            break

    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), output_filename)
    try:
        tree = ET.ElementTree(all_records_xml)
        ET.indent(tree, space="  ", level=0)
        tree.write(output_path, encoding="utf-8", xml_declaration=True)
        print(f"\nMoissonnage terminé. Tous les {records_count} enregistrements ont été sauvegardés dans '{output_path}'")
    except Exception as e:
        print(f"Erreur lors de la sauvegarde du fichier XML final : {e}")


if __name__ == "__main__":
    available_repositories = {
        "recherche_data_gouv": {
            "base_url": "https://entrepot.recherche.data.gouv.fr/oai",
            "metadata_prefix": "oai_dc",
            "set_spec": "ALL",
            "description": "Entrepôt principal de recherche.data.gouv.fr"
        },
        "inrae": {
            "base_url": "https://entrepot.recherche.data.gouv.fr/oai",
            "metadata_prefix": "dataverse_json",
            "set_spec": "INRAE",
            "description": "Entrepôt INRAE"
        },
        "example_repo": {
            "base_url": "http://www.openarchives.org/OAI/2.0/oai.php",
            "metadata_prefix": "oai_dc",
            "set_spec": "ALL",
            "description": "Exemple de dépôt OAI-PMH"
        }
    }

    parser = argparse.ArgumentParser(description="Moissonne des entrepôts OAI-PMH définis.")
    parser.add_argument(
        "repository_name", 
        choices=available_repositories.keys(),
        help="Nom de l'entrepôt à moissonner. Choix disponibles: " + ", ".join(available_repositories.keys())
    )
    parser.add_argument(
        "-o", "--output",
        help="Nom de base du fichier de sortie (la date et l'heure seront ajoutées).",
        default=None
    )

    args = parser.parse_args()

    repo_info = available_repositories[args.repository_name]

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    if args.output:
        base_output_name = args.output.rsplit('.', 1)
        if len(base_output_name) > 1:
            output_filename = f"{base_output_name[0]}_{timestamp}.{base_output_name[1]}"
        else:
            output_filename = f"{base_output_name[0]}_{timestamp}.xml"
    else:
        output_filename = f"{args.repository_name}_{timestamp}.xml"

    harvest_all_oai_records(
        base_url=repo_info["base_url"],
        metadata_prefix=repo_info["metadata_prefix"],
        set_spec=repo_info["set_spec"],
        output_filename=output_filename
    )