import solve

import hashlib

import pandas as pd

location_type = "region"

multipolygons = getattr(solve,"get_{}_multipolygons".format(location_type))()

years = range(2011,2014)

techs = ["solar","onwind"]

cf_exponents = [0.,1.,2.]

assumption_years = [2020,2030,2050]



booleans = ["wind","solar","battery","hydrogen"]

floats = ["cf_exponent","load","wind_cost","solar_cost","battery_energy_cost",
          "battery_power_cost","hydrogen_electrolyser_cost",
          "hydrogen_energy_cost",
          "hydrogen_electrolyser_efficiency",
          "hydrogen_turbine_cost",
          "hydrogen_turbine_efficiency",
          "discount_rate"]

ints = ["year","frequency"]


base_assumptions = {"wind" : True,
                    "solar" : True,
                    "battery" : True,
                    "hydrogen" : True,
                    "load" : 100.0,
                    "frequency" : 3,
                    "discount_rate" : 5.0}


#copied from static/solver.js
tech_assumptions = {"2020" : {"wind_cost" : 1240,
			      "solar_cost" : 750,
			      "battery_energy_cost" : 300,
			      "battery_power_cost" : 300,
			      "hydrogen_energy_cost" : 0.5,
			      "hydrogen_electrolyser_cost" : 900,
			      "hydrogen_electrolyser_efficiency" : 75,
			      "hydrogen_turbine_cost" : 800,
			      "hydrogen_turbine_efficiency" : 60,
				 },
		    "2030" : {"wind_cost" : 1182,
			      "solar_cost" : 600,
			      "battery_energy_cost" : 200,
			      "battery_power_cost" : 200,
			      "hydrogen_energy_cost" : 0.5,
			      "hydrogen_electrolyser_cost" : 700,
			      "hydrogen_electrolyser_efficiency" : 80,
			      "hydrogen_turbine_cost" : 800,
			      "hydrogen_turbine_efficiency" : 60,
		    },
		    "2050" : {"wind_cost" : 1075,
			      "solar_cost" : 425,
			      "battery_energy_cost" : 100,
			      "battery_power_cost" : 100,
			      "hydrogen_energy_cost" : 0.5,
			      "hydrogen_electrolyser_cost" : 500,
			      "hydrogen_electrolyser_efficiency" : 80,
			      "hydrogen_turbine_cost" : 800,
			      "hydrogen_turbine_efficiency" : 60,
		    }
}

for year in years:
    for cf_exponent in cf_exponents:
        for location in multipolygons:
            weather_hex = hashlib.md5("{}&{}&{}".format((location_type + ":" + location).replace("country:",""), year, cf_exponent).encode()).hexdigest()
            weather_csv = 'data/time-series-{}.csv'.format(weather_hex)
            pu = pd.read_csv(weather_csv,
                             index_col=0,
                             parse_dates=True)
            for assumption_year in assumption_years:
                assumptions = base_assumptions.copy()
                assumptions.update(tech_assumptions[str(assumption_year)])
                assumptions["year"] = year
                assumptions["cf_exponent"] = cf_exponent
                assumptions["location"] = location_type + ":" + location
                results_string = assumptions["location"].replace("country:","")

                for item in ints+booleans:
                    results_string += "&{}".format(assumptions[item])
                for item in floats:
                    results_string += "&{}".format(float(assumptions[item]))

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
