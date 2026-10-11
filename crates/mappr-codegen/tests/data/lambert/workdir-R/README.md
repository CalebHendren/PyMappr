# lambert - PyMappr map export

A ready-to-run R recreation of the PyMappr map "lambert"
(sf + ggplot2).

## Run it

Open `lambert.Rproj` in RStudio, open `recreate_map.R`, and click Source.
Or, from a terminal in this folder:

    Rscript recreate_map.R

If sf or ggplot2 is missing the script tells you; install them with:

    Rscript install.R

It downloads its map data from Natural Earth into
`naturalearth_cache/` and reads your point data from the CSV files in
`data/`. The finished map is written to `map.png`.
