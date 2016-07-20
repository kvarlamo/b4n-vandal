#B4N vandal
Script for configuring and testing Brain4Net. Inc. controller services
**This is absolutely unuseful for anybody outside Brain4Net Inc. engineers**

## Prerequisites

You should have python2.X as interpreter. Python 3 not supported.

Install python modules

	apt-get install python-pip
	pip install PyYAML
	pip install argparse
	pip install pprint

Configure network via orchestrator
* add controller(s)
* make cluster of controllers (script will use the first one)
* connect external interfaces referenced by configuration
* add QoS rule (script will use the first one)

## Configure
config.yaml is default config. It divided into sections:
### ORCHESTRATOR settings: orc
* url
* user
* pass

### Variables generator: vars
You can define all vars and their ranges.
Don't declare variables you don't use in services - each service runs over each combination. If you keep unused vars your services will overlap and script will be too slow.

### Services sections: p2p, p2m, m2m
Each service section consists of list of services of each type. Each service has its name and list of service interfaces
You can reference variables defined in vars and apply simple math evaluations (see built-in eval function).
Good idea to add integers that don't allow services overlap.

## Run
Make it executable

    chmod +x vandal.py

Run and see built-in help

    ./vandal.py -h
   
Run with default config.yaml

    ./vandal.py
    
Run with verbose logging:

    ./vandal.py -d
    
Run with another config file:

    ./vandal.py --config=~/1.txt

