"""What the app does when the user acts: the menus' and the control panel's
handlers.

``PyMapprApp`` in pymappr.app is put together from one mixin per concern:

- ``project_files``: new, open, save, import and export of projects, and
  the session restored at the next launch
- ``state``: everything a project stores, collected into one dict and
  applied back
- ``datasets``: adding, editing and removing datasets, the filter, grouping,
  open symbols and point styling, and laying the points out for the map
- ``presets``: the built-in Standard preset, user-saved presets and the
  legend
- ``map_settings``: basemap, projection, layers, north arrow, scale bar,
  inset map, palette, labels and graticule, plus image and code export

The mixins have no ``__init__``; they use the attributes ``PyMapprApp``
sets up (``root``, ``panel``, ``renderer``, ``entries`` and so on).
"""

from pymappr.handlers.datasets import DatasetsMixin
from pymappr.handlers.map_settings import MapSettingsMixin
from pymappr.handlers.presets import PresetsMixin
from pymappr.handlers.project_files import ProjectFilesMixin
from pymappr.handlers.state import StateMixin

__all__ = ["DatasetsMixin", "MapSettingsMixin", "PresetsMixin",
           "ProjectFilesMixin", "StateMixin"]
