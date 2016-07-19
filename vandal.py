#!/usr/bin/env python2.7
import yaml, argparse, pprint, logging, re, os, itertools
from pprint import pprint,pformat
from lib.ctlapi import *
logging.basicConfig(format = u'%(levelname)s %(message)s', level=logging.INFO)
logger=logging.getLogger(__name__)
scriptdir=os.path.dirname(os.path.realpath(__file__))
logger.setLevel(logging.DEBUG)

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=file, help='configuration file in YAML format', required=False, default=scriptdir+"/config.yaml", metavar='CONFIGFILE')
    parser.add_argument('-d', action='store_true', help='enable verbose debugging', required=False)
    parser.add_argument('ACTION', nargs='*')
    args = parser.parse_args()
    if args.d:
        logger.setLevel(logging.DEBUG)
    logger.debug("args: %s", pformat(args))
    config = yaml.safe_load(args.config)
    return (args, config)

def config_var_str_to_lists(config):
    # processes var section of config and evaluates strings X-Y to lists
    for var in config['vars'].keys():
        config['vars'][var]=evaluate_str_range(config['vars'][var])
    return config

def evaluate_config(cfg, **kwargs):
    # recursively evaluates all string leafs with  evaluate_str_var() function
    if isinstance(cfg, dict):
        for x in cfg:
            cfg[x] = evaluate_config(cfg[x],**kwargs)
    elif isinstance(cfg, list):
        for x in range(len(cfg)):
            cfg[x] = evaluate_config(cfg[x],**kwargs)
    if isinstance(cfg, str):
        cfg=evaluate_str_var(cfg,**kwargs)
    return cfg

def evaluate_str_range(str):
    # evaluates string records X-Y to list [X .. Y]
    m = re.search(r'^(\d+)\-(\d+)$',str)
    if m:
        return range(int(m.group(1)),int(m.group(2))+1)
    else:
        return str

def evaluate_str_var(eval_str, **kwargs):
    # replaces $var to kwargs key value
    for key in kwargs.keys():
        eval_str=eval_str.replace("$"+key, str(kwargs[key]))
    return eval_str

def make_list_from_dict(input_dict):
    l=[]
    keys = input_dict.keys()
    keys.sort()
    for key in keys:
        d={}
        for val in input_dict[key]:
            d[key]=val
            print "%s %s" % (key,val)
            l.append(d.copy())
    return l

def cartesian_prod(*args):
    print args
    lst=[]
    for i in args:
        ikeys = i.keys()
        ikeys.sort()
        for k in ikeys:
            lst.append(make_list_from_dict(i.fromkeys(k,i[k])))
    list_of_joined_dicts=[]
    for item in itertools.product(*lst):
        joined_dict={}
        for m in item:
            joined_dict.update(m)
        list_of_joined_dicts.append(joined_dict)
    return list_of_joined_dicts





if __name__ == '__main__':
    args, config = parse_args()
    logger.debug("args: %s, config: %s", pformat(args), pformat(config))
    pprint(config)
    config=config_var_str_to_lists(config)
    pprint(config)
    pprint(cartesian_prod(config['vars']))
    #pprint (itertools.product([{'x': 'a'},{'x': 'b'}],[{'y': 'a'},{'y': 'b'}]))
    #config=evaluate_config(config, **{'x':1, 'y':2})
    #pprint(config)
    #rotate(config['vars'])
    exit()
    #resolve_config(config)
    exit()
    c = CtlAPI('http://10.255.148.110:8080/', 'admin', 'admin', logger=logger)
    clusters=(c.get_clusters())
    logger.debug("Got clusters: %s", clusters)
    if len(clusters)<1:
        raise(Exception, "Clusters are not configured")
    logger.debug("Number of clusters: %s", len(clusters))
    switches=c.get_switches_of_cluster(clusters[0]['id'])
    logger.debug("Got switches: %s", switches)
