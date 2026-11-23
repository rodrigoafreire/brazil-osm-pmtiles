#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Envia os arquivos PMTiles por UF do OSM e o manifest.json para o Cloudflare R2 (bucket dados-urbanos).
"""

import json
import sys
import time
from datetime import datetime, timezone

import boto3
import urllib3
from boto3.s3.transfer import TransferConfig

from osm_config import (
    OSM_LAYERS,
    R2_ACCESS_KEY,
    R2_ACCOUNT_ID,
    R2_BUCKET_NAME,
    R2_PREFIX,
    R2_SECRET_KEY,
    RAW_PBF_PATH,
    WORKER_BASE_URL,
    get_uf_pmtiles_path,
    get_uf_r2_key,
    load_uf_bboxes,
)
from update_osm_pbf import read_pbf_replication_info

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class ProgressPrinter:
    def __init__(self, label: str, total_bytes: int):
        self.label = label
        self.total = float(total_bytes)
        self.seen = 0
        self.t0 = time.time()

    def __call__(self, bytes_amount: int):
        self.seen += bytes_amount
        elapsed = time.time() - self.t0
        pct = (self.seen / self.total) * 100 if self.total else 100
        mb_s = (self.seen / (1024 * 1024)) / elapsed if elapsed > 0 else 0
        sys.stdout.write(
            f"\r[R2] {self.label}: {self.seen / (1024*1024):.1f}/{self.total / (1024*1024):.1f} MB ({pct:.1f}%) @ {mb_s:.2f} MB/s   "
        )
        sys.stdout.flush()


def get_r2_client():
    if not R2_ACCESS_KEY or not R2_SECRET_KEY:
        raise RuntimeError(
            "Credenciais R2_ACCESS_KEY / R2_SECRET_KEY nao definidas no .env ou variaveis de ambiente."
        )
    return boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        region_name="auto",
        verify=False,
    )


def upload_all_to_r2(target_layers=None, target_ufs=None):
    layers = list(target_layers or OSM_LAYERS.keys())
    ufs = [u.upper() for u in target_ufs] if target_ufs else sorted(load_uf_bboxes().keys())
    s3 = get_r2_client()
    transfer_cfg = TransferConfig(
        multipart_threshold=50 * 1024 * 1024,
        max_concurrency=8,
        multipart_chunksize=25 * 1024 * 1024,
        use_threads=True,
    )

    uploaded = {}
    for uf in ufs:
        uploaded[uf] = {}
        for k in layers:
            pmtiles_path = get_uf_pmtiles_path(uf, k)
            if not pmtiles_path.exists():
                continue
            r2_key = get_uf_r2_key(uf, k)
            size_bytes = pmtiles_path.stat().st_size
            s3.upload_file(
                str(pmtiles_path),
                R2_BUCKET_NAME,
                r2_key,
                Config=transfer_cfg,
                Callback=ProgressPrinter(f"{uf}/{pmtiles_path.name}", size_bytes),
                ExtraArgs={
                    "ContentType": "application/vnd.pmtiles",
                    "CacheControl": "public, max-age=3600",
                },
            )
            print()
            uploaded[uf][k] = {
                "url": f"{WORKER_BASE_URL}/{r2_key}",
                "size_bytes": size_bytes,
            }

    pbf_info = read_pbf_replication_info(RAW_PBF_PATH) if RAW_PBF_PATH.exists() else {}
    manifest = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "osm_replication": pbf_info,
        "ufs": uploaded,
    }
    s3.put_object(
        Bucket=R2_BUCKET_NAME,
        Key=f"{R2_PREFIX}/manifest.json",
        Body=json.dumps(manifest, indent=2).encode("utf-8"),
        ContentType="application/json",
        CacheControl="public, max-age=300",
    )
    print(f"[R2] Manifest publicado em: {WORKER_BASE_URL}/{R2_PREFIX}/manifest.json")


if __name__ == "__main__":
    ufs = sys.argv[1].split(",") if len(sys.argv) > 1 and sys.argv[1] != "ALL" else None
    lyrs = sys.argv[2].split(",") if len(sys.argv) > 2 else None
    try:
        upload_all_to_r2(target_layers=lyrs, target_ufs=ufs)
    except Exception as exc:
        print(f"[ERRO] {exc}", file=sys.stderr)
        sys.exit(1)
