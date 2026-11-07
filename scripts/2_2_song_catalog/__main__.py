"""
Main - Entry Point for Song Catalog Builder
============================================================================
Command-line entry point for the `2_2_build_song_catalog` package.

This module acts as a thin orchestrator. It executes the ETL pipeline and,
if successful, prints a summary of the catalog statistics. It does not
contain any business logic, ensuring the package remains modular and
testable.

Workflow:
    1. Execute ETL pipeline to update the song catalog.
    2. Display catalog summary statistics.
    3. Return appropriate exit code (0 = success, 1 = error).

Features
--------
- Executable as a module (`python -m 2_2_build_song_catalog`).
- Proper exit codes for CI/CD integration (GitHub Actions).
- Graceful error handling: if the migration fails, it logs the error and
  exits with code 1.

Dependencies
------------
- Internal: `.migrate` (migrate_data), `.catalog_summary`
  (list_catalog_summary), `.config` (logger).
- External: sys (stdlib).

Requirements
------------
- Python 3.7+

Notes
-----
- This module is deliberately kept minimal. Any new logic should be added
  to the respective submodules (e.g., `migrate.py`, `resolver.py`).
- The summary function is wrapped in a try-except block to ensure that a
  reporting failure does not mask a successful migration.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

import sys

from .config import logger
from .migrate import migrate_data
from .catalog_summary import list_catalog_summary


def main() -> int:
    """
    Execute the catalog builder pipeline and print the summary.

    This function serves as the main entry point for the package. It calls
    the ETL pipeline and, if successful, prints the catalog summary.

    Returns
    -------
    int
        Exit code (0 = success, 1 = error). This value is used by the
        operating system or CI/CD runner to determine if the script
        completed successfully.
    """
    try:
        # Execute migration (ETL pipeline)
        exit_code = migrate_data()
        
        if exit_code == 0:
            # Display catalog summary if migration succeeded
            try:
                list_catalog_summary()
            except Exception as e:
                # Ensure a summary failure doesn't mask a successful migration
                logger.warning(f"\n   ⚠️  Could not generate catalog summary: {e}")
        else:
            logger.error("\n❌ Migration failed. See errors above.")
            
        return exit_code

    except KeyboardInterrupt:
        logger.warning("\n\n⚠️  Process interrupted by user (Ctrl+C).")
        return 130  # Standard exit code for SIGINT
        
    except Exception as e:
        logger.error(f"\n❌ Unexpected error during execution: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
