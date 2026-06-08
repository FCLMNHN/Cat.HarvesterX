import os
import glob
from typing import List, Tuple

# --- CONFIGURATION (À adapter si nécessaire) ---
# Nom du répertoire à vérifier (doit contenir les fichiers JSON)
INPUT_DIR = "INRAE_XML_2025-11-14" 
# Caractère à rechercher
SEARCH_CHARACTER = "‡"
# ----------------------------------------------


def check_json_for_pipe(directory: str, search_char: str) -> Tuple[List[str], List[str]]:
    """
    Vérifie tous les fichiers JSON dans le répertoire donné pour la présence du caractère spécifié.

    Args:
        directory: Le chemin du répertoire contenant les fichiers JSON.
        search_char: Le caractère ou la chaîne à rechercher.

    Returns:
        Un tuple contenant (liste des fichiers AVEC le caractère, liste des fichiers SANS le caractère).
    """
    print(f"--- Démarrage de la vérification du caractère '{search_char}' ---")
    
    search_path = os.path.join(directory, '*.json')
    json_files = glob.glob(search_path)
    
    if not json_files:
        print(f"ERREUR : Aucun fichier JSON trouvé dans le répertoire '{directory}'.")
        return [], []

    print(f"Fichiers JSON trouvés : {len(json_files)}")
    
    files_with_char = []
    files_without_char = []
    
    for i, file_path in enumerate(json_files):
        file_name = os.path.basename(file_path)
        
        try:
            # Ouvrir le fichier en mode texte et lire tout le contenu
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Vérification simple de la présence du caractère
            if search_char in content:
                print(f"  [⚠️ TROUVÉ] Le caractère '{search_char}' est présent dans : {file_name}")
                files_with_char.append(file_name)
            else:
                print(f"  [✅ OK] Le caractère '{search_char}' est ABSENT de : {file_name}")
                files_without_char.append(file_name)
                
        except Exception as e:
            print(f"  [❌ ERREUR] Impossible de lire le fichier '{file_name}' : {e}")

    return files_with_char, files_without_char


def main():
    files_with, files_without = check_json_for_pipe(INPUT_DIR, SEARCH_CHARACTER)

    print("\n--- ✅ Résumé de la Vérification ---")
    
    total_files = len(files_with) + len(files_without)
    
    if total_files == 0:
        return

    if files_with:
        print(f"\n⚠️ {len(files_with)} fichier(s) CONTIENNENT le caractère '{SEARCH_CHARACTER}':")
        for f in files_with:
            print(f"  - {f}")
        print("\nCONCLUSION : L'utilisation de ce caractère comme séparateur CSV est RISQUÉE car il sera confondu avec les données.")
    else:
        print(f"\n✅ Le caractère '{SEARCH_CHARACTER}' est ABSENT des {total_files} fichiers analysés.")
        print("\nCONCLUSION : Vous pouvez utiliser le caractère '|' comme séparateur CSV en toute sécurité.")


if __name__ == "__main__":
    main()