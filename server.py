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




from flask import Flask, request, jsonify, render_template, Response

from markupsafe import Markup

from solve import export_time_series, generate_overview

from redis import Redis

import rq
from rq.job import Job
from rq import Queue

import time, datetime

import json, os, hashlib, yaml

import pandas as pd

import pypsa

conn = Redis.from_url('redis://')

queue = Queue('whobs', connection=conn)

with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

app = Flask(__name__)
app.jinja_env.filters['json'] = lambda v: Markup(json.dumps(v))




#na_filter leaves "" as "" rather than doing nan which confuses jinja2
defaults = pd.read_csv("defaults.csv",index_col=[0,1],na_filter=False)

for (n,t) in [("f",float),("i",int)]:
    defaults.loc[defaults["type"] == n, "value"] = defaults.loc[defaults["type"] == n,"value"].astype(t)

#work around fact bool("False") returns True
defaults.loc[defaults.type == "b","value"] = (defaults.loc[defaults.type == "b","value"] == "True")

defaults_t = {str(year): defaults.swaplevel().loc[str(year)] for year in config["tech_years"]}
defaults = defaults.swaplevel().loc[""]

defaults = pd.concat((defaults,defaults_t[str(config["tech_years_default"])])).sort_index()

first = ["load","hydrogen_load","year","frequency"]
defaults = defaults.reindex(first + defaults.index.drop(first).to_list())

booleans = defaults.index[defaults.type == "b"].to_list()

floats = defaults.index[defaults.type == "f"].to_list()

ints = defaults.index[defaults.type == "i"].to_list()

strings = defaults.index[defaults.type == "s"].to_list()

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

        if assumptions[key] < 0 or assumptions[key] > config["float_upper_limit"]:
            return "{} {} was not in the valid range [0,{}]".format(key,assumptions[key],config["float_upper_limit"]), None

    for key in ints:
        try:
            assumptions[key] = int(assumptions[key])
        except:
            return "{} {} could not be converted to an integer".format(key,assumptions[key]), None

    for key in strings:
        assumptions[key] = str(assumptions[key])

    if assumptions["frequency"] < 1 or assumptions["frequency"] > 8760:
        return "Frequency {} is not in the valid range [1,8760]".format(assumptions["frequency"]), None

    if assumptions["year"] not in config["weather_years"]:
        return "Year {} not in valid range".format(assumptions["year"]), None

    if assumptions["load"] == 0 and assumptions["hydrogen_load"] == 0:
        return "No load", None

    if not assumptions["hydrogen"] and assumptions["hydrogen_load"] != 0:
        return "Non-zero hydrogen load is defined without activating hydrogen infrastructure", None

    return None, assumptions

def compute_results_hash(assumptions):
    results_string = ""
    for item in strings+ints+booleans+floats:
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
    network_fn = f'networks/{results_hash}.nc'

    if not os.path.isfile(assumptions_json):
        return "Assumptions file is missing", {}
    if not os.path.isfile(network_fn):
        return "Network file is missing", {}

    print("Using preexisting results files:", assumptions_json, network_fn)
    with(open(assumptions_json, 'r')) as f:
        assumptions = json.load(f)

    n = pypsa.Network(network_fn)

    results_overview = generate_overview(n)

    carrier_series = export_time_series(n).round(1)

    #determine nice ordering of components
    current_order = results_overview.index[results_overview.index.str[-6:] == " totex"].str[:-6]
    preferred_order = pd.Index(config["preferred order"])
    new_order = preferred_order.intersection(current_order).append(current_order.difference(preferred_order))

    print("old:",current_order)
    print("new:",new_order)

    results = dict(results_overview)

    results["assumptions"] = assumptions

    results["order"] = list(new_order)

    results["snapshots"] = [str(s) for s in carrier_series.index]

    results["carrier_series"] = {}

    for carrier in config["balances_to_display"]:

        if carrier not in carrier_series:
            continue

        print("processing series for energy carrier", carrier)

        #group technologies
        df =  carrier_series[carrier]

        #sort into positive and negative
        separated = {}
        separated["positive"] = pd.DataFrame(index=df.index,
                                             dtype=float)
        separated["negative"] = pd.DataFrame(index=df.index,
                                             dtype=float)

        for col in df.columns:
            if df[col].min() > -1:
                separated["positive"][col] = df[col]
                separated["positive"][col][separated["positive"][col] < 0] = 0

            elif df[col].max() < 1:
                separated["negative"][col] = df[col]
                separated["negative"][col][separated["negative"][col] > 0] = 0

            else:
                separated["positive"][col] = df[col]
                separated["positive"][col][separated["positive"][col] < 0] = 0
                separated["negative"][col] = df[col]
                separated["negative"][col][separated["negative"][col] > 0] = 0

        separated["negative"] *= -1

        results["carrier_series"][carrier] = {}
        results["carrier_series"][carrier]["label"] = "power"
        results["carrier_series"][carrier]["units"] = "MW"

        for sign in ["positive","negative"]:
            results["carrier_series"][carrier][sign] = {}
            results["carrier_series"][carrier][sign]["columns"] = separated[sign].columns.tolist()
            results["carrier_series"][carrier][sign]["data"] = (separated[sign].values).tolist()
            print(sign,separated[sign].columns)
            results["carrier_series"][carrier][sign]["color"] = [config["colors"][i] for i in separated[sign].columns]

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
                           defaults=defaults.T.to_dict(),
                           defaults_t={year: defaults_t[year].T.to_dict() for year in defaults_t},
                           config=config,
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


@app.route('/csvs/overview-<resultshex>.csv')
def overview_api(resultshex):
    fn = f'networks/{resultshex}.nc'
    try:
        n = pypsa.Network(fn)
    except:
        return Response(f"network {resultshex} not found")

    csv = generate_overview(n).to_csv(header=False)
    response = Response(csv, content_type='text/csv')
    response.headers['Content-Disposition'] = f'attachment; filename=overview-{resultshex}.csv'
    return response


@app.route('/csvs/series-<resultshex>.csv')
def series_api(resultshex):
    fn = f'networks/{resultshex}.nc'
    try:
        n = pypsa.Network(fn)
    except:
        return Response(f"network {resultshex} not found")

    csv = export_time_series(n).round(1).to_csv()
    response = Response(csv, content_type='text/csv')
    response.headers['Content-Disposition'] = f'attachment; filename=series-{resultshex}.csv'
    return response

if __name__ == '__main__':
    app.run(port='5002')
