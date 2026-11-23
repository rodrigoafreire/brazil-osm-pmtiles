#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Empacota os PMTiles de todas as regioes para release:
1. Reune os arquivos gerados pelas maquinas da matriz
2. Cria tar.gz por regiao para release compacta
3. Gera o manifest.json
"""

import json
import shutil
import tarfile
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ARTIFACTS_DIR = BASE_DIR / "all_pmtiles"
DIST_DIR = BASE_DIR / "release_dist"
DIST_DIR.mkdir(parents=True, exist_ok=True)

manifest = {
    "version": 1,
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "ufs": {}
}

# Organiza diretorios
for art_dir in ARTIFACTS_DIR.glob("pmtiles-*"):
    region_name = art_dir.name.replace("pmtiles-", "")
    tar_path = DIST_DIR / f"pmtiles_{region_name}.tar.gz"
    
    with tarfile.open(tar_path, "w:gz") as tar:
        for pmtiles_file in art_dir.rglob("*.pmtiles"):
            uf = pmtiles_file.parent.name
            manifest["ufs"].setdefault(uf, {})
            manifest["ufs"][uf][pmtiles_file.stem] = {
                "size_mb": round(pmtiles_file.stat().st_size / (1024 * 1024), 2),
                "filename": pmtiles_file.name
            }
            # Adiciona ao tar mantendo estrutura {UF}/{arquivo}.pmtiles
            arcname = f"{uf}/{pmtiles_file.name}"
            tar.add(pmtiles_file, arcname=arcname)
            print(f"[PACKAGE] {arcname} ({pmtiles_file.stat().st_size / (1024*1024):.1f} MB)")

manifest_path = DIST_DIR / "manifest.json"
manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"[PACKAGE] manifest.json gerado com {len(manifest['ufs'])} UFs.")
