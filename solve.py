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

import json, os, hashlib

#required to stop wierd failures
import netCDF4

from atlite.gis import spdiag, compute_indicatormatrix

import xarray as xr

import scipy as sp

import numpy as np

from shapely.geometry import box, Point, Polygon, MultiPolygon

current_version = 190929

octant_folder = "../cutouts/"

#based on mean deviation against renewables.ninja capacity factors for European countries for 2011-2013
solar_correction_factor = 0.926328


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
                              index=["wind","solar","hydrogen_electrolyser","hydrogen_turbine","hydrogen_energy",
                                     "battery_power","battery_energy","dispatchable1","dispatchable2"],
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


def get_octant_bounds(octant):

    x0 = -180 + (octant//2)*90.
    x1 = x0 + 90.

    y0 = 90. - (octant%2)*90.
    y1 = y0 - 90.

    return x0,x1,y0,y1

def generate_octant_grid_cells(octant, mesh=0.5):

    x0,x1,y0,y1 = get_octant_bounds(octant)

    x = np.arange(x0,
                  x1 + mesh,
                  mesh)

    y = np.arange(y0,
                  y1 - mesh,
                      -mesh)


    #grid_coordinates and grid_cells copied from atlite/cutout.py
    xs, ys = np.meshgrid(x,y)
    grid_coordinates = np.asarray((np.ravel(xs), np.ravel(ys))).T

    span = mesh / 2
    return [box(*c) for c in np.hstack((grid_coordinates - span, grid_coordinates + span))]


def get_octant(lon,lat):

    # 0 for lon -180--90, 1 for lon -90-0, etc.
    quadrant = find_interval(-180.,90,lon)

    #0 for lat 90-0, 1 for lat 0--90
    hemisphere = 1-find_interval(-90,90,lat)

    octant = 2*quadrant + hemisphere

    rel_x = lon - quadrant*90 + 180.

    rel_y = lat + 90*hemisphere

    span = 0.5

    n_per_octant = int(90/span +1)

    i = find_interval(0-span/2,span,rel_x)
    j = n_per_octant - 1 - find_interval(0-span/2,span,rel_y)

    position = j*n_per_octant+i

    #paranoid check
    if False:
        grid_cells = generate_octant_grid_cells(octant, mesh=span)
        assert grid_cells[position].contains(Point(lon,lat))

    return octant, position

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

    octant, position = get_octant(lon,lat)

    pu = {}

    for tech in ["solar", "onwind"]:
        o = xr.open_dataarray("{}octant{}-{}-{}.nc".format(octant_folder,octant,year,tech))
        pu[tech] = o.loc[position,:].to_pandas()

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

    #use for index
    da = xr.open_dataarray("{}octant0-{}-onwind.nc".format(octant_folder,year))

    techs = ["onwind","solar"]
    final_result = pd.DataFrame(0.,columns=techs,
                                index=da.coords["time"].to_pandas())
    matrix_sum = { tech : 0. for tech in techs}

    #range over octants
    for i in range(8):

        x0,x1,y0,y1 = get_octant_bounds(i)

        if bounds[0] > x1 or bounds[2] < x0 or bounds[3] < y1 or bounds[1] > y0:
            print("Skipping octant {}, since it is out of bounds".format(i))
            continue

        print("Computing transfer matrix with octant {}".format(i))

        grid_cells = generate_octant_grid_cells(i, mesh=0.5)

        matrix = compute_indicatormatrix(grid_cells,[polygon])

        matrix = sp.sparse.csr_matrix(matrix)

        for tech in techs:
            da = xr.open_dataarray("{}octant{}-{}-{}.nc".format(octant_folder,i,year,tech))
            means = pd.read_csv("data/octant{}-{}-{}-mean.csv".format(i,year,tech),index_col=0,squeeze=True)

            layout = (means.values)**cf_exponent

            tech_matrix = matrix.dot(spdiag(layout))

            result = tech_matrix*da

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



def run_optimisation(assumptions, pu):
    """Needs cleaned-up assumptions and pu.
    return results_overview, results_series, error_msg"""


    Nyears = 1

    techs = ["wind","solar","battery_energy","battery_power","hydrogen_electrolyser","hydrogen_energy","hydrogen_turbine","dispatchable1","dispatchable2"]

    for item in techs:
        assumptions_df.at[item,"discount rate"] = assumptions[item + "_discount"]/100.
        assumptions_df.at[item,"investment"] = assumptions[item + "_cost"]
        assumptions_df.at[item,"FOM"] = assumptions[item + "_fom"]
        assumptions_df.at[item,"lifetime"] = assumptions[item + "_lifetime"]

    #convert costs from per kW to per MW
    assumptions_df["investment"] *= 1000.
    assumptions_df["fixed"] = [(annuity(v["lifetime"],v["discount rate"])+v["FOM"]/100.)*v["investment"]*Nyears for i,v in assumptions_df.iterrows()]

    print('Starting task for {} with assumptions {}'.format(assumptions["location"],assumptions_df))

    network = pypsa.Network()

    snapshots = pd.date_range("{}-01-01".format(assumptions["year"]),"{}-12-31 23:00".format(assumptions["year"]),
                              freq=str(assumptions["frequency"])+"H")

    network.set_snapshots(snapshots)

    network.snapshot_weightings = pd.Series(float(assumptions["frequency"]),index=network.snapshots)

    network.add("Bus","elec")
    network.add("Load","load",
                bus="elec",
                p_set=assumptions["load"])

    if assumptions["solar"]:
        network.add("Generator","solar",
                    bus="elec",
                    p_max_pu = pu["solar"],
                    p_nom_extendable = True,
                    p_nom_min = assumptions["solar_min"],
                    p_nom_max = assumptions["solar_max"],
                    marginal_cost = 0.1, #Small cost to prefer curtailment to destroying energy in storage, solar curtails before wind
                    capital_cost = assumptions_df.at['solar','fixed'])

    if assumptions["wind"]:
        network.add("Generator","wind",
                    bus="elec",
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
                        bus="elec",
                        carrier=name,
                        p_nom_extendable=True,
                        marginal_cost=assumptions[name+"_marginal_cost"],
                        capital_cost=assumptions_df.at[name,'fixed'])

    if assumptions["battery"]:

        network.add("Bus","battery")

        network.add("Store","battery_energy",
                    bus = "battery",
                    e_nom_extendable = True,
                    e_cyclic=True,
                    capital_cost=assumptions_df.at['battery_energy','fixed'])

        network.add("Link","battery_power",
                    bus0 = "elec",
                    bus1 = "battery",
                    efficiency = assumptions["battery_power_efficiency_charging"]/100.,
                    p_nom_extendable = True,
                    capital_cost=assumptions_df.at['battery_power','fixed'])

        network.add("Link","battery_discharge",
                    bus0 = "battery",
                    bus1 = "elec",
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

    if assumptions["hydrogen"]:

        network.add("Bus",
                     "hydrogen",
                     carrier="hydrogen")

        network.add("Load","hydrogen_load",
                    bus="hydrogen",
                    p_set=assumptions["hydrogen_load"])

        network.add("Link",
                    "hydrogen_electrolyser",
                    bus1="hydrogen",
                    bus0="elec",
                    p_nom_extendable=True,
                    efficiency=assumptions["hydrogen_electrolyser_efficiency"]/100.,
                    capital_cost=assumptions_df.at["hydrogen_electrolyser","fixed"])

        network.add("Link",
                     "hydrogen_turbine",
                     bus0="hydrogen",
                     bus1="elec",
                     p_nom_extendable=True,
                     efficiency=assumptions["hydrogen_turbine_efficiency"]/100.,
                     capital_cost=assumptions_df.at["hydrogen_turbine","fixed"]*assumptions["hydrogen_turbine_efficiency"]/100.)  #NB: fixed cost is per MWel

        network.add("Store",
                     "hydrogen_energy",
                     bus="hydrogen",
                     e_nom_extendable=True,
                     e_cyclic=True,
                     capital_cost=assumptions_df.at["hydrogen_energy","fixed"])

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
    results_overview["objective"] = network.objective/8760
    results_overview["average_price"] = network.buses_t.marginal_price.mean()["elec"]
    if assumptions["hydrogen"]:
        results_overview["average_hydrogen_price"] = network.buses_t.marginal_price.mean()["hydrogen"]

    year_weight = network.snapshot_weightings.objective.sum()

    vre = ["wind","solar"]

    results_series = pd.DataFrame(index=network.snapshots,columns=vre+["battery_discharge","hydrogen_turbine","battery_charge","hydrogen_electrolyser","dispatchable1","dispatchable2","electricity_price","hydrogen_price","battery_energy","hydrogen_energy"],dtype=float)

    results_series["electricity_price"] = network.buses_t.marginal_price["elec"]

    for g in vre:
        if assumptions[g] and network.generators.p_nom_opt[g] > threshold:
            results_overview[g+"_capacity"] = network.generators.p_nom_opt[g]
            results_overview[g+"_cost"] = (network.generators.p_nom_opt*network.generators.capital_cost)[g]/year_weight + network.generators.at[g,"marginal_cost"]*network.generators_t.p[g].mean()
            results_overview[g+"_available"] = network.generators.p_nom_opt[g]*network.generators_t.p_max_pu[g].mean()
            results_overview[g+"_used"] = network.generators_t.p[g].mean()
            results_overview[g+"_curtailment"] =  (results_overview[g+"_available"] - results_overview[g+"_used"])/results_overview[g+"_available"]
            results_overview[g+"_cf_available"] = network.generators_t.p_max_pu[g].mean()
            results_overview[g+"_cf_used"] = results_overview[g+"_used"]/network.generators.p_nom_opt[g]
            results_overview[g+"_rmv"] = (network.buses_t.marginal_price["elec"]*network.generators_t.p[g]).sum()/network.generators_t.p[g].sum()/results_overview["average_price"]
            results_series[g] = network.generators_t.p[g]
        else:
            results_overview[g+"_capacity"] = 0.
            results_overview[g+"_cost"] = 0.
            results_overview[g+"_curtailment"] = 0.
            results_overview[g+"_used"] = 0.
            results_overview[g+"_available"] = 0.
            results_overview[g+"_cf_used"] = 0.
            results_overview[g+"_cf_available"] = 0.
            results_overview[g+"_rmv"] = 0.
            results_series[g] = 0.

    for i in range(1,3):
        g = "dispatchable" + str(i)
        if assumptions[g] and network.generators.p_nom_opt[g] > threshold:
            results_overview[g+"_capacity"] = network.generators.p_nom_opt[g]
            results_overview[g+"_cost"] = (network.generators.p_nom_opt*network.generators.capital_cost)[g]/year_weight
            results_overview[g+"_marginal_cost"] = network.generators_t.p[g].mean()*network.generators.at[g,"marginal_cost"]
            results_overview[g+"_used"] = network.generators_t.p[g].mean()
            results_overview[g+"_cf_used"] = results_overview[g+"_used"]/network.generators.p_nom_opt[g]
            results_overview[g+"_rmv"] = (network.buses_t.marginal_price["elec"]*network.generators_t.p[g]).sum()/network.generators_t.p[g].sum()/results_overview["average_price"]
            results_series[g] = network.generators_t.p[g]
        else:
            results_overview[g+"_capacity"] = 0.
            results_overview[g+"_cost"] = 0.
            results_overview[g+"_marginal_cost"] = 0.
            results_overview[g+"_used"] = 0.
            results_overview[g+"_cf_used"] = 0.
            results_overview[g+"_rmv"] = 0.
            results_series[g] = 0.

    if assumptions["battery"] and network.links.at["battery_power","p_nom_opt"] > threshold and network.stores.at["battery_energy","e_nom_opt"]:
        results_overview["battery_power_capacity"] = network.links.at["battery_power","p_nom_opt"]
        results_overview["battery_power_cost"] = network.links.at["battery_power","p_nom_opt"]*network.links.at["battery_power","capital_cost"]/year_weight
        results_overview["battery_energy_capacity"] = network.stores.at["battery_energy","e_nom_opt"]
        results_overview["battery_energy_cost"] = network.stores.at["battery_energy","e_nom_opt"]*network.stores.at["battery_energy","capital_cost"]/year_weight
        results_overview["battery_power_used"] = network.links_t.p0["battery_discharge"].mean()
        results_overview["battery_power_cf_used"] = results_overview["battery_power_used"]/network.links.at["battery_power","p_nom_opt"]
        results_overview["battery_energy_used"] = network.stores_t.e["battery_energy"].mean()
        results_overview["battery_energy_cf_used"] = results_overview["battery_energy_used"]/network.stores.at["battery_energy","e_nom_opt"]
        results_overview["battery_power_rmv"] = (network.buses_t.marginal_price["elec"]*network.links_t.p0["battery_power"]).sum()/network.links_t.p0["battery_power"].sum()/results_overview["average_price"]
        results_overview["battery_discharge_rmv"] = (network.buses_t.marginal_price["elec"]*network.links_t.p0["battery_discharge"]).sum()/network.links_t.p0["battery_discharge"].sum()/results_overview["average_price"]
        results_series["battery_discharge"] = -network.links_t.p1["battery_discharge"]
        results_series["battery_charge"] = network.links_t.p0["battery_power"]
        results_series["battery_energy"] = network.stores_t.e["battery_energy"]
    else:
        results_overview["battery_power_capacity"] = 0.
        results_overview["battery_power_cost"] = 0.
        results_overview["battery_energy_capacity"] = 0.
        results_overview["battery_energy_cost"] = 0.
        results_overview["battery_power_used"] = 0.
        results_overview["battery_power_cf_used"] = 0.
        results_overview["battery_energy_used"] = 0.
        results_overview["battery_energy_cf_used"] = 0.
        results_overview["battery_power_rmv"] = 0.
        results_overview["battery_discharge_rmv"] = 0.
        results_series["battery_discharge"] = 0.
        results_series["battery_charge"] = 0.
        results_series["battery_energy"] = 0.

    if assumptions["hydrogen"]:
        results_overview["hydrogen_electrolyser_capacity"] = network.links.at["hydrogen_electrolyser","p_nom_opt"]
        results_overview["hydrogen_electrolyser_cost"] = network.links.at["hydrogen_electrolyser","p_nom_opt"]*network.links.at["hydrogen_electrolyser","capital_cost"]/year_weight
        results_overview["hydrogen_turbine_capacity"] = network.links.at["hydrogen_turbine","p_nom_opt"]*network.links.at["hydrogen_turbine","efficiency"]
        results_overview["hydrogen_turbine_cost"] = network.links.at["hydrogen_turbine","p_nom_opt"]*network.links.at["hydrogen_turbine","capital_cost"]/year_weight
        results_overview["hydrogen_energy_capacity"] = network.stores.at["hydrogen_energy","e_nom_opt"]
        results_overview["hydrogen_energy_cost"] = network.stores.at["hydrogen_energy","e_nom_opt"]*network.stores.at["hydrogen_energy","capital_cost"]/year_weight
        results_overview["hydrogen_electrolyser_used"] = network.links_t.p0["hydrogen_electrolyser"].mean()
        if network.links.at["hydrogen_electrolyser","p_nom_opt"] > threshold:
            results_overview["hydrogen_electrolyser_cf_used"] = results_overview["hydrogen_electrolyser_used"]/network.links.at["hydrogen_electrolyser","p_nom_opt"]
            results_overview["hydrogen_electrolyser_rmv"] = (network.buses_t.marginal_price["elec"]*network.links_t.p0["hydrogen_electrolyser"]).sum()/network.links_t.p0["hydrogen_electrolyser"].sum()/results_overview["average_price"]
        else:
            results_overview["hydrogen_electrolyser_cf_used"] = 0.
            results_overview["hydrogen_electrolyser_rmv"] = 0.
        results_overview["hydrogen_turbine_used"] = network.links_t.p0["hydrogen_turbine"].mean()*network.links.at["hydrogen_turbine","efficiency"]
        if network.links.at["hydrogen_turbine","p_nom_opt"] > threshold:
            results_overview["hydrogen_turbine_cf_used"] = results_overview["hydrogen_turbine_used"]/results_overview["hydrogen_turbine_capacity"]
            results_overview["hydrogen_turbine_rmv"] = (network.buses_t.marginal_price["elec"]*network.links_t.p0["hydrogen_turbine"]).sum()/network.links_t.p0["hydrogen_turbine"].sum()/results_overview["average_price"]
        else:
            results_overview["hydrogen_turbine_cf_used"] = 0.
            results_overview["hydrogen_turbine_rmv"] = 0.
        results_overview["hydrogen_energy_used"] = network.stores_t.e["hydrogen_energy"].mean()
        if network.stores.at["hydrogen_energy","e_nom_opt"] > threshold:
            results_overview["hydrogen_energy_cf_used"] = results_overview["hydrogen_energy_used"]/network.stores.at["hydrogen_energy","e_nom_opt"]
        else:
            results_overview["hydrogen_energy_cf_used"] = 0.
        results_series["hydrogen_turbine"] = -network.links_t.p1["hydrogen_turbine"]
        results_series["hydrogen_electrolyser"] = network.links_t.p0["hydrogen_electrolyser"]
        results_series["hydrogen_energy"] = network.stores_t.e["hydrogen_energy"]
        results_series["hydrogen_price"] = network.buses_t.marginal_price["hydrogen"]
    else:
        results_overview["hydrogen_electrolyser_capacity"] = 0.
        results_overview["hydrogen_electrolyser_cost"] = 0.
        results_overview["hydrogen_turbine_capacity"] = 0.
        results_overview["hydrogen_turbine_cost"] = 0.
        results_overview["hydrogen_energy_capacity"] = 0.
        results_overview["hydrogen_energy_cost"] = 0.
        results_overview["hydrogen_electrolyser_used"] = 0.
        results_overview["hydrogen_electrolyser_cf_used"] = 0.
        results_overview["hydrogen_turbine_used"] = 0.
        results_overview["hydrogen_turbine_cf_used"] = 0.
        results_overview["hydrogen_energy_used"] = 0.
        results_overview["hydrogen_energy_cf_used"] = 0.
        results_overview["hydrogen_turbine_rmv"] = 0.
        results_overview["hydrogen_electrolyser_rmv"] = 0.
        results_series["hydrogen_turbine"] = 0.
        results_series["hydrogen_electrolyser"] = 0.
        results_series["hydrogen_energy"] = 0.
        results_series["hydrogen_price"] = 0.

    results_overview["average_cost"] = sum([results_overview[s] for s in results_overview.index if s[-5:] == "_cost"])/(assumptions["load"]+assumptions["hydrogen_load"])

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
