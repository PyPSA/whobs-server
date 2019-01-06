
import pypsa

import pandas as pd
from pyomo.environ import Constraint
from rq import get_current_job

import json



idx = pd.IndexSlice



#read in renewables.ninja solar time series
solar_pu = pd.read_csv('ninja_pv_europe_v1.1_sarah.csv',
                       index_col=0,parse_dates=True)

#read in renewables.ninja wind time series
wind_pu = pd.read_csv('ninja_wind_europe_v1.1_current_on-offshore.csv',
                       index_col=0,parse_dates=True)

colors = {"wind":"#3B6182",
          "solar" :"#FFFF00",
          "battery" : "#999999",
          "battery_power" : "#999999",
          "battery_energy" : "#666666",
          "hydrogen_turbine" : "red",
          "hydrogen_electrolyser" : "cyan",
          "hydrogen_energy" : "magenta",
}

def annuity(lifetime,rate):
    if rate == 0.:
        return 1/lifetime
    else:
        return rate/(1. - 1. / (1. + rate)**lifetime)


assumptions_df = pd.DataFrame(columns=["FOM","fixed","discount rate","lifetime","investment","efficiency"],
                              index=["wind","solar","hydrogen_electrolyser","hydrogen_turbine","hydrogen_energy",
                                     "battery_power","battery_energy"],
                              dtype=float)

assumptions_df["lifetime"] = 25.
assumptions_df.at["hydrogen_electrolyser","lifetime"] = 20.
assumptions_df.at["battery_power","lifetime"] = 15.
assumptions_df.at["battery_energy","lifetime"] = 15.
assumptions_df["discount rate"] = 0.05
assumptions_df["FOM"] = 3.
assumptions_df["efficiency"] = 1.
assumptions_df.at["battery_power","efficiency"] = 0.9

booleans = ["wind","solar","battery","hydrogen"]

floats = ["wind_cost","solar_cost","battery_energy_cost",
          "battery_power_cost","hydrogen_electrolyser_cost",
          "hydrogen_energy_cost",
          "hydrogen_electrolyser_efficiency",
          "hydrogen_turbine_cost",
          "hydrogen_turbine_efficiency",
          "discount_rate"]

threshold = 0.1

def solve(assumptions):

    job = get_current_job()
    job.meta['status'] = "Reading in data"
    job.save_meta()


    for key in booleans:
        try:
            assumptions[key] = bool(assumptions[key])
        except:
            job.meta['status'] = "Error"
            job.save_meta()
            return {"error" : "{} could not be converted to boolean".format(key)}

    for key in floats:
        try:
            assumptions[key] = float(assumptions[key])
        except:
            job.meta['status'] = "Error"
            job.save_meta()
            return {"error" : "{} could not be converted to float".format(key)}

    print(assumptions)
    ct = assumptions['country']
    if ct not in solar_pu.columns:
        job.meta['status'] = "Error"
        job.save_meta()
        return {"error" : "Country {} not found among valid countries".format(ct)}

    try:
        year = int(assumptions['year'])
    except:
        job.meta['status'] = "Error"
        job.save_meta()
        return {"error" : "Year {} could not be converted to an integer".format(assumptions['year'])}

    if year < 1985 or year > 2015:
        job.meta['status'] = "Error"
        job.save_meta()
        return {"error" : "Year {} not in valid range".format(year)}

    year_start = year
    year_end = year

    Nyears = year_end - year_start + 1

    try:
        load = float(assumptions['load'])
    except:
        job.meta['status'] = "Error"
        job.save_meta()
        return {"error" : "Load {} could not be converted to a float".format(assumptions["load"])}

    try:
        frequency = int(assumptions['frequency'])
    except:
        job.meta['status'] = "Error"
        job.save_meta()
        return {"error" : "Frequency {} could not be converted to an int".format(assumptions["frequency"])}

    if frequency < 3:
        job.meta['status'] = "Error"
        job.save_meta()
        return {"error" : "Frequencies below 3 cannot be supported due to limited computation resources".format(frequency)}
    elif  frequency > 8760:
        job.meta['status'] = "Error"
        job.save_meta()
        return {"error" : "Frequency {} not in valid range".format(frequency)}


    assumptions_df["discount rate"] = assumptions["discount_rate"]/100.

    for item in ["wind","solar","battery_energy","battery_power","hydrogen_electrolyser","hydrogen_energy","hydrogen_turbine"]:
        assumptions_df.at[item,"investment"] = assumptions[item + "_cost"]

    for item in ["hydrogen_electrolyser","hydrogen_turbine"]:
        assumptions_df.at[item,"efficiency"] = assumptions[item + "_efficiency"]/100.


    #convert costs from per kW to per MW
    assumptions_df["investment"] *= 1000.
    assumptions_df["fixed"] = [(annuity(v["lifetime"],v["discount rate"])+v["FOM"]/100.)*v["investment"]*Nyears for i,v in assumptions_df.iterrows()]

    print('Starting task for {} with assumptions {}'.format(ct,assumptions_df))

    network = pypsa.Network()

    snapshots = pd.date_range("{}-01-01".format(year_start),"{}-12-31 23:00".format(year_end),
                              freq=str(frequency)+"H")

    network.set_snapshots(snapshots)

    network.snapshot_weightings = pd.Series(float(frequency),index=network.snapshots)

    network.add("Bus",ct)
    network.add("Load",ct,
                bus=ct,
                p_set=load)

    if assumptions["solar"]:
        network.add("Generator",ct+" solar",
                    bus=ct,
                    p_max_pu = solar_pu[ct],
                    p_nom_extendable = True,
                    marginal_cost = 0.1, #Small cost to prefer curtailment to destroying energy in storage, solar curtails before wind
                    capital_cost = assumptions_df.at['solar','fixed'])

    if assumptions["wind"]:
        network.add("Generator",ct+" wind",
                    bus=ct,
                    p_max_pu = wind_pu[ct+"_ON"],
                    p_nom_extendable = True,
                    marginal_cost = 0.2, #Small cost to prefer curtailment to destroying energy in storage, solar curtails before wind
                    capital_cost = assumptions_df.at['wind','fixed'])


    if assumptions["battery"]:

        network.add("Bus",ct + " battery")

        network.add("Store",ct + " battery_energy",
                    bus = ct + " battery",
                    e_nom_extendable = True,
                    e_cyclic=True,
                    capital_cost=assumptions_df.at['battery_energy','fixed'])

        network.add("Link",ct + " battery_power",
                    bus0 = ct,
                    bus1 = ct + " battery",
                    efficiency = assumptions_df.at['battery_power','efficiency'],
                    p_nom_extendable = True,
                    capital_cost=assumptions_df.at['battery_power','fixed'])

        network.add("Link",ct + " battery_discharge",
                    bus0 = ct + " battery",
                    bus1 = ct,
                    p_nom_extendable = True,
                    efficiency = assumptions_df.at['battery_power','efficiency'])

        def extra_functionality(network,snapshots):
            def battery(model):
                return model.link_p_nom[ct + " battery_power"] == model.link_p_nom[ct + " battery_discharge"]*network.links.at[ct + " battery_power","efficiency"]

            network.model.battery = Constraint(rule=battery)
    else:
        def extra_functionality(network,snapshots):
            pass

    if assumptions["hydrogen"]:

        network.add("Bus",
                     ct + " hydrogen",
                     carrier="hydrogen")

        network.add("Link",
                    ct + " hydrogen_electrolyser",
                    bus1=ct + " hydrogen",
                    bus0=ct,
                    p_nom_extendable=True,
                    efficiency=assumptions_df.at["hydrogen_electrolyser","efficiency"],
                    capital_cost=assumptions_df.at["hydrogen_electrolyser","fixed"])

        network.add("Link",
                     ct + " hydrogen_turbine",
                     bus0=ct + " hydrogen",
                     bus1=ct,
                     p_nom_extendable=True,
                     efficiency=assumptions_df.at["hydrogen_turbine","efficiency"],
                     capital_cost=assumptions_df.at["hydrogen_turbine","fixed"]*assumptions_df.at["hydrogen_turbine","efficiency"])  #NB: fixed cost is per MWel

        network.add("Store",
                     ct + " hydrogen_energy",
                     bus=ct + " hydrogen",
                     e_nom_extendable=True,
                     e_cyclic=True,
                     capital_cost=assumptions_df.at["hydrogen_energy","fixed"])

    network.consistency_check()

    job.meta['status'] = "Solving optimisation problem"
    job.save_meta()

    solver_name = "cbc"
    formulation = "kirchhoff"
    status, termination_condition = network.lopf(solver_name=solver_name,
                                                 formulation=formulation,
                                                 extra_functionality=extra_functionality)

    print(status,termination_condition)

    if status != "ok":
        job.meta['status'] = "Error"
        job.save_meta()
        return {"error" : "Job failed to optimise correctly"}

    if termination_condition == "infeasible":
        job.meta['status'] = "Error"
        job.save_meta()
        return {"error" : "Problem was infeasible"}

    job.meta['status'] = "Finished"
    job.save_meta()

    print(network.generators.p_nom_opt)

    print(network.links.p_nom_opt)
    print(network.stores.e_nom_opt)

    results = {"objective" : network.objective/8760,
               "average_price" : network.buses_t.marginal_price.mean()[ct]}

    year_weight = network.snapshot_weightings.sum()

    power = {}

    vre = ["wind","solar"]

    power["positive"] = pd.DataFrame(index=network.snapshots,columns=vre+["battery","hydrogen_turbine"])
    power["negative"] = pd.DataFrame(index=network.snapshots,columns=["battery","hydrogen_electrolyser"])


    for g in ["wind","solar"]:
        if assumptions[g] and network.generators.p_nom_opt[ct + " " + g] > threshold:
            results[g+"_capacity"] = network.generators.p_nom_opt[ct + " " + g]
            results[g+"_cost"] = (network.generators.p_nom_opt*network.generators.capital_cost)[ct + " " + g]/year_weight
            results[g+"_available"] = network.generators.p_nom_opt[ct + " " + g]*network.generators_t.p_max_pu[ct + " " + g].mean()
            results[g+"_used"] = network.generators_t.p[ct + " " + g].mean()
            results[g+"_curtailment"] =  (results[g+"_available"] - results[g+"_used"])/results[g+"_available"]
            results[g+"_cf_available"] = network.generators_t.p_max_pu[ct + " " + g].mean()
            results[g+"_cf_used"] = results[g+"_used"]/network.generators.p_nom_opt[ct + " " + g]
            power["positive"][g] = network.generators_t.p[ct + " " + g]
        else:
            results[g+"_capacity"] = 0.
            results[g+"_cost"] = 0.
            results[g+"_curtailment"] = 0.
            results[g+"_used"] = 0.
            results[g+"_available"] = 0.
            results[g+"_cf_used"] = 0.
            results[g+"_cf_available"] = 0.
            power["positive"][g] = 0.

    if assumptions["battery"] and network.links.at[ct + " battery_power","p_nom_opt"] > threshold:
        results["battery_power_capacity"] = network.links.at[ct + " battery_power","p_nom_opt"]
        results["battery_power_cost"] = network.links.at[ct + " battery_power","p_nom_opt"]*network.links.at[ct + " battery_power","capital_cost"]/year_weight
        results["battery_energy_capacity"] = network.stores.at[ct + " battery_energy","e_nom_opt"]
        results["battery_energy_cost"] = network.stores.at[ct + " battery_energy","e_nom_opt"]*network.stores.at[ct + " battery_energy","capital_cost"]/year_weight
        results["battery_power_used"] = network.links_t.p0[ct + " battery_discharge"].mean()
        results["battery_power_cf_used"] = results["battery_power_used"]/network.links.at[ct + " battery_power","p_nom_opt"]
        power["positive"]["battery"] = -network.links_t.p1[ct + " battery_discharge"]
        power["negative"]["battery"] = network.links_t.p0[ct + " battery_power"]
    else:
        results["battery_power_capacity"] = 0.
        results["battery_power_cost"] = 0.
        results["battery_energy_capacity"] = 0.
        results["battery_energy_cost"] = 0.
        results["battery_power_used"] = 0.
        results["battery_power_cf_used"] = 0.
        power["positive"]["battery"] = 0.
        power["negative"]["battery"] = 0.

    if assumptions["hydrogen"] and network.links.at[ct + " hydrogen_electrolyser","p_nom_opt"] > threshold and network.links.at[ct + " hydrogen_turbine","p_nom_opt"] > threshold:
        results["hydrogen_electrolyser_capacity"] = network.links.at[ct + " hydrogen_electrolyser","p_nom_opt"]
        results["hydrogen_electrolyser_cost"] = network.links.at[ct + " hydrogen_electrolyser","p_nom_opt"]*network.links.at[ct + " hydrogen_electrolyser","capital_cost"]/year_weight
        results["hydrogen_turbine_capacity"] = network.links.at[ct + " hydrogen_turbine","p_nom_opt"]*network.links.at[ct + " hydrogen_turbine","efficiency"]
        results["hydrogen_turbine_cost"] = network.links.at[ct + " hydrogen_turbine","p_nom_opt"]*network.links.at[ct + " hydrogen_turbine","capital_cost"]/year_weight
        results["hydrogen_energy_capacity"] = network.stores.at[ct + " hydrogen_energy","e_nom_opt"]
        results["hydrogen_energy_cost"] = network.stores.at[ct + " hydrogen_energy","e_nom_opt"]*network.stores.at[ct + " hydrogen_energy","capital_cost"]/year_weight
        results["hydrogen_electrolyser_used"] = network.links_t.p0[ct + " hydrogen_electrolyser"].mean()
        results["hydrogen_electrolyser_cf_used"] = results["hydrogen_electrolyser_used"]/network.links.at[ct + " hydrogen_electrolyser","p_nom_opt"]
        results["hydrogen_turbine_used"] = network.links_t.p0[ct + " hydrogen_turbine"].mean()
        results["hydrogen_turbine_cf_used"] = results["hydrogen_turbine_used"]/network.links.at[ct + " hydrogen_turbine","p_nom_opt"]
        power["positive"]["hydrogen_turbine"] = -network.links_t.p1[ct + " hydrogen_turbine"]
        power["negative"]["hydrogen_electrolyser"] = network.links_t.p0[ct + " hydrogen_electrolyser"]
    else:
        results["hydrogen_electrolyser_capacity"] = 0.
        results["hydrogen_electrolyser_cost"] = 0.
        results["hydrogen_turbine_capacity"] = 0.
        results["hydrogen_turbine_cost"] = 0.
        results["hydrogen_energy_capacity"] = 0.
        results["hydrogen_energy_cost"] = 0.
        results["hydrogen_electrolyser_cf_used"] = 0.
        results["hydrogen_turbine_cf_used"] = 0.
        power["positive"]["hydrogen_turbine"] = 0.
        power["negative"]["hydrogen_electrolyser"] = 0.

    results["assumptions"] = assumptions

    results["average_cost"] = sum([results[s] for s in results if s[-5:] == "_cost"])/load

    results["snapshots"] = [str(s) for s in network.snapshots]

    for sign in ["negative","positive"]:
        results[sign] = {}
        results[sign]["columns"] = list(power[sign].columns)
        results[sign]["data"] = power[sign].values.tolist()
        results[sign]["color"] = [colors[c] for c in power[sign].columns]

    print(power["positive"].head())
    print(power["negative"].head())

    balance = power["positive"].sum(axis=1) - power["negative"].sum(axis=1)

    print(balance.describe())

    #with open('results-{}.json'.format(job.id), 'w') as fp:
    #    json.dump(results,fp)

    return results
