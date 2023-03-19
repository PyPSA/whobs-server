import os
import yaml
import urllib.request


with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)


# Create folders for results
os.makedirs('results', exist_ok=True)
os.makedirs('results-solve', exist_ok=True)
os.makedirs('assumptions', exist_ok=True)
os.makedirs('data', exist_ok=True)

# Get static files excluded from repo
for filename in ['d3-tip.js','d3.v4.min.js','ne-countries-110m.json','results-initial.json','selected_admin1.json']:
    urllib.request.urlretrieve(f"https://model.energy/static/{filename}",
                               f"static/{filename}")

# Get weather data octants
# To build your own from ERA5 data, see README.md
os.makedirs(config["octant_folder"], exist_ok=True)

for year in config["weather_years"]:
    for quadrant in range(4):
        for hemisphere in range(2):
            for tech in ["onwind","solar"]:
                print(f"downloading weather octants for year {year} quadrant {quadrant} hemisphere {hemisphere} tech {tech}")
                url = f"https://model.energy/octants/octant-{year}-{quadrant}-{hemisphere}-{tech}.nc"
                filename = os.path.join(config["octant_folder"],
                                        f"octant-{year}-{quadrant}-{hemisphere}-{tech}.nc")
                urllib.request.urlretrieve(url, filename)
