import os
import atlite
import logging
import numpy as np
import pandas as pd
from shapely.geometry import box
import scipy as sp, scipy.sparse

logger = logging.getLogger(__name__)

logging.basicConfig(level="INFO")

config = {"onwind" : { "resource" : { "turbine" : "Vestas_V112_3MW"}},
          "solar" : { "correction_factor": 1.,
                      "resource" : { "panel" : "CSi",
                                     "orientation" : {"slope" : 35.,
                                                       "azimuth" : 0.}}}}

method = {"onwind" : "wind",
          "solar" : "pv"}


def indicator(range_start, range_end, range_gap, interval_start, interval_end):
    """ Return list of locations of overlaps between interval and range
    Example: indicator(0, 90, 0.3, 89.5, 90.5) returns
    [[298, 0.666666666], [299, 1]]
    """
    if interval_end < range_start or interval_start > range_end:
        return []

    i_start = max(int((interval_start-range_start)/range_gap),0)
    i_end = min(int((interval_end-range_start)/range_gap),int(round((range_end-range_start)/range_gap))-1)

    result = []

    #potential overlaps
    for i in range(i_start,i_end+1):
        candidate_start = range_start + i*range_gap
        candidate_end = range_start + (i+1)*range_gap
        #print(candidate_start, candidate_end)

        overlap_start = max(interval_start,candidate_start)
        overlap_end = min(interval_end,candidate_end)

        fraction = (overlap_end-overlap_start)/range_gap
        if abs(fraction) > 1e-5:
            result.append([i,fraction])

    return result




def generate_octant(cutout_name, cutout_span, years, xs, ys, azimuth, filename):

    config["solar"]["resource"]["orientation"]["azimuth"] = azimuth

    cutout = atlite.Cutout(cutout_name+".nc").sel(x=xs,y=ys)

    print("cutout has extent", cutout.extent)

    new_mesh = 0.5

    x = np.arange(cutout.coords['x'].values[0],
                  cutout.coords['x'].values[-1] + new_mesh,
                  new_mesh)

    y = np.arange(cutout.coords['y'].values[0],
                  cutout.coords['y'].values[-1] + new_mesh,
                  +new_mesh)


    #grid_coordinates and grid_cells copied from atlite/cutout.py

    xs, ys = np.meshgrid(x,y)
    new_grid_coordinates = np.asarray((np.ravel(xs), np.ravel(ys))).T


    span = new_mesh / 2
    new_grid_cells = [box(*c) for c in np.hstack((new_grid_coordinates - span, new_grid_coordinates + span))]

    ## build transfer matrix from cutout grid to new grid
    matrix = cutout.indicatormatrix(new_grid_cells)

    # Normalise so that i'th row adds up to 1 (since have 1 MW in each coarse grid_cell)
    matrix = matrix.multiply(1/matrix.sum(axis=1))


    for tech in config.keys():

        print("Making {} profiles".format(tech))

        resource = config[tech]['resource']

        func = getattr(cutout, method[tech])

        profiles = func(matrix=matrix,
                        index=pd.Index(range(matrix.shape[0])),
                        **resource)

        correction_factor = config[tech].get('correction_factor', 1.)

        (correction_factor * profiles).to_netcdf("{}-{}.nc".format(filename, tech))



year = 2011

for i in range(8):

    quadrant = i//2

    x0 = -180 + quadrant*90.
    x1 = x0 + 90.

    y0 = -90. + (i%2)*90.
    y1 = y0 + 90.


    filename = "octant{}-{}".format(i, year)
    years = slice(year,year)
    xs = slice(x0,x1)
    ys = slice(y0,y1)

    cutout_name = "quadrant-{}-{}".format(year, quadrant)

    cutout_span = 0.25

    if y0 == 0.:
        azimuth = 180.
    else:
        azimuth = 0.

    print("Doing octant",i,"corresponding to quadrant",quadrant,"and azimuth",azimuth)
    print(x0,x1,y0,y1)

    generate_octant(cutout_name, cutout_span, years, xs, ys, azimuth, filename)
