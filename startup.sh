#!/bin/bash

mkdir -p /talus/logs/master
mkdir -p /talus/data/master

#!/bin/bash
set -e

# Create the kvm node (required --privileged)
if [ ! -e /dev/kvm ]; then
	mknod /dev/kvm c 10 $(grep '\<kvm\>' /proc/misc | cut -f 1 -d' ')	
fi

# If we have a BRIDGE_IF set, add it to /etc/qemu/bridge.conf
if [ -n "$BRIDGE_IF" ]; then
	echo "allow $BRIDGE_IF" >/etc/qemu/bridge.conf

	# Make sure we have the tun device node
	if [ ! -e /dev/net/tun ]; then
		mkdir -p /dev/net
		mknod /dev/net/tun c 10 $(grep '\<tun\>' /proc/misc | cut -f 1 -d' ')
	fi
fi

# Configure default group and ownership to set root/www-data to be default

grep "^user.*=root$" /etc/libvirt/qemu.conf
if [ $? -ne 0 ]; then
    echo "user = \"root\"" >> /etc/libvirt/qemu.conf
fi
grep "^group.*=www-data$" /etc/libvirt/qemu.conf
if [ $? -ne 0 ]; then
    echo "group = \"www-data\"" >> /etc/libvirt/qemu.conf
fi
grep "^dynamic ownership.*=0$" /etc/libvirt/qemu.conf
if [ $? -ne 0 ]; then
    echo "dynamic_ownership = 1" >> /etc/libvirt/qemu.conf
fi

libvirtd -d

python -m master
