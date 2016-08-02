#!/usr/bin/env python2.7
import yaml, argparse, pprint, logging, re, os, itertools, copy, time
from pprint import pprint,pformat
import Queue
import threading
from lib.ctlapi import *
import signal, sys
logging.basicConfig(format = u'%(levelname)s %(message)s', level=logging.INFO)
logger=logging.getLogger(__name__)
scriptdir=os.path.dirname(os.path.realpath(__file__))
CFG_VAR_SECTION='vars'
SUPPORTED_SERVICES=['p2m','p2p','m2m']
start_time=time.time()

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=file, help='configuration file in YAML format', required=False, default=scriptdir+"/config.yaml", metavar='CONFIGFILE')
    parser.add_argument('-d', action='store_true', help='enable verbose debugging', required=False)
    parser.add_argument('ACTION', nargs='?')
    args = parser.parse_args()
    if args.d:
        logger.setLevel(logging.DEBUG)
    logger.debug("args: %s", pformat(args))
    config = yaml.safe_load(args.config)
    return (args, config)

def compose_config():
    global uniq, flat_cfg, config
    logger.debug("Original config loaded from file :\n%s",pformat(config))
    #resolve to lists
    config=config_var_str_to_lists(config)
    logger.debug("Config with resolved math shortcuts :\n%s", pformat(config))
    config_combs=cartesian_prod(config[CFG_VAR_SECTION])
    logger.debug("Generated combinations:\n%s", pformat(config_combs))
    logger.info("Length of generated combinations: %s items", len(config_combs))
    logger.debug("Config vars combinations are :\n%s", pformat(config_combs))
    tpl_config=config_get_template_sections(config,*SUPPORTED_SERVICES)
    logger.debug("Config template:\n%s ", pformat(tpl_config))
    composed_configs=eval_configtemplate_to_configs(tpl_config,config_combs)
    logger.info("Composed configs contain: %s tuples (vars combinations)", len(composed_configs))
    logger.debug("Composed configs dump:\n%s ", pformat(composed_configs))
    uniq=get_unique_sets(composed_configs)
    flat_cfg = flatten_composed_configs(composed_configs)

def validate_cfg_against_controller():
    # begin interaction with orc
    global c, cluster_id, default_qos, switches, qoslist
    logger.info("Validated generated configs against network configuration..")
    logger.info("Conneting to Orchestrator %s", config['orc']['url'])
    c = CtlAPI(config['orc']['url'], config['orc']['user'], config['orc']['pass'], logger=logger)
    logger.info("Connected. Getting clusters")
    clusters=c.get_clusters()
    logger.debug("Got clusters: %s", clusters)
    if len(clusters)<1:
        raise Exception("Clusters are not configured")
    logger.debug("Number of clusters: %s", len(clusters))
    if len(clusters) > 1:
        logger.warning("There is more than one cluster! We hope we are in luck")
    cluster_id=clusters[0]['id']
    logger.info("Current cluster ID: %s", cluster_id)
    logger.info("Checking if QoS configured - we need at least one profile")
    qos_profiles = c.get_qos(clusters[0]['id'])
    if len(qos_profiles) > 0:
        logger.debug("QOS rules are already configured %s", qos_profiles)
        logger.info("We-ll use first rule as default: %s", qos_profiles[0])
    else:
        logger.warning("QOS Rules not configured: %s", qos_profiles)
        raise Exception("QOS Rules not configured")
    default_qos = qos_profiles[0]
    qoslist = qos_profiles
    logger.debug("Default QOS profile: %s", default_qos)
    logger.info("Getting switches configurations...")
    switches=c.get_switches_of_cluster(cluster_id)
    logger.debug("Got switches: %s", pformat(switches))
    logger.info("%s switches there", len((switches)))
    check_switches(uniq,switches)
    check_qos()

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
    m = re.search(r'^(\d+)::(\d+)$',str)
    if m:
        return range(int(m.group(1)),int(m.group(2))+1)
    else:
        return str

def evaluate_str_var(eval_str, **kwargs):
    # replaces $var to kwargs key value
    for key in kwargs.keys():
        eval_str=eval_str.replace("$"+key, str(kwargs[key]))
        try:
            eval_str=str(eval(eval_str))
        except:
            pass
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
    logger.info("Checking if switches really online and have referenced ports")
    res_uniq={'switches':[],'parent_ifaces':[]}
    for uniq_sw in uniq['switches']:
        for act_sw in actual_switches:
            if uniq_sw['name'] == act_sw['name']:
                if act_sw['connectionStatus'] == 'CONNECTED':
                    logger.info("%s exists in topology and Connected",uniq_sw['name'])
                    res_uniq['switches'].append({'name':uniq_sw['name'], 'id': act_sw['id']})
                    logger.info("Polling switches for ports")
                    for parentif_obj in uniq['parent_ifaces']:
                        if parentif_obj['switch'] == act_sw['name']:
                            try:
                                for act_external_port in act_sw['classifiedPortExternal']:
                                    if parentif_obj['port'] == act_external_port['number']:
                                        logger.debug("Port %s on sw %s OK", parentif_obj['port'], uniq_sw['name'])
                                        res_uniq['parent_ifaces'].append({'switch':uniq_sw['name'],'port':parentif_obj['port']})
                                        break
                                else:
                                    logger.warning("Port %s on sw %s not found", parentif_obj['port'], uniq_sw['name'])
                            except TypeError:
                                pass
                else:
                    logger.warning("%s is in topology, but not up" % uniq_sw['name'])
                break
        else:
            logger.warning("%s not found in topology" % uniq_sw['name'])
            raise(Exception("switch %s not found in topology" % uniq_sw['name']))
    return res_uniq


# Check if cluster has all QoS profles referenced by configuration
def check_qos():
    global qos_by_name
    for cfg in flat_cfg:
        if 'qos' in cfg.keys() and cfg['type']=='p2p':
            qos_by_name[cfg['qos']] = None
        else:
            for si in cfg['si']:
                if 'qos' in si.keys():
                    qos_by_name[si['qos']] = None
    for cfg_qosname in qos_by_name.keys():
        for actual_qosrule in qoslist:
            if actual_qosrule['name'] == cfg_qosname:
                qos_by_name[cfg_qosname] = actual_qosrule
                break
        else:
            raise Exception("No QoS profile %s in system" % cfg_qosname)
    return


# make a single list of all services with type
def flatten_composed_configs(composedcfg):
    flatten=[]
    for i in composedcfg:
        for type in i.keys():
            if type in SUPPORTED_SERVICES:
                for k in i[type]:
                    k['type']=type
                    flatten.append(k)
            else:
                logger.warning("Unknown service type %s", type)
                raise(Exception("Unknown service type %s" % type))
    return flatten

def normalize_services(svc):
    """add missing parameters for each type of services"""
    newsvc=[]
    for s in svc:
        if s['type']=='p2p':
            s['obj']={"tunnelType": "STATIC", "pathfinding": "SHORTEST_PATH", "symmetry": "SYMMETRIC", "name": s['name'],
               "src": None, "dst": None}
            if "reserveSI" in s.keys():
                s['obj']["reservePathfinding"]=s['obj']["pathfinding"]
                s['obj']["reserveTransitCommutators"]=[]
                s['obj']["hasReserve"] = True
            if "qos" in s.keys():
                s['obj']['qos'] = qos_by_name[s['qos']]['id']
            else:
                s['obj']['qos'] = default_qos['id']
            newsvc.append(s)
        elif s['type']=='m2m':
            s['obj'] = {
                "sessionIdleTimeout": 10,
                "tunnelIdleTimeout": 60,
                "macIdleTimeout": 300,
                "macTableSize": 100,
                "rows": [],
                "name": s['name']}
            newsvc.append(s)
        elif s['type']=='p2m':
            s['obj'] = {
                "sessionIdleTimeout": 10,
                "tunnelIdleTimeout": 60,
                "macIdleTimeout": 300,
                "macTableSize": 100,
                "rows": [],
                "name": s['name']}
            newsvc.append(s)
        else:
            pass
    return newsvc

def normalize_si(si):
    if 'secondVlan' in si.keys():
        si['tagType'] = "DOUBLE_VLAN"
    elif "vlan" in si.keys():
        si['tagType'] = "VLAN"
    else:
        logger.warning(
            "SI doesn't contain neither vlan nor second Vlan, so we can't assign tagType. UNTAGGED ifaces not supported")
    si["commutatorId"] = get_switch_id_by_name(si['switch'])
    if 'qos' in si.keys():
        si['qos'] = qos_by_name[si['qos']]
    else:
        si['qos'] = default_qos
    del (si['switch'])
    return si


def normalize_sis(svc):
    #normalized_sis=[]
    #ret_svc=
    for s in svc:
        for si in s['si']:
            si=normalize_si(si)
            if "reserveSI" in si:
                si["reserveSI"]=normalize_si(si["reserveSI"])
        if ("reserveSI" in s.keys()) and (s["type"] == "p2p"):
            s["si"].append(normalize_si(s["reserveSI"]))
    #normalized_sis.append(s)
    return svc

def normalize_interfaces(svc):
    """populate rows or src/dst"""
    if svc['type']=='p2p':
        svc['obj']['src'] = svc['si'][0]['id']
        svc['obj']['dst'] = svc['si'][1]['id']
        if "hasReserve" in svc['obj'].keys():
            if svc['obj']["hasReserve"] == True:
                svc['obj']["reserveSI"] = svc['si'][2]['id']
    elif svc['type']=='m2m':
        for si in svc['si']:
            new_si={}
            if "defaultInterface" in si.keys():
                new_si['defaultInterface'] = si['defaultInterface']
            else:
                new_si["defaultInterface"] = False
            if 'qos' in si.keys():
                new_si['qos'] = si['qos']
            else:
                new_si['qos'] = default_qos
            new_si['si']=si['id']
            # here
            if "reserveSI" in si.keys():
                new_si["reserveSI"] = si["reserveSI"]
            svc['obj']['rows'].append(new_si)
    elif svc['type'] == 'p2m':
        for si in svc['si']:
            new_si = {}
            if "defaultInterface" in si.keys():
                new_si['defaultInterface'] = si['defaultInterface']
            else:
                new_si["defaultInterface"] = False
            if 'qos' in si.keys():
                new_si['qos'] = si['qos']
            else:
                new_si['qos'] = default_qos
            if "role" in si.keys():
                new_si['role'] = si['role']
            else:
                new_si["role"] = "LEAF"
            new_si['si'] = si['id']
            if "reserveSI" in si.keys():
                new_si["reserveSI"] = si["reserveSI"]
            svc['obj']['rows'].append(new_si)
    return(svc)

def get_si_by_object(obj):
    ports=c.get_switch(obj['commutatorId'])
    for port in ports:
        if port["port"] == obj["port"]:
            if obj["tagType"] == "VLAN":
                if str(port["vlan"]) == str(obj["vlan"]):
                    return port['id']
            elif obj["tagType"] == 'DOUBLE_VLAN':
                if str(port["vlan"]) == str(obj["vlan"]) and str(port['secondVlan']) == str(obj['secondVlan']):
                    return port['id']

def add_services_with_sis():
    norm_sis = normalize_sis(flat_cfg)
    norm_svcs = normalize_services(flat_cfg)
    for n_svc in range(len(norm_svcs)):
        logger.info("Adding service %s/%s (%s%%)", n_svc+1,len(norm_svcs),int(float((n_svc+1))/float(len(norm_svcs))*100))
        for ifacenum in range(len(norm_svcs[n_svc]['si'])):
            logger.debug("    Adding SI %s/%s",  ifacenum+1 , len(norm_svcs[n_svc]['si']))
            if "reserveSI" in norm_svcs[n_svc]['si'][ifacenum]:
                logger.debug("    Adding Reserve for SI %s/%s", ifacenum + 1, len(norm_svcs[n_svc]['si']))
                ifc = c.add_si(cluster_id, norm_svcs[n_svc]['si'][ifacenum]["reserveSI"])
                ifaceid = ifc.json()[u'id']
                norm_svcs[n_svc]['si'][ifacenum]["reserveSI"]=ifaceid
            ifc=c.add_si(cluster_id,norm_svcs[n_svc]['si'][ifacenum])
            ifaceid=ifc.json()[u'id']
            norm_svcs[n_svc]['si'][ifacenum]['id']=ifaceid
        normalize_interfaces(norm_svcs[n_svc])
        if norm_svcs[n_svc]['type']=='p2p':
            c.add_p2p_service(cluster_id,norm_svcs[n_svc]['obj'])
        elif norm_svcs[n_svc]['type']=='m2m':
            c.add_m2m_service(cluster_id, norm_svcs[n_svc]['obj'])
        elif norm_svcs[n_svc]['type'] == 'p2m':
            c.add_p2m_service(cluster_id, norm_svcs[n_svc]['obj'])
    logger.debug("Services created\n %s\n" % pformat(norm_svcs))
    return(norm_svcs)

def get_all_services():
    existing_services={'p2p':[],'m2m':[],'p2m':[]}
    existing_services['p2p'] = c.get_p2p_services(cluster_id)
    existing_services['m2m'] = c.get_m2m_services(cluster_id)
    existing_services['p2m'] = c.get_p2m_services(cluster_id)
    for i in existing_services.keys():
        if existing_services[i]==None:
            existing_services[i]=[]
    return existing_services

def get_all_sis_of_cluster():
    switches=c.get_switches_of_cluster(cluster_id)
    ifs=[]
    for sw in switches:
        ifs.extend(c.get_switch(sw['id']))
    return ifs

def delete_all_unused_sis(sis):
    for si in range(len(sis)):
        logger.info("Delete SIs %s/%s",si,len(sis))
        c.del_si(sis[si]['id'])

def delete_sis(sis_list):
    for si in range(len(sis_list)):
        logger.info("Delete SIs %s/%s", si+1, len(sis_list))
        if sis_list[si] != None and 'id' in sis_list[si].keys():
            c.del_si(sis_list[si]["id"])

# Delete all services and unused SIs
def delete_all_services_with_sis():
    svcs=get_all_services()
    for svc in svcs['p2p']:
        logger.info("Delete P2P service %s", svc["name"])
        c.del_p2p_service(cluster_id,svc)
    for svc in svcs['m2m']:
        logger.info("Delete M2M service %s", svc["name"])
        c.del_m2m_service(cluster_id,svc)
    for svc in svcs['p2m']:
        logger.info("Delete P2M service %s", svc["name"])
        c.del_p2m_service(cluster_id,svc)
    logger.info("Get all SIs of cluster")
    all_sis=get_all_sis_of_cluster()
    logger.info("Delete all SIs of cluster")
    delete_all_unused_sis(all_sis)

def del_config_services_with_sis():
    """
    Delete services listed in configuration file.
    Only 'name' AND 'type' checked, other fields ignored
    """
    sis_to_delete=[]
    svcs = get_all_services()
    logger.info("Delete P2P services which name matches template")
    for svc in svcs['p2p']:
        for flatsvcitem in flat_cfg:
            if flatsvcitem['type'] == 'p2p' and flatsvcitem['name'] == svc['name']:
                sis_to_delete.append(svc['dst'])
                sis_to_delete.append(svc['src'])
                if 'reserveSI' in svc.keys():
                    sis_to_delete.append(svc['reserveSI'])
                logger.info("Delete P2P service %s" % svc['name'])
                c.del_p2p_service(cluster_id,svc)
    logger.info("Delete M2M services which name matches template")
    for svc in svcs['m2m']:
        for flatsvcitem in flat_cfg:
            if flatsvcitem['type'] == 'm2m' and flatsvcitem['name'] == svc['name']:
                for ifc in svc['rows']:
                    sis_to_delete.append(ifc['si'])
                    if 'reserveSI' in ifc.keys():
                        sis_to_delete.append(ifc['reserveSI'])
                logger.info("Delete M2M service %s" % svc['name'])
                c.del_m2m_service(cluster_id, svc)
    logger.info("Delete P2M services which name matches template")
    for svc in svcs['p2m']:
        for flatsvcitem in flat_cfg:
            if flatsvcitem['type'] == 'p2m' and flatsvcitem['name'] == svc['name']:
                for ifc in svc['rows']:
                    sis_to_delete.append(ifc['si'])
                    if 'reserveSI' in ifc.keys():
                        sis_to_delete.append(ifc['reserveSI'])
                logger.info("Delete P2M service %s" % svc['name'])
                c.del_p2m_service(cluster_id, svc)
    logger.info("Delete SIs of removed services")
    delete_sis(sis_to_delete)
    return

def get_switch_id_by_name(sw_name):
    for switch in switches:
        if switch['name']==sw_name:
            return str(switch['id'])

if __name__ == '__main__':
    #config is python'ed content of YAML configuration, then we resolve X-Y sentences to lists
    uniq = None
    flat_cfg = None
    c = None
    cluster_id = None
    default_qos = None
    qoslist = None
    qos_by_name = {}
    switches = None
    config = None
    args, config = parse_args()
    logger.debug("args: %s, config: %s", pformat(args), pformat(config))
    action = args.ACTION
    if action=="validate":
        logger.info("Validating configuration against controller. No changes enforced")
        compose_config()
        validate_cfg_against_controller()
    elif action=="del-all":
        logger.info("REMOVING ALL services and SIs from controller configuration")
        compose_config()
        validate_cfg_against_controller()
        delete_all_services_with_sis()
    elif action=="del":
        logger.info("REMOVING from controller configuration services and SIs listed in template")
        compose_config()
        validate_cfg_against_controller()
        del_config_services_with_sis()
    elif action=="add":
        logger.info("Adding services and SIs listed in template")
        compose_config()
        validate_cfg_against_controller()
        add_services_with_sis()
    else:
        logger.warning("Your arg didn't match any action. Possible actions are\n\n del-all  - Remove all configured services and SIs\n del  - Remove all services which name matches template\n add  - Add services from template\n")

