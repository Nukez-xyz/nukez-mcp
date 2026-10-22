"""Single source of truth for the nukez-mcp package version.

The version lives in this dependency-free module so that the package root
(``nukez_mcp.__version__``) and the ``clientInfo`` sent in the MCP
``initialize`` handshake derive from the same string. Bump this value
together with the ``version`` field in ``pyproject.toml`` when releasing.
"""

__version__ = "0.1.2"
