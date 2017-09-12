#!/usr/bin/env python
# encoding: utf-8


"""
This module handles the processing of insertion, updates,
and deletion of Job documents in the MongoDB database.
"""


import bson
import os
import sys
import uuid


import master.models
import master.lib.webhooks as webhooks
from master.lib.jobs import JobManager
from master.watchers import WatcherBase
from master.lib.amqp_man import AmqpManager


class JobWatcher(WatcherBase):
    """The watcher for the ``talus.job`` collection in the database.
    """

    collection = "talus.job"

    def __init__(self, *args, **kwargs):
        WatcherBase.__init__(self, *args, **kwargs)

        self._job_man = JobManager()
        # this needs to be continuously running
        self._job_man.start()

        for job in master.models.Job.objects(status__name__in=["run", "stop", "cancel"]):
            self._handle_status(job.id, job=job)

    def stop(self):
        """Stop the JobWatcher"""
        self._job_man.stop()

    def insert(self, id_, obj):
        self._log.debug("handling insert")

        new_status=None
        if "status" in obj and "name" in obj["status"]:
            new_status = obj["status"]["name"]

        self._handle_status(id_, obj, new_status=new_status)

    def update(self, id, mod):
        self._log.debug("handling update {} {}".format(id, mod))

        # if the status is being updated, fire off a new webhook
        # status being modified should look like this:
        # {'$set': {'status': {'name': 'running'}}}
        #
        # NOTE that _handle_status is intended to fire
        if "$set" not in mod:
            return
        if "status" not in mod["$set"]:
            return
        if "name" not in mod["$set"]["status"]:
            return

        new_status = mod["$set"]["status"]["name"]
        self._handle_status(id, mod, new_status=new_status)
    
    def delete(self, id):
        self._log.debug("handling delete")

        #self._handle_status(id)

    # -----------------------

    def _handle_status(self, id_, obj=None, job=None, new_status=None):
        self._log.info("handling updated job status: {!r}".format(new_status))

        switch = {
            "run"    : self._handle_run,
            "stop"   : self._handle_stop,
            "cancel" : self._handle_cancel,
        }

        if job is None:
            jobs = master.models.Job.objects(id=id_)
            if len(jobs) == 0:
                self._log.debug("_handle_status failed to find job {}".format(id_))
                return
            job = jobs[0]

        self._log.info("triggering webhook for job status change (job: {}, status: {!r})".format(
            job.id,
            new_status,
        ))
        webhooks.trigger("job", new_status, job)

        self._log.debug("_handle_status status is {}".format(job.status["name"]))
        if job.status["name"] in switch:
            switch[job.status["name"]](id_, job)

    def _handle_run(self, id_, job):
        """Handle running a job
        """
        self._log.info("handling job runnage")

        if job.image.status["name"] != "ready":
            self._log.warn("Image is not in a ready state! cannot run the job yet, cancelling")
            job.status = {"name": "cancelled", "desc": "image not ready"}
            job.save()
            return

        self._job_man.run_job(job)

        job.status = {
            "name": "running"
        }
        job.save()

    def _handle_stop(self, id_, job):
        """Handle stopping a job - to be used only for internal purposes. Not
        really intended for a user to be able to set this.
        """
        self._log.info("handling job cancellation")

        job.status = {
            "name": "stopping"
        }
        job.save()

        self._job_man.stop_job(job)

    def _handle_cancel(self, id_, job):
        """Handle cancelling a job
        """
        self._log.info("handling job cancellation")

        job.status = {
            "name": "cancelling"
        }
        job.save()

        self._job_man.cancel_job(job)
