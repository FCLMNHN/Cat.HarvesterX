import requests
import pandas as pd
import io
import os

# --- CONFIGURATION ---
# URL de l'export CSV du catalogue PNDB avec les paramètres spécifiés
PNDB_CATALOG_URL = "https://pndb.opendatasoft.com/api/explore/v2.1/catalog/exports/csv?delimiter=%3B&list_separator=%2C&quote_all=false&with_bom=true"

# Nom du fichier Excel de sortie
OUTPUT_FILENAME = "Front_DisplayMetadataTabs.xlsx"
# Chemin du répertoire de destination
OUTPUT_DIRECTORY = "/Users/francisclement/Documents/PNDB/Moissonnage/Commun/Code/Front_DisplayMetadataTabs" 

# Chemin complet du fichier de sortie
OUTPUT_EXCEL_FILE = os.path.join(OUTPUT_DIRECTORY, OUTPUT_FILENAME)

# Colonnes à utiliser pour le filtrage
DATASET_ID_COLUMN = "datasetid"
KEYWORD_COLUMN = "default.keyword"
FILTER_KEYWORD = "CIRAD"

# En-tête de la colonne dans le fichier Excel final
FINAL_COLUMN_HEADER = "identifier"
# ---------------------

def filter_pndb_datasets():
    """
    Télécharge le catalogue PNDB, filtre les jeux de données contenant le mot-clé IRD (CIRAD ou...),
    et exporte la liste des identifiants dans un fichier Excel à l'emplacement spécifié.
    """
    print(f"--- Démarrage du script de filtrage PNDB ---")
    
    # 1. Création du répertoire de destination si nécessaire
    if not os.path.exists(OUTPUT_DIRECTORY):
        print(f"1. Création du répertoire de destination : {OUTPUT_DIRECTORY}")
        try:
            os.makedirs(OUTPUT_DIRECTORY)
        except OSError as e:
            print(f"   ERREUR : Impossible de créer le répertoire {OUTPUT_DIRECTORY}. Vérifiez les permissions.")
            print(f"   Détails de l'erreur : {e}")
            return
    
    print(f"2. Téléchargement du catalogue CSV depuis PNDB...")

    try:
        # Téléchargement du fichier CSV
        response = requests.get(PNDB_CATALOG_URL)
        response.raise_for_status()  # Lève une exception pour les codes d'erreur HTTP

        print("   ✅ Téléchargement réussi.")

        # Lecture du contenu CSV en mémoire
        csv_data = io.StringIO(response.content.decode('utf-8'))
        
        # Le séparateur dans l'URL est ';'
        df = pd.read_csv(csv_data, sep=';', dtype=str)

        print(f"   Catalogue chargé : {len(df)} jeux de données trouvés.")

        # 3. Vérification et Filtrage
        if DATASET_ID_COLUMN not in df.columns or KEYWORD_COLUMN not in df.columns:
            # Code pour gérer les colonnes manquantes...
            missing_cols = []
            if DATASET_ID_COLUMN not in df.columns: missing_cols.append(DATASET_ID_COLUMN)
            if KEYWORD_COLUMN not in df.columns: missing_cols.append(KEYWORD_COLUMN)
            
            print(f"   ERREUR : Colonnes requises manquantes dans le CSV : {', '.join(missing_cols)}")
            print("   Veuillez vérifier les noms des colonnes du catalogue PNDB.")
            return

        print(f"3. Filtrage des jeux de données contenant '{FILTER_KEYWORD}' dans la colonne '{KEYWORD_COLUMN}'...")
        
        df[KEYWORD_COLUMN] = df[KEYWORD_COLUMN].fillna("")
        
        # Filtrage insensible à la casse
        df_filtered = df[df[KEYWORD_COLUMN].str.contains(FILTER_KEYWORD, case=False, na=False)].copy()

        print(f"   ✅ Filtrage terminé : {len(df_filtered)} jeux de données '{FILTER_KEYWORD}' trouvés.")

        # 4. Création du DataFrame final pour l'exportation
        df_final = pd.DataFrame()
        df_final[FINAL_COLUMN_HEADER] = df_filtered[DATASET_ID_COLUMN]
        
        # 5. Exportation vers le fichier Excel dans le répertoire spécifié
        print(f"4. Exportation de la liste vers le fichier Excel : '{OUTPUT_EXCEL_FILE}'...")
        
        # Utilisation de l'objet ExcelWriter pour forcer le format xlsx
        writer = pd.ExcelWriter(OUTPUT_EXCEL_FILE, engine='xlsxwriter')
        # Écriture dans le fichier Excel (sans index)
        df_final.to_excel(writer, index=False, sheet_name='Sheet1')
        writer.close()

        print(f"\n--- ✅ SUCCÈS ---")
        print(f"Fichier généré : {OUTPUT_EXCEL_FILE}")
        print(f"Nombre d'identifiants exportés : {len(df_final)}")

    except requests.exceptions.RequestException as e:
        print(f"\n--- ❌ ERREUR DE CONNEXION ---")
        print(f"Impossible de télécharger le fichier : {e}")
    except Exception as e:
        print(f"\n--- ❌ ERREUR INATTENDUE ---")
        print(f"Une erreur est survenue lors du traitement : {e}")

if __name__ == "__main__":
    filter_pndb_datasets()