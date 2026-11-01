# Radar Matemáticas — tareas comunes
# make check   → compilación + privacidad + suite de tests
# make test    → solo tests
# make server  → servidor local (http://localhost:8643)
# make reporte → regenera war_room.html

PY ?= python3

.PHONY: check test compile privacidad server reporte clean

check: compile privacidad test

compile:
	@$(PY) -m py_compile *.py scripts/*.py tests/*.py static_data/*.py 2>/dev/null || $(PY) -m py_compile *.py scripts/*.py tests/*.py
	@echo "✓ compila"

privacidad:
	@$(PY) scripts/check_privacidad.py

test:
	@$(PY) -m unittest discover -s tests -v

server:
	$(PY) app.py

reporte:
	$(PY) generar_reporte.py

clean:
	rm -rf __pycache__ tests/__pycache__ .mypy_cache
	find . -name '*.pyc' -delete
