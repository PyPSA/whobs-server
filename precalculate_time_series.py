import solve

import hashlib

import pandas as pd

location_type = "region"

multipolygons = getattr(solve,"get_{}_multipolygons".format(location_type))()

years = range(2011,2014)

techs = ["solar","onwind"]

cf_exponents = [0.,1.,2.]


for year in years:
    for cf_exponent in cf_exponents:

        matrix_sums = pd.DataFrame(0.,index=list(multipolygons.keys()),columns=techs)

        for location in multipolygons:
            weather_hex = hashlib.md5("{}&{}&{}".format((location_type + ":" + location).replace("country:",""), year, cf_exponent).encode()).hexdigest()
            print(location, year, cf_exponent, weather_hex)
            pu, matrix_sum, error_msg = solve.get_weather(location_type + ":" + location, year, cf_exponent)

            weather_csv = 'data/time-series-{}.csv'.format(weather_hex)

            pu.round(3).to_csv(weather_csv)

            for tech in techs:
                matrix_sums.loc[location,tech] = matrix_sum[tech]

        matrix_sums.to_csv("data/{}_matrix_sums-{}-{}.csv".format(location_type,year,cf_exponent))
