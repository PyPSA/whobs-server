
import pypsa
from six import iteritems
import pandas as pd
from pyomo.environ import Constraint
from rq import get_current_job



idx = pd.IndexSlice

solar_pu = pd.read_csv('ninja_pv_europe_v1.1_sarah.csv',
                       index_col=0,parse_dates=True)


def annuity(lifetime,rate):
    if rate == 0.:
        return 1/lifetime
    else:
        return rate/(1. - 1. / (1. + rate)**lifetime)

countries = ["DE"]

load_shedding = True

add_hydrogen = True

electrolysis_override = 1e6 #None  #None or e.g. 1e6 EUR/MWh

voll = 1e4  # EUR/MWh

load = 1 #MW

year_start = 2011
year_end = 2011

frequency = "43H"

#set all asset costs and other parameters
costs = pd.read_csv("costs.csv",index_col=list(range(3))).sort_index()

#correct units to MW and EUR
costs.loc[costs.unit.str.contains("/kW"),"value"]*=1e3
costs.loc[costs.unit.str.contains("USD"),"value"]*=0.7532

cost_year = 2030

costs = costs.loc[idx[:,cost_year,:],"value"].unstack(level=2).groupby(level="technology").sum(min_count=1)

costs = costs.fillna({"CO2 intensity" : 0,
                          "FOM" : 0,
                          "VOM" : 0,
                          "discount rate" : 0.07,
                          "efficiency" : 1,
                          "fuel" : 0,
                          "investment" : 0,
                          "lifetime" : 25
    })

Nyears = year_end - year_start + 1

if electrolysis_override is not None:
    costs.at["electrolysis","investment"] = electrolysis_override

costs["discount rate"] = 0.

costs["fixed"] = [(annuity(v["lifetime"],v["discount rate"])+v["FOM"]/100.)*v["investment"]*Nyears for i,v in costs.iterrows()]



def solve(ct,wind_cost):
    job = get_current_job()
    job.meta['progress'] = "Reading in data"
    job.save_meta()

    print('Starting task for {} with wind cost {}'.format(ct,wind_cost))

    network = pypsa.Network()

    snapshots = pd.date_range("{}-01-01".format(year_start),"{}-12-31 23:00".format(year_start),freq=frequency)

    network.set_snapshots(snapshots)

    network.add("Bus",ct)
    network.add("Load",ct,
                bus=ct,
                p_set=load)

    network.add("Generator",ct+" solar",
                bus=ct,
                p_max_pu = solar_pu[ct],
                p_nom_extendable = True,
                capital_cost = costs.at['solar-rooftop','fixed'])

    network.add("Bus",ct + " battery")

    network.add("Store",ct + " battery",
                bus = ct + " battery",
                e_nom_extendable = True,
                e_cyclic=True,
                capital_cost=costs.at['battery storage','fixed'])

    network.add("Link",ct + " battery charge",
                bus0 = ct,
                bus1 = ct + " battery",
                efficiency = costs.at['battery inverter','efficiency']**0.5,
                p_nom_extendable = True,
                capital_cost=costs.at['battery inverter','fixed'])

    network.add("Link",ct + " battery discharge",
                bus0 = ct + " battery",
                bus1 = ct,
                p_nom_extendable = True,
                efficiency = costs.at['battery inverter','efficiency']**0.5)

    def extra_functionality(network,snapshots):
        def battery(model):
            return model.link_p_nom[ct + " battery charge"] == model.link_p_nom[ct + " battery discharge"]*network.links.at[ct + " battery charge","efficiency"]

        network.model.battery = Constraint(rule=battery)

    if add_hydrogen:

        network.add("Bus",
                     ct + " H2",
                     carrier="H2")

        network.add("Link",
                    ct + " H2 Electrolysis",
                    bus1=ct + " H2",
                    bus0=ct,
                    p_nom_extendable=True,
                    efficiency=costs.at["electrolysis","efficiency"],
                    capital_cost=costs.at["electrolysis","fixed"])

        network.add("Link",
                     ct + " H2 Fuel Cell",
                     bus0=ct + " H2",
                     bus1=ct,
                     p_nom_extendable=True,
                     efficiency=costs.at["fuel cell","efficiency"],
                     capital_cost=costs.at["fuel cell","fixed"]*costs.at["fuel cell","efficiency"])  #NB: fixed cost is per MWel

        network.add("Store",
                     ct + " H2 Store",
                     bus=ct + " H2",
                     e_nom_extendable=True,
                     e_cyclic=True,
                     capital_cost=costs.at["hydrogen storage","fixed"])

    job.meta['progress'] = "Solving optimisation problem"
    job.save_meta()

    network.lopf(solver_name="gurobi",
                 extra_functionality=extra_functionality)

    print(network.generators.p_nom_opt)

    print(network.links.p_nom_opt)
    print(network.stores.e_nom_opt)

    job.meta['progress'] = "Finished"
    job.save_meta()

    return {"objective" : network.objective/8760,
            "solar_cap" : network.generators.at[ct+" solar","p_nom_opt"]}


if __name__ == '__main__':
    print(solve("FR",1000))
