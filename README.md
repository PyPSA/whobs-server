
# Online optimisation for Wind-Hydrogen-Other-Battery-Solar (WHOBS) systems

This is the code for the online optimisation of
[WHOBS](https://github.com/PyPSA/WHOBS) systems. You can optimise a
zero-direct-emission electricity system with wind, solar and storage
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

<https://whobs.org/>



## Requirements

### Software

Ubuntu packages:

`sudo apt install coinor-clp coinor-cbc python3-venv redis-server`

In addition for a server deployment:

`sudo apt install nginx`

Python:

`pip install ipython pandas numpy redis rq Flask xarray netcdf4 json`

`pip install git+https://github.com/PyPSA/PyPSA.git`

In addition for a server deployment:

`pip install gunicorn`


### Data

For the wind and solar generation time series, get from the [renewables.ninja download page](https://www.renewables.ninja/downloads):

- Solar time series `ninja_pv_europe_v1.1_sarah.csv` from "PV v1.1 Europe"

- Wind time series `ninja_wind_europe_v1.1_current_on-offshore.csv` from "Wind v1.1 Europe"


Convert them to netCDF format with:

```python
import xarray as xr
import pandas as pd
solar_pu = pd.read_csv('ninja_pv_europe_v1.1_sarah.csv',
                       index_col=0, parse_dates=True)
ds = xr.Dataset.from_dataframe(solar_pu)
ds.to_netcdf('ninja_pv_europe_v1.1_sarah.nc')
```

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

See <nginx-configuration.txt> for the nginx server configuration.


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
