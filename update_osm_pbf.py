#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Atualiza incrementalmente brazil-latest.osm.pbf usando pyosmium-up-to-date
e detecta quais UFs tiveram alteracoes nos diffs (.osc.gz) do Geofabrik.
"""

import gzip
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import osmium
import requests

from osm_config import GEOFABRIK_PBF_URL, RAW_PBF_PATH, ensure_dirs, load_uf_bboxes


def read_pbf_replication_info(pbf_path: Path) -> dict:
    reader = osmium.io.Reader(str(pbf_path))
    try:
        header = reader.header()
        return {
            "url": header.get("osmosis_replication_base_url", ""),
            "seq": str(header.get("osmosis_replication_sequence_number", "")),
            "timestamp": header.get("osmosis_replication_timestamp", ""),
        }
    finally:
        reader.close()


def download_initial_pbf(dest: Path):
    print(f"[OSM] Arquivo base nao encontrado. Baixando {GEOFABRIK_PBF_URL}...")
    with requests.get(GEOFABRIK_PBF_URL, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        tmp_dest = dest.with_suffix(".osm.pbf.part")
        with open(tmp_dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8 * 1024 * 1024):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = downloaded * 100 / total
                        print(f"\r[OSM] Download: {downloaded / (1024**2):.1f} / {total / (1024**2):.1f} MB ({pct:.1f}%)", end="", flush=True)
        print()
        tmp_dest.replace(dest)
    print(f"[OSM] Download inicial concluido: {dest}")


def _seq_to_path(seq_num: int) -> str:
    s = f"{seq_num:09d}"
    return f"{s[0:3]}/{s[3:6]}/{s[6:9]}.osc.gz"


def detect_changed_ufs(base_url: str, old_seq: int, new_seq: int) -> list:
    """Inspeciona os diffs .osc.gz entre old_seq+1 e new_seq e retorna as UFs afetadas."""
    if not base_url or new_seq <= old_seq:
        return []
    bboxes = load_uf_bboxes()
    changed = set()
    base = base_url.rstrip("/")

    for seq in range(old_seq + 1, new_seq + 1):
        url = f"{base}/{_seq_to_path(seq)}"
        try:
            resp = requests.get(url, timeout=60)
            if resp.status_code != 200:
                continue
            xml_bytes = gzip.decompress(resp.content)
            root = ET.fromstring(xml_bytes)
            for node in root.iter("node"):
                lat_s = node.attrib.get("lat")
                lon_s = node.attrib.get("lon")
                if not lat_s or not lon_s:
                    continue
                lat = float(lat_s)
                lon = float(lon_s)
                for uf, (minx, miny, maxx, maxy) in bboxes.items():
                    if minx <= lon <= maxx and miny <= lat <= maxy:
                        changed.add(uf)
        except Exception as exc:
            print(f"[OSM] Aviso ao inspecionar diff seq={seq}: {exc}")

    return sorted(changed)


def update_pbf_incremental(pbf_path: Path = RAW_PBF_PATH, chunk_mb: int = 512) -> dict:
    ensure_dirs()
    if not pbf_path.exists():
        download_initial_pbf(pbf_path)

    exe = shutil.which("pyosmium-up-to-date")
    if not exe:
        raise RuntimeError("pyosmium-up-to-date nao encontrado no PATH. Instale com: pip install osmium")

    # Garante que requests e bibliotecas SSL encontrem o bundle de certificados do certifi no Windows
    env = os.environ.copy()
    try:
        import certifi
        ca_bundle = certifi.where()
        env.setdefault("REQUESTS_CA_BUNDLE", ca_bundle)
        env.setdefault("SSL_CERT_FILE", ca_bundle)
        env.setdefault("CURL_CA_BUNDLE", ca_bundle)
    except Exception:
        pass

    before = read_pbf_replication_info(pbf_path)
    print(f"[OSM] Estado atual: seq={before['seq']} | timestamp={before['timestamp']} | server={before['url']}")

    round_num = 0
    while True:
        round_num += 1
        print(f"[OSM] Aplicando diffs incrementais (rodada {round_num}, limite {chunk_mb} MB)...")
        proc = subprocess.run([exe, "-v", "-s", str(chunk_mb), str(pbf_path)], env=env, check=False)
        if proc.returncode == 0:
            print("[OSM] Arquivo PBF totalmente atualizado com o servidor Geofabrik.")
            break
        elif proc.returncode == 1:
            print("[OSM] Lote de diffs aplicado; ainda ha mais atualizacoes pendentes. Continuando...")
            continue
        else:
            raise RuntimeError(f"pyosmium-up-to-date falhou com codigo {proc.returncode}")

    after = read_pbf_replication_info(pbf_path)
    print(f"[OSM] Novo estado:  seq={after['seq']} | timestamp={after['timestamp']}")
    changed = before["seq"] != after["seq"]
    changed_ufs = []
    if changed and before["seq"].isdigit() and after["seq"].isdigit():
        changed_ufs = detect_changed_ufs(after["url"] or before["url"], int(before["seq"]), int(after["seq"]))
        print(f"[OSM] UFs com alteracoes detectadas: {changed_ufs}")
    return {"changed": changed, "before": before, "after": after, "changed_ufs": changed_ufs}


if __name__ == "__main__":
    try:
        res = update_pbf_incremental()
        print(f"[OSM] Resultado: changed={res['changed']} | ufs={res['changed_ufs']}")
    except Exception as exc:
        print(f"[ERRO] {exc}", file=sys.stderr)
        sys.exit(1)
