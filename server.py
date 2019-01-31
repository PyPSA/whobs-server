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




from flask import Flask, request, jsonify, render_template


from redis import Redis

import rq
from rq.job import Job
from rq import Queue

import time, datetime

import json

conn = Redis.from_url('redis://')

queue = Queue('whobs', connection=conn)


app = Flask(__name__)


@app.route('/')
def root():
    return render_template('index.html')

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
