
# Ubuntu 14.04

Ubuntu 14.04 is the recommended OS to install talus on. Installation on this
OS should be very straightforward and should be completed solely by running
the install script.

# Ubuntu 15.10 Installation Attempts

Run the install script. It will fail, but it will setup directories and place the
`talus_master` upstart script in /etc/init/. Then continue on with this:

Ubuntu 15.X uses `systemd`, we need to switch it back to upstart:

	sudo apt-get install upstart-sysv
	sudo update-initramfs -u
	# maybe reboot too

Install all of the following:

	sudo apt-get install \
		libxml2 libxml2-dev \
		libdevmapper-dev \
		libnl-3-dev libnl-3-200 \
		libnl-nf-3-200 libnl-nf-3-dev \
		libnl-route-3-200 libnl-route-3-dev \
		libnl-genl-3-200 libnl-genl-3-dev \
		apparmor-utils \
		python python-pip \
		ebtables \
		qemu-utils virtinst qemu-kvm

Compile and install `libvirt 1.2.20`, specifying that it should use libpcap, upstart for the
init system, and `/usr` as the prefix:

	(
		cd /tmp ; \
		wget http://libvirt.org/sources/libvirt-1.2.20.tar.gz ; \
		tar -xzf libvirt-1.2.20.tar.gz ; \
		cd libvirt-1.2.20 ; \
		./configure --prefix=/usr --with-libpcap --with-init-system=upstart; \
		make -j 8 ; \
		sudo make install ; \
		sudo /etc/init.d/libvirt-bin stop ; \
		sudo /etc/init.d/libvirt-bin start
	)

This (in my testing) will create an upstart script in /etc/event.d/libvirtd. Move this to
/etc/init/libvirtd.conf:

	sudo mv /etc/event.d/libvirtd /etc/init/libvirtd.conf

Now install some more python stuff:

	sudo apt-get install python-libvirt
	sudo pip install netifaces
	sudo pip install \
		mongoengine \
		mock \
		netifaces \
		paramiko \
		pika \
		pymongo==2.8.0 \
		pywinrm \
		scp \
		sh \
		twisted \
		xmltodict
