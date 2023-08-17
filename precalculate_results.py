import solve

from server import sanitise_assumptions, compute_weather_hash, compute_results_hash

import hashlib, json, yaml

import pandas as pd

countries = "country:" + pd.Index(solve.get_country_multipolygons().keys())

regions = "region:" + pd.Index(solve.get_region_multipolygons().keys())

locations = countries.append(regions)

country_names = solve.get_country_names()

years = range(2011,2012)

techs = ["solar","onwind"]

cf_exponents = [2.]

assumption_years = [2030]


with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)


#na_filter leaves "" as "" rather than doing nan which confuses jinja2
defaults = pd.read_csv("defaults.csv",index_col=[0,1],na_filter=False)

for (n,t) in [("f",float),("i",int)]:
    defaults.loc[defaults["type"] == n, "value"] = defaults.loc[defaults["type"] == n,"value"].astype(t)

#work around fact bool("False") returns True
defaults.loc[defaults.type == "b","value"] = (defaults.loc[defaults.type == "b","value"] == "True")

defaults_t = {str(year): defaults.swaplevel().loc[str(year)]["value"].to_dict() for year in config["tech_years"]}
defaults = defaults.swaplevel().loc[""]["value"].to_dict()

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
                assumptions.update(defaults_t[str(assumption_year)])

                error_message, assumptions = sanitise_assumptions(assumptions)
                if error_message is not None:
                    print(error_message)
                    sys.exit()

                assumptions['results_hex'] = compute_results_hash(assumptions)
                print(assumptions['results_hex'])

                print("Calculating results from scratch, saving with hex",assumptions['results_hex'])
                error_msg = solve.run_optimisation(assumptions, pu)
                print(error_msg)

                with open('data/results-assumptions-{}.json'.format(assumptions['results_hex']), 'w') as fp:
                    json.dump(assumptions,fp)
