"""Helpers de tests: aislan data/ con RADAR_DATA_DIR antes de importar módulos."""
import os
import sys
import tempfile

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TMP = None


def datos_temp():
    """Devuelve SIEMPRE el mismo directorio temporal (cacheado): los módulos
    capturan util.DATA al importar, y todos los tests deben compartirlo."""
    global _TMP
    if _TMP is None:
        _TMP = tempfile.mkdtemp(prefix='radar_test_')
        os.environ['RADAR_DATA_DIR'] = _TMP
    if BASE not in sys.path:
        sys.path.insert(0, BASE)
    return _TMP
