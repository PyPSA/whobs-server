import pandas as pd, urllib.request, os, yaml

df = pd.read_csv("defaults-initial.csv",
                 index_col=[0,1],
                 na_filter=False)

with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)


years = config["tech_years"]


df.at[("year",""),"text"] = df.at[("year",""),"text"].replace("weather_years",str(config["weather_years"])[1:-1])


#get technology data
td = {}
for year in years:

    fn = f"costs_{year}.csv"
    url = f"https://raw.githubusercontent.com/PyPSA/technology-data/{config['tech_data_commit']}/outputs/{fn}"

    if not os.path.isfile(fn):
        print("downloading",fn)
        urllib.request.urlretrieve(url,fn)

    td[year] = pd.read_csv(fn,
                           index_col=[0,1])


#get traces efficiencies

fn = "efficiencies.csv"
url = f"https://raw.githubusercontent.com/euronion/trace/{config['trace_commit']}/data/{fn}"
if not os.path.isfile(fn):
    print("downloading",fn)
    urllib.request.urlretrieve(url,fn)

eff = pd.read_csv(fn,
                  index_col=[0,1,2])


for name,td_name,full_name in [("wind","onwind","Onshore wind turbine"),
                               ("solar","solar-utility","Utility-scale solar PV"),
                               ("hydrogen_electrolyser","electrolysis","Hydrogen electrolyser"),
                               ("desalination","seawater desalination","Seawater desalination"),
                               ("hydrogen_energy","hydrogen storage underground","Hydrogen underground salt cavern storage"),
                               ("hydrogen_turbine","CCGT","Hydrogen combined cycle turbine"),
                               ("battery_energy","battery storage","Utility-scale battery energy"),
                               ("battery_power","battery inverter","Utility-scale battery converter power"),
                               ("hydrogen_compressor","hydrogen storage compressor","Hydrogen storage compressor")]:
    print(name,full_name)
    df.loc[(name + "_discount",""),:] = ["f",5,"percent",full_name + " discount rate",""]
    for year in years:
        value = td[year].loc[(td_name,"investment"),"value"]
        unit = td[year].loc[(td_name,"investment"),"unit"]

        df.loc[(name + "_cost",str(year)),:] = ["f",
                                                value,
                                                unit,
                                                full_name + " capital cost (overnight)",
                                                td[year].loc[(td_name,"investment"),"source"]]
        df.loc[(name + "_fom",str(year)),:] = ["f",
                                               td[year].loc[(td_name,"FOM"),"value"] if (td_name,"FOM") in td[year].index else 0,
                                               "percent of overnight cost per year",
                                               full_name + " fixed operation and maintenance costs",
                                               td[year].loc[(td_name,"FOM"),"source"] if (td_name,"FOM") in td[year].index else "default"]
        df.loc[(name + "_lifetime",str(year)),:] = ["f",
                                                    td[year].loc[(td_name,"lifetime"),"value"],
                                                    td[year].loc[(td_name,"lifetime"),"unit"],
                                                    full_name + " lifetime",
                                                    td[year].loc[(td_name,"lifetime"),"source"]]


for name,td_name,full_name in [("battery_power_efficiency_charging","battery inverter","Battery power charging efficiency"),
                               ("battery_power_efficiency_discharging","battery inverter","Battery power discharging efficiency"),
                               ("hydrogen_electrolyser_efficiency","electrolysis","Hydrogen electrolyser efficiency"),
                               ("hydrogen_turbine_efficiency","CCGT","Hydrogen combined cycle turbine efficiency")]:

    for year in years:
        value = 100*td[year].loc[(td_name,"efficiency"),"value"]
        unit = "percent"
        if "battery" in name:
            value = 100*((value/100.)**0.5)
        elif "hydrogen" in name:
            unit ='"percent, LHV"'

        df.loc[(name,str(year)),:] = ["f",
                                      value,
                                      unit,
                                      full_name,
                                      td[year].loc[(td_name,"efficiency"),"source"]]


df.loc[("hydrogen_electrolyser_water",""),:] = ["f",
                                                eff.loc[("electrolysis","all","water"),"from_amount"][0]/eff.loc[("electrolysis","all","water"),"to_amount"][0],
                                                "m3-H2O/MWh-H2-LHV",
                                                "Hydrogen electrolyser water input",
                                                eff.loc[("electrolysis","all","water"),"source"][0]]


df.loc[("desalination_electricity",""),:] = ["f",
                                             eff.loc[("seawater desalination","all","electricity"),"from_amount"][0]/eff.loc[("seawater desalination","all","electricity"),"to_amount"][0],
                                             "MWh-el/m3-H2O",
                                             "Seawater desalination electricity input",
                                             eff.loc[("seawater desalination","all","electricity"),"source"][0]]


df.loc[("hydrogen_compressor_electricity",""),:] = ["f",
                                                    eff.loc[("H2 storage compressor","all","electricity"),"from_amount"][0]/eff.loc[("H2 storage compressor","all","electricity"),"to_amount"][0],
                                                    "MWhel/MWh-H2-LHV",
                                                    "Hydrogen storage compressor electricity input",
                                                    eff.loc[("H2 storage compressor","all","electricity"),"source"][0]]



print(df)



cost_df = df.index[df.index.get_level_values(0).str.contains("cost") & (~df.index.get_level_values(0).str.contains("marginal_cost")) & (~df.index.get_level_values(0).str.contains("co2_cost"))]

inflation_factor = (1 + config["inflation"]/100)**(config["cost_year"] - config["cost_year_assumptions"])

print("inflation factor",inflation_factor)

df.loc[cost_df,"value"] = (inflation_factor*df.loc[cost_df,"value"].astype(float)).round(1)

df.to_csv("defaults.csv")
