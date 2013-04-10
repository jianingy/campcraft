#!/bin/sh

PYTHON="$(which 2>/dev/null /home/tops/bin/python /usr/local/bin/python2 /usr/bin/python2 /static-python)"
exec $PYTHON $(dirname $0)/camp.py $@
