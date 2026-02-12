from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
AGENT_SERVICE_PATH = ROOT / "services" / "agent-service"

if str(AGENT_SERVICE_PATH) not in sys.path:
    sys.path.insert(0, str(AGENT_SERVICE_PATH))
