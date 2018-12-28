



To run locally you need to start the Python Flask server in one terminal, and redis in another:

Start the Flask server in one terminal with:

`python flask_queue.py`

This will serve to local address:

http://127.0.0.1:5002/

In the second terminal start Redis:

`rq worker microblog-tasks`

where `microblog-tasks` is the name of the queue. No jobs will be
solved until this is run. You can run multiple workers to process jobs
in parallel.