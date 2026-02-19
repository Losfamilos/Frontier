# Nordic Banking Frontier Radar (V1)

A full-automatic strategic radar for Nordic banks:
- Pull-only ingestion (arXiv + trusted RSS feeds)
- Movements (clusters) + fixed scoring model
- Top themes bubble view
- Audit trail (why a score)
- Quarterly snapshots + history

## Quickstart (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt

python cli.py init-db
python cli.py ingest --days 365
python cli.py build --days 365
python cli.py snapshot

python cli.py serve --port 8000
# open http://127.0.0.1:8000
```

## Add / Replace Sources

Edit `cli.py` -> `register_default_connectors()` and update RSS URLs.
The connector interface is stable: connectors return items with:

- `event_uid`, `date`, `title`, `url`, `raw_text`

## V1.1 Premium APIs

Create `connectors/premium/*.py` that conforms to the same interface.
Then register them like the existing connectors.

## Notes

- Scoring is fixed weights and fully audit-able.
- LLM is NOT required in V1 (summaries are deterministic). You can add LLM later in `engine/summary.py`.

## 3) Hvad du får ud af det her (i UI)

- Dashboard med **Executive Summary** + **ELT/Board topics**
- Bubble chart (Top 5 temaer)
- Klik på tema → liste af movements
- Klik på movement → **audit trail + links**
- History-side (kræver at du kører `cli.py snapshot` over tid)

## 4) Næste skridt for at “komme i mål” i banken

1) Skift RSS feeds til bankens “approved” kildeliste (ECB/BIS/EBA/MAS + SWIFT/DTCC/Euroclear + VC)
2) Kør i en uge, se støj vs signal
3) Justér:
   - `distance_threshold` i clustering
   - query i arXiv
4) Dockerize (kan vi gøre som næste step)
