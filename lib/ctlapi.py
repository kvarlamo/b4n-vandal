#!/usr/bin/env python
import requests
import json
import logging
logger = logging.getLogger(__name__)

class CtlAPI:
    def __init__(self, baseurl, login, password, **kwargs):
        if 'logger' in kwargs:
            self.logger=kwargs['logger']
            logging.getLogger("requests").setLevel(self.logger.level)
            logging.getLogger("urllib3").setLevel(self.logger.level)
        else:
            self.logger=logger
            logging.getLogger("requests").setLevel(logging.WARNING)
            logging.getLogger("urllib3").setLevel(logging.WARNING)
        self.baseurl = baseurl
        self.login = login
        self.password = password
        self.client = requests.session()
        self.get_csrf_token()
        login_data = dict(j_username=self.login, j_password=self.password)
        self.logger.debug("Login as %s :" % self.login)
        self.r = self.client.post(self.baseurl + "api/authentication", data=login_data, headers={'Referer':self.baseurl, 'X-CSRF-TOKEN':self.csrf})
        self.logger.debug("HTTP_Resp:%s" , self.r.status_code)
    def post(self, url, request):
        self.url = url
        self.request = json.dumps(request).encode('utf8')
        self.get_csrf_token()
        self.logger.debug("POST %s%s %s " % (self.baseurl, self.url, self.request))
        self.r = self.client.post(self.baseurl + self.url, data=self.request, headers={"content-type": "application/json;charset=utf-8", 'X-CSRF-TOKEN': self.csrf})
        self.logger.debug("HTTP_Resp:%s" % self.r.status_code)
    def delete(self, url):
        self.url = url
        self.get_csrf_token()
        self.logger.debug("DELETE %s%s " % (self.baseurl, self.url))
        self.r = self.client.delete(self.baseurl + self.url, headers={"content-type": "application/json;charset=utf-8", 'X-CSRF-TOKEN': self.csrf})
        self.logger.debug("HTTP_Resp:%s %s" % (self.r.status_code, self.r.text))
    def get(self, url):
        self.url = url
        #self.get_csrf_token()
        self.logger.debug("GET %s%s " % (self.baseurl, self.url))
        self.r = self.client.get(self.baseurl + self.url, headers={"content-type": "application/json;charset=utf-8", 'X-CSRF-TOKEN': self.csrf})
        self.logger.debug("HTTP_Resp:%s %s" % (self.r.status_code, self.r.text))
        return(self.r.json())
    def put(self, url, request):
        self.url = url
        self.request = json.dumps(request).encode('utf8')
        #self.get_csrf_token()
        self.logger.debug("PUT %s%s %s " % (self.baseurl, self.url, self.request))
        self.r = self.client.put(self.baseurl + self.url, self.request, headers={"content-type": "application/json;charset=utf-8", 'X-CSRF-TOKEN': self.csrf})
    def get_csrf_token(self):
        self.logger.debug("GET CSRF Token at %s " % self.baseurl)
        self.r = self.client.get(self.baseurl)
        self.logger.debug("HTTP_Resp:%s " % self.r.status_code)
        self.csrf = self.r.cookies['CSRF-TOKEN']
        self.logger.debug("Token:%s" % self.csrf)
    def get_clusters(self):
        return self.get('api/clusters')
    def get_switches_of_cluster(self, cluster_id):
        return self.get("api/cluster/%s/commutators?page=1&size=15" % cluster_id)['content']
    def get_switch(self,sw_id):
        return self.get("api/si/commutator?commutatorId=%s" % sw_id)
    def get_p2p_services(self,cluster_id):
        res=self.get("api/cluster/%s/p2PTunnels?page=1&size=15" % cluster_id)
        if 'content' in res.keys():
            return res['content']
    def get_m2m_services(self, cluster_id):
        res=self.get("api/cluster/%s/m2m?page=1&size=15" % cluster_id)
        if 'content' in res.keys():
            return res['content']
    def get_p2m_services(self, cluster_id):
        res = self.get("api/cluster/%s/p2m?page=1&size=15" % cluster_id)
        if 'content' in res.keys():
            return res['content']
    def get_qos(self, cluster_id):
        return self.get("api/cluster/%s/qos?page=1&size=15" % cluster_id)['content']
    def add_si(self, cluster_id, iface_object):
        return self.post("api/si?clusterId=%s" % cluster_id,iface_object)
    def del_si(self,si_id):
        return self.delete("api/si/%s" % si_id)
    def add_p2p_service(self,cluster_id, obj):
        return self.post("api/cluster/%s/p2PTunnels" % cluster_id,obj)
    def del_p2p_service(self, cluster_id, obj):
        return self.delete("api/cluster/%s/p2PTunnels/%s" % (cluster_id, obj['id']))