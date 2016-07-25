**This code is absolutely unuseful for anybody outside Brain4Net Inc. engineering team**

#B4N vandal
Script for templating P2P, P2M, M2M services on Brain4Net controller.

## Prerequisites

Install python modules

	apt-get install python-pip
	pip install PyYAML
	pip install argparse
	pip install pprint

Configure network via orchestrator
* add controller(s)
* make cluster of controllers
* connect external interfaces referenced by configuration
* add QoS rule (script will use the first one)

## Get 

### Clone from git
    git clone https://github.com/kvarlamo/b4n-vandal.git
    Cloning into 'b4n-vandal'...
    remote: Counting objects: 66, done.
    remote: Compressing objects: 100% (53/53), done.
    remote: Total 66 (delta 30), reused 39 (delta 8), pack-reused 0
    Unpacking objects: 100% (66/66), done.
    Checking connectivity... done.
    cd b4n-vandal

## Configure

Default config file is "config.yaml". You can point to any other file with --config option
YAML-based config divided into sections (dictionaries). 

### Orchestrator settings section: orc
* url
* user
* pass

### Variables generator section: vars
You can define any vars and their ranges.
For most cases just one var will be enough.

### Services sections: p2p, p2m, m2m
Each service section consists of list of services of each type. Each service has its name and list of service interfaces
You can reference variables defined in vars as $var and apply simple math evaluations $var+1 or Service_$var

## Run

### Run and read built-in help

    ./vandal.py -h
   
### Start with default config and push it:

    ./vandal.py add
    
### The same with verbose logging:

    ./vandal.py -d add
    
### Run with another config file:

    ./vandal.py --config=~/1.txt add
    
### Delete services and SIs:

    ./vandal.py del


