import solve

from server import sanitise_assumptions, compute_weather_hash, compute_results_hash

import hashlib, json

import pandas as pd

countries = "country:" + pd.Index(solve.get_country_multipolygons().keys())

regions = "region:" + pd.Index(solve.get_region_multipolygons().keys())

locations = countries.append(regions)

country_names = solve.get_country_names()

years = range(2011,2013)

techs = ["solar","onwind"]

cf_exponents = [2.,1.,0.]

assumption_years = [2020,2030,2050]


#copied from static/solver.js
tech_assumptions = {"2020" : {"wind_cost" : 1120,
				  "wind_fom" : 3,
				  "wind_lifetime" : 25,
				  "solar_cost" : 420,
				  "solar_fom" : 3,
				  "solar_lifetime" : 25,
				  "battery_energy_cost" : 232,
				  "battery_energy_fom" : 3,
				  "battery_energy_lifetime" : 15,
				  "battery_power_cost" : 270,
				  "battery_power_fom" : 3,
				  "battery_power_lifetime" : 15,
				  "battery_power_efficiency_charging" : 95,
				  "battery_power_efficiency_discharging" : 95,
				  "hydrogen_energy_cost" : 0.7,
				  "hydrogen_energy_fom" : 14,
				  "hydrogen_energy_lifetime" : 25,
				  "hydrogen_electrolyser_cost" : 1100,
				  "hydrogen_electrolyser_efficiency" : 58,
				  "hydrogen_electrolyser_fom" : 3,
				  "hydrogen_electrolyser_lifetime" : 20,
				  "hydrogen_turbine_cost" : 880,
				  "hydrogen_turbine_efficiency" : 56,
				  "hydrogen_turbine_fom" : 3,
				  "hydrogen_turbine_lifetime" : 25,
				  "dispatchable1_cost" : 400,
				  "dispatchable1_marginal_cost" : 50,
				  "dispatchable1_emissions" : 500,
				  "dispatchable1_fom" : 3,
				  "dispatchable1_lifetime" : 25,
				  "dispatchable2_cost" : 6000,
				  "dispatchable2_marginal_cost" : 10,
				  "dispatchable2_emissions" : 0,
				  "dispatchable2_fom" : 3,
				  "dispatchable2_lifetime" : 25,
				 },
			"2030" : {"wind_cost" : 1040,
				  "wind_fom" : 3,
				  "wind_lifetime" : 25,
				  "solar_cost" : 300,
				  "solar_fom" : 3,
				  "solar_lifetime" : 25,
				  "battery_energy_cost" : 142,
				  "battery_energy_fom" : 3,
				  "battery_energy_lifetime" : 15,
				  "battery_power_cost" : 160,
				  "battery_power_fom" : 3,
				  "battery_power_lifetime" : 15,
				  "battery_power_efficiency_charging" : 95,
				  "battery_power_efficiency_discharging" : 95,
				  "hydrogen_energy_cost" : 0.7,
				  "hydrogen_energy_fom" : 14,
				  "hydrogen_energy_lifetime" : 25,
				  "hydrogen_electrolyser_cost" : 600,
				  "hydrogen_electrolyser_efficiency" : 62,
				  "hydrogen_electrolyser_fom" : 3,
				  "hydrogen_electrolyser_lifetime" : 20,
				  "hydrogen_turbine_cost" : 830,
				  "hydrogen_turbine_efficiency" : 58,
				  "hydrogen_turbine_fom" : 3,
				  "hydrogen_turbine_lifetime" : 25,
				  "dispatchable1_cost" : 400,
				  "dispatchable1_marginal_cost" : 50,
				  "dispatchable1_emissions" : 500,
				  "dispatchable1_fom" : 3,
				  "dispatchable1_lifetime" : 25,
				  "dispatchable2_cost" : 6000,
				  "dispatchable2_marginal_cost" : 10,
				  "dispatchable2_emissions" : 0,
				  "dispatchable2_fom" : 3,
				  "dispatchable2_lifetime" : 25,
				 },
			"2050" : {"wind_cost" : 960,
				  "wind_fom" : 3,
				  "wind_lifetime" : 25,
				  "solar_cost" : 240,
				  "solar_fom" : 3,
				  "solar_lifetime" : 25,
				  "battery_energy_cost" : 75,
				  "battery_energy_fom" : 3,
				  "battery_energy_lifetime" : 15,
				  "battery_power_cost" : 60,
				  "battery_power_fom" : 3,
				  "battery_power_lifetime" : 15,
				  "battery_power_efficiency_charging" : 95,
				  "battery_power_efficiency_discharging" : 95,
				  "hydrogen_energy_cost" : 0.7,
				  "hydrogen_energy_fom" : 14,
				  "hydrogen_energy_lifetime" : 25,
				  "hydrogen_electrolyser_cost" : 400,
				  "hydrogen_electrolyser_efficiency" : 67,
				  "hydrogen_electrolyser_fom" : 3,
				  "hydrogen_electrolyser_lifetime" : 20,
				  "hydrogen_turbine_cost" : 800,
				  "hydrogen_turbine_efficiency" : 60,
				  "hydrogen_turbine_fom" : 3,
				  "hydrogen_turbine_lifetime" : 25,
				  "dispatchable1_cost" : 400,
				  "dispatchable1_marginal_cost" : 50,
				  "dispatchable1_emissions" : 500,
				  "dispatchable1_fom" : 3,
				  "dispatchable1_lifetime" : 25,
				  "dispatchable2_cost" : 6000,
				  "dispatchable2_marginal_cost" : 10,
				  "dispatchable2_emissions" : 0,
				  "dispatchable2_fom" : 3,
				  "dispatchable2_lifetime" : 25,
				 }
		       };

defaults = {"version" : 190929,
	    "location" : "country:DE",
	    "location_name" : "Germany",
	    "job_type" : "none",
	    "year" : 2011,
	    "frequency" : 3,
	    "cf_exponent" : 2,
	    "load" : 100,
	    "hydrogen_load" : 0,
	    "wind_min" : 0,
	    "solar_min" : 0,
	    "wind_max" : 1e7,
	    "solar_max" : 1e7,
	    "wind_discount" : 5,
	    "solar_discount" : 5,
	    "battery_energy_discount" : 5,
	    "battery_power_discount" : 5,
	    "hydrogen_energy_discount" : 5,
	    "hydrogen_electrolyser_discount" : 5,
	    "hydrogen_turbine_discount" : 5,
	    "dispatchable1_discount" : 10,
	    "dispatchable2_discount" : 10,
	    "co2_emissions" : 100,
	    "wind" : True,
	    "solar" : True,
	    "battery" : True,
	    "hydrogen" : True,
	    "dispatchable1" : False,
	    "dispatchable2" : False,
	    "co2_limit" : False,
	   };



defaults["job_type"] = "solve"

for cf_exponent in cf_exponents:
    for year in years:
        for location in locations:
            print(year,cf_exponent,location)
            assumptions_base = defaults.copy()
            assumptions_base["year"] = year
            assumptions_base["cf_exponent"] = cf_exponent
            assumptions_base["location"] = location
            if location[:len("country:")] == "country:":
                assumptions_base["location_name"] = country_names[location[len("country:"):]]
            elif location[:len("region:")] == "region:":
                assumptions_base["location_name"] = location[len("region:"):]
            else:
                assumptions_base["location_name"] = "None"
            assumptions_base["weather_hex"] =  compute_weather_hash(assumptions_base)
            weather_csv = 'data/time-series-{}.csv'.format(assumptions_base["weather_hex"])
            pu = pd.read_csv(weather_csv,
                             index_col=0,
                             parse_dates=True)
            snapshots = pd.date_range("{}-01-01".format(year),"{}-12-31 23:00".format(year),freq="H")
            pu = pu.reindex(snapshots,method="nearest")

            for assumption_year in assumption_years:
                assumptions = assumptions_base.copy()
                assumptions.update(tech_assumptions[str(assumption_year)])

                error_message, assumptions = sanitise_assumptions(assumptions)
                if error_message is not None:
                    print(error_message)
                    sys.exit()

                assumptions['results_hex'] = compute_results_hash(assumptions)
                print(assumptions['results_hex'])
                series_csv = 'data/results-series-{}.csv'.format(assumptions['results_hex'])
                overview_csv = 'data/results-overview-{}.csv'.format(assumptions['results_hex'])

                print("Calculating results from scratch, saving as:", series_csv, overview_csv)
                results_overview, results_series, error_msg = solve.run_optimisation(assumptions, pu)
                print(error_msg)
                results_series = results_series.round(1)
                results_series.to_csv(series_csv)
                results_overview.to_csv(overview_csv,header=False)

                with open('data/results-assumptions-{}.json'.format(assumptions['results_hex']), 'w') as fp:
                    json.dump(assumptions,fp)
