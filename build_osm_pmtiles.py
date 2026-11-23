#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compila os arquivos GeoJSONSeq (.geojsonl) por UF em PMTiles via Tippecanoe no WSL Ubuntu.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

from osm_config import (
    OSM_LAYERS,
    ensure_dirs,
    get_uf_geojsonl_path,
    get_uf_pmtiles_path,
    load_uf_bboxes,
)


def win_to_wsl_path(win_path: Path) -> str:
    abs_path = str(win_path.resolve())
    drive, rest = os.path.splitdrive(abs_path)
    drive_letter = drive.replace(":", "").lower()
    clean_rest = rest.replace("\\", "/")
    return f"/mnt/{drive_letter}{clean_rest}"


def build_uf_layer_pmtiles(uf: str, layer_key: str):
    cfg = OSM_LAYERS[layer_key]
    src_geojsonl = get_uf_geojsonl_path(uf, layer_key)
    dst_pmtiles = get_uf_pmtiles_path(uf, layer_key)

    if not src_geojsonl.exists() or src_geojsonl.stat().st_size == 0:
        print(f"[TILES] Pulando {uf}/{layer_key} (geojsonl vazio ou ausente).")
        return

    dst_pmtiles.parent.mkdir(parents=True, exist_ok=True)
    wsl_in = win_to_wsl_path(src_geojsonl)
    wsl_out_final = win_to_wsl_path(dst_pmtiles)
    wsl_tmp = f"/tmp/osm_{uf}_{layer_key}.pmtiles"
    flags = " ".join(cfg["tippecanoe_flags"])

    cmd = (
        f"set -e; "
        f"rm -f {wsl_tmp}; "
        f"tippecanoe --read-parallel -P -o {wsl_tmp} "
        f"-Z{cfg['min_zoom']} -z{cfg['max_zoom']} "
        f"-l {cfg['layer_name']} "
        f"--attribution 'OpenStreetMap contributors (Geofabrik)' "
        f"--force {flags} {wsl_in} && "
        f"mv -f {wsl_tmp} {wsl_out_final}"
    )

    t0 = time.time()
    subprocess.run(["wsl", "-d", "Ubuntu", "bash", "-c", cmd], check=True)
    size_mb = dst_pmtiles.stat().st_size / (1024 * 1024)
    print(f"[TILES] {uf}/{dst_pmtiles.name} pronto em {time.time() - t0:.1f}s ({size_mb:.2f} MB)")
    src_geojsonl.unlink(missing_ok=True)


def build_all_pmtiles(target_layers=None, target_ufs=None):
    ensure_dirs()
    layers = list(target_layers or OSM_LAYERS.keys())
    ufs = [u.upper() for u in target_ufs] if target_ufs else sorted(load_uf_bboxes().keys())
    for uf in ufs:
        for k in layers:
            build_uf_layer_pmtiles(uf, k)


if __name__ == "__main__":
    ufs = sys.argv[1].split(",") if len(sys.argv) > 1 and sys.argv[1] != "ALL" else None
    lyrs = sys.argv[2].split(",") if len(sys.argv) > 2 else None
    try:
        build_all_pmtiles(target_layers=lyrs, target_ufs=ufs)
    except Exception as exc:
        print(f"[ERRO] {exc}", file=sys.stderr)
        sys.exit(1)
