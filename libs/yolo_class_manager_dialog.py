try:
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import *
except ImportError:
    from PyQt4.QtCore import Qt
    from PyQt4.QtGui import *

from libs.yolo_class_manager import (
    YoloClassManagementError, YoloClassManager)


class YoloClassManagerDialog(QDialog):

    def __init__(self, label_dir, parent=None):
        super(YoloClassManagerDialog, self).__init__(parent)
        self.label_dir = label_dir
        self.manager = None
        self.changed = False
        self.setWindowTitle('Manage YOLO Classes')
        self.resize(720, 520)

        self.directory_label = QLabel(
            'Label directory: {}'.format(self.label_dir))
        self.directory_label.setWordWrap(True)
        self.summary_label = QLabel()
        self.issue_label = QLabel()
        self.issue_label.setWordWrap(True)
        self.issue_label.setStyleSheet('color: #b71c1c; font-weight: bold;')

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(['ID', 'Class', 'Box count'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)

        self.source_combo = QComboBox()
        self.target_combo = QComboBox()
        self.transfer_button = QPushButton('Transfer A to B')
        self.transfer_button.setToolTip(
            'Reassign every box from A to B. Class A remains and becomes empty.')
        self.delete_button = QPushButton('Delete selected empty class')
        self.delete_button.setToolTip(
            'Deletion is allowed only when the selected class has zero boxes.')

        transfer_layout = QGridLayout()
        transfer_layout.addWidget(QLabel('A (source)'), 0, 0)
        transfer_layout.addWidget(self.source_combo, 0, 1)
        transfer_layout.addWidget(QLabel('B (target)'), 1, 0)
        transfer_layout.addWidget(self.target_combo, 1, 1)
        transfer_layout.addWidget(self.transfer_button, 0, 2, 2, 1)

        close_button = QPushButton('Close')
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.delete_button)
        button_layout.addStretch(1)
        button_layout.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.directory_label)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.issue_label)
        layout.addWidget(self.table, 1)
        layout.addLayout(transfer_layout)
        layout.addLayout(button_layout)

        self.transfer_button.clicked.connect(self.transfer_classes)
        self.delete_button.clicked.connect(self.delete_selected_class)
        close_button.clicked.connect(self.accept)
        self.refresh()

    def refresh(self):
        try:
            self.manager = YoloClassManager(self.label_dir)
        except YoloClassManagementError as error:
            self.manager = None
            self.issue_label.setText(str(error))
            self.transfer_button.setEnabled(False)
            self.delete_button.setEnabled(False)
            return

        self.table.setRowCount(len(self.manager.classes))
        self.source_combo.clear()
        self.target_combo.clear()
        for class_id, class_name in enumerate(self.manager.classes):
            count = self.manager.counts[class_id]
            self.table.setItem(class_id, 0, QTableWidgetItem(str(class_id)))
            self.table.setItem(class_id, 1, QTableWidgetItem(class_name))
            self.table.setItem(class_id, 2, QTableWidgetItem(str(count)))
            combo_text = '[{}] {} ({} boxes)'.format(
                class_id, class_name, count)
            self.source_combo.addItem(combo_text, class_id)
            self.target_combo.addItem(combo_text, class_id)
        if self.target_combo.count() > 1:
            self.target_combo.setCurrentIndex(1)

        total_boxes = sum(self.manager.counts)
        self.summary_label.setText(
            '{} classes, {} boxes, {} label files (current directory only)'.format(
                len(self.manager.classes), total_boxes,
                len(self.manager.label_files)))
        if self.manager.issues:
            self.issue_label.setText(
                'Changes are disabled because the dataset has problems:\n{}'.format(
                    '\n'.join(self.manager.issues[:5])))
            enabled = False
        else:
            self.issue_label.setText(
                'Every operation creates a backup under .labelimg_class_backups.')
            self.issue_label.setStyleSheet('color: #2e7d32;')
            enabled = True
        self.transfer_button.setEnabled(enabled and len(self.manager.classes) > 1)
        self.delete_button.setEnabled(enabled)
        self.table.resizeColumnsToContents()

    def transfer_classes(self):
        source_id = self.source_combo.currentData()
        target_id = self.target_combo.currentData()
        try:
            plan = self.manager.transfer_plan(source_id, target_id)
        except YoloClassManagementError as error:
            QMessageBox.warning(self, 'Manage Classes', str(error))
            return
        message = (
            'Transfer {boxes} box(es) in {files} file(s)\n'
            'from [{source}] {source_name}\n'
            'to [{target}] {target_name}?\n\n'
            'Class A will remain in classes.txt with zero boxes.\n'
            'An automatic backup will be created.').format(
                boxes=plan['box_count'], files=plan['file_count'],
                source=source_id, source_name=self.manager.classes[source_id],
                target=target_id, target_name=self.manager.classes[target_id])
        if QMessageBox.question(
                self, 'Confirm class transfer', message,
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            result = self.manager.transfer(source_id, target_id)
        except (OSError, YoloClassManagementError) as error:
            QMessageBox.critical(self, 'Class transfer failed', str(error))
            return
        self.changed = True
        self.refresh()
        QMessageBox.information(
            self, 'Class transfer complete',
            'Transferred {} box(es).\nBackup: {}'.format(
                result['box_count'], result['backup_dir']))

    def delete_selected_class(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(
                self, 'Manage Classes', 'Select one class row first.')
            return
        class_id = selected_rows[0].row()
        try:
            plan = self.manager.delete_plan(class_id)
        except YoloClassManagementError as error:
            QMessageBox.warning(self, 'Cannot delete class', str(error))
            return
        message = (
            'Delete empty class [{class_id}] {name}?\n\n'
            '{files} label file(s) contain higher class IDs and will be '
            'renumbered. An automatic backup will be created.').format(
                class_id=class_id, name=self.manager.classes[class_id],
                files=plan['file_count'])
        if QMessageBox.question(
                self, 'Confirm class deletion', message,
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            result = self.manager.delete_empty_class(class_id)
        except (OSError, YoloClassManagementError) as error:
            QMessageBox.critical(self, 'Class deletion failed', str(error))
            return
        self.changed = True
        self.refresh()
        QMessageBox.information(
            self, 'Class deletion complete',
            'Deleted the empty class.\nBackup: {}'.format(
                result['backup_dir']))
