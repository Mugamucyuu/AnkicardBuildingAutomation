"""Windows desktop entry point, also used by the frozen executable."""
from vocab_app.desktop import main

if __name__ == "__main__":
    raise SystemExit(main())
