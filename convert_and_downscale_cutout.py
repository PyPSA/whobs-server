import os, yaml
import atlite
import logging
import numpy as np
import pandas as pd
from shapely.geometry import box
import scipy as sp, scipy.sparse

logger = logging.getLogger(__name__)

logging.basicConfig(level="INFO")

with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)


def generate_octant(cutout_name, cutout_span, years, xs, ys, azimuth, octant_name):

    config["renewable"]["solar"]["resource"]["orientation"]["azimuth"] = azimuth

    cutout = atlite.Cutout(cutout_name).sel(x=xs,y=ys)

    logger.info(f"cutout has extent {cutout.extent}")

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


    for tech in config['renewable'].keys():

        logger.info(f"Making {tech} profiles")

        resource = config['renewable'][tech]['resource']

        func = getattr(cutout, config['renewable'][tech]['method'])

        profiles = func(matrix=matrix,
                        index=pd.Index(range(matrix.shape[0])),
                        **resource)

        correction_factor = config['renewable'][tech].get('correction_factor', 1.)

        profiles *= correction_factor

        #reducing from 64-bit to 32-bit halves size
        profiles = profiles.astype(np.float32)

        encoding = {profiles.name: {'zlib': True,
                                    'complevel': config['octant_compression']['complevel'],
                                    'least_significant_digit' : config['octant_compression']['least_significant_digit']}}

        filename = f"{octant_name}-{tech}.nc"

        profiles.to_netcdf(filename,
                           encoding=encoding)

        mean = profiles.mean(dim="time")

        filename = f"{octant_name}-{tech}-mean.nc"

        mean.to_netcdf(filename)



for year in config["weather_years"]:
    for quadrant in range(4):
        for hemisphere in range(2):

            logger.info(f"processing year {year} quadrant {quadrant} and hemisphere {hemisphere}")

            x0 = -180 + quadrant*90.
            x1 = x0 + 90.

            y0 = -90. + hemisphere*90.
            y1 = y0 + 90.


            octant_name = os.path.join(config["octant_folder"],
                                       f"octant-{year}-{quadrant}-{hemisphere}")

            if all([os.path.isfile(f"{octant_name}-{tech}.nc") for tech in config['renewable'].keys()]):
                logger.info(f"skipping following octant, since it already exists: {octant_name}")
                continue

            years = slice(int(year),int(year))
            xs = slice(x0,x1)
            ys = slice(y0,y1)

            cutout_name = os.path.join(config["cutout_folder"],
                                       f"quadrant-{year}-{quadrant}.nc")

            cutout_span = 0.25

            if y0 == 0.:
                azimuth = 180.
            else:
                azimuth = 0.

            logger.info(f"xs {xs}, ys {ys}")
            logger.info(f"Azimuth is {azimuth}")

            generate_octant(cutout_name, cutout_span, years, xs, ys, azimuth, octant_name)
