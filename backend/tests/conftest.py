import os
import tempfile

# Point the app at a throwaway data dir before any app module imports settings.
os.environ.setdefault("AGENTIC_DATA_DIR", tempfile.mkdtemp(prefix="agentic-test-"))
