"""Read permission state. Never requests or grants macOS permissions silently."""
import json
import os
from pathlib import Path
import subprocess
import time


class Access:
    def __init__(self):
        self.photo_status='unavailable'
        self.checked_at=0

    def read(self, folder, force=False):
        try:
            with os.scandir(Path(folder).expanduser()) as entries:next(entries,None)
            recordings='granted'
        except PermissionError:recordings='denied'
        except (FileNotFoundError,NotADirectoryError):recordings='missing'
        except OSError:recordings='unavailable'
        helper=os.environ.get('VOICE_NOTEBOOK_PHOTOS_HELPER')
        if helper and Path(helper).is_file() and (force or time.monotonic()-self.checked_at>10):
            try:
                result=subprocess.run([helper,'--permissions'],capture_output=True,text=True,timeout=5)
                state=json.loads(result.stdout) if result.returncode==0 else {}
                self.photo_status=state.get('photos','unavailable')
            except (ValueError,OSError,subprocess.TimeoutExpired):self.photo_status='unavailable'
            self.checked_at=time.monotonic()
        elif not helper:self.photo_status='unavailable'
        return {'recordings':recordings,'photos':self.photo_status,
                'photos_enabled':self.photo_status in ('authorized','limited'),'native':bool(helper)}
