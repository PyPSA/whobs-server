
import os, json, hashlib

from server import sanitise_assumptions

ass_dir = "assumptions/"

booleans = ["wind","solar","battery","hydrogen","dispatchable1","dispatchable2","co2_limit"]

floats = ["cf_exponent","load","hydrogen_load","wind_cost","solar_cost","battery_energy_cost",
          "battery_power_cost","hydrogen_electrolyser_cost",
          "hydrogen_energy_cost",
          "hydrogen_electrolyser_efficiency",
          "hydrogen_turbine_cost",
          "hydrogen_turbine_efficiency",
          "discount_rate",
          "dispatchable1_cost",
          "dispatchable1_marginal_cost",
          "dispatchable1_emissions",
          "dispatchable1_discount",
          "dispatchable2_cost",
          "dispatchable2_marginal_cost",
          "dispatchable2_emissions",
          "dispatchable2_discount",
          "co2_emissions"]

ints = ["year","frequency","version"]

strings = ["location"]


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
                    "year" : 2011,
                    "cf_exponent" : 2.,
                    "version" : 0,
                    "discount_rate" : 5.0}
#                    "version" : solve.current_version}


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

base_assumptions.update(tech_assumptions["2030"])


jobids = []

for filename in os.listdir(ass_dir):
    if not (filename[-5:] == ".json" and filename[:12] == "assumptions-"):
        print(filename)
        continue
    else:
        with open(os.path.join(ass_dir,filename),"r") as f:
            assumptions = json.load(f)
        print(assumptions)

        # fill in for e.g. dispatchable1/2
        for key,value in base_assumptions.items():
            if key not in assumptions:
                assumptions[key] = value

        if "country" in assumptions:
            assumptions["location"] = "country:" + assumptions["country"]
        error_message, assumptions = sanitise_assumptions(assumptions)


        if error_message is not None:
            print(error_message)
            continue

        if assumptions["version"] == 0:
            assumptions['weather_hex'] = hashlib.md5("{}&{}&{}".format(assumptions["location"].replace("country:",""), assumptions["year"], assumptions['cf_exponent']).encode()).hexdigest()
        else:
            assumptions['weather_hex'] = hashlib.md5("{}&{}&{}&{}".format(assumptions["location"].replace("country:",""), assumptions["year"], assumptions['cf_exponent'], assumptions["version"]).encode()).hexdigest()

        print(assumptions["weather_hex"])


        weather_csv = 'data/time-series-{}.csv'.format(assumptions['weather_hex'])
        if os.path.isfile(weather_csv):
            with open(os.path.join("data",'weather-assumptions-{}.json'.format(assumptions['weather_hex'])), 'w') as fp:
                json.dump(assumptions,fp)


        results_string = assumptions["location"].replace("country:","")
        for item in ints+booleans+floats:
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

        if os.path.isfile(series_csv) and os.path.isfile(overview_csv):
            with open(os.path.join("data",'results-assumptions-{}.json'.format(assumptions['results_hex'])), 'w') as fp:
                json.dump(assumptions,fp)
