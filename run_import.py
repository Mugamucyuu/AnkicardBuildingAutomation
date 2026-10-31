"""Source-checkout CLI; installed users run `ankicard-import`."""
from vocab_app.cli import main
from vocab_app.examples import OfflineClient

if __name__ == "__main__":
    raise SystemExit(main())
