import solve

import hashlib

import pandas as pd

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

for cf_exponent in cf_exponents:
    for year in years:
        for location in locations:
            print(year,cf_exponent,location)
            weather_hex = hashlib.md5("{}&{}&{}&{}".format(location.replace("country:",""), year, cf_exponent, base_assumptions["version"]).encode()).hexdigest()
            weather_csv = 'data/time-series-{}.csv'.format(weather_hex)
            pu = pd.read_csv(weather_csv,
                             index_col=0,
                             parse_dates=True)
            snapshots = pd.date_range("{}-01-01".format(year),"{}-12-31 23:00".format(year),freq="H")
            pu = pu.reindex(snapshots,method="nearest")

            for assumption_year in assumption_years:
                assumptions = base_assumptions.copy()
                assumptions.update(tech_assumptions[str(assumption_year)])
                assumptions["year"] = year
                assumptions["cf_exponent"] = cf_exponent
                assumptions["location"] = location
                results_string = assumptions["location"].replace("country:","")

                for item in solve.floats:
                    assumptions[item] = float(assumptions[item])

                for item in solve.ints+solve.booleans+solve.floats:
                    if "dispatchable1" in item and not assumptions["dispatchable1"]:
                        continue
                    if "dispatchable2" in item and not assumptions["dispatchable2"]:
                        continue
                    if "co2" in item and not assumptions["co2_limit"]:
                        continue
                    if item == "version" and assumptions["version"] == 0:
                        continue
                    if item == "hydrogen_load" and assumptions["hydrogen_load"] == 0:
                        continue
                    results_string += "&{}".format(assumptions[item])

                assumptions['results_hex'] = hashlib.md5(results_string.encode()).hexdigest()
                print(results_string)
                print(assumptions['results_hex'])
                series_csv = 'data/results-series-{}.csv'.format(assumptions['results_hex'])
                overview_csv = 'data/results-overview-{}.csv'.format(assumptions['results_hex'])

                print("Calculating results from scratch, saving as:", series_csv, overview_csv)
                results_overview, results_series, error_msg = solve.run_optimisation(assumptions, pu)
                print(error_msg)
                results_series = results_series.round(1)
                results_series.to_csv(series_csv)
                results_overview.to_csv(overview_csv,header=False)
