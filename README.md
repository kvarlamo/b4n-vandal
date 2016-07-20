**This code is absolutely unuseful for anybody outside Brain4Net Inc. engineering team**

#B4N vandal
Script for template-based configuring P2P, P2M, M2M services and corresponding SIs on Brain4Net controller.
It parses and validates config and controller state, **REMOVES ALL EXISTING SERVICES AND SIS** and creates configured services.

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

YAML-based config divided into sections (dictionaries)

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

### Clone from git
    git clone https://github.com/kvarlamo/b4n-vandal.git
    Cloning into 'b4n-vandal'...
    remote: Counting objects: 66, done.
    remote: Compressing objects: 100% (53/53), done.
    remote: Total 66 (delta 30), reused 39 (delta 8), pack-reused 0
    Unpacking objects: 100% (66/66), done.
    Checking connectivity... done.
    cd b4n-vandal

### Make it executable

    chmod +x vandal.py

### Run and see built-in help

    ./vandal.py -h
   
### Run with default config.yaml

    ./vandal.py
    
### Run with verbose logging:

    ./vandal.py -d
    
### Run with another config file:

    ./vandal.py --config=~/1.txt

