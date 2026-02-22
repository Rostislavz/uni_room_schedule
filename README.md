# uni_room_schedule (GitHub Pages branch)

This branch (`gh_pages`) is the static bundle used by GitHub Pages and embedded into Google Sites.

## Files served
- `index.html`
- `style.css`
- `script.js`
- `data/index.json`
- `data/floors/<building>/<floor>.json`

## Update workflow
1. Update source data in the main working repo.
2. Rebuild static data:
   ```bash
   python scripts/build_static_data.py
   ```
3. Copy updated static files to this branch/repo.
4. Commit and push `gh_pages`.
