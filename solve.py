## Copyright 2018-2020 Tom Brown

## This program is free software; you can redistribute it and/or
## modify it under the terms of the GNU Affero General Public License as
## published by the Free Software Foundation; either version 3 of the
## License, or (at your option) any later version.

## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU Affero General Public License for more details.

## License and more information at:
## https://github.com/PyPSA/whobs-server



import pypsa

from pypsa.linopt import get_var, linexpr, define_constraints

import pandas as pd
from pyomo.environ import Constraint
from rq import get_current_job

import json, os, hashlib, yaml

#required to stop wierd failures
import netCDF4

from atlite.gis import spdiag, compute_indicatormatrix

import xarray as xr

import scipy as sp

import numpy as np

from shapely.geometry import box, Point, Polygon, MultiPolygon


with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

defaults = pd.read_csv("defaults.csv",index_col=[0,1],na_filter=False)

current_version = config["current_version"]

octant_folder = config["octant_folder"]

#based on mean deviation against renewables.ninja capacity factors for European countries for 2011-2013
solar_correction_factor = 0.926328


override_component_attrs = pypsa.descriptors.Dict(
        {k: v.copy() for k, v in pypsa.components.component_attrs.items()}
    )
override_component_attrs["Link"].loc["bus2"] = [
        "string",
        np.nan,
        np.nan,
        "2nd bus",
        "Input (optional)",
    ]
override_component_attrs["Link"].loc["bus3"] = [
        "string",
        np.nan,
        np.nan,
        "3rd bus",
        "Input (optional)",
    ]
override_component_attrs["Link"].loc["efficiency2"] = [
        "static or series",
        "per unit",
        1.0,
        "2nd bus efficiency",
        "Input (optional)",
    ]
override_component_attrs["Link"].loc["efficiency3"] = [
        "static or series",
        "per unit",
        1.0,
        "3rd bus efficiency",
        "Input (optional)",
    ]
override_component_attrs["Link"].loc["p2"] = [
        "series",
        "MW",
        0.0,
        "2nd bus output",
        "Output",
    ]
override_component_attrs["Link"].loc["p3"] = [
        "series",
        "MW",
        0.0,
        "3rd bus output",
        "Output",
    ]



def get_country_multipolygons():

    with open('static/ne-countries-110m.json', 'r') as myfile:
        geojson = json.load(myfile)

    def get_multipolygon(feature):
        if feature["geometry"]["type"] == "Polygon":
            polys = [Polygon(feature['geometry']["coordinates"][0])]
        else:
            polys = []

            for p in feature['geometry']["coordinates"]:
                polys.append(Polygon(p[0]))

        return MultiPolygon(polys)

    return {feature["properties"]["iso_a2"] : get_multipolygon(feature) for feature in geojson["features"] if feature["properties"]["iso_a2"] != "-99"}

country_multipolygons = get_country_multipolygons()



def get_country_names():

    with open('static/ne-countries-110m.json', 'r') as myfile:
        geojson = json.load(myfile)

    return {feature["properties"]["iso_a2"] : feature["properties"]["name"] for feature in geojson["features"] if feature["properties"]["iso_a2"] != "-99"}


def get_region_multipolygons():

    with open('static/selected_admin1.json', 'r') as myfile:
        geojson = json.load(myfile)

    def get_multipolygon(feature):
        if feature["geometry"]["type"] == "Polygon":
            polys = [Polygon(feature['geometry']["coordinates"][0])]
        else:
            polys = []

            for p in feature['geometry']["coordinates"]:
                polys.append(Polygon(p[0]))

        return MultiPolygon(polys)

    return {feature["properties"]["name"] : get_multipolygon(feature) for feature in geojson["features"]}

region_multipolygons = get_region_multipolygons()


def annuity(lifetime,rate):
    if rate == 0.:
        return 1/lifetime
    else:
        return rate/(1. - 1. / (1. + rate)**lifetime)


assumptions_df = pd.DataFrame(columns=["FOM","fixed","discount rate","lifetime","investment"],
                              dtype=float)

threshold = 0.1

def error(message, jobid):
    with open('results-solve/results-{}.json'.format(jobid), 'w') as fp:
        json.dump({"jobid" : jobid,
                   "status" : "Error",
                   "error" : message
                   },fp)
    print("Error: {}".format(message))
    return {"error" : message}

def find_interval(interval_start,interval_length,value):
    return int((value-interval_start)//interval_length)


def get_octant_bounds(quadrant, hemisphere):

    x0 = -180 + quadrant*90.
    x1 = x0 + 90.

    y0 = -90. + hemisphere*90.
    y1 = y0 + 90.

    return x0,x1,y0,y1

def generate_octant_grid_cells(quadrant, hemisphere, mesh=0.5):

    x0,x1,y0,y1 = get_octant_bounds(quadrant, hemisphere)

    x = np.arange(x0,
                  x1 + mesh,
                  mesh)

    y = np.arange(y0,
                  y1 + mesh,
                  mesh)

    #grid_coordinates and grid_cells copied from atlite/cutout.py
    xs, ys = np.meshgrid(x,y)
    grid_coordinates = np.asarray((np.ravel(xs), np.ravel(ys))).T

    span = mesh / 2
    return [box(*c) for c in np.hstack((grid_coordinates - span, grid_coordinates + span))]


def get_octant(lon,lat):

    # 0 for lon -180--90, 1 for lon -90-0, etc.
    quadrant = find_interval(-180.,90,lon)

    #0 for lat -90 - 0, 1 for lat 0 - 90
    hemisphere = find_interval(-90,90,lat)

    print(f"octant is in quadrant {quadrant} and hemisphere {hemisphere}")

    rel_x = lon - quadrant*90 + 180.

    rel_y = lat - hemisphere*90 + 90.

    span = 0.5

    n_per_octant = int(90/span +1)

    i = find_interval(0-span/2,span,rel_x)
    j = find_interval(0-span/2,span,rel_y)

    position = j*n_per_octant+i

    print("position",position)

    #paranoid check
    if True:
        grid_cells = generate_octant_grid_cells(quadrant, hemisphere, mesh=span)
        assert grid_cells[position].contains(Point(lon,lat))

    return quadrant, hemisphere, position

def process_point(ct,year):
    """Return error_msg, solar_pu, wind_pu
    error_msg: string
    solar/wind_pu: pandas.Series
    """

    try:
        lon,lat = ct[6:].split(",")
    except:
        return "Error reading point's coordinates", None, None

    try:
        lon = float(lon)
    except:
        return "Error turning point's longitude into float", None, None

    try:
        lat = float(lat)
    except:
        return "Error turning point's latitude into float", None, None

    if lon < -180 or lon > 180 or lat > 90 or lat < -90:
        return "Point's coordinates not within lon*lat range of (-180,180)*(-90,90)", None, None

    quadrant, hemisphere, position = get_octant(lon,lat)

    pu = {}

    for tech in ["solar", "onwind"]:
        filename = os.path.join(octant_folder,
                                f"octant-{year}-{quadrant}-{hemisphere}-{tech}.nc")
        o = xr.open_dataarray(filename)
        pu[tech] = o.loc[{"dim_0":position}].to_pandas()

    return None, pd.DataFrame(pu)


def process_shapely_polygon(polygon,year,cf_exponent):
    """Return error_msg, solar_pu, wind_pu
    error_msg: string
    solar/wind_pu: pandas.Series
    """

    #minimum bounding region (minx, miny, maxx, maxy)
    bounds = polygon.bounds
    if bounds[0] < -180 or bounds[2] > 180 or bounds[3] > 90 or bounds[1] < -90:
        return "Polygon's coordinates not within lon*lat range of (-180,180)*(-90,90)", None, None

    techs = ["onwind","solar"]

    final_result = pd.DataFrame(0.,
                                columns=techs,
                                index=pd.date_range(f'{year}-01-01', f'{year}-12-31', freq='1H', inclusive="left"))

    matrix_sum = { tech : 0. for tech in techs}

    #range over octants
    for quadrant in range(4):
        for hemisphere in range(2):

            x0,x1,y0,y1 = get_octant_bounds(quadrant, hemisphere)

            if bounds[0] > x1 or bounds[1] > y1 or bounds[2] < x0 or bounds[3] < y0:
                print(f"Skipping octant {quadrant}, {hemisphere} since it is out of bounds")
                continue

            print(f"Computing transfer matrix with octant {quadrant}, {hemisphere}")

            grid_cells = generate_octant_grid_cells(quadrant, hemisphere, mesh=0.5)

            matrix = compute_indicatormatrix(grid_cells,[polygon])

            matrix = sp.sparse.csr_matrix(matrix)

            for tech in techs:

                da = xr.open_dataarray(os.path.join(octant_folder, f"octant-{year}-{quadrant}-{hemisphere}-{tech}.nc"))
                if da.isnull().any():
                    print(tech,"has some NaN values:")
                    print(da.where(da.isnull(),drop=True))
                    print("filling with zero")
                    da = da.fillna(0.)

                #precalculated for speed
                means = xr.open_dataarray(os.path.join(octant_folder, f"octant-{year}-{quadrant}-{hemisphere}-{tech}-mean.nc"))
                #means = da.mean(dim="time")

                layout = means**cf_exponent

                tech_matrix = matrix.dot(spdiag(layout))

                result = tech_matrix*da.T

                final_result[tech] += pd.Series(result[0],
                                                index=da.coords["time"].to_pandas())

                matrix_sum[tech] += tech_matrix.sum(axis=1)[0,0]

    for tech in techs:
        print("Matrix sum for {}: {}".format(tech,matrix_sum[tech]))
        final_result[tech] = final_result[tech]/matrix_sum[tech]



    return None, final_result, matrix_sum



def process_polygon(ct,year,cf_exponent):
    """Return error_msg, solar_pu, wind_pu
    error_msg: string
    solar/wind_pu: pandas.Series
    """

    try:
        coords_string = ct[8:].split(";")
    except:
        return "Error parsing polygon coordinates", None, None

    coords = []
    for lonlat_string in coords_string:
        if lonlat_string == "":
            continue
        try:
            coords.append([float(item) for item in lonlat_string.split(",")])
        except:
            return "Error parsing polygon coordinates", None, None

    print("Polygon coordinates:",coords)

    try:
        polygon = Polygon(coords)
    except:
        return "Error creating polygon", None, None

    return process_shapely_polygon(polygon,year,cf_exponent)

def get_weather(ct, year, cf_exponent):

    if ct[:8] == "country:" and ct[8:] in country_multipolygons:
        error_msg, pu, matrix_sum = process_shapely_polygon(country_multipolygons[ct[8:]], year, cf_exponent)
    elif ct[:7] == "region:" and ct[7:] in region_multipolygons:
        error_msg, pu, matrix_sum = process_shapely_polygon(region_multipolygons[ct[7:]], year, cf_exponent)
    elif ct[:6] == "point:":
        error_msg, pu = process_point(ct,year)
        matrix_sum = None
    elif ct[:8] == "polygon:":
        error_msg, pu, matrix_sum = process_polygon(ct, year, cf_exponent)
    else:
        error_msg = "Location {} is not valid".format(ct)
        pu = None
        matrix_sum = None

    if pu is not None:
        pu["solar"] = solar_correction_factor*pu["solar"]

    return pu, matrix_sum, error_msg



def export_time_series(n):

    bus_carriers = n.buses.carrier.unique()

    all_carrier_dict = {}

    for i in bus_carriers:
        bus_map = (n.buses.carrier == i)
        bus_map.at[""] = False

        carrier_df = pd.DataFrame(index=n.snapshots,
                                  dtype=float)

        for c in n.iterate_components(n.one_port_components):

            items = c.df.index[c.df.bus.map(bus_map).fillna(False)]

            if len(items) == 0:
                continue

            s = c.pnl.p[items].multiply(c.df.loc[items,'sign'],axis=1).groupby(c.df.loc[items,'carrier'],axis=1).sum()
            carrier_df = pd.concat([carrier_df,s],axis=1)

        for c in n.iterate_components(n.branch_components):

            for end in [col[3:] for col in c.df.columns if col[:3] == "bus"]:

                print(end)
                print(bus_map)
                print(c.df["bus" + str(end)].map(bus_map,na_action=False))

                items = c.df.index[c.df["bus" + str(end)].map(bus_map,na_action=False)]

                if len(items) == 0:
                    continue

                s = (-1)*c.pnl["p"+end][items].groupby(c.df.loc[items,'carrier'],axis=1).sum()
                carrier_df = pd.concat([carrier_df,s],axis=1)

        all_carrier_dict[i] = carrier_df

    all_carrier_df = pd.concat(all_carrier_dict, axis=1)

    return all_carrier_df




def run_optimisation(assumptions, pu):
    """Needs cleaned-up assumptions and pu.
    return results_overview, results_series, error_msg"""


    Nyears = 1

    techs = [tech[:-5] for tech in assumptions if tech[-5:] == "_cost" and tech[-14:] != "_marginal_cost" and tech != "co2_cost"]

    print("calculating costs for",techs)


    for item in techs:
        assumptions_df.at[item,"discount rate"] = assumptions[item + "_discount"]/100.
        assumptions_df.at[item,"investment"] = assumptions[item + "_cost"]*1e3 if "EUR/kW" in defaults.loc[item + "_cost"]["unit"][0] else assumptions[item + "_cost"]
        assumptions_df.at[item,"FOM"] = assumptions[item + "_fom"]
        assumptions_df.at[item,"lifetime"] = assumptions[item + "_lifetime"]

    assumptions_df["fixed"] = [(annuity(v["lifetime"],v["discount rate"])+v["FOM"]/100.)*v["investment"]*Nyears for i,v in assumptions_df.iterrows()]

    print('Starting task for {} with assumptions {}'.format(assumptions["location"],assumptions_df))

    network = pypsa.Network(override_component_attrs=override_component_attrs)

    snapshots = pd.date_range("{}-01-01".format(assumptions["year"]),"{}-12-31 23:00".format(assumptions["year"]),
                              freq=str(assumptions["frequency"])+"H")

    network.set_snapshots(snapshots)

    network.snapshot_weightings = pd.Series(float(assumptions["frequency"]),index=network.snapshots)

    network.add("Bus","electricity",
                carrier="electricity")
    network.add("Load","load",
                bus="electricity",
                carrier="load",
                p_set=assumptions["load"])

    if assumptions["solar"]:
        network.add("Generator","solar",
                    bus="electricity",
                    carrier="solar",
                    p_max_pu = pu["solar"],
                    p_nom_extendable = True,
                    p_nom_min = assumptions["solar_min"],
                    p_nom_max = assumptions["solar_max"],
                    marginal_cost = 0.1, #Small cost to prefer curtailment to destroying energy in storage, solar curtails before wind
                    capital_cost = assumptions_df.at['solar','fixed'])

    if assumptions["wind"]:
        network.add("Generator","wind",
                    bus="electricity",
                    carrier="wind",
                    p_max_pu = pu["onwind"],
                    p_nom_extendable = True,
                    p_nom_min = assumptions["wind_min"],
                    p_nom_max = assumptions["wind_max"],
                    marginal_cost = 0.2, #Small cost to prefer curtailment to destroying energy in storage, solar curtails before wind
                    capital_cost = assumptions_df.at['wind','fixed'])

    for i in range(1,3):
        name = "dispatchable" + str(i)
        if assumptions[name]:
            network.add("Carrier",name,
                        co2_emissions=assumptions[name+"_emissions"])
            network.add("Generator",name,
                        bus="electricity",
                        carrier=name,
                        p_nom_extendable=True,
                        marginal_cost=assumptions[name+"_marginal_cost"],
                        capital_cost=assumptions_df.at[name,'fixed'])

    if assumptions["battery"]:

        network.add("Bus","battery",
                    carrier="battery")

        network.add("Store","battery_energy",
                    bus = "battery",
                    carrier="battery storage",
                    e_nom_extendable = True,
                    e_cyclic=True,
                    capital_cost=assumptions_df.at['battery_energy','fixed'])

        network.add("Link","battery_power",
                    bus0 = "electricity",
                    bus1 = "battery",
                    carrier="battery inverter",
                    efficiency = assumptions["battery_power_efficiency_charging"]/100.,
                    p_nom_extendable = True,
                    capital_cost=assumptions_df.at['battery_power','fixed'])

        network.add("Link","battery_discharge",
                    bus0 = "battery",
                    bus1 = "electricity",
                    carrier="battery discharger",
                    p_nom_extendable = True,
                    efficiency = assumptions["battery_power_efficiency_discharging"]/100.)

        def extra_functionality(network,snapshots):

            link_p_nom = get_var(network, "Link", "p_nom")

            lhs = linexpr((1,link_p_nom["battery_power"]),
                          (-network.links.loc["battery_discharge", "efficiency"],
                           link_p_nom["battery_discharge"]))
            define_constraints(network, lhs, "=", 0, 'Link', 'charger_ratio')
    else:
        def extra_functionality(network,snapshots):
            pass

    network.add("Bus",
                "hydrogen",
                carrier="hydrogen")

    network.add("Load","hydrogen_load",
                bus="hydrogen",
                carrier="hydrogen",
                p_set=assumptions["hydrogen_load"])

    network.add("Link",
                "hydrogen_electrolyser",
                bus0="electricity",
                bus1="hydrogen",
                carrier="hydrogen electrolyser",
                p_nom_extendable=True,
                efficiency=assumptions["hydrogen_electrolyser_efficiency"]/100.,
                capital_cost=assumptions_df.at["hydrogen_electrolyser","fixed"])

    network.add("Bus",
                "compressed hydrogen",
                carrier="compressed hydrogen")

    network.add("Link",
                "hydrogen_compressor",
                carrier="hydrogen storing compressor",
                bus0="hydrogen",
                bus1="compressed hydrogen",
                bus2="electricity",
                p_nom_extendable=True,
                efficiency=1,
                efficiency2=-assumptions["hydrogen_compressor_electricity"],
                capital_cost=assumptions_df.at["hydrogen_compressor","fixed"])

    network.add("Link",
                "hydrogen_decompressor",
                carrier="hydrogen storing decompressor",
                bus0="compressed hydrogen",
                bus1="hydrogen",
                p_nom_extendable=True)

    network.add("Store",
                "hydrogen_energy",
                bus="compressed hydrogen",
                carrier="hydrogen storage",
                e_nom_extendable=True,
                e_cyclic=True,
                capital_cost=assumptions_df.at["hydrogen_energy","fixed"])


    if assumptions["hydrogen"]:

        network.add("Link",
                     "hydrogen_turbine",
                     bus0="hydrogen",
                     bus1="electricity",
                     carrier="hydrogen turbine",
                     p_nom_extendable=True,
                     efficiency=assumptions["hydrogen_turbine_efficiency"]/100.,
                     capital_cost=assumptions_df.at["hydrogen_turbine","fixed"]*assumptions["hydrogen_turbine_efficiency"]/100.)  #NB: fixed cost is per MWel

    if assumptions["methanol"]:

        network.add("Bus",
                    "co2",
                    carrier="co2")

        network.add("Bus",
                    "heat",
                    carrier="heat")

        network.add("Link",
                    "heat pump",
                    bus0="electricity",
                    bus1="heat",
                    carrier="heat pump",
                    p_nom_extendable=True,
                    capital_cost=assumptions_df.at["heat_pump","fixed"]*assumptions["heat_pump_efficiency"]/100.,
                    efficiency=assumptions["heat_pump_efficiency"]/100.)

        network.add("Link",
                    "dac",
                    bus0="electricity",
                    bus1="co2",
                    bus2="heat",
                    carrier="dac",
                    p_nom_extendable=True,
                    capital_cost=assumptions_df.at["dac","fixed"]/assumptions["dac_electricity"],
                    efficiency=1/assumptions["dac_electricity"],
                    efficiency2=-assumptions["dac_heat"]/assumptions["dac_electricity"])

        network.add("Store",
                    "co2",
                    bus="co2",
                    carrier="co2 storage",
                    e_nom_extendable=True,
                    e_cyclic=True,
                    capital_cost=assumptions_df.at["co2_storage","fixed"])

        network.add("Bus",
                     "methanol",
                     carrier="methanol")

        network.add("Store",
                    "methanol",
                    bus="methanol",
                    carrier="methanol storage",
                    e_nom_extendable=True,
                    e_cyclic=True,
                    capital_cost=assumptions_df.at["liquid_carbonaceous_storage","fixed"]/config["mwh_per_m3"]["methanol"])

        network.add("Link",
                    "methanol synthesis",
                    bus0="hydrogen",
                    bus1="methanol",
                    bus2="electricity",
                    bus3="co2",
                    carrier="methanol synthesis",
                    p_nom_extendable=True,
                    p_min_pu=assumptions["methanolisation_min_part_load"]/100,
                    efficiency=assumptions["methanolisation_efficiency"],
                    efficiency2=-assumptions["methanolisation_electricity"]*assumptions["methanolisation_efficiency"],
                    efficiency3=-assumptions["methanolisation_co2"]*assumptions["methanolisation_efficiency"],
                    capital_cost=assumptions_df.at["methanolisation","fixed"]*assumptions["methanolisation_efficiency"]) #NB: cost is EUR/kW_MeOH

        network.add("Link",
                    "Allam",
                    bus0="methanol",
                    bus1="electricity",
                    bus2="co2",
                    carrier="Allam cycle",
                    p_nom_extendable=True,
                    efficiency=0.6,
                    efficiency2=assumptions["methanolisation_co2"]*0.98,
                    capital_cost=assumptions_df.at["hydrogen_turbine","fixed"]*2*0.6)


    if assumptions["co2_limit"]:
        network.add("GlobalConstraint","co2_limit",
                    sense="<=",
                    constant=assumptions["co2_emissions"]*assumptions["load"]*network.snapshot_weightings.objective.sum())

    network.consistency_check()

    solver_name = "cbc"
    solver_options = {}
    #solver_name = "gurobi"
    #solver_options = {"method": 2, # barrier
    #                  "crossover": 0}
                      #"BarConvTol": 1.e-5,
                      #"AggFill": 0,
                      #"PreDual": 0,
                      #"GURO_PAR_BARDENSETHRESH": 200}

    formulation = "kirchhoff"
    status, termination_condition = network.lopf(pyomo=False,
                                                 solver_name=solver_name,
                                                 solver_options=solver_options,
                                                 formulation=formulation,
                                                 extra_functionality=extra_functionality)

    print(status,termination_condition)

    if termination_condition in ["infeasible","infeasible or unbounded"]:
        return None, None, "Problem was infeasible"
    elif termination_condition in ["numeric"]:
        return None, None, "Numerical trouble encountered, problem could be infeasible"
    elif status == "ok" and termination_condition == "optimal":
        pass
    elif status == "warning" and termination_condition == "suboptimal":
        pass
    else:
        return None, None, "Job failed to optimise correctly"


    results_overview = pd.Series(dtype=float)
    results_overview["average_price"] = network.buses_t.marginal_price.mean()["electricity"]
    if assumptions["hydrogen"]:
        results_overview["average_hydrogen_price"] = network.buses_t.marginal_price.mean()["hydrogen"]

    results_series = export_time_series(network)

    absmax = results_series.abs().max()

    to_drop = absmax.index[absmax < threshold*(assumptions["load"]+assumptions["hydrogen_load"])]
    results_series.drop(to_drop,
                        axis=1,
                        inplace=True)

    stats = network.statistics(aggregate_time="sum").groupby(level=1).sum()

    stats["Total Expenditure"] = stats[["Capital Expenditure","Operational Expenditure"]].sum(axis=1)

    #exclude components contributing less than 0.1 EUR/MWh
    selection = stats.index[stats["Total Expenditure"]/(assumptions["load"]+assumptions["hydrogen_load"]) > 100*threshold]
    stats = stats.loc[selection]

    for name,full_name in [("capex","Capital Expenditure"),("opex","Operational Expenditure"),("totex","Total Expenditure"),("capacity","Optimal Capacity")]:
        results_overview = pd.concat((results_overview,
                                      stats[full_name].rename(lambda x: x+ f" {name}")))

    results_overview["average_cost"] = sum([results_overview[s] for s in results_overview.index if s[-6:] == " totex"])/(assumptions["load"]+assumptions["hydrogen_load"])/8760.

    #report capacity from p1 not p0
    if "hydrogen turbine capacity" in results_overview:
        results_overview.loc["hydrogen turbine capacity"] *= network.links.at["hydrogen_turbine","efficiency"]


    results_overview = pd.concat((results_overview,
                                  (stats["Curtailment"]/(stats["Supply"]+stats["Curtailment"])).rename(lambda x: x+ " curtailment")))

    results_overview = pd.concat((results_overview,
                                  (stats["Total Expenditure"]/(stats["Supply"])).rename(lambda x: x+ " LCOE")))


    stats_mean = network.statistics(aggregate_time="mean").groupby(level=1).sum().loc[selection]
    results_overview = pd.concat((results_overview,
                                  stats_mean["Capacity Factor"].rename(lambda x: x+ " cf used")))
    results_overview = pd.concat((results_overview,
                                  ((stats_mean["Supply"]+stats_mean["Curtailment"])/stats_mean["Optimal Capacity"]).rename(lambda x: x+ " cf available")))

    #RMV
    bus_map = (network.buses.carrier == "electricity")
    bus_map.at[""] = False
    for c in network.iterate_components(network.one_port_components):
        items = c.df.index[c.df.bus.map(bus_map).fillna(False)]
        if len(items) == 0:
            continue
        rmv = (c.pnl.p[items].multiply(network.buses_t.marginal_price["electricity"], axis=0).sum()/c.pnl.p[items].sum()).groupby(c.df.loc[items,'carrier']).mean()/results_overview["average_price"]
        results_overview = pd.concat((results_overview,
                                      rmv.rename(lambda x: x+ " rmv").replace([np.inf, -np.inf], np.nan).dropna()))

    for c in network.iterate_components(network.branch_components):
        for end in [col[3:] for col in c.df.columns if col[:3] == "bus"]:
            items = c.df.index[c.df["bus" + str(end)].map(bus_map,na_action=False)]
            if len(items) == 0:
                continue
            rmv = (c.pnl["p"+end][items].multiply(network.buses_t.marginal_price["electricity"], axis=0).sum()/c.pnl["p"+end][items].sum()).groupby(c.df.loc[items,'carrier']).mean()/results_overview["average_price"]
            results_overview = pd.concat((results_overview,
                                          rmv.rename(lambda x: x+ " rmv").replace([np.inf, -np.inf], np.nan).dropna()))

    #LCOS
    if "battery_power" in network.links.index:
        battery_fedin = -network.links_t.p1.multiply(network.snapshot_weightings["generators"],axis=0).sum()["battery_discharge"]
        battery_costs = sum([results_overview[f"battery {name} totex"] for name in ["inverter","storage"]])
        battery_charging_costs = network.links_t.p0.multiply(network.snapshot_weightings["generators"],axis=0).sum()["battery_power"]*results_overview["battery inverter rmv"]*results_overview["average_price"]
        results_overview["battery inverter LCOE"] = (battery_costs + battery_charging_costs)/battery_fedin

    if "hydrogen_turbine" in network.links.index:
        hydrogen_fedin = -network.links_t.p1.multiply(network.snapshot_weightings["generators"],axis=0).sum()["hydrogen_turbine"]
        hydrogen_costs = sum([results_overview[f"hydrogen {name} totex"] for name in ["electrolyser","turbine","storage","storing compressor"]])
        hydrogen_charging_costs = network.links_t.p0.multiply(network.snapshot_weightings["generators"],axis=0).sum()["hydrogen_electrolyser"]*results_overview["hydrogen electrolyser rmv"]*results_overview["average_price"]
        results_overview["hydrogen turbine LCOE"] = (hydrogen_costs + hydrogen_charging_costs)/hydrogen_fedin


    fn = 'networks/{}.nc'.format(assumptions['results_hex'])
    network.export_to_netcdf(fn)

    return results_overview, results_series, None


def solve(assumptions):

    job = get_current_job()
    jobid = job.get_id()

    job.meta['status'] = "Reading in data"
    job.save_meta()

    # it could be that for a solve job, the weather data already exists
    weather_csv = 'data/time-series-{}.csv'.format(assumptions['weather_hex'])
    if os.path.isfile(weather_csv):
        print("Using preexisting weather file:", weather_csv)
        pu = pd.read_csv(weather_csv,
                         index_col=0,
                         parse_dates=True)
    else:
        if assumptions["version"] != current_version:
            return error(f'Outdated version {assumptions["version"]} can no longer be calculated; please use version {current_version} instead', jobid)

        print("Calculating weather from scratch, saving as:", weather_csv)
        pu, matrix_sum, error_msg = get_weather(assumptions["location"], assumptions["year"], assumptions['cf_exponent'])
        if error_msg is not None:
            return error(error_msg, jobid)
        pu = pu.round(3)
        pu.to_csv(weather_csv)
        with open('data/weather-assumptions-{}.json'.format(assumptions['weather_hex']), 'w') as fp:
            json.dump(assumptions,fp)

    if assumptions["job_type"] == "weather":
        print("Returning weather for {}".format(assumptions["location"]))

        with open('results-solve/results-{}.json'.format(jobid), 'w') as fp:
            json.dump({"jobid" : jobid,
                       "job_type" : assumptions["job_type"],
                       "weather_hex" : assumptions['weather_hex']
                   },fp)

        return {"job_type" : "weather", "weather_hex" : assumptions['weather_hex']}


    #for test data stored monthly, make hourly again
    snapshots = pd.date_range("{}-01-01".format(assumptions["year"]),"{}-12-31 23:00".format(assumptions["year"]),freq="H")
    pu = pu.reindex(snapshots,method="nearest")

    if assumptions["version"] != current_version:
        return error(f'Outdated version {assumptions["version"]} can no longer be calculated; please use version {current_version} instead', jobid)

    series_csv = 'data/results-series-{}.csv'.format(assumptions['results_hex'])
    overview_csv = 'data/results-overview-{}.csv'.format(assumptions['results_hex'])

    print("Calculating results from scratch, saving as:", series_csv, overview_csv)
    job.meta['status'] = "Solving optimisation problem"
    job.save_meta()
    results_overview, results_series, error_msg = run_optimisation(assumptions, pu)
    if error_msg is not None:
        return error(error_msg, jobid)
    results_series = results_series.round(1)

    results_series.to_csv(series_csv)
    results_overview.to_csv(overview_csv,header=False)
    with open('data/results-assumptions-{}.json'.format(assumptions['results_hex']), 'w') as fp:
        json.dump(assumptions,fp)

    job.meta['status'] = "Processing and sending results"
    job.save_meta()

    with open('results-solve/results-{}.json'.format(jobid), 'w') as fp:
        json.dump({"jobid" : jobid,
                   "status" : "Finished",
                   "job_type" : assumptions["job_type"],
                   "average_cost" : results_overview["average_cost"],
                   "results_hex" : assumptions['results_hex']
                   },fp)

    #with open('results-{}.json'.format(job.id), 'w') as fp:
    #    json.dump(results,fp)

    return {"job_type" : "solve", "results_hex" : assumptions['results_hex']}
