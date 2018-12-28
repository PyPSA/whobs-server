
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


#For regular pages, use this pattern
@app.route('/')
def root():
    return render_template('index.html')


#For restful API pages, use this pattern
class Solve(Resource):
    def get(self,country,wind_cost):
        job = queue.enqueue("solve.solve",country,wind_cost)
        result = {"jobid" : job.get_id()}
        return jsonify(result)

class Poll(Resource):
    def get(self,jobid):
        job = Job.fetch(jobid, connection=conn)
        try:
            return job.meta['progress']
        except:
            return "Job not running"

class Final(Resource):
    def get(self,jobid):
        job = Job.fetch(jobid, connection=conn)
        if job.is_finished:
            return jsonify(job.result)
        else:
            return "Nay!", 202



class Coordinates(Resource):
    def get(self,lat,lng):
        lat = float(lat)
        lng = float(lng)
        result = {"lat" : lat,
                  "lng" : lng,
                  "product" : lat*lng}
        return jsonify(result)


api.add_resource(Solve, '/solve/<country>/<wind_cost>')
api.add_resource(Poll, '/poll/<jobid>')
api.add_resource(Final, '/final/<jobid>')
api.add_resource(Coordinates, '/coordinates/<lat>/<lng>')


if __name__ == '__main__':
    app.run(port='5002')
