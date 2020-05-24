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




from flask import Flask, request, jsonify, render_template, Markup


from redis import Redis

import rq
from rq.job import Job
from rq import Queue

import time, datetime

import json, os, hashlib

import pandas as pd

current_version = 190929

conn = Redis.from_url('redis://')

queue = Queue('whobs', connection=conn)


app = Flask(__name__)
app.jinja_env.filters['json'] = lambda v: Markup(json.dumps(v))


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
          "co2_emissions",
          "wind_max",
          "solar_max"]


ints = ["year","frequency","version"]

strings = ["location"]


colors = {"wind":"#3B6182",
          "solar" :"#FFFF00",
          "battery" : "#999999",
          "battery_charge" : "#999999",
          "battery_discharge" : "#999999",
          "battery_power" : "#999999",
          "battery_energy" : "#666666",
          "hydrogen_turbine" : "red",
          "hydrogen_electrolyser" : "cyan",
          "hydrogen_energy" : "magenta",
          "dispatchable1" : "orange",
          "dispatchable2" : "lime",
}


years_available_start = 2011
years_available_end = 2013

float_upper_limit = 1e7


def sanitise_assumptions(assumptions):
    """
    Fix types of assumptions and check they are in correct
    range.

    Parameters
    ----------
    assumptions : dict
        Assumptions (location, technical and economic parameters)

    Returns
    -------
    error_message : None or string
        If there was an error, details of the error
    assumptions : dict
        If there was no error, the clean type-safe assumptions
    """
    for key in strings+ints+booleans+floats:
        if key not in assumptions:
            return f"{key} missing from assumptions", None

    for key in booleans:
        try:
            assumptions[key] = bool(assumptions[key])
        except:
            return "{} {} could not be converted to boolean".format(key,assumptions[key]), None

    for key in floats:
        try:
            assumptions[key] = float(assumptions[key])
        except:
            return "{} {} could not be converted to float".format(key,assumptions[key]), None

        if assumptions[key] < 0 or assumptions[key] > float_upper_limit:
            return "{} {} was not in the valid range [0,{}]".format(key,assumptions[key],float_upper_limit), None

    for key in ints:
        try:
            assumptions[key] = int(assumptions[key])
        except:
            return "{} {} could not be converted to an integer".format(key,assumptions[key]), None

    for key in strings:
        assumptions[key] = str(assumptions[key])

    if assumptions["frequency"] < 1 or assumptions["frequency"] > 8760:
        return "Frequency {} is not in the valid range [1,8760]".format(assumptions["frequency"]), None

    if assumptions["year"] < years_available_start or assumptions["year"] > years_available_end:
        return "Year {} not in valid range".format(assumptions["year"]), None

    if assumptions["load"] == 0 and assumptions["hydrogen_load"] == 0:
        return "No load", None

    if not assumptions["hydrogen"] and assumptions["hydrogen_load"] != 0:
        return "Non-zero hydrogen load is defined without activating hydrogen infrastructure", None

    return None, assumptions

def compute_results_hash(assumptions):
    results_string = ""
    for item in strings+ints+booleans+floats:
        #remove assumptions for excluded technologies
        skip = False
        for tech in ["wind","solar","hydrogen","battery","dispatchable1","dispatchable2"]:
            if not assumptions[tech] and tech in item and tech != item:
                skip = True
                continue
        if not assumptions["co2_limit"] and item == "co2_emissions":
            skip = True
        if not skip:
            results_string += "&{}={}".format(item,assumptions[item])
    print(results_string)
    return hashlib.md5(results_string.encode()).hexdigest()

def compute_weather_hash(assumptions):
    weather_string = ""
    for item in ["location","year","cf_exponent","version"]:
        weather_string += "&{}={}".format(item,assumptions[item])
    print(weather_string)
    return hashlib.md5(weather_string.encode()).hexdigest()


def find_results(results_hash):

    assumptions_json = f'data/results-assumptions-{results_hash}.json'
    series_csv = f'data/results-series-{results_hash}.csv'
    overview_csv = f'data/results-overview-{results_hash}.csv'

    if not os.path.isfile(assumptions_json):
        return "Assumptions file is missing", {}
    if not os.path.isfile(series_csv):
        return "Series results file is missing", {}
    if not os.path.isfile(overview_csv):
        return "Overview results file is missing", {}

    print("Using preexisting results files:", assumptions_json, series_csv, overview_csv)
    with(open(assumptions_json, 'r')) as f:
        assumptions = json.load(f)
    results_overview = pd.read_csv(overview_csv,
                                   index_col=0,
                                   header=None,
                                   squeeze=True)
    results_series = pd.read_csv(series_csv,
                                 index_col=0,
                                 parse_dates=True)

    #fill in old results before dispatchable
    for i in range(1,3):
        g = "dispatchable" + str(i)
        if not assumptions[g]:
            results_overview[g+"_capacity"] = 0.
            results_overview[g+"_cost"] = 0.
            results_overview[g+"_marginal_cost"] = 0.
            results_overview[g+"_used"] = 0.
            results_overview[g+"_cf_used"] = 0.
            results_overview[g+"_rmv"] = 0.
            results_series[g] = 0.

    results = dict(results_overview)

    results["assumptions"] = assumptions

    results["snapshots"] = [str(s) for s in results_series.index]

    columns = {"positive" : ["wind","solar","battery_discharge","hydrogen_turbine","dispatchable1","dispatchable2"],
               "negative" : ["battery_charge","hydrogen_electrolyser"]}


    for sign, cols in columns.items():
        results[sign] = {}
        results[sign]["columns"] = cols
        results[sign]["data"] = results_series[cols].values.tolist()
        results[sign]["color"] = [colors[c] for c in cols]

    balance = results_series[columns["positive"]].sum(axis=1) - results_series[columns["negative"]].sum(axis=1)

    print(balance.describe())

    return None, results



def find_weather(weather_hash):

    assumptions_json = f'data/weather-assumptions-{weather_hash}.json'
    weather_csv = f'data/time-series-{weather_hash}.csv'

    if not os.path.isfile(assumptions_json):
        return "Assumptions file is missing", {}
    if not os.path.isfile(weather_csv):
        return "Weather file is missing", {}

    print("Using preexisting weather files:", assumptions_json, weather_csv)

    with(open(assumptions_json, 'r')) as f:
        assumptions = json.load(f)
    pu = pd.read_csv(weather_csv,
                     index_col=0,
                     parse_dates=True)

    results = {}
    results['assumptions'] = assumptions
    results["snapshots"] = [str(s) for s in pu.index]

    for v in ["onwind","solar"]:
        results[v+'_pu'] = pu[v].values.tolist()
        results[v+"_cf_available"] = pu[v].mean()

    return None, results



#defaults to only listen to GET and HEAD
@app.route('/')
def root():

    print("requests:",request.args)
    if "results" in request.args:
        results_hash = request.args.get("results",type=str)
        error_message, results = find_results(results_hash)
        if error_message is not None:
            print(error_message)
    elif "weather" in request.args:
        weather_hash = request.args.get("weather",type=str)
        error_message, results = find_weather(weather_hash)
        if error_message is not None:
            print(error_message)
    else:
        results = {}

    return render_template('index.html',
                           results=results)


@app.route('/jobs', methods=['GET','POST'])
def jobs_api():
    if request.method == "POST":
        if request.headers.get('Content-Type','missing') != 'application/json':
            return jsonify({"status" : "Error", "error" : "No JSON assumptions sent."})

        print(request.json)

        error_message, assumptions = sanitise_assumptions(request.json)

        if error_message is not None:
            return jsonify({"status" : "Error", "error" : error_message})

        if assumptions["job_type"] == "weather":
            assumptions["weather_hex"] = compute_weather_hash(assumptions)
            error_message, results = find_weather(assumptions["weather_hex"])
            if error_message is None:
                assumptions["timestamp"] = str(datetime.datetime.now())
                assumptions["jobid"] = hashlib.md5(assumptions["timestamp"].encode()).hexdigest()
                assumptions["queue_length"] = 0
                with open('assumptions/assumptions-{}.json'.format(assumptions["jobid"]), 'w') as fp:
                    json.dump(assumptions, fp)
                mini_results = {"jobid" : assumptions["jobid"], "status" : "Finished",
                                "error" : None, "average_cost" : None}
                with open('results/results-{}.json'.format(assumptions["jobid"]), 'w') as fp:
                    json.dump(mini_results, fp)
                return jsonify(results)
        elif assumptions["job_type"] == "solve":
            assumptions["weather_hex"] = compute_weather_hash(assumptions)
            assumptions["results_hex"] = compute_results_hash(assumptions)
            error_message, results = find_results(assumptions["results_hex"])
            if error_message is None:
                assumptions["timestamp"] = str(datetime.datetime.now())
                assumptions["jobid"] = hashlib.md5(assumptions["timestamp"].encode()).hexdigest()
                assumptions["queue_length"] = 0
                with open('assumptions/assumptions-{}.json'.format(assumptions["jobid"]), 'w') as fp:
                    json.dump(assumptions, fp)
                mini_results = {"jobid" : assumptions["jobid"], "status" : "Finished",
                                "error" : None, "average_cost" : results["average_cost"]}
                with open('results/results-{}.json'.format(assumptions["jobid"]), 'w') as fp:
                    json.dump(mini_results, fp)
                return jsonify(results)
        else:
            return jsonify({"status" : "Error", "error" : "job_type not one of solve or weather"})

        job = queue.enqueue("solve.solve", args=(assumptions,), job_timeout=300)
        result = {"jobid" : job.get_id()}
        assumptions.update({"jobid" : result["jobid"],
                            "timestamp" : str(datetime.datetime.now()),
                            "queue_length" : len(queue.jobs)})
        with open('assumptions/assumptions-{}.json'.format(assumptions["jobid"]), 'w') as fp:
            json.dump(assumptions, fp)
        print("jobid {} request:".format(result["jobid"]))
        print(assumptions)
        return jsonify(result)
    elif request.method == "GET":
        return "jobs in queue: {}".format(len(queue.jobs))

@app.route('/jobs/<jobid>')
def jobid_api(jobid):
    try:
        job = Job.fetch(jobid, connection=conn)
    except:
        return jsonify({"status" : "Error", "error" : "Failed to find job!"})

    if job.is_failed:
        return jsonify({"status" : "Error", "error" : "Job failed."})

    try:
        status = job.meta['status']
    except:
        status = "Waiting for job to run (jobs in queue: {})".format(len(queue.jobs))

    result = {"status" : status}

    if job.is_finished:
        if "error" in job.result:
            result["status"] = "Error"
            result["error"] = job.result["error"]
        else:
            result["status"] = "Finished"

            if job.result["job_type"] == "weather":
                error_message, results = find_weather(job.result["weather_hex"])
                if error_message is not None:
                    result["status"] = "Error"
                    result["error"] = error_message
            elif job.result["job_type"] == "solve":
                error_message, results = find_results(job.result["results_hex"])
                if error_message is not None:
                    result["status"] = "Error"
                    result["error"] = error_message

        if result["status"] == "Finished":
            results.update(result)
            result = results

        mini_results = {"jobid" : jobid,
                        "status" : result["status"],
                        "error" : result.get("error",None),
                        "average_cost" : result.get("average_cost",None)}

        print("jobid {} results:".format(jobid))
        print(mini_results)
        with open('results/results-{}.json'.format(jobid), 'w') as fp:
            json.dump(mini_results, fp)

    return jsonify(result)


if __name__ == '__main__':
    app.run(port='5002')
