#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (c) 2015

# Author(s):

#   Martin Raspaud <martin.raspaud@smhi.se>
#   David Hoese <david.hoese@ssec.wisc.edu>

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Base classes for composite objects.
"""

from mpop.projectable import InfoObject, Projectable
import numpy as np
import logging

LOG = logging.getLogger(__name__)
# TODO: overview_sun


class CompositeBase(InfoObject):

    def __init__(self, name, compositor, prerequisites, default_image_config=None,
                 **kwargs):
        # Required info
        kwargs["name"] = name
        kwargs["compositor"] = compositor
        kwargs["prerequisites"] = []
        for prerequisite in prerequisites.split(","):
            try:
                kwargs["prerequisites"].append(float(prerequisite))
            except ValueError:
                kwargs["prerequisites"].append(prerequisite)
        InfoObject.__init__(self, **kwargs)
        if default_image_config is None:
            return
        for key, value in default_image_config.iteritems():
            self.info.setdefault(key, value)

    @property
    def prerequisites(self):
        # Semi-backward compatible
        return self.info["prerequisites"]

    def __call__(self, projectables, nonprojectables=None, **info):
        raise NotImplementedError()


class SunZenithNormalize(object):
    # FIXME: the cache should be cleaned up
    coszen = {}

    def __call__(self, projectable,  *args, **kwargs):
        from pyorbital.astronomy import cos_zen
        key = (projectable.info["start_time"], projectable.info["area"].name)
        if key not in self.coszen:
            LOG.debug("Computing sun zenith angles.")
            self.coszen[key] = np.ma.masked_outside(cos_zen(projectable.info["start_time"],
                                                    *projectable.info["area"].get_lonlats()),
                                                    0.035, # about 88 degrees.
                                                    1,
                                                    copy=False)
        return projectable / self.coszen[key]


class RGBCompositor(CompositeBase):
    def __call__(self, projectables, nonprojectables=None, **info):
        if len(projectables) != 3:
            raise ValueError("Expected 3 projectables, got %d" % (len(projectables),))
        the_data = np.rollaxis(np.ma.dstack([projectable for projectable in projectables]), axis=2)
        info = projectables[0].info.copy()
        info.update(projectables[1].info)
        info.update(projectables[2].info)
        info.update(self.info)
        # FIXME: should this be done here ?
        info.pop("wavelength_range", None)
        info.pop("units", None)
        sensor = set()
        for projectable in projectables:
            current_sensor = projectable.info.get("sensor", None)
            if current_sensor:
                if isinstance(current_sensor, (str, unicode)):
                    sensor.add(current_sensor)
                else:
                    sensor |= current_sensor
        if len(sensor) == 0:
            sensor = None
        elif len(sensor) == 1:
            sensor = list(sensor)[0]
        info["sensor"] = sensor
        info["mode"] = "RGB"
        return Projectable(data=the_data, **info)


class SunCorrectedRGB(RGBCompositor):
    def __call__(self, projectables, *args, **kwargs):
        suncorrector = SunZenithNormalize()
        for i, projectable in enumerate(projectables):
            if projectable.info.get("units") == "%":
                projectables[i] = suncorrector(projectable)
        res = RGBCompositor.__call__(self,
                                     projectables,
                                     *args, **kwargs)
        return res


class Airmass(RGBCompositor):
    def __call__(self, projectables, *args, **kwargs):
        """Make an airmass RGB image composite.

        +--------------------+--------------------+--------------------+
        | Channels           | Temp               | Gamma              |
        +====================+====================+====================+
        | WV6.2 - WV7.3      |     -25 to 0 K     | gamma 1            |
        +--------------------+--------------------+--------------------+
        | IR9.7 - IR10.8     |     -40 to 5 K     | gamma 1            |
        +--------------------+--------------------+--------------------+
        | WV6.2              |   243 to 208 K     | gamma 1            |
        +--------------------+--------------------+--------------------+
        """
        res = RGBCompositor.__call__(self,
                                     (projectables[0] - projectables[1],
                                      projectables[2] - projectables[3],
                                      projectables[0]),
                                     *args, **kwargs)
        return res


class Convection(RGBCompositor):
    def __call__(self, projectables, *args, **kwargs):
        """Make a Severe Convection RGB image composite.

        +--------------------+--------------------+--------------------+
        | Channels           | Span               | Gamma              |
        +====================+====================+====================+
        | WV6.2 - WV7.3      |     -30 to 0 K     | gamma 1            |
        +--------------------+--------------------+--------------------+
        | IR3.9 - IR10.8     |      0 to 55 K     | gamma 1            |
        +--------------------+--------------------+--------------------+
        | IR1.6 - VIS0.6     |    -70 to 20 %     | gamma 1            |
        +--------------------+--------------------+--------------------+
        """
        res = RGBCompositor.__call__(self,
                                     (projectables[3] - projectables[4],
                                      projectables[2] - projectables[5],
                                      projectables[1] - projectables[0]),
                                     *args, **kwargs)
        return res


class Dust(RGBCompositor):
    def __call__(self, projectables, *args, **kwargs):
        """Make a Dust RGB image composite.

        +--------------------+--------------------+--------------------+
        | Channels           | Temp               | Gamma              |
        +====================+====================+====================+
        | IR12.0 - IR10.8    |     -4 to 2 K      | gamma 1            |
        +--------------------+--------------------+--------------------+
        | IR10.8 - IR8.7     |     0 to 15 K      | gamma 2.5          |
        +--------------------+--------------------+--------------------+
        | IR10.8             |   261 to 289 K     | gamma 1            |
        +--------------------+--------------------+--------------------+
        """
        res = RGBCompositor.__call__(self,
                                     (projectables[2] - projectables[1],
                                      projectables[1] - projectables[0],
                                      projectables[1]),
                                     *args, **kwargs)
        return res