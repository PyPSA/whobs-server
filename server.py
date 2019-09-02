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




from flask import Flask, request, jsonify, render_template, Markup


from redis import Redis

import rq
from rq.job import Job
from rq import Queue

import time, datetime

import json

conn = Redis.from_url('redis://')

queue = Queue('whobs', connection=conn)


app = Flask(__name__)
app.jinja_env.filters['json'] = lambda v: Markup(json.dumps(v))

# Load allowed country names
with(open('static/ne-countries-110m.json', 'r')) as f:
    j = json.load(f)
country_names = [f['properties']['iso_a2'] for f in j['features']]
country_names_full = [f['properties']['name'] for f in j['features']]

# Load allowed region names
with(open('static/selected_admin1.json', 'r')) as f:
    j = json.load(f)
region_names = [f['properties']['name'] for f in j['features']]


tbooleans = ["wind","solar","battery","hydrogen"]
fbooleans = ["dispatchable1","dispatchable2","co2_limit"]

float_tech_options = ["wind_cost", "solar_cost", "battery_energy_cost","battery_power_cost", "hydrogen_energy_cost", "hydrogen_electrolyser_cost", "hydrogen_electrolyser_efficiency", "hydrogen_turbine_cost", "hydrogen_turbine_efficiency","co2_emissions"]


@app.route('/')
def root():
    if request.method == "GET":

        # Try to get settings from URL
        assumptions = {}
        assumptions["location"] = request.args.get('location', default = 'DE', type = str)
        assumptions["job_type"] = request.args.get('job_type', default = 'none', type = str)
        assumptions["year"] = request.args.get('year', default = 2011, type = int)
        assumptions["frequency"] = request.args.get('frequency', default = 3, type = int)
        assumptions["cf_exponent"] = request.args.get('cf_exponent', default = 2, type = float)
        assumptions["load"] = request.args.get('load', default = 100, type = float)
        assumptions["discount_rate"] = request.args.get('discount_rate', default = 5, type = float)
        assumptions["co2_emissions"] = request.args.get('co2_emissions', default = 100, type = float)
        for boolean in tbooleans:
            assumptions[boolean] = request.args.get(boolean, default = 1, type = int)
        for boolean in fbooleans:
            assumptions[boolean] = request.args.get(boolean, default = 0, type = int)
        for float_tech_option in float_tech_options:
            if float_tech_option in request.args:
                assumptions[float_tech_option] = request.args.get(float_tech_option, default = 100, type = float)


        if assumptions["location"][:8] == "country:" and assumptions["location"][8:] in country_names:
            assumptions["location_name"] = country_names_full[country_names.index(assumptions["location"][8:])]
        elif assumptions["location"][:6] == "point:":
            assumptions["location_name"] = assumptions["location"]
        elif assumptions["location"][:8] == "polygon:":
            assumptions["location_name"] = "polygon"
        elif assumptions["location"][:7] == "region:" and assumptions["location"][7:] in region_names:
            assumptions["location_name"] = assumptions["location"][7:]
        else:
            assumptions["location"] = 'country:DE'
            assumptions["location_name"] = country_names_full[country_names.index(assumptions["location"][8:])]

        for boolean in tbooleans + fbooleans:
            if assumptions[boolean] == 0:
                assumptions[boolean] = False
            else:
                assumptions[boolean] = True

    return render_template('index.html', settings=assumptions)


@app.route('/jobs', methods=['GET','POST'])
def jobs_api():
    if request.method == "POST":
        print(request.headers['Content-Type'])
        print(request.json)
        job = queue.enqueue("solve.solve", args=(request.json,), job_timeout=300)
        result = {"jobid" : job.get_id()}
        request.json.update({"jobid" : result["jobid"],
                             "timestamp" : str(datetime.datetime.now()),
                             "queue_length" : len(queue.jobs)})
        with open('assumptions/assumptions-{}.json'.format(result["jobid"]), 'w') as fp:
            json.dump(request.json, fp)
        print("jobid {} request:".format(result["jobid"]))
        print(request.json)
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
        result.update(job.result)
        if "error" in result:
            result["status"] = "Error"
        else:
            result["status"] = "Finished"

        jobid = job.get_id()

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
