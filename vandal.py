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

def compose_config(config):
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
    return uniq, flat_cfg

def validate_cfg_against_controller():
    # begin interaction with orc
    logger.info("Validated generated configs against network configuration..")
    logger.info("Conneting to Orchestrator %s", config['orc']['url'])
    c = CtlAPI(config['orc']['url'], config['orc']['user'], config['orc']['pass'], logger=logger)
    logger.info("Connected. Getting clusters")
    clusters=c.get_clusters()
    logger.debug("Got clusters: %s", clusters)
    if len(clusters)<1:
        raise(Exception, "Clusters are not configured")
    logger.debug("Number of clusters: %s", len(clusters))
    if len(clusters) > 1:
        logger.warning("There is more than one cluster! We hope we are in luck")
    cluster_id=clusters[0]['id']
    logger.info("Current cluster ID: %s", cluster_id)
    logger.info("Checking if QoS configured - we need at least one profile")
    qos_profiles = c.get_qos(clusters[0]['id'])
    if len(qos_profiles) == 1:
        logger.debug("QOS is already configured %s", qos_profiles)
    elif len(qos_profiles) == 0:
        logger.warning("QOS Rules not configured: %s", qos_profiles)
    elif len(qos_profiles) > 1:
        logger.warning("Multiple QOS Rules configured: %s", qos_profiles)
        logger.warning("We-ll use first rule: %s", qos_profiles[0])
    qos=qos_profiles[0]
    logger.debug("Current QOS profile: %s", qos)
    logger.info("Getting switches configurations...")
    switches=c.get_switches_of_cluster(cluster_id)
    logger.debug("Got switches: %s", pformat(switches))
    logger.info("%s switches there", len((switches)))
    check_switches(uniq,switches)
    return c, cluster_id, qos, switches

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
    newsvc=[]
    for s in svc:
        if s['type']=='p2p':
            s['obj']={"tunnelType": "STATIC", "pathfinding": "SHORTEST_PATH", "symmetry": "SYMMETRIC", "name": s['name'],
               "src": None, "dst": None,
               "qos": qos['id']}
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

def normalize_sis(svc):
    #normalized_sis=[]
    for s in svc:
        for si in s['si']:
            if 'secondVlan' in si.keys():
                si['tagType']="DOUBLE_VLAN"
            elif "vlan" in si.keys():
                si['tagType'] ="VLAN"
            else:
                logger.warning("SI doesn't contain neither vlan nor second Vlan, so we can't assign tagType. UNTAGGED ifaces not supported")
            si["commutatorId"]=get_switch_id_by_name(si['switch'])
            del(si['switch'])
    #normalized_sis.append(s)
    return svc

def normalize_interfaces(svc):
    if svc['type']=='p2p':
        svc['obj']['src'] = svc['si'][0]['id']
        svc['obj']['dst'] = svc['si'][1]['id']
    elif svc['type']=='m2m':
        for si in svc['si']:
            new_si={}
            if "defaultInterface" in si.keys():
                new_si['defaultInterface'] = si['defaultInterface']
            else:
                new_si["defaultInterface"] = False
            new_si['qos']=qos
            new_si['si']=si['id']
            svc['obj']['rows'].append(new_si)
    elif svc['type'] == 'p2m':
        for si in svc['si']:
            new_si = {}
            if "defaultInterface" in si.keys():
                new_si['defaultInterface'] = si['defaultInterface']
            else:
                new_si["defaultInterface"] = False
            if "role" in si.keys():
                new_si['role'] = si['role']
            else:
                new_si["role"] = "LEAF"
            new_si['qos'] = qos
            new_si['si'] = si['id']
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

def add_services_with_sis(flat_services_config, thread_id):
    norm_sis = normalize_sis(flat_services_config)
    norm_svcs = normalize_services(norm_sis)
    for n_svc in range(len(norm_svcs)):
        logger.info("Thread%s: Adding service %s/%s (%s%%)", thread_id, n_svc+1,len(norm_svcs),int(float((n_svc+1))/float(len(norm_svcs))*100))
        for ifacenum in range(len(norm_svcs[n_svc]['si'])):
            ifc=c.add_si(cluster_id,norm_svcs[n_svc]['si'][ifacenum])
            #pprint.pprint(ifc.json())
            ifaceid=ifc.json()[u'id']
            #ifaceid=get_si_by_object(norm_svcs[n_svc]['si'][ifacenum])
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

# Delete all services and unused SIs
def delete_all_services_with_sis():
    svcs=get_all_services()
    for svc in svcs['p2p']:
        c.del_p2p_service(cluster_id,svc)
    for svc in svcs['m2m']:
        c.del_m2m_service(cluster_id,svc)
    for svc in svcs['p2m']:
        c.del_p2m_service(cluster_id,svc)
    all_sis=get_all_sis_of_cluster()
    delete_all_unused_sis(all_sis)

def get_switch_id_by_name(sw_name):
    for switch in switches:
        if switch['name']==sw_name:
            return str(switch['id'])

def split_list_to_chunks(in_list, num_chunks):
    if num_chunks>len(in_list):
        num_chunks=len(in_list)
    out_list = []
    for l in range(num_chunks):
        out_list.append([])
    while True:
        for out_l in range(num_chunks):
            try:
                item=in_list.pop(0)
                out_list[out_l].append(item)
            except:
                return out_list
    return out_list

def thread_task():
    pass

if __name__ == '__main__':
    #config is python'ed content of YAML configuration, then we resolve X-Y sentences to lists
    args, config = parse_args()
    logger.debug("args: %s, config: %s", pformat(args), pformat(config))
    action = args.ACTION
    if action=="validate":
        logger.info("Validating configuration against controller. No changes enforced")
        uniq, flat_cfg = compose_config(config)
        c, cluster_id, qos, switches = validate_cfg_against_controller()
    elif action=="clear-all":
        logger.info("REMOVING ALL services and SIs from controller configuration")
        uniq, flat_cfg = compose_config(config)
        c, cluster_id, qos, switches = validate_cfg_against_controller()
        delete_all_services_with_sis()
    elif action=="del":
        logger.info("REMOVING from controller configuration services and SIs listed in template")
        logger.info("NOT IMPLEMENTED YET. Does the same as clear-all")
        uniq, flat_cfg = compose_config(config)
        c, cluster_id, qos, switches = validate_cfg_against_controller()
        delete_all_services_with_sis()
    elif action=="add":
        logger.info("Re-adding (REMOVING and ADDING) services and SIs listed in template")
        logger.info("NOT IMPLEMENTED YET. TOTALLY REMOVES ALL SERVICES AND ADDS SIS from template")
        uniq, flat_cfg = compose_config(config)
        c, cluster_id, qos, switches = validate_cfg_against_controller()
        #delete_all_services_with_sis()
        #add_services_with_sis(flat_cfg)
        #
        # TODO threading goes here - need to reuse
        threads=1
        q = Queue.Queue()
        flcfg_chunked=split_list_to_chunks(flat_cfg,threads)
        threads_obj = []
        try:
            for thread_id in range(len(flcfg_chunked)):
                t = threading.Thread(target=add_services_with_sis, args=([flcfg_chunked.pop(),thread_id]))
                t.start()
                threads_obj.append(t)
                while time.sleep(1):
                    alive=0
                    for u in threads_obj:
                        if u.is_alive():
                            alive += 1
                            print "waiting thread %s" % u
                    print "%s alive" % alive
                    if alive == 0:
                        exit()
        except (KeyboardInterrupt, SystemExit):
            logger.info('\n! Received keyboard interrupt, quitting threads.\n Please wait ~30 seconds')
            os.kill(os.getpid(), signal.SIGTERM)
    else:
        logger.warning("Your arg didn't match any action. Possible actions are\n\n validate\n clear-all\n del\n add\n")

