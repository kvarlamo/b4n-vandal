#!/usr/bin/env python2.7
import yaml, argparse, pprint, logging, re, os
from pprint import pprint,pformat
#logging.basicConfig(format = u'%(filename)s:%(lineno)d %(message)s', level=logging.INFO)
logging.basicConfig(format = u'%(levelname)s %(message)s', level=logging.INFO)
logger=logging.getLogger("log")
scriptdir=os.path.dirname(os.path.realpath(__file__))

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=file, help='configuration file in YAML format', required=False, default=scriptdir+"/config.yaml", metavar='CONFIGFILE')
    parser.add_argument('-d', action='store_true', help='enable verbose debugging', required=False)
    parser.add_argument('ACTION', nargs='*')
    args = parser.parse_args()
    #if args.d: TODO uncomment for conditional debug
    logger.setLevel(logging.DEBUG)
    logger.debug("args: %s", pformat(args))
    config = yaml.safe_load(args.config)
    return (args, config)

def resolve_vars(config):
    list_of_tuples=[]
    evaled={'x': eval(config['vars']['x']), 'y': eval(config['vars']['x']), 'z':eval(config['vars']['z'])}
    logger.info("Number of items in lists: x: %s, y: %s, z: %s", len(evaled['x']), len(evaled['y']),len(evaled['z']))
    for x in eval(config['vars']['x']):
        for y in eval(config['vars']['y']):
            for z in eval(config['vars']['z']):
                list_of_tuples.append({'x':x, 'y':y, 'z':z})
    logger.info("Generated %s combinations", len(list_of_tuples))
    logger.debug("Tuples list:\n %s" % pformat(list_of_tuples))
    return list_of_tuples



if __name__ == '__main__':
    args, config = parse_args()
    logger.debug("args: %s, config: %s", pformat(args), pformat(config))
    resolve_vars(config)
#    for varname in config['vars']:
#        exec(varname + " = " + (config['vars'][varname]))
#    logger.debug(secvlan)