.PHONY: help install test lint format clean repl demo

help:
	@echo "GeoLLM - UV Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install    Install dependencies"
	@echo "  make dev        Install with dev dependencies"
	@echo "  make download-data Download SwissNames3D dataset"
	@echo ""
	@echo "Running:"
	@echo "  make repl       Run interactive REPL"
	@echo "  make demo       Run the demo app"

	@echo ""
	@echo "Maintenance:"
	@echo "  make clean      Clean build artifacts"

install:
	uv sync

dev:
	uv sync --extra dev

DATA_PKT = data/swissNAMES3D_PLY.shp

IGN_ARCHIVE = BDTOPO_2-2_ADMINISTRATIF_SHP_WGS84G_FRA_2018-01-01
DATA_PKT_IGN = data/IGNF_BD-TOPO_COMMUNE.shp

repl:
	uv run python repl.py

demo:
	uv run uvicorn demo.main:app --port 8000 --reload

download-data: $(DATA_PKT)

download-data-ign: $(DATA_PKT_IGN)

$(DATA_PKT):
	mkdir -p data
	curl -L https://data.geo.admin.ch/ch.swisstopo.swissnames3d/swissnames3d_2025/swissnames3d_2025_2056.shp.zip -o data/swissnames3d.zip
	unzip -o data/swissnames3d.zip -d data/
	rm data/swissnames3d.zip

$(DATA_PKT_IGN):
	mkdir -p data
	curl -L https://data.geopf.fr/telechargement/download/BDTOPO/$(IGN_ARCHIVE)/$(IGN_ARCHIVE).7z -o data/$(IGN_ARCHIVE).7z
	uv run --with py7zr python -c "import py7zr; py7zr.SevenZipFile('data/$(IGN_ARCHIVE).7z').extractall('data/')"
	rm data/$(IGN_ARCHIVE).7z
	find data/$(IGN_ARCHIVE) -path "*/ADMINISTRATIF/*" -type f | while read f; do mv "$$f" "$$(dirname $$f)/IGNF_BD-TOPO_$$(basename $$f)"; done
	find data/$(IGN_ARCHIVE) -path "*/ADMINISTRATIF/IGNF_BD-TOPO_*" -type f -exec mv {} data/ \;
	rm -rf data/$(IGN_ARCHIVE)

clean:
	rm -rf .pytest_cache htmlcov .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
