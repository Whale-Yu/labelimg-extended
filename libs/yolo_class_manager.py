import datetime
import io
import json
import os
import re
import shutil


class YoloClassManagementError(Exception):
    pass


class YoloClassManager(object):
    """Safely inspect and rewrite one flat YOLO label directory."""

    def __init__(self, label_dir):
        self.label_dir = os.path.abspath(label_dir)
        self.classes_path = os.path.join(self.label_dir, 'classes.txt')
        self.classes = []
        self.counts = []
        self.label_files = []
        self.issues = []
        self._file_class_ids = {}
        self.refresh()

    def refresh(self):
        if not os.path.isdir(self.label_dir):
            raise YoloClassManagementError(
                'Label directory does not exist: {}'.format(self.label_dir))
        if not os.path.isfile(self.classes_path):
            raise YoloClassManagementError(
                'classes.txt was not found in: {}'.format(self.label_dir))

        with io.open(self.classes_path, 'r', encoding='utf-8-sig') as stream:
            self.classes = [line.rstrip('\r\n') for line in stream]
        if not self.classes:
            raise YoloClassManagementError('classes.txt contains no classes.')

        self.issues = []
        for class_id, class_name in enumerate(self.classes):
            if not class_name.strip():
                self.issues.append(
                    'classes.txt line {} has an empty class name.'.format(
                        class_id + 1))

        self.counts = [0] * len(self.classes)
        self.label_files = sorted(
            os.path.join(self.label_dir, name)
            for name in os.listdir(self.label_dir)
            if name.lower().endswith('.txt')
            and name.lower() != 'classes.txt')
        self._file_class_ids = {}

        for label_path in self.label_files:
            class_ids = []
            with io.open(label_path, 'r', encoding='utf-8-sig', newline='') as stream:
                for line_number, line in enumerate(stream, 1):
                    if not line.strip():
                        continue
                    parts = line.split()
                    if len(parts) < 5:
                        self.issues.append(
                            '{}:{} is not a valid YOLO row.'.format(
                                os.path.basename(label_path), line_number))
                        continue
                    try:
                        class_id = int(parts[0])
                    except ValueError:
                        self.issues.append(
                            '{}:{} has a non-integer class ID.'.format(
                                os.path.basename(label_path), line_number))
                        continue
                    if class_id < 0 or class_id >= len(self.classes):
                        self.issues.append(
                            '{}:{} uses class ID {}, outside 0..{}.'.format(
                                os.path.basename(label_path), line_number,
                                class_id, len(self.classes) - 1))
                        continue
                    self.counts[class_id] += 1
                    class_ids.append(class_id)
            self._file_class_ids[label_path] = class_ids
        return self

    def _require_safe_dataset(self):
        if self.issues:
            raise YoloClassManagementError(
                'Class changes are blocked until these problems are fixed:\n{}'.format(
                    '\n'.join(self.issues[:8])))

    def _require_class_id(self, class_id):
        if class_id < 0 or class_id >= len(self.classes):
            raise YoloClassManagementError(
                'Class ID {} does not exist.'.format(class_id))

    def transfer_plan(self, source_id, target_id):
        self.refresh()
        self._require_safe_dataset()
        self._require_class_id(source_id)
        self._require_class_id(target_id)
        if source_id == target_id:
            raise YoloClassManagementError(
                'Source and target classes must be different.')
        if self.counts[source_id] == 0:
            raise YoloClassManagementError(
                'The source class is already empty; there is nothing to transfer.')
        affected_files = [
            path for path, ids in self._file_class_ids.items()
            if source_id in ids]
        return {
            'source_id': source_id,
            'target_id': target_id,
            'box_count': self.counts[source_id],
            'file_count': len(affected_files),
            'affected_files': affected_files,
        }

    def delete_plan(self, class_id):
        self.refresh()
        self._require_safe_dataset()
        self._require_class_id(class_id)
        if len(self.classes) <= 1:
            raise YoloClassManagementError(
                'The last remaining class cannot be deleted.')
        if self.counts[class_id] != 0:
            raise YoloClassManagementError(
                'Class [{}] {} still has {} box(es) and cannot be deleted.'.format(
                    class_id, self.classes[class_id], self.counts[class_id]))
        affected_files = [
            path for path, ids in self._file_class_ids.items()
            if any(existing_id > class_id for existing_id in ids)]
        return {
            'class_id': class_id,
            'file_count': len(affected_files),
            'affected_files': affected_files,
        }

    @staticmethod
    def _replace_class_ids(text, mapping):
        output = []
        for line in text.splitlines(True):
            if not line.strip():
                output.append(line)
                continue
            match = re.match(r'^(\s*)(\S+)(.*)$', line, re.DOTALL)
            if match is None:
                output.append(line)
                continue
            class_id = int(match.group(2))
            new_class_id = mapping(class_id)
            output.append('{}{}{}'.format(
                match.group(1), new_class_id, match.group(3)))
        return ''.join(output)

    @staticmethod
    def _read_text(path):
        with io.open(path, 'r', encoding='utf-8-sig', newline='') as stream:
            return stream.read()

    def _create_backup(self, paths, operation, details):
        timestamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        backup_dir = os.path.join(
            self.label_dir + '.labelimg_class_backups',
            '{}-{}'.format(timestamp, operation))
        os.makedirs(backup_dir)
        for path in paths:
            shutil.copy2(path, os.path.join(backup_dir, os.path.basename(path)))
        manifest = {
            'operation': operation,
            'label_directory': self.label_dir,
            'details': details,
            'files': [os.path.basename(path) for path in paths],
        }
        with io.open(
                os.path.join(backup_dir, 'manifest.json'), 'w',
                encoding='utf-8') as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2)
        return backup_dir

    def _commit_updates(self, updates, operation, details):
        backup_paths = sorted(set([self.classes_path] + list(updates.keys())))
        backup_dir = self._create_backup(
            backup_paths, operation, details)
        temp_paths = {}
        try:
            for path, text in updates.items():
                temp_path = path + '.labelimg.tmp'
                with io.open(
                        temp_path, 'w', encoding='utf-8', newline='') as stream:
                    stream.write(text)
                temp_paths[path] = temp_path
            for path, temp_path in temp_paths.items():
                os.replace(temp_path, path)
            self.refresh()
        except Exception:
            for path in backup_paths:
                backup_path = os.path.join(
                    backup_dir, os.path.basename(path))
                if os.path.isfile(backup_path):
                    shutil.copy2(backup_path, path)
            for temp_path in temp_paths.values():
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            try:
                self.refresh()
            except Exception:
                pass
            raise
        return backup_dir

    def transfer(self, source_id, target_id):
        plan = self.transfer_plan(source_id, target_id)
        updates = {}
        for path in plan['affected_files']:
            old_text = self._read_text(path)
            new_text = self._replace_class_ids(
                old_text,
                lambda class_id: target_id if class_id == source_id else class_id)
            if new_text != old_text:
                updates[path] = new_text
        backup_dir = self._commit_updates(
            updates, 'transfer', {
                'source_id': source_id,
                'source_name': self.classes[source_id],
                'target_id': target_id,
                'target_name': self.classes[target_id],
                'box_count': plan['box_count'],
            })
        plan['backup_dir'] = backup_dir
        return plan

    def delete_empty_class(self, class_id):
        plan = self.delete_plan(class_id)
        class_name = self.classes[class_id]
        new_classes = self.classes[:class_id] + self.classes[class_id + 1:]
        updates = {
            self.classes_path: ''.join(
                '{}\n'.format(name) for name in new_classes)
        }
        for path in plan['affected_files']:
            old_text = self._read_text(path)
            new_text = self._replace_class_ids(
                old_text,
                lambda existing_id: (
                    existing_id - 1 if existing_id > class_id else existing_id))
            if new_text != old_text:
                updates[path] = new_text
        backup_dir = self._commit_updates(
            updates, 'delete', {
                'class_id': class_id,
                'class_name': class_name,
            })
        plan['backup_dir'] = backup_dir
        return plan
