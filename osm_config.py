#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuracao central do pipeline semanal de dados OSM particionado por UF
no repositorio publico de geracao automatica via GitHub Actions.
"""

import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
OSM_DATA_DIR = BASE_DIR / "data" / "OSM"

RAW_DIR = OSM_DATA_DIR / "raw"
EXTRACTED_DIR = OSM_DATA_DIR / "extracted"
PMTILES_DIR = OSM_DATA_DIR / "pmtiles"
LOGS_DIR = OSM_DATA_DIR / "logs"

RAW_PBF_PATH = RAW_DIR / "brazil-latest.osm.pbf"
UF_GEOJSON_PATH = BASE_DIR / "br_uf_2025.geojson"
UF_BBOXES_PATH = BASE_DIR / "uf_bboxes.json"
GEOFABRIK_PBF_URL = "https://download.geofabrik.de/south-america/brazil-latest.osm.pbf"

REGIONS = {
    "sudeste": ["SP", "MG", "RJ", "ES"],
    "sul": ["PR", "SC", "RS"],
    "nordeste": ["BA", "PE", "CE", "MA", "PB", "RN", "PI", "AL", "SE"],
    "centro_oeste": ["GO", "MT", "MS", "DF"],
    "norte": ["PA", "AM", "RO", "TO", "AC", "AP", "RR"]
}

OSM_LAYERS = {
    "buildings": {
        "layer_name": "buildings",
        "min_zoom": 13,
        "max_zoom": 15,
        "tippecanoe_flags": [
            "--drop-densest-as-needed",
            "--extend-zooms-if-still-dropping",
            "--coalesce-densest-as-needed",
            "--no-tiny-polygon-reduction",
        ],
    },
    "roads": {
        "layer_name": "roads",
        "min_zoom": 8,
        "max_zoom": 15,
        "tippecanoe_flags": [
            "--drop-densest-as-needed",
            "--extend-zooms-if-still-dropping",
            "--simplification=2",
        ],
    },
    "pois": {
        "layer_name": "pois",
        "min_zoom": 10,
        "max_zoom": 15,
        "tippecanoe_flags": [
            "--drop-densest-as-needed",
            "--extend-zooms-if-still-dropping",
        ],
    },
    "landuse": {
        "layer_name": "landuse",
        "min_zoom": 10,
        "max_zoom": 15,
        "tippecanoe_flags": [
            "--drop-densest-as-needed",
            "--extend-zooms-if-still-dropping",
            "--coalesce-densest-as-needed",
        ],
    },
}


def load_uf_bboxes() -> dict:
    return json.loads(UF_BBOXES_PATH.read_text(encoding="utf-8"))


def get_uf_geojsonl_path(uf: str, layer: str) -> Path:
    return EXTRACTED_DIR / uf / f"osm_{layer}.geojsonl"


def get_uf_pmtiles_path(uf: str, layer: str) -> Path:
    return PMTILES_DIR / uf / f"osm_{layer}.pmtiles"


def ensure_dirs():
    for d in (RAW_DIR, EXTRACTED_DIR, PMTILES_DIR, LOGS_DIR):
        d.mkdir(parents=True, exist_ok=True)
