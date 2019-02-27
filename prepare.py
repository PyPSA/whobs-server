import os
import subprocess
import xarray as xr
import pandas as pd

# Get weather data from renewables.ninja
os.makedirs('data', exist_ok=True)
subprocess.call(['wget', '-O', 'data/ninja_europe_pv_v1.1.zip',
                 'https://www.renewables.ninja/static/downloads/ninja_europe_pv_v1.1.zip'])
subprocess.call(['wget', '-O', 'data/ninja_europe_wind_v1.1.zip',
                 'https://www.renewables.ninja/static/downloads/ninja_europe_wind_v1.1.zip'])
subprocess.call(['unzip', 'data/*', '-d', 'data/'])

# Convert data to netCDF
solar_pu = pd.read_csv('data/ninja_pv_europe_v1.1_sarah.csv',
                       index_col=0, parse_dates=True)
ds = xr.Dataset.from_dataframe(solar_pu)
ds.to_netcdf('data/ninja_pv_europe_v1.1_sarah.nc')

wind_pu = pd.read_csv(
    'data/ninja_wind_europe_v1.1_current_on-offshore.csv', index_col=0, parse_dates=True)
ds = xr.Dataset.from_dataframe(wind_pu)
ds.to_netcdf('data/ninja_wind_europe_v1.1_current_on-offshore.nc')

# Create folders for results
os.makedirs('results', exist_ok=True)
os.makedirs('results-solve', exist_ok=True)
os.makedirs('assumptions', exist_ok=True)

# Get static files excluded from repo
subprocess.call(['wget', '-O', 'static/d3-tip.js',
                 'https://model.energy/static/d3-tip.js'])
subprocess.call(['wget', '-O', 'static/d3.v4.min.js',
                 'https://model.energy/static/d3.v4.min.js'])
subprocess.call(['wget', '-O', 'static/ne_50m_admin_0_countries_simplified_europe.json',
                 'https://model.energy/static/ne_50m_admin_0_countries_simplified_europe.json'])
subprocess.call(['wget', '-O', 'static/results-initial.json',
                 'https://model.energy/static/results-initial.json'])
