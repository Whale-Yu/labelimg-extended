import os
import tempfile
from unittest import TestCase

from PyQt5.QtGui import QImage

from libs.dataset_analyzer import AnalysisCancelled, analyze_yolo_dataset


class TestDatasetAnalyzer(TestCase):

    def test_yolo_summary_geometry_and_quality_issues(self):
        with tempfile.TemporaryDirectory() as root_dir:
            image_dir = os.path.join(root_dir, 'images')
            label_dir = os.path.join(root_dir, 'labels')
            os.mkdir(image_dir)
            os.mkdir(label_dir)
            image_paths = []
            for name in ('a.png', 'b.png', 'c.png'):
                path = os.path.join(image_dir, name)
                image = QImage(100, 50, QImage.Format_RGB32)
                image.fill(0)
                self.assertTrue(image.save(path))
                image_paths.append(path)

            with open(os.path.join(label_dir, 'a.txt'), 'w') as stream:
                stream.write(
                    '0 0.5 0.5 0.2 0.4\n'
                    '0 0.5 0.5 0.2 0.4\n'
                    '0 0.95 0.5 0.2 0.2\n'
                    '4 0.5 0.5 0.1 0.1\n')
            with open(os.path.join(label_dir, 'b.txt'), 'w'):
                pass
            with open(os.path.join(label_dir, 'orphan.txt'), 'w') as stream:
                stream.write('0 0.5 0.5 0.1 0.1\n')

            progress = []
            result = analyze_yolo_dataset(
                image_paths, label_dir, ['target'],
                progress_callback=lambda current, total: progress.append(
                    (current, total)))

            summary = result['summary']
            self.assertEqual(summary['images'], 3)
            self.assertEqual(summary['annotated_images'], 2)
            self.assertEqual(summary['object_images'], 1)
            self.assertEqual(summary['negative_images'], 1)
            self.assertEqual(summary['unannotated_images'], 1)
            self.assertEqual(summary['boxes'], 3)
            self.assertEqual(summary['orphan_labels'], 1)
            self.assertEqual(result['classes'][0]['boxes'], 3)
            self.assertEqual(result['classes'][0]['images'], 1)
            self.assertEqual(
                result['geometry']['pixel width']['median'], 20.0)
            self.assertEqual(result['resolutions'][0]['images'], 3)
            issue_types = {
                row['type']: row['count'] for row in result['issue_summary']
            }
            self.assertEqual(issue_types['duplicate box'], 1)
            self.assertEqual(issue_types['box outside image'], 1)
            self.assertEqual(issue_types['class ID out of range'], 1)
            self.assertEqual(issue_types['orphan label'], 1)
            self.assertEqual(progress[-1], (3, 3))

    def test_analysis_can_be_cancelled(self):
        with self.assertRaises(AnalysisCancelled):
            analyze_yolo_dataset(
                ['unused.png'], None, [], is_cancelled=lambda: True)

    def test_labels_beside_images_follow_nested_directories(self):
        with tempfile.TemporaryDirectory() as root_dir:
            image_paths = []
            for directory_name in ('one', 'two'):
                directory = os.path.join(root_dir, directory_name)
                os.mkdir(directory)
                image_path = os.path.join(directory, 'same.png')
                image = QImage(20, 20, QImage.Format_RGB32)
                image.fill(0)
                self.assertTrue(image.save(image_path))
                image_paths.append(image_path)
                with open(os.path.join(directory, 'same.txt'), 'w') as stream:
                    stream.write('0 0.5 0.5 0.5 0.5\n')

            result = analyze_yolo_dataset(
                image_paths, None, ['target'])

            self.assertEqual(result['summary']['annotated_images'], 2)
            self.assertEqual(result['summary']['boxes'], 2)
            self.assertFalse(any(
                row['type'] == 'duplicate image stem'
                for row in result['issue_summary']))
