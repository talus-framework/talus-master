#!/usr/bin/env python
# encoding: utf-8

import gridfs
import json
import os
from StringIO import StringIO
import sys
import tabulate
import zipfile

import master.watchers.result_processors as processors
from master.models import *

try:
    import master.watchers.result_processors.crash_task_maker as crash_task_maker
except ImportError as e:
    crash_task_maker = None


class CrashProcessor(processors.ResultProcessorBase):
    """A simple crash processor
    """

    def can_process(self, result):
        """Return True/False if the result is a crash result
        """
        self._log.info("result type: {!r}".format(result.type))
        return result.type == "crash"

    def delete_result(self, result):
        """Completely Delete a result
        """
        fs = gridfs.GridFS(result._collection.database)
        for repro in result.data.setdefault("repro", []):
            fs.delete(repro)

        result.delete()

    def process(self, result):
        """Process the crash result

        :param mongoengine.Document result: The result to process
        """
        self._log.info("processing crash")

        if Result.objects(data__hash_major=result.data["hash_major"],
                          data__hash_minor=result.data["hash_minor"]).count() > 50:
            self._log.debug("removing unneeded crash result ({}:{} hash)".format(result.data["hash_major"],
                                                                                 result.data["hash_minor"]))
            self.delete_result(result)
            return

        self._log.debug("CREATING NEW TASK FOR CRASH!!!")

        if crash_task_maker is None:
            return

        try:
            is_blacklisted = crash_task_maker.is_blacklisted(result)
        except:
            self._log.exception("ERROR CHECKING BLACKLISTS")
            return

        if is_blacklisted:
            self._log.info("crash has been blacklisted, deleting it")
            self.delete_result(result)
            return

        if Result.objects(data__hash_major=result.data["hash_major"],
                          data__hash_minor=result.data["hash_minor"]).count() == 1:
            try:
                crash_task_maker.create_crash_task(result)
            except:
                self._log.exception("ERROR CREATING CRASH TASK!")
