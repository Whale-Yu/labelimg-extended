import os
from functools import partial

try:
    from PyQt5.QtCore import Qt, QPoint
    from PyQt5.QtWidgets import *
except ImportError:
    from PyQt4.QtCore import Qt, QPoint
    from PyQt4.QtGui import *

from libs.yolo_class_manager import (
    YoloClassManagementError, YoloClassManager)


class YoloClassManagerPanel(QWidget):

    def __init__(self, parent=None, changed_callback=None):
        super(YoloClassManagerPanel, self).__init__(parent)
        self.main_window = parent
        self.changed_callback = changed_callback
        self.label_dir = None
        self.manager = None
        self.pending_action = None
        self._updating = False

        self.summary_label = QLabel('Open a YOLO label directory.')
        self.summary_label.setWordWrap(True)
        self.refresh_button = QPushButton('Refresh')
        self.refresh_button.setMaximumWidth(80)
        summary_layout = QHBoxLayout()
        summary_layout.addWidget(self.summary_label, 1)
        summary_layout.addWidget(self.refresh_button)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['ID', 'Class', 'Boxes', ''])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setMinimumHeight(120)

        self.message_label = QLabel()
        self.message_label.setWordWrap(True)
        self.message_label.setMinimumHeight(32)

        self.confirm_button = QPushButton('Confirm')
        self.cancel_button = QPushButton('Cancel')
        confirmation_layout = QHBoxLayout()
        confirmation_layout.setContentsMargins(0, 0, 0, 0)
        confirmation_layout.addStretch(1)
        confirmation_layout.addWidget(self.confirm_button)
        confirmation_layout.addWidget(self.cancel_button)
        self.confirm_widget = QWidget()
        self.confirm_widget.setLayout(confirmation_layout)
        self.confirm_widget.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        layout.addLayout(summary_layout)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.message_label)
        layout.addWidget(self.confirm_widget)

        self.refresh_button.clicked.connect(self.refresh)
        self.confirm_button.clicked.connect(self.confirm_pending)
        self.cancel_button.clicked.connect(self.cancel_pending)
        self.set_context(None, False)

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
        context_changed = normalized_dir != self.label_dir or not is_yolo
        self.label_dir = normalized_dir if is_yolo else None
        if not is_yolo:
            self.manager = None
            self.clear_contents()
            self.summary_label.setText('Switch to YOLO mode to manage classes.')
            self.set_message('Class management is disabled in this format.')
            return
        if not self.label_dir:
            self.manager = None
            self.clear_contents()
            self.summary_label.setText('Choose a label directory first.')
            self.set_message('classes.txt is required.')
            return
        if context_changed or force or self.manager is None:
            self.refresh()

    def clear_contents(self):
        self._updating = True
        self.table.setRowCount(0)
        self._updating = False
        self.table.setEnabled(False)
        self.cancel_pending()

    def refresh(self):
        if not self.label_dir:
            return
        self.cancel_pending()
        try:
            self.manager = YoloClassManager(self.label_dir)
        except (OSError, YoloClassManagementError) as error:
            self.manager = None
            self.clear_contents()
            self.summary_label.setText('Unable to load YOLO classes.')
            self.set_message(str(error), 'error')
            return

        self._updating = True
        self.table.setRowCount(len(self.manager.classes))
        for class_id, class_name in enumerate(self.manager.classes):
            count = self.manager.counts[class_id]
            id_item = QTableWidgetItem(str(class_id))
            id_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(class_id, 0, id_item)
            self.table.setItem(class_id, 1, QTableWidgetItem(class_name))
            count_item = QTableWidgetItem(str(count))
            count_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(class_id, 2, count_item)
            action_button = QToolButton(self.table)
            action_button.setText('...')
            action_button.setToolTip('Transfer or delete this class')
            action_button.clicked.connect(partial(
                self.show_class_menu, class_id, action_button))
            self.table.setCellWidget(class_id, 3, action_button)
        self._updating = False

        total_boxes = sum(self.manager.counts)
        self.summary_label.setText(
            '{} classes | {} boxes | {} label files'.format(
                len(self.manager.classes), total_boxes,
                len(self.manager.label_files)))
        self.summary_label.setToolTip(self.label_dir)
        if self.manager.issues:
            self.table.setEnabled(False)
            self.set_message(
                'Changes blocked: {}'.format(' | '.join(self.manager.issues[:3])),
                'error')
        else:
            self.table.setEnabled(True)
            self.set_message(
                'Use ... on a class row to transfer or delete it.')
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setColumnWidth(1, max(120, self.table.columnWidth(1)))
        self.table.setColumnWidth(3, 42)

    def show_class_menu(self, class_id, button):
        if self.manager is None or self.manager.issues:
            return
        menu = QMenu(self)
        transfer_menu = menu.addMenu('Transfer to')
        source_count = self.manager.counts[class_id]
        for target_id, target_name in enumerate(self.manager.classes):
            if target_id == class_id:
                continue
            target_action = transfer_menu.addAction(
                '[{}] {}'.format(target_id, target_name))
            target_action.triggered.connect(partial(
                self.request_transfer, class_id, target_id))
        transfer_menu.setEnabled(
            source_count > 0 and len(self.manager.classes) > 1)

        menu.addSeparator()
        if len(self.manager.classes) <= 1:
            delete_action = menu.addAction('Delete (last class cannot be deleted)')
            delete_action.setEnabled(False)
        elif source_count != 0:
            delete_action = menu.addAction(
                'Delete (requires 0 boxes; current {})'.format(source_count))
            delete_action.setEnabled(False)
        else:
            delete_action = menu.addAction('Delete empty class')
            delete_action.triggered.connect(partial(
                self.request_delete, class_id))
        menu.exec_(button.mapToGlobal(QPoint(0, button.height())))

    def _ensure_clean(self):
        if self.main_window is not None and self.main_window.dirty:
            self.set_message(
                'Save or discard the current image changes before managing classes.',
                'warning')
            return False
        return True

    def request_transfer(self, source_id, target_id, _checked=False):
        if self.manager is None or not self._ensure_clean():
            return
        try:
            plan = self.manager.transfer_plan(source_id, target_id)
        except YoloClassManagementError as error:
            self.set_message(str(error), 'error')
            return
        self.pending_action = ('transfer', source_id, target_id)
        self.confirm_button.setText('Confirm transfer')
        self.confirm_widget.show()
        self.set_message(
            'Move {} box(es) in {} file(s) from [{}] {} to [{}] {}? '
            'The source class will remain with count 0.'.format(
                plan['box_count'], plan['file_count'], source_id,
                self.manager.classes[source_id], target_id,
                self.manager.classes[target_id]),
            'warning')

    def request_delete(self, class_id, _checked=False):
        if self.manager is None or not self._ensure_clean():
            return
        try:
            plan = self.manager.delete_plan(class_id)
        except YoloClassManagementError as error:
            self.set_message(str(error), 'error')
            return
        self.pending_action = ('delete', class_id)
        self.confirm_button.setText('Confirm delete')
        self.confirm_widget.show()
        self.set_message(
            'Delete empty class [{}] {}? {} file(s) with higher IDs '
            'will be renumbered.'.format(
                class_id, self.manager.classes[class_id],
                plan['file_count']),
            'warning')

    def cancel_pending(self):
        self.pending_action = None
        self.confirm_widget.hide()

    def confirm_pending(self):
        if self.pending_action is None or self.manager is None:
            return
        action = self.pending_action
        self.cancel_pending()
        try:
            if action[0] == 'transfer':
                result = self.manager.transfer(action[1], action[2])
                success_text = 'Transferred {} box(es).'.format(
                    result['box_count'])
            else:
                result = self.manager.delete_empty_class(action[1])
                success_text = 'Deleted the empty class.'
        except (OSError, YoloClassManagementError) as error:
            self.set_message(str(error), 'error')
            return

        backup_dir = result['backup_dir']
        self.refresh()
        self.set_message(
            '{} Backup: {}'.format(success_text, backup_dir), 'success')
        if self.changed_callback is not None:
            self.changed_callback(backup_dir)
