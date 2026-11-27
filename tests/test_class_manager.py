import io
import json
import os
import tempfile
from unittest import TestCase, mock

from libs.yolo_class_manager import (
    YoloClassManagementError, YoloClassManager)


class TestYoloClassManager(TestCase):

    @staticmethod
    def write(path, text):
        with io.open(path, 'w', encoding='utf-8', newline='') as stream:
            stream.write(text)

    @staticmethod
    def read(path):
        with io.open(path, 'r', encoding='utf-8', newline='') as stream:
            return stream.read()

    def test_transfer_then_delete_empty_class_and_renumber(self):
        with tempfile.TemporaryDirectory() as root_dir:
            label_dir = os.path.join(root_dir, 'labels')
            os.mkdir(label_dir)
            classes_path = os.path.join(label_dir, 'classes.txt')
            first_path = os.path.join(label_dir, 'first.txt')
            second_path = os.path.join(label_dir, 'second.txt')
            negative_path = os.path.join(label_dir, 'negative.txt')
            self.write(classes_path, 'A\nB\nC\nUnused\n')
            self.write(
                first_path,
                '0 0.5 0.5 0.2 0.2\n  2 0.4 0.4 0.1 0.1\n')
            self.write(second_path, '1 0.5 0.5 0.3 0.3\n')
            self.write(negative_path, '')

            manager = YoloClassManager(label_dir)
            self.assertEqual(manager.classes, ['A', 'B', 'C', 'Unused'])
            self.assertEqual(manager.counts, [1, 1, 1, 0])

            transfer = manager.transfer(0, 1)
            self.assertEqual(transfer['box_count'], 1)
            self.assertEqual(transfer['file_count'], 1)
            self.assertTrue(os.path.isdir(transfer['backup_dir']))
            self.assertEqual(manager.classes, ['A', 'B', 'C', 'Unused'])
            self.assertEqual(manager.counts, [0, 2, 1, 0])
            self.assertEqual(
                self.read(first_path),
                '1 0.5 0.5 0.2 0.2\n  2 0.4 0.4 0.1 0.1\n')

            deletion = manager.delete_empty_class(0)
            self.assertEqual(manager.classes, ['B', 'C', 'Unused'])
            self.assertEqual(manager.counts, [2, 1, 0])
            self.assertEqual(
                self.read(first_path),
                '0 0.5 0.5 0.2 0.2\n  1 0.4 0.4 0.1 0.1\n')
            self.assertEqual(
                self.read(second_path), '0 0.5 0.5 0.3 0.3\n')
            self.assertEqual(self.read(negative_path), '')
            manifest_path = os.path.join(
                deletion['backup_dir'], 'manifest.json')
            with io.open(manifest_path, 'r', encoding='utf-8') as stream:
                manifest = json.load(stream)
            self.assertEqual(manifest['operation'], 'delete')

    def test_nonempty_class_cannot_be_deleted(self):
        with tempfile.TemporaryDirectory() as label_dir:
            self.write(os.path.join(label_dir, 'classes.txt'), 'A\nB\n')
            self.write(
                os.path.join(label_dir, 'one.txt'),
                '0 0.5 0.5 0.2 0.2\n')
            manager = YoloClassManager(label_dir)
            with self.assertRaises(YoloClassManagementError):
                manager.delete_empty_class(0)

    def test_invalid_class_id_blocks_all_changes(self):
        with tempfile.TemporaryDirectory() as label_dir:
            self.write(os.path.join(label_dir, 'classes.txt'), 'A\n')
            self.write(
                os.path.join(label_dir, 'bad.txt'),
                '3 0.5 0.5 0.2 0.2\n')
            manager = YoloClassManager(label_dir)
            self.assertTrue(manager.issues)
            with self.assertRaises(YoloClassManagementError):
                manager.transfer_plan(0, 0)

    def test_last_remaining_class_cannot_be_deleted(self):
        with tempfile.TemporaryDirectory() as label_dir:
            self.write(os.path.join(label_dir, 'classes.txt'), 'Only\n')
            self.write(os.path.join(label_dir, 'negative.txt'), '')
            manager = YoloClassManager(label_dir)
            with self.assertRaises(YoloClassManagementError):
                manager.delete_empty_class(0)

    def test_partial_write_failure_restores_original_files(self):
        with tempfile.TemporaryDirectory() as root_dir:
            label_dir = os.path.join(root_dir, 'labels')
            os.mkdir(label_dir)
            classes_path = os.path.join(label_dir, 'classes.txt')
            label_path = os.path.join(label_dir, 'one.txt')
            self.write(classes_path, 'Empty\nUsed\n')
            self.write(label_path, '1 0.5 0.5 0.2 0.2\n')
            manager = YoloClassManager(label_dir)

            original_replace = os.replace
            replace_count = [0]

            def fail_second_replace(source, target):
                replace_count[0] += 1
                if replace_count[0] == 2:
                    raise OSError('simulated replacement failure')
                return original_replace(source, target)

            with mock.patch(
                    'libs.yolo_class_manager.os.replace',
                    side_effect=fail_second_replace):
                with self.assertRaises(OSError):
                    manager.delete_empty_class(0)

            self.assertEqual(self.read(classes_path), 'Empty\nUsed\n')
            self.assertEqual(
                self.read(label_path), '1 0.5 0.5 0.2 0.2\n')
