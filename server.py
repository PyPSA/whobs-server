
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
        job = queue.enqueue("solve.solve",request.json)
        result = {"jobid" : job.get_id()}
        request.json.update({"jobid" : result["jobid"],
                             "timestamp" : str(datetime.datetime.now())})
        with open('assumptions/assumptions-{}.json'.format(result["jobid"]), 'w') as fp:
            json.dump(request.json, fp)
        return jsonify(result)
    elif request.method == "GET":
        #return number of active jobs
        return "not implemented yet"

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

    if "status" == "Error" or job.is_finished:
        for i in range(10):
            if job.result is not None and job.result != {}:
                result.update(job.result)
                print(result)
                print(type(job.result))
                break
            else:
                print("Results not available on try {}".format(i))
                print(job.result)
                print(type(job.result))
                time.sleep(1)

    return jsonify(result)


if __name__ == '__main__':
    app.run(port='5002')
