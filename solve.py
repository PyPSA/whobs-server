## Copyright 2018-2019 Tom Brown

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

import pandas as pd
from pyomo.environ import Constraint
from rq import get_current_job

import json

from atlite.gis import compute_indicatormatrix

import xarray as xr

import scipy as sp

import numpy as np

from shapely.geometry import box, Point, Polygon, MultiPolygon

octant_folder = "../cutouts/"

colors = {"wind":"#3B6182",
          "solar" :"#FFFF00",
          "battery" : "#999999",
          "battery_power" : "#999999",
          "battery_energy" : "#666666",
          "hydrogen_turbine" : "red",
          "hydrogen_electrolyser" : "cyan",
          "hydrogen_energy" : "magenta",
}

years_available_start = 2011
years_available_end = 2013


def get_country_multipolygons():

    with open('static/ne-countries-110m.json', 'r') as myfile:
        data=myfile.read()

        geojson = json.loads(data)

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

floats = ["load","wind_cost","solar_cost","battery_energy_cost",
          "battery_power_cost","hydrogen_electrolyser_cost",
          "hydrogen_energy_cost",
          "hydrogen_electrolyser_efficiency",
          "hydrogen_turbine_cost",
          "hydrogen_turbine_efficiency",
          "discount_rate"]

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

    return None, pu["solar"], pu["onwind"]


def process_shapely_polygon(polygon,year):
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
    final_result = { tech : pd.Series(0.,index=da.coords["time"].to_pandas()) for tech in techs}
    matrix_sum = 0.

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

            result = matrix*da

            final_result[tech] += pd.Series(result[0],
                                            index=da.coords["time"].to_pandas())

        matrix_sum += matrix.sum(axis=1)[0,0]

    for tech in techs:
        final_result[tech] = final_result[tech]/matrix_sum
    print("Matrix sum:",matrix_sum)


    return None, final_result["solar"], final_result["onwind"]



def process_polygon(ct,year):
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

    return process_shapely_polygon(polygon,year)



def solve(assumptions):

    job = get_current_job()
    jobid = job.get_id()

    job.meta['status'] = "Reading in data"
    job.save_meta()


    for key in booleans:
        try:
            assumptions[key] = bool(assumptions[key])
        except:
            return error("{} could not be converted to boolean".format(key), jobid)

    for key in floats:
        try:
            assumptions[key] = float(assumptions[key])
        except:
            return error("{} could not be converted to float".format(key), jobid)

        if assumptions[key] < 0 or assumptions[key] > 1e5:
            return error("{} {} was not in the valid range [0,1e5]".format(key,assumptions[key]), jobid)


    print(assumptions)

    try:
        year = int(assumptions['year'])
    except:
        return error("Year {} could not be converted to an integer".format(assumptions['year']), jobid)


    if year < years_available_start or year > years_available_end:
        return error("Year {} not in valid range".format(year), jobid)

    year_start = year
    year_end = year

    Nyears = year_end - year_start + 1

    ct = assumptions['country']

    if ct in country_multipolygons:
        error_msg, solar_pu, wind_pu = process_shapely_polygon(country_multipolygons[ct],year)
        assumptions["country"] = "country " + ct
    elif ct[:6] == "point:":
        error_msg, solar_pu, wind_pu = process_point(ct,year)
        ct = "point"
        assumptions["country"] = ct
    elif ct[:8] == "polygon:":
        error_msg, solar_pu, wind_pu = process_polygon(ct,year)
        ct = "polygon"
        assumptions["country"] = ct
    else:
        return error("Location {} is not valid".format(ct), jobid)

    if error_msg is not None:
        return error(error_msg, jobid)

    try:
        frequency = int(assumptions['frequency'])
    except:
        return error("Frequency {} could not be converted to an int".format(assumptions["frequency"]), jobid)

    if frequency < 1 or frequency > 8760:
        return error("Frequency {} is not in the valid range [1,8760]".format(frequency), jobid)


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
                p_set=assumptions["load"])

    if assumptions["solar"]:
        network.add("Generator",ct+" solar",
                    bus=ct,
                    p_max_pu = solar_pu.reindex(snapshots,method="nearest"),
                    p_nom_extendable = True,
                    marginal_cost = 0.1, #Small cost to prefer curtailment to destroying energy in storage, solar curtails before wind
                    capital_cost = assumptions_df.at['solar','fixed'])

    if assumptions["wind"]:
        network.add("Generator",ct+" wind",
                    bus=ct,
                    p_max_pu = wind_pu.reindex(snapshots,method="nearest"),
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
        return error("Job failed to optimise correctly", jobid)

    if termination_condition == "infeasible":
        return error("Problem was infeasible", jobid)

    job.meta['status'] = "Finished solving, processing and sending results"
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
            results[g+"_rmv"] = (network.buses_t.marginal_price[ct]*network.generators_t.p[ct + " " + g]).sum()/network.generators_t.p[ct + " " + g].sum()/results["average_price"]
            power["positive"][g] = network.generators_t.p[ct + " " + g]
        else:
            results[g+"_capacity"] = 0.
            results[g+"_cost"] = 0.
            results[g+"_curtailment"] = 0.
            results[g+"_used"] = 0.
            results[g+"_available"] = 0.
            results[g+"_cf_used"] = 0.
            results[g+"_cf_available"] = 0.
            results[g+"_rmv"] = 0.
            power["positive"][g] = 0.

    if assumptions["battery"] and network.links.at[ct + " battery_power","p_nom_opt"] > threshold and network.stores.at[ct + " battery_energy","e_nom_opt"]:
        results["battery_power_capacity"] = network.links.at[ct + " battery_power","p_nom_opt"]
        results["battery_power_cost"] = network.links.at[ct + " battery_power","p_nom_opt"]*network.links.at[ct + " battery_power","capital_cost"]/year_weight
        results["battery_energy_capacity"] = network.stores.at[ct + " battery_energy","e_nom_opt"]
        results["battery_energy_cost"] = network.stores.at[ct + " battery_energy","e_nom_opt"]*network.stores.at[ct + " battery_energy","capital_cost"]/year_weight
        results["battery_power_used"] = network.links_t.p0[ct + " battery_discharge"].mean()
        results["battery_power_cf_used"] = results["battery_power_used"]/network.links.at[ct + " battery_power","p_nom_opt"]
        results["battery_energy_used"] = network.stores_t.e[ct + " battery_energy"].mean()
        results["battery_energy_cf_used"] = results["battery_energy_used"]/network.stores.at[ct + " battery_energy","e_nom_opt"]
        results["battery_power_rmv"] = (network.buses_t.marginal_price[ct]*network.links_t.p0[ct + " battery_power"]).sum()/network.links_t.p0[ct + " battery_power"].sum()/results["average_price"]
        results["battery_discharge_rmv"] = (network.buses_t.marginal_price[ct]*network.links_t.p0[ct + " battery_discharge"]).sum()/network.links_t.p0[ct + " battery_discharge"].sum()/results["average_price"]
        power["positive"]["battery"] = -network.links_t.p1[ct + " battery_discharge"]
        power["negative"]["battery"] = network.links_t.p0[ct + " battery_power"]
    else:
        results["battery_power_capacity"] = 0.
        results["battery_power_cost"] = 0.
        results["battery_energy_capacity"] = 0.
        results["battery_energy_cost"] = 0.
        results["battery_power_used"] = 0.
        results["battery_power_cf_used"] = 0.
        results["battery_energy_used"] = 0.
        results["battery_energy_cf_used"] = 0.
        results["battery_power_rmv"] = 0.
        results["battery_discharge_rmv"] = 0.
        power["positive"]["battery"] = 0.
        power["negative"]["battery"] = 0.

    if assumptions["hydrogen"] and network.links.at[ct + " hydrogen_electrolyser","p_nom_opt"] > threshold and network.links.at[ct + " hydrogen_turbine","p_nom_opt"] > threshold and network.stores.at[ct + " hydrogen_energy","e_nom_opt"] > threshold:
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
        results["hydrogen_energy_used"] = network.stores_t.e[ct + " hydrogen_energy"].mean()
        results["hydrogen_energy_cf_used"] = results["hydrogen_energy_used"]/network.stores.at[ct + " hydrogen_energy","e_nom_opt"]
        results["hydrogen_turbine_rmv"] = (network.buses_t.marginal_price[ct]*network.links_t.p0[ct + " hydrogen_turbine"]).sum()/network.links_t.p0[ct + " hydrogen_turbine"].sum()/results["average_price"]
        results["hydrogen_electrolyser_rmv"] = (network.buses_t.marginal_price[ct]*network.links_t.p0[ct + " hydrogen_electrolyser"]).sum()/network.links_t.p0[ct + " hydrogen_electrolyser"].sum()/results["average_price"]
        power["positive"]["hydrogen_turbine"] = -network.links_t.p1[ct + " hydrogen_turbine"]
        power["negative"]["hydrogen_electrolyser"] = network.links_t.p0[ct + " hydrogen_electrolyser"]
    else:
        results["hydrogen_electrolyser_capacity"] = 0.
        results["hydrogen_electrolyser_cost"] = 0.
        results["hydrogen_turbine_capacity"] = 0.
        results["hydrogen_turbine_cost"] = 0.
        results["hydrogen_energy_capacity"] = 0.
        results["hydrogen_energy_cost"] = 0.
        results["hydrogen_electrolyser_used"] = 0.
        results["hydrogen_electrolyser_cf_used"] = 0.
        results["hydrogen_turbine_used"] = 0.
        results["hydrogen_turbine_cf_used"] = 0.
        results["hydrogen_energy_used"] = 0.
        results["hydrogen_energy_cf_used"] = 0.
        results["hydrogen_turbine_rmv"] = 0.
        results["hydrogen_electrolyser_rmv"] = 0.
        power["positive"]["hydrogen_turbine"] = 0.
        power["negative"]["hydrogen_electrolyser"] = 0.

    results["assumptions"] = assumptions

    results["average_cost"] = sum([results[s] for s in results if s[-5:] == "_cost"])/assumptions["load"]

    results["snapshots"] = [str(s) for s in network.snapshots]

    for sign in ["negative","positive"]:
        results[sign] = {}
        results[sign]["columns"] = list(power[sign].columns)
        results[sign]["data"] = power[sign].round(1).values.tolist()
        results[sign]["color"] = [colors[c] for c in power[sign].columns]

    balance = power["positive"].sum(axis=1) - power["negative"].sum(axis=1)

    with open('results-solve/results-{}.json'.format(jobid), 'w') as fp:
        json.dump({"jobid" : jobid,
                   "status" : "Finished",
                   "average_cost" : results["average_cost"]
                   },fp)

    #with open('results-{}.json'.format(job.id), 'w') as fp:
    #    json.dump(results,fp)

    return results
