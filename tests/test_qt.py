
import os
import tempfile
from unittest import TestCase

from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtGui import QImage
from PyQt5.QtWidgets import QToolButton

from labelImg import get_main_app
from libs.constants import FORMAT_YOLO
from libs.shape import Shape


class TestMainWindow(TestCase):

    app = None
    win = None

    def setUp(self):
        self.settings_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.settings_dir.cleanup)
        self.app, self.win = get_main_app()
        self.win.settings.path = os.path.join(
            self.settings_dir.name, '.labelImgSettings.pkl')

    def tearDown(self):
        self.win.close()
        self.app.quit()

    def test_noop(self):
        pass

    def test_label_list_geometry_updates_when_shape_moves(self):
        shape = Shape(label='target')
        for x, y in ((10, 20), (110, 20), (110, 70), (10, 70)):
            shape.add_point(QPointF(x, y))
        shape.close()

        self.win.add_label(shape)
        item = self.win.label_list.item(0)
        self.assertEqual(
            item.text(), 'target  [x:10 y:20 w:100 h:50 area:5000]')

        self.win.canvas.selected_shape = shape
        shape.points = [point + QPointF(5, 7) for point in shape.points]
        self.win.canvas.shapeMoved.emit()

        self.assertEqual(
            item.text(), 'target  [x:15 y:27 w:100 h:50 area:5000]')
        combo_labels = [
            self.win.combo_box.cb.itemText(index)
            for index in range(self.win.combo_box.cb.count())
        ]
        self.assertIn('target', combo_labels)
        self.win.set_clean()

    def test_no_object_marker_persists_and_does_not_rewrite_classes(self):
        with tempfile.TemporaryDirectory() as output_dir:
            image_path = os.path.join(output_dir, 'negative.png')
            image = QImage(32, 24, QImage.Format_RGB32)
            image.fill(0)
            self.assertTrue(image.save(image_path))

            self.win.default_save_dir = output_dir
            self.win.set_format(FORMAT_YOLO)
            self.assertTrue(self.win.load_file(image_path))

            action = self.win.actions.noObject
            self.assertEqual(action.shortcut().toString(), 'Space')
            self.assertIn('Shortcut: Space', action.toolTip())
            self.assertTrue(any(
                button.defaultAction() is action
                for button in self.win.tools.findChildren(QToolButton)))
            space_actions = [
                button.defaultAction()
                for button in self.win.tools.findChildren(QToolButton)
                if button.defaultAction() is not None
                and button.defaultAction().shortcut().toString() == 'Space'
            ]
            self.assertEqual(space_actions, [action])
            self.assertFalse(hasattr(self.win, 'no_object_button'))
            self.assertFalse(self.win.canvas.no_object_status)
            self.assertIn('Unlabeled', self.win.annotation_status_label.text())

            action.trigger()
            label_path = os.path.join(output_dir, 'negative.txt')
            self.assertTrue(os.path.isfile(label_path))
            self.assertEqual(os.path.getsize(label_path), 0)
            self.assertFalse(os.path.exists(
                os.path.join(output_dir, 'classes.txt')))
            self.assertTrue(action.isChecked())
            self.assertTrue(self.win.canvas.no_object_status)
            self.assertIn(
                'Confirmed no object', self.win.annotation_status_label.text())

            self.assertTrue(self.win.load_file(image_path))
            self.assertTrue(action.isChecked())
            self.assertIn(
                'Confirmed no object', self.win.annotation_status_label.text())

            action.trigger()
            self.assertFalse(os.path.exists(label_path))
            self.assertFalse(action.isChecked())
            self.assertFalse(self.win.canvas.no_object_status)
            self.assertIn('Unlabeled', self.win.annotation_status_label.text())
            self.win.set_clean()

    def test_file_list_annotation_summary_filter_and_navigation(self):
        with tempfile.TemporaryDirectory() as image_dir, \
                tempfile.TemporaryDirectory() as label_dir:
            image_paths = []
            for name in ('a.png', 'b.png', 'c.png'):
                image_path = os.path.join(image_dir, name)
                image = QImage(32, 24, QImage.Format_RGB32)
                image.fill(0)
                self.assertTrue(image.save(image_path))
                image_paths.append(image_path)

            with open(os.path.join(label_dir, 'classes.txt'), 'w') as stream:
                stream.write('target\n')
            with open(os.path.join(label_dir, 'a.txt'), 'w') as stream:
                stream.write('0 0.5 0.5 0.5 0.5\n')
            with open(os.path.join(label_dir, 'b.txt'), 'w'):
                pass

            self.win.default_save_dir = label_dir
            self.win.set_format(FORMAT_YOLO)
            self.win.import_dir_images(image_dir)

            self.assertEqual(self.win.file_list_widget.count(), 3)
            self.assertEqual(self.win.file_count_label.text(), '2/3')
            self.assertEqual(
                [self.win.file_list_widget.item(row).checkState()
                 for row in range(3)],
                [Qt.Checked, Qt.Checked, Qt.Unchecked])
            for row in range(3):
                self.assertFalse(
                    self.win.file_list_widget.item(row).flags()
                    & Qt.ItemIsUserCheckable)

            annotated_index = self.win.file_filter_combo.findData('annotated')
            self.win.file_filter_combo.setCurrentIndex(annotated_index)
            self.assertEqual(
                [self.win.file_list_widget.item(row).isHidden()
                 for row in range(3)],
                [False, False, True])

            unannotated_index = self.win.file_filter_combo.findData('unannotated')
            self.win.file_filter_combo.setCurrentIndex(unannotated_index)
            self.assertEqual(
                [self.win.file_list_widget.item(row).isHidden()
                 for row in range(3)],
                [True, True, False])

            self.win.open_next_image()
            self.assertEqual(self.win.file_path, image_paths[2])

            self.win.actions.noObject.trigger()
            self.assertEqual(self.win.file_count_label.text(), '3/3')
            self.assertEqual(
                self.win.file_list_widget.item(2).checkState(), Qt.Checked)
            self.assertTrue(os.path.isfile(os.path.join(label_dir, 'c.txt')))
            self.assertEqual(os.path.getsize(os.path.join(label_dir, 'c.txt')), 0)

            all_index = self.win.file_filter_combo.findData('all')
            self.win.file_filter_combo.setCurrentIndex(all_index)
            self.assertFalse(any(
                self.win.file_list_widget.item(row).isHidden()
                for row in range(3)))
            self.win.set_clean()
