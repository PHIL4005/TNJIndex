### scraping for Tieba:
```
v run python scrapers/tieba_fetch.py --kw novelai --out data/staging/tieba/run1 --max-threads 100 --sort create --skip-pages 4
```

### blur imgs
```
uv run python scrapers/tieba_blur_corner.py \
  --input-dir data/staging/tieba/test_blur \
  --in-place
```

### ingest
```
cd /Users/philshi/repos/TNJIndex
uv run python scrapers/ingest.py --dir data/staging/tieba/collected_20260410 --source "tieba collected 20260410"
```