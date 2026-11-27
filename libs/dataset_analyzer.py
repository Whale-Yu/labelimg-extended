import collections
import io
import math
import os

try:
    from PyQt5.QtGui import QImageReader
except ImportError:
    from PyQt4.QtGui import QImageReader


class AnalysisCancelled(Exception):
    pass


def _percentile(sorted_values, fraction):
    if not sorted_values:
        return None
    position = (len(sorted_values) - 1) * fraction
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return sorted_values[lower]
    weight = position - lower
    return (sorted_values[lower] * (1.0 - weight) +
            sorted_values[upper] * weight)


def _describe(values):
    if not values:
        return None
    values = sorted(values)
    return {
        'min': values[0],
        'p25': _percentile(values, 0.25),
        'median': _percentile(values, 0.50),
        'mean': sum(values) / float(len(values)),
        'p75': _percentile(values, 0.75),
        'p95': _percentile(values, 0.95),
        'max': values[-1],
    }


def analyze_yolo_dataset(image_paths, label_dir, class_names,
                         progress_callback=None, is_cancelled=None):
    image_paths = list(image_paths)
    class_names = list(class_names)
    total_images = len(image_paths)
    class_box_counts = [0] * len(class_names)
    class_image_counts = [0] * len(class_names)
    resolution_counts = collections.Counter()
    issue_counts = collections.Counter()
    issues = []
    normalized_widths = []
    normalized_heights = []
    normalized_areas = []
    pixel_widths = []
    pixel_heights = []
    pixel_areas = []
    annotated_images = 0
    object_images = 0
    negative_images = 0
    total_boxes = 0
    def label_directory_for_image(image_path):
        return label_dir if label_dir else os.path.dirname(image_path)

    def label_key(image_path):
        return (
            os.path.normcase(os.path.abspath(
                label_directory_for_image(image_path))),
            os.path.splitext(os.path.basename(image_path))[0])

    image_label_keys = collections.Counter(
        label_key(path) for path in image_paths)

    def add_issue(issue_type, path, detail):
        issue_counts[issue_type] += 1
        if len(issues) < 1000:
            issues.append({
                'type': issue_type,
                'file': os.path.basename(path),
                'path': path,
                'detail': detail,
            })

    for (directory, stem), count in image_label_keys.items():
        if count > 1:
            add_issue(
                'duplicate image stem', os.path.join(directory, stem),
                '{} images resolve to the same YOLO label file.'.format(count))

    for image_index, image_path in enumerate(image_paths):
        if is_cancelled is not None and is_cancelled():
            raise AnalysisCancelled()
        if progress_callback is not None and (
                image_index == 0 or image_index % 25 == 0):
            progress_callback(image_index, total_images)

        reader = QImageReader(image_path)
        image_size = reader.size()
        image_width = image_size.width()
        image_height = image_size.height()
        if image_width <= 0 or image_height <= 0:
            add_issue('unreadable image', image_path, reader.errorString())
            image_width = None
            image_height = None
        else:
            resolution_counts[(image_width, image_height)] += 1

        stem = os.path.splitext(os.path.basename(image_path))[0]
        label_path = os.path.join(
            label_directory_for_image(image_path), stem + '.txt')
        if not os.path.isfile(label_path):
            continue

        annotated_images += 1
        try:
            with io.open(
                    label_path, 'r', encoding='utf-8-sig', newline='') as stream:
                lines = stream.readlines()
        except (OSError, UnicodeError) as error:
            add_issue('unreadable label', label_path, str(error))
            continue

        nonempty_lines = [line for line in lines if line.strip()]
        if not nonempty_lines:
            negative_images += 1
            continue

        image_class_ids = set()
        seen_rows = set()
        valid_boxes_in_image = 0
        for line_number, line in enumerate(nonempty_lines, 1):
            normalized_row = ' '.join(line.split())
            if normalized_row in seen_rows:
                add_issue(
                    'duplicate box', label_path,
                    'Duplicate row at non-empty line {}.'.format(line_number))
            seen_rows.add(normalized_row)

            parts = line.split()
            if len(parts) != 5:
                add_issue(
                    'invalid YOLO row', label_path,
                    'Line {} has {} fields; expected 5.'.format(
                        line_number, len(parts)))
                continue
            try:
                class_id = int(parts[0])
                x_center, y_center, width, height = [
                    float(value) for value in parts[1:]]
            except ValueError:
                add_issue(
                    'non-numeric YOLO row', label_path,
                    'Line {} contains invalid numeric data.'.format(line_number))
                continue
            if not all(math.isfinite(value) for value in (
                    x_center, y_center, width, height)):
                add_issue(
                    'non-finite coordinates', label_path,
                    'Line {} contains NaN or infinity.'.format(line_number))
                continue
            if class_id < 0 or class_id >= len(class_names):
                add_issue(
                    'class ID out of range', label_path,
                    'Line {} uses class ID {}; valid range is 0..{}.'.format(
                        line_number, class_id, len(class_names) - 1))
                continue
            if width <= 0 or height <= 0:
                add_issue(
                    'non-positive box', label_path,
                    'Line {} has width {} and height {}.'.format(
                        line_number, width, height))
                continue
            if (x_center - width / 2.0 < 0 or
                    y_center - height / 2.0 < 0 or
                    x_center + width / 2.0 > 1 or
                    y_center + height / 2.0 > 1):
                add_issue(
                    'box outside image', label_path,
                    'Line {} extends outside normalized image bounds.'.format(
                        line_number))

            total_boxes += 1
            valid_boxes_in_image += 1
            class_box_counts[class_id] += 1
            image_class_ids.add(class_id)
            normalized_widths.append(width)
            normalized_heights.append(height)
            normalized_areas.append(width * height)
            if image_width is not None and image_height is not None:
                pixel_width = width * image_width
                pixel_height = height * image_height
                pixel_widths.append(pixel_width)
                pixel_heights.append(pixel_height)
                pixel_areas.append(pixel_width * pixel_height)

        if valid_boxes_in_image:
            object_images += 1
        for class_id in image_class_ids:
            class_image_counts[class_id] += 1

    if progress_callback is not None:
        progress_callback(total_images, total_images)

    orphan_labels = 0
    label_directories = {label_dir} if label_dir else {
        os.path.dirname(path) for path in image_paths}
    for directory in label_directories:
        if is_cancelled is not None and is_cancelled():
            raise AnalysisCancelled()
        if not directory or not os.path.isdir(directory):
            continue
        for filename in os.listdir(directory):
            if (not filename.lower().endswith('.txt') or
                    filename.lower() == 'classes.txt'):
                continue
            stem = os.path.splitext(filename)[0]
            key = (os.path.normcase(os.path.abspath(directory)), stem)
            if key not in image_label_keys:
                orphan_labels += 1
                add_issue(
                    'orphan label', os.path.join(directory, filename),
                    'No image with this basename is loaded.')

    class_rows = []
    for class_id, class_name in enumerate(class_names):
        class_rows.append({
            'id': class_id,
            'name': class_name,
            'boxes': class_box_counts[class_id],
            'images': class_image_counts[class_id],
            'percent': (
                class_box_counts[class_id] * 100.0 / total_boxes
                if total_boxes else 0.0),
        })

    resolution_rows = [
        {'width': width, 'height': height, 'images': count,
         'percent': count * 100.0 / total_images if total_images else 0.0}
        for (width, height), count in resolution_counts.most_common()
    ]
    issue_rows = [
        {'type': issue_type, 'count': count}
        for issue_type, count in issue_counts.most_common()
    ]

    return {
        'summary': {
            'images': total_images,
            'annotated_images': annotated_images,
            'object_images': object_images,
            'negative_images': negative_images,
            'unannotated_images': total_images - annotated_images,
            'boxes': total_boxes,
            'classes': len(class_names),
            'avg_boxes_per_image': (
                total_boxes / float(total_images) if total_images else 0.0),
            'avg_boxes_per_object_image': (
                total_boxes / float(object_images) if object_images else 0.0),
            'orphan_labels': orphan_labels,
            'issues': sum(issue_counts.values()),
        },
        'classes': class_rows,
        'geometry': {
            'normalized width': _describe(normalized_widths),
            'normalized height': _describe(normalized_heights),
            'normalized area': _describe(normalized_areas),
            'pixel width': _describe(pixel_widths),
            'pixel height': _describe(pixel_heights),
            'pixel area': _describe(pixel_areas),
        },
        'resolutions': resolution_rows,
        'issue_summary': issue_rows,
        'issues': issues,
    }
