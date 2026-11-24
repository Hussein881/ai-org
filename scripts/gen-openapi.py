"""Write the FastAPI OpenAPI schema (input to openapi-typescript)."""

import json
import sys
from pathlib import Path

from app.api.main import app

out = Path(sys.argv[1] if len(sys.argv) > 1 else "artifacts/openapi.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n")
