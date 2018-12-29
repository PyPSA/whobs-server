
from flask import Flask, request, jsonify, render_template
from flask_restful import Resource, Api


from redis import Redis

import rq
from rq.job import Job
from rq import Queue


conn = Redis.from_url('redis://')

queue = Queue('whobs', connection=conn)


app = Flask(__name__)
api = Api(app)


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
        status = "Waiting for job to run"

    result = {"status" : status}

    if "status" == "Error":
        result.update(job.result)
    elif job.is_finished:
        result.update(job.result)

    print(result)

    return jsonify(result)


if __name__ == '__main__':
    app.run(port='5002')
