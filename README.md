
# model.energy: online optimisation of energy systems

This is the code for the online optimisation of zero-direct-emission
electricity systems with wind, solar and storage (using batteries and
electrolysed hydrogen gas) to provide a baseload electricity demand,
using the cost and other assumptions of your choice. It uses only free
software and open data, including [Python for Power System Analysis
(PyPSA)](https://github.com/PyPSA/PyPSA) for the optimisation
framework, the European Centre for Medium-Range Weather Forecasts
(ECMWF) [ERA5
dataset](https://cds.climate.copernicus.eu/cdsapp#!/dataset/reanalysis-era5-single-levels)
for the open weather data, the [atlite
library](https://github.com/FRESNA/atlite) for converting weather data
to generation profiles, [Clp](https://projects.coin-or.org/Clp) for
the solver, [D3.js](https://d3js.org/) for graphics,
[Mapbox](https://www.mapbox.com/), [Leaflet](http://leafletjs.com/)
and [Natural Earth](https://www.naturalearthdata.com/) for maps, and
free software for the server infrastructure (GNU/Linux, nginx, Flask,
gunicorn, Redis).

You can find a live version at:

<https://model.energy/>


## Requirements

### Software

This software has only been tested on the Ubuntu distribution of GNU/Linux.

Ubuntu packages:

`sudo apt install coinor-clp coinor-cbc redis-server`

To install, we recommend using [miniconda](https://docs.conda.io/en/latest/miniconda.html) in combination with [mamba](https://github.com/QuantStack/mamba).

	conda install -c conda-forge mamba
	mamba env create -f environment.yaml

For (optional) server deployment:

	sudo apt install nginx
	mamba install gunicorn


### Automatic preparation

After installing the dependencies above, run the following line of code:

	python prepare.py

This helps you:

1. Fetch the pre-processed wind and solar data for the globe (around 6.5 GB per weather year specified in `config.yaml`)
1. Create folders for results
1. Fetch static files not included in this repository

Now you are ready to [run the server locally](#run-server-locally-on-your-own-computer).

### Generating wind and solar data yourself

The script `prepare.py` will download everything you need to get
started, including the pre-processed wind and solar data for the
globe. If you want to build this data from scratch from wind and solar
data, follow these instructions. Be warned that the global datasets
take space of 444 GB per weather year.

For the wind and solar generation time series, we use the European
Centre for Medium-Range Weather Forecasts (ECMWF) [ERA5
dataset](https://cds.climate.copernicus.eu/cdsapp#!/dataset/reanalysis-era5-single-levels).

First you need to download the weather data (e.g. wind speeds, direct
and diffuse solar radiation) as cutouts, then you need to convert them
to power system data for particular wind turbines and solar
panels. The weather data is in a 0.25 by 0.25 degree spatial
resolution grid for the whole globe, but to save space, we downscale
it to 0.5 by 0.5 degrees.

Data is downloaded from the European [Climate Data Store
(CDS)](https://cds.climate.copernicus.eu/) using the [atlite
library](https://github.com/FRESNA/atlite) using the script:

`python build_cutouts.py`

Note that you need to register an account on the CDS first in order to
get a CDS API key.

As of 19.03.2023 the atlite master cannot cope with such large
cutouts, so you need to use the [monthly retrieval
branch](https://github.com/PyPSA/atlite/tree/feat/era5-monthly-retrieveal)
of atlite. If you have shapely 2.0 you will need to backport [this bug
fix](https://github.com/PyPSA/atlite/blob/ad6c9f5a076054e2b953666076447729e33c2fb0/atlite/gis.py#L150)
by hand in the code.


Set the `weather_years` you want to download in `config.yaml`. For
each year it will download 4 quadrants cutouts (4 slices of 90 degrees
of longitude) to cover the whole globe. Each quadrant takes up 111 GB,
so you will need 444 GB per year.

To build the power system data, i.e. wind and solar generation time
series for each point on the globe, run the script:

`python convert_and_downscale_cutout.py`

Each quadrant is split into two octants, one for the northern half of
the quadrant with solar panels facing south, and the other for the
southern half with solar panels facing north (with a slope of 35
degrees against the horizontal in both cases). The script downscales
the spatial resolution to 0.5 by 0.5 degrees to save disk space. Each
octant takes up 820 MB for both technologies (solar and onshore wind),
so in total for a year we have 820 MB times 8 octants, i.e. 6.5 GB.


## Run without server

See the regular [WHOBS](https://github.com/PyPSA/WHOBS) repository.

## Run server locally on your own computer

To run locally you need to start the Python Flask server in one terminal, and redis in another:

Start the Flask server in one terminal with:

`python server.py`

This will serve to local address:

http://127.0.0.1:5002/

In the second terminal start Redis:

`rq worker whobs`

where `whobs` is the name of the queue. No jobs will be solved until
this is run. You can run multiple workers to process jobs in parallel.


## Deploy on a publicly-accessible server

Use nginx, gunicorn for the Python server, rq, and manage with supervisor.

See [nginx server configuration](nginx-configuration.txt).


## License

Copyright 2018-2023 Tom Brown <https://nworbmot.org/>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation; either [version 3 of the
License](LICENSE.txt), or (at your option) any later version.

This program is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the [GNU
Affero General Public License](LICENSE.txt) for more details.
