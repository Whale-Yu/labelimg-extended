
import os
import tempfile
from unittest import TestCase

from PyQt5.QtCore import QPointF

from labelImg import get_main_app
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
