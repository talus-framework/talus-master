#!/usr/bin/env python
# encoding: utf-8


import bson
import logging
import os
from sh import md5sum
import sys
import time
import uuid


import master.models
from master.lib.vm.manage import VMManager
from master.watchers import WatcherBase

logging.getLogger("sh").setLevel(logging.WARN)


class VMWatcher(WatcherBase):
    collection = "talus.image"

    def __init__(self, *args, **kwargs):
        WatcherBase.__init__(self, *args, **kwargs)

        self._vm_manager = master.lib.vm.manage.VMManager(on_worker_exited=self._on_worker_exited)

        for img in master.models.Image.objects(status__name__in=["import", "configure", "create", "delete"]):
            self._handle_status(img.id, image=img)

    def insert(self, id_, obj):
        self._log.debug("handling insert")

        self._handle_status(id_, obj)

    def update(self, id, mod):
        self._log.debug("handling update")

        self._handle_status(id, mod)

    def delete(self, id):
        self._log.debug("handling delete")

        # self._handle_status(id)

    # -----------------------

    def _on_worker_exited(self):
        from master import Master
        Master.instance().update_status(vms=self._get_running_vms())

    def _handle_status(self, id_, obj=None, image=None):
        switch = {
            "import"     : self._handle_import,
            "configure"  : self._handle_configure,
            "create"     : self._handle_create,
            "delete"     : self._handle_delete,
            "iso-create" : self._handle_iso_create,
        }

        if image is None:
            images = master.models.Image.objects(id=id_)
            if len(images) == 0:
                return
            image = images[0]

        if image.status["name"] in switch:
            switch[image.status["name"]](id_, image)

    def _get_running_vms(self):
        vms = []
        for worker in self._vm_manager._workers.values():
            vms.append(worker.get_vnc_info())
        return vms

    def _handle_iso_create(self, id_, image):
        """Handle creating a new VM from scratch using the iso provided in
        the state object.
        """
        self._log.info("creating new image using iso")

        iso_id = bson.ObjectId(image.status["iso"])
        iso_file = master.models.TmpFile.objects(id=iso_id)[0]

        if iso_file.path.startswith("/"):
            iso_file.path = iso_file.path[1:]

        iso_path = os.path.join("/tmp/talus", iso_file.path)
        if not os.path.exists(iso_path):
            self._log.warn("cannot locate iso {!r} for image {!r} creation".format(
                iso_file.path,
                image.name,
            ))
            iso_file.delete()
            image.status = {
                "name": "iso-create error",
            }
            image.save()
            return

        vnc_info = self._vm_manager.create_from_iso(
            iso_path    = iso_path,
            #vagrantfile = image.status.setdefault("vagrantfile", None),
            image_name  = str(image.id),
            username    = image.username,
            password    = image.password,
            on_success  = self._set_image_ready,
        )

        from master import Master
        Master.instance().update_status(vms=self._get_running_vms())

        if os.path.exists(iso_file.path):
            os.remove(iso_file.path)
        iso_file.delete()

        image.status = {
            "name": "configuring",
            "vnc": vnc_info,
        }
        image.save()

        self._log.info("new VM is starting up with iso {!r}, ready for initial configuration\n    {!r}".format(
            os.path.basename(iso_path),
            vnc_info,
        ))

    def _handle_import(self, id_, image):
        """This is the initial step when importing an image from the API. The API
        will insert a new Image document into the database with status["name"] set to
        "importing"
        """
        self._log.info("Importing image {}".format(image.id))

        image_to_import = bson.ObjectId(image.status["tmpfile"])
        tmp_file = master.models.TmpFile.objects(id=image_to_import)[0]

        if tmp_file.path.startswith("/"):
            tmp_file.path = tmp_file.path[1:]

        image_path = os.path.join("/tmp/talus", tmp_file.path)
        if not os.path.exists(image_path):
            self._log.warn("Cannot import image: {!r}, image to import not found ({})".format(
                image.name,
                tmp_file.path
            ))
            tmp_file.delete()
            image.status = {
                "name": "import_error"
            }
            image.save()
            return

        vnc_info = self._vm_manager.import_image(
            image_path,
            str(image.id), # image name
            user_interaction = True,
            username         = image.username,
            password         = image.password,
            on_success       = self._set_image_ready
        )

        from master import Master
        Master.instance().update_status(vms=self._get_running_vms())

        if os.path.exists(tmp_file.path):
            os.remove(tmp_file.path)
        tmp_file.delete()

        image.status = {
            "name": "configuring",
            "vnc": vnc_info
        }
        image.save()

        self._log.info("image is imported and running, ready for initial configuration:\n\t{!r}".format(vnc_info))

    def _handle_configure(self, id_, image):
        """Configure the image (spin it up, let the user muck around in it, commit all changes
        back into the original image)
        """
        child_snapshots = master.models.Image.objects(base_image=image.id)
        if len(child_snapshots) > 0:
            self._log.warn("ERROR! ILLEGAL OPERATION! I WILL NOT MODIFY AN IMAGE WITH {} DEPENDENT SNAPSHOTS!".format(
                len(child_snapshots)
            ))
            image.status = {"name": "ready"}
            return

        vagrantfile = image.status.setdefault("vagrantfile", None)
        user_interaction = image.status.setdefault("user_interaction", False)

        vnc_info = self._vm_manager.configure_image(
            str(image.id),
            vagrantfile      = vagrantfile,
            user_interaction = user_interaction,
            on_success       = self._set_image_ready,
            kvm              = image.status["kvm"]
        )
        self._log.debug("got vnc info from configure image: {!r}".format(vnc_info))

        from master import Master
        Master.instance().update_status(vms=self._get_running_vms())

        image = master.models.Image.objects(id=image.id)[0]
        if user_interaction:
            image.status = {
                "name": "configuring",
                "vnc": vnc_info
            }
            image.save()

    def _handle_create(self, id_, image):
        """Handle creating a new VM based on an existing VM
        """
        self._log.info("creating an image")

        base = image.base_image
        dest_name = image.name
        vagrantfile = image.status.setdefault("vagrantfile", None)
        user_interaction = image.status.setdefault("user_interaction", False)

        vnc_info = self._vm_manager.create_image(
            vagrantfile,
            base_name        = str(base.id),
            dest_name        = str(image.id),
            user_interaction = user_interaction,
            on_success       = self._set_image_ready
        )

        from master import Master
        Master.instance().update_status(vms=self._get_running_vms())

        image = master.models.Image.objects(id=image.id)[0]
        if user_interaction:
            image.status = {
                "name": "configuring",
                "vnc": vnc_info
            }
            image.save()

    def _handle_delete(self, id_, image):
        """Handle deleting an image from the DB and on disk"""
        child_images = master.models.Image.objects(base_image=image.id)

        if len(child_images) > 0:
            image.status = {
                "name": "ready",
                "error": "image has child images, can't delete"
            }
            image.save()
        else:
            self._vm_manager.delete_image(str(image.id))
            image.delete()

    # -----------------------

    def _set_image_ready(self, image_name):
        """Update the image named 'image_name' with a ready status. This SHOULD only
        be called once the image has been imported, initially configured, and then
        successfully shutdown.

        :image_name: The name of the image to update to ready status
        """
        self._log.info("operation for image {!r} completed successfully!".format(image_name))

        images = master.models.Image.objects(id=image_name)
        if len(images) == 0:
            self._log.warn("Could not set image named {!r} as ready, not found in database!".format(image_name))
            return

        self._log.debug("images: {} ({!r})".format(images, image_name))
        image = images[0]
        self._log.debug("image: {}".format(image))
        image.status = {"name": "ready"}

        path = "/var/lib/libvirt/images/{}_vagrant_box_image_0.img".format(str(image.id))
        if not os.path.exists(path):
            path = os.path.join(
                os.path.expanduser("~"),
                ".vagrant.d",
                "boxes",
                str(image.id),
                "0",
                "libvirt",
                "box.img"
            )

        self._log.info("recalculating md5 of image found at {}".format(path))

        if not os.path.exists(path):
            self._log.warn("Could not find valid path for image {} to update md5".format(str(image.id)))
            return

        md5, _ = md5sum(path).split()

        self._log.info("new md5: {}".format(md5))
        image.md5 = md5
        image.timestamps["modified"] = time.time()
        image.save()

        self._log.info("updated md5 for image {!r}".format(image_name))
