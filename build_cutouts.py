import atlite
import logging
import yaml, os

logger = logging.getLogger(__name__)

logging.basicConfig(level="INFO")

with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)


for year in config["weather_years"]:

    logger.info(f"Downloading weather data for year {year}")

    for quadrant in range(4):

        logger.info(f"preparing quadrant {quadrant}")

        x0 = -180 + quadrant*90.
        x1 = x0 + 90.

        y0 = -90.
        y1 = 90.

        cutout_name = os.path.join(config["cutout_folder"],
                                   f"quadrant-{year}-{quadrant}.nc")

        if os.path.isfile(cutout_name):
            logger.info(f"skipping following file, since it already exists: {cutout_name}")
            continue


        cutout = atlite.Cutout(path=cutout_name,
                               module="era5",
                               x=slice(x0,x1),
                               y=slice(y0,y1),
                               time=str(year))

        cutout.prepare()
