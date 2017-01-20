#!/usr/bin/env python
# encoding: utf-8

import argparse
import sys

import master

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('intf', type=str, help="Network interface")
    args = parser.parse_args()

    master.main(args.intf)
