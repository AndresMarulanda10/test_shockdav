"""Entrypoint principal.
Este archivo simplemente reexporta la instancia `app` que se define en
`src.fastapi_app.main`. Se mantiene para compatibilidad con los scripts
antiguos que importan `app.main`.
"""

from src.fastapi_app.main import app
