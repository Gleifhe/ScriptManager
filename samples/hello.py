"""Sample script: hello.py — simple demo for ScriptManager."""
import sys
from datetime import datetime

print(f"[{datetime.now().isoformat()}] Hello from ScriptManager!")
print(f"Python: {sys.version}")
print("Arguments:", sys.argv[1:])
