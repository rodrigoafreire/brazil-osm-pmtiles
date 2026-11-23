#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Orquestrador semanal de atualizacao dos dados OSM Brasil particionado por UF:
  1. Atualiza brazil-latest.osm.pbf incrementalmente via Geofabrik diffs (pyosmium-up-to-date)
  2. Detecta quais UFs mudaram nos diffs (ou usa --uf)
  3. Extrai as 4 camadas tematicas por UF para GeoJSONSeq
  4. Compila os PMTiles por UF via Tippecanoe (WSL Ubuntu)
  5. Envia os PMTiles + manifest.json para o Cloudflare R2
"""

import argparse
import ctypes
import sys
import time
from datetime import datetime

from build_osm_pmtiles import build_all_pmtiles
from extract_osm_layers import extract_layers
from osm_config import LOGS_DIR, OSM_LAYERS, ensure_dirs, load_uf_bboxes
from update_osm_pbf import update_pbf_incremental
from upload_osm_to_r2 import upload_all_to_r2


class TeeLogger:
    def __init__(self, log_path):
        self._terminal = sys.stdout
        self._log = open(log_path, "a", encoding="utf-8")

    def write(self, message):
        self._terminal.write(message)
        self._log.write(message)

    def flush(self):
        self._terminal.flush()
        self._log.flush()

    def close(self):
        self._log.close()


def prevent_sleep():
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001 | 0x00000040)
    except Exception:
        pass


def allow_sleep():
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(description="Pipeline semanal OSM Brasil por UF -> PMTiles -> Cloudflare R2")
    parser.add_argument("--skip-update", action="store_true", help="Pula o download incremental do PBF")
    parser.add_argument("--skip-extract", action="store_true", help="Pula a extracao GeoJSONSeq")
    parser.add_argument("--skip-tiles", action="store_true", help="Pula a compilacao PMTiles")
    parser.add_argument("--skip-upload", action="store_true", help="Pula o upload para o Cloudflare R2")
    parser.add_argument("--force", action="store_true", help="Continua mesmo se nao houver novos diffs no Geofabrik")
    parser.add_argument("--uf", type=str, default="", help="Lista de UFs separadas por virgula (ex: DF,MG). Padrao: todas ou apenas alteradas.")
    parser.add_argument(
        "--only-layers",
        type=str,
        default="",
        help=f"Lista separada por virgula ({','.join(OSM_LAYERS.keys())})",
    )
    args = parser.parse_args()

    target_layers = [x.strip() for x in args.only_layers.split(",") if x.strip()] or list(OSM_LAYERS.keys())
    for lyr in target_layers:
        if lyr not in OSM_LAYERS:
            parser.error(f"Camada invalida: {lyr}. Opcoes: {list(OSM_LAYERS.keys())}")

    all_ufs = sorted(load_uf_bboxes().keys())
    target_ufs = [x.strip().upper() for x in args.uf.split(",") if x.strip()] or None
    if target_ufs:
        for u in target_ufs:
            if u not in all_ufs:
                parser.error(f"UF invalida: {u}")

    ensure_dirs()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = LOGS_DIR / f"osm_weekly_{stamp}.log"
    tee = TeeLogger(log_file)
    sys.stdout = tee
    sys.stderr = tee

    print("=" * 70)
    print(f"[PIPELINE OSM] Inicio: {datetime.now().isoformat()} | UFs: {target_ufs or 'AUTO'} | Camadas: {target_layers}")
    print("=" * 70)

    t_total = time.time()
    prevent_sleep()
    try:
        if not args.skip_update:
            res = update_pbf_incremental()
            if not res["changed"] and not args.force:
                print("[PIPELINE OSM] PBF ja estava na ultima versao do Geofabrik. Use --force para reprocessar.")
                return
            if target_ufs is None and res["changed_ufs"]:
                target_ufs = res["changed_ufs"]
                print(f"[PIPELINE OSM] Reprocessando apenas UFs alteradas na semana: {target_ufs}")

        if target_ufs is None:
            target_ufs = all_ufs

        if not args.skip_extract:
            extract_layers(target_layers=target_layers, target_ufs=target_ufs)

        if not args.skip_tiles:
            build_all_pmtiles(target_layers=target_layers, target_ufs=target_ufs)

        if not args.skip_upload:
            upload_all_to_r2(target_layers=target_layers, target_ufs=target_ufs)

        print(f"[PIPELINE OSM] Concluido com sucesso em {(time.time() - t_total) / 60:.1f} min.")
    finally:
        allow_sleep()
        sys.stdout = tee._terminal
        sys.stderr = tee._terminal
        tee.close()


if __name__ == "__main__":
    main()
