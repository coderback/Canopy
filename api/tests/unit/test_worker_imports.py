"""The worker loads only canopy.jobs.app. It must still see every table, or the
first flush fails with NoReferencedTableError (a bug found against real Xero)."""

import subprocess
import sys

CHECK = """
from canopy.jobs import app  # what `python -m canopy worker` loads
from canopy.core.db import Base
from sqlalchemy.orm import configure_mappers
configure_mappers()
for table in Base.metadata.sorted_tables:  # resolves every foreign key
    pass
print(len(Base.metadata.tables))
"""


def test_worker_process_registers_every_table():
    out = subprocess.run([sys.executable, "-c", CHECK], capture_output=True, text=True, check=True)
    assert int(out.stdout.strip().splitlines()[-1]) == 14
