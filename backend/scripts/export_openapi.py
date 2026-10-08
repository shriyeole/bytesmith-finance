"""Write the API's OpenAPI schema to backend/openapi.json (input for the frontend type generator).

Usage (from backend/):  python scripts/export_openapi.py
Then (from frontend/):  npm run gen:api
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.main import app  # noqa: E402

out = pathlib.Path(__file__).resolve().parents[1] / "openapi.json"
out.write_text(json.dumps(app.openapi(), indent=2) + "\n", encoding="utf-8")
print(f"wrote {out}")
