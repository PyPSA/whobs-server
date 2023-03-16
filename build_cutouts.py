import atlite
import logging
import yaml, os

logger = logging.getLogger(__name__)

logging.basicConfig(level="INFO")

year = 2011

with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

octant_folder = config["octant_folder"]

for quadrant in range(4):

    print("preparing quadrant",quadrant)

    x0 = -180 + quadrant*90.
    x1 = x0 + 90.

    y0 = -90.
    y1 = 90.

    cutout_name = os.path.join(octant_folder,
                               f"quadrant-{year}-{quadrant}.nc")

    cutout = atlite.Cutout(path=cutout_name,
                           module="era5",
                           x=slice(x0,x1),
                           y=slice(y0,y1),
                           time=str(year))

    cutout.prepare()
