"""Received-files index: a small JSON file in the downloads dir, so the list survives a restart.
Only ids we generated map to files, and the file name is always a bare name inside out_dir (no traversal)."""
import json
import os
import secrets
import threading

INDEX_NAME = ".mpft-received.json"


class ReceivedIndex:
    def __init__(self, out_dir):
        self.out_dir, self.lock = out_dir, threading.Lock()
        self.path = os.path.join(out_dir, INDEX_NAME)
        try:
            with open(self.path) as f:
                self.items = json.load(f)
        except (OSError, ValueError):
            self.items = []
        # drop entries whose file was deleted outside the app (failed attempts have no file)
        self.items = [x for x in self.items if x["status"] != "ok" or os.path.isfile(self.file_path(x))]

    def file_path(self, entry):
        return os.path.join(self.out_dir, os.path.basename(entry["name"]))

    def _save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.items, f)
        os.replace(tmp, self.path)

    def add(self, name, size, sha256, when, sender, session, ok, error=None):
        entry = {"id": secrets.token_hex(8), "name": name, "size": size, "sha256": sha256, "time": when, "sender": sender,
                 "session": session, "verified": ok, "status": "ok" if ok else "failed", "error": error}
        with self.lock:
            self.items.append(entry)
            self._save()
        return entry

    def get(self, file_id):
        return next((x for x in self.items if x["id"] == file_id), None)

    def downloadable(self, file_id):
        """(entry, absolute path) for a verified file that still exists, else (entry or None, None)."""
        e = self.get(file_id)
        if not e or e["status"] != "ok":
            return e, None
        real = os.path.realpath(self.file_path(e))
        return (e, real) if real.startswith(os.path.realpath(self.out_dir) + os.sep) and os.path.isfile(real) else (e, None)

    def remove(self, file_id):
        """Forget an entry and delete its file. Returns False when the id is unknown."""
        e = self.get(file_id)
        if not e:
            return False
        if e["status"] == "ok":
            try:
                os.remove(self.file_path(e))
            except FileNotFoundError:
                pass
        with self.lock:
            self.items = [x for x in self.items if x["id"] != file_id]
            self._save()
        return True
