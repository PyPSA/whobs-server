import solve

from server import compute_weather_hash

import hashlib, json

import pandas as pd

countries = "country:" + pd.Index(solve.get_country_multipolygons().keys())

regions = "region:" + pd.Index(solve.get_region_multipolygons().keys())

locations = countries.append(regions)

country_names = solve.get_country_names()

years = range(2011,2013)

techs = ["solar","onwind"]

cf_exponents = [2.,1.,0.]


for cf_exponent in cf_exponents:
    for year in years:
        matrix_sums = pd.DataFrame(0.,index=locations,columns=techs)
        for location in locations:
            assumptions = {"year" : year,
                           "location" : location,
                           "cf_exponent" : cf_exponent,
                           "version" : 190929,
                           "job_type" : "weather"}
            if location[:len("country:")] == "country:":
                assumptions["location_name"] = country_names[location[len("country:"):]]
            elif location[:len("region:")] == "region:":
                assumptions["location_name"] = location[len("region:"):]
            else:
                assumptions["location_name"] = "None"
            assumptions["weather_hex"] =  compute_weather_hash(assumptions)
            print(location, assumptions["location_name"], year, cf_exponent, assumptions["weather_hex"])
            pu, matrix_sum, error_msg = solve.get_weather(location, year, cf_exponent)

            weather_csv = 'data/time-series-{}.csv'.format(assumptions["weather_hex"])

            pu.round(3).to_csv(weather_csv)
            with open('data/weather-assumptions-{}.json'.format(assumptions['weather_hex']), 'w') as fp:
                json.dump(assumptions,fp)

            for tech in techs:
                matrix_sums.loc[location,tech] = matrix_sum[tech]

        matrix_sums.to_csv("data/matrix_sums-{}-{}.csv".format(year,cf_exponent))
