from urllib import urlencode
import json
import os
from geomancer.app_config import MANCER_KEYS
from geomancer.helpers import encoded_dict
from geomancer.mancers.geotype import State, StateFIPS
from geomancer.mancers.base import BaseMancer, MancerError
from string import punctuation
import re
from urlparse import urlparse
import us
import requests

class BureauLaborStatistics(BaseMancer):
    """ 
    Subclassing the main BaseMancer class
    """

    name = 'Bureau of Labor Statistics'
    machine_name = 'bureau_labor_statistics'
    base_url = 'http://api.bls.gov/publicAPI/v2/timeseries/data'
    info_url = 'http://www.bls.gov/'
    description = """ 
        Data from the Bureau of Labor Statistics
    """
    api_key_required = True

    # store the data for each column
    # b/c bls api has low limit & it doesn't take long to grab all states
    oes_column_data = {}
    # a mapping of bls oes series id data codes to geomancer column names
    oes_column_lookup = {   '13': '2014 Annual Wages - Median',
                            '12': '2014 Annual Wages - 25th Percentile',
                            '14': '2014 Annual Wages - 75th Percentile'}

    def __init__(self, api_key=None):
        self.api_key = MANCER_KEYS[self.machine_name]
        BaseMancer.__init__(self)

    def column_info(self):
        columns = [
            {
                'table_id': 'oes',
                'human_name': 'Occupational Employment Statistics',
                'description': 'Occupational Employment Statistics',
                'source_name': self.name,
                'source_url': '',  'http://www.bls.gov/oes/'
                'geo_types': [State(), StateFIPS()],
                'columns': ['2014 Annual Wages - Median', '2014 Annual Wages - 25th Percentile', '2014 Annual Wages - 75th Percentile'], # should median/25/75 be diff cols in same chunk or diff chunks? does it matter?
                'count': 3
            }

        return columns

    # given a search term, returns state fips code
    def lookup_state_name(self, term):
        st = us.states.lookup(term)
        if not st:
            st = [s for s in us.STATES if getattr(s, 'ap_abbr') == term]
        if st:
            return st.fips
        else:
            return search_term

    def bls_oes_series_id(self, geo_id, stat_id):
        # documentation on constructing series ids at http://www.bls.gov/help/hlpforma.htm#OE
        # geo_id is state FIPS code as string
        prefix = 'OEU'
        area_type = 'S'
        area_code = geo_id + '00000'
        industry_code = '000000' # this is the code for all industries
        occupation_code = '000000' # this is the code for all occupations
        datatype_code = stat_id

        return prefix+area_type+area_code+industry_code+occupation_code+datatype_code


    def geo_lookup(self, search_term, geo_type=None):
        regex = re.compile('[%s]' % re.escape(punctuation))
        search_term = regex.sub('', search_term)
        if geo_type == 'state' or geo_type == 'state_fips':
            return {'term': search_term, 'geoid': self.lookup_state_name(search_term)}
        else:
            return {'term': search_term, 'geoid': search_term}

    def grab_data(self, geo_ids=None):
        # geo_ids is a list of state fips code strings
        for col in self.oes_column_lookup:
            series_ids = []
            for geo_id in geo_ids:
                series_id = self.bls_oes_series_id(geo_id, col)
                series_ids.append(series_id)

            # make the request
            headers = {'Content-type': 'application/json'}
            data = json.dumps({"seriesid": series_ids,"startyear":"2014", "endyear":"2014", "registrationKey":self.api_key})
            p = requests.post('http://api.bls.gov/publicAPI/v2/timeseries/data/', data=data, headers=headers)
            json_data = json.loads(p.text)

            self.oes_column_data[col] = {}
            # loop through the json data and add it to oes_column_data[col][geo_id]
            for result in json_data['Results']['series']:
                # grab state id from results series id
                this_geo_id = result['seriesID'][4:6]
                this_val = result['data'][0]['value']
                self.oes_column_data[col][this_geo_id] = this_val


    def search(self, geo_ids=None, columns=None):
        # columns is a list consisting of table_ids from the possible values in column_info?
        results = {'header':[]}

        all_state_fips = ['01', '02', '04', '05', '06', '08', '09', '10',
              '12', '13', '15', '16', '17', '18', '19', '20', '21', '22',
              '23', '24', '25', '26', '27', '28', '29', '30', '31', '32', '33',
              '34', '35', '36', '37', '38', '39', '40', '41', '42', '44',
              '45', '46', '47', '48', '49', '50', '51', '53', '54', '55', '56']

        for table_id in columns:
            # currently oes is the only table id
            if table_id == 'oes':
                # only grab data when oes_column_data is not populated
                if len(self.oes_column_data)==0:
                    for col in self.oes_column_lookup:
                        self.oes_column_data[col] = {}

                    self.grab_data(all_state_fips)

                # looping through columns in OES data
                for col in self.oes_column_lookup:
                    results['header'].append(self.oes_column_lookup[col])

                    # compiling matched geo data for results
                    for geo_type, geo_id in geo_ids:
                        if not results.get(geo_id):
                            results[geo_id] = []
                        if geo_type == 'state' or geo_type =='state_fips':
                            results[geo_id].append(self.oes_column_data[col][geo_id])

        return results

