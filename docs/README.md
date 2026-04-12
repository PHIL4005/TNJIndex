### Phase 02 本地检索测试页（默认 127.0.0.1，勿暴露公网）

```
uv run python -m pipelines.app
```

浏览器打开 `http://127.0.0.1:8000`；固定查询集见 `pipelines/eval_queries.txt`。

### scraping for Tieba:
```
uv run python scrapers/tieba_fetch.py --kw novelai --out data/staging/tieba/run1 --max-threads 100 --sort create --skip-pages 4
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