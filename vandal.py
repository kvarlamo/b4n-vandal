#!/usr/bin/env python2.7
import yaml, argparse, pprint, logging
from pprint import pprint,pformat
logging.basicConfig(format = u'%(filename)s:%(lineno)d %(message)s', level=logging.INFO)
logger=logging.getLogger("log")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=file, help='configuration file in YAML format', required=False, default="config.yaml", metavar='CONFIGFILE')
    parser.add_argument('-d', action='store_true', help='enable verbose debugging', required=False)
    parser.add_argument('ACTION', nargs='*')
    args = parser.parse_args()
    if args.d:
        logger.setLevel(logging.DEBUG)
    logger.debug("args: %s", args)
    config = yaml.safe_load(args.config)
    return (args, config)

if __name__ == '__main__':
    args, config = parse_args()
    logger.debug("args: %s, config: %s", args, config)