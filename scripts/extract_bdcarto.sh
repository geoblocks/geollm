#!/usr/bin/env bash
# extract_bdcarto.sh  <archive.7z>  <dest_dir>
#
# Extracts the IGN BD-CARTO 7z archive, copies only the useful .gpkg files
# to <dest_dir>, then removes the temporary extraction folder.
#
# Useful layers kept:
#   ADMINISTRATIF  – commune, departement, region, canton, arrondissement*,
#                    collectivite_territoriale, commune_associee_ou_deleguee
#   HYDROGRAPHIE   – cours_d_eau, plan_d_eau, surface_hydrographique,
#                    troncon_hydrographique
#   LIEUX_NOMMES   – zone_d_habitation, lieu_dit_non_habite, detail_orographique
#   ZONES_REGLEMENTEES – parc_ou_reserve
#
# Layers intentionally excluded:
#   BATI, TRANSPORT (routes, rond_point, …), SERVICES_ET_ACTIVITES,
#   ZONE_D_OCCUPATION_DU_SOL
set -euo pipefail

ARCHIVE="${1:?Usage: $0 <archive.7z> <dest_dir>}"
DEST="${2:?Usage: $0 <archive.7z> <dest_dir>}"
TMP_DIR="$(dirname "$ARCHIVE")/_bdcarto_tmp"

USEFUL_LAYERS=(
    # Administrative boundaries
    commune
    commune_associee_ou_deleguee
    departement
    region
    canton
    arrondissement
    arrondissement_municipal
    collectivite_territoriale
    # Hydrography
    cours_d_eau
    plan_d_eau
    surface_hydrographique
    troncon_hydrographique
    # Named places
    zone_d_habitation
    lieu_dit_non_habite
    detail_orographique
    # Protected areas
    parc_ou_reserve
)

echo "Extracting $ARCHIVE …"
uv run --with py7zr python - << PYEOF
import py7zr, sys
with py7zr.SevenZipFile("$ARCHIVE") as z:
    z.extractall("$TMP_DIR")
PYEOF

mkdir -p "$DEST"

echo "Copying useful layers to $DEST …"
for layer in "${USEFUL_LAYERS[@]}"; do
    # Find the gpkg anywhere inside the extraction tree
    gpkg=$(find "$TMP_DIR" -name "${layer}.gpkg" -type f | head -1)
    if [[ -n "$gpkg" ]]; then
        cp "$gpkg" "$DEST/$layer.gpkg"
        echo "  ✓ $layer.gpkg"
    else
        echo "  ✗ $layer.gpkg  (not found, skipping)"
    fi
done

echo "Cleaning up …"
rm -rf "$TMP_DIR"
echo "Done. Files in $DEST:"
ls -lh "$DEST"/*.gpkg 2>/dev/null || echo "  (no .gpkg files found)"
