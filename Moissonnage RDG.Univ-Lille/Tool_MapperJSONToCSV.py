import sys
import json
import os
import glob
from collections import defaultdict

# Importations PySide6
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, 
    QHBoxLayout, QPushButton, QLineEdit, QFileDialog, 
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox, 
    QLabel, QProgressBar, QAbstractItemView, QMessageBox
)
from PySide6.QtCore import (
    QSize, Qt, QThreadPool, QObject, QRunnable, Signal, Slot
)
from PySide6.QtGui import QCursor, QColor, QFont

# ====================================================================
# Fonctions de Traitement des Chemins JSON (Logique Métier)
# ====================================================================

def get_all_paths(data, current_path="", path_list=None):
    """
    Fonction récursive pour découvrir tous les chemins dans la structure JSON.
    Gère spécifiquement le motif 'fields' pour proposer la logique 'find_in_array'.
    """
    if path_list is None:
        path_list = []

    if isinstance(data, dict):
        for key, value in data.items():
            new_path = f"{current_path}.{key}" if current_path else key
            
            # --- Logique de détection de la structure Dataverse (fields) ---
            if new_path.endswith('.fields') and isinstance(value, list) and value:
                
                if isinstance(value[0], dict):
                    for item in value:
                        if isinstance(item, dict) and 'typeName' in item:
                            type_name = item['typeName']
                            
                            if 'value' in item:
                                path_list.append({
                                    "type": "array_lookup",
                                    "typeName": type_name,
                                    "array_path": new_path,
                                    "extraction_key": "value"
                                })
                            elif isinstance(item.get('value'), dict):
                                for sub_key in item['value'].keys():
                                    path_list.append({
                                        "type": "array_lookup_composite",
                                        "typeName": type_name,
                                        "array_path": new_path,
                                        "extraction_key": f"value.{sub_key}"
                                    })
                                
                continue 
            # -------------------------------------------------------------
            
            # Si c'est un tableau de fichiers ou ressources (pour le mapping complexe de liens HTML)
            elif new_path.endswith('.files') and isinstance(value, list):
                 path_list.append({
                    "type": "html_link_list",
                    "list_path": new_path,
                    "csv_column_name": "Lien_Telechargement_Complet"
                })
                 continue
            
            # Récursion normale pour les dictionnaires
            get_all_paths(value, new_path, path_list)
            
    elif isinstance(data, list):
        if len(data) > 0 and isinstance(data[0], (dict, list)):
            get_all_paths(data[0], current_path, path_list)
        elif current_path:
             path_list.append({"type": "simple_list", "json_path": current_path, "transformation": "join_list_with_comma"})

    elif current_path and data is not None:
        path_list.append({"type": "simple", "json_path": current_path})
        
    return path_list


# ====================================================================
# Classe de Travailleur (Worker) - S'exécute dans un Thread séparé
# ====================================================================

class AnalysisSignals(QObject):
    """Signaux disponibles émis par le thread d'analyse."""
    finished = Signal(list)     # Émis avec la liste des mappings finaux
    error = Signal(str)         # Émis en cas d'erreur bloquante
    progress = Signal(int, int, str) # Émis pour mettre à jour la barre de progression

class JsonAnalysisWorker(QRunnable):
    """Effectue l'analyse des fichiers JSON en arrière-plan."""
    def __init__(self, json_dir):
        super().__init__()
        self.json_dir = json_dir
        self.signals = AnalysisSignals()

    @Slot()
    def run(self):
        """Méthode exécutée dans le thread séparé."""
        json_files = glob.glob(os.path.join(self.json_dir, '*.json'))
        if not json_files:
            self.signals.error.emit("Aucun fichier JSON trouvé dans ce répertoire.")
            return

        all_paths_from_files = []
        file_count = len(json_files)

        # 1. Boucle d'analyse des fichiers
        for i, file_path in enumerate(json_files):
            file_name = os.path.basename(file_path)
            # Émission du progrès pour garder l'interface réactive
            self.signals.progress.emit(i + 1, file_count, f"Analyse du fichier {i + 1}/{file_count}: {file_name}")

            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                current_file_paths = get_all_paths(data)
                all_paths_from_files.extend(current_file_paths)
                
            except json.JSONDecodeError:
                print(f"AVERTISSEMENT: Le fichier {file_name} n'est pas un JSON valide et a été ignoré.")
            except Exception as e:
                print(f"Erreur lors de l'analyse du fichier {file_name}: {e}")
        
        # 2. Préparation et normalisation des mappings
        unique_mappings = {}
        for path_info in all_paths_from_files:
            
            key = ""
            csv_name = ""
            
            # Initialise la clé de lookup si nécessaire pour la génération finale du JSON
            if path_info['type'] in ['array_lookup', 'array_lookup_composite']:
                path_info['lookup_key'] = 'typeName'
            
            if path_info['type'] == 'array_lookup':
                key = f"LOOKUP: {path_info['typeName']} -> {path_info['extraction_key']}"
                csv_name = path_info['typeName'].replace('.', '_').replace('-', '_').title()
            elif path_info['type'] == 'array_lookup_composite':
                key = f"LOOKUP COMPOSITE: {path_info['typeName']} -> {path_info['extraction_key']}"
                csv_name = f"{path_info['typeName']}_{path_info['extraction_key'].split('.')[-1]}".replace('.', '_').replace('-', '_').title()
            elif path_info['type'] == 'html_link_list':
                 key = f"LISTE D'OBJETS: {path_info['list_path']}"
                 csv_name = path_info.get('csv_column_name', 'Liens_HTML_Concat').title()
            else: # simple / simple_list
                key = f"SIMPLE: {path_info['json_path']}"
                csv_name = path_info['json_path'].split('.')[-1].replace('.', '_').replace('-', '_').title()

            unique_key = (path_info['type'], path_info.get('typeName'), path_info.get('json_path'), path_info.get('extraction_key'))
            
            if unique_key not in unique_mappings:
                path_info['csv_column_name'] = csv_name 
                path_info['selected'] = True 
                unique_mappings[unique_key] = path_info
        
        # 3. Émission du résultat final
        self.signals.finished.emit(list(unique_mappings.values()))


# ====================================================================
# Classe de l'Application PySide6 (Interface Utilisateur)
# ====================================================================

class JsonMapperApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Générateur de Fichier de Mapping JSON (PySide6 - Multithreadé)")
        self.setMinimumSize(QSize(850, 600))
        
        self.json_dir = ""
        self.discovered_mappings = []
        
        # Le Pool de Threads gère l'exécution des tâches en arrière-plan
        self.threadpool = QThreadPool()
        
        self._setup_ui()
        self.update_table()

    def _setup_ui(self):
        # ------------------- Widgets de base -------------------
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # 1. Section Entrée
        input_group = QGroupBox("Fichiers d'Entrée")
        input_layout = QHBoxLayout(input_group)
        
        self.dir_entry = QLineEdit()
        self.dir_entry.setReadOnly(True)
        self.dir_entry.setPlaceholderText("Chemin du dossier contenant les fichiers JSON")
        self.dir_button = QPushButton("Sélectionner Dossier JSON")
        self.dir_button.clicked.connect(self.select_directory)

        input_layout.addWidget(self.dir_entry)
        input_layout.addWidget(self.dir_button)
        main_layout.addWidget(input_group)

        # 1b. Section Analyse/Progression
        analysis_layout = QVBoxLayout()

        self.analyze_button = QPushButton("Analyser les Fichiers JSON")
        self.analyze_button.setEnabled(False)
        self.analyze_button.clicked.connect(self.analyze_json_files)
        analysis_layout.addWidget(self.analyze_button)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        analysis_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Sélectionnez un dossier pour commencer.")
        analysis_layout.addWidget(self.status_label)
        
        main_layout.addLayout(analysis_layout)

        # 2. Section Tableau de Mapping
        table_title = QLabel("Mappings Découverts (Double-clic sur la colonne CSV pour éditer, Clic sur '✓' pour sélectionner):")
        table_title.setFont(QFont("Arial", 10, QFont.Bold))
        main_layout.addWidget(table_title)
        
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["✓", "Type de Mapping", "Chemin Source", "Nom de Colonne CSV"])
        
        # Redimensionnement des colonnes pour utiliser l'espace disponible
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(1, 150)
        
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked) # Permet l'édition intégrée
        
        self.table.cellClicked.connect(self.toggle_selection)
        self.table.itemChanged.connect(self.save_edit)
        
        main_layout.addWidget(self.table)

        # 3. Section Sortie
        output_group = QGroupBox("Génération du Fichier")
        output_layout = QHBoxLayout(output_group)
        
        output_name_label = QLabel("Nom du fichier de mapping JSON:")
        self.output_entry = QLineEdit("mapping_config.json")
        self.generate_button = QPushButton("Générer Fichier de Mapping")
        self.generate_button.setEnabled(False)
        self.generate_button.clicked.connect(self.generate_mapping_file)

        output_layout.addWidget(output_name_label)
        output_layout.addWidget(self.output_entry)
        output_layout.addWidget(self.generate_button)
        main_layout.addWidget(output_group)
        
    # ------------------- Gestion des Événements UI -------------------

    def select_directory(self):
        """Sélectionne le répertoire et active le bouton d'analyse immédiatement."""
        folder_selected = QFileDialog.getExistingDirectory(self, "Sélectionner le répertoire JSON")
        
        if folder_selected:
            # 1. Mise à jour de l'interface (rapide)
            self.json_dir = folder_selected
            self.dir_entry.setText(folder_selected)
            self.analyze_button.setEnabled(True)
            self.generate_button.setEnabled(False)
            self.status_label.setText("Dossier sélectionné. Prêt à analyser.")
            QApplication.processEvents() # Force le rafraîchissement
            
            # 2. Nettoyage du tableau (moins critique dans Qt mais bonne pratique)
            self.discovered_mappings = []
            self.update_table()

    # ------------------- Gestion du Multithreading -------------------

    def analyze_json_files(self):
        """Démarre l'analyse dans un thread séparé (Worker)."""
        if not self.json_dir:
            QMessageBox.critical(self, "Erreur", "Veuillez sélectionner un répertoire.")
            return

        # 1. Blocage de l'interface et feedback visuel immédiat
        self.analyze_button.setEnabled(False)
        self.generate_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.status_label.setText("Début de l'analyse en arrière-plan... (Interface réactive)")
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor)) 
        
        # 2. Préparation et lancement du Worker
        self.discovered_mappings = [] 
        self.update_table() # Nettoie le tableau avant le lancement

        worker = JsonAnalysisWorker(self.json_dir)
        
        # Connexion des signaux du worker aux slots de l'interface (Main Thread)
        worker.signals.finished.connect(self.analysis_complete)
        worker.signals.error.connect(self.analysis_error)
        worker.signals.progress.connect(self.update_progress)

        # Exécuter le worker dans le pool de threads (non-bloquant)
        self.threadpool.start(worker)

    @Slot(int, int, str)
    def update_progress(self, current, total, message):
        """Reçoit les mises à jour de progression du thread d'analyse."""
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.status_label.setText(message)

    @Slot(list)
    def analysis_complete(self, results):
        """Reçoit les résultats finaux du thread d'analyse."""
        # 1. Mise à jour du modèle de données et du tableau
        self.discovered_mappings = results
        self.update_table()
        
        # 2. Réinitialisation de l'état de l'interface
        self.analyze_button.setEnabled(True)
        self.generate_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        QApplication.restoreOverrideCursor() 
        
        final_message = f"{len(results)} chemins uniques découverts. Analyse terminée."
        self.status_label.setText(final_message)
        QMessageBox.information(self, "Analyse Réussie", final_message)

    @Slot(str)
    def analysis_error(self, message):
        """Gère les erreurs provenant du thread d'analyse."""
        # Réinitialisation de l'état de l'interface
        self.analyze_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        QApplication.restoreOverrideCursor() 
        self.status_label.setText("Erreur lors de l'analyse. Veuillez vérifier la console.")
        QMessageBox.critical(self, "Erreur d'Analyse", message)

    # ------------------- Gestion du Tableau -------------------

    def update_table(self):
        """Peuple le QTableWidget à partir de la liste interne des mappings."""
        self.table.setRowCount(len(self.discovered_mappings))

        for i, mapping in enumerate(self.discovered_mappings):
            is_selected = mapping.get('selected', False)
            display_select = " [✓] " if is_selected else " [✗] " 
            display_type = mapping['type'].replace('_', ' ').upper()
            
            if mapping['type'] in ['array_lookup', 'array_lookup_composite']:
                path_display = f"{mapping['typeName']} ({mapping['extraction_key']})"
            elif mapping['type'] == 'html_link_list':
                path_display = mapping['list_path']
            else:
                path_display = mapping['json_path']
            
            csv_name = mapping['csv_column_name']

            # Couleur de fond pour indiquer la sélection
            color = QColor(240, 255, 240) if is_selected else QColor(255, 255, 255)
            
            # Colonne 0: Sélection
            item_select = QTableWidgetItem(display_select)
            item_select.setTextAlignment(Qt.AlignCenter)
            item_select.setFlags(item_select.flags() & ~Qt.ItemIsEditable) # Non éditable
            item_select.setBackground(color)
            self.table.setItem(i, 0, item_select)
            
            # Colonnes 1-2: Type et Chemin (Non éditables)
            item_type = QTableWidgetItem(display_type)
            item_type.setFlags(item_type.flags() & ~Qt.ItemIsEditable)
            item_type.setBackground(color)
            self.table.setItem(i, 1, item_type)
            
            item_path = QTableWidgetItem(path_display)
            item_path.setFlags(item_path.flags() & ~Qt.ItemIsEditable)
            item_path.setBackground(color)
            self.table.setItem(i, 2, item_path)
            
            # Colonnes 3: Nom de Colonne CSV (Éditable)
            item_csv = QTableWidgetItem(csv_name)
            item_csv.setBackground(color)
            # Pas besoin de setFlags car par défaut, l'édition est autorisée via setEditTriggers
            self.table.setItem(i, 3, item_csv)

    @Slot(int, int)
    def toggle_selection(self, row, column):
        """Gère le clic sur la colonne de sélection (#0) pour basculer l'état."""
        if column == 0 and row < len(self.discovered_mappings):
            mapping = self.discovered_mappings[row]
            mapping['selected'] = not mapping.get('selected', False)
            
            # Mise à jour sélective pour la fluidité
            self.update_table() # Rafraîchit visuellement la ligne

    @Slot(QTableWidgetItem)
    def save_edit(self, item):
        """Sauvegarde la nouvelle valeur éditée lorsque l'édition d'une cellule se termine."""
        row = item.row()
        column = item.column()

        if column == 3 and row < len(self.discovered_mappings):
            new_value = item.text().strip()
            
            if new_value:
                # Mise à jour du modèle de données interne
                self.discovered_mappings[row]['csv_column_name'] = new_value
            else:
                # Si la valeur est vide, on restaure l'ancienne valeur
                old_value = self.discovered_mappings[row]['csv_column_name']
                item.setText(old_value)


    # ------------------- Génération de Sortie -------------------

    def generate_mapping_file(self):
        """Génère le fichier de mapping JSON final."""
        output_name = self.output_entry.text().strip()
        if not output_name or not output_name.endswith('.json'):
            QMessageBox.critical(self, "Erreur", "Veuillez spécifier un nom de fichier JSON valide.")
            return

        final_mapping_list = []
        selected_mappings = [m for m in self.discovered_mappings if m.get('selected', False)]

        if not selected_mappings:
            QMessageBox.warning(self, "Avertissement", "Aucun mapping n'est sélectionné. Le fichier généré sera vide.")
            return

        for mapping in selected_mappings:
            output_item = {"csv_column_name": mapping['csv_column_name']}

            if mapping['type'] == 'array_lookup':
                output_item.update({
                    "array_path": mapping['array_path'],
                    "lookup_key": "typeName",
                    "lookup_value": mapping['typeName'],
                    "extraction_key": mapping['extraction_key'],
                    "transformation": "find_in_array"
                })
            elif mapping['type'] == 'array_lookup_composite':
                 output_item.update({
                    "array_path": mapping['array_path'],
                    "lookup_key": "typeName",
                    "lookup_value": mapping['typeName'],
                    "extraction_key": mapping['extraction_key'],
                    "transformation": "find_in_composite_array"
                })
            elif mapping['type'] == 'html_link_list':
                output_item.update({
                    "list_path": mapping['list_path'],
                    "transformation": "join_html_links",
                    "link_template": {
                        "url_path": "dataFile.persistentId",
                        "label_path": "label",
                        "base_url": "https://entrepot.recherche.data.gouv.fr/api/datasets/export?exporter=dataverse_json&persistentId="
                    }
                })
            elif mapping['type'] == 'simple_list':
                 output_item.update({
                    "json_path": mapping['json_path'],
                    "transformation": "join_list_with_comma"
                })
            else: 
                output_item.update({
                    "json_path": mapping['json_path']
                })
            
            final_mapping_list.append(output_item)
        
        try:
            # Enregistrement du fichier
            with open(output_name, 'w', encoding='utf-8') as f:
                json.dump(final_mapping_list, f, indent=4, ensure_ascii=False)
            
            QMessageBox.information(self, "Succès", f"Le fichier de mapping a été généré avec succès :\n{os.path.abspath(output_name)}")
            
        except Exception as e:
            QMessageBox.critical(self, "Erreur de Sauvegarde", f"Impossible de sauvegarder le fichier : {e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = JsonMapperApp()
    window.show()
    sys.exit(app.exec())