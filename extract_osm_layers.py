#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Extrai em passagem unica (single-pass) as 4 camadas tematicas do brazil-latest.osm.pbf
particionadas por UF para data/OSM/extracted/{UF}/osm_{layer}.geojsonl.
"""

import json
import sys
import time
from pathlib import Path

import osmium
from shapely.geometry import Point, shape
from shapely.prepared import prep

from osm_config import (
    OSM_LAYERS,
    RAW_PBF_PATH,
    UF_GEOJSON_PATH,
    ensure_dirs,
    get_uf_geojsonl_path,
)

POI_KEYS = ("amenity", "shop", "leisure", "tourism", "public_transport")
BUILDING_KEEP_TAGS = (
    "building", "building:part", "building:use", "height", "building:levels",
    "roof:levels", "roof:shape", "roof:height", "amenity", "shop", "office", "name"
)
ROAD_KEEP_TAGS = (
    "highway", "railway", "name", "oneway", "lanes", "maxspeed", "surface",
    "bridge", "tunnel", "lit", "sidewalk", "footway", "cycleway",
    "cycleway:left", "cycleway:right", "bicycle", "traffic_calming", "width", "incline"
)
POI_KEEP_TAGS = (
    "amenity", "shop", "leisure", "tourism", "public_transport", "highway",
    "railway", "natural", "name", "operator", "network", "opening_hours",
    "tactile_paving", "kerb", "crossing", "traffic_calming"
)
LANDUSE_KEEP_TAGS = ("landuse", "natural", "leisure", "waterway", "name", "surface", "leaf_type")

LANDUSE_NATURAL_VALUES = {"water", "wood", "scrub", "wetland", "grassland", "heath", "beach", "sand"}
LANDUSE_LEISURE_VALUES = {"park", "garden", "playground", "sports_centre", "pitch", "stadium", "nature_reserve", "recreation_ground"}
ROAD_SKIP_HIGHWAY = {"bus_stop", "crossing", "street_lamp", "traffic_signals", "stop", "give_way"}


def _pick_tags(tags, keys):
    props = {}
    for k in keys:
        v = tags.get(k)
        if v is not None:
            props[k] = v
    return props


def _ring_centroid(coords):
    if not coords:
        return None
    n = len(coords)
    return [round(sum(pt[0] for pt in coords) / n, 6), round(sum(pt[1] for pt in coords) / n, 6)]


def _load_uf_spatial_index(target_ufs):
    raw = json.loads(UF_GEOJSON_PATH.read_text(encoding="utf-8"))
    target_set = set(u.upper() for u in target_ufs) if target_ufs else None
    uf_entries = []
    g_minx, g_miny, g_maxx, g_maxy = 180.0, 90.0, -180.0, -90.0

    for feat in raw["features"]:
        uf = feat["properties"]["SIGLA_UF"].upper()
        if target_set and uf not in target_set:
            continue
        geom = shape(feat["geometry"])
        minx, miny, maxx, maxy = geom.bounds
        g_minx = min(g_minx, minx)
        g_miny = min(g_miny, miny)
        g_maxx = max(g_maxx, maxx)
        g_maxy = max(g_maxy, maxy)
        uf_entries.append((uf, minx, miny, maxx, maxy, prep(geom)))

    if not uf_entries:
        raise ValueError(f"Nenhuma UF encontrada para: {target_ufs}")
    return uf_entries, (g_minx, g_miny, g_maxx, g_maxy)


class BrazilOsmUfExtractor(osmium.SimpleHandler):
    def __init__(self, target_layers, uf_entries, global_bbox):
        super().__init__()
        self.target_layers = set(target_layers)
        self.uf_entries = uf_entries
        self.g_minx, self.g_miny, self.g_maxx, self.g_maxy = global_bbox
        self.geo = osmium.geom.GeoJSONFactory()
        self.files = {}
        self.counts = {uf: {k: 0 for k in self.target_layers} for uf, *_ in uf_entries}
        self._start = time.time()
        self._written = 0

        for uf, *_ in uf_entries:
            self.files[uf] = {}
            for layer in self.target_layers:
                out_path = get_uf_geojsonl_path(uf, layer)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                self.files[uf][layer] = open(out_path, "w", encoding="utf-8", buffering=512 * 1024)

    def close(self):
        for layer_files in self.files.values():
            for f in layer_files.values():
                f.close()

    def _find_uf(self, lon: float, lat: float):
        if not (self.g_minx <= lon <= self.g_maxx and self.g_miny <= lat <= self.g_maxy):
            return None
        candidates = [
            (uf, pgeom)
            for uf, minx, miny, maxx, maxy, pgeom in self.uf_entries
            if minx <= lon <= maxx and miny <= lat <= maxy
        ]
        if not candidates:
            return None
        pt = Point(lon, lat)
        for uf, pgeom in candidates:
            if pgeom.contains(pt):
                return uf
        return None

    def _write_feature(self, uf, layer_name, osm_id, props, geom_dict):
        props["osm_id"] = osm_id
        feat = {
            "type": "Feature",
            "id": osm_id,
            "properties": props,
            "geometry": geom_dict,
        }
        self.files[uf][layer_name].write(json.dumps(feat, ensure_ascii=False, separators=(",", ":")) + "\n")
        self.counts[uf][layer_name] += 1
        self._written += 1
        if self._written % 250_000 == 0:
            elapsed = time.time() - self._start
            print(f"[EXTRACT] {elapsed:6.1f}s | {self._written:,} feicoes gravadas...", flush=True)

    def node(self, n):
        if "pois" not in self.target_layers or not n.tags or not n.location.valid():
            return
        lon = n.location.lon
        lat = n.location.lat
        if not (self.g_minx <= lon <= self.g_maxx and self.g_miny <= lat <= self.g_maxy):
            return

        tags = n.tags
        is_poi = (
            any(k in tags for k in POI_KEYS)
            or tags.get("highway") in ("bus_stop", "crossing", "traffic_signals")
            or tags.get("natural") == "tree"
            or tags.get("railway") in ("station", "halt", "tram_stop", "subway_entrance")
            or "traffic_calming" in tags
            or tags.get("tactile_paving") == "yes"
        )
        if not is_poi:
            return

        uf = self._find_uf(lon, lat)
        if not uf:
            return
        props = _pick_tags(tags, POI_KEEP_TAGS)
        self._write_feature(uf, "pois", n.id, props, {"type": "Point", "coordinates": [round(lon, 7), round(lat, 7)]})

    def way(self, w):
        if not w.tags or not w.nodes:
            return
        tags = w.tags
        hw = tags.get("highway")
        rw = tags.get("railway")
        ww = tags.get("waterway")

        want_road = "roads" in self.target_layers and ((hw and hw not in ROAD_SKIP_HIGHWAY) or rw) and tags.get("area") != "yes"
        want_water = "landuse" in self.target_layers and (
            ww in ("river", "stream", "canal") or tags.get("natural") == "tree_row"
        )
        if not (want_road or want_water):
            return

        # Pre-filtro rapido pelo primeiro no valido antes de montar GeoJSON
        first_loc = next((nd.location for nd in w.nodes if nd.location.valid()), None)
        if first_loc is None:
            return
        if not (self.g_minx <= first_loc.lon <= self.g_maxx and self.g_miny <= first_loc.lat <= self.g_maxy):
            return

        uf = self._find_uf(first_loc.lon, first_loc.lat)
        if not uf:
            return

        try:
            geom = json.loads(self.geo.create_linestring(w))
        except osmium.InvalidLocationError:
            return

        if want_road:
            self._write_feature(uf, "roads", w.id, _pick_tags(tags, ROAD_KEEP_TAGS), geom)
        if want_water:
            self._write_feature(uf, "landuse", w.id, _pick_tags(tags, LANDUSE_KEEP_TAGS), geom)

    def area(self, a):
        if not a.tags:
            return
        tags = a.tags

        want_building = "buildings" in self.target_layers and ("building" in tags or "building:part" in tags)
        want_landuse = "landuse" in self.target_layers and (
            "landuse" in tags
            or tags.get("natural") in LANDUSE_NATURAL_VALUES
            or tags.get("leisure") in LANDUSE_LEISURE_VALUES
        )
        want_poi_center = "pois" in self.target_layers and (
            any(k in tags for k in POI_KEYS)
            or tags.get("railway") in ("station", "halt", "subway_entrance")
        )
        if not (want_building or want_landuse or want_poi_center):
            return

        try:
            ring_iter = next(iter(a.outer_rings()), None)
            if ring_iter is None:
                return
            first_node = next(iter(ring_iter), None)
            if first_node is None or not first_node.location.valid():
                return
            if not (self.g_minx <= first_node.lon <= self.g_maxx and self.g_miny <= first_node.lat <= self.g_maxy):
                return
            uf = self._find_uf(first_node.lon, first_node.lat)
            if not uf:
                return
            geom = json.loads(self.geo.create_multipolygon(a))
        except osmium.InvalidLocationError:
            return

        osm_id = a.orig_id()

        if want_building:
            self._write_feature(uf, "buildings", osm_id, _pick_tags(tags, BUILDING_KEEP_TAGS), geom)
        if want_landuse:
            self._write_feature(uf, "landuse", osm_id, _pick_tags(tags, LANDUSE_KEEP_TAGS), geom)
        if want_poi_center:
            coords = geom.get("coordinates", [])
            ring = coords[0][0] if geom.get("type") == "MultiPolygon" and coords and coords[0] else None
            centroid = _ring_centroid(ring)
            if centroid:
                self._write_feature(uf, "pois", osm_id, _pick_tags(tags, POI_KEEP_TAGS), {"type": "Point", "coordinates": centroid})


def extract_layers(target_layers=None, target_ufs=None, pbf_path: Path = RAW_PBF_PATH):
    ensure_dirs()
    if not pbf_path.exists():
        raise FileNotFoundError(f"Arquivo PBF nao encontrado: {pbf_path}")

    layers = list(target_layers or OSM_LAYERS.keys())
    uf_entries, global_bbox = _load_uf_spatial_index(target_ufs)
    uf_names = [u[0] for u in uf_entries]
    print(f"[EXTRACT] Extraindo camadas={layers} para UFs={uf_names} de {pbf_path.name}...")
    t0 = time.time()

    handler = BrazilOsmUfExtractor(layers, uf_entries, global_bbox)
    try:
        handler.apply_file(str(pbf_path), locations=True, idx="flex_mem")
    finally:
        handler.close()

    elapsed = time.time() - t0
    print(f"[EXTRACT] Concluido em {elapsed:.1f}s ({handler._written:,} feicoes totais).")
    for uf in uf_names:
        summary = ", ".join(f"{k}:{handler.counts[uf][k]:,}" for k in layers)
        print(f"  - {uf}: {summary}")


if __name__ == "__main__":
    ufs = sys.argv[1].split(",") if len(sys.argv) > 1 and sys.argv[1] != "ALL" else None
    lyrs = sys.argv[2].split(",") if len(sys.argv) > 2 else None
    extract_layers(target_layers=lyrs, target_ufs=ufs)
