"""Legacy compatibility facade.

The database implementation has been split into focused repository modules.
This file remains only for old imports that may still reference
`slipform.repositories.legacy_db`.
"""

from slipform.db import *  # noqa: F401,F403
from slipform.repositories.connection import ClosingConnection, connect  # noqa: F401
from slipform.repositories.schema import SCHEMA_DESCRIPTION, SCHEMA_VERSION, init_db  # noqa: F401

