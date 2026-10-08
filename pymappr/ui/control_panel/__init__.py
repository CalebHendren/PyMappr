"""Tabbed side panel holding every map control.

With ~30 layer toggles the panel is organized as a notebook of five
scrollable tabs - Data (CSV, styling), Legend, Map (view, projection,
graticule, compass, export), Layers (every Natural Earth layer, grouped),
and Labels. The panel owns the Tk variables and forwards changes to the
app's handler methods; the app owns the renderer and the data.

``ControlPanel`` is put together from one mixin per concern:

- ``widgets``: the plain widgets every tab is built from
- ``data_tab``: the Data and Legend tabs
- ``map_tab``: the Map tab, and the inset's options
- ``layers_tab``: the Layers and Labels tabs
- ``values``: the getters and setters over the panel's Tk variables

``tables`` holds the fixed tables: display names for each choice and the
rows of the Layers, Labels and Legend tabs.
"""

from pymappr.ui.control_panel.core import ControlPanel
from pymappr.ui.control_panel.tables import (INSET_REGION_LABELS,
                                             TYPING_PAUSE_MS, name_for)

__all__ = ["ControlPanel", "INSET_REGION_LABELS", "TYPING_PAUSE_MS",
           "name_for"]
