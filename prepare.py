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
subprocess.call(['wget', '-O', 'static/d3-tip.js',
                 'https://model.energy/static/d3-tip.js'])
subprocess.call(['wget', '-O', 'static/d3.v4.min.js',
                 'https://model.energy/static/d3.v4.min.js'])
subprocess.call(['wget', '-O', 'static/ne-countries-110m.json',
                 'https://model.energy/static/ne-countries-110m.json'])
subprocess.call(['wget', '-O', 'static/results-initial.json',
                 'https://model.energy/static/results-initial.json'])
