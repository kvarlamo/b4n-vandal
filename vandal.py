#!/usr/bin/env python2.7
import yaml, argparse, pprint, logging, re, os, itertools, copy
from pprint import pprint,pformat
from lib.ctlapi import *
logging.basicConfig(format = u'%(levelname)s %(message)s', level=logging.DEBUG)
logger=logging.getLogger(__name__)
scriptdir=os.path.dirname(os.path.realpath(__file__))
CFG_VAR_SECTION='vars'
CFG_TEMPLATE_SECTIONS=['p2m','p2p']

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
    for var in config[CFG_VAR_SECTION].keys():
        config[CFG_VAR_SECTION][var]=evaluate_str_range(config[CFG_VAR_SECTION][var])
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

def config_get_template_sections(config,*args):
    #get only template sections from config
    result_config={}
    for sec in config.keys():
        if sec in args:
            result_config[sec]=config[sec]
    return result_config

def eval_configtemplate_to_configs(config, config_values):
    configs = []
    logger.info("Evaluating config templates with vars to configs with exact values")
    for item in config_values:
        configtemplate = copy.deepcopy(config)
        evaluated_config=evaluate_config(configtemplate, **item)
        logger.debug("%s resolved to %s", item, evaluated_config)
        configs.append(evaluated_config)
    return configs

# returns list of switches, parent (Phy) ifaces and SIs ifaces from config
def get_unique_sets(configs):
    logger.info("Extract unique values and analyse resolved config for correctness (SIs should not overlap)")
    all_parent_ifaces=[]
    all_sis=[]
    all_switches = []
    switches=[]
    sis=[]
    parent_ifaces = []
    for cfg in configs:
        for sect in cfg.keys():
            for svclist in cfg[sect]:
                if 'si' in svclist.keys():
                    all_sis.extend(svclist['si'])
                    for item in svclist['si']:
                        all_parent_ifaces.append({'switch':item['switch'],'port':item['port']})
                        all_switches.append(item['switch'])
    for i in all_sis:
        if i in sis:
            logger.warning("configured SIs not unique. %s SIs overlap", i)
        else:
            sis.append(i)
    for i in all_parent_ifaces:
        if i not in parent_ifaces:
            parent_ifaces.append(i)
    for i in all_switches:
        if {'name':i} not in switches:
            switches.append({'name':i})
    logger.debug("Unique SIs: \n%s\n Unique ParentIfs: \n%s\n Unique Switches \n%s\n", sis, parent_ifaces, switches)
    logger.info("Unique SIs: %s, Unique ParentIfs: %s, Unique Switches %s", len(sis), len(parent_ifaces), len(switches))
    return({'switches':switches,'sis':sis,'parent_ifaces':parent_ifaces})

# Check if switches really online and have referenced ports
def check_switches(uniq,actual_switches):
    res_uniq={'switches':[],'parent_ifaces':[]}
    for uniq_sw in uniq['switches']:
        for act_sw in actual_switches:
            if uniq_sw['name'] == act_sw['name']:
                if act_sw['connectionStatus'] == 'CONNECTED':
                    logger.debug("%s exists in topology and Connected",uniq_sw['name'])
                    res_uniq['switches'].append({'name':uniq_sw['name'], 'id': act_sw['id']})
                    #checking ports
                    for parentif_obj in uniq['parent_ifaces']:
                        if parentif_obj['switch'] == act_sw['name']:
                            for act_external_port in act_sw['classifiedPortExternal']:
                                if parentif_obj['port'] == act_external_port['number']:
                                    logger.debug("Port %s on sw %s OK", parentif_obj['port'], uniq_sw['name'])
                                    res_uniq['parent_ifaces'].append({'switch':uniq_sw['name'],'port':parentif_obj['port']})
                                    break
                            else:
                                logger.warning("Port %s on sw %s not found", parentif_obj['port'], uniq_sw['name'])
                else:
                    logger.warning("%s is in topology, but not up" % uniq_sw['name'])
                break
        else:
            logger.warning("%s not found in topology" % uniq_sw['name'])
            # TODO uncomment raise
            #raise(Exception("switch %s not found in topology" % uniq_sw['name']))
    pprint(res_uniq)
    return res_uniq

if __name__ == '__main__':
    #config is python'ed content of YAML configuration, then we resolve X-Y sentences to lists
    args, config = parse_args()
    logger.debug("args: %s, config: %s", pformat(args), pformat(config))
    logger.debug("Original config loaded from file :\n%s",pformat(config))
    #resolve to lists
    config=config_var_str_to_lists(config)
    logger.debug("Config with resolved math shortcuts :\n%s", pformat(config))
    config_combs=cartesian_prod(config[CFG_VAR_SECTION])
    logger.info("Generated combinations:\n%s", pformat(config_combs))
    logger.info("Length of generated combinations: %s items", len(config_combs))
    logger.debug("Config vars combinations are :\n%s", pformat(config_combs))
    # TODO
    tpl_config=config_get_template_sections(config,'p2p', 'p2m')
    logger.debug("Config template:\n%s ", pformat(tpl_config))
    composed_configs=eval_configtemplate_to_configs(tpl_config,config_combs)
    logger.info("Composed configs contain: %s records", len(composed_configs))
    logger.debug("Composed configs dump:\n%s ", pformat(composed_configs))
    uniq=get_unique_sets(composed_configs)
    # begin interaction with orc
    c = CtlAPI(config['orc']['url'], config['orc']['user'], config['orc']['pass'], logger=logger)
    clusters=(c.get_clusters())
    logger.debug("Got clusters: %s", clusters)
    if len(clusters)<1:
        raise(Exception, "Clusters are not configured")
    logger.debug("Number of clusters: %s", len(clusters))
    if len(clusters) > 1:
        logger.warning("There is more than one cluster! We hope we are in luck")
    switches=c.get_switches_of_cluster(clusters[0]['id'])
    logger.debug("Got switches: %s", pformat(switches))
    check_switches(uniq,switches)
