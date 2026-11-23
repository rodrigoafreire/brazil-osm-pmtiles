# brazil-osm-pmtiles 🗺️🇧🇷

Este repositório é responsável pela **extração semanal e compilação automatizada dos dados do OpenStreetMap Brasil** em formato **PMTiles**, utilizando **GitHub Actions** particionado em matriz paralela.

---

## Arquitetura do Pipeline

```
                              OpenStreetMap (Geofabrik)
                                         │
                 ┌───────────────────────┴───────────────────────┐
                 ▼                                               ▼
         [GitHub Actions: Runner 1]                      [GitHub Actions: Runner 2] ...
             Região Sudeste                                  Região Sul ...
      (SP, MG, RJ, ES: ~40 min)                      (PR, SC, RS: ~25 min)
                 │                                               │
                 └───────────────────────┬───────────────────────┘
                                         ▼
                            [GitHub Release Semanal]
                                 osm-br-XXXXX
                       (pmtiles_sudeste.tar.gz, etc.)
                                         │
                                         ▼ (Webhook / Sincronização)
                          [Seu Repositório Privado ou R2]
                                (Upload seguro R2)
```

1. **Repositório Público**: Roda toda a computação pesada de graça (minutos ilimitados no GitHub Actions). **Zero credenciais ou senhas** ficam expostas aqui.
2. **Matriz de Regiões**: 5 máquinas virtuais executam simultaneamente. O tempo total cai de ~5 horas para **menos de 45 minutos**.
3. **Publicação via Release**: Cada execução gera uma Release com os pacotes `.tar.gz` organizados por região e o `manifest.json`.

---

## Estrutura de Arquivos

- `.github/workflows/build_pmtiles.yml`: Definição da matriz paralela de CI/CD.
- `build_region_worker.py`: Script executado em cada máquina virtual para extrair e compilar a região específica.
- `package_release.py`: Agrupador final que cria os pacotes `.tar.gz` e gera o `manifest.json`.
- `osm_config.py`: Parâmetros de zoom, camadas (`buildings`, `roads`, `pois`, `landuse`) e UFs.
- `br_uf_2025.geojson` e `uf_bboxes.json`: Malha territorial de recorte.

---

## Como Ativar no GitHub

1. Crie um repositório **Público** no seu GitHub: `brazil-osm-pmtiles`.
2. Faça o push dos arquivos desta pasta:
   ```bash
   git init
   git remote add origin https://github.com/rodrigoafreire/brazil-osm-pmtiles.git
   git add -A
   git commit -m "feat: esteira semanal de pmtiles osm brasil"
   git branch -M main
   git push -u origin main
   ```
3. O workflow roda automaticamente todo domingo às **00:00 (Brasília)** ou manualmente pela aba **Actions -> Run workflow**.
