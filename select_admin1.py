## Copyright 2018-2019 Tom Brown

## This program is free software; you can redistribute it and/or
## modify it under the terms of the GNU Affero General Public License as
## published by the Free Software Foundation; either version 3 of the
## License, or (at your option) any later version.

## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU Affero General Public License for more details.

## License and more information at:
## https://github.com/PyPSA/whobs-server


import json

#from https://datahub.io/core/geo-ne-admin1
with open('static/admin1.geojson') as json_file:
    data = json.load(json_file)


#only keep some countries to avoid very large file sizes
#select large countries and those with big populations
countries_to_keep = ["Australia","Germany","Russia","United States of America","India","China"]
regions_to_keep = []
for d in data["features"]:
    country = d["properties"]["country"]
    if country in countries_to_keep:
        if d["properties"]["name"] is not None:
            regions_to_keep.append(d)
        else:
            print("skipping region",d["properties"]["name"],"in",d["properties"]["country"])

regions_json = {"type" : "FeatureCollection",
                "features" : regions_to_keep}


with open('static/selected_admin1.json', 'w') as fp:
    json.dump(regions_json, fp)
