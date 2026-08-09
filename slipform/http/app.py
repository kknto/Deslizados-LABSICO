"""Compatible HTTP app entrypoint."""

from slipform.http.legacy_server import SlipformHandler, run

__all__ = ["SlipformHandler", "run"]
