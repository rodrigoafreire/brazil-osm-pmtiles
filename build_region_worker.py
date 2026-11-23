#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Worker que processa uma regiao especifica (conjunto de UFs) no GitHub Actions:
1. Baixa o extract regional ou PBF nacional (se necessario)
2. Extrai feicoes das UFs da regiao
3. Compila PMTiles via tippecanoe
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

from osm_config import (
    EXTRACTED_DIR,
    GEOFABRIK_PBF_URL,
    OSM_LAYERS,
    PMTILES_DIR,
    RAW_DIR,
    RAW_PBF_PATH,
    REGIONS,
    ensure_dirs,
    get_uf_geojsonl_path,
    get_uf_pmtiles_path,
)
from extract_osm_layers import BrazilOsmUfExtractor, _load_uf_spatial_index
from build_osm_pmtiles import build_pmtiles_for_uf


def download_pbf_if_needed():
    ensure_dirs()
    if RAW_PBF_PATH.exists() and RAW_PBF_PATH.stat().st_size > 100 * 1024 * 1024:
        return
    print(f"[WORKER] Baixando {GEOFABRIK_PBF_URL}...")
    import requests
    with requests.get(GEOFABRIK_PBF_URL, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(RAW_PBF_PATH, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024 * 8):
                if chunk:
                    f.write(chunk)
    print(f"[WORKER] Download concluido: {RAW_PBF_PATH.stat().st_size / (1024*1024):.1f} MB")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", required=True, choices=list(REGIONS.keys()))
    args = parser.parse_args()

    target_ufs = REGIONS[args.region]
    print(f"============================================================")
    print(f"[WORKER REGIONAL] Regiao: {args.region.upper()} | UFs: {target_ufs}")
    print(f"============================================================")

    download_pbf_if_needed()

    ensure_dirs()
    uf_entries, global_bbox = _load_uf_spatial_index(target_ufs)
    extractor = BrazilOsmUfExtractor(list(OSM_LAYERS.keys()), uf_entries, global_bbox)

    print(f"[EXTRACT] Extraindo feicoes para {target_ufs}...")
    t0 = time.time()
    extractor.apply_file(str(RAW_PBF_PATH), locations=True, idx="flex_mem")
    extractor.close()
    print(f"[EXTRACT] Concluido em {time.time() - t0:.1f}s")

    # Compilar PMTiles para cada UF da regiao
    for uf in target_ufs:
        print(f"\n[TILES] Compilando PMTiles para {uf}...")
        for layer_key in OSM_LAYERS.keys():
            in_file = get_uf_geojsonl_path(uf, layer_key)
            out_file = get_uf_pmtiles_path(uf, layer_key)
            out_file.parent.mkdir(parents=True, exist_ok=True)
            if not in_file.exists() or in_file.stat().st_size == 0:
                print(f"[TILES] {uf}/{layer_key} vazio ou inexistente. Pulando.")
                continue
            build_pmtiles_for_uf(uf, layer_key, force=True)

    print(f"\n[WORKER] Regiao {args.region.upper()} finalizada com sucesso!")


if __name__ == "__main__":
    main()
