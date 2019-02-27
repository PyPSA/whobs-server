
# model.energy: online optimisation of energy systems

This is the code for the online optimisation of
zero-direct-emission electricity systems with wind, solar and storage
(using batteries and electrolysed hydrogen gas) to provide a baseload
electricity demand, using the cost and other assumptions of your
choice. It uses only free software and open data, including [Python
for Power System Analysis (PyPSA)](https://github.com/PyPSA/PyPSA) for
the optimisation framework,
[renewables.ninja](https://www.renewables.ninja/) for the open weather
data, [Clp](https://projects.coin-or.org/Clp) for the solver,
[D3.js](https://d3js.org/) for graphics,
[Mapbox](https://www.mapbox.com/), [Leaflet](http://leafletjs.com/)
and [Natural Earth](https://www.naturalearthdata.com/) for maps, and
free software for the server infrastructure (GNU/Linux, nginx, Flask,
gunicorn, Redis).

You can find a live version at:

<https://model.energy/>


## Requirements

### Software

Ubuntu packages:

`sudo apt install coinor-clp coinor-cbc python3-venv redis-server`

Python:

	python3 -m venv venv
	. venv/bin/activate
	pip install -r requirements.txt

For (optional) server deployment:

	sudo apt install nginx
	pip install gunicorn

### Preparation

After installing the dependencies above, run the following line of code:

	python prepare.py

This helps you:

1. Fetch the weather data described below
1. Convert it to netCDF
1. Create folders for results
1. Fetch static files not included in this repository

Now you are ready to [run the server locally](#run-server-locally-on-your-own-computer).

### Data

For the wind and solar generation time series, we use the following from the [renewables.ninja download page](https://www.renewables.ninja/downloads):

- Solar time series `ninja_pv_europe_v1.1_sarah.csv` from "PV v1.1 Europe"
- Wind time series `ninja_wind_europe_v1.1_current_on-offshore.csv` from "Wind v1.1 Europe"

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

Copyright 2018-2019 Tom Brown <https://nworbmot.org/>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation; either [version 3 of the
License](LICENSE.txt), or (at your option) any later version.

This program is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the [GNU
Affero General Public License](LICENSE.txt) for more details.
