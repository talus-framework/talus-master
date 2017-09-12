#!/usr/bin/env python
# encoding: utf-8


from mongoengine import *
import datetime
import os


def do_connect():
    # this is to be set by whatever starts the master docker container
    talus_env = os.environ["TALUS_DB_PORT_27017_TCP"].replace("tcp://", "")
    talus_host, talus_port = talus_env.split(":")
    talus_port = int(talus_port)

    connect("talus", host=talus_host, port=talus_port)


class Webhook(Document):
    """Defines user-controlled webhooks that will trigger on a specific
    event. The related/affected database model's JSON will be sent in an
    HTTP POST request to the specified url.
    """
    type = StringField(required=True)
    """The type of event to watch. Must be one of:

      * ``job`` - will trigger when the job's status changes
    """
    url = StringField(required=True)
    """The url to send the webhook to. Only http and https url-schemes are
    supported.
    """
    auth_string = StringField(required=False, default=None)
    """An authorization string to send along with the ``POST`` request. This
    value will be appended to url as a url-parameter with the name ``auth``.

    E.g.:

    .. code-block:: text

       http://your.domain/webhooks/talus?auth=AUTH_STRING
    """
    verify_ssl = BooleanField(default=True)
    """Whether ssl certificates should be verified.
    """


class Result(Document):
    job     = ReferenceField("Job", required=True)
    type    = StringField(required=True)
    tool    = StringField(required=True)
    data    = DictField()
    created = DateTimeField(default=datetime.datetime.now)
    tags    = ListField(StringField())
    slave   = StringField(required=False, default="unknown")


class Code(Document):
    name       = StringField(unique_with="type")
    type       = StringField()
    params     = ListField()
    bases      = ListField()
    desc       = StringField()
    timestamps = DictField()
    tags       = ListField(StringField())


class Task(Document):
    name       = StringField(unique_with="tool")
    tool       = ReferenceField("Code", required=True)
    image      = ReferenceField("Image", required=False)
    params     = DictField()
    version    = StringField() # intended to be used for git versioning
    timestamps = DictField()
    limit      = IntField(default=1)
    vm_max     = IntField(default=30*60)
    # see #28 - specify amount of ram/cpu needed for the job
    vm_ram     = IntField(default=1024, required=False)
    vm_cpu     = IntField(default=1, required=False)
    network    = StringField()
    tags       = ListField(StringField())


class JobError(EmbeddedDocument):
    message   = StringField()
    backtrace = StringField()
    logs      = ListField(StringField())


class Job(Document):
    name       = StringField()
    task       = ReferenceField("Task", required=True)
    params     = DictField()
    status     = DictField()
    timestamps = DictField()
    queue      = StringField()
    priority   = IntField(default=50) # 0-100
    limit      = IntField(default=1)
    progress   = IntField(default=0)
    image      = ReferenceField("Image", required=True)
    network    = StringField()
    debug      = BooleanField(default=False)
    vm_max     = IntField(default=30*60)
    # see #28 - specify amount of ram/cpu needed for the job
    vm_ram     = IntField(default=1024, required=False)
    vm_cpu     = IntField(default=1, required=False)
    errors     = ListField(EmbeddedDocumentField(JobError))
    logs       = ListField(EmbeddedDocumentField(JobError))
    tags       = ListField(StringField())


class FileSet(Document):
    name       = StringField()
    files      = ListField()

    # created, modified
    timestamps = DictField()

    # for use when it's the result set output of a job
    job        = ReferenceField("Job", required=False)
    tags       = ListField(StringField())


class TmpFile(Document):
    path       = StringField(unique=True)


class OS(Document):
    name    = StringField(unique=True)
    version = StringField()
    type    = StringField()
    arch    = StringField()
    tags    = ListField(StringField())


class Image(Document):
    name       = StringField(unique=True)
    os         = ReferenceField('OS', required=True)
    desc       = StringField(default="desc", required=False)
    tags       = ListField(StringField())
    status     = DictField()
    base_image = ReferenceField('Image', null=True, required=False)
    username   = StringField(required=True, default="user")
    password   = StringField(required=True, default="password")
    md5        = StringField(required=False, null=True, default=None)
    timestamps = DictField()


class Master(Document):
    hostname = StringField(unique=True)
    ip       = StringField()
    vms      = ListField(DictField())
    queues   = DictField()


class Slave(Document):
    meta = {
        "indexes": [
            {
                "fields"             : ["timestamps.modified"],
                "expireAfterSeconds" : 60,
            }
        ]
    }

    hostname       = StringField()
    uuid           = StringField()
    ip             = StringField()
    max_vms        = IntField(default=1)
    max_ram        = IntField(default=1, required=False)
    max_cpus       = IntField(default=1, required=False)
    used_ram       = IntField(default=0, required=False)
    used_cpus      = IntField(default=0, required=False)
    running_vms    = IntField(default=0)
    total_jobs_run = IntField(default=0)
    vms            = ListField(DictField())
    timestamps     = DictField()
