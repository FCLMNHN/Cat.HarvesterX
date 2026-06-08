import xml.etree.ElementTree as ET
import argparse
import os

def decode_xml_characters(input_filepath, output_filepath):
    """
    Lit un fichier XML, effectue une correction spécifique de la double-entité (&amp;amp;),
    décode les entités XML en caractères Unicode, puis écrit le contenu
    dans un nouveau fichier XML en UTF-8.

    Args:
        input_filepath (str): Chemin vers le fichier XML d'entrée.
        output_filepath (str): Chemin vers le fichier XML de sortie.
    """
    try:
        # 1. Lire le contenu brut du fichier pour pouvoir le modifier
        # On utilise une lecture standard pour obtenir la chaîne brute.
        with open(input_filepath, 'r', encoding='utf-8') as f:
            raw_content = f.read()

        # 2. 🌟 CORRECTION SPÉCIFIQUE : Remplacer la double-entité
        # '&amp;amp;' est remplacé par '&amp;' (l'encodage simple).
        # L'étape de parsing ElementTree suivante convertira ensuite '&amp;' en '&'.
        corrected_content = raw_content.replace("&amp;amp;", "&amp;")
        
        # 3. Parser le contenu corrigé à partir de la chaîne de caractères.
        # ET.fromstring décode toutes les entités standard (&amp;, &lt;, etc.) en Unicode.
        root = ET.fromstring(corrected_content)
        tree = ET.ElementTree(root)

        # 4. (Optionnel) Vérifier et enregistrer les namespaces pour une meilleure sortie
        namespaces = {
            '': "http://www.openarchives.org/OAI/2.0/",
            'oai': "http://www.openarchives.org/OAI/2.0/",
            'oai_dc': "http://www.openarchives.org/OAI/2.0/oai_dc/",
            'dc': "http://purl.org/dc/elements/1.1/",
            'xsi': "http://www.w3.org/2001/XMLSchema-instance"
        }
        for prefix, uri in namespaces.items():
            ET.register_namespace(prefix, uri)

        # 5. Écrire l'arbre XML dans un nouveau fichier.
        ET.indent(tree, space="  ", level=0) # Pour une sortie indentée et lisible
        tree.write(output_filepath, encoding="utf-8", xml_declaration=True)

        print(f"Fichier XML décodé et sauvegardé avec succès dans : '{output_filepath}'")

    except FileNotFoundError:
        print(f"Erreur : Le fichier d'entrée '{input_filepath}' n'a pas été trouvé.")
    except ET.ParseError as e:
        print(f"Erreur de parsing XML pour '{input_filepath}' : {e}")
        print("Assurez-vous que le fichier XML est bien formé et correctement encodé.")
    except Exception as e:
        print(f"Une erreur inattendue est survenue : {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Décode les caractères encodés dans un fichier XML et le sauvegarde en UTF-8."
    )
    parser.add_argument(
        "input_file",
        help="Chemin vers le fichier XML à décoder."
    )
    parser.add_argument(
        "-o", "--output_file",
        help="Chemin vers le fichier de sortie. Par défaut, ajoute '_decoded' au nom du fichier d'entrée.",
        default=None
    )

    args = parser.parse_args()

    input_path = args.input_file
    output_path = args.output_file

    if not output_path:
        # Créer un nom de fichier de sortie par défaut
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}_decoded{ext}"

    decode_xml_characters(input_path, output_path)