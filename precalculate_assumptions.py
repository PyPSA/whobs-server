import solve

import hashlib, json

import pandas as pd

from server import sanitise_assumptions, compute_weather_hash, compute_results_hash

countries = "country:" + pd.Index(solve.get_country_multipolygons().keys())

regions = "region:" + pd.Index(solve.get_region_multipolygons().keys())

locations = countries.append(regions)

years = range(2011,2014)

techs = ["solar","onwind"]

cf_exponents = [2.,1.,0.]

assumption_years = [2020,2030,2050]

base_assumptions = {"wind" : True,
                    "solar" : True,
                    "battery" : True,
                    "hydrogen" : True,
                    "dispatchable1": False,
                    "dispatchable2": False,
                    "co2_limit": False,
                    "dispatchable1_cost" : 400,
      	            "dispatchable1_marginal_cost" : 50,
       	            "dispatchable1_emissions" : 500,
       	            "dispatchable1_discount" : 10,
       	            "dispatchable2_cost" : 6000,
       	            "dispatchable2_marginal_cost" : 10,
       	            "dispatchable2_emissions" : 0,
       	            "dispatchable2_discount" : 10,
                    "co2_emissions" : 0,
                    "load" : 100.0,
                    "hydrogen_load" : 0.0,
                    "frequency" : 3,
                    "discount_rate" : 5.0,
                    "version" : solve.current_version}


#copied from static/solver.js
tech_assumptions = {"2020" : {"wind_cost" : 1120,
			      "solar_cost" : 420,
			      "battery_energy_cost" : 232,
			      "battery_power_cost" : 270,
			      "hydrogen_energy_cost" : 0.7,
			      "hydrogen_electrolyser_cost" : 1100,
			      "hydrogen_electrolyser_efficiency" : 58,
			      "hydrogen_turbine_cost" : 880,
			      "hydrogen_turbine_efficiency" : 56,
				 },
		    "2030" : {"wind_cost" : 1040,
			      "solar_cost" : 300,
			      "battery_energy_cost" : 142,
			      "battery_power_cost" : 160,
			      "hydrogen_energy_cost" : 0.7,
			      "hydrogen_electrolyser_cost" : 600,
			      "hydrogen_electrolyser_efficiency" : 62,
			      "hydrogen_turbine_cost" : 830,
			      "hydrogen_turbine_efficiency" : 58,
		    },
		    "2050" : {"wind_cost" : 960,
			      "solar_cost" : 240,
			      "battery_energy_cost" : 75,
			      "battery_power_cost" : 60,
			      "hydrogen_energy_cost" : 0.7,
			      "hydrogen_electrolyser_cost" : 400,
			      "hydrogen_electrolyser_efficiency" : 67,
			      "hydrogen_turbine_cost" : 800,
			      "hydrogen_turbine_efficiency" : 60,
		    }
}

assumptions = base_assumptions.copy()

for cf_exponent in cf_exponents:
    for year in years:
        for location in locations:
            assumptions["cf_exponent"] = cf_exponent
            assumptions["location"] = location
            assumptions["year"] = year

            for assumption_year in assumption_years:

                assumptions.update(tech_assumptions[str(assumption_year)])

                error_message, assumptions = sanitise_assumptions(assumptions)
                if error_message is not None:
                    print(error_message)
                    sys.exit()

                assumptions["weather_hex"] = compute_weather_hash(assumptions)

                assumptions["job_type"] = "weather"

                with open('data/weather-assumptions-{}.json'.format(assumptions['weather_hex']), 'w') as fp:
                    json.dump(assumptions,fp)

                assumptions["results_hex"] = compute_results_hash(assumptions)

                assumptions["job_type"] = "solve"

                with open('data/results-assumptions-{}.json'.format(assumptions['results_hex']), 'w') as fp:
                    json.dump(assumptions,fp)
