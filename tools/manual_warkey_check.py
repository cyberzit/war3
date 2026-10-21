"""Manual UI test harness; isolated mappings, no account or user settings changes."""
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mongolranger as app

with tempfile.TemporaryDirectory(prefix='mongolranger-warkey-') as folder:
    app.SETTINGS_FILE=Path(folder)/'settings.json'
    app.SETTINGS_FILE.write_text(json.dumps({'warkey_inv_slots':{'0':85},'warkey_skill_slots':{'4':89}}))
    window=app.MongolRangerApp('WarKey test')
    window.notebook.select(window.tab_warkey)
    window.mainloop()
