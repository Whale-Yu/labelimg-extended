import os

try:
    from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot
    from PyQt5.QtWidgets import (
        QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
        QProgressBar, QPushButton, QSplitter, QTabWidget, QTableWidget,
        QTableWidgetItem, QVBoxLayout, QWidget)
except ImportError:
    from PyQt4.QtCore import QObject, QThread, pyqtSignal, pyqtSlot
    from PyQt4.QtGui import (
        QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
        QProgressBar, QPushButton, QSplitter, QTabWidget, QTableWidget,
        QTableWidgetItem, QVBoxLayout, QWidget)

from libs.dataset_analyzer import AnalysisCancelled, analyze_yolo_dataset


class DatasetAnalysisWorker(QObject):
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, image_paths, label_dir, class_names):
        super(DatasetAnalysisWorker, self).__init__()
        self.image_paths = list(image_paths)
        self.label_dir = label_dir
        self.class_names = list(class_names)
        self._cancel_requested = False

    def cancel(self):
        self._cancel_requested = True

    @pyqtSlot()
    def run(self):
        try:
            result = analyze_yolo_dataset(
                self.image_paths, self.label_dir, self.class_names,
                progress_callback=self.progress.emit,
                is_cancelled=lambda: self._cancel_requested)
        except AnalysisCancelled:
            self.cancelled.emit()
        except Exception as error:
            self.failed.emit(str(error))
        else:
            self.finished.emit(result)


class DatasetAnalysisPage(QWidget):
    back_requested = pyqtSignal()
    analysis_finished = pyqtSignal(object)

    SUMMARY_METRICS = (
        ('Images', 'images'),
        ('Labels present', 'annotated_images'),
        ('Images with objects', 'object_images'),
        ('Confirmed negatives', 'negative_images'),
        ('Unannotated images', 'unannotated_images'),
        ('Bounding boxes', 'boxes'),
        ('Classes', 'classes'),
        ('Boxes / all images', 'avg_boxes_per_image'),
        ('Boxes / object image', 'avg_boxes_per_object_image'),
        ('Orphan label files', 'orphan_labels'),
        ('Detected issues', 'issues'),
    )
    GEOMETRY_COLUMNS = ('Metric', 'Min', 'P25', 'Median', 'Mean', 'P75', 'P95', 'Max')

    def __init__(self, parent=None):
        super(DatasetAnalysisPage, self).__init__(parent)
        self.image_paths = []
        self.label_dir = None
        self.class_names = []
        self.thread = None
        self.worker = None
        self.last_result = None

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(14, 12, 14, 12)

        header_layout = QHBoxLayout()
        self.back_button = QPushButton(u'← Back to Annotation')
        self.title_label = QLabel('Dataset Analysis')
        self.title_label.setStyleSheet('font-size: 18px; font-weight: bold;')
        self.refresh_button = QPushButton('Analyze / Refresh')
        self.cancel_button = QPushButton('Cancel')
        self.cancel_button.setEnabled(False)
        header_layout.addWidget(self.back_button)
        header_layout.addWidget(self.title_label)
        header_layout.addStretch(1)
        header_layout.addWidget(self.refresh_button)
        header_layout.addWidget(self.cancel_button)
        root_layout.addLayout(header_layout)

        self.context_label = QLabel('Open an image directory to analyze it.')
        self.context_label.setWordWrap(True)
        self.context_label.setStyleSheet('color: #555;')
        root_layout.addWidget(self.context_label)

        progress_layout = QHBoxLayout()
        self.status_label = QLabel('Ready')
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.status_label)
        progress_layout.addWidget(self.progress_bar, 1)
        root_layout.addLayout(progress_layout)

        self.tabs = QTabWidget()
        self.summary_table = self._make_table(('Metric', 'Value'))
        self.class_table = self._make_table(
            ('ID', 'Class', 'Boxes', 'Images', 'Box share'))
        self.geometry_table = self._make_table(self.GEOMETRY_COLUMNS)
        self.resolution_table = self._make_table(
            ('Width', 'Height', 'Images', 'Image share'))
        self.issue_summary_table = self._make_table(('Issue', 'Count'))
        self.issue_detail_table = self._make_table(('Issue', 'File', 'Detail'))

        self.tabs.addTab(self.summary_table, 'Overview')
        self.tabs.addTab(self.class_table, 'Classes')
        self.tabs.addTab(self.geometry_table, 'Box Geometry')
        self.tabs.addTab(self.resolution_table, 'Image Sizes')
        issue_page = QWidget()
        issue_layout = QVBoxLayout(issue_page)
        issue_splitter = QSplitter()
        issue_splitter.addWidget(self.issue_summary_table)
        issue_splitter.addWidget(self.issue_detail_table)
        issue_splitter.setStretchFactor(0, 1)
        issue_splitter.setStretchFactor(1, 3)
        issue_layout.addWidget(issue_splitter)
        self.tabs.addTab(issue_page, 'Data Quality')
        root_layout.addWidget(self.tabs, 1)

        note = QLabel(
            'Scope: YOLO detection labels only. Empty label files are counted '
            'as confirmed negatives; missing label files are unannotated. '
            'Coordinates and area are derived from the current image set.')
        note.setWordWrap(True)
        note.setStyleSheet(
            'padding: 6px; background: #fff8e1; color: #5d4037;')
        root_layout.addWidget(note)

        self.back_button.clicked.connect(self.back_requested.emit)
        self.refresh_button.clicked.connect(self.start_analysis)
        self.cancel_button.clicked.connect(self.cancel_analysis)

    @staticmethod
    def _make_table(headers):
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        if len(headers) > 1:
            table.horizontalHeader().setSectionResizeMode(
                len(headers) - 1, QHeaderView.Stretch)
        return table

    def set_context(self, image_paths, label_dir, class_names,
                    auto_start=True):
        self.image_paths = list(image_paths)
        self.label_dir = label_dir
        self.class_names = list(class_names)
        try:
            image_root = os.path.commonpath(self.image_paths) \
                if self.image_paths else '(none)'
        except ValueError:
            image_root = '(multiple locations)'
        if image_root and not os.path.isdir(image_root):
            image_root = os.path.dirname(image_root)
        self.context_label.setText(
            'Images: {}  |  Labels: {}  |  Loaded images: {}'.format(
                image_root or '(none)', label_dir or '(beside each image)',
                len(self.image_paths)))
        self.refresh_button.setEnabled(bool(self.image_paths))
        if auto_start and self.refresh_button.isEnabled():
            self.start_analysis()

    def start_analysis(self):
        if self.thread is not None and self.thread.isRunning():
            return
        if not self.image_paths:
            self.status_label.setText(
                'Open an image directory before running analysis.')
            return

        self.last_result = None
        self.status_label.setText('Analyzing…')
        self.progress_bar.setRange(0, len(self.image_paths))
        self.progress_bar.setValue(0)
        self.refresh_button.setEnabled(False)
        self.cancel_button.setEnabled(True)

        self.thread = QThread(self)
        self.worker = DatasetAnalysisWorker(
            self.image_paths, self.label_dir, self.class_names)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.worker.cancelled.connect(self._on_cancelled)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.worker.cancelled.connect(self.thread.quit)
        self.thread.finished.connect(self._thread_finished)
        self.thread.start()

    def cancel_analysis(self):
        if self.worker is not None:
            self.worker.cancel()
            self.status_label.setText('Cancelling…')
            self.cancel_button.setEnabled(False)

    def shutdown(self):
        self.cancel_analysis()
        if self.thread is not None and self.thread.isRunning():
            self.thread.quit()
            self.thread.wait()

    def _on_progress(self, current, total):
        self.progress_bar.setRange(0, max(total, 1))
        self.progress_bar.setValue(current)
        self.status_label.setText('Analyzing image {} / {}…'.format(
            current, total))

    def _on_finished(self, result):
        self.last_result = result
        self._render_result(result)
        summary = result['summary']
        self.status_label.setText(
            'Complete: {} images, {} boxes, {} issue(s).'.format(
                summary['images'], summary['boxes'], summary['issues']))
        self.progress_bar.setValue(self.progress_bar.maximum())
        self.analysis_finished.emit(result)

    def _on_failed(self, message):
        self.status_label.setText('Analysis failed: {}'.format(message))
        QMessageBox.warning(self, 'Dataset Analysis', message)

    def _on_cancelled(self):
        self.status_label.setText('Analysis cancelled.')

    def _thread_finished(self):
        if self.worker is not None:
            self.worker.deleteLater()
        if self.thread is not None:
            self.thread.deleteLater()
        self.worker = None
        self.thread = None
        self.refresh_button.setEnabled(bool(self.image_paths))
        self.cancel_button.setEnabled(False)

    @staticmethod
    def _format_number(value):
        if value is None:
            return '—'
        if isinstance(value, float):
            return '{:.4f}'.format(value)
        return str(value)

    @staticmethod
    def _set_rows(table, rows):
        table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(row):
                table.setItem(
                    row_index, column_index,
                    QTableWidgetItem(str(value)))

    def _render_result(self, result):
        summary = result['summary']
        self._set_rows(self.summary_table, [
            (label, self._format_number(summary[key]))
            for label, key in self.SUMMARY_METRICS
        ])
        self._set_rows(self.class_table, [
            (row['id'], row['name'], row['boxes'], row['images'],
             '{:.2f}%'.format(row['percent']))
            for row in result['classes']
        ])
        geometry_rows = []
        for name, stats in result['geometry'].items():
            geometry_rows.append((name,) + tuple(
                self._format_number(stats[key]) if stats else '—'
                for key in ('min', 'p25', 'median', 'mean', 'p75', 'p95', 'max')))
        self._set_rows(self.geometry_table, geometry_rows)
        self._set_rows(self.resolution_table, [
            (row['width'], row['height'], row['images'],
             '{:.2f}%'.format(row['percent']))
            for row in result['resolutions']
        ])
        self._set_rows(self.issue_summary_table, [
            (row['type'], row['count']) for row in result['issue_summary']
        ])
        self._set_rows(self.issue_detail_table, [
            (row['type'], row['file'], row['detail'])
            for row in result['issues']
        ])
