
try:
    from urllib2 import urlopen, quote
except:
    from urllib.request import urlopen, quote, Request
import json
import shutil
import os

class VeneerRetriever(object):
    '''
    Retrieve all information from a Veneer web service and write it out to disk in the same path structure.

    Typically used for creating/archiving static dashboards from an existing Veneer web application.
    '''
    def __init__(self,destination,port=9876,host='localhost',protocol='http',
                 retrieve_daily=True,retrieve_monthly=True,retrieve_annual=True,
                 retrieve_slim_ts=True,retrieve_single_ts=True,
                 retrieve_single_runs=True,retrieve_daily_for=[],
                 retrieve_ts_json=True,retrieve_ts_csv=False,
                 print_all = False, print_urls = False):
        from .general import Veneer,log
        self.destination = destination
        self.port = port
        self.host = host
        self.protocol = protocol
        self.retrieve_daily = retrieve_daily
        self.retrieve_monthly = retrieve_monthly
        self.retrieve_annual = retrieve_annual
        self.retrieve_slim_ts = retrieve_slim_ts
        self.retrieve_single_ts = retrieve_single_ts
        self.retrieve_single_runs = retrieve_single_runs
        self.retrieve_daily_for = retrieve_daily_for
        self.retrieve_ts_json=retrieve_ts_json
        self.retrieve_ts_csv=retrieve_ts_csv
        self.print_all = print_all
        self.print_urls = print_urls
        self.base_url = "%s://%s:%d" % (protocol,host,port)
        self._veneer = Veneer(host=self.host,port=self.port,protocol=self.protocol)
        self.log = log

    def mkdirs(self,directory):
        import os
        if not os.path.exists(directory):
            os.makedirs(directory)

    def save_data(self,base_name,data,ext,mode="b"):
        import os
        base_name = os.path.join(self.destination,base_name + "."+ext)
        directory = os.path.dirname(base_name)
        self.mkdirs(directory)
        f = open(base_name,"w"+mode)
        f.write(data)
        f.close()
    
    def retrieve_json(self,url,**kwargs):
        if self.print_urls:
            print("*** %s ***" % (url))
    
        try:
            text = urlopen(self.base_url + quote(url)).read().decode('utf-8')
        except:
            self.log("Couldn't retrieve %s"%url)
            return None

        self.save_data(url[1:],bytes(text,'utf-8'),"json")
    
        if self.print_all:
            print(json.loads(text))
            print("")
        return json.loads(text)
    
    def retrieve_csv(self,url):
        text = self._veneer.retrieve_csv(url)
        self.save_data(url[1:],bytes(text,'utf-8'),"csv")

    def retrieve_resource(self,url,ext):
        if self.print_urls:
            print("*** %s ***" % (url))
    
        self.save_data(url[1:],urlopen(self.base_url+quote(url)).read(),ext,mode="b")

    # Process Run list and results
    def retrieve_runs(self):
        run_list = self.retrieve_json("/runs")
        all_results = []
        for run in run_list:
            run_results = self.retrieve_json(run['RunUrl'])
            ts_results = run_results['Results']
            all_results += ts_results

            if not self.retrieve_single_runs:
                continue

            if self.retrieve_single_ts:
                for result in ts_results:
                    self.retrieve_ts(result['TimeSeriesUrl'])

            if self.retrieve_slim_ts:
                self.retrieve_multi_ts(ts_results)

        if self.retrieve_slim_ts and len(run_list):
            all_results = self.unique_results_across_runs(all_results)
            self.retrieve_multi_ts(all_results,run="__all__")
            self.retrieve_across_runs(all_results)

    def unique_results_across_runs(self,all_results):
        result = {}
        for ts in all_results:
            generic_url = self.translate_url(ts['TimeSeriesUrl'],run='__all__')
            if not generic_url in result:
                result[generic_url] = ts
        return result.values()

    def translate_url(self,orig,run=None,loc=None,elem=None,var=None):
        url = orig.split('/')
        if not run is None:
            url[2] = run
        if not loc is None:
            url[4] = loc
        if not elem is None:
            url[6] = elem
        if not var is None:
            url[8] = var
        return '/'.join(url)

    def retrieve_multi_ts(self,ts_results,run=None):
        recorders = list(set([(r['RecordingElement'],r['RecordingVariable']) for r in ts_results]))
        for r in recorders:
            for option in ts_results:
                if option['RecordingElement'] == r[0] and option['RecordingVariable'] == r[1]:
                    url = self.translate_url(option['TimeSeriesUrl'],run=run,loc='__all__')
                    self.retrieve_ts(url)
                    break

    def retrieve_across_runs(self,results_set):
        for option in results_set:
            url = self.translate_url(option['TimeSeriesUrl'],run='__all__')
            self.retrieve_ts(url)

    def retrieve_this_daily(self,ts_url):
        if self.retrieve_daily: return True

        splits = ts_url.split('/')
        run = splits[2]
        loc = splits[4]
        ele = splits[6]
        var = splits[8]

        for exception in self.retrieve_daily_for:
            matched = True
            for key,val in exception.items():
                if key=='NetworkElement' and val!=loc: 
                    matched=False;
                    break
                if key=='RecordingElement' and val!=ele:
                    matched=False;
                    break
                if key=='RecordingVariable' and val!=var:
                    matched=False;
                    break
            if matched: return True
        return False

    def retrieve_ts(self,ts_url):
        urls = []

        if self.retrieve_this_daily(ts_url):
            urls.append(ts_url)
        if self.retrieve_monthly:
            urls.append(ts_url + "/aggregated/monthly")
        if self.retrieve_annual:
            urls.append(ts_url + "/aggregated/annual")

        for url in urls:
            if self.retrieve_ts_json:
                self.retrieve_json(url)
            if self.retrieve_ts_csv:
                self.retrieve_csv(url)
    
    def retrieve_variables(self):
        variables = self.retrieve_json("/variables")
        for var in variables:
            if var['TimeSeries']: self.retrieve_json(var['TimeSeries'])
            if var['PiecewiseFunction']: self.retrieve_json(var['PiecewiseFunction'])

    def retrieve_all(self,clean=False):
        if os.path.exists(self.destination):
            if clean:
                shutil.rmtree(self.destination)
            else:
                raise Exception("Destination (%s) already exists. Use clean=True to overwrite"%self.destination)
        self.mkdirs(self.destination)
        self.retrieve_runs()
        self.retrieve_json("/functions")
        self.retrieve_variables()
        self.retrieve_json("/inputSets")
        self.retrieve_json("/")
        network = self.retrieve_json("/network")
        icons_retrieved = []
        for f in network['features']:
            #retrieve_json(f['id'])
            if not f['properties']['feature_type'] == 'node': continue
            if f['properties']['icon'] in icons_retrieved: continue
            self.retrieve_resource(f['properties']['icon'],'png')
            icons_retrieved.append(f['properties']['icon'])
