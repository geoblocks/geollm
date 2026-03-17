.PHONY: help install test lint format clean repl demo

help:
	@echo "Setup:"
	@echo "  make install          	Install dependencies"
	@echo "  make dev              	Install with dev dependencies"
	@echo "  make download-data    	Download SwissNames3D dataset"
	@echo "  make download-data-ign  	Download IGN BD-CARTO dataset"
	@echo ""
	@echo "Running:"
	@echo "  make repl             	Run interactive REPL"
	@echo "  make demo             	Run the demo app"
	@echo ""
	@echo "Maintenance:"
	@echo "  make clean            	Clean build artifacts"

install:
	uv sync

dev:
	uv sync --extra dev

DATA_PKT = data/swissNAMES3D_PLY.shp

BDCARTO_ARCHIVE_NAME = BDCARTO_5-0_TOUSTHEMES_GPKG_LAMB93_FXX_2025-09-15
BDCARTO_URL = https://data.geopf.fr/telechargement/download/BDCARTO/$(BDCARTO_ARCHIVE_NAME)/$(BDCARTO_ARCHIVE_NAME).7z
BDCARTO_ARCHIVE = data/bdcarto.7z
BDCARTO_DIR = data/bdcarto
DATA_PKT_IGN = $(BDCARTO_DIR)/commune.gpkg

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
	mkdir -p $(BDCARTO_DIR)
	curl -L $(BDCARTO_URL) -o $(BDCARTO_ARCHIVE)
	bash scripts/extract_bdcarto.sh $(BDCARTO_ARCHIVE) $(BDCARTO_DIR)
	rm $(BDCARTO_ARCHIVE)

clean:
	rm -rf .pytest_cache htmlcov .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
