"""DeltaRecon: the stage contracts of ``contracts/v1`` as a runnable procedure.

The core modules (``documents``, ``export``, ``changes``, ``run``, ``replay``) handle
documents, exports, and run records and know no calculation engine. An engine sits behind
the small protocol of ``degelmann.deltarecon.run``; the adapters live under ``degelmann.deltarecon.engines``.
"""
