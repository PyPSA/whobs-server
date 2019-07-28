import os
import subprocess
import xarray as xr
import pandas as pd

# TODO Get weather data from ERA5
os.makedirs('data', exist_ok=True)

# Create folders for results
os.makedirs('results', exist_ok=True)
os.makedirs('results-solve', exist_ok=True)
os.makedirs('assumptions', exist_ok=True)

# Get static files excluded from repo
for filename in ['d3-tip.js','d3.v4.min.js','ne-countries-110m.json','results-initial.json','selected_admin1.json']:
    subprocess.call(['wget', '-O', 'static/{}'.format(filename),
                     'https://model.energy/static/{}'.format(filename)])
