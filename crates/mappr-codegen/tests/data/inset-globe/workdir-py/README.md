# inset globe - PyMappr map export

A ready-to-run Python recreation of the PyMappr map "inset globe"
(pandas + geopandas + matplotlib), replicating PyMappr's own renderer.

## Run it

Open this folder in your IDE (PyCharm, VS Code, ...) and run
`recreate_map.py`. Or, from a terminal in this folder:

    python recreate_map.py

If a package is missing the script tells you; set up the environment
with:

    pip install -r requirements.txt

(or run `python recreate_map.py --install-deps` to let it install them).

It downloads its map data from Natural Earth into
`naturalearth_cache/` and reads your point data from the CSV files in
`data/`. The finished map is written to `map.png`.
