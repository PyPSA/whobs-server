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
with(open('static/ne_50m_admin_0_countries_simplified_europe.json', 'r')) as f:
    j = json.load(f)
country_names = [f['properties']['iso_a2'] for f in j['features']]
country_names_full = [f['properties']['name'] for f in j['features']]


@app.route('/')
def root():
    if request.method == "GET":
        # Try to get settings from URL
        country = request.args.get('country', default = 'GB', type = str)
        year = request.args.get('year', default = 2013, type = int)
        freq = request.args.get('freq', default = 3, type = int)
        demand = request.args.get('demand', default = 100, type = int)
        scenario = request.args.get('scenario', default = 2030, type = int)
        wind = request.args.get('wind', default = 1, type = int)
        solar = request.args.get('solar', default = 1, type = int)
        battery = request.args.get('battery', default = 1, type = int)
        hydrogen = request.args.get('hydrogen', default = 1, type = int)

        # Validate settings
        if country not in country_names:
            country = 'GB'
        country_name = country_names_full[country_names.index(country)]
        if year < 1985 or year > 2015:
            year = 2013
        if freq < 1 or freq > 8760:
            freq = 3
        if demand <= 0:
            demand = 100
        if scenario not in [2020, 2030, 2050]:
            scenario = 2030
        if wind == 0:
            wind = False
        else:
            wind = True
        if solar == 0:
            solar = False
        else:
            solar = True
        if battery == 0:
            battery = False
        else:
            battery = True
        if hydrogen == 0:
            hydrogen = False
        else:
            hydrogen = True

        settings_dict = {
            'country': country,
            'year': year,
            'frequency': freq,
            'load': demand,
            'wind': wind,
            'solar': solar,
            'battery': battery,
            'hydrogen': hydrogen,
            'discount_rate': 5
        }
    return render_template('index.html', settings=settings_dict, country_name=country_name, scenario=scenario)

@app.route('/jobs', methods=['GET','POST'])
def jobs_api():
    if request.method == "POST":
        print(request.headers['Content-Type'])
        print(request.json)
        job = queue.enqueue("solve.solve",request.json, timeout=300)
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
        return {"status" : "Error", "error" : "Failed to find job!"}

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
