import os

try:
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import *
except ImportError:
    from PyQt4.QtCore import Qt
    from PyQt4.QtGui import *

from libs.yolo_class_manager import (
    YoloClassManagementError, YoloClassManager)


class YoloClassManagerPanel(QGroupBox):

    def __init__(self, parent=None, changed_callback=None):
        super(YoloClassManagerPanel, self).__init__('YOLO Classes', parent)
        self.main_window = parent
        self.changed_callback = changed_callback
        self.label_dir = None
        self.manager = None
        self.pending_action = None
        self._updating = False
        self.setCheckable(True)
        self.setChecked(False)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)

        self.summary_label = QLabel('Open a YOLO label directory.')
        self.summary_label.setWordWrap(True)
        self.refresh_button = QPushButton('Refresh')
        self.refresh_button.setMaximumWidth(80)

        summary_layout = QHBoxLayout()
        summary_layout.addWidget(self.summary_label, 1)
        summary_layout.addWidget(self.refresh_button)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(['ID', 'Class', 'Boxes'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setMaximumHeight(130)

        self.source_combo = QComboBox()
        self.target_combo = QComboBox()
        transfer_layout = QGridLayout()
        transfer_layout.setContentsMargins(0, 0, 0, 0)
        self.source_label = QLabel('A')
        self.target_label = QLabel('B')
        transfer_layout.addWidget(self.source_label, 0, 0)
        transfer_layout.addWidget(self.source_combo, 0, 1)
        transfer_layout.addWidget(self.target_label, 1, 0)
        transfer_layout.addWidget(self.target_combo, 1, 1)

        self.transfer_button = QPushButton('Transfer A to B')
        self.delete_button = QPushButton('Delete selected empty class')
        action_layout = QHBoxLayout()
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.addWidget(self.transfer_button)
        action_layout.addWidget(self.delete_button)

        self.message_label = QLabel()
        self.message_label.setWordWrap(True)
        self.message_label.setMinimumHeight(32)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        layout.addLayout(summary_layout)
        layout.addWidget(self.table)
        layout.addLayout(transfer_layout)
        layout.addLayout(action_layout)
        layout.addWidget(self.message_label)

        self.refresh_button.clicked.connect(self.refresh)
        self.transfer_button.clicked.connect(self.transfer_clicked)
        self.delete_button.clicked.connect(self.delete_clicked)
        self.source_combo.currentIndexChanged.connect(self.cancel_pending)
        self.target_combo.currentIndexChanged.connect(self.cancel_pending)
        self.table.itemSelectionChanged.connect(self.cancel_pending)
        self.toggled.connect(self.set_panel_expanded)
        self._content_widgets = (
            self.summary_label, self.refresh_button, self.table,
            self.source_label, self.target_label,
            self.source_combo, self.target_combo,
            self.transfer_button, self.delete_button, self.message_label)
        self.set_panel_expanded(False)
        self.set_context(None, False)

    def set_panel_expanded(self, expanded):
        for widget in self._content_widgets:
            widget.setVisible(expanded)

    @staticmethod
    def _combo_class_id(combo):
        value = combo.itemData(combo.currentIndex())
        if hasattr(value, 'toInt'):
            value, converted = value.toInt()
            return value if converted else None
        return value

    def set_message(self, text, state='neutral'):
        colors = {
            'neutral': '#616161',
            'success': '#1b5e20',
            'warning': '#e65100',
            'error': '#b71c1c',
        }
        self.message_label.setStyleSheet(
            'color: {}; font-weight: {};'.format(
                colors.get(state, colors['neutral']),
                'bold' if state != 'neutral' else 'normal'))
        self.message_label.setText(text)

    def set_context(self, label_dir, is_yolo=True, force=False):
        normalized_dir = os.path.abspath(label_dir) if label_dir else None
        context_changed = (
            normalized_dir != self.label_dir or not is_yolo)
        self.label_dir = normalized_dir if is_yolo else None
        if not is_yolo:
            self.manager = None
            self.clear_contents()
            self.setTitle('YOLO Classes')
            self.summary_label.setText('Switch to YOLO mode to manage classes.')
            self.set_message('Class management is disabled in this format.')
            return
        if not self.label_dir:
            self.manager = None
            self.clear_contents()
            self.setTitle('YOLO Classes')
            self.summary_label.setText('Choose a label directory first.')
            self.set_message('classes.txt is required.')
            return
        if context_changed or force or self.manager is None:
            self.refresh()

    def clear_contents(self):
        self._updating = True
        self.table.setRowCount(0)
        self.source_combo.clear()
        self.target_combo.clear()
        self._updating = False
        self.set_controls_enabled(False)
        self.reset_pending()

    def set_controls_enabled(self, enabled):
        self.table.setEnabled(enabled)
        self.source_combo.setEnabled(enabled)
        self.target_combo.setEnabled(enabled)
        self.transfer_button.setEnabled(enabled and self.source_combo.count() > 1)
        self.delete_button.setEnabled(enabled and self.table.rowCount() > 1)

    def refresh(self):
        if not self.label_dir:
            return
        self.reset_pending()
        try:
            self.manager = YoloClassManager(self.label_dir)
        except (OSError, YoloClassManagementError) as error:
            self.manager = None
            self.clear_contents()
            self.setTitle('YOLO Classes')
            self.summary_label.setText('Unable to load YOLO classes.')
            self.set_message(str(error), 'error')
            return

        self._updating = True
        self.table.setRowCount(len(self.manager.classes))
        self.source_combo.clear()
        self.target_combo.clear()
        for class_id, class_name in enumerate(self.manager.classes):
            count = self.manager.counts[class_id]
            self.table.setItem(class_id, 0, QTableWidgetItem(str(class_id)))
            self.table.setItem(class_id, 1, QTableWidgetItem(class_name))
            count_item = QTableWidgetItem(str(count))
            count_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(class_id, 2, count_item)
            combo_text = '[{}] {} ({})'.format(class_id, class_name, count)
            self.source_combo.addItem(combo_text, class_id)
            self.target_combo.addItem(combo_text, class_id)
        if self.target_combo.count() > 1:
            self.target_combo.setCurrentIndex(1)
        self._updating = False

        total_boxes = sum(self.manager.counts)
        self.setTitle('YOLO Classes ({} / {} boxes)'.format(
            len(self.manager.classes), total_boxes))
        self.summary_label.setText(
            '{} classes | {} boxes | {} label files'.format(
                len(self.manager.classes), total_boxes,
                len(self.manager.label_files)))
        self.summary_label.setToolTip(self.label_dir)
        if self.manager.issues:
            self.set_controls_enabled(False)
            self.set_message(
                'Changes blocked: {}'.format(' | '.join(self.manager.issues[:3])),
                'error')
        else:
            self.set_controls_enabled(True)
            self.set_message(
                'Transfer keeps A; delete is allowed only when its count is 0.')
        self.table.resizeColumnsToContents()

    def reset_pending(self):
        self.pending_action = None
        self.transfer_button.setText('Transfer A to B')
        self.delete_button.setText('Delete selected empty class')

    def cancel_pending(self, _value=None):
        if self._updating or self.pending_action is None:
            return
        self.reset_pending()
        self.set_message('Pending operation cancelled because the selection changed.')
        if self.manager is not None and not self.manager.issues:
            self.set_controls_enabled(True)

    def _ensure_clean(self):
        if self.main_window is not None and self.main_window.dirty:
            self.set_message(
                'Save or discard the current image changes before managing classes.',
                'warning')
            return False
        return True

    def transfer_clicked(self):
        if self.manager is None or not self._ensure_clean():
            return
        source_id = self._combo_class_id(self.source_combo)
        target_id = self._combo_class_id(self.target_combo)
        action_key = ('transfer', source_id, target_id)
        if self.pending_action != action_key:
            try:
                plan = self.manager.transfer_plan(source_id, target_id)
            except YoloClassManagementError as error:
                self.set_message(str(error), 'error')
                return
            self.pending_action = action_key
            self.transfer_button.setText('Confirm transfer')
            self.delete_button.setEnabled(False)
            self.set_message(
                'Confirm: move {} box(es) in {} file(s) from A to B. '
                'A will remain with count 0.'.format(
                    plan['box_count'], plan['file_count']),
                'warning')
            return

        try:
            result = self.manager.transfer(source_id, target_id)
        except (OSError, YoloClassManagementError) as error:
            self.reset_pending()
            self.set_message(str(error), 'error')
            return
        backup_dir = result['backup_dir']
        self.refresh()
        self.set_message(
            'Transferred {} box(es). Backup: {}'.format(
                result['box_count'], backup_dir), 'success')
        if self.changed_callback is not None:
            self.changed_callback(backup_dir)

    def delete_clicked(self):
        if self.manager is None or not self._ensure_clean():
            return
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            self.set_message('Select one class row first.', 'warning')
            return
        class_id = selected_rows[0].row()
        action_key = ('delete', class_id)
        if self.pending_action != action_key:
            try:
                plan = self.manager.delete_plan(class_id)
            except YoloClassManagementError as error:
                self.set_message(str(error), 'error')
                return
            self.pending_action = action_key
            self.delete_button.setText('Confirm delete')
            self.transfer_button.setEnabled(False)
            self.set_message(
                'Confirm: delete empty class [{}] {}. {} file(s) with '
                'higher IDs will be renumbered.'.format(
                    class_id, self.manager.classes[class_id],
                    plan['file_count']),
                'warning')
            return

        try:
            result = self.manager.delete_empty_class(class_id)
        except (OSError, YoloClassManagementError) as error:
            self.reset_pending()
            self.set_message(str(error), 'error')
            return
        backup_dir = result['backup_dir']
        self.refresh()
        self.set_message(
            'Deleted the empty class. Backup: {}'.format(backup_dir),
            'success')
        if self.changed_callback is not None:
            self.changed_callback(backup_dir)
