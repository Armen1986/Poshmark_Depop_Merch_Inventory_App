# ODYSSEY // Inventory Nexus

Local-first resale operations dashboard for tracking inventory, researching markets, organizing photo evidence, and generating listing copy.

## What’s included

- SQLite-backed inventory database
- Item entry, editing, and status tracking
- Market research links for eBay, Poshmark, Mercari, Depop, and Google Images
- Confirmed comparable sales tracking with suggested-price updates
- Photo upload and review workflow
- Listing-copy generation with optional OpenAI support

## Requirements

- Python 3.10+
- tkinter (included with most Python installations on macOS and Windows)
- Optional dependencies:
  - `python3 -m pip install requests pillow`

## Run locally

```bash
python3 inventory_nexus.py
```

## Notes

- No API key is embedded in the app source.
- If `OPENAI_API_KEY` is present, the listing helper can use it; otherwise the app remains fully local.
- Market links open in your browser, and confirmed comps require user confirmation.
