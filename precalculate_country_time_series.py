import solve

import hashlib

import pandas as pd

country_multipolygons = solve.get_country_multipolygons()

years = range(2011,2014)

techs = ["solar","onwind"]

cf_exponents = [0.,1.,2.]


for year in years:
    for cf_exponent in cf_exponents:

        matrix_sums = pd.DataFrame(0.,index=list(country_multipolygons.keys()),columns=techs)

        for i,ct in enumerate(country_multipolygons):
            weather_hex = hashlib.md5("{}&{}&{}".format(ct, year, cf_exponent).encode()).hexdigest()
            print(ct, year, cf_exponent, weather_hex)
            pu, matrix_sum, error_msg = solve.get_weather(ct, year, cf_exponent)

            weather_csv = 'data/time-series-{}.csv'.format(weather_hex)

            pu.round(3).to_csv(weather_csv)

            for tech in techs:
                matrix_sums.loc[ct,tech] = matrix_sum[tech]

        matrix_sums.to_csv("data/country_matrix_sums-{}-{}.csv".format(year,cf_exponent))
