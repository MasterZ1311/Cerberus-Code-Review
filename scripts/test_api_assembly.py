"""
Test assembling the Python code blocks in API_SPECIFICATIONS.md and DATABASE_DESIGN.md
and validating FastAPI app instantiation, routes, and OpenAPI schema generation.
"""
import re
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verify_python_blocks import extract_python_blocks
import cerberus.models.database as c_db

def assemble_full_api():
    src = types.ModuleType("src")
    src.__path__ = []
    sys.modules["src"] = src

    models = types.ModuleType("src.models")
    models.__path__ = []
    sys.modules["src.models"] = models

    models_db = types.ModuleType("src.models.database")
    for attr in dir(c_db):
        setattr(models_db, attr, getattr(c_db, attr))
    for extra in ["CustomRuleRecord", "TeamExpertiseRecord", "SecurityFindingRecord"]:
        if not hasattr(models_db, extra):
            setattr(models_db, extra, type(extra, (), {}))
    sys.modules["src.models.database"] = models_db

    routers_pkg = types.ModuleType("src.routers")
    routers_pkg.__path__ = []
    sys.modules["src.routers"] = routers_pkg

    def load_v(name, code):
        m = types.ModuleType(name)
        m.__file__ = f"<virtual:{name}>"
        sys.modules[name] = m
        exec(code, m.__dict__)
        return m

    file_map = {}
    for doc in ["DATABASE_DESIGN.md", "API_SPECIFICATIONS.md"]:
        for b in extract_python_blocks(ROOT / doc):
            m = re.search(r"#\s*File:\s*(.+)", b["content"])
            if m:
                file_map[m.group(1).strip()] = b["content"]

    load_v("src.config", file_map["src/config.py"])
    load_v("src.core.logging", file_map["src/core/logging.py"])
    load_v("src.core.caching", file_map["src/core/caching.py"])
    load_v("src.db.session", file_map["src/db/session.py"])
    load_v("src.dependencies.auth", file_map["src/dependencies/auth.py"])
    load_v("src.middleware.rate_limit", file_map["src/middleware/rate_limit.py"])
    load_v("src.middleware.error_handler", file_map["src/middleware/error_handler.py"])
    load_v("src.schemas.reviews", file_map["src/schemas/reviews.py"])
    load_v("src.schemas.analytics", file_map["src/schemas/analytics.py"])
    load_v("src.schemas.rules", file_map["src/schemas/rules.py"])
    load_v("src.schemas.teams", file_map["src/schemas/teams.py"])
    load_v("src.schemas.system", file_map["src/schemas/system.py"])

    for r in ["health", "reviews", "analytics", "rules", "teams", "websocket", "agents", "config", "webhooks"]:
        fname = f"src/routers/{r}.py"
        modname = f"src.routers.{r}"
        load_v(modname, file_map[fname])
        setattr(routers_pkg, r, sys.modules[modname])

    main_mod = load_v("src.main", file_map["src/main.py"])
    app = main_mod.app
    print(f"App title: {app.title}, version: {app.version}")
    
    schema = app.openapi()
    print(f"Generated OpenAPI endpoints count: {len(schema['paths'])}")
    for path, methods in schema["paths"].items():
        print(f"  {list(methods.keys())} {path}")
        
    return app, schema

if __name__ == "__main__":
    assemble_full_api()
