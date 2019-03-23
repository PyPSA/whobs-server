import os
import atlite
import logging
logger = logging.getLogger(__name__)

logging.basicConfig(level="INFO")


year = 2014

cutout_dir = "/beegfs/work/ws/ka_kc5996-cutouts-0/"


for quadrant in range(4):
    x0 = -180 + quadrant*90.
    x1 = x0 + 90.

    y0 = 90.
    y1 = -90.

    cutout_name = "quadrant{}-{}".format(quadrant,year)


    cutout_params = {"module" : "era5",
                     "xs" : [x0,x1],
                     "ys" : [y0,y1],
                     "years" : [year, year]}

    print("Preparing cutout for quadrant {} with name {} and parameters {}".format(quadrant,cutout_name,cutout_params))


    for p in ('xs', 'ys', 'years', 'months'):
        if p in cutout_params:
            cutout_params[p] = slice(*cutout_params[p])

    cutout = atlite.Cutout(cutout_name,
                           cutout_dir=cutout_dir,
                           **cutout_params)

    cutout.prepare(nprocesses=4)

    print("Preparation finished")
